#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import asyncio
import logging
import re
import time
import uuid
from copy import deepcopy

logger = logging.getLogger(__name__)
from datetime import datetime
from functools import partial
from timeit import default_timer as timer
from langfuse import Langfuse
from peewee import fn
from api.db.services.file_service import FileService
from common.constants import LLMType, ParserType, StatusEnum
from api.db.db_models import DB, Dialog
from api.db.services.common_service import CommonService
from api.db.services.doc_metadata_service import DocMetadataService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.langfuse_service import TenantLangfuseService
from api.db.services.llm_service import LLMBundle
from api.db.services.memory_service import MemoryService
from common.metadata_utils import apply_meta_data_filter
from api.utils.reference_metadata_utils import (
    enrich_chunks_with_document_metadata,
    resolve_reference_metadata_preferences,
)
from api.db.services.tenant_llm_service import TenantLLMService
from api.db.joint_services.memory_message_service import query_message
from api.db.joint_services.tenant_model_service import get_model_config_by_id, get_model_config_by_type_and_name, get_tenant_default_model_by_type
from common.misc_utils import thread_pool_exec
from common.time_utils import current_timestamp, datetime_format
from common.text_utils import normalize_arabic_digits
from rag.graphrag.general.mind_map_extractor import MindMapExtractor
from rag.advanced_rag import DeepResearcher
from rag.app.tag import label_question
from rag.nlp.search import index_name
from rag.prompts.generator import chunks_format, citation_prompt, cross_languages, full_question, kb_prompt, keyword_extraction, message_fit_in, memory_prompt, PROMPT_JINJA_ENV, ASK_SUMMARY
from common.token_utils import num_tokens_from_string
from rag.utils.tavily_conn import Tavily
from rag.utils.tts_cache import synthesize_with_cache
from common.string_utils import remove_redundant_spaces
from common import settings

def _chunk_kb_id_for_doc(row_dict, kb_ids, doc_id):
    if len(kb_ids or []) == 1:
        return kb_ids[0]
    return row_dict.get("kb_id") or row_dict.get("kb_id_kwd")


async def _hydrate_chunk_vectors(retriever, chunks, tenant_ids, kb_ids):
    """
    Citation prep: on the ES backend the main retrieval call deliberately
    skips fetching the chunk embedding. insert_citations needs it, so we
    pull the vectors for just the candidate chunks right before computing
    answer-vs-chunk similarity. Chunks without an ES chunk_id (e.g. web
    search results) keep whatever placeholder they were given. Other
    backends still carry vectors in the chunk, so we skip the round-trip.
    """
    if settings.DOC_ENGINE_INFINITY or settings.DOC_ENGINE_OCEANBASE:
        return
    if not chunks:
        return
    dim = 0
    for ck in chunks:
        v = ck.get("vector")
        if isinstance(v, list) and v:
            dim = len(v)
            break
    if not dim:
        return
    # Skip chunks that already have a non-zero vector (e.g. parent chunks
    # produced by retrieval_by_children copy the child vector inline).
    chunk_ids = []
    for ck in chunks:
        cid = ck.get("chunk_id")
        if not cid:
            continue
        v = ck.get("vector") or []
        if any(x for x in v):
            continue
        chunk_ids.append(cid)
    if not chunk_ids:
        return
    try:
        vectors = await retriever.fetch_chunk_vectors(chunk_ids, tenant_ids, kb_ids, dim)
    except Exception as e:  # noqa: BLE001 - degrade gracefully on hydrate failure
        logger.warning("fetch_chunk_vectors failed; citations will use placeholders: %s", e)
        return
    if not vectors:
        return
    for ck in chunks:
        cid = ck.get("chunk_id")
        if cid and cid in vectors:
            ck["vector"] = vectors[cid]

def _normalize_internet_flag(value):
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off", ""}:
            return False
    return None


def _should_use_web_search(prompt_config, internet=None):
    if not prompt_config.get("tavily_api_key"):
        return False
    normalized = _normalize_internet_flag(internet)
    return normalized is True


def _resolve_reference_metadata(config, request_payload=None):
    return resolve_reference_metadata_preferences(request_payload or {}, config)


def _enrich_chunks_with_document_metadata(chunks, metadata_fields=None):
    enrich_chunks_with_document_metadata(chunks, metadata_fields)



class DialogService(CommonService):
    model = Dialog

    @classmethod
    def save(cls, **kwargs):
        """Save a new record to database.

        This method creates a new record in the database with the provided field values,
        forcing an insert operation rather than an update.

        Args:
            **kwargs: Record field values as keyword arguments.

        Returns:
            Model instance: The created record object.
        """
        sample_obj = cls.model(**kwargs).save(force_insert=True)
        return sample_obj

    @classmethod
    def update_many_by_id(cls, data_list):
        """Update multiple records by their IDs.

        This method updates multiple records in the database, identified by their IDs.
        It automatically updates the update_time and update_date fields for each record.

        Args:
            data_list (list): List of dictionaries containing record data to update.
                             Each dictionary must include an 'id' field.
        """
        with DB.atomic():
            for data in data_list:
                data["update_time"] = current_timestamp()
                data["update_date"] = datetime_format(datetime.now())
                cls.model.update(data).where(cls.model.id == data["id"]).execute()

    @classmethod
    @DB.connection_context()
    def get_list(cls, tenant_id, page_number, items_per_page, orderby, desc, id, name):
        chats = cls.model.select()
        if id:
            chats = chats.where(cls.model.id == id)
        if name:
            chats = chats.where(cls.model.name == name)
        chats = chats.where((cls.model.tenant_id == tenant_id) & (cls.model.status == StatusEnum.VALID.value))
        if desc:
            chats = chats.order_by(cls.model.getter_by(orderby).desc())
        else:
            chats = chats.order_by(cls.model.getter_by(orderby).asc())

        chats = chats.paginate(page_number, items_per_page)

        return list(chats.dicts())

    @classmethod
    @DB.connection_context()
    def get_by_tenant_ids(
        cls,
        joined_tenant_ids,
        user_id,
        page_number,
        items_per_page,
        orderby,
        desc,
        keywords,
        id=None,
        name=None,
    ):
        from api.db.db_models import User

        fields = [
            cls.model.id,
            cls.model.tenant_id,
            cls.model.name,
            cls.model.description,
            cls.model.language,
            cls.model.llm_id,
            cls.model.llm_setting,
            cls.model.prompt_type,
            cls.model.prompt_config,
            cls.model.similarity_threshold,
            cls.model.vector_similarity_weight,
            cls.model.top_n,
            cls.model.top_k,
            cls.model.do_refer,
            cls.model.rerank_id,
            cls.model.kb_ids,
            cls.model.icon,
            cls.model.status,
            User.nickname,
            User.avatar.alias("tenant_avatar"),
            cls.model.update_time,
            cls.model.create_time,
        ]
        dialogs = (
            cls.model.select(*fields)
            .join(User, on=(cls.model.tenant_id == User.id))
            .where(
                (cls.model.tenant_id.in_(joined_tenant_ids) | (cls.model.tenant_id == user_id)) & (cls.model.status == StatusEnum.VALID.value),
            )
        )
        if id:
            dialogs = dialogs.where(cls.model.id == id)
        if name:
            dialogs = dialogs.where(cls.model.name == name)
        if keywords:
            dialogs = dialogs.where(fn.LOWER(cls.model.name).contains(keywords.lower()))
        if desc:
            dialogs = dialogs.order_by(cls.model.getter_by(orderby).desc())
        else:
            dialogs = dialogs.order_by(cls.model.getter_by(orderby).asc())

        count = dialogs.count()

        if page_number and items_per_page:
            dialogs = dialogs.paginate(page_number, items_per_page)

        return list(dialogs.dicts()), count

    @classmethod
    @DB.connection_context()
    def get_all_dialogs_by_tenant_id(cls, tenant_id):
        fields = [cls.model.id]
        dialogs = cls.model.select(*fields).where(cls.model.tenant_id == tenant_id)
        dialogs.order_by(cls.model.create_time.asc())
        offset, limit = 0, 100
        res = []
        while True:
            d_batch = dialogs.offset(offset).limit(limit)
            _temp = list(d_batch.dicts())
            if not _temp:
                break
            res.extend(_temp)
            offset += limit
        return res

    @classmethod
    @DB.connection_context()
    def get_null_tenant_llm_id_row(cls):
        fields = [cls.model.id, cls.model.tenant_id, cls.model.llm_id]
        objs = cls.model.select(*fields).where(cls.model.tenant_llm_id.is_null())
        return list(objs)

    @classmethod
    @DB.connection_context()
    def get_null_tenant_rerank_id_row(cls):
        fields = [cls.model.id, cls.model.tenant_id, cls.model.rerank_id]
        objs = cls.model.select(*fields).where(cls.model.tenant_rerank_id.is_null())
        return list(objs)


async def async_chat_solo(dialog, messages, stream=True, **kwargs):
    llm_type = TenantLLMService.llm_id2llm_type(dialog.llm_id)
    pure_llm_route = kwargs.get("_pure_llm_route", False)
    if pure_llm_route:
        latest_user = next((m for m in reversed(messages) if m.get("role") == "user"), messages[-1])
        messages = [latest_user]
    attachments = ""
    image_attachments = []
    image_files = []
    if "files" in messages[-1]:
        if llm_type == "chat":
            text_attachments, image_attachments = split_file_attachments(messages[-1]["files"])
        else:
            text_attachments, image_files = split_file_attachments(messages[-1]["files"], raw=True)
        attachments = "\n\n".join(text_attachments)

    if dialog.llm_id:
        model_config = get_model_config_by_type_and_name(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)
    elif dialog.tenant_llm_id:
        model_config = get_model_config_by_id(dialog.tenant_llm_id)
    else:
        model_config = get_tenant_default_model_by_type(dialog.tenant_id, LLMType.CHAT)

    chat_mdl = LLMBundle(dialog.tenant_id, model_config)
    factory = model_config.get("llm_factory", "") if model_config else ""

    prompt_config = deepcopy(dialog.prompt_config or {})
    if pure_llm_route:
        prompt_config["system"] = PURE_LLM_SYSTEM_PROMPT
        prompt_config["quote"] = False
        prompt_config["reasoning"] = False
    tts_mdl = None
    if prompt_config.get("tts"):
        default_tts_model = get_tenant_default_model_by_type(dialog.tenant_id, LLMType.TTS)
        tts_mdl = LLMBundle(dialog.tenant_id, default_tts_model)
    msg = [{"role": m["role"], "content": re.sub(r"##\d+\$\$", "", m["content"])} for m in messages if m["role"] != "system"]
    if attachments and msg:
        msg[-1]["content"] += attachments
    if llm_type == "chat" and image_attachments:
        convert_last_user_msg_to_multimodal(msg, image_attachments, factory)
    gen_conf = deepcopy(dialog.llm_setting or {})
    if pure_llm_route:
        gen_conf["reasoning"] = False
        gen_conf["reasoning_effort"] = "none"
    elif dialog.prompt_config.get("reasoning", False) or kwargs.get("reasoning"):
        gen_conf["reasoning"] = True
    if stream:
        if llm_type == "chat":
            stream_iter = chat_mdl.async_chat_streamly_delta(prompt_config.get("system", ""), msg, gen_conf)
        else:
            stream_iter = chat_mdl.async_chat_streamly_delta(prompt_config.get("system", ""), msg, gen_conf, images=image_files)
        async for kind, value, state in _stream_with_think_delta(stream_iter):
            if kind == "marker":
                flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                yield {"answer": "", "reference": {}, "audio_binary": None, "prompt": "", "created_at": time.time(), "final": False, **flags}
                continue
            yield {"answer": value, "reference": {}, "audio_binary": tts(tts_mdl, value), "prompt": "", "created_at": time.time(), "final": False}
    else:
        if llm_type == "chat":
            answer = await chat_mdl.async_chat(prompt_config.get("system", ""), msg, gen_conf)
        else:
            answer = await chat_mdl.async_chat(prompt_config.get("system", ""), msg, gen_conf, images=image_files)
        user_content = msg[-1].get("content", "[content not available]")
        logging.debug("User: {}|Assistant: {}".format(user_content, answer))
        yield {"answer": answer, "reference": {}, "audio_binary": tts(tts_mdl, answer), "prompt": "", "created_at": time.time()}


def get_models(dialog):
    embd_mdl, chat_mdl, rerank_mdl, tts_mdl = None, None, None, None
    kbs = KnowledgebaseService.get_by_ids(dialog.kb_ids)
    embedding_list = list(set([kb.embd_id for kb in kbs]))
    if len(embedding_list) > 1:
        raise Exception("**ERROR**: Knowledge bases use different embedding models.")

    if embedding_list:
        embd_owner_tenant_id = kbs[0].tenant_id
        embd_model_config = get_model_config_by_type_and_name(embd_owner_tenant_id, LLMType.EMBEDDING, embedding_list[0])
        embd_mdl = LLMBundle(embd_owner_tenant_id, embd_model_config)
        if not embd_mdl:
            raise LookupError("Embedding model(%s) not found" % embedding_list[0])

    if dialog.llm_id:
        chat_model_config = get_model_config_by_type_and_name(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)
    elif dialog.tenant_llm_id:
        chat_model_config = get_model_config_by_id(dialog.tenant_llm_id)
    else:
        chat_model_config = get_tenant_default_model_by_type(dialog.tenant_id, LLMType.CHAT)

    chat_mdl = LLMBundle(dialog.tenant_id, chat_model_config)

    if dialog.rerank_id:
        rerank_model_config = get_model_config_by_type_and_name(dialog.tenant_id, LLMType.RERANK, dialog.rerank_id)
        rerank_mdl = LLMBundle(dialog.tenant_id, rerank_model_config)

    if dialog.prompt_config.get("tts"):
        default_tts_model_config = get_tenant_default_model_by_type(dialog.tenant_id, LLMType.TTS)
        tts_mdl = LLMBundle(dialog.tenant_id, default_tts_model_config)
    return kbs, embd_mdl, rerank_mdl, chat_mdl, tts_mdl


def split_file_attachments(files: list[dict] | None, raw: bool = False) -> tuple[list[str], list[str] | list[dict]]:
    if not files:
        return [], []

    text_attachments = []
    if raw:
        file_contents, image_files = FileService.get_files(files, raw=True)
        for content in file_contents:
            if not isinstance(content, str):
                content = str(content)
            text_attachments.append(content)
        return text_attachments, image_files

    image_attachments = []
    for content in FileService.get_files(files, raw=False):
        if not isinstance(content, str):
            content = str(content)
        if content.strip().startswith("data:"):
            image_attachments.append(content.strip())
            continue
        text_attachments.append(content)
    return text_attachments, image_attachments


_DATA_URI_RE = re.compile(r"^data:(?P<mime>[^;]+);base64,(?P<b64>[A-Za-z0-9+/=\s]+)$")


def _parse_data_uri_or_b64(s: str, default_mime: str = "image/png") -> tuple[str, str]:
    s = (s or "").strip()
    match = _DATA_URI_RE.match(s)
    if match:
        mime = match.group("mime").strip()
        b64 = match.group("b64").strip()
        return mime, b64
    return default_mime, s


def _normalize_text_from_content(content) -> str:
    if content is None:
        return ""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for blk in content:
            if isinstance(blk, dict):
                if blk.get("type") in {"text", "input_text"}:
                    txt = blk.get("text")
                    if txt:
                        texts.append(str(txt))
                elif "text" in blk and isinstance(blk.get("text"), (str, int, float)):
                    texts.append(str(blk["text"]))
        return "\n".join(texts).strip()
    return str(content)


def convert_last_user_msg_to_multimodal(msg: list[dict], image_data_uris: list[str], factory: str) -> None:
    if not msg or not image_data_uris:
        return

    factory_norm = (factory or "").strip().lower()

    for idx in range(len(msg) - 1, -1, -1):
        if msg[idx].get("role") != "user":
            continue

        original_content = msg[idx].get("content", "")
        text = _normalize_text_from_content(original_content)

        if factory_norm == "gemini":
            parts = []
            if text:
                parts.append({"text": text})
            for image in image_data_uris:
                mime, b64 = _parse_data_uri_or_b64(str(image), default_mime="image/png")
                parts.append({"inline_data": {"mime_type": mime, "data": b64}})
            msg[idx]["content"] = parts
            return

        if factory_norm == "anthropic":
            blocks = []
            if text:
                blocks.append({"type": "text", "text": text})
            for image in image_data_uris:
                mime, b64 = _parse_data_uri_or_b64(str(image), default_mime="image/png")
                blocks.append(
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": mime, "data": b64},
                    }
                )
            msg[idx]["content"] = blocks
            return

        multimodal_content = []
        if isinstance(original_content, list):
            multimodal_content = deepcopy(original_content)
        else:
            text_content = "" if original_content is None else str(original_content)
            if text_content:
                multimodal_content.append({"type": "text", "text": text_content})

        for data_uri in image_data_uris:
            image_url = data_uri
            if not isinstance(image_url, str):
                image_url = str(image_url)
            if not image_url.startswith("data:"):
                image_url = f"data:image/png;base64,{image_url}"
            multimodal_content.append({"type": "image_url", "image_url": {"url": image_url}})

        msg[idx]["content"] = multimodal_content
        return


BAD_CITATION_PATTERNS = [
    re.compile(r"\(\s*ID\s*[: ]*\s*(\d+)\s*\)"),  # (ID: 12)
    re.compile(r"\[\s*ID\s*[: ]*\s*(\d+)\s*\]"),  # [ID: 12]
    re.compile(r"【\s*ID\s*[: ]*\s*(\d+)\s*】"),  # 【ID: 12】
    re.compile(r"ref\s*(\d+)", flags=re.IGNORECASE),  # ref12、REF 12
]
CITATION_MARKER_PATTERN = re.compile(
    r"(?:\[(?:ID:)?([0-9\u0660-\u0669\u06F0-\u06F9]+)\]|"
    r"【(?:ID:)?([0-9\u0660-\u0669\u06F0-\u06F9]+)】|"
    r"\(\s*ID\s*[: ]\s*([0-9\u0660-\u0669\u06F0-\u06F9]+)\s*\))"
)


def citation_match_index(match: re.Match):
    for group in match.groups():
        if group:
            return int(group)
    return None


TABLE_SEPARATOR_ROW_PATTERN = re.compile(r"^\s*\|?\s*:?-{3,}:?\s*(?:\|\s*:?-{3,}:?\s*)+\|?\s*$")


def normalize_markdown_table_citations(answer: str):
    """Move citations away from markdown table separator rows so GFM tables render."""
    if not answer:
        return answer

    lines = answer.splitlines(keepends=True)
    pending_markers = ""
    normalized_lines = []

    for line in lines:
        newline = ""
        body = line
        if body.endswith("\r\n"):
            body, newline = body[:-2], "\r\n"
        elif body.endswith("\n"):
            body, newline = body[:-1], "\n"

        markers = " ".join(match.group(0) for match in CITATION_MARKER_PATTERN.finditer(body))
        body_without_markers = CITATION_MARKER_PATTERN.sub("", body).rstrip()

        if markers and TABLE_SEPARATOR_ROW_PATTERN.match(body_without_markers):
            target_index = next(
                (
                    i
                    for i in range(len(normalized_lines) - 1, -1, -1)
                    if normalized_lines[i].strip() and not normalized_lines[i].lstrip().startswith("|")
                ),
                None,
            )
            if target_index is None:
                pending_markers = f"{pending_markers} {markers}".strip()
            else:
                target_line = normalized_lines[target_index]
                target_newline = ""
                target_body = target_line
                if target_body.endswith("\r\n"):
                    target_body, target_newline = target_body[:-2], "\r\n"
                elif target_body.endswith("\n"):
                    target_body, target_newline = target_body[:-1], "\n"
                normalized_lines[target_index] = f"{target_body.rstrip()} {markers}{target_newline}"
            normalized_lines.append(body_without_markers + newline)
            continue

        if pending_markers and body.strip():
            body = f"{body.rstrip()} {pending_markers}"
            pending_markers = ""

        normalized_lines.append(body + newline)

    if pending_markers and normalized_lines:
        normalized_lines[-1] = normalized_lines[-1].rstrip() + f" {pending_markers}"

    return "".join(normalized_lines)


def build_compact_reference(answer: str, kbinfos: dict, idx: set):
    chunks = kbinfos.get("chunks") or []
    cited_chunk_indexes = [int(i) for i in sorted(idx) if 0 <= int(i) < len(chunks)]
    if not cited_chunk_indexes:
        return answer, {"chunks": [], "doc_aggs": []}

    old_to_new = {old_index: new_index for new_index, old_index in enumerate(cited_chunk_indexes)}

    def replace_marker(match: re.Match):
        old_index = citation_match_index(match)
        if old_index in old_to_new:
            return f"[ID:{old_to_new[old_index]}]"
        return match.group(0)

    answer = CITATION_MARKER_PATTERN.sub(replace_marker, answer)
    compact_chunks = [deepcopy(chunks[i]) for i in cited_chunk_indexes]
    attach_raptor_source_chunks(compact_chunks, kbinfos.get("tenant_ids", []), kbinfos.get("kb_ids", []))
    for chunk in compact_chunks:
        if chunk.get("vector"):
            del chunk["vector"]
        if "content" not in chunk:
            chunk["content"] = chunk.get("content_with_weight", "")
        chunk["document_id"] = chunk.get("document_id") or chunk.get("doc_id", "")
        chunk["document_name"] = chunk.get("document_name") or chunk.get("docnm_kwd", "")
        kb_id = chunk.get("kb_id")
        chunk["dataset_id"] = chunk.get("dataset_id") or ((kb_id or [""])[0] if isinstance(kb_id, list) else kb_id or "")

    cited_doc_ids = {chunk.get("doc_id") for chunk in compact_chunks if chunk.get("doc_id")}
    refs = {
        "chunks": compact_chunks,
        "doc_aggs": [d for d in kbinfos.get("doc_aggs", []) if d.get("doc_id") in cited_doc_ids],
    }
    return answer, refs


def is_raptor_summary_chunk(chunk: dict):
    return chunk.get("raptor_kwd") == "raptor" or chunk.get("raptor_layer_int") is not None


def _evidence_terms(text: str):
    if not text:
        return set()
    return set(re.findall(r"[\w\u4e00-\u9fff]{2,}", text.lower()))


def attach_raptor_source_chunks(chunks: list[dict], tenant_ids: list[str], kb_ids: list[str], max_sources: int = 3):
    source_cache = {}

    for chunk in chunks:
        if not is_raptor_summary_chunk(chunk):
            chunk["is_raptor_summary"] = False
            continue

        chunk["is_raptor_summary"] = True
        doc_id = chunk.get("doc_id")
        if not doc_id or not tenant_ids:
            chunk["source_chunks"] = []
            continue

        cache_key = (doc_id, tuple(kb_ids or []))
        if cache_key not in source_cache:
            source_cache[cache_key] = list(
                settings.retriever.chunk_list(
                    doc_id,
                    tenant_ids[0],
                    kb_ids,
                    max_count=256,
                    fields=[
                        "docnm_kwd",
                        "content_with_weight",
                        "img_id",
                        "position_int",
                        "page_num_int",
                        "top_int",
                        "doc_id",
                        "kb_id",
                        "raptor_kwd",
                        "raptor_layer_int",
                    ],
                    sort_by_position=True,
                )
            )

        summary_terms = _evidence_terms(chunk.get("content_with_weight", ""))
        candidates = []
        for source in source_cache[cache_key]:
            if source.get("raptor_kwd") == "raptor" or source.get("raptor_layer_int") is not None:
                continue
            source_terms = _evidence_terms(source.get("content_with_weight", ""))
            score = len(summary_terms & source_terms)
            if score <= 0:
                continue
            candidates.append((score, source))

        candidates.sort(key=lambda item: item[0], reverse=True)
        chunk["source_chunks"] = [
            {
                "content": source.get("content_with_weight", ""),
                "document_name": source.get("docnm_kwd", chunk.get("docnm_kwd", "")),
                "document_id": source.get("doc_id", doc_id),
                "image_id": source.get("img_id", ""),
                "positions": source.get("position_int", []),
                "page_num": source.get("page_num_int"),
            }
            for _, source in candidates[:max_sources]
        ]


def repair_bad_citation_formats(answer: str, kbinfos: dict, idx: set):
    max_index = len(kbinfos["chunks"])
    normalized_answer = normalize_arabic_digits(answer) or ""

    def safe_add(i):
        if 0 <= i < max_index:
            idx.add(i)
            return True
        return False

    def find_and_replace(pattern, group_index=1, repl=lambda digits: f"ID:{digits}"):
        nonlocal answer
        nonlocal normalized_answer

        matches = list(pattern.finditer(normalized_answer))
        if not matches:
            return

        parts = []
        last_idx = 0
        for match in matches:
            parts.append(answer[last_idx : match.start()])
            try:
                i = int(match.group(group_index))
            except Exception:
                parts.append(answer[match.start() : match.end()])
                last_idx = match.end()
                continue

            if safe_add(i):
                digit_start, digit_end = match.span(group_index)
                digits_original = answer[digit_start:digit_end]
                parts.append(f"[{repl(digits_original)}]")
            else:
                parts.append(answer[match.start() : match.end()])
            last_idx = match.end()

        parts.append(answer[last_idx:])
        answer = "".join(parts)
        normalized_answer = normalize_arabic_digits(answer) or ""

    for pattern in BAD_CITATION_PATTERNS:
        find_and_replace(pattern)

    return answer, idx


def append_fallback_citations(answer: str, kbinfos: dict, max_refs: int = 3):
    chunks = kbinfos.get("chunks") or []
    if not answer or not chunks:
        return answer, set()

    citation_count = min(max_refs, len(chunks))
    markers = " ".join(f"[ID:{i}]" for i in range(citation_count))
    stripped_answer = answer.rstrip()
    trailing = answer[len(stripped_answer):]
    punctuation = re.search(r"([。！？.!?])$", stripped_answer)
    if punctuation:
        pos = punctuation.start(1)
        cited_answer = f"{stripped_answer[:pos]} {markers}{stripped_answer[pos:]}"
    else:
        cited_answer = f"{stripped_answer} {markers}"
    return cited_answer + trailing, set(range(citation_count))


ERROR_HISTORY_PATTERNS = (
    "**ERROR**:",
    "ERROR:",
    "ApiError(",
    "Traceback (most recent call last)",
    "search_phase_execution_exception",
    "CUDA error",
    "invalid_request_error",
    "知识库中未找到您要的答案",
    "知识库内容为空",
)
THINK_BLOCK_PATTERN = re.compile(r"<think>[\s\S]*?</think>", flags=re.IGNORECASE)


def _is_error_history_message(message: dict) -> bool:
    if message.get("role") != "assistant":
        return False
    content = message.get("content") or ""
    if not isinstance(content, str):
        content = str(content)
    return any(pattern in content for pattern in ERROR_HISTORY_PATTERNS)


def _sanitize_chat_history(messages: list[dict]) -> list[dict]:
    """Drop generated errors and strip assistant reasoning before retrieval/prompting."""
    sanitized = []
    for message in messages:
        if _is_error_history_message(message):
            continue
        if message.get("role") == "assistant" and isinstance(message.get("content"), str):
            message = deepcopy(message)
            message["content"] = THINK_BLOCK_PATTERN.sub("", message["content"]).strip()
        sanitized.append(message)
    if sanitized and sanitized[-1].get("role") == "user":
        return sanitized
    latest_user = next((m for m in reversed(messages) if m.get("role") == "user"), None)
    if latest_user:
        sanitized.append(latest_user)
    return sanitized or messages


MODEL_SELF_QUESTION_PATTERNS = (
    "你是谁",
    "你是什么",
    "你叫什么",
    "你是哪个模型",
    "什么模型",
    "模型参数",
    "多少参数",
    "上下文多长",
    "支持多长上下文",
    "和deepseek r1",
    "和 deepseek r1",
    "和r1",
    "和 r1",
)

GENERAL_CHAT_PATTERNS = (
    "你好",
    "您好",
    "谢谢",
    "讲个笑话",
    "你能做什么",
)

EXPLICIT_KB_INTENT_PATTERNS = (
    "根据",
    "参考",
    "知识库",
    "文档",
    "文件",
    "pdf",
    "报告",
    "资料",
    "附件",
    "这份",
    "这个报告",
    "该报告",
    "上面",
    "刚才",
)

CONTEXT_DEPENDENT_PATTERNS = (
    "它",
    "他",
    "她",
    "这个",
    "那个",
    "这些",
    "那些",
    "上述",
    "上面",
    "前面",
    "刚才",
    "其中",
    "该报告",
    "这个报告",
    "继续",
)

MAX_RETRIEVAL_QUERY_CHARS = 512
DEFAULT_MODEL_CONTEXT_TOKENS = 8192
DEEPSEEK_V4_CONTEXT_TOKENS = 131072
MIN_OUTPUT_TOKENS = 1
DEFAULT_OUTPUT_TOKENS = 512
MEMORY_CONTEXT_TOKENS = 2048
MAX_MEMORY_RESULTS = 5
MAX_MEMORY_GROUPS = 4
MAX_KNOWLEDGE_CONTEXT_RATIO = 0.70
MAX_PROMPT_CONTEXT_RATIO = 0.95
PURE_LLM_SYSTEM_PROMPT = """你是 Panython / RightTime 本地部署的 DeepSeek V4 Flash 智能助手。

当前请求已被判定为普通聊天或模型自身相关问题，不要检索知识库，不要引用 PDF、文档、Fig. 或来源片段。
请直接、简洁地回答用户当前问题。回答身份、模型、能力、上下文等问题时，应说明你是本地部署的 DeepSeek V4 Flash 服务；不要声称自己是 Kimi、OpenAI、ChatGPT 或其他模型。

You are the locally deployed DeepSeek V4 Flash assistant served by Panython / RightTime.
For general chat or model-self questions, answer directly without knowledge-base citations or document references."""


def _normalize_route_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


def _should_route_to_pure_llm(latest_question: str, kwargs: dict) -> tuple[bool, str]:
    if kwargs.get("doc_ids"):
        return False, "explicit_doc_ids"

    normalized = _normalize_route_text(latest_question)
    if not normalized:
        return False, "empty_question"

    if any(pattern in normalized for pattern in EXPLICIT_KB_INTENT_PATTERNS):
        return False, "explicit_kb_intent"

    if any(pattern in normalized for pattern in MODEL_SELF_QUESTION_PATTERNS):
        return True, "model_self_question"

    if any(pattern in normalized for pattern in GENERAL_CHAT_PATTERNS) and len(normalized) <= 24:
        return True, "general_chat"

    return False, "default_kb_route"


def _question_depends_on_history(latest_question: str) -> bool:
    normalized = _normalize_route_text(latest_question)
    return any(pattern in normalized for pattern in CONTEXT_DEPENDENT_PATTERNS)


def _build_retrieval_query(question: str) -> str:
    normalized = re.sub(r"\s+", " ", (question or "").strip())
    if len(normalized) <= MAX_RETRIEVAL_QUERY_CHARS:
        return normalized
    return normalized[:MAX_RETRIEVAL_QUERY_CHARS]


def _safe_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _resolve_model_context_tokens(llm_model_config: dict | None, dialog) -> int:
    configured_tokens = _safe_positive_int((llm_model_config or {}).get("max_tokens"), DEFAULT_MODEL_CONTEXT_TOKENS)
    llm_name = " ".join(
        str(v or "")
        for v in (
            getattr(dialog, "llm_id", ""),
            (llm_model_config or {}).get("llm_name"),
            (llm_model_config or {}).get("model_name"),
        )
    ).lower()
    if "deepseek-v4" in llm_name or "deepseek v4" in llm_name:
        configured_tokens = max(configured_tokens, DEEPSEEK_V4_CONTEXT_TOKENS)
    return configured_tokens


def _resolve_output_tokens(llm_setting: dict | None) -> int:
    return _safe_positive_int((llm_setting or {}).get("max_tokens"), DEFAULT_OUTPUT_TOKENS)


def _resolve_context_budgets(llm_model_config: dict | None, dialog) -> dict[str, int]:
    model_context_tokens = _resolve_model_context_tokens(llm_model_config, dialog)
    output_tokens = min(_resolve_output_tokens(getattr(dialog, "llm_setting", None)), max(MIN_OUTPUT_TOKENS, model_context_tokens - MIN_OUTPUT_TOKENS))
    prompt_tokens = max(MIN_OUTPUT_TOKENS, model_context_tokens - output_tokens)
    return {
        "model": model_context_tokens,
        "output": output_tokens,
        "prompt": prompt_tokens,
        "knowledge": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * MAX_KNOWLEDGE_CONTEXT_RATIO)),
        "fit": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * MAX_PROMPT_CONTEXT_RATIO)),
    }


def _group_accessible_memories_for_query(tenant_id: str) -> list[list[str]]:
    memories, _ = MemoryService.get_by_filter({"accessible_user_id": tenant_id}, "", page=1, page_size=50)
    grouped: dict[tuple[str, str], list[str]] = {}
    for memory in memories:
        key = (str(memory.get("tenant_embd_id") or ""), str(memory.get("embd_id") or ""))
        grouped.setdefault(key, []).append(memory["id"])
    return list(grouped.values())[:MAX_MEMORY_GROUPS]


async def _retrieve_memory_context(tenant_id: str, query: str, token_budget: int = MEMORY_CONTEXT_TOKENS) -> list[str]:
    if not query:
        return []
    try:
        memory_groups = await thread_pool_exec(_group_accessible_memories_for_query, tenant_id)
    except Exception as exc:  # noqa: BLE001 - memory should not break chat
        logging.warning("MemoryContext failed to list accessible memories: %s", exc)
        return []
    if not memory_groups:
        return []

    memory_messages = []
    for memory_ids in memory_groups:
        try:
            matches = await thread_pool_exec(
                query_message,
                {"memory_id": memory_ids},
                {
                    "query": query,
                    "similarity_threshold": 0.2,
                    "keywords_similarity_weight": 0.3,
                    "top_n": MAX_MEMORY_RESULTS,
                },
            )
        except Exception as exc:  # noqa: BLE001 - degrade if a memory index is absent or incompatible
            logging.warning("MemoryContext query failed for memories=%s: %s", memory_ids, exc)
            continue
        for message in matches or []:
            content = message.get("content") if isinstance(message, dict) else None
            if content:
                memory_messages.append({"content": str(content)})
            if len(memory_messages) >= MAX_MEMORY_RESULTS:
                break
        if len(memory_messages) >= MAX_MEMORY_RESULTS:
            break

    if not memory_messages:
        return []
    return memory_prompt(memory_messages, token_budget)


async def async_chat(dialog, messages, stream=True, **kwargs):
    logging.debug("Begin async_chat")
    assert messages[-1]["role"] == "user", "The last content of this conversation is not from user."
    messages = _sanitize_chat_history(messages)
    use_web_search = _should_use_web_search(dialog.prompt_config, kwargs.get("internet"))
    logging.debug("web_search kb=%s tavily=%s internet=%r enabled=%s", bool(dialog.kb_ids), bool(dialog.prompt_config.get("tavily_api_key")), kwargs.get("internet"), use_web_search)
    latest_question = next((m.get("content", "") for m in reversed(messages) if m.get("role") == "user"), "")
    pure_llm_route, route_reason = _should_route_to_pure_llm(latest_question, kwargs)
    if dialog.kb_ids and pure_llm_route and not use_web_search:
        logging.info("QueryPlanner route=pure_llm reason=%s question=%s", route_reason, latest_question[:120])
        async for ans in async_chat_solo(dialog, messages, stream, _pure_llm_route=True, **kwargs):
            yield ans
        return
    if not dialog.kb_ids and not use_web_search:
        async for ans in async_chat_solo(dialog, messages, stream, **kwargs):
            yield ans
        return

    chat_start_ts = timer()
    llm_type = TenantLLMService.llm_id2llm_type(dialog.llm_id)
    if llm_type == "image2text":
        llm_model_config = TenantLLMService.get_model_config(dialog.tenant_id, LLMType.IMAGE2TEXT, dialog.llm_id)
    else:
        llm_model_config = TenantLLMService.get_model_config(dialog.tenant_id, LLMType.CHAT, dialog.llm_id)

    factory = llm_model_config.get("llm_factory", "") if llm_model_config else ""
    context_budget = _resolve_context_budgets(llm_model_config, dialog)
    max_tokens = context_budget["model"]
    logging.debug(
        "ContextBudget model=%s prompt=%s knowledge=%s fit=%s output=%s llm_id=%s",
        context_budget["model"],
        context_budget["prompt"],
        context_budget["knowledge"],
        context_budget["fit"],
        context_budget["output"],
        dialog.llm_id,
    )

    check_llm_ts = timer()

    langfuse_tracer = None
    langfuse_generation = None
    trace_context = {}
    langfuse_keys = TenantLangfuseService.filter_by_tenant(tenant_id=dialog.tenant_id)
    if langfuse_keys:
        langfuse = Langfuse(public_key=langfuse_keys.public_key, secret_key=langfuse_keys.secret_key, host=langfuse_keys.host)
        try:
            if langfuse.auth_check():
                langfuse_tracer = langfuse
                trace_id = langfuse_tracer.create_trace_id()
                trace_context = {"trace_id": trace_id}
        except Exception:
            # Skip langfuse tracing if connection fails
            pass

    check_langfuse_tracer_ts = timer()
    kbs, embd_mdl, rerank_mdl, chat_mdl, tts_mdl = get_models(dialog)
    toolcall_session, tools = kwargs.get("toolcall_session"), kwargs.get("tools")
    if toolcall_session and tools:
        chat_mdl.bind_tools(toolcall_session, tools)
    bind_models_ts = timer()

    retriever = settings.retriever
    questions = [m["content"] for m in messages if m["role"] == "user"][-3:]
    attachments = None
    if "doc_ids" in kwargs:
        attachments = [doc_id for doc_id in kwargs["doc_ids"].split(",") if doc_id]
    attachments_ = ""
    image_attachments = []
    image_files = []
    if "doc_ids" in messages[-1]:
        attachments = [doc_id for doc_id in messages[-1]["doc_ids"] if doc_id]
    if "files" in messages[-1]:
        if llm_type == "chat":
            text_attachments, image_attachments = split_file_attachments(messages[-1]["files"])
        else:
            text_attachments, image_files = split_file_attachments(messages[-1]["files"], raw=True)
        attachments_ = "\n\n".join(text_attachments)

    prompt_config = dialog.prompt_config
    include_reference_metadata, metadata_fields = _resolve_reference_metadata(prompt_config, request_payload=kwargs)
    field_map = KnowledgebaseService.get_field_map(dialog.kb_ids)
    logging.debug(f"field_map retrieved: {field_map}")
    # try to use sql if field mapping is good to go
    if field_map:
        logging.debug("Use SQL to retrieval:{}".format(questions[-1]))
        ans = await use_sql(questions[-1], field_map, dialog.tenant_id, chat_mdl, prompt_config.get("quote", True), dialog.kb_ids)
        # For aggregate queries (COUNT, SUM, etc.), chunks may be empty but answer is still valid
        if ans and (ans.get("reference", {}).get("chunks") or ans.get("answer")):
            if include_reference_metadata and ans.get("reference", {}).get("chunks"):
                if len(dialog.kb_ids) != 1 and any(not c.get("kb_id") for c in ans["reference"]["chunks"]):
                    logging.warning(
                        "Skipping some _enrich_chunks_with_document_metadata results because "
                        "dialog.kb_ids has %d entries and use_sql returned chunks without kb_id.",
                        len(dialog.kb_ids),
                    )
                _enrich_chunks_with_document_metadata(ans["reference"]["chunks"], metadata_fields)
            yield ans
            return
        else:
            logging.debug("SQL failed or returned no results, falling back to vector search")

    param_keys = [p["key"] for p in prompt_config.get("parameters", [])]
    if dialog.kb_ids and "knowledge" not in param_keys and "{knowledge}" in prompt_config.get("system", ""):
        logging.warning("prompt_config['parameters'] is missing 'knowledge' entry despite kb_ids being set; auto-fixing.")
        prompt_config.setdefault("parameters", []).append({"key": "knowledge", "optional": False})
        param_keys.append("knowledge")
    logging.debug(f"attachments={attachments}, param_keys={param_keys}, embd_mdl={embd_mdl}")

    for p in prompt_config.get("parameters", []):
        if p["key"] == "knowledge":
            continue
        if p["key"] not in kwargs and not p["optional"]:
            raise KeyError("Miss parameter: " + p["key"])
        if p["key"] not in kwargs:
            prompt_config["system"] = prompt_config["system"].replace("{%s}" % p["key"], " ")

    latest_user_question = questions[-1] if questions else latest_question
    depends_on_history = _question_depends_on_history(latest_user_question)
    if len(questions) > 1 and prompt_config.get("refine_multiturn") and depends_on_history:
        questions = [await full_question(dialog.tenant_id, dialog.llm_id, messages)]
    else:
        questions = questions[-1:]

    if prompt_config.get("cross_languages"):
        questions = [await cross_languages(dialog.tenant_id, dialog.llm_id, questions[0], prompt_config["cross_languages"])]

    if dialog.meta_data_filter:
        attachments = await apply_meta_data_filter(
            dialog.meta_data_filter,
            None,
            questions[-1],
            chat_mdl,
            attachments,
            kb_ids=dialog.kb_ids,
            metas_loader=lambda: DocMetadataService.get_flatted_meta_by_kbs(dialog.kb_ids),
        )

    if prompt_config.get("keyword", False):
        questions[-1] = questions[-1] + "," + await keyword_extraction(chat_mdl, questions[-1])
    retrieval_query = _build_retrieval_query(questions[-1])
    refine_question_ts = timer()

    thought = ""
    kbinfos = {"total": 0, "chunks": [], "doc_aggs": []}
    knowledges = []
    deep_research_enabled = False

    if "knowledge" in param_keys:
        logging.debug("Proceeding with retrieval")
        deep_research_enabled = prompt_config.get("reasoning", False) or kwargs.get("reasoning")
        if not deep_research_enabled:
            query_preview = retrieval_query.replace("\n", " ").strip()[:160]
            yield {
                "answer": f"<retrieving>Analyzing the question.\nSearching datasets for: {query_preview}\n",
                "reference": {},
                "audio_binary": None,
                "final": False,
            }
        tenant_ids = list(set([kb.tenant_id for kb in kbs]))
        kbinfos["tenant_ids"] = tenant_ids
        kbinfos["kb_ids"] = dialog.kb_ids
        knowledges = []
        if deep_research_enabled:
            reasoner = DeepResearcher(
                chat_mdl,
                prompt_config,
                partial(
                    retriever.retrieval,
                    embd_mdl=embd_mdl,
                    tenant_ids=tenant_ids,
                    kb_ids=dialog.kb_ids,
                    page=1,
                    page_size=dialog.top_n,
                    similarity_threshold=0.2,
                    vector_similarity_weight=0.3,
                    doc_ids=attachments,
                ),
                internet_enabled=use_web_search,
            )
            queue = asyncio.Queue()

            async def callback(msg: str):
                nonlocal queue
                await queue.put(msg + "<br/>")

            await callback("<START_DEEP_RESEARCH>")
            task = asyncio.create_task(reasoner.research(kbinfos, questions[-1], questions[-1], callback=callback))
            while True:
                msg = await queue.get()
                if msg.find("<START_DEEP_RESEARCH>") == 0:
                    yield {"answer": "<retrieving>", "reference": {}, "audio_binary": None, "final": False}
                elif msg.find("<END_DEEP_RESEARCH>") == 0:
                    yield {"answer": "</retrieving>", "reference": {}, "audio_binary": None, "final": False}
                    break
                else:
                    yield {"answer": msg, "reference": {}, "audio_binary": None, "final": False}

            await task

        else:
            if embd_mdl:
                kbinfos = await retriever.retrieval(
                    retrieval_query,
                    embd_mdl,
                    tenant_ids,
                    dialog.kb_ids,
                    1,
                    dialog.top_n,
                    dialog.similarity_threshold,
                    dialog.vector_similarity_weight,
                    doc_ids=attachments,
                    top=dialog.top_k,
                    aggs=True,
                    rerank_mdl=rerank_mdl,
                    rank_feature=label_question(retrieval_query, kbs),
                )
                if prompt_config.get("toc_enhance"):
                    cks = await retriever.retrieval_by_toc(retrieval_query, kbinfos["chunks"], tenant_ids, chat_mdl, dialog.top_n)
                    if cks:
                        kbinfos["chunks"] = cks
                kbinfos["chunks"] = retriever.retrieval_by_children(kbinfos["chunks"], tenant_ids)
                yield {
                    "answer": (
                        f"Found {len(kbinfos.get('chunks', []))} relevant passages"
                        f" from {len(kbinfos.get('doc_aggs', []))} documents.\n"
                    ),
                    "reference": {},
                    "audio_binary": None,
                    "final": False,
                }
            if use_web_search:
                tav = Tavily(prompt_config["tavily_api_key"])
                tav_res = tav.retrieve_chunks(retrieval_query)
                kbinfos["chunks"].extend(tav_res["chunks"])
                kbinfos["doc_aggs"].extend(tav_res["doc_aggs"])
                yield {
                    "answer": f"Added {len(tav_res.get('chunks', []))} web search passages.\n",
                    "reference": {},
                    "audio_binary": None,
                    "final": False,
                }
            if prompt_config.get("use_kg"):
                default_chat_model = get_tenant_default_model_by_type(dialog.tenant_id, LLMType.CHAT)
                ck = await settings.kg_retriever.retrieval(retrieval_query, tenant_ids, dialog.kb_ids, embd_mdl, LLMBundle(dialog.tenant_id, default_chat_model))
                if ck["content_with_weight"]:
                    kbinfos["chunks"].insert(0, ck)
                    yield {"answer": "Added knowledge graph context.\n", "reference": {}, "audio_binary": None, "final": False}
        if not deep_research_enabled:
            yield {
                "answer": "Preparing retrieved evidence for answer generation.\n</retrieving>",
                "reference": {},
                "audio_binary": None,
                "final": False,
            }

    if include_reference_metadata:
        logging.debug(
            "reference_metadata enrichment enabled for async_chat: chunk_count=%d metadata_fields=%s",
            len(kbinfos.get("chunks", [])),
            metadata_fields,
        )
        _enrich_chunks_with_document_metadata(kbinfos.get("chunks", []), metadata_fields)

    knowledges = kb_prompt(kbinfos, context_budget["knowledge"])
    logging.debug("{}->{}".format(" ".join(questions), "\n->".join(knowledges)))
    memory_context = await _retrieve_memory_context(
        dialog.tenant_id,
        retrieval_query,
        min(MEMORY_CONTEXT_TOKENS, max(MIN_OUTPUT_TOKENS, context_budget["prompt"] // 10)),
    )
    if memory_context:
        logging.debug("MemoryContext injected %d snippets for tenant=%s", len(memory_context), dialog.tenant_id)

    retrieval_ts = timer()
    if not knowledges and prompt_config.get("empty_response"):
        empty_res = prompt_config["empty_response"]
        yield {"answer": empty_res, "reference": kbinfos, "prompt": "\n\n### Query:\n%s" % " ".join(questions), "audio_binary": tts(tts_mdl, empty_res), "final": True}
        return

    kwargs["knowledge"] = "\n------\n" + "\n\n------\n\n".join(knowledges)
    gen_conf = deepcopy(dialog.llm_setting or {})
    if prompt_config.get("reasoning", False) or kwargs.get("reasoning"):
        gen_conf["reasoning"] = True
    if "max_tokens" in gen_conf:
        gen_conf["max_tokens"] = context_budget["output"]

    memory_context_text = ""
    if memory_context:
        memory_context_text = "\n\n### Conversation memory:\n" + "\n".join(f"- {m}" for m in memory_context)

    msg = [{"role": "system", "content": prompt_config["system"].format(**kwargs) + memory_context_text + attachments_}]
    prompt4citation = ""
    if knowledges and (prompt_config.get("quote", True) and kwargs.get("quote", True)):
        prompt4citation = citation_prompt()
    msg.extend([{"role": m["role"], "content": re.sub(r"##\d+\$\$", "", m["content"])} for m in messages if m["role"] != "system"])
    original_message_count = len(msg)
    used_token_count, msg = message_fit_in(msg, context_budget["fit"])
    if len(msg) < original_message_count:
        logging.info(
            "ContextBudget trimmed chat history from %s to %s messages under fit_budget=%s",
            original_message_count,
            len(msg),
            context_budget["fit"],
        )
    if llm_type == "chat" and image_attachments:
        convert_last_user_msg_to_multimodal(msg, image_attachments, factory)
    assert len(msg) >= 2, f"message_fit_in has bug: {msg}"
    prompt = msg[0]["content"]

    if "max_tokens" in gen_conf:
        available_output_tokens = max(MIN_OUTPUT_TOKENS, max_tokens - used_token_count)
        gen_conf["max_tokens"] = max(MIN_OUTPUT_TOKENS, min(int(gen_conf["max_tokens"]), available_output_tokens))

    async def decorate_answer(answer):
        nonlocal embd_mdl, prompt_config, knowledges, kwargs, kbinfos, prompt, retrieval_ts, questions, langfuse_generation

        refs = []
        ans = answer.split("</think>")
        think = ""
        if len(ans) == 2:
            think = ans[0] + "</think>"
            answer = ans[1]

        if knowledges and (prompt_config.get("quote", True) and kwargs.get("quote", True)):
            idx = set([])
            normalized_answer = normalize_arabic_digits(answer) or ""
            if embd_mdl and not CITATION_MARKER_PATTERN.search(normalized_answer):
                # Main retrieval no longer ships chunk vectors back from ES.
                # Pull them on demand for the chunks we are about to cite.
                await _hydrate_chunk_vectors(retriever, kbinfos.get("chunks", []), tenant_ids, dialog.kb_ids)
                answer, idx = retriever.insert_citations(
                    answer,
                    [ck["content_ltks"] for ck in kbinfos["chunks"]],
                    [ck["vector"] for ck in kbinfos["chunks"]],
                    embd_mdl,
                    tkweight=1 - dialog.vector_similarity_weight,
                    vtweight=dialog.vector_similarity_weight,
                )
            else:
                for match in CITATION_MARKER_PATTERN.finditer(normalized_answer):
                    i = citation_match_index(match)
                    if i is not None and i < len(kbinfos["chunks"]):
                        idx.add(i)

            answer, idx = repair_bad_citation_formats(answer, kbinfos, idx)
            if not idx and kbinfos.get("chunks"):
                logging.warning(
                    "Citation insertion produced no markers; applying fallback citations for query=%s",
                    " ".join(questions),
                )
                answer, idx = append_fallback_citations(answer, kbinfos)
            answer = normalize_markdown_table_citations(answer)
            answer, refs = build_compact_reference(answer, kbinfos, idx)

        if answer.lower().find("invalid key") >= 0 or answer.lower().find("invalid api") >= 0:
            answer += " Please set LLM API-Key in 'User Setting -> Model providers -> API-Key'"
        finish_chat_ts = timer()

        total_time_cost = (finish_chat_ts - chat_start_ts) * 1000
        check_llm_time_cost = (check_llm_ts - chat_start_ts) * 1000
        check_langfuse_tracer_cost = (check_langfuse_tracer_ts - check_llm_ts) * 1000
        bind_embedding_time_cost = (bind_models_ts - check_langfuse_tracer_ts) * 1000
        refine_question_time_cost = (refine_question_ts - bind_models_ts) * 1000
        retrieval_time_cost = (retrieval_ts - refine_question_ts) * 1000
        generate_result_time_cost = (finish_chat_ts - retrieval_ts) * 1000

        tk_num = num_tokens_from_string(think + answer)
        prompt += "\n\n### Query:\n%s" % " ".join(questions)
        prompt = (
            f"{prompt}\n\n"
            "## Time elapsed:\n"
            f"  - Total: {total_time_cost:.1f}ms\n"
            f"  - Check LLM: {check_llm_time_cost:.1f}ms\n"
            f"  - Check Langfuse tracer: {check_langfuse_tracer_cost:.1f}ms\n"
            f"  - Bind models: {bind_embedding_time_cost:.1f}ms\n"
            f"  - Query refinement(LLM): {refine_question_time_cost:.1f}ms\n"
            f"  - Retrieval: {retrieval_time_cost:.1f}ms\n"
            f"  - Generate answer: {generate_result_time_cost:.1f}ms\n\n"
            "## Token usage:\n"
            f"  - Generated tokens(approximately): {tk_num}\n"
            f"  - Token speed: {int(tk_num / (generate_result_time_cost / 1000.0))}/s"
        )

        # Add a condition check to call the end method only if langfuse_generation exists
        if langfuse_generation is not None:
            langfuse_output = "\n" + re.sub(r"^.*?(### Query:.*)", r"\1", prompt, flags=re.DOTALL)
            langfuse_output = {"time_elapsed:": re.sub(r"\n", "  \n", langfuse_output), "created_at": time.time()}
            langfuse_generation.update(
                output=langfuse_output,
                usage_details={
                    "input": used_token_count,
                    "output": tk_num,
                    "total": used_token_count + tk_num,
                },
            )
            langfuse_generation.end()

        return {"answer": think + answer, "reference": refs, "prompt": re.sub(r"\n", "  \n", prompt), "created_at": time.time()}

    if langfuse_tracer:
        try:
            langfuse_generation = langfuse_tracer.start_observation(
                as_type="generation",
                trace_context=trace_context,
                name="chat",
                model=llm_model_config["llm_name"],
                input={"prompt": prompt, "prompt4citation": prompt4citation, "messages": msg},
            )
        except Exception as e:  # noqa: BLE001 - tracing must not break chat flow
            logger.warning("Langfuse start_observation failed; continuing without tracing: %s", e)
            langfuse_tracer = None
            langfuse_generation = None

    if stream:
        if "knowledge" in param_keys and not deep_research_enabled:
            yield {
                "answer": "<think>Reviewing retrieved evidence and composing the answer.\n</think>",
                "reference": {},
                "audio_binary": None,
                "final": False,
            }
        if llm_type == "chat":
            stream_iter = chat_mdl.async_chat_streamly_delta(prompt + prompt4citation, msg[1:], gen_conf)
        else:
            stream_iter = chat_mdl.async_chat_streamly_delta(prompt + prompt4citation, msg[1:], gen_conf, images=image_files)
        last_state = None
        async for kind, value, state in _stream_with_think_delta(stream_iter):
            last_state = state
            if kind == "marker":
                flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                yield {"answer": "", "reference": {}, "audio_binary": None, "final": False, **flags}
                continue
            yield {"answer": value, "reference": {}, "audio_binary": tts(tts_mdl, value), "final": False}
        full_answer = last_state.full_text if last_state else ""
        if full_answer:
            final = await decorate_answer(_extract_visible_answer(thought + full_answer))
            final["final"] = True
            final["audio_binary"] = None
            yield final
    else:
        if llm_type == "chat":
            answer = await chat_mdl.async_chat(prompt + prompt4citation, msg[1:], gen_conf)
        else:
            answer = await chat_mdl.async_chat(prompt + prompt4citation, msg[1:], gen_conf, images=image_files)
        user_content = msg[-1].get("content", "[content not available]")
        logging.debug("User: {}|Assistant: {}".format(user_content, answer))
        res = await decorate_answer(answer)
        res["audio_binary"] = tts(tts_mdl, answer)
        yield res

    return


async def use_sql(question, field_map, tenant_id, chat_mdl, quota=True, kb_ids=None):
    """Answer a natural-language question by generating and executing SQL against the document index.

    Detects the active document engine (Infinity, OceanBase, or Elasticsearch), asks the
    chat model to produce the appropriate SQL, injects a validated kb_id filter, executes
    the query, and returns formatted results with optional source citations.

    Args:
        question: Natural-language question from the user.
        field_map: Mapping of field names to types describing the indexed document schema.
        tenant_id: Tenant identifier used to derive the target index/table name.
        chat_mdl: LLM bundle used to generate SQL from the question.
        quota: Whether to enforce token-quota checks (default True).
        kb_ids: Optional list of knowledge-base UUIDs to restrict the query scope.

    Returns:
        A dict with keys ``answer`` (formatted response string), ``reference``
        (dict of supporting document chunks and doc_aggs), and ``prompt``
        (the system prompt used), or ``None`` if SQL generation or execution fails.
    """
    logging.debug(f"use_sql: Question: {question}")

    # Determine which document engine we're using
    if settings.DOC_ENGINE_INFINITY:
        doc_engine = "infinity"
    elif settings.DOC_ENGINE_OCEANBASE:
        doc_engine = "oceanbase"
    else:
        doc_engine = "es"

    def _assert_valid_uuid(value: str, label: str = "id") -> None:
        try:
            uuid.UUID(str(value))
        except (ValueError, AttributeError, TypeError):
            logger.warning("SQL injection guard rejected invalid %s value (length=%d)", label, len(str(value)))
            raise ValueError(f"Invalid {label} format: {value!r}")

    # Construct the full table name
    # For Elasticsearch: ragflow_{tenant_id} (kb_id is in WHERE clause)
    # For Infinity: ragflow_{tenant_id}_{kb_id} (each KB has its own table)
    base_table = index_name(tenant_id)
    if doc_engine == "infinity" and kb_ids and len(kb_ids) == 1:
        # Infinity: append kb_id to table name — validate before interpolating
        _assert_valid_uuid(kb_ids[0], "kb_id")
        table_name = f"{base_table}_{kb_ids[0]}"
        logging.debug(f"use_sql: Using Infinity table name: {table_name}")
    else:
        # Elasticsearch/OpenSearch: use base index name
        table_name = base_table
        logging.debug(f"use_sql: Using ES/OS table name: {table_name}")

    expected_doc_name_column = "docnm" if doc_engine == "infinity" else "docnm_kwd"

    def has_source_columns(columns):
        """Return True if the result set contains the columns needed to build source citations."""
        normalized_names = {str(col.get("name", "")).lower() for col in columns}
        return "doc_id" in normalized_names and bool({"docnm_kwd", "docnm"} & normalized_names)

    def is_aggregate_sql(sql_text):
        """Return True if *sql_text* contains an aggregate function (COUNT, SUM, AVG, MAX, MIN, DISTINCT)."""
        return bool(re.search(r"(count|sum|avg|max|min|distinct)\s*\(", (sql_text or "").lower()))

    def normalize_sql(sql):
        """Strip LLM artefacts from *sql* and return a clean, executable SQL string.

        Removes ``<think>`` reasoning blocks, Chinese reasoning markers, markdown
        code fences, and trailing semicolons that some engines reject.
        """
        logging.debug(f"use_sql: Raw SQL from LLM: {repr(sql[:500])}")
        # Remove think blocks if present (format: </think>...)
        sql = re.sub(r"</think>\n.*?\n\s*", "", sql, flags=re.DOTALL)
        sql = re.sub(r"思考\n.*?\n", "", sql, flags=re.DOTALL)
        # Remove markdown code blocks (```sql ... ```)
        sql = re.sub(r"```(?:sql)?\s*", "", sql, flags=re.IGNORECASE)
        sql = re.sub(r"```\s*$", "", sql, flags=re.IGNORECASE)
        # Remove trailing semicolon that ES SQL parser doesn't like
        return sql.rstrip().rstrip(";").strip()

    def add_kb_filter(sql):
        """Inject a validated kb_id WHERE filter into *sql* for ES/OceanBase engines.

        Infinity encodes the knowledge-base scope in the table name, so this
        function is a no-op for that engine.  All kb_id values are validated as
        canonical UUIDs before interpolation to prevent SQL injection.
        """
        # Add kb_id filter for ES/OS only (Infinity already has it in table name)
        if doc_engine == "infinity" or not kb_ids:
            return sql

        # Validate all kb_ids are UUIDs before interpolating into SQL
        for kid in kb_ids:
            _assert_valid_uuid(kid, "kb_id")

        # Build kb_filter: single KB or multiple KBs with OR
        if len(kb_ids) == 1:
            kb_filter = f"kb_id = '{kb_ids[0]}'"
        else:
            kb_filter = "(" + " OR ".join([f"kb_id = '{kid}'" for kid in kb_ids]) + ")"

        if "where " not in sql.lower():
            o = sql.lower().split("order by")
            if len(o) > 1:
                sql = o[0] + f" WHERE {kb_filter}  order by " + o[1]
            else:
                sql += f" WHERE {kb_filter}"
        elif "kb_id =" not in sql.lower() and "kb_id=" not in sql.lower():
            sql = re.sub(r"\bwhere\b ", f"where {kb_filter} and ", sql, flags=re.IGNORECASE)
        return sql

    def is_row_count_question(q: str) -> bool:
        """Return True if *q* is asking for a total row count of a dataset or table."""
        q = (q or "").lower()
        if not re.search(r"\bhow many rows\b|\bnumber of rows\b|\brow count\b", q):
            return False
        return bool(re.search(r"\bdataset\b|\btable\b|\bspreadsheet\b|\bexcel\b", q))

    # Generate engine-specific SQL prompts
    if doc_engine == "infinity":
        # Build Infinity prompts with JSON extraction context
        json_field_names = list(field_map.keys())
        row_count_override = f"SELECT COUNT(*) AS rows FROM {table_name}" if is_row_count_question(question) else None
        sys_prompt = """You are a Database Administrator. Write SQL for a table with JSON 'chunk_data' column.

JSON Extraction: json_extract_string(chunk_data, '$.FieldName')
Numeric Cast: CAST(json_extract_string(chunk_data, '$.FieldName') AS INTEGER/FLOAT)
NULL Check: json_extract_isnull(chunk_data, '$.FieldName') == false

RULES:
1. Use EXACT field names (case-sensitive) from the list below
2. For SELECT: include doc_id, docnm, and json_extract_string() for requested fields
3. For COUNT: use COUNT(*) or COUNT(DISTINCT json_extract_string(...))
4. Add AS alias for extracted field names
5. DO NOT select 'content' field
6. Only add NULL check (json_extract_isnull() == false) in WHERE clause when:
   - Question asks to "show me" or "display" specific columns
   - Question mentions "not null" or "excluding null"
   - Add NULL check for count specific column
   - DO NOT add NULL check for COUNT(*) queries (COUNT(*) counts all rows including nulls)
7. Output ONLY the SQL, no explanations"""
        user_prompt = """Table: {}
Fields (EXACT case): {}
{}
Question: {}
Write SQL using json_extract_string() with exact field names. Include doc_id, docnm for data queries. Only SQL.""".format(
            table_name, ", ".join(json_field_names), "\n".join([f"  - {field}" for field in json_field_names]), question
        )
    elif doc_engine == "oceanbase":
        # Build OceanBase prompts with JSON extraction context
        json_field_names = list(field_map.keys())
        row_count_override = f"SELECT COUNT(*) AS rows FROM {table_name}" if is_row_count_question(question) else None
        sys_prompt = """You are a Database Administrator. Write SQL for a table with JSON 'chunk_data' column.

JSON Extraction: json_extract_string(chunk_data, '$.FieldName')
Numeric Cast: CAST(json_extract_string(chunk_data, '$.FieldName') AS INTEGER/FLOAT)
NULL Check: json_extract_isnull(chunk_data, '$.FieldName') == false

RULES:
1. Use EXACT field names (case-sensitive) from the list below
2. For SELECT: include doc_id, docnm_kwd, and json_extract_string() for requested fields
3. For COUNT: use COUNT(*) or COUNT(DISTINCT json_extract_string(...))
4. Add AS alias for extracted field names
5. DO NOT select 'content' field
6. Only add NULL check (json_extract_isnull() == false) in WHERE clause when:
   - Question asks to "show me" or "display" specific columns
   - Question mentions "not null" or "excluding null"
   - Add NULL check for count specific column
   - DO NOT add NULL check for COUNT(*) queries (COUNT(*) counts all rows including nulls)
7. Output ONLY the SQL, no explanations"""
        user_prompt = """Table: {}
Fields (EXACT case): {}
{}
Question: {}
Write SQL using json_extract_string() with exact field names. Include doc_id, docnm_kwd for data queries. Only SQL.""".format(
            table_name, ", ".join(json_field_names), "\n".join([f"  - {field}" for field in json_field_names]), question
        )
    else:
        # Build ES/OS prompts with direct field access
        row_count_override = None
        sys_prompt = """You are a Database Administrator. Write SQL queries.

RULES:
1. Use EXACT field names from the schema below (e.g., product_tks, not product)
2. Quote field names starting with digit: "123_field"
3. Add IS NOT NULL in WHERE clause when:
   - Question asks to "show me" or "display" specific columns
4. Include doc_id/docnm in non-aggregate statement
5. Output ONLY the SQL, no explanations"""
        user_prompt = """Table: {}
Available fields:
{}
Question: {}
Write SQL using exact field names above. Include doc_id, docnm_kwd for data queries. Only SQL.""".format(table_name, "\n".join([f"  - {k} ({v})" for k, v in field_map.items()]), question)

    tried_times = 0

    async def get_table(custom_user_prompt=None):
        nonlocal sys_prompt, user_prompt, question, tried_times, row_count_override
        if row_count_override and custom_user_prompt is None:
            sql = row_count_override
        else:
            prompt = custom_user_prompt if custom_user_prompt is not None else user_prompt
            sql = await chat_mdl.async_chat(sys_prompt, [{"role": "user", "content": prompt}], {"temperature": 0.06})
        sql = normalize_sql(sql)
        sql = add_kb_filter(sql)

        logging.debug(f"{question} get SQL(refined): {sql}")
        tried_times += 1
        logging.debug(f"use_sql: Executing SQL retrieval (attempt {tried_times})")
        tbl = settings.retriever.sql_retrieval(sql, format="json")
        if tbl is None:
            logging.debug("use_sql: SQL retrieval returned None")
            return None, sql
        logging.debug(f"use_sql: SQL retrieval completed, got {len(tbl.get('rows', []))} rows")
        return tbl, sql

    async def repair_table_for_missing_source_columns(previous_sql):
        if doc_engine in ("infinity", "oceanbase"):
            json_field_names = list(field_map.keys())
            repair_prompt = """Table name: {};
JSON fields available in 'chunk_data' column (use exact names):
{}

Question: {}
Previous SQL:
{}

The previous SQL result is missing required source columns for citations.
Rewrite SQL to keep the same query intent and include doc_id and {} in the SELECT list.
For extracted JSON fields, use json_extract_string(chunk_data, '$.field_name').
Return ONLY SQL.""".format(table_name, "\n".join([f"  - {field}" for field in json_field_names]), question, previous_sql, expected_doc_name_column)
        else:
            repair_prompt = """Table name: {}
Available fields:
{}

Question: {}
Previous SQL:
{}

The previous SQL result is missing required source columns for citations.
Rewrite SQL to keep the same query intent and include doc_id and docnm_kwd in the SELECT list.
Return ONLY SQL.""".format(table_name, "\n".join([f"  - {k} ({v})" for k, v in field_map.items()]), question, previous_sql)
        return await get_table(custom_user_prompt=repair_prompt)

    try:
        tbl, sql = await get_table()
        logging.debug(f"use_sql: Initial SQL execution SUCCESS. SQL: {sql}")
        logging.debug(f"use_sql: Retrieved {len(tbl.get('rows', []))} rows, columns: {[c['name'] for c in tbl.get('columns', [])]}")
    except Exception as e:
        logging.warning(f"use_sql: Initial SQL execution FAILED with error: {e}")
        # Build retry prompt with error information
        if doc_engine in ("infinity", "oceanbase"):
            # Build Infinity error retry prompt
            json_field_names = list(field_map.keys())
            user_prompt = """
Table name: {};
JSON fields available in 'chunk_data' column (use these exact names in json_extract_string):
{}

Question: {}
Please write the SQL using json_extract_string(chunk_data, '$.field_name') with the field names from the list above. Only SQL, no explanations.


The SQL error you provided last time is as follows:
{}

Please correct the error and write SQL again using json_extract_string(chunk_data, '$.field_name') syntax with the correct field names. Only SQL, no explanations.
""".format(table_name, "\n".join([f"  - {field}" for field in json_field_names]), question, e)
        else:
            # Build ES/OS error retry prompt
            user_prompt = """
        Table name: {};
        Table of database fields are as follows (use the field names directly in SQL):
        {}

        Question are as follows:
        {}
        Please write the SQL using the exact field names above, only SQL, without any other explanations or text.


        The SQL error you provided last time is as follows:
        {}

        Please correct the error and write SQL again using the exact field names above, only SQL, without any other explanations or text.
        """.format(table_name, "\n".join([f"{k} ({v})" for k, v in field_map.items()]), question, e)
        try:
            tbl, sql = await get_table()
            logging.debug(f"use_sql: Retry SQL execution SUCCESS. SQL: {sql}")
            logging.debug(f"use_sql: Retrieved {len(tbl.get('rows', []))} rows on retry")
        except Exception:
            logging.error("use_sql: Retry SQL execution also FAILED, returning None")
            return

    if len(tbl["rows"]) == 0:
        logging.warning(f"use_sql: No rows returned from SQL query, returning None. SQL: {sql}")
        return None

    if not is_aggregate_sql(sql) and not has_source_columns(tbl.get("columns", [])):
        logging.warning(f"use_sql: Non-aggregate SQL missing required source columns; retrying once. SQL: {sql}")
        try:
            repaired_tbl, repaired_sql = await repair_table_for_missing_source_columns(sql)
            if repaired_tbl and len(repaired_tbl.get("rows", [])) > 0 and has_source_columns(repaired_tbl.get("columns", [])):
                tbl, sql = repaired_tbl, repaired_sql
                logging.info(f"use_sql: Source-column SQL repair succeeded. SQL: {sql}")
            else:
                logging.warning(f"use_sql: Source-column SQL repair did not provide required columns. Repaired SQL: {repaired_sql}")
        except Exception as e:
            logging.warning(f"use_sql: Source-column SQL repair failed, returning best-effort answer. Error: {e}")

    logging.debug(f"use_sql: Proceeding with {len(tbl['rows'])} rows to build answer")

    docid_idx = set([ii for ii, c in enumerate(tbl["columns"]) if c["name"].lower() == "doc_id"])
    doc_name_idx = set([ii for ii, c in enumerate(tbl["columns"]) if c["name"].lower() in ["docnm_kwd", "docnm"]])
    kb_id_idx = set([ii for ii, c in enumerate(tbl["columns"]) if c["name"].lower() in ["kb_id", "kb_id_kwd"]])

    logging.debug(f"use_sql: All columns: {[(i, c['name']) for i, c in enumerate(tbl['columns'])]}")
    logging.debug(f"use_sql: docid_idx={docid_idx}, doc_name_idx={doc_name_idx}, kb_id_idx={kb_id_idx}")

    column_idx = [ii for ii in range(len(tbl["columns"])) if ii not in (docid_idx | doc_name_idx | kb_id_idx)]

    logging.debug(f"use_sql: column_idx={column_idx}")
    logging.debug(f"use_sql: field_map={field_map}")

    # Helper function to map column names to display names
    def map_column_name(col_name):
        if col_name.lower() == "count(star)":
            return "COUNT(*)"

        # First, try to extract AS alias from any expression (aggregate functions, json_extract_string, etc.)
        # Pattern: anything AS alias_name
        as_match = re.search(r"\s+AS\s+([^\s,)]+)", col_name, re.IGNORECASE)
        if as_match:
            alias = as_match.group(1).strip("\"'")

            # Use the alias for display name lookup
            if alias in field_map:
                display = field_map[alias]
                return re.sub(r"(/.*|（[^（）]+）)", "", display)
            # If alias not in field_map, try to match case-insensitively
            for field_key, display_value in field_map.items():
                if field_key.lower() == alias.lower():
                    return re.sub(r"(/.*|（[^（）]+）)", "", display_value)
            # Return alias as-is if no mapping found
            return alias

        # Try direct mapping first (for simple column names)
        if col_name in field_map:
            display = field_map[col_name]
            # Clean up any suffix patterns
            return re.sub(r"(/.*|（[^（）]+）)", "", display)

        # Try case-insensitive match for simple column names
        col_lower = col_name.lower()
        for field_key, display_value in field_map.items():
            if field_key.lower() == col_lower:
                return re.sub(r"(/.*|（[^（）]+）)", "", display_value)

        # For aggregate expressions or complex expressions without AS alias,
        # try to replace field names with display names
        result = col_name
        for field_name, display_name in field_map.items():
            # Replace field_name with display_name in the expression
            result = result.replace(field_name, display_name)

        # Clean up any suffix patterns
        result = re.sub(r"(/.*|（[^（）]+）)", "", result)
        return result

    # compose Markdown table
    columns = "|" + "|".join([map_column_name(tbl["columns"][i]["name"]) for i in column_idx]) + ("|Source|" if docid_idx and doc_name_idx else "|")

    line = "|" + "|".join(["------" for _ in range(len(column_idx))]) + ("|------|" if docid_idx and docid_idx else "")

    # Build rows ensuring column names match values - create a dict for each row
    # keyed by column name to handle any SQL column order
    rows = []
    for row_idx, r in enumerate(tbl["rows"]):
        row_dict = {tbl["columns"][i]["name"]: r[i] for i in range(len(tbl["columns"])) if i < len(r)}
        if row_idx == 0:
            logging.debug(f"use_sql: First row data: {row_dict}")
        row_values = []
        for col_idx in column_idx:
            col_name = tbl["columns"][col_idx]["name"]
            value = row_dict.get(col_name, " ")
            row_values.append(remove_redundant_spaces(str(value)).replace("None", " "))
        # Add Source column with citation marker if Source column exists
        if docid_idx and doc_name_idx:
            row_values.append(f" ##{row_idx}$$")
        row_str = "|" + "|".join(row_values) + "|"
        if re.sub(r"[ |]+", "", row_str):
            rows.append(row_str)
    if quota:
        rows = "\n".join(rows)
    else:
        rows = "\n".join(rows)
    rows = re.sub(r"T[0-9]{2}:[0-9]{2}:[0-9]{2}(\.[0-9]+Z)?\|", "|", rows)

    if not docid_idx or not doc_name_idx:
        logging.warning(f"use_sql: SQL missing required doc_id or docnm_kwd field. docid_idx={docid_idx}, doc_name_idx={doc_name_idx}. SQL: {sql}")
        # For aggregate queries (COUNT, SUM, AVG, MAX, MIN, DISTINCT), fetch doc_id, docnm_kwd separately
        # to provide source chunks, but keep the original table format answer
        if is_aggregate_sql(sql):
            # Keep original table format as answer
            answer = "\n".join([columns, line, rows])

            # Now fetch doc_id, docnm_kwd to provide source chunks
            # Extract WHERE clause from the original SQL
            where_match = re.search(r"\bwhere\b(.+?)(?:\bgroup by\b|\border by\b|\blimit\b|$)", sql, re.IGNORECASE)
            if where_match:
                where_clause = where_match.group(1).strip()
                # Build a query to get source fields with the same WHERE clause.
                # Single-KB queries can derive kb_id from the dialog, while multi-KB
                # ES/OS queries need the row value for metadata enrichment.
                chunks_kb_column = ", kb_id" if not (kb_ids and len(kb_ids) == 1) else ""
                chunks_sql = f"select doc_id, {expected_doc_name_column}{chunks_kb_column} from {table_name} where {where_clause}"
                # Add LIMIT to avoid fetching too many chunks
                if "limit" not in chunks_sql.lower():
                    chunks_sql += " limit 20"
                logging.debug(f"use_sql: Fetching chunks with SQL: {chunks_sql}")
                try:
                    chunks_tbl = settings.retriever.sql_retrieval(chunks_sql, format="json")
                    if chunks_tbl.get("rows") and len(chunks_tbl["rows"]) > 0:
                        # Build chunks reference - use case-insensitive matching
                        chunks_did_idx = next((i for i, c in enumerate(chunks_tbl["columns"]) if c["name"].lower() == "doc_id"), None)
                        chunks_dn_idx = next((i for i, c in enumerate(chunks_tbl["columns"]) if c["name"].lower() in ["docnm_kwd", "docnm"]), None)
                        chunks_kb_idx = next((i for i, c in enumerate(chunks_tbl["columns"]) if c["name"].lower() in ["kb_id", "kb_id_kwd"]), None)
                        if chunks_did_idx is not None and chunks_dn_idx is not None:
                            chunks = []
                            for r in chunks_tbl["rows"]:
                                chunk = {"doc_id": r[chunks_did_idx], "docnm_kwd": r[chunks_dn_idx]}
                                row_dict = {chunks_tbl["columns"][i]["name"]: r[i] for i in range(len(chunks_tbl["columns"])) if i < len(r)}
                                kb_id = _chunk_kb_id_for_doc(row_dict, kb_ids, chunk["doc_id"])
                                if kb_id:
                                    chunk["kb_id"] = kb_id
                                elif chunks_kb_idx is not None:
                                    chunk["kb_id"] = r[chunks_kb_idx]
                                chunks.append(chunk)
                            # Build doc_aggs
                            doc_aggs = {}
                            for r in chunks_tbl["rows"]:
                                doc_id = r[chunks_did_idx]
                                doc_name = r[chunks_dn_idx]
                                if doc_id not in doc_aggs:
                                    doc_aggs[doc_id] = {"doc_name": doc_name, "count": 0}
                                doc_aggs[doc_id]["count"] += 1
                            doc_aggs_list = [{"doc_id": did, "doc_name": d["doc_name"], "count": d["count"]} for did, d in doc_aggs.items()]
                            logging.debug(f"use_sql: Returning aggregate answer with {len(chunks)} chunks from {len(doc_aggs)} documents")
                            return {"answer": answer, "reference": {"chunks": chunks, "doc_aggs": doc_aggs_list}, "prompt": sys_prompt}
                except Exception as e:
                    logging.warning(f"use_sql: Failed to fetch chunks: {e}")
            # Fallback: return answer without chunks
            return {"answer": answer, "reference": {"chunks": [], "doc_aggs": []}, "prompt": sys_prompt}
        # Fallback to table format for other cases
        return {"answer": "\n".join([columns, line, rows]), "reference": {"chunks": [], "doc_aggs": []}, "prompt": sys_prompt}

    docid_idx = list(docid_idx)[0]
    doc_name_idx = list(doc_name_idx)[0]
    doc_aggs = {}
    for r in tbl["rows"]:
        if r[docid_idx] not in doc_aggs:
            doc_aggs[r[docid_idx]] = {"doc_name": r[doc_name_idx], "count": 0}
        doc_aggs[r[docid_idx]]["count"] += 1

    result = {
        "answer": "\n".join([columns, line, rows]),
        "reference": {
            "chunks": [
                {
                    key: value
                    for key, value in {
                        "doc_id": r[docid_idx],
                        "docnm_kwd": r[doc_name_idx],
                        "kb_id": _chunk_kb_id_for_doc(
                            {tbl["columns"][i]["name"]: r[i] for i in range(len(tbl["columns"])) if i < len(r)},
                            kb_ids,
                            r[docid_idx],
                        ),
                    }.items()
                    if value
                }
                for r in tbl["rows"]
            ],
            "doc_aggs": [{"doc_id": did, "doc_name": d["doc_name"], "count": d["count"]} for did, d in doc_aggs.items()],
        },
        "prompt": sys_prompt,
    }
    logging.debug(f"use_sql: Returning answer with {len(result['reference']['chunks'])} chunks from {len(doc_aggs)} documents")
    return result


def clean_tts_text(text: str) -> str:
    if not text:
        return ""

    text = text.encode("utf-8", "ignore").decode("utf-8", "ignore")

    text = re.sub(r"[\x00-\x08\x0B-\x0C\x0E-\x1F\x7F]", "", text)

    emoji_pattern = re.compile(
        "[\U0001f600-\U0001f64f\U0001f300-\U0001f5ff\U0001f680-\U0001f6ff\U0001f1e0-\U0001f1ff\U00002700-\U000027bf\U0001f900-\U0001f9ff\U0001fa70-\U0001faff\U0001fad0-\U0001faff]+", flags=re.UNICODE
    )
    text = emoji_pattern.sub("", text)

    text = re.sub(r"\s+", " ", text).strip()

    MAX_LEN = 500
    if len(text) > MAX_LEN:
        text = text[:MAX_LEN]

    return text


def tts(tts_mdl, text):
    if not tts_mdl or not text:
        return None
    text = clean_tts_text(text)
    if not text:
        return None
    return synthesize_with_cache(tts_mdl, text)


class _ThinkStreamState:
    def __init__(self) -> None:
        self.full_text = ""
        self.last_idx = 0
        self.endswith_think = False
        self.last_full = ""
        self.last_model_full = ""
        self.in_think = False
        self.buffer = ""


def _extract_visible_answer(text: str) -> str:
    text = text or ""
    if "</think>" not in text:
        return re.sub(r"</?think>", "", text)

    thought, answer = text.rsplit("</think>", 1)
    thought = re.sub(r"</?think>", "", thought).strip()
    answer = re.sub(r"</?think>", "", answer)
    if not thought:
        return answer
    return f"<think>{thought}</think>{answer}"


def _next_think_delta(state: _ThinkStreamState) -> str:
    full_text = state.full_text
    if full_text == state.last_full:
        return ""
    state.last_full = full_text
    delta_ans = full_text[state.last_idx :]

    if delta_ans.find("<think>") == 0:
        state.last_idx += len("<think>")
        return "<think>"
    if delta_ans.find("<think>") > 0:
        delta_text = full_text[state.last_idx : state.last_idx + delta_ans.find("<think>")]
        state.last_idx += delta_ans.find("<think>")
        return delta_text
    if delta_ans.endswith("</think>"):
        state.endswith_think = True
    elif state.endswith_think:
        state.endswith_think = False
        return "</think>"

    state.last_idx = len(full_text)
    if full_text.endswith("</think>"):
        state.last_idx -= len("</think>")
    return re.sub(r"(<think>|</think>)", "", delta_ans)


async def _stream_with_think_delta(stream_iter, min_tokens: int = 16):
    state = _ThinkStreamState()
    async for chunk in stream_iter:
        if not chunk:
            continue
        if chunk.startswith(state.last_model_full):
            new_part = chunk[len(state.last_model_full) :]
            state.last_model_full = chunk
        else:
            new_part = chunk
            state.last_model_full += chunk
        if not new_part:
            continue
        state.full_text += new_part
        delta = _next_think_delta(state)
        if not delta:
            continue
        if delta in ("<think>", "</think>"):
            if delta == "<think>" and state.in_think:
                continue
            if delta == "</think>" and not state.in_think:
                continue
            if state.buffer:
                yield ("text", state.buffer, state)
                state.buffer = ""
            state.in_think = delta == "<think>"
            yield ("marker", delta, state)
            continue
        state.buffer += delta
        if num_tokens_from_string(state.buffer) < min_tokens:
            continue
        yield ("text", state.buffer, state)
        state.buffer = ""

    if state.buffer:
        yield ("text", state.buffer, state)
        state.buffer = ""
    if state.endswith_think:
        yield ("marker", "</think>", state)


async def async_ask(question, kb_ids, tenant_id, chat_llm_name=None, search_config={}, search_id=None):
    doc_ids = search_config.get("doc_ids", [])
    rerank_mdl = None
    kb_ids = search_config.get("kb_ids", kb_ids)
    chat_llm_name = search_config.get("chat_id", chat_llm_name)
    rerank_id = search_config.get("rerank_id", "")
    meta_data_filter = search_config.get("meta_data_filter")
    include_reference_metadata, metadata_fields = _resolve_reference_metadata(search_config)

    kbs = KnowledgebaseService.get_by_ids(kb_ids)
    embedding_list = list(set([kb.embd_id for kb in kbs]))

    is_knowledge_graph = all([kb.parser_id == ParserType.KG for kb in kbs])
    retriever = settings.retriever if not is_knowledge_graph else settings.kg_retriever
    embd_owner_tenant_id = kbs[0].tenant_id
    embd_model_config = get_model_config_by_type_and_name(embd_owner_tenant_id, LLMType.EMBEDDING, embedding_list[0])
    embd_mdl = LLMBundle(embd_owner_tenant_id, embd_model_config)
    chat_model_config = get_model_config_by_type_and_name(tenant_id, LLMType.CHAT, chat_llm_name)
    chat_mdl = LLMBundle(tenant_id, chat_model_config)
    if rerank_id:
        rerank_model_config = get_model_config_by_type_and_name(tenant_id, LLMType.RERANK, rerank_id)
        rerank_mdl = LLMBundle(tenant_id, rerank_model_config)
    max_tokens = chat_mdl.max_length
    tenant_ids = list(set([kb.tenant_id for kb in kbs]))

    if meta_data_filter:
        doc_ids = await apply_meta_data_filter(
            meta_data_filter,
            None,
            question,
            chat_mdl,
            doc_ids,
            kb_ids=kb_ids,
            metas_loader=lambda: DocMetadataService.get_flatted_meta_by_kbs(kb_ids),
        )

    vector_similarity_weight = search_config.get("vector_similarity_weight", 0.3)
    try:
        full_text_weight = 1 - vector_similarity_weight
    except TypeError:
        full_text_weight = None
    logger.debug(
        "Search async_ask retrieval weight: search_id=%s tenant_id=%s kb_count=%s "
        "vector_similarity_weight=%s full_text_weight=%s",
        search_id,
        tenant_id,
        len(kb_ids),
        vector_similarity_weight,
        full_text_weight,
    )

    kbinfos = await retriever.retrieval(
        question=question,
        embd_mdl=embd_mdl,
        tenant_ids=tenant_ids,
        kb_ids=kb_ids,
        page=1,
        page_size=12,
        similarity_threshold=search_config.get("similarity_threshold", 0.1),
        vector_similarity_weight=vector_similarity_weight,
        top=search_config.get("top_k", 1024),
        doc_ids=doc_ids,
        aggs=True,
        rerank_mdl=rerank_mdl,
        rank_feature=label_question(question, kbs),
        trace_id=search_id,
    )
    if include_reference_metadata:
        logging.debug(
            "reference_metadata enrichment enabled for async_ask: chunk_count=%d metadata_fields=%s",
            len(kbinfos.get("chunks", [])),
            metadata_fields,
        )
        _enrich_chunks_with_document_metadata(kbinfos.get("chunks", []), metadata_fields)

    knowledges = kb_prompt(kbinfos, max_tokens)
    sys_prompt = PROMPT_JINJA_ENV.from_string(ASK_SUMMARY).render(knowledge="\n".join(knowledges))

    msg = [{"role": "user", "content": question}]

    async def decorate_answer(answer):
        nonlocal knowledges, kbinfos, sys_prompt
        # Main retrieval no longer ships chunk vectors back from ES. Pull
        # them on demand for the chunks we are about to cite.
        await _hydrate_chunk_vectors(retriever, kbinfos.get("chunks", []), tenant_ids, kb_ids)
        answer, idx = retriever.insert_citations(answer, [ck["content_ltks"] for ck in kbinfos["chunks"]], [ck["vector"] for ck in kbinfos["chunks"]], embd_mdl, tkweight=0.7, vtweight=0.3)
        idx = set([kbinfos["chunks"][int(i)]["doc_id"] for i in idx])
        recall_docs = [d for d in kbinfos["doc_aggs"] if d["doc_id"] in idx]
        if not recall_docs:
            recall_docs = kbinfos["doc_aggs"]
        kbinfos["doc_aggs"] = recall_docs
        refs = deepcopy(kbinfos)
        for c in refs["chunks"]:
            if c.get("vector"):
                del c["vector"]

        if answer.lower().find("invalid key") >= 0 or answer.lower().find("invalid api") >= 0:
            answer += " Please set LLM API-Key in 'User Setting -> Model Providers -> API-Key'"
        refs["chunks"] = chunks_format(refs)
        return {"answer": answer, "reference": refs}

    stream_iter = chat_mdl.async_chat_streamly_delta(sys_prompt, msg, {"temperature": 0.1})
    last_state = None
    async for kind, value, state in _stream_with_think_delta(stream_iter):
        last_state = state
        if kind == "marker":
            flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
            yield {"answer": "", "reference": {}, "final": False, **flags}
            continue
        yield {"answer": value, "reference": {}, "final": False}
    full_answer = last_state.full_text if last_state else ""
    final = await decorate_answer(_extract_visible_answer(full_answer))
    final["final"] = True
    yield final


async def gen_mindmap(question, kb_ids, tenant_id, search_config={}):
    meta_data_filter = search_config.get("meta_data_filter", {})
    doc_ids = search_config.get("doc_ids", [])
    rerank_id = search_config.get("rerank_id", "")
    rerank_mdl = None
    kbs = KnowledgebaseService.get_by_ids(kb_ids)
    if not kbs:
        return {"error": "No KB selected"}
    tenant_embedding_list = list(set([kb.tenant_embd_id for kb in kbs]))
    tenant_ids = list(set([kb.tenant_id for kb in kbs]))
    if tenant_embedding_list[0]:
        embd_model_config = get_model_config_by_id(tenant_embedding_list[0])
        embd_owner_tenant_id = kbs[0].tenant_id
    else:
        embd_owner_tenant_id = kbs[0].tenant_id
        embd_model_config = get_model_config_by_type_and_name(embd_owner_tenant_id, LLMType.EMBEDDING, kbs[0].embd_id)
    embd_mdl = LLMBundle(embd_owner_tenant_id, embd_model_config)
    chat_id = search_config.get("chat_id", "")
    if chat_id:
        chat_model_config = get_model_config_by_type_and_name(tenant_id, LLMType.CHAT, chat_id)
    else:
        chat_model_config = get_tenant_default_model_by_type(tenant_id, LLMType.CHAT)
    chat_mdl = LLMBundle(tenant_id, chat_model_config)
    if rerank_id:
        rerank_model_config = get_model_config_by_type_and_name(tenant_id, LLMType.RERANK, rerank_id)
        rerank_mdl = LLMBundle(tenant_id, rerank_model_config)

    if meta_data_filter:
        doc_ids = await apply_meta_data_filter(
            meta_data_filter,
            None,
            question,
            chat_mdl,
            doc_ids,
            kb_ids=kb_ids,
            metas_loader=lambda: DocMetadataService.get_flatted_meta_by_kbs(kb_ids),
        )

    ranks = await settings.retriever.retrieval(
        question=question,
        embd_mdl=embd_mdl,
        tenant_ids=tenant_ids,
        kb_ids=kb_ids,
        page=1,
        page_size=12,
        similarity_threshold=search_config.get("similarity_threshold", 0.2),
        vector_similarity_weight=search_config.get("vector_similarity_weight", 0.3),
        top=search_config.get("top_k", 1024),
        doc_ids=doc_ids,
        aggs=False,
        rerank_mdl=rerank_mdl,
        rank_feature=label_question(question, kbs),
    )
    mindmap = MindMapExtractor(chat_mdl)
    mind_map = await mindmap([c["content_with_weight"] for c in ranks["chunks"]])
    return mind_map.output
