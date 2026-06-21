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
import hashlib
import json
import logging
import os
import re
import time
import uuid
from collections import Counter
from contextlib import asynccontextmanager
from contextvars import ContextVar
from copy import deepcopy

logger = logging.getLogger(__name__)
from datetime import datetime
from functools import partial
from timeit import default_timer as timer
from langfuse import Langfuse
from peewee import fn
from api.db.services.file_service import FileService
from common.constants import LLMType, MemoryType, ParserType, StatusEnum
from api.db.db_models import DB, Dialog
from api.db.services.common_service import CommonService
from api.db.services.doc_metadata_service import DocMetadataService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.langfuse_service import TenantLangfuseService
from api.db.services.llm_service import LLMBundle
from api.db.services.memory_service import MemoryService
from api.db.services.panython_tts_settings_service import PanythonTTSSettingsService, build_tts_kwargs
from common.metadata_utils import apply_meta_data_filter
from api.utils.reference_metadata_utils import (
    enrich_chunks_with_document_metadata,
    resolve_reference_metadata_preferences,
)
from api.utils.memory_utils import get_memory_display_name
from api.db.services.tenant_llm_service import TenantLLMService
from api.db.joint_services.memory_message_service import embed_and_save, query_message
from api.db.joint_services.tenant_model_service import get_model_config_by_id, get_model_config_by_type_and_name, get_tenant_default_model_by_type
from common.misc_utils import get_uuid, thread_pool_exec
from common.time_utils import current_timestamp, datetime_format, timestamp_to_date
from common.text_utils import normalize_arabic_digits
from rag.graphrag.general.mind_map_extractor import MindMapExtractor
from rag.advanced_rag import DeepResearcher
from rag.app.tag import label_question
from rag.nlp.search import index_name
from rag.prompts.generator import chunks_format, cross_languages, full_question, kb_prompt, keyword_extraction, memory_prompt, PROMPT_JINJA_ENV, ASK_SUMMARY
from common.token_utils import DynamicTokenCounter, num_tokens_from_string
from rag.utils.tavily_conn import Tavily
from rag.utils.tts_cache import synthesize_with_cache
from rag.utils.redis_conn import REDIS_CONN
from common.feature_flags import feature_enabled
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


def _tts_globally_enabled() -> bool:
    try:
        return bool(PanythonTTSSettingsService.get_settings().get("tts_enabled"))
    except Exception as exc:  # noqa: BLE001 - TTS must not break chat
        logging.warning("Failed to read Panython TTS settings: %s", exc)
        return False


def _should_enable_tts(prompt_config: dict | None) -> bool:
    return bool((prompt_config or {}).get("tts")) and _tts_globally_enabled()


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
    tts_config = prompt_config.get("tts_config") or {}
    tts_mdl = None
    if _should_enable_tts(prompt_config):
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
            yield {"answer": value, "reference": {}, "audio_binary": visible_tts(tts_mdl, value, state.in_think, tts_config), "prompt": "", "created_at": time.time(), "final": False}
    else:
        if llm_type == "chat":
            answer = await chat_mdl.async_chat(prompt_config.get("system", ""), msg, gen_conf)
        else:
            answer = await chat_mdl.async_chat(prompt_config.get("system", ""), msg, gen_conf, images=image_files)
        user_content = msg[-1].get("content", "[content not available]")
        logging.debug("User: {}|Assistant: {}".format(user_content, answer))
        yield {"answer": answer, "reference": {}, "audio_binary": visible_tts(tts_mdl, answer, tts_config=tts_config), "prompt": "", "created_at": time.time()}


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

    if _should_enable_tts(dialog.prompt_config):
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
MULTI_ID_CITATION_PATTERN = re.compile(
    r"[（(]\s*ID\s*[:：]\s*"
    r"([0-9\u0660-\u0669\u06F0-\u06F9]+(?:\s*[,，、]\s*(?:ID\s*[:：]\s*)?[0-9\u0660-\u0669\u06F0-\u06F9]+)+)"
    r"\s*[)）]",
    flags=re.IGNORECASE,
)
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
    cited_chunk_indexes = []
    for raw_index in idx or []:
        try:
            chunk_index = int(raw_index)
        except (TypeError, ValueError):
            continue
        if 0 <= chunk_index < len(chunks):
            cited_chunk_indexes.append(chunk_index)
    cited_chunk_indexes = sorted(set(cited_chunk_indexes))
    if not cited_chunk_indexes:
        return answer, {"chunks": [], "doc_aggs": []}, {}

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
    return answer, refs, old_to_new


def build_compact_evidence_audit(
    refs: dict,
    question: str,
    retrieval_query: str,
    answer: str,
) -> dict:
    """Build evidence audit against the same compact IDs returned to the UI.

    The answer is rewritten to compact citation IDs before references are sent
    to the frontend. The audit panel must use the same ID space, otherwise the
    UI can display Fig.4/Fig.6-style source IDs while the reference list only
    contains compact Fig.1/Fig.2 entries.
    """
    compact_chunks = [chunk for chunk in (refs or {}).get("chunks", []) if isinstance(chunk, dict)]
    compact_indexes = set(range(len(compact_chunks)))
    compact_kbinfos = {
        "chunks": compact_chunks,
        "doc_aggs": (refs or {}).get("doc_aggs", []),
    }
    compact_id_map = {index: index for index in compact_indexes}
    audit = _build_evidence_audit(
        compact_kbinfos,
        compact_indexes,
        question,
        retrieval_query,
        answer,
        compact_id_map,
    )
    audit["id_space"] = "compact_reference"
    return audit


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


def expand_raptor_chunks_for_generation(kbinfos: dict, max_sources: int = 3, max_chars_per_source: int = 1200):
    chunks = kbinfos.get("chunks") or []
    if not chunks:
        return
    attach_raptor_source_chunks(chunks, kbinfos.get("tenant_ids", []), kbinfos.get("kb_ids", []), max_sources=max_sources)
    for chunk in chunks:
        if not chunk.get("is_raptor_summary") or not chunk.get("source_chunks"):
            continue
        source_texts = []
        for index, source in enumerate(chunk.get("source_chunks", [])[:max_sources], start=1):
            content = str(source.get("content") or "").strip()
            if not content:
                continue
            if len(content) > max_chars_per_source:
                content = content[:max_chars_per_source].rstrip() + "\n...[truncated]"
            source_texts.append(f"Source excerpt {index}:\n{content}")
        if not source_texts:
            continue
        original = str(chunk.get("content_with_weight") or chunk.get("content") or "")
        chunk["content_with_weight"] = (
            f"{original}\n\n[This is a RAPTOR summary chunk. Use the following linked original source excerpts as evidence before concluding the knowledge base lacks details.]\n"
            + "\n\n".join(source_texts)
        )


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

    def replace_multi_id(match: re.Match):
        marker_text = match.group(0)
        digits = re.findall(r"[0-9\u0660-\u0669\u06F0-\u06F9]+", marker_text)
        markers = []
        for raw_digit in digits:
            try:
                normalized_digit = normalize_arabic_digits(raw_digit) or raw_digit
                i = int(normalized_digit)
            except Exception:
                continue
            if safe_add(i):
                markers.append(f"[ID:{normalized_digit}]")
        return " ".join(markers) if markers else marker_text

    if MULTI_ID_CITATION_PATTERN.search(answer):
        answer = MULTI_ID_CITATION_PATTERN.sub(replace_multi_id, answer)
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
    "CONNECTION_ERROR",
    "INVALID_REQUEST",
    "ApiError(",
    "Traceback (most recent call last)",
    "search_phase_execution_exception",
    "CUDA error",
    "invalid_request_error",
    "layer-slice token span exceeds context",
    "kv payload staging failed",
    "知识库中未找到您要的答案",
    "知识库内容为空",
)
THINK_BLOCK_PATTERN = re.compile(r"<think>[\s\S]*?</think>", flags=re.IGNORECASE)
RETRIEVING_BLOCK_PATTERN = re.compile(r"<retrieving>[\s\S]*?</retrieving>", flags=re.IGNORECASE)
PROCESS_TAG_PATTERN = re.compile(r"</?(?:think|retrieving)>", flags=re.IGNORECASE)


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
            content = THINK_BLOCK_PATTERN.sub("", message["content"])
            content = RETRIEVING_BLOCK_PATTERN.sub("", content)
            message["content"] = PROCESS_TAG_PATTERN.sub("", content).strip()
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
EXPLICIT_TOPIC_RESET_PATTERNS = (
    "换个话题",
    "换一个话题",
    "另一个问题",
    "新的问题",
    "重新开始",
    "不要参考上文",
    "不参考上文",
    "忽略上文",
    "reset context",
    "new topic",
    "start over",
)
STRONG_CONTEXT_FOLLOWUP_PATTERNS = (
    "继续",
    "其中",
    "上述",
    "上面",
    "前面",
    "刚才",
    "该报告",
    "这个报告",
)

SEMANTIC_ROUTE_SCORE_THRESHOLD = float(os.environ.get("RAGFLOW_SEMANTIC_ROUTE_THRESHOLD", "0.32"))
SEMANTIC_ROUTE_EXAMPLES = {
    "pure_chat": (
        "你好",
        "谢谢",
        "讲个笑话",
        "你能做什么",
        "hello",
        "thanks",
        "tell me a joke",
        "what can you do",
    ),
    "model_identity": (
        "你是谁",
        "你是什么模型",
        "你有多少参数",
        "你的上下文多长",
        "和deepseek r1对比",
        "who are you",
        "what model are you",
        "how many parameters do you have",
        "what is your context length",
    ),
    "rag_question": (
        "根据报告回答",
        "参考知识库",
        "这份pdf里说了什么",
        "该报告的结论是什么",
        "从文档中查找",
        "according to the report",
        "search the knowledge base",
        "based on the document",
        "what does this pdf say",
    ),
    "follow_up": (
        "继续",
        "上面说的是什么意思",
        "其中哪一点最重要",
        "该报告还有什么结论",
        "这个领域还有哪些专家",
        "continue",
        "what about the above",
        "what does it mean",
        "which of those is most important",
    ),
    "long_generation": (
        "写一篇长报告",
        "生成一万字小说",
        "输出完整研究报告",
        "详细研究并形成markdown文档",
        "write a long report",
        "write a novel",
        "generate a markdown document",
        "deep research report",
    ),
    "memo_add": (
        "加入备忘录",
        "总结到记忆",
        "保存这段对话",
        "add to memo",
        "save to memory",
        "summarize this conversation to memory",
    ),
    "memo_search": (
        "查一下备忘录",
        "以前讨论过什么",
        "从记忆里找",
        "search my memory",
        "find from memo",
        "what did we discuss before",
    ),
    "agent_task": (
        "运行智能体",
        "启动深度研究智能体",
        "执行流程",
        "run the agent",
        "start the workflow",
        "execute this agent",
    ),
    "external_search_needed": (
        "联网搜索最新",
        "查一下最新消息",
        "今天的新闻",
        "最新股价",
        "search the web",
        "latest news",
        "today's update",
        "current stock price",
    ),
    "error_noise": (
        "ERROR:",
        "CONNECTION_ERROR",
        "INVALID_REQUEST",
        "Traceback",
        "layer-slice token span exceeds context",
        "kv payload staging failed",
    ),
}

MAX_RETRIEVAL_QUERY_CHARS = 220
MAX_RETRIEVAL_QUERY_TERMS = 36
DEFAULT_MODEL_CONTEXT_TOKENS = 8192
DEEPSEEK_V4_CONTEXT_TOKENS = 131072
DEEPSEEK_V4_EFFECTIVE_CONTEXT_TOKENS = 65536
DEEPSEEK_V4_RETRY_CONTEXT_TOKENS = 32768
DEEPSEEK_V4_PROMPT_HARD_TOKENS = 60000
MIN_OUTPUT_TOKENS = 1
DEFAULT_OUTPUT_TOKENS = 512
DEEPSEEK_V4_RAG_OUTPUT_TOKENS = 4096
MEMORY_CONTEXT_TOKENS = 2048
MAX_MEMORY_RESULTS = 5
MAX_MEMORY_GROUPS = 4
MAX_KNOWLEDGE_CONTEXT_RATIO = 0.30
MAX_PROMPT_CONTEXT_RATIO = 0.95
MAX_RAG_HISTORY_TOKENS = 4096
DEFAULT_RETRIEVAL_TOP_N = 8
DEFAULT_RETRIEVAL_TOP_K = 1024
try:
    DS4_MAX_CONCURRENT_GENERATIONS = max(1, int(os.environ.get("DS4_MAX_CONCURRENT_GENERATIONS", "2")))
except ValueError:
    DS4_MAX_CONCURRENT_GENERATIONS = 2
DS4_GENERATION_SEMAPHORE = asyncio.Semaphore(DS4_MAX_CONCURRENT_GENERATIONS)
ACTIVE_TOKEN_COUNTER: ContextVar[DynamicTokenCounter | None] = ContextVar("active_rag_token_counter", default=None)
CONTEXT_SPAN_ERROR_PATTERNS = (
    "layer-slice token span exceeds context",
    "kv payload staging failed",
    "exceeds context",
    "context length",
    "maximum context",
)
PURE_LLM_SYSTEM_PROMPT = """你是 Panython / RightTime 本地部署的 DeepSeek V4 Flash 智能助手。

当前请求已被判定为普通聊天或模型自身相关问题，不要检索知识库，不要引用 PDF、文档、Fig. 或来源片段。
请直接、简洁地回答用户当前问题。回答身份、模型、能力、上下文等问题时，应说明你是本地部署的 DeepSeek V4 Flash 服务；不要声称自己是 Kimi、OpenAI、ChatGPT 或其他模型。
如果用户只是问“你是谁 / who are you”，只用 1-2 句话回答身份和部署方；不要主动提及免费、上下文长度、知识截止、文件上传、联网、多模态或具体能力限制，除非用户明确询问这些细节。

You are the locally deployed DeepSeek V4 Flash assistant served by Panython / RightTime.
For general chat or model-self questions, answer directly without knowledge-base citations or document references.
For a simple identity question, answer in 1-2 sentences and do not volunteer pricing, context length, knowledge cutoff, upload, web, multimodal, or capability-limit details unless explicitly asked."""

COMPACT_CITATION_PROMPT = """

### Citation rules
Use retrieved knowledge only when it supports the answer. When a sentence uses a retrieved passage, append its source marker as [ID:n], where n is the passage ID shown in the knowledge context. Do not invent IDs. If multiple passages support one sentence, append multiple markers such as [ID:1] [ID:3].
Keep any reasoning brief and make sure the final answer is completed before reaching the token limit.
"""

MAX_RAG_HISTORY_MESSAGES = 4
MAX_RAG_ASSISTANT_HISTORY_CHARS = 1200
MAX_RAG_USER_HISTORY_CHARS = 1000
CONVERSATION_SUMMARY_KEY = "_conversation_summary"
SYSTEM_CONVERSATION_MEMORY_NAME = "__panython_conversation_memory__"
SUMMARY_RECENT_MESSAGE_KEEP = 4
SUMMARY_SOURCE_TOKEN_LIMIT = 6000
SUMMARY_MAX_TOKENS = 768
SUMMARY_CONTEXT_TOKEN_BUDGET = 1024
STRUCTURED_MEMORY_TOKEN_BUDGET = 1200
SEMANTIC_TOPIC_SIMILARITY_THRESHOLD = float(os.environ.get("RAGFLOW_TOPIC_RESET_SEMANTIC_THRESHOLD", "0.38"))
SEMANTIC_TOPIC_CONTEXT_CHARS = int(os.environ.get("RAGFLOW_TOPIC_RESET_CONTEXT_CHARS", "2400"))
HISTORY_STOP_TERMS = {
    "这个",
    "那个",
    "这些",
    "那些",
    "其中",
    "问题",
    "回答",
    "内容",
    "please",
    "what",
    "which",
    "with",
    "from",
    "that",
}


def _normalize_route_text(text: str) -> str:
    return re.sub(r"\s+", " ", (text or "").strip().lower())


_SEMANTIC_ROUTE_VECTOR_CACHE: dict[str, list[Counter]] | None = None


def _route_terms(text: str) -> list[str]:
    normalized = _normalize_route_text(text)
    terms = re.findall(r"[a-z0-9][a-z0-9_.-]{1,}", normalized)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", normalized)
    for size in (2, 3, 4):
        for idx in range(0, max(0, len(chinese_chars) - size + 1)):
            terms.append("".join(chinese_chars[idx : idx + size]))
    return [term for term in terms if term not in HISTORY_STOP_TERMS]


def _route_vector(text: str) -> Counter:
    return Counter(_route_terms(text))


def _semantic_route_vectors() -> dict[str, list[Counter]]:
    global _SEMANTIC_ROUTE_VECTOR_CACHE
    if _SEMANTIC_ROUTE_VECTOR_CACHE is None:
        _SEMANTIC_ROUTE_VECTOR_CACHE = {
            route: [_route_vector(example) for example in examples]
            for route, examples in SEMANTIC_ROUTE_EXAMPLES.items()
        }
    return _SEMANTIC_ROUTE_VECTOR_CACHE


def _sparse_cosine(left: Counter, right: Counter) -> float:
    if not left or not right:
        return 0.0
    common = set(left) & set(right)
    numerator = sum(left[key] * right[key] for key in common)
    left_norm = sum(value * value for value in left.values()) ** 0.5
    right_norm = sum(value * value for value in right.values()) ** 0.5
    if left_norm <= 0 or right_norm <= 0:
        return 0.0
    return float(numerator / (left_norm * right_norm))


def _semantic_route_layer(latest_question: str, kwargs: dict | None = None) -> dict:
    start_ts = timer()
    kwargs = kwargs or {}
    if not feature_enabled("semantic_router"):
        return {"route": "rag_question", "score": 0.0, "reason": "feature_disabled", "elapsed_ms": 0.0}
    normalized = _normalize_route_text(latest_question)
    route = "rag_question"
    score = 0.0
    reason = "default"

    if kwargs.get("doc_ids"):
        return {"route": "rag_question", "score": 1.0, "reason": "explicit_doc_ids", "elapsed_ms": 0.0}
    if not normalized:
        return {"route": "unknown", "score": 0.0, "reason": "empty_question", "elapsed_ms": 0.0}
    if any(pattern.lower() in normalized for pattern in ERROR_HISTORY_PATTERNS):
        return {"route": "error_noise", "score": 1.0, "reason": "error_marker", "elapsed_ms": 0.0}

    query_vector = _route_vector(normalized)
    for candidate_route, vectors in _semantic_route_vectors().items():
        candidate_score = max((_sparse_cosine(query_vector, vector) for vector in vectors), default=0.0)
        if candidate_score > score:
            route = candidate_route
            score = candidate_score
            reason = "example_similarity"

    if any(pattern in normalized for pattern in EXPLICIT_KB_INTENT_PATTERNS):
        route, score, reason = "rag_question", max(score, 0.95), "explicit_kb_intent"
    elif any(pattern in normalized for pattern in MODEL_SELF_QUESTION_PATTERNS):
        route, score, reason = "model_identity", max(score, 0.95), "model_self_pattern"
    elif any(pattern in normalized for pattern in GENERAL_CHAT_PATTERNS) and len(normalized) <= 24:
        route, score, reason = "pure_chat", max(score, 0.9), "general_chat_pattern"
    elif any(pattern in normalized for pattern in CONTEXT_DEPENDENT_PATTERNS):
        route, score, reason = "follow_up", max(score, 0.75), "context_dependent_pattern"

    elapsed_ms = (timer() - start_ts) * 1000
    return {"route": route, "score": score, "reason": reason, "elapsed_ms": elapsed_ms}


def _has_model_self_signal(normalized_question: str) -> bool:
    if any(pattern in normalized_question for pattern in MODEL_SELF_QUESTION_PATTERNS):
        return True
    return bool(
        re.search(
            r"\b(you|your|yourself)\b|\bparameters?\b|\bcontext\s+length\b|\bwho\s+are\s+you\b|\bwhat\s+model\b",
            normalized_question,
            flags=re.IGNORECASE,
        )
    )


def _should_route_to_pure_llm(latest_question: str, kwargs: dict, route_result: dict | None = None) -> tuple[bool, str]:
    if kwargs.get("doc_ids"):
        return False, "explicit_doc_ids"

    normalized = _normalize_route_text(latest_question)
    if not normalized:
        return False, "empty_question"

    route_result = route_result or _semantic_route_layer(latest_question, kwargs)
    route = route_result.get("route")
    score = float(route_result.get("score") or 0)
    if score >= SEMANTIC_ROUTE_SCORE_THRESHOLD:
        if route in {"pure_chat", "model_identity", "error_noise"}:
            if route == "model_identity" and not _has_model_self_signal(normalized):
                return False, f"semantic_model_identity_without_self_signal_{score:.3f}_{route_result.get('reason')}"
            return True, f"semantic_{route}_{score:.3f}_{route_result.get('reason')}"
        if route in {"rag_question", "follow_up", "memo_search", "external_search_needed", "agent_task", "long_generation"}:
            return False, f"semantic_{route}_{score:.3f}_{route_result.get('reason')}"

    if any(pattern in normalized for pattern in EXPLICIT_KB_INTENT_PATTERNS):
        return False, "explicit_kb_intent"

    if _has_model_self_signal(normalized):
        return True, "model_self_question"

    if any(pattern in normalized for pattern in GENERAL_CHAT_PATTERNS) and len(normalized) <= 24:
        return True, "general_chat"

    return False, "default_kb_route"


def _question_depends_on_history(latest_question: str, route_result: dict | None = None) -> bool:
    normalized = _normalize_route_text(latest_question)
    if route_result and route_result.get("route") == "follow_up" and float(route_result.get("score") or 0) >= SEMANTIC_ROUTE_SCORE_THRESHOLD:
        return True
    return any(pattern in normalized for pattern in CONTEXT_DEPENDENT_PATTERNS)


def _should_reset_topic(latest_question: str, cached_summary: dict | None, messages: list[dict], depends_on_history: bool) -> tuple[bool, str]:
    cached_content = _summary_content(cached_summary)
    if not cached_content:
        return False, "no_cached_summary"

    normalized = _normalize_route_text(latest_question)
    if any(pattern in normalized for pattern in EXPLICIT_TOPIC_RESET_PATTERNS):
        return True, "explicit_reset"
    if any(pattern in normalized for pattern in MODEL_SELF_QUESTION_PATTERNS):
        return True, "model_self_question"
    if any(pattern in normalized for pattern in GENERAL_CHAT_PATTERNS) and len(normalized) <= 24:
        return True, "general_chat"

    if not depends_on_history:
        score = _history_relevance_score(latest_question, cached_content)
        if score <= 0:
            return True, "new_independent_topic"
        return False, "independent_but_related"

    if any(pattern in normalized for pattern in STRONG_CONTEXT_FOLLOWUP_PATTERNS):
        return False, "strong_followup"

    recent_context = "\n".join(
        _strip_process_blocks(str(m.get("content", "")))
        for m in (messages or [])[-6:]
        if m.get("role") in {"user", "assistant"} and not _is_error_history_message(m)
    )
    score = _history_relevance_score(latest_question, cached_content + "\n" + recent_context)
    if score <= 0:
        return True, "dependent_terms_without_topic_overlap"
    return False, f"related_score_{score}"


def _safe_token_count(text) -> int:
    try:
        token_counter = ACTIVE_TOKEN_COUNTER.get()
        if token_counter:
            return token_counter.count_text(_normalize_text_from_content(text))
        return num_tokens_from_string(_normalize_text_from_content(text))
    except Exception:  # noqa: BLE001 - token logging must never break chat
        return max(1, len(str(text or "")) // 3)


def _messages_token_count(messages: list[dict]) -> int:
    try:
        token_counter = ACTIVE_TOKEN_COUNTER.get()
        if token_counter:
            return token_counter.count_messages(messages or [])
    except Exception:  # noqa: BLE001 - token logging must never break chat
        pass
    return sum(_safe_token_count(message.get("content", "")) for message in messages or [])


def _truncate_to_tokens(content: str, token_limit: int) -> str:
    token_counter = ACTIVE_TOKEN_COUNTER.get()
    if token_counter:
        effective_limit = max(0, int(token_limit / max(1.0, token_counter.fallback_safety_factor)))
        return token_counter.truncate_text(content, effective_limit)
    return content[: max(0, token_limit * 3)]


def _significant_terms(text: str) -> set[str]:
    text = _strip_process_blocks(str(text or "")).lower()
    terms = set(re.findall(r"[a-z0-9_]{3,}", text))
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for size in (2, 3):
        for idx in range(0, max(0, len(chinese_chars) - size + 1)):
            terms.add("".join(chinese_chars[idx : idx + size]))
    return {term for term in terms if term not in HISTORY_STOP_TERMS}


def _history_relevance_score(latest_question: str, history_text: str) -> int:
    question_terms = _significant_terms(latest_question)
    history_terms = _significant_terms(history_text)
    if not question_terms or not history_terms:
        return 0
    return len(question_terms & history_terms)


def _cosine_similarity(left, right) -> float | None:
    try:
        left_values = [float(v) for v in left]
        right_values = [float(v) for v in right]
        if not left_values or not right_values or len(left_values) != len(right_values):
            return None
        numerator = sum(a * b for a, b in zip(left_values, right_values))
        left_norm = sum(a * a for a in left_values) ** 0.5
        right_norm = sum(b * b for b in right_values) ** 0.5
        if left_norm <= 0 or right_norm <= 0:
            return None
        return numerator / (left_norm * right_norm)
    except Exception:  # noqa: BLE001 - semantic reset must degrade to lexical reset
        return None


def _encode_topic_pair(embd_mdl, latest_question: str, context: str):
    vectors, _ = embd_mdl.encode([latest_question, context])
    if vectors is None or len(vectors) < 2:
        return None
    return _cosine_similarity(vectors[0], vectors[1])


async def _semantic_topic_similarity(embd_mdl, latest_question: str, context: str) -> float | None:
    if not embd_mdl or not latest_question or not context:
        return None
    context = _strip_process_blocks(context).strip()
    if not context:
        return None
    context = context[:SEMANTIC_TOPIC_CONTEXT_CHARS]
    try:
        return await thread_pool_exec(_encode_topic_pair, embd_mdl, latest_question, context)
    except Exception as exc:  # noqa: BLE001 - semantic reset must not break chat
        logging.warning("TopicReset semantic similarity failed: %s", exc)
        return None


async def _should_reset_topic_with_semantics(
    latest_question: str,
    cached_summary: dict | None,
    messages: list[dict],
    depends_on_history: bool,
    embd_mdl=None,
) -> tuple[bool, str]:
    reset, reason = _should_reset_topic(latest_question, cached_summary, messages, depends_on_history)
    if not reset or reason == "explicit_reset":
        return reset, reason

    if reason != "dependent_terms_without_topic_overlap":
        return reset, reason

    cached_content = _summary_content(cached_summary)
    recent_context = "\n".join(
        _strip_process_blocks(str(m.get("content", "")))
        for m in (messages or [])[-6:]
        if m.get("role") in {"user", "assistant"} and not _is_error_history_message(m)
    )
    semantic_context = "\n".join([cached_content, recent_context]).strip()
    similarity = await _semantic_topic_similarity(embd_mdl, latest_question, semantic_context)
    if similarity is None:
        return reset, f"{reason}_semantic_unavailable"
    if similarity >= SEMANTIC_TOPIC_SIMILARITY_THRESHOLD:
        return False, f"semantic_related_{similarity:.3f}"
    return True, f"{reason}_semantic_{similarity:.3f}"


def _truncate_history_content(content: str, limit: int) -> str:
    content = _strip_process_blocks(str(content or "")).strip()
    if len(content) <= limit:
        return content
    return content[:limit].rstrip() + "\n...[truncated]"


def _rag_generation_messages(
    messages: list[dict],
    latest_question: str,
    depends_on_history: bool,
    token_budget: int = MAX_RAG_HISTORY_TOKENS,
) -> list[dict]:
    """Keep RAG generation focused on the current turn and avoid KV/context buildup."""
    latest_user_index = next((idx for idx in range(len(messages) - 1, -1, -1) if messages[idx].get("role") == "user"), None)
    latest_user = messages[latest_user_index] if latest_user_index is not None else None
    if latest_user is None:
        return []

    latest_content = _truncate_history_content(latest_user.get("content", ""), MAX_RAG_USER_HISTORY_CHARS)
    latest_message = {"role": "user", "content": latest_content}
    if not depends_on_history:
        return [latest_message]

    used_tokens = _safe_token_count(latest_content)
    selected = []
    previous_messages = [m for m in messages[:latest_user_index] if m.get("role") in {"user", "assistant"}]
    for distance, message in enumerate(reversed(previous_messages)):
        if len(selected) >= MAX_RAG_HISTORY_MESSAGES:
            break
        role = message.get("role")
        limit = MAX_RAG_USER_HISTORY_CHARS if role == "user" else MAX_RAG_ASSISTANT_HISTORY_CHARS
        content = _truncate_history_content(message.get("content", ""), limit)
        if not content:
            continue
        is_recent_turn = distance < 2
        if not is_recent_turn and _history_relevance_score(latest_question, content) <= 0:
            continue
        content_tokens = _safe_token_count(content)
        if used_tokens + content_tokens > token_budget:
            continue
        selected.append({"role": role, "content": content})
        used_tokens += content_tokens

    selected.reverse()
    selected.append(latest_message)
    return selected


def _message_stable_id(message: dict, fallback_index: int) -> str:
    return str(message.get("id") or f"idx:{fallback_index}")


def _summary_source_ids(summary: dict | None) -> set[str]:
    if not isinstance(summary, dict):
        return set()
    ids = summary.get("source_message_ids") or []
    return {str(item) for item in ids if item is not None}


def _summary_content(summary: dict | None) -> str:
    if not isinstance(summary, dict):
        return ""
    return str(summary.get("content") or "").strip()


def _clean_message_for_summary(message: dict) -> str:
    content = _strip_process_blocks(str(message.get("content") or "")).strip()
    if not content:
        return ""
    if any(pattern in content for pattern in ERROR_HISTORY_PATTERNS):
        return ""
    limit = MAX_RAG_USER_HISTORY_CHARS if message.get("role") == "user" else MAX_RAG_ASSISTANT_HISTORY_CHARS
    return _truncate_history_content(content, limit)


def _messages_to_summarize(messages: list[dict], cached_summary: dict | None) -> tuple[list[dict], list[str]]:
    latest_user_index = next((idx for idx in range(len(messages) - 1, -1, -1) if messages[idx].get("role") == "user"), None)
    if latest_user_index is None:
        return [], []
    previous = [
        (idx, message)
        for idx, message in enumerate(messages[:latest_user_index])
        if message.get("role") in {"user", "assistant"} and not _is_error_history_message(message)
    ]
    if len(previous) <= SUMMARY_RECENT_MESSAGE_KEEP:
        return [], []

    summarized_ids = _summary_source_ids(cached_summary)
    candidates = previous[:-SUMMARY_RECENT_MESSAGE_KEEP]
    selected = []
    source_ids = set(summarized_ids)
    used_tokens = 0
    for idx, message in candidates:
        message_id = _message_stable_id(message, idx)
        if message_id in summarized_ids:
            continue
        content = _clean_message_for_summary(message)
        if not content:
            source_ids.add(message_id)
            continue
        token_count = _safe_token_count(content)
        if selected and used_tokens + token_count > SUMMARY_SOURCE_TOKEN_LIMIT:
            break
        selected.append({"role": message.get("role"), "content": content, "id": message_id})
        source_ids.add(message_id)
        used_tokens += token_count
    return selected, sorted(source_ids)


async def _resolve_conversation_summary(chat_mdl, llm_model_config, dialog, messages: list[dict], cached_summary: dict | None, depends_on_history: bool):
    if not depends_on_history:
        return None

    new_messages, source_ids = _messages_to_summarize(messages, cached_summary)
    cached_content = _summary_content(cached_summary)
    if not new_messages:
        return cached_summary if cached_content else None

    transcript = "\n".join(
        f"{item['role']} ({item['id']}): {item['content']}"
        for item in new_messages
    )
    system_prompt = (
        "You maintain a compact rolling summary for a RAG chat session.\n"
        "Rules:\n"
        "- Do not include model reasoning, retrieval traces, errors, or raw PDF chunks.\n"
        "- Preserve only facts useful for future follow-up questions.\n"
        "- Keep document IDs or knowledge-base IDs only when explicitly present.\n"
        "- Output in Chinese unless the transcript is mostly English.\n"
        "- Use this exact structure:\n"
        "已确认事实:\n"
        "用户当前目标:\n"
        "重要实体:\n"
        "结构化记忆:\n"
        "- 实体:\n"
        "- 日期:\n"
        "- 金额:\n"
        "- 结论:\n"
        "未解决问题:\n"
        "涉及知识库/文档ID:\n"
    )
    user_prompt = (
        f"Existing summary:\n{cached_content or '(none)'}\n\n"
        f"New conversation turns to merge:\n{transcript}\n\n"
        "Return the updated compact summary."
    )
    try:
        async with _generation_slot(llm_model_config, dialog):
            summary = await chat_mdl.async_chat(
                system_prompt,
                [{"role": "user", "content": user_prompt}],
                {"temperature": 0.1, "max_tokens": SUMMARY_MAX_TOKENS, "reasoning": False, "reasoning_effort": "none"},
            )
    except Exception as exc:  # noqa: BLE001 - summary must never break chat
        logging.warning("ConversationSummary update failed; using cached summary: %s", exc)
        return cached_summary if cached_content else None

    if isinstance(summary, tuple):
        summary = summary[0]
    summary = _strip_process_blocks(str(summary or "")).strip()
    if not summary or any(pattern in summary for pattern in ERROR_HISTORY_PATTERNS):
        return cached_summary if cached_content else None

    return {
        "content": _truncate_to_tokens(summary, SUMMARY_CONTEXT_TOKEN_BUDGET),
        "structured_memory": _structured_memory_from_summary_content(summary),
        "source_message_ids": source_ids,
        "token_count": _safe_token_count(summary),
        "changed": True,
        "updated_at": time.time(),
    }


def _format_conversation_summary_context(summary: dict | None) -> str:
    content = _summary_content(summary)
    if not content:
        return ""
    content = _truncate_to_tokens(content, SUMMARY_CONTEXT_TOKEN_BUDGET)
    return (
        "\n\n### Rolling conversation summary\n"
        "Use this only to resolve follow-up references. Do not treat it as retrieved knowledge evidence.\n"
        f"{content}\n"
    )


SUMMARY_SECTION_HEADING_RE = (
    r"(?:已确认事实|用户当前目标|重要实体|结构化记忆|未解决问题|"
    r"涉及知识库\s*(?:ID\s*)?/\s*文档\s*ID)"
)


def _summary_heading_re(heading: str) -> str:
    if heading == "涉及知识库/文档ID":
        return r"涉及知识库\s*(?:ID\s*)?/\s*文档\s*ID"
    return re.escape(heading)


def _extract_summary_section(content: str, heading: str) -> str:
    pattern = re.compile(
        rf"{_summary_heading_re(heading)}\s*[:：]?\s*(.*?)(?=\n{SUMMARY_SECTION_HEADING_RE}\s*[:：]|\Z)",
        flags=re.DOTALL,
    )
    match = pattern.search(content or "")
    return match.group(1).strip() if match else ""


def _split_summary_items(value: str) -> list[str]:
    items = []
    for raw_line in str(value or "").splitlines():
        line = re.sub(r"^\s*[-*•\d.、]+\s*", "", raw_line).strip()
        line = re.sub(r"^\s*[-–—]\s*", "", line).strip()
        if not line or line in {"无", "none", "None", "null", "N/A", "n/a"}:
            continue
        items.append(line)
    fallback = re.sub(r"^\s*[-–—]\s*", "", str(value or "").strip()).strip()
    if not items and fallback and fallback not in {"无", "none", "None", "null", "N/A", "n/a"}:
        items.append(fallback)
    return items


def _split_inline_values(value: str) -> list[str]:
    cleaned = re.sub(r"^[^:：]{1,12}[:：]\s*", "", str(value or "").strip())
    parts = re.split(r"[;；、]\s*", cleaned)
    return [part.strip() for part in parts if part.strip() and part.strip() not in {"无", "none", "None", "null"}]


def _structured_memory_from_summary_content(content: str) -> dict:
    sections = {
        "facts": _split_summary_items(_extract_summary_section(content, "已确认事实")),
        "current_goal": " ".join(_split_summary_items(_extract_summary_section(content, "用户当前目标"))),
        "entities": _split_summary_items(_extract_summary_section(content, "重要实体")),
        "unresolved": _split_summary_items(_extract_summary_section(content, "未解决问题")),
        "source_ids": _split_summary_items(_extract_summary_section(content, "涉及知识库/文档ID")),
    }
    structured_section = _extract_summary_section(content, "结构化记忆")
    structured = {
        "entities": [],
        "dates": [],
        "amounts": [],
        "conclusions": [],
    }
    for item in _split_summary_items(structured_section):
        normalized = item.strip()
        if re.match(r"^(实体|entities?)\s*[:：]", normalized, flags=re.IGNORECASE):
            structured["entities"].extend(_split_inline_values(normalized))
        elif re.match(r"^(日期|dates?)\s*[:：]", normalized, flags=re.IGNORECASE):
            structured["dates"].extend(_split_inline_values(normalized))
        elif re.match(r"^(金额|numbers?|amounts?)\s*[:：]", normalized, flags=re.IGNORECASE):
            structured["amounts"].extend(_split_inline_values(normalized))
        elif re.match(r"^(结论|conclusions?)\s*[:：]", normalized, flags=re.IGNORECASE):
            structured["conclusions"].extend(_split_inline_values(normalized))
    if not structured["entities"]:
        structured["entities"] = sections["entities"]
    return {
        "facts": sections["facts"],
        "current_goal": sections["current_goal"],
        "entities": list(dict.fromkeys(structured["entities"])),
        "dates": list(dict.fromkeys(structured["dates"])),
        "amounts": list(dict.fromkeys(structured["amounts"])),
        "conclusions": list(dict.fromkeys(structured["conclusions"])),
        "unresolved": sections["unresolved"],
        "source_ids": sections["source_ids"],
    }


def _structured_memory_from_summary(summary: dict | None) -> dict:
    if isinstance(summary, dict) and isinstance(summary.get("structured_memory"), dict):
        return summary["structured_memory"]
    return _structured_memory_from_summary_content(_summary_content(summary))


def _build_structured_memory_text(summary: dict | None) -> str:
    content = _summary_content(summary)
    if not content:
        return ""
    structured = _structured_memory_from_summary(summary)
    body = (
        "会话结构化记忆(JSON):\n"
        + json.dumps(structured, ensure_ascii=False, sort_keys=True)
        + "\n\n会话摘要:\n"
        + content
    )
    return _truncate_to_tokens(body, STRUCTURED_MEMORY_TOKEN_BUDGET)


def _memory_context_is_relevant(query: str, content: str) -> bool:
    if not query or not content:
        return False
    if _history_relevance_score(query, content) > 0:
        return True
    # Keep structured memories when they are strongly entity/date/amount oriented
    # and contain at least one non-trivial Chinese or alphanumeric term from query.
    query_terms = _significant_terms(query)
    content_terms = _significant_terms(content)
    return bool(query_terms and content_terms and query_terms & content_terms)


def _get_or_create_system_conversation_memory(dialog, kbs):
    if not kbs:
        return None
    kb = kbs[0]
    embd_id = getattr(kb, "embd_id", "") or ""
    if not embd_id:
        return None
    existing = list(MemoryService.query(tenant_id=dialog.tenant_id, name=SYSTEM_CONVERSATION_MEMORY_NAME))
    if existing:
        return existing[0]
    _, memory = MemoryService.create_memory(
        dialog.tenant_id,
        SYSTEM_CONVERSATION_MEMORY_NAME,
        [MemoryType.RAW.name.lower()],
        embd_id,
        getattr(kb, "tenant_embd_id", None),
        getattr(dialog, "llm_id", "") or "",
        getattr(dialog, "tenant_llm_id", None),
    )
    try:
        MemoryService.update_memory(
            dialog.tenant_id,
            memory.id,
            {
                "description": "System-managed structured conversation memory for prompt-safe long-context recall.",
                "permissions": "me",
                "memory_size": 20 * 1024 * 1024,
            },
        )
    except Exception as exc:  # noqa: BLE001 - memory metadata update is best effort
        logging.warning("ConversationMemory metadata update failed: %s", exc)
    return MemoryService.get_by_memory_id(memory.id)


async def _persist_structured_conversation_memory(dialog, kbs, summary: dict | None, session_id: str | None):
    content = _build_structured_memory_text(summary)
    if not content:
        return False
    try:
        memory = await thread_pool_exec(_get_or_create_system_conversation_memory, dialog, kbs)
        if not memory:
            logging.info("ConversationMemory skipped: no memory or embedding config available")
            return False
        message_id = REDIS_CONN.generate_auto_increment_id(namespace="memory")
        message = {
            "message_id": message_id,
            "message_type": MemoryType.RAW.name.lower(),
            "source_id": 0,
            "memory_id": memory.id,
            "user_id": getattr(dialog, "tenant_id", ""),
            "agent_id": getattr(dialog, "id", "") or getattr(dialog, "llm_id", ""),
            "session_id": session_id or "",
            "content": content,
            "valid_at": timestamp_to_date(current_timestamp()),
            "invalid_at": None,
            "forget_at": None,
            "status": True,
        }
        ok, msg = await embed_and_save(memory, [message])
        if not ok:
            logging.warning("ConversationMemory save failed memory=%s msg=%s", getattr(memory, "id", ""), msg)
            return False
        logging.info("ConversationMemory saved memory=%s message_id=%s tokens=%s", memory.id, message_id, _safe_token_count(content))
        return True
    except Exception as exc:  # noqa: BLE001 - memory persistence must not break chat
        logging.warning("ConversationMemory save failed: %s", exc)
        return False


ANSWER_LIKE_QUERY_PATTERNS = (
    "主要包括",
    "包括：",
    "包括:",
    "如下",
    "合同条款",
    "违约责任",
    "担保措施",
    "legal protections",
    "include:",
    "includes:",
    "mainly include",
)


def _clean_generated_query_text(text: str) -> str:
    text = _strip_process_blocks(text or "")
    text = re.sub(r"[*`#>]+", " ", text)
    text = re.sub(r"(?i)\b(output|input|chinese|english|中文|英文)\s*[:：]", " ", text)
    text = re.sub(r"\s*(?:###|===)\s*", "\n", text)
    lines = []
    for line in text.splitlines():
        line = re.sub(r"^\s*[-*\d.、]+\s*", "", line).strip()
        if line:
            lines.append(line)
    return " ".join(lines)


def _build_retrieval_query(question: str, fallback_question: str | None = None) -> str:
    normalized = re.sub(r"\s+", " ", _clean_generated_query_text(question)).strip()
    fallback = re.sub(r"\s+", " ", _clean_generated_query_text(fallback_question or "")).strip()
    lower = normalized.lower()

    if not normalized:
        normalized = fallback
    elif any(pattern in lower for pattern in ANSWER_LIKE_QUERY_PATTERNS) and fallback:
        normalized = fallback

    normalized_lower = normalized.lower()
    if (
        ("租金" in normalized or "rent" in normalized_lower or "rents" in normalized_lower)
        and ("契诺" in normalized or "covenant" in normalized_lower or "covenants" in normalized_lower)
        and ("责任" in normalized or "liability" in normalized_lower or "liabilities" in normalized_lower or "保障" in normalized)
    ):
        legal_expansion_terms = [
            "预留基金",
            "个人法律责任",
            "后续申索",
            "转让财产",
            "分配遗产",
            "future claim",
            "sufficient fund",
            "personally liable",
        ]
        existing = normalized_lower
        additions = [term for term in legal_expansion_terms if term.lower() not in existing]
        if additions:
            normalized = f"{normalized} {' '.join(additions)}"

    terms = normalized.split()
    if len(terms) > MAX_RETRIEVAL_QUERY_TERMS:
        normalized = " ".join(terms[:MAX_RETRIEVAL_QUERY_TERMS])

    if len(normalized) <= MAX_RETRIEVAL_QUERY_CHARS:
        return normalized
    return normalized[:MAX_RETRIEVAL_QUERY_CHARS].rstrip()


def _classify_retrieval_scope(question: str) -> str:
    normalized = _normalize_route_text(question)
    if any(word in normalized for word in ("比较", "对比", "区别", "总结", "汇总", "compare", "summary", "summarize")):
        return "summary"
    if any(word in normalized for word in ("研究", "分析", "报告", "趋势", "影响", "research", "analysis", "report")):
        return "research"
    if any(word in normalized for word in ("法律", "条文", "条例", "责任", "保障", "契诺", "租金", "liability", "covenant", "rent")):
        return "legal"
    if len(normalized) <= 40 or any(word in normalized for word in ("是什么", "是谁", "定义", "what is", "define")):
        return "definition"
    return "default"


def _resolve_dynamic_retrieval_limits(dialog, question: str, deep_research_enabled: bool) -> tuple[int, int, str]:
    configured_top_n = _safe_positive_int(getattr(dialog, "top_n", None), DEFAULT_RETRIEVAL_TOP_N)
    configured_top_k = _safe_positive_int(getattr(dialog, "top_k", None), DEFAULT_RETRIEVAL_TOP_K)
    if deep_research_enabled:
        return configured_top_n, configured_top_k, "deep_research"

    scope = _classify_retrieval_scope(question)
    if scope == "definition":
        target_top_n, target_top_k = 5, 512
    elif scope == "legal":
        target_top_n, target_top_k = 8, 1024
    elif scope == "summary":
        target_top_n, target_top_k = 12, 1536
    elif scope == "research":
        target_top_n, target_top_k = 12, 2048
    else:
        target_top_n, target_top_k = 8, 1024

    return max(1, min(configured_top_n, target_top_n)), max(1, min(configured_top_k, target_top_k)), scope


def _chunk_text_for_hash(chunk: dict) -> str:
    return re.sub(r"\s+", " ", str(chunk.get("content_with_weight") or chunk.get("content") or "")).strip().lower()


def _chunk_dedup_key(chunk: dict) -> tuple:
    doc_id = chunk.get("doc_id") or chunk.get("document_id") or ""
    page = chunk.get("page_num_int") or chunk.get("page_num") or ""
    position = chunk.get("position_int") or chunk.get("positions") or ""
    image_id = chunk.get("img_id") or chunk.get("image_id") or ""
    if doc_id and (page or position or image_id):
        return ("loc", doc_id, str(page), str(position), str(image_id))
    digest = hashlib.sha1(_chunk_text_for_hash(chunk)[:5000].encode("utf-8", "ignore")).hexdigest()
    return ("txt", doc_id, digest)


def _deduplicate_retrieved_chunks(kbinfos: dict) -> tuple[int, int]:
    chunks = kbinfos.get("chunks") or []
    seen = set()
    deduped = []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        key = _chunk_dedup_key(chunk)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(chunk)
    if len(deduped) != len(chunks):
        kbinfos["chunks"] = deduped
    return len(chunks), len(deduped)


def _chunk_value(chunk: dict, *keys, default=""):
    for key in keys:
        value = chunk.get(key)
        if value is not None:
            return value
    return default


def _chunk_structured_metadata(chunk: dict) -> dict:
    extra = chunk.get("extra")
    if isinstance(extra, str):
        try:
            extra = json.loads(extra)
        except Exception:  # noqa: BLE001 - malformed metadata should not break retrieval
            extra = {}
    if not isinstance(extra, dict):
        return {}
    structured = extra.get("structured") or extra.get("structured_extraction") or {}
    return structured if isinstance(structured, dict) else {}


_EVIDENCE_EXCERPT_MAX_CHARS = 1800


def _query_terms_for_excerpt(query: str) -> set[str]:
    terms = set()
    for term in re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9_-]{2,}", str(query or "").lower()):
        if len(term) >= 2:
            terms.add(term)
    expansions = {
        "租金": {"rent", "rents"},
        "契诺": {"covenant", "covenants"},
        "法律责任": {"liability", "liabilities"},
        "保障": {"protection", "protections"},
        "受托人": {"trustee"},
        "遗产代理人": {"personal", "representative"},
    }
    for source, expanded in expansions.items():
        if source in str(query or ""):
            terms.update(expanded)
    if "rent" in terms or "rents" in terms:
        terms.add("租金")
    if "covenant" in terms or "covenants" in terms:
        terms.add("契诺")
    if "liability" in terms or "liabilities" in terms:
        terms.add("法律责任")
    return terms


def _split_evidence_units(content: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(content or "")).strip()
    if not normalized:
        return []
    normalized = re.sub(r"(?=(?:\(\d+\)|\([a-z]\)|第\s*\d+\s*条|Section\s+\d+|Part\s+\d+|Division\s+\d+))", "\n", normalized, flags=re.I)
    normalized = re.sub(r"([。！？；;])", r"\1\n", normalized)
    normalized = re.sub(r"(\s(?:or|and)\s+\([a-z]\))", r"\n\1", normalized, flags=re.I)
    return [unit.strip(" \n\r\t") for unit in normalized.splitlines() if unit.strip()]


def _query_focused_content_excerpt(content: str, query: str = "") -> str:
    raw = str(content or "")
    terms = _query_terms_for_excerpt(query)
    if not raw or not terms:
        return raw

    units = _split_evidence_units(raw)
    if not units:
        return raw

    query_text = str(query or "").lower()
    rent_terms = {"租金", "租约", "租費", "租费", "批地", "rent", "rents", "lease", "leases", "grant", "rentcharge"}
    covenant_terms = {"契诺", "协议", "弥偿", "covenant", "covenants", "agreement", "agreements", "indemnity"}
    liability_terms = {"法律责任", "责任", "liability", "liabilities", "protection", "protections", "保障"}
    query_requires_rent_and_covenant = any(term in query_text for term in rent_terms) and any(term in query_text for term in covenant_terms)
    unrelated_neighbor_patterns = (
        "shall not be invalid",
        "nominal share",
        "unsubstantial",
        "illusory",
        "object of the power",
        "share in the property",
    )
    continuation_terms = {
        "已履行",
        "预留",
        "基金",
        "申索",
        "索赔",
        "转易",
        "转让",
        "分配",
        "无须",
        "个人法律责任",
        "出租人",
        "批地人",
        "satisfies all liabilities",
        "sets apart",
        "sufficient fund",
        "future claim",
        "convey",
        "distribute",
        "personally liable",
        "subsequent claim",
        "lessor",
        "grantor",
    }

    selected_indexes: set[int] = set()
    anchor_indexes: set[int] = set()
    for index, unit in enumerate(units):
        unit_lower = unit.lower()
        if any(pattern in unit_lower for pattern in unrelated_neighbor_patterns):
            continue
        if query_requires_rent_and_covenant:
            has_rent = any(term in unit_lower for term in rent_terms)
            has_covenant = any(term in unit_lower for term in covenant_terms)
            has_liability = any(term in unit_lower for term in liability_terms)
            has_exact_topic = "租金及契诺" in unit or "rents and covenants" in unit_lower or "rent and covenant" in unit_lower
            if not (has_exact_topic or (has_rent and has_covenant) or (has_rent and has_liability)):
                continue
        hit_count = sum(1 for term in terms if term and term.lower() in unit_lower)
        if not hit_count:
            continue
        selected_indexes.add(index)
        anchor_indexes.add(index)

    if query_requires_rent_and_covenant and anchor_indexes:
        for anchor in sorted(anchor_indexes):
            for offset in range(1, 8):
                follow_index = anchor + offset
                if follow_index >= len(units):
                    break
                follow = units[follow_index]
                follow_lower = follow.lower()
                if any(pattern in follow_lower for pattern in unrelated_neighbor_patterns):
                    break
                if re.search(r"^(?:29\.|30\.|31-32\.|第\s*29\s*条|第\s*30\s*条|Section\s+29|Section\s+30)\b", follow, flags=re.I):
                    break
                has_continuation = any(term in follow_lower for term in continuation_terms)
                has_same_clause_context = any(term in follow_lower for term in rent_terms | covenant_terms | liability_terms)
                if not has_continuation and not has_same_clause_context:
                    continue
                selected_indexes.add(follow_index)

    if not selected_indexes:
        return "" if query_requires_rent_and_covenant else raw

    selected = [units[index] for index in sorted(selected_indexes)]
    excerpt = " ".join(selected)
    if len(excerpt) > _EVIDENCE_EXCERPT_MAX_CHARS:
        excerpt = excerpt[:_EVIDENCE_EXCERPT_MAX_CHARS].rstrip() + "..."

    if len(excerpt) >= len(raw) * 0.92:
        return raw
    return (
        "[Query-focused excerpt. Use only this focused excerpt for answer generation; "
        "the full source chunk is still available in references.]\n"
        + excerpt
    )


def _format_knowledge_chunk(chunk: dict, chunk_id: int, query: str = "") -> str:
    def draw_node(label, value):
        if value is not None and not isinstance(value, str):
            value = str(value)
        if not value:
            return ""
        return f"\n├── {label}: " + re.sub(r"\n+", " ", value, flags=re.DOTALL)

    content = _query_focused_content_excerpt(_chunk_value(chunk, "content", "content_with_weight"), query)
    if not str(content or "").strip():
        return ""
    formatted = f"\nID: {chunk_id}"
    formatted += draw_node("Title", _chunk_value(chunk, "docnm_kwd", "document_name"))
    formatted += draw_node("URL", chunk.get("url", ""))
    meta = chunk.get("document_metadata") or {}
    if isinstance(meta, dict):
        for key, value in meta.items():
            formatted += draw_node(key, value)
    structured = _chunk_structured_metadata(chunk)
    if structured:
        formatted += draw_node("EvidenceType", structured.get("evidence_type"))
        formatted += draw_node("Clause", structured.get("clause_id"))
        formatted += draw_node("ClauseTitle", structured.get("clause_title"))
    formatted += "\n└── Content:\n"
    formatted += str(content or "")
    return formatted


def _chunk_document_name(chunk: dict) -> str:
    return str(_chunk_value(chunk, "docnm_kwd", "document_name") or "")


def _chunk_content(chunk: dict) -> str:
    return str(_chunk_value(chunk, "content", "content_with_weight") or "")


def _chunk_score(chunk: dict) -> float:
    for key in ("similarity", "vector_similarity", "term_similarity"):
        value = chunk.get(key)
        try:
            if value is not None:
                return round(float(value), 4)
        except (TypeError, ValueError):
            continue
    return 0.0


def _evidence_strength(evidence_type: str) -> tuple[str, str]:
    if evidence_type == "original_text":
        return "strong", ""
    if evidence_type == "raptor_summary_with_sources":
        return "medium", "摘要证据已关联原文，但结论应优先回到关联原文核验"
    if evidence_type == "weak_context":
        return "weak", "片段上下文较弱，需要更多原文证据共同支持"
    if evidence_type == "title_only":
        return "weak", "标题或目录不能单独支撑结论"
    if evidence_type == "raptor_summary":
        return "weak", "摘要缺少关联原文，不能作为强结论依据"
    return "unknown", "证据类型未知，需要人工复核"


def _classify_evidence_chunk(chunk: dict) -> tuple[str, str]:
    content = _chunk_content(chunk).strip()
    compact = re.sub(r"\s+", "", content)
    structured = _chunk_structured_metadata(chunk)
    structured_type = str(structured.get("evidence_type") or "").lower()
    structured_clause = structured.get("clause_id") or structured.get("clause_title")
    has_article_signal = bool(
        re.search(
            r"(第\s*\d+\s*条|Section\s+\d+|subsection|\(\d+\)|\(1\)|凡任何|Where\s+a\s+personal|shall|不得|可将|法律责任|liability)",
            content,
            flags=re.IGNORECASE,
        )
    )
    if is_raptor_summary_chunk(chunk):
        if chunk.get("source_chunks"):
            return "raptor_summary_with_sources", "摘要型证据，已关联原文片段，可辅助定位但不应单独支持强结论"
        return "raptor_summary", "摘要型证据，缺少关联原文，只能作为导航线索"
    if structured_type == "title":
        return "title_only", "结构化识别为标题，不能单独作为结论依据"
    if structured_type == "table":
        return "original_text", "结构化识别为表格证据，可直接用于回答"
    if len(compact) < 80:
        return "title_only", "内容过短，主要像标题或目录，不能单独作为结论依据"
    if structured_type in {"clause", "definition", "fact"} and (structured_clause or has_article_signal):
        return "original_text", "结构化识别为原文证据，包含条文/事实信息，可直接用于回答"
    if not has_article_signal and len(compact) < 220:
        return "weak_context", "片段较短且缺少条文/事实信号，需要其他原文共同支持"
    return "original_text", "包含可直接用于回答的原文或条文信息"


def _build_answer_evidence_plan(evidence: list[dict], cited: set, citation_id_map: dict) -> list[dict]:
    plan = []
    for item in evidence:
        index = item.get("id")
        if index not in cited:
            continue
        fig_id = citation_id_map.get(index)
        evidence_strength, missing_reason = _evidence_strength(str(item.get("type") or ""))
        chunk_id = item.get("chunk_id") or index
        plan.append(
            {
                "claim": f"引用 Fig.{fig_id + 1} 的回答结论" if fig_id is not None else f"引用 ID:{index} 的回答结论",
                "supporting_chunk_ids": [chunk_id],
                "source_ids": [index],
                "fig_ids": [fig_id] if fig_id is not None else [],
                "evidence_strength": evidence_strength,
                "missing_evidence_reason": missing_reason,
            }
        )
    return plan


def _build_evidence_audit(
    kbinfos: dict,
    cited_indexes: set | None,
    question: str,
    retrieval_query: str,
    answer: str = "",
    citation_id_map: dict | None = None,
) -> dict:
    chunks = [chunk for chunk in (kbinfos.get("chunks") or []) if isinstance(chunk, dict)]
    cited = set()
    for raw_index in cited_indexes or set():
        try:
            cited.add(int(raw_index))
        except (TypeError, ValueError):
            continue

    evidence = []
    warnings = []
    type_counts = {}
    citation_id_map = citation_id_map or {}
    for index, chunk in enumerate(chunks):
        evidence_type, reason = _classify_evidence_chunk(chunk)
        fig_id = citation_id_map.get(index)
        type_counts[evidence_type] = type_counts.get(evidence_type, 0) + 1
        if evidence_type in {"title_only", "raptor_summary"}:
            warnings.append(reason)
        evidence.append(
            {
                "id": index,
                "chunk_id": _chunk_value(chunk, "id", "chunk_id"),
                "doc_id": _chunk_value(chunk, "doc_id", "document_id"),
                "doc_name": _chunk_document_name(chunk),
                "type": evidence_type,
                "fig_id": fig_id,
                "score": _chunk_score(chunk),
                "has_image": bool(_chunk_value(chunk, "img_id", "image_id")),
                "is_cited": index in cited,
                "why": reason if index in cited else reason.replace("可直接用于回答", "可作为候选依据"),
                "preview": _chunk_content(chunk).strip()[:260],
            }
        )

    docs = {
        _chunk_value(chunk, "doc_id", "document_id")
        for chunk in chunks
        if _chunk_value(chunk, "doc_id", "document_id")
    }
    answer_basis = []
    if cited:
        answer_basis.append(
            {
                "claim": "最终回答中出现引用标记的结论",
                "source_ids": sorted(cited),
                "fig_ids": [citation_id_map[index] for index in sorted(cited) if index in citation_id_map],
            }
        )
    if any(item["type"] == "original_text" and item["is_cited"] for item in evidence):
        source_ids = [item["id"] for item in evidence if item["type"] == "original_text" and item["is_cited"]]
        answer_basis.append(
            {
                "claim": "优先使用包含原文或条文信息的 chunk",
                "source_ids": source_ids,
                "fig_ids": [citation_id_map[index] for index in source_ids if index in citation_id_map],
            }
        )
    if any(item["type"] in {"title_only", "weak_context"} for item in evidence):
        warnings.append("存在标题型或弱上下文片段，生成答案时不应把它们单独当作充分依据")
    answer_evidence_plan = _build_answer_evidence_plan(evidence, cited, citation_id_map)

    return {
        "intent": "knowledge_base_question",
        "query": question,
        "rewritten_query": retrieval_query,
        "retrieval": {
            "candidate_docs": len([doc for doc in docs if doc]),
            "candidate_chunks": len(chunks),
            "selected_chunks": len(cited),
            "type_counts": type_counts,
        },
        "evidence": evidence,
        "answer_basis": answer_basis,
        "answer_evidence_plan": answer_evidence_plan,
        "warnings": sorted(set(warnings)),
        "answer_citation_markers": sorted(set(CITATION_MARKER_PATTERN.findall(answer))) if answer else [],
    }


def _format_evidence_guidance_for_prompt(kbinfos: dict) -> str:
    chunks = [chunk for chunk in (kbinfos.get("chunks") or []) if isinstance(chunk, dict)]
    if not chunks:
        return ""

    lines = []
    for index, chunk in enumerate(chunks[:12]):
        evidence_type, reason = _classify_evidence_chunk(chunk)
        doc_name = _chunk_document_name(chunk)
        lines.append(f"- ID:{index} {evidence_type}: {reason}; source={doc_name[:90]}")

    return (
        "\n\n### Evidence audit guidance\n"
        "Use this audit to choose reliable evidence before answering. Prefer original_text chunks. "
        "Do not conclude the knowledge base lacks details if at least one original_text chunk directly addresses the question. "
        "Do not rely on title_only or weak_context chunks alone for legal or factual conclusions. "
        "If a RAPTOR summary is used, ground the claim in its linked original source chunks when available.\n"
        + "\n".join(lines)
    )


def _prioritize_evidence_chunks(kbinfos: dict) -> None:
    chunks = [chunk for chunk in (kbinfos.get("chunks") or []) if isinstance(chunk, dict)]
    if len(chunks) < 2:
        return

    priority = {
        "original_text": 0,
        "raptor_summary_with_sources": 1,
        "weak_context": 2,
        "raptor_summary": 3,
        "title_only": 4,
    }
    indexed = []
    for order, chunk in enumerate(chunks):
        evidence_type, _ = _classify_evidence_chunk(chunk)
        indexed.append((priority.get(evidence_type, 2), order, chunk))
    ordered = [chunk for _, _, chunk in sorted(indexed, key=lambda item: (item[0], item[1]))]
    if ordered != chunks:
        kbinfos["chunks"] = ordered
        logging.info(
            "EvidenceAudit reordered chunks original_types=%s",
            [item[0] for item in indexed[:12]],
        )


def _kb_prompt_dynamic(kbinfos: dict, max_tokens: int, query: str = "") -> list[str]:
    chunks = kbinfos.get("chunks") or []
    knowledges = []
    used_token_count = 0
    limit = max(MIN_OUTPUT_TOKENS, int(max_tokens * 0.97))
    for index, chunk in enumerate(chunks):
        if not isinstance(chunk, dict):
            continue
        formatted = _format_knowledge_chunk(chunk, index, query)
        if not formatted:
            continue
        chunk_tokens = _safe_token_count(formatted)
        if knowledges and used_token_count + chunk_tokens > limit:
            logging.warning(
                "KnowledgeBudget trimmed chunks=%s/%s used=%s limit=%s",
                len(knowledges),
                len(chunks),
                used_token_count,
                limit,
            )
            break
        if not knowledges and chunk_tokens > limit:
            formatted = _truncate_to_tokens(formatted, limit)
            chunk_tokens = _safe_token_count(formatted)
        knowledges.append(formatted)
        used_token_count += chunk_tokens
        if used_token_count >= limit:
            break
    kbinfos["_prompt_chunk_count"] = len(knowledges)
    kbinfos["_prompt_knowledge_tokens"] = used_token_count
    return knowledges


def _safe_positive_int(value, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


def _is_deepseek_v4_model(llm_model_config: dict | None, dialog) -> bool:
    llm_name = " ".join(
        str(v or "")
        for v in (
            getattr(dialog, "llm_id", ""),
            (llm_model_config or {}).get("llm_name"),
            (llm_model_config or {}).get("model_name"),
        )
    ).lower()
    return "deepseek-v4" in llm_name or "deepseek v4" in llm_name


def _resolve_dsv4_thinking_mode(prompt_config: dict | None, kwargs: dict | None) -> str:
    kwargs = kwargs or {}
    prompt_config = prompt_config or {}
    reasoning = prompt_config.get("reasoning", False) or kwargs.get("reasoning")
    reasoning_effort = str(kwargs.get("reasoning_effort") or "").strip().lower()
    if reasoning or (reasoning_effort and reasoning_effort != "none"):
        return "thinking"
    return "chat"


def _resolve_model_context_tokens(llm_model_config: dict | None, dialog) -> int:
    configured_tokens = _safe_positive_int((llm_model_config or {}).get("max_tokens"), DEFAULT_MODEL_CONTEXT_TOKENS)
    if _is_deepseek_v4_model(llm_model_config, dialog):
        configured_tokens = max(configured_tokens, DEEPSEEK_V4_CONTEXT_TOKENS)
        configured_tokens = min(configured_tokens, DEEPSEEK_V4_EFFECTIVE_CONTEXT_TOKENS)
    return configured_tokens


def _resolve_output_tokens(llm_setting: dict | None) -> int:
    return _safe_positive_int((llm_setting or {}).get("max_tokens"), DEFAULT_OUTPUT_TOKENS)


def _resolve_context_budgets(llm_model_config: dict | None, dialog) -> dict[str, int]:
    model_context_tokens = _resolve_model_context_tokens(llm_model_config, dialog)
    output_tokens = min(_resolve_output_tokens(getattr(dialog, "llm_setting", None)), max(MIN_OUTPUT_TOKENS, model_context_tokens - MIN_OUTPUT_TOKENS))
    if _is_deepseek_v4_model(llm_model_config, dialog):
        output_tokens = min(
            max(output_tokens, DEEPSEEK_V4_RAG_OUTPUT_TOKENS),
            max(MIN_OUTPUT_TOKENS, model_context_tokens - MIN_OUTPUT_TOKENS),
        )
    prompt_tokens = max(MIN_OUTPUT_TOKENS, model_context_tokens - output_tokens)
    return {
        "model": model_context_tokens,
        "output": output_tokens,
        "prompt": prompt_tokens,
        "knowledge": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * MAX_KNOWLEDGE_CONTEXT_RATIO)),
        "fit": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * MAX_PROMPT_CONTEXT_RATIO)),
    }


def _resolve_retry_context_budgets(context_budget: dict[str, int]) -> dict[str, int]:
    model_context_tokens = min(context_budget["model"], DEEPSEEK_V4_RETRY_CONTEXT_TOKENS)
    output_tokens = min(context_budget["output"], DEFAULT_OUTPUT_TOKENS, max(MIN_OUTPUT_TOKENS, model_context_tokens - MIN_OUTPUT_TOKENS))
    prompt_tokens = max(MIN_OUTPUT_TOKENS, model_context_tokens - output_tokens)
    return {
        "model": model_context_tokens,
        "output": output_tokens,
        "prompt": prompt_tokens,
        "knowledge": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * 0.35)),
        "fit": max(MIN_OUTPUT_TOKENS, int(prompt_tokens * 0.90)),
    }


def _prompt_hard_limit(context_budget: dict[str, int], output_tokens: int) -> int:
    hard_limit = context_budget["fit"]
    if context_budget["model"] >= DEEPSEEK_V4_EFFECTIVE_CONTEXT_TOKENS:
        hard_limit = min(hard_limit, DEEPSEEK_V4_PROMPT_HARD_TOKENS)
    reserve = max(1024, output_tokens)
    return max(MIN_OUTPUT_TOKENS, min(hard_limit, context_budget["model"] - reserve))


def _fit_messages_to_budget(msg: list[dict], context_budget: dict[str, int], gen_conf: dict, stage: str) -> tuple[int, list[dict], int]:
    output_tokens = _safe_positive_int(gen_conf.get("max_tokens"), context_budget["output"])
    prompt_limit = _prompt_hard_limit(context_budget, output_tokens)
    original_count = len(msg)
    used_token_count, fitted_msg = _message_fit_in_dynamic(msg, prompt_limit)
    if len(fitted_msg) < original_count or used_token_count > prompt_limit:
        logging.info(
            "ContextBudget stage=%s trimmed messages=%s->%s used=%s prompt_limit=%s output=%s model=%s",
            stage,
            original_count,
            len(fitted_msg),
            used_token_count,
            prompt_limit,
            output_tokens,
            context_budget["model"],
        )
    return used_token_count, fitted_msg, prompt_limit


def _message_fit_in_dynamic(msg: list[dict], max_length: int) -> tuple[int, list[dict]]:
    fitted = [{"role": m.get("role", "user"), "content": str(m.get("content", ""))} for m in msg or []]

    def count(messages: list[dict]) -> int:
        return _messages_token_count(messages)

    def force_fit(messages: list[dict]) -> tuple[int, list[dict]]:
        """Final hard guard for tokenizer approximation drift.

        The normal trimming path keeps system + current user. Some tokenizers
        count mixed CJK / punctuation more densely than the fallback truncator,
        so this last pass repeatedly trims the largest non-current message
        until the measured count is under the hard prompt limit.
        """
        current = count(messages)
        attempts = 0
        while current > max_length and messages and attempts < 16:
            candidates = list(range(len(messages)))
            if len(messages) > 1:
                candidates = candidates[:-1]
            idx = max(candidates, key=lambda i: _safe_token_count(messages[i].get("content", "")))
            content = messages[idx].get("content", "")
            content_tokens = max(1, _safe_token_count(content))
            excess = max(1, current - max_length)
            keep_tokens = max(1, content_tokens - excess - 8)
            trimmed = _truncate_to_tokens(content, keep_tokens)
            if trimmed == content:
                trimmed = content[: max(0, len(content) // 2)]
            messages[idx]["content"] = trimmed
            current = count(messages)
            attempts += 1
        return current, messages

    current_count = count(fitted)
    if current_count < max_length:
        return current_count, fitted

    preserved = [m for m in fitted if m.get("role") == "system"]
    if len(fitted) > 1:
        preserved.append(fitted[-1])
    fitted = preserved
    current_count = count(fitted)
    if current_count < max_length:
        return current_count, fitted

    if not fitted:
        return 0, fitted

    if len(fitted) == 1:
        fitted[0]["content"] = _truncate_to_tokens(fitted[0]["content"], max_length)
        return force_fit(fitted)

    system_tokens = max(0, _safe_token_count(fitted[0].get("content", "")))
    user_tokens = max(0, _safe_token_count(fitted[-1].get("content", "")))
    total = system_tokens + user_tokens
    if total <= 0:
        return 0, fitted

    if system_tokens / total > 0.8:
        preserved_user = min(user_tokens, max_length)
        fitted[-1]["content"] = _truncate_to_tokens(fitted[-1]["content"], preserved_user)
        fitted[0]["content"] = _truncate_to_tokens(fitted[0]["content"], max(0, max_length - preserved_user))
        return force_fit(fitted)

    preserved_system = min(system_tokens, max_length)
    fitted[0]["content"] = _truncate_to_tokens(fitted[0]["content"], preserved_system)
    fitted[-1]["content"] = _truncate_to_tokens(fitted[-1]["content"], max(0, max_length - preserved_system))
    return force_fit(fitted)


@asynccontextmanager
async def _generation_slot(llm_model_config: dict | None, dialog):
    if not _is_deepseek_v4_model(llm_model_config, dialog):
        yield
        return
    logging.debug("DS4GenerationQueue waiting max_concurrent=%s llm_id=%s", DS4_MAX_CONCURRENT_GENERATIONS, dialog.llm_id)
    async with DS4_GENERATION_SEMAPHORE:
        logging.debug("DS4GenerationQueue acquired llm_id=%s", dialog.llm_id)
        yield


def _log_rag_token_budget(
    stage: str,
    context_budget: dict[str, int],
    msg: list[dict],
    gen_conf: dict,
    kbinfos: dict,
    retrieval_scope: str,
    retrieval_top_n: int,
    retrieval_top_k: int,
    knowledge_text: str,
    memory_context_text: str,
    attachments_text: str,
) -> None:
    try:
        output_tokens = _safe_positive_int(gen_conf.get("max_tokens"), context_budget["output"])
        system_tokens = _safe_token_count(msg[0].get("content", "")) if msg else 0
        latest_user_tokens = 0
        history_tokens = 0
        user_indexes = [idx for idx, m in enumerate(msg) if m.get("role") == "user"]
        latest_user_index = user_indexes[-1] if user_indexes else None
        for idx, message in enumerate(msg[1:], start=1):
            tokens = _safe_token_count(message.get("content", ""))
            if latest_user_index is not None and idx == latest_user_index:
                latest_user_tokens += tokens
            else:
                history_tokens += tokens
        logging.info(
            "RAGTokenBudget stage=%s model=%s prompt_fit=%s prompt_hard=%s output=%s final_prompt=%s "
            "system=%s knowledge=%s memory=%s attachments=%s history=%s question=%s chunks=%s docs=%s "
            "retrieval_scope=%s top_n=%s top_k=%s",
            stage,
            context_budget["model"],
            context_budget["fit"],
            _prompt_hard_limit(context_budget, output_tokens),
            output_tokens,
            _messages_token_count(msg),
            system_tokens,
            _safe_token_count(knowledge_text),
            _safe_token_count(memory_context_text),
            _safe_token_count(attachments_text),
            history_tokens,
            latest_user_tokens,
            len(kbinfos.get("chunks", [])),
            len(kbinfos.get("doc_aggs", [])),
            retrieval_scope,
            retrieval_top_n,
            retrieval_top_k,
        )
    except Exception as exc:  # noqa: BLE001 - budget logging is diagnostic only
        logging.warning("RAGTokenBudget logging failed at stage=%s: %s", stage, exc)


def _is_context_span_error(exc: Exception | str) -> bool:
    text = str(exc).lower()
    return any(pattern in text for pattern in CONTEXT_SPAN_ERROR_PATTERNS)


def _memory_topic_text(memory: dict) -> str:
    display_name = get_memory_display_name(memory.get("name"), memory.get("description"))
    pieces = [display_name]
    if memory.get("description"):
        pieces.append(str(memory.get("description")))
    if memory.get("name") and str(memory.get("name")) != display_name:
        pieces.append(str(memory.get("name")))
    return " ".join(piece for piece in pieces if piece).strip()


def _select_topic_relevant_memories(memories: list[dict], query: str) -> list[dict]:
    if not memories or not query:
        return []
    query_lower = str(query).lower()
    scored = []
    for memory in memories:
        topic_text = _memory_topic_text(memory)
        if not topic_text:
            continue
        query_terms = _significant_terms(query)
        topic_terms = _significant_terms(topic_text)
        overlap = query_terms & topic_terms
        if not overlap:
            continue
        score = len(overlap)
        topic_lower = topic_text.lower()
        if query_lower and query_lower in topic_lower:
            score += 3
        if score > 0:
            scored.append((score, memory))
    if not scored:
        return []
    scored.sort(key=lambda item: item[0], reverse=True)
    return [memory for _, memory in scored[: max(MAX_MEMORY_GROUPS * MAX_MEMORY_RESULTS, MAX_MEMORY_RESULTS)]]


def _group_accessible_memories_for_query(tenant_id: str, query: str) -> list[list[str]]:
    memories, _ = MemoryService.get_by_filter({"accessible_user_id": tenant_id}, "", page=1, page_size=50)
    memories = _select_topic_relevant_memories(memories, query)
    grouped: dict[tuple[str, str], list[str]] = {}
    for memory in memories:
        key = (str(memory.get("tenant_embd_id") or ""), str(memory.get("embd_id") or ""))
        grouped.setdefault(key, []).append(memory["id"])
    return list(grouped.values())[:MAX_MEMORY_GROUPS]


async def _retrieve_memory_context(tenant_id: str, query: str, token_budget: int = MEMORY_CONTEXT_TOKENS) -> list[str]:
    if not feature_enabled("memory_context"):
        return []
    if not query:
        return []
    try:
        memory_groups = await thread_pool_exec(_group_accessible_memories_for_query, tenant_id, query)
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
            if content and _memory_context_is_relevant(query, str(content)):
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
    semantic_route = _semantic_route_layer(latest_question, kwargs)
    logging.info(
        "SemanticRoute route=%s score=%.3f reason=%s elapsed_ms=%.2f question=%s",
        semantic_route.get("route"),
        float(semantic_route.get("score") or 0),
        semantic_route.get("reason"),
        float(semantic_route.get("elapsed_ms") or 0),
        latest_question[:120],
    )
    pure_llm_route, route_reason = _should_route_to_pure_llm(latest_question, kwargs, semantic_route)
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
    dsv4_thinking_mode = _resolve_dsv4_thinking_mode(getattr(dialog, "prompt_config", None), kwargs)
    token_counter = DynamicTokenCounter.from_model_config(llm_model_config, dsv4_thinking_mode=dsv4_thinking_mode)
    ACTIVE_TOKEN_COUNTER.set(token_counter)
    logging.debug(
        "TokenizerCounter model=%s provider=%s base_url=%s fallback_safety=%.2f dsv4_thinking_mode=%s",
        token_counter.model_name,
        token_counter.provider,
        token_counter.base_url,
        token_counter.fallback_safety_factor,
        token_counter.resolved_dsv4_thinking_mode,
    )
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
    tts_config = (prompt_config or {}).get("tts_config") or {}
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
    latest_semantic_route = semantic_route if latest_user_question == latest_question else _semantic_route_layer(latest_user_question, kwargs)
    depends_on_history = _question_depends_on_history(latest_user_question, latest_semantic_route)
    cached_conversation_summary = kwargs.get(CONVERSATION_SUMMARY_KEY)
    if not isinstance(cached_conversation_summary, dict):
        cached_conversation_summary = None
    reset_conversation_summary, topic_reset_reason = await _should_reset_topic_with_semantics(
        latest_user_question,
        cached_conversation_summary,
        messages,
        depends_on_history,
        embd_mdl,
    )
    use_history_context = depends_on_history and not reset_conversation_summary
    if reset_conversation_summary:
        logging.info("ConversationSummary reset reason=%s question=%s", topic_reset_reason, latest_user_question[:120])

    if len(questions) > 1 and prompt_config.get("refine_multiturn") and use_history_context:
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
    retrieval_query = _build_retrieval_query(questions[-1], latest_user_question)
    refine_question_ts = timer()

    thought = ""
    kbinfos = {"total": 0, "chunks": [], "doc_aggs": []}
    knowledges = []
    deep_research_enabled = False
    retrieval_top_n = _safe_positive_int(getattr(dialog, "top_n", None), DEFAULT_RETRIEVAL_TOP_N)
    retrieval_top_k = _safe_positive_int(getattr(dialog, "top_k", None), DEFAULT_RETRIEVAL_TOP_K)
    retrieval_scope = "not_retrieved"

    if "knowledge" in param_keys:
        logging.debug("Proceeding with retrieval")
        deep_research_enabled = prompt_config.get("reasoning", False) or kwargs.get("reasoning")
        retrieval_top_n, retrieval_top_k, retrieval_scope = _resolve_dynamic_retrieval_limits(dialog, retrieval_query, deep_research_enabled)
        logging.info(
            "RetrievalPlanner scope=%s top_n=%s top_k=%s configured_top_n=%s configured_top_k=%s query=%s",
            retrieval_scope,
            retrieval_top_n,
            retrieval_top_k,
            getattr(dialog, "top_n", None),
            getattr(dialog, "top_k", None),
            retrieval_query[:160],
        )
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
                    page_size=retrieval_top_n,
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
                    retrieval_top_n,
                    dialog.similarity_threshold,
                    dialog.vector_similarity_weight,
                    doc_ids=attachments,
                    top=retrieval_top_k,
                    aggs=True,
                    rerank_mdl=rerank_mdl,
                    rank_feature=label_question(retrieval_query, kbs),
                )
                if prompt_config.get("toc_enhance"):
                    cks = await retriever.retrieval_by_toc(retrieval_query, kbinfos["chunks"], tenant_ids, chat_mdl, retrieval_top_n)
                    if cks:
                        kbinfos["chunks"] = cks
                kbinfos["chunks"] = retriever.retrieval_by_children(kbinfos["chunks"], tenant_ids)
                before_dedup, after_dedup = _deduplicate_retrieved_chunks(kbinfos)
                if before_dedup != after_dedup:
                    logging.info("RetrievalDedup chunks=%s->%s query=%s", before_dedup, after_dedup, retrieval_query[:160])
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
                before_dedup, after_dedup = _deduplicate_retrieved_chunks(kbinfos)
                if before_dedup != after_dedup:
                    logging.info("RetrievalDedup after_web chunks=%s->%s query=%s", before_dedup, after_dedup, retrieval_query[:160])
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
                    _deduplicate_retrieved_chunks(kbinfos)
                    yield {"answer": "Added knowledge graph context.\n", "reference": {}, "audio_binary": None, "final": False}
        if not deep_research_enabled:
            yield {
                "answer": "Preparing retrieved evidence for answer generation.\n</retrieving>",
                "reference": {},
                "audio_binary": None,
                "final": False,
            }

    before_dedup, after_dedup = _deduplicate_retrieved_chunks(kbinfos)
    if before_dedup != after_dedup:
        logging.info("RetrievalDedup final chunks=%s->%s query=%s", before_dedup, after_dedup, retrieval_query[:160])

    if include_reference_metadata:
        logging.debug(
            "reference_metadata enrichment enabled for async_chat: chunk_count=%d metadata_fields=%s",
            len(kbinfos.get("chunks", [])),
            metadata_fields,
        )
        _enrich_chunks_with_document_metadata(kbinfos.get("chunks", []), metadata_fields)

    expand_raptor_chunks_for_generation(kbinfos)
    _prioritize_evidence_chunks(kbinfos)
    knowledges = _kb_prompt_dynamic(kbinfos, context_budget["knowledge"], retrieval_query)
    logging.debug("{}->{}".format(" ".join(questions), "\n->".join(knowledges)))
    evidence_guidance_text = _format_evidence_guidance_for_prompt(kbinfos) if knowledges else ""
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
        yield {"answer": empty_res, "reference": kbinfos, "prompt": "\n\n### Query:\n%s" % " ".join(questions), "audio_binary": visible_tts(tts_mdl, empty_res, tts_config=tts_config), "final": True}
        return

    kwargs["knowledge"] = "\n------\n" + "\n\n------\n\n".join(knowledges)
    gen_conf = deepcopy(dialog.llm_setting or {})
    if prompt_config.get("reasoning", False) or kwargs.get("reasoning"):
        gen_conf["reasoning"] = True
    gen_conf["max_tokens"] = context_budget["output"]

    memory_context_text = ""
    if memory_context:
        memory_context_text = "\n\n### Conversation memory:\n" + "\n".join(f"- {m}" for m in memory_context)

    if reset_conversation_summary:
        conversation_summary_update = {"content": "", "reset": True, "reason": topic_reset_reason, "updated_at": time.time()}
        prompt_conversation_summary = None
    else:
        conversation_summary_update = None
        prompt_conversation_summary = cached_conversation_summary if use_history_context else None
    summary_update_pending = use_history_context and not reset_conversation_summary
    conversation_summary_text = _format_conversation_summary_context(prompt_conversation_summary)
    if conversation_summary_text:
        logging.info(
            "ConversationSummary injected cached tokens=%s source_messages=%s",
            _safe_token_count(conversation_summary_text),
            len((prompt_conversation_summary or {}).get("source_message_ids") or []),
        )

    prompt4citation = ""
    if knowledges and (prompt_config.get("quote", True) and kwargs.get("quote", True)):
        prompt4citation = COMPACT_CITATION_PROMPT
    system_prompt = prompt_config["system"].format(**kwargs) + evidence_guidance_text + conversation_summary_text + memory_context_text + attachments_ + prompt4citation
    msg = [{"role": "system", "content": system_prompt}]
    generation_history = _rag_generation_messages(
        messages,
        latest_user_question,
        use_history_context,
        min(MAX_RAG_HISTORY_TOKENS, max(MIN_OUTPUT_TOKENS, context_budget["prompt"] // 8)),
    )
    msg.extend([{"role": m["role"], "content": re.sub(r"##\d+\$\$", "", m["content"])} for m in generation_history if m["role"] != "system"])
    used_token_count, msg, prompt_hard_limit = _fit_messages_to_budget(msg, context_budget, gen_conf, "initial")
    if llm_type == "chat" and image_attachments:
        convert_last_user_msg_to_multimodal(msg, image_attachments, factory)
    assert len(msg) >= 2, f"message_fit_in has bug: {msg}"
    prompt = msg[0]["content"]
    prompt4citation = ""

    available_output_tokens = max(MIN_OUTPUT_TOKENS, max_tokens - used_token_count)
    gen_conf["max_tokens"] = max(MIN_OUTPUT_TOKENS, min(int(gen_conf["max_tokens"]), available_output_tokens))
    _log_rag_token_budget(
        "initial",
        context_budget,
        msg,
        gen_conf,
        kbinfos,
        retrieval_scope,
        retrieval_top_n,
        retrieval_top_k,
        kwargs.get("knowledge", ""),
        memory_context_text,
        attachments_,
    )

    async def decorate_answer(answer, include_think=True):
        nonlocal embd_mdl, prompt_config, knowledges, kwargs, kbinfos, prompt, retrieval_ts, questions, langfuse_generation

        refs = []
        ans = answer.split("</think>")
        think = ""
        if len(ans) == 2:
            think = ans[0] + "</think>"
            answer = ans[1]

        if any(pattern in answer for pattern in ERROR_HISTORY_PATTERNS):
            cleaned_error = _strip_process_blocks(answer)
            return {
                "answer": cleaned_error or answer,
                "reference": {"chunks": [], "doc_aggs": []},
            }

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
            answer, refs, citation_id_map = build_compact_reference(answer, kbinfos, idx)
            if feature_enabled("evidence_audit"):
                refs["evidence_audit"] = build_compact_evidence_audit(
                    refs,
                    " ".join(questions),
                    retrieval_query,
                    answer,
                )

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

        final_conversation_summary_update = conversation_summary_update
        if summary_update_pending:
            final_conversation_summary_update = await _resolve_conversation_summary(
                chat_mdl,
                llm_model_config,
                dialog,
                messages,
                cached_conversation_summary,
                True,
            )

        result_answer = (think if include_think else "") + answer
        result = {"answer": result_answer, "reference": refs, "prompt": re.sub(r"\n", "  \n", prompt), "created_at": time.time()}
        if isinstance(final_conversation_summary_update, dict) and (final_conversation_summary_update.get("content") or final_conversation_summary_update.get("reset")):
            result[CONVERSATION_SUMMARY_KEY] = final_conversation_summary_update
            if final_conversation_summary_update.get("content") and final_conversation_summary_update.get("changed"):
                await _persist_structured_conversation_memory(dialog, kbs, final_conversation_summary_update, kwargs.get("_session_id"))
        return result

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

    async def run_model_stream(current_prompt, current_msg, current_gen_conf):
        async with _generation_slot(llm_model_config, dialog):
            if llm_type == "chat":
                current_stream_iter = chat_mdl.async_chat_streamly_delta(current_prompt, current_msg[1:], current_gen_conf)
            else:
                current_stream_iter = chat_mdl.async_chat_streamly_delta(current_prompt, current_msg[1:], current_gen_conf, images=image_files)
            async for item in _stream_with_think_delta(current_stream_iter):
                yield item

    async def run_model_once(current_prompt, current_msg, current_gen_conf):
        async with _generation_slot(llm_model_config, dialog):
            if llm_type == "chat":
                return await chat_mdl.async_chat(current_prompt, current_msg[1:], current_gen_conf)
            return await chat_mdl.async_chat(current_prompt, current_msg[1:], current_gen_conf, images=image_files)

    def build_context_retry_payload():
        retry_budget = _resolve_retry_context_budgets(context_budget)
        retry_knowledges = _kb_prompt_dynamic(kbinfos, retry_budget["knowledge"], retrieval_query)
        retry_kwargs = deepcopy(kwargs)
        retry_kwargs["knowledge"] = "\n------\n" + "\n\n------\n\n".join(retry_knowledges)
        retry_prompt4citation = ""
        if retry_knowledges and (prompt_config.get("quote", True) and kwargs.get("quote", True)):
            retry_prompt4citation = COMPACT_CITATION_PROMPT
        retry_evidence_guidance_text = _format_evidence_guidance_for_prompt(kbinfos) if retry_knowledges else ""
        retry_system_prompt = prompt_config["system"].format(**retry_kwargs) + retry_evidence_guidance_text + conversation_summary_text + memory_context_text + attachments_ + retry_prompt4citation
        retry_msg = [{"role": "system", "content": retry_system_prompt}]
        retry_msg.extend([{"role": m["role"], "content": re.sub(r"##\d+\$\$", "", m["content"])} for m in generation_history if m["role"] != "system"])
        retry_gen_conf = deepcopy(gen_conf)
        retry_gen_conf["max_tokens"] = min(_safe_positive_int(retry_gen_conf.get("max_tokens"), retry_budget["output"]), retry_budget["output"])
        retry_used_token_count, retry_msg, _ = _fit_messages_to_budget(retry_msg, retry_budget, retry_gen_conf, "retry")
        if llm_type == "chat" and image_attachments:
            convert_last_user_msg_to_multimodal(retry_msg, image_attachments, factory)
        retry_prompt = retry_msg[0]["content"]
        available_output_tokens = max(MIN_OUTPUT_TOKENS, retry_budget["model"] - retry_used_token_count)
        retry_gen_conf["max_tokens"] = max(
            MIN_OUTPUT_TOKENS,
            min(int(retry_gen_conf["max_tokens"]), retry_budget["output"], available_output_tokens),
        )
        logging.warning(
            "ContextBudget retry model=%s prompt=%s knowledge=%s fit=%s output=%s used=%s llm_id=%s",
            retry_budget["model"],
            retry_budget["prompt"],
            retry_budget["knowledge"],
            retry_budget["fit"],
            retry_budget["output"],
            retry_used_token_count,
            dialog.llm_id,
        )
        _log_rag_token_budget(
            "retry",
            retry_budget,
            retry_msg,
            retry_gen_conf,
            kbinfos,
            retrieval_scope,
            retrieval_top_n,
            retrieval_top_k,
            retry_kwargs.get("knowledge", ""),
            memory_context_text,
            attachments_,
        )
        return retry_prompt, retry_msg, retry_gen_conf

    if stream:
        if "knowledge" in param_keys and not deep_research_enabled:
            yield {
                "answer": "<think>Reviewing retrieved evidence and composing the answer.\n</think>",
                "reference": {},
                "audio_binary": None,
                "final": False,
            }
        last_state = None
        try:
            async for kind, value, state in run_model_stream(prompt, msg, gen_conf):
                last_state = state
                if kind == "marker":
                    flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                    yield {"answer": "", "reference": {}, "audio_binary": None, "final": False, **flags}
                    continue
                if _is_context_span_error(value):
                    raise RuntimeError(value)
                yield {"answer": value, "reference": {}, "audio_binary": visible_tts(tts_mdl, value, state.in_think, tts_config), "final": False}
        except Exception as exc:
            if not _is_context_span_error(exc):
                raise
            logging.warning("Context span error from LLM; retrying with reduced prompt budget: %s", exc)
            retry_prompt, retry_msg, retry_gen_conf = build_context_retry_payload()
            last_state = None
            async for kind, value, state in run_model_stream(retry_prompt, retry_msg, retry_gen_conf):
                last_state = state
                if kind == "marker":
                    flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                    yield {"answer": "", "reference": {}, "audio_binary": None, "final": False, **flags}
                    continue
                if _is_context_span_error(value):
                    raise RuntimeError(value)
                yield {"answer": value, "reference": {}, "audio_binary": visible_tts(tts_mdl, value, state.in_think, tts_config), "final": False}
        full_answer = last_state.full_text if last_state else ""
        if full_answer:
            final = await decorate_answer(_extract_visible_answer(thought + full_answer), include_think=False)
            final["final"] = True
            final["audio_binary"] = None
            yield final
    else:
        try:
            answer = await run_model_once(prompt, msg, gen_conf)
            if _is_context_span_error(answer):
                raise RuntimeError(answer)
        except Exception as exc:
            if not _is_context_span_error(exc):
                raise
            logging.warning("Context span error from LLM; retrying non-stream request with reduced prompt budget: %s", exc)
            retry_prompt, retry_msg, retry_gen_conf = build_context_retry_payload()
            answer = await run_model_once(retry_prompt, retry_msg, retry_gen_conf)
        user_content = msg[-1].get("content", "[content not available]")
        logging.debug("User: {}|Assistant: {}".format(user_content, answer))
        res = await decorate_answer(answer)
        res["audio_binary"] = visible_tts(tts_mdl, answer, tts_config=tts_config)
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


def tts(tts_mdl, text, tts_config=None):
    if not tts_mdl or not text:
        return None
    text = clean_tts_text(text)
    if not text:
        return None
    engine_settings = PanythonTTSSettingsService.get_settings()
    if not engine_settings.get("tts_enabled"):
        return None
    tts_kwargs = build_tts_kwargs(tts_config, text, engine_settings)
    return synthesize_with_cache(tts_mdl, text, **tts_kwargs)


def visible_tts(tts_mdl, text, in_think: bool = False, tts_config=None):
    if in_think:
        return None
    text = _strip_process_blocks(text)
    if not text:
        return None
    return tts(tts_mdl, text, tts_config)


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


def _strip_process_blocks(text: str) -> str:
    text = THINK_BLOCK_PATTERN.sub("", text or "")
    text = RETRIEVING_BLOCK_PATTERN.sub("", text)
    return PROCESS_TAG_PATTERN.sub("", text).strip()


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


async def async_ask(question, kb_ids, tenant_id, chat_llm_name=None, search_config=None, search_id=None):
    search_config = search_config or {}
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
    class _SearchSummaryDialog:
        def __init__(self, llm_id, llm_setting, top_n, top_k):
            self.llm_id = llm_id or ""
            self.llm_setting = llm_setting or {}
            self.top_n = top_n
            self.top_k = top_k

    search_llm_setting = deepcopy(search_config.get("llm_setting") or {})
    search_dialog = _SearchSummaryDialog(
        chat_llm_name or (chat_model_config or {}).get("llm_name", ""),
        search_llm_setting,
        search_config.get("top_n", DEFAULT_RETRIEVAL_TOP_N),
        search_config.get("top_k", DEFAULT_RETRIEVAL_TOP_K),
    )
    context_budget = _resolve_context_budgets(chat_model_config, search_dialog)
    if _is_deepseek_v4_model(chat_model_config, search_dialog):
        # Search result summaries are auxiliary UI content. Keep them on the
        # safer 32K lane so they cannot destabilize the shared DS4 service.
        context_budget = _resolve_retry_context_budgets(context_budget)
        context_budget["output"] = min(
            DEEPSEEK_V4_RAG_OUTPUT_TOKENS,
            max(MIN_OUTPUT_TOKENS, context_budget["model"] - MIN_OUTPUT_TOKENS),
        )
        context_budget["prompt"] = max(MIN_OUTPUT_TOKENS, context_budget["model"] - context_budget["output"])
        context_budget["knowledge"] = max(MIN_OUTPUT_TOKENS, int(context_budget["prompt"] * 0.35))
        context_budget["fit"] = max(MIN_OUTPUT_TOKENS, int(context_budget["prompt"] * 0.90))
    retrieval_top_n, retrieval_top_k, retrieval_scope = _resolve_dynamic_retrieval_limits(search_dialog, question, False)
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
        page_size=retrieval_top_n,
        similarity_threshold=search_config.get("similarity_threshold", 0.1),
        vector_similarity_weight=vector_similarity_weight,
        top=retrieval_top_k,
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

    original_chunk_count, deduped_chunk_count = _deduplicate_retrieved_chunks(kbinfos)
    expand_raptor_chunks_for_generation(kbinfos)
    _prioritize_evidence_chunks(kbinfos)
    if original_chunk_count != deduped_chunk_count:
        logging.info(
            "SearchSummary deduplicated chunks=%s->%s search_id=%s",
            original_chunk_count,
            deduped_chunk_count,
            search_id,
        )

    knowledges = []
    sys_prompt = ""
    msg = []
    gen_conf = {}

    def build_generation_payload(current_budget: dict[str, int], stage: str):
        current_knowledges = _kb_prompt_dynamic(kbinfos, current_budget["knowledge"], question)
        evidence_guidance_text = _format_evidence_guidance_for_prompt(kbinfos) if current_knowledges else ""
        current_sys_prompt = PROMPT_JINJA_ENV.from_string(ASK_SUMMARY).render(knowledge="\n".join(current_knowledges)) + evidence_guidance_text
        current_gen_conf = deepcopy(search_llm_setting)
        current_gen_conf["temperature"] = 0.1
        current_gen_conf["max_tokens"] = min(
            _safe_positive_int(current_gen_conf.get("max_tokens"), current_budget["output"]),
            current_budget["output"],
        )
        current_msg = [
            {"role": "system", "content": current_sys_prompt},
            {"role": "user", "content": question},
        ]
        used_token_count, current_msg, _ = _fit_messages_to_budget(current_msg, current_budget, current_gen_conf, stage)
        available_output_tokens = max(MIN_OUTPUT_TOKENS, current_budget["model"] - used_token_count)
        current_gen_conf["max_tokens"] = max(
            MIN_OUTPUT_TOKENS,
            min(int(current_gen_conf["max_tokens"]), current_budget["output"], available_output_tokens),
        )
        _log_rag_token_budget(
            stage,
            current_budget,
            current_msg,
            current_gen_conf,
            kbinfos,
            retrieval_scope,
            retrieval_top_n,
            retrieval_top_k,
            "\n".join(current_knowledges),
            "",
            "",
        )
        return current_msg[0]["content"], current_msg, current_gen_conf, current_knowledges

    async def decorate_answer(answer):
        nonlocal knowledges, kbinfos
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

    async def run_summary_stream(current_prompt, current_msg, current_gen_conf):
        async with _generation_slot(chat_model_config, search_dialog):
            current_stream_iter = chat_mdl.async_chat_streamly_delta(current_prompt, current_msg[1:], current_gen_conf)
            async for item in _stream_with_think_delta(current_stream_iter):
                yield item

    sys_prompt, msg, gen_conf, knowledges = build_generation_payload(context_budget, "search_summary_initial")
    last_state = None
    try:
        async for kind, value, state in run_summary_stream(sys_prompt, msg, gen_conf):
            last_state = state
            if kind == "marker":
                flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                yield {"answer": "", "reference": {}, "final": False, **flags}
                continue
            if _is_context_span_error(value):
                raise RuntimeError(value)
            yield {"answer": value, "reference": {}, "final": False}
    except Exception as exc:
        if not _is_context_span_error(exc):
            raise
        logging.warning("SearchSummary context span error; retrying with reduced prompt budget: %s", exc)
        retry_budget = _resolve_retry_context_budgets(context_budget)
        sys_prompt, msg, gen_conf, knowledges = build_generation_payload(retry_budget, "search_summary_retry")
        last_state = None
        async for kind, value, state in run_summary_stream(sys_prompt, msg, gen_conf):
            last_state = state
            if kind == "marker":
                flags = {"start_to_think": True} if value == "<think>" else {"end_to_think": True}
                yield {"answer": "", "reference": {}, "final": False, **flags}
                continue
            if _is_context_span_error(value):
                raise RuntimeError(value)
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
