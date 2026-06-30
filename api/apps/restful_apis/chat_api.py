#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
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

import json
import logging
import io
import os
import re
import wave
import asyncio
import tempfile
import binascii
from difflib import SequenceMatcher
from copy import deepcopy
from datetime import datetime
from types import SimpleNamespace

from quart import Response, request

from api.apps import current_user, login_required
from api.db.db_models import UserManagementOperationLog
from api.db.joint_services.tenant_model_service import (
    get_model_config_by_type_and_name,
    get_tenant_default_model_by_type,
)
from api.db.services.chunk_feedback_service import ChunkFeedbackService
from api.db.services.conversation_service import ConversationService, structure_answer
from api.db.services.dialog_service import DialogService, async_chat, gen_mindmap
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.llm_service import LLMBundle
from api.db.services.memory_service import MemoryService
from api.db.services.panython_tts_settings_service import PanythonTTSSettingsService, build_tts_kwargs
from api.db.services.panython_asr_settings_service import PanythonASRSettingsService
from api.db.services.search_service import SearchService
from api.db.services.tenant_llm_service import TenantLLMService
from api.db.joint_services.memory_message_service import queue_save_to_memory_task
from api.db.services.user_service import TenantService, UserTenantService
from api.utils.api_utils import (
    check_duplicate_ids,
    get_data_error_result,
    get_json_result,
    get_request_json,
    server_error_response,
    validate_request,
)
from api.apps.services import memory_profile_service
from api.utils.tenant_utils import ensure_tenant_model_id_for_params
from common.constants import LLMType, RetCode, StatusEnum
from common import settings
from common.misc_utils import get_uuid, thread_pool_exec
from rag.prompts.generator import chunks_format
from rag.prompts.template import load_prompt
from rag.utils.redis_conn import REDIS_CONN
from memory.services.messages import MessageService

_DEFAULT_PROMPT_CONFIG = {
    "system": (
        'You are an intelligent assistant. Please summarize the content of the dataset to answer the question. '
        'Please list the data in the dataset and answer in detail. When all dataset content is irrelevant to the '
        'question, your answer must include the sentence "The answer you are looking for is not found in the dataset!" '
        "Answers need to consider chat history.\n"
        "      Here is the knowledge base:\n"
        "      {knowledge}\n"
        "      The above is the knowledge base."
    ),
    "prologue": "Hi! I'm your assistant. What can I do for you?",
    "parameters": [{"key": "knowledge", "optional": False}],
    "empty_response": "Sorry! No relevant content was found in the knowledge base!",
    "quote": True,
    "tts": False,
    "refine_multiturn": True,
}
_DEFAULT_DIRECT_CHAT_PROMPT_CONFIG = {
    "system": "",
    "prologue": "",
    "parameters": [],
    "empty_response": "",
    "quote": False,
    "tts": False,
    "refine_multiturn": True,
}

_CHAT_MESSAGE_DELETE_LOG_LIMIT = 1200


def _truncate_deleted_message_log_text(value, limit=_CHAT_MESSAGE_DELETE_LOG_LIMIT):
    if value is None:
        return ""
    if not isinstance(value, str):
        value = json.dumps(value, ensure_ascii=False)
    value = _strip_memo_process_text(value)
    value = re.sub(r"\s+", " ", value).strip()
    if len(value) <= limit:
        return value
    return value[:limit].rstrip() + "..."


def _write_chat_message_delete_log(chat_id, session_id, msg_id, deleted_messages):
    try:
        if not UserManagementOperationLog.table_exists():
            UserManagementOperationLog.create_table(safe=True)
        user_message = next((m for m in deleted_messages if m.get("role") == "user"), {})
        assistant_message = next((m for m in deleted_messages if m.get("role") == "assistant"), {})
        target_label = _truncate_deleted_message_log_text(user_message.get("content"), 180)
        UserManagementOperationLog.create(
            id=get_uuid(),
            operator_id=current_user.id,
            operator_label=getattr(current_user, "nickname", None) or getattr(current_user, "email", None) or current_user.id,
            action="chat_message_delete",
            target_type="chat_message",
            target_id=msg_id,
            target_label=target_label or msg_id,
            tenant_id=getattr(current_user, "tenant_id", None),
            details={
                "chat_id": chat_id,
                "session_id": session_id,
                "message_id": msg_id,
                "user": _truncate_deleted_message_log_text(user_message.get("content")),
                "assistant": _truncate_deleted_message_log_text(assistant_message.get("content")),
            },
        )
    except Exception:
        logging.warning("Failed to write chat message delete log chat=%s session=%s msg=%s", chat_id, session_id, msg_id)
_DEFAULT_RERANK_MODELS = {"BAAI/bge-reranker-v2-m3", "maidalun1020/bce-reranker-base_v1"}
_READONLY_FIELDS = {"id", "tenant_id", "created_by", "create_time", "create_date", "update_time", "update_date"}
_PERSISTED_FIELDS = set(DialogService.model._meta.fields)
_CHAT_MEMO_MEMORY_TYPES = ["raw", "semantic", "episodic"]
_CONTEXT_SPAN_ERROR_PATTERNS = (
    "layer-slice token span exceeds context",
    "exceeds context",
    "context length",
    "maximum context",
)
_CONTEXT_RECOVERY_WAIT_SECONDS = int(os.environ.get("RAGFLOW_CONTEXT_RECOVERY_WAIT_SECONDS", "75"))
_LONG_MARKDOWN_MAX_SECTIONS = int(os.environ.get("RAGFLOW_LONG_MARKDOWN_MAX_SECTIONS", "8"))
_LONG_MARKDOWN_SECTION_TOKENS = int(os.environ.get("RAGFLOW_LONG_MARKDOWN_SECTION_TOKENS", "1600"))
_TTS_PCM_SAMPLE_RATE = int(os.environ.get("RAGFLOW_TTS_PCM_SAMPLE_RATE", "24000"))
_TTS_PCM_CHANNELS = int(os.environ.get("RAGFLOW_TTS_PCM_CHANNELS", "1"))
_TTS_PCM_SAMPLE_WIDTH = int(os.environ.get("RAGFLOW_TTS_PCM_SAMPLE_WIDTH", "2"))
# Structural breaks (markdown / code symbols, newlines) — replace with space.
# Do NOT include sentence-terminal punctuation here; those are speech cues for CosyVoice.
_TTS_STRUCTURAL_BREAK_PATTERN = re.compile(r"[/《》\n\r:;]+")
# Split AFTER sentence-terminal punctuation so the mark stays attached to the preceding chunk.
# CosyVoice uses trailing ，。？！；： to determine pause duration and intonation.
_TTS_SENTENCE_SPLIT_PATTERN = re.compile(r"(?<=[，。？！；：])\s*")
_TTS_PROCESS_BLOCK_PATTERN = re.compile(r"<(?:retrieving|think)>[\s\S]*?</(?:retrieving|think)>", re.I)
_TTS_PROCESS_TAG_PATTERN = re.compile(r"</?(?:retrieving|think)>", re.I)
_TTS_SYNC_JOB_PREFIX = "panython:tts:sync:"
_TTS_SYNC_JOB_TTL_SECONDS = int(os.environ.get("RAGFLOW_TTS_SYNC_JOB_TTL_SECONDS", "3600"))
_CHAT_MEMO_TOPIC_MAX_CHARS = int(os.environ.get("RAGFLOW_CHAT_MEMO_TOPIC_MAX_CHARS", "36"))
_CHAT_MEMO_TOPIC_SAMPLE_CHARS = int(os.environ.get("RAGFLOW_CHAT_MEMO_TOPIC_SAMPLE_CHARS", "8000"))
_CHAT_MEMO_CONTENT_SAMPLE_CHARS = int(os.environ.get("RAGFLOW_CHAT_MEMO_CONTENT_SAMPLE_CHARS", "12000"))
_CHAT_MEMO_BODY_MAX_CHARS = int(os.environ.get("RAGFLOW_CHAT_MEMO_BODY_MAX_CHARS", "3000"))
_CHAT_MEMO_ERROR_MARKERS = (
    "ERROR:",
    "CONNECTION_ERROR",
    "INVALID_REQUEST",
    "Traceback",
    "layer-slice token span exceeds context",
    "kv payload staging failed",
)
_SESSION_ORGANIZE_DUPLICATE_THRESHOLD = float(os.environ.get("RAGFLOW_SESSION_ORGANIZE_DUPLICATE_THRESHOLD", "0.7"))
_SESSION_ORGANIZE_MAX_SESSIONS = int(os.environ.get("RAGFLOW_SESSION_ORGANIZE_MAX_SESSIONS", "100"))
_SESSION_ORGANIZE_ERROR_MARKERS = tuple(
    marker.lower()
    for marker in (
        *_CHAT_MEMO_ERROR_MARKERS,
        "**ERROR**:",
        "Something went wrong",
        "Sorry, an error occurred while loading the page",
        "Error details",
        "TypeError:",
        "ReferenceError:",
        "Internal Server Error",
        "Bad Gateway",
        "Gateway Timeout",
        "Failed to fetch",
        "NetworkError",
        "request failed",
    )
)
_tts_route_log = logging.getLogger("panython.tts.route")


def _is_context_span_error(exc: Exception | str) -> bool:
    text = str(exc).lower()
    return any(pattern in text for pattern in _CONTEXT_SPAN_ERROR_PATTERNS)


def _strip_tts_process_text(text: str) -> str:
    text = _TTS_PROCESS_BLOCK_PATTERN.sub("", text or "")
    return _TTS_PROCESS_TAG_PATTERN.sub("", text).strip()


def _split_tts_text(text: str) -> list[str]:
    """Split TTS text into phrase chunks, keeping terminal punctuation with each chunk.

    CosyVoice uses trailing punctuation (，。？！) to determine pause duration and intonation.
    Stripping punctuation before synthesis causes flat, pause-free speech.
    """
    # Replace structural/non-speech marks with a space (they're not speech cues)
    text = _TTS_STRUCTURAL_BREAK_PATTERN.sub(" ", text or "")
    # Split AFTER sentence-terminal punctuation — the mark stays in the preceding chunk
    parts = _TTS_SENTENCE_SPLIT_PATTERN.split(text)
    return [p.strip() for p in parts if p.strip()]


def _build_wav_from_pcm(pcm: bytes) -> bytes:
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as wf:
        wf.setnchannels(_TTS_PCM_CHANNELS)
        wf.setsampwidth(_TTS_PCM_SAMPLE_WIDTH)
        wf.setframerate(_TTS_PCM_SAMPLE_RATE)
        wf.writeframes(pcm)
    return buffer.getvalue()


def _tts_sync_job_key(job_id: str) -> str:
    return f"{_TTS_SYNC_JOB_PREFIX}{job_id}"


def _store_tts_sync_job(job_id: str, payload: dict):
    REDIS_CONN.set(_tts_sync_job_key(job_id), json.dumps(payload, ensure_ascii=False), exp=_TTS_SYNC_JOB_TTL_SECONDS)


def _load_tts_sync_job(job_id: str) -> dict | None:
    value = REDIS_CONN.get(_tts_sync_job_key(job_id))
    if not value:
        return None
    if isinstance(value, bytes):
        value = value.decode("utf-8")
    return json.loads(value)


def _split_tts_sync_segments(text: str, engine_settings: dict) -> list[str]:
    max_zh = int(engine_settings.get("segment_max_chars_zh") or 45)
    max_en = int(engine_settings.get("segment_max_words_en") or 18)
    raw_parts = _split_tts_text(text)
    if not raw_parts:
        return []

    segments: list[str] = []
    current = ""

    def over_limit(candidate: str) -> bool:
        has_chinese = any("\u4e00" <= char <= "\u9fff" for char in candidate)
        if has_chinese:
            return len(candidate) > max_zh
        return len(candidate.split()) > max_en

    for part in raw_parts:
        # Chinese chunks: concatenate directly (punctuation already in chunk, no space needed)
        has_chinese = any("\u4e00" <= char <= "\u9fff" for char in current + part)
        joiner = "" if has_chinese else " "
        candidate = (current + joiner + part).strip() if current else part
        if current and over_limit(candidate):
            segments.append(current)
            current = part
        else:
            current = candidate
    if current:
        segments.append(current)
    return segments


def _synthesize_tts_audio(tenant_id: str, segments: list[str], tts_kwargs: dict) -> tuple[bytes, str]:
    t0 = datetime.now()
    voice = tts_kwargs.get("voice", "default")
    speed = float(tts_kwargs.get("speed", 1.0))
    n_chars = sum(len(s) for s in segments)
    n_segs = len(segments)

    default_tts_model_config = get_tenant_default_model_by_type(tenant_id, LLMType.TTS)
    model_name = "unknown"
    if default_tts_model_config:
        model_name = (
            getattr(default_tts_model_config, "llm_name", None)
            or getattr(default_tts_model_config, "model_name", None)
            or "unknown"
        )
    tts_mdl = LLMBundle(tenant_id, default_tts_model_config)
    mdl = getattr(tts_mdl, "mdl", None)

    if hasattr(mdl, "tts_pcm"):
        pcm_chunks = []
        for txt in segments:
            for chunk in mdl.tts_pcm(txt, **tts_kwargs):
                if isinstance(chunk, (bytes, bytearray)) and chunk:
                    pcm_chunks.append(bytes(chunk))
        if not pcm_chunks:
            raise RuntimeError("TTS returned no audio.")
        pcm_raw = b"".join(pcm_chunks)
        audio = _build_wav_from_pcm(pcm_raw)
        elapsed = (datetime.now() - t0).total_seconds()
        audio_dur_s = len(pcm_raw) / (_TTS_PCM_SAMPLE_RATE * _TTS_PCM_CHANNELS * _TTS_PCM_SAMPLE_WIDTH)
        _tts_route_log.info(
            "ROUTE=pcm→wav | model=%s | voice=%s | speed=%.2f | segments=%d | chars=%d"
            " | audio_bytes=%d | audio_dur=%.2fs | elapsed=%.2fs",
            model_name, voice, speed, n_segs, n_chars, len(audio), audio_dur_s, elapsed,
        )
        return audio, "audio/wav"

    audio_chunks = []
    for txt in segments:
        for chunk in tts_mdl.tts(txt, **tts_kwargs):
            if isinstance(chunk, (bytes, bytearray)) and chunk:
                audio_chunks.append(bytes(chunk))
    if not audio_chunks:
        raise RuntimeError("TTS returned no audio.")
    audio = b"".join(audio_chunks)
    elapsed = (datetime.now() - t0).total_seconds()
    _tts_route_log.info(
        "ROUTE=mp3 | model=%s | voice=%s | speed=%.2f | segments=%d | chars=%d"
        " | audio_bytes=%d | elapsed=%.2fs",
        model_name, voice, speed, n_segs, n_chars, len(audio), elapsed,
    )
    return audio, "audio/mpeg"


def _build_chat_response(chat):
    data = chat.to_dict() if hasattr(chat, "to_dict") else dict(chat)
    kb_ids, kb_names = _resolve_kb_names(data.get("kb_ids", []))
    data["dataset_ids"] = kb_ids
    data.pop("kb_ids", None)
    data["kb_names"] = kb_names
    return data


def _resolve_kb_names(kb_ids):
    ids, names = [], []
    for kb_id in kb_ids or []:
        ok, kb = KnowledgebaseService.get_by_id(kb_id)
        if not ok or kb.status != StatusEnum.VALID.value:
            continue
        ids.append(kb_id)
        names.append(kb.name)
    return ids, names


def _has_knowledge_placeholder(prompt_config):
    return "{knowledge}" in (prompt_config or {}).get("system", "")


def _chat_memo_name(chat_id: str, session_id: str) -> str:
    return f"chat-memo-{chat_id}-{session_id}"[:128]


def _strip_memo_process_text(content: str) -> str:
    content = re.sub(r"<retrieving>[\s\S]*?</retrieving>", "", content or "", flags=re.IGNORECASE)
    content = re.sub(r"<think>[\s\S]*?</think>", "", content, flags=re.IGNORECASE)
    return content.strip()


def _has_memo_error_content(content: str) -> bool:
    return any(marker.lower() in (content or "").lower() for marker in _CHAT_MEMO_ERROR_MARKERS)


def _format_conversation_transcript(messages: list[dict]) -> str:
    lines = []
    for message in messages or []:
        role = message.get("role")
        if role not in {"user", "assistant"}:
            continue
        content = message.get("content") or ""
        if not isinstance(content, str):
            content = json.dumps(content, ensure_ascii=False)
        content = _strip_memo_process_text(content)
        if _has_memo_error_content(content):
            continue
        if content:
            lines.append(f"{role}: {content}")
    return "\n\n".join(lines)


def _sanitize_chat_memo_topic(topic: str | None) -> str:
    topic = _strip_memo_process_text(str(topic or ""))
    topic = re.sub(
        r"^(我们注意到用户的问题是关于|我们注意到|我注意到|用户的问题是关于|这个问题是关于|The user asks about|This question is about)\s*[:：，,]*\s*",
        "",
        topic,
        flags=re.IGNORECASE,
    )
    topic = re.sub(r"^[#\-\s\"'“”‘’]+|[#\-\s\"'“”‘’。.!！]+$", "", topic).strip()
    topic = re.sub(r"\s+", " ", topic)
    if _has_memo_error_content(topic):
        return ""
    return topic[:_CHAT_MEMO_TOPIC_MAX_CHARS].strip()


def _fallback_chat_memo_topic(transcript: str) -> str:
    for line in transcript.splitlines():
        line = line.strip()
        if not line.lower().startswith("user:"):
            continue
        topic = _sanitize_chat_memo_topic(line.split(":", 1)[1])
        if topic:
            return topic
    compact = _sanitize_chat_memo_topic(transcript)
    return compact or "Chat memo"


def _memo_topic_sample(transcript: str) -> str:
    transcript = transcript.strip()
    if len(transcript) <= _CHAT_MEMO_TOPIC_SAMPLE_CHARS:
        return transcript
    half = _CHAT_MEMO_TOPIC_SAMPLE_CHARS // 2
    return f"{transcript[:half]}\n\n...\n\n{transcript[-half:]}"


def _memo_content_sample(transcript: str) -> str:
    transcript = transcript.strip()
    if len(transcript) <= _CHAT_MEMO_CONTENT_SAMPLE_CHARS:
        return transcript
    half = _CHAT_MEMO_CONTENT_SAMPLE_CHARS // 2
    return f"{transcript[:half]}\n\n...\n\n{transcript[-half:]}"


async def _resolve_chat_memo_topic(transcript: str, chat_config: dict, requested_topic: str | None) -> str:
    explicit_topic = _sanitize_chat_memo_topic(requested_topic)
    if explicit_topic:
        return explicit_topic

    fallback = _fallback_chat_memo_topic(transcript)
    try:
        chat_mdl = LLMBundle(current_user.id, chat_config)
        generated_topic = await chat_mdl.async_chat(
            "Generate a short noun-phrase title for a conversation memo. Return only the title, in the same language as the conversation. "
            "Do not write explanations such as 'the user asks about'. Do not use Markdown, quotes, prefixes, or punctuation. "
            "Keep it within 12 Chinese characters or 6 English words.",
            [{"role": "user", "content": _memo_topic_sample(transcript)}],
            {"temperature": 0.1, "max_tokens": 64},
        )
        return _sanitize_chat_memo_topic(generated_topic) or fallback
    except Exception as exc:  # noqa: BLE001 - memo title generation must not block saving
        logging.warning("Failed to generate chat memo topic; using fallback: %s", exc)
        return fallback


def _fallback_chat_memo_content(transcript: str, topic: str) -> str:
    compact = _memo_content_sample(_strip_memo_process_text(transcript))
    if len(compact) > _CHAT_MEMO_BODY_MAX_CHARS:
        compact = compact[:_CHAT_MEMO_BODY_MAX_CHARS].rstrip() + "\n..."
    return f"Topic: {topic or _fallback_chat_memo_topic(transcript)}\n\nSummary:\n{compact}"


async def _resolve_chat_memo_content(transcript: str, topic: str, chat_config: dict) -> str:
    fallback = _fallback_chat_memo_content(transcript, topic)
    try:
        chat_mdl = LLMBundle(current_user.id, chat_config)
        memo = await chat_mdl.async_chat(
            "You write compact conversation memos for future retrieval. "
            "Never include retrieval logs, thinking traces, debug text, stack traces, or error messages. "
            "Keep the same language as the conversation. Return concise Markdown with these sections: "
            "Confirmed facts, User goal, Key entities, Decisions or conclusions, Open questions. "
            "Keep it under 600 Chinese characters or 350 English words.",
            [
                {
                    "role": "user",
                    "content": f"Memo topic: {topic}\n\nConversation:\n{_memo_content_sample(transcript)}",
                }
            ],
            {"temperature": 0.1, "max_tokens": 700},
        )
        memo = _strip_memo_process_text(memo)
        if not memo or _has_memo_error_content(memo):
            return fallback
        memo = re.sub(r"\n{3,}", "\n\n", memo).strip()
        if len(memo) > _CHAT_MEMO_BODY_MAX_CHARS:
            memo = memo[:_CHAT_MEMO_BODY_MAX_CHARS].rstrip() + "\n..."
        return f"Topic: {topic or _fallback_chat_memo_topic(transcript)}\n\n{memo}"
    except Exception as exc:  # noqa: BLE001 - memo summarization must not block saving
        logging.warning("Failed to summarize chat memo; using compact transcript: %s", exc)
        return fallback


async def _cleanup_created_chat_memo(memory):
    try:
        if await thread_pool_exec(MessageService.has_index, memory.tenant_id, memory.id):
            await thread_pool_exec(MessageService.delete_index, memory.tenant_id, memory.id)
        await thread_pool_exec(MemoryService.delete_memory, memory.id)
    except Exception as exc:  # noqa: BLE001 - best-effort cleanup after failed memo creation
        logging.warning("Failed to clean up incomplete chat memo %s: %s", getattr(memory, "id", ""), exc)


def _validate_name(name, *, required=True):
    if name is None:
        if required:
            return None, "`name` is required."
        return None, None
    if not isinstance(name, str):
        return None, "Chat name must be a string."
    name = name.strip()
    if not name:
        return None, "`name` is required." if required else "`name` cannot be empty."
    if len(name.encode("utf-8")) > 255:
        return None, f"Chat name length is {len(name.encode('utf-8'))} which is larger than 255."
    return name, None


def _build_session_response(conv: dict) -> dict:
    conv = dict(conv)
    conv["chat_id"] = conv.pop("dialog_id", conv.get("chat_id"))
    conv["messages"] = conv.pop("message", conv.get("messages", []))
    return conv


def _session_organize_text(value) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    try:
        return json.dumps(value, ensure_ascii=False)
    except Exception:
        return str(value)


def _session_organize_visible_text(value) -> str:
    text = _strip_memo_process_text(_session_organize_text(value))
    text = re.sub(r"##\d+\$\$", "", text)
    text = re.sub(r"\bFig(?:ure)?\.?\s*\d+\b", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\bID\s*[:：]?\s*\d+\b", "", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _session_organize_similarity_key(value) -> str:
    text = _session_organize_visible_text(value).lower()
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", text, flags=re.UNICODE)[:20000]


def _session_organize_similarity(left: str, right: str) -> float:
    if not left or not right:
        return 0.0
    if left == right:
        return 1.0
    return SequenceMatcher(None, left, right, autojunk=False).ratio()


def _is_session_organize_error_turn(user_msg: dict, assistant_msg: dict) -> bool:
    assistant_content = _session_organize_text(assistant_msg.get("content"))
    visible_answer = _session_organize_visible_text(assistant_content)
    if not visible_answer:
        return True

    haystack = assistant_content.lower()
    return any(marker in haystack for marker in _SESSION_ORGANIZE_ERROR_MARKERS)


def _session_prologue_message(conv: dict, fallback: str = "") -> dict:
    messages = conv.get("message") or conv.get("messages") or []
    if messages and messages[0].get("role") == "assistant":
        prologue = deepcopy(messages[0])
        if not prologue.get("id"):
            prologue["id"] = get_uuid()
        return prologue
    return {"role": "assistant", "content": fallback or "", "id": get_uuid()}


def _extract_session_organize_turns(conv: dict) -> list[dict]:
    messages = conv.get("message") or conv.get("messages") or []
    references = conv.get("reference") or []
    turns = []
    reference_index = 0
    index = 0

    while index < len(messages):
        message = messages[index]
        role = message.get("role")

        if role == "assistant" and index == 0:
            index += 1
            continue

        if role != "user":
            index += 1
            continue

        if index + 1 >= len(messages) or messages[index + 1].get("role") != "assistant":
            index += 1
            continue

        reference = (
            deepcopy(references[reference_index])
            if reference_index < len(references)
            else {"chunks": [], "doc_aggs": []}
        )
        turns.append(
            {
                "user": deepcopy(message),
                "assistant": deepcopy(messages[index + 1]),
                "reference": reference,
                "session_id": conv.get("id"),
                "create_time": conv.get("create_time") or 0,
            }
        )
        reference_index += 1
        index += 2

    return turns


def _merge_session_organize_turns(convs: list[dict]) -> tuple[list[dict], list[dict], dict]:
    kept_turns: list[dict] = []
    kept_similarity_keys: list[str] = []
    stats = {
        "input_turns": 0,
        "kept_turns": 0,
        "dropped_error_turns": 0,
        "dropped_duplicate_turns": 0,
    }

    for conv in sorted(convs, key=lambda item: item.get("create_time") or 0):
        for turn in _extract_session_organize_turns(conv):
            stats["input_turns"] += 1
            if _is_session_organize_error_turn(turn["user"], turn["assistant"]):
                stats["dropped_error_turns"] += 1
                continue

            similarity_key = _session_organize_similarity_key(turn["assistant"].get("content"))
            duplicate_index = next(
                (
                    index
                    for index, existing_key in enumerate(kept_similarity_keys)
                    if _session_organize_similarity(similarity_key, existing_key)
                    >= _SESSION_ORGANIZE_DUPLICATE_THRESHOLD
                ),
                None,
            )

            if duplicate_index is not None:
                stats["dropped_duplicate_turns"] += 1
                if len(similarity_key) > len(kept_similarity_keys[duplicate_index]):
                    kept_turns[duplicate_index] = turn
                    kept_similarity_keys[duplicate_index] = similarity_key
                continue

            kept_turns.append(turn)
            kept_similarity_keys.append(similarity_key)

    merged_messages = []
    merged_references = []
    used_message_ids = set()

    for turn in kept_turns:
        pair_id = turn["user"].get("id") or turn["assistant"].get("id") or get_uuid()
        if pair_id in used_message_ids:
            pair_id = get_uuid()
        used_message_ids.add(pair_id)

        user_msg = deepcopy(turn["user"])
        assistant_msg = deepcopy(turn["assistant"])
        user_msg["id"] = pair_id
        assistant_msg["id"] = pair_id
        merged_messages.extend([user_msg, assistant_msg])
        merged_references.append(deepcopy(turn["reference"]))

    stats["kept_turns"] = len(kept_turns)
    return merged_messages, merged_references, stats


async def _ensure_owned_chat(chat_id):
    return await thread_pool_exec(
        DialogService.query,
        tenant_id=current_user.id, id=chat_id, status=StatusEnum.VALID.value
    )


def _build_default_completion_dialog():
    return SimpleNamespace(
        tenant_id=current_user.id,
        llm_id="",
        tenant_llm_id=None,
        llm_setting={},
        prompt_config=deepcopy(_DEFAULT_DIRECT_CHAT_PROMPT_CONFIG),
        kb_ids=[],
        top_n=6,
        top_k=1024,
        rerank_id="",
        similarity_threshold=0.1,
        vector_similarity_weight=0.3,
        meta_data_filter=None,
    )


async def _create_session_for_completion(chat_id, dialog, user_id):
    conv = {
        "id": get_uuid(),
        "dialog_id": chat_id,
        "name": "New session",
        "message": [{"role": "assistant", "content": dialog.prompt_config.get("prologue", "")}],
        "user_id": user_id,
        "reference": [],
    }
    await thread_pool_exec(ConversationService.save, **conv)
    ok, conv_obj = await thread_pool_exec(ConversationService.get_by_id, conv["id"])
    if not ok:
        raise LookupError("Fail to create a session!")
    return conv_obj


def _get_bool_request_flag(req, *names, default=False):
    for name in names:
        if name not in req:
            continue
        value = req.pop(name)
        if isinstance(value, str):
            return value.strip().lower() in {"1", "true", "yes", "on"}
        return bool(value)
    return default


def _normalize_completion_messages(req):
    messages = req.get("messages")
    if messages is None:
        question = req.get("question")
        if question is None:
            return None, get_data_error_result(
                code=RetCode.ARGUMENT_ERROR,
                message="required argument are missing: messages",
            )
        messages = [{"role": "user", "content": question}]
        if req.get("files"):
            messages[-1]["files"] = req["files"]

    if not isinstance(messages, list) or not messages:
        return None, get_data_error_result(
            code=RetCode.ARGUMENT_ERROR,
            message="`messages` must be a non-empty list.",
        )

    for message in messages:
        if not isinstance(message, dict):
            return None, get_data_error_result(
                code=RetCode.ARGUMENT_ERROR,
                message="Every item in `messages` must be an object.",
            )
        if "role" not in message or "content" not in message:
            return None, get_data_error_result(
                code=RetCode.ARGUMENT_ERROR,
                message="Every item in `messages` must include `role` and `content`.",
            )

    msg = []
    for m in messages:
        if m["role"] == "system":
            continue
        if m["role"] == "assistant" and not msg:
            continue
        msg.append(m)

    if not msg:
        return None, get_data_error_result(
            code=RetCode.ARGUMENT_ERROR,
            message="`messages` must contain a user message.",
        )
    if msg[-1]["role"] != "user":
        return None, get_data_error_result(
            code=RetCode.ARGUMENT_ERROR,
            message="The last message must be from user.",
        )
    if not msg[-1].get("id"):
        msg[-1]["id"] = get_uuid()

    # till now, message and msg are sharing the same copy
    return (messages, msg), None


async def _validate_llm_id(llm_id, tenant_id, llm_setting=None):
    if not llm_id:
        return None

    llm_name, llm_factory = TenantLLMService.split_model_name_and_factory(llm_id)
    model_type = (llm_setting or {}).get("model_type")
    if model_type not in {"chat", "image2text"}:
        model_type = "chat"

    if not await thread_pool_exec(
        TenantLLMService.query,
        tenant_id=tenant_id,
        llm_name=llm_name,
        llm_factory=llm_factory,
        model_type=model_type,
    ):
        return f"`llm_id` {llm_id} doesn't exist"
    return None


async def _validate_rerank_id(rerank_id, tenant_id):
    if not rerank_id:
        return None
    llm_name, llm_factory = TenantLLMService.split_model_name_and_factory(rerank_id)
    if llm_name in _DEFAULT_RERANK_MODELS:
        return None
    if await thread_pool_exec(
        TenantLLMService.query,
        tenant_id=tenant_id,
        llm_name=llm_name,
        llm_factory=llm_factory,
        model_type="rerank",
    ):
        return None
    return f"`rerank_id` {rerank_id} doesn't exist"


# def _validate_prompt_config(prompt_config):
#     for parameter in prompt_config.get("parameters", []):
#         if parameter.get("optional"):
#             continue
#         if prompt_config.get("system", "").find("{%s}" % parameter["key"]) < 0:
#             return f"Parameter '{parameter['key']}' is not used"
#     return None


async def _validate_dataset_ids(dataset_ids, tenant_id):
    if dataset_ids is None:
        return []
    if not isinstance(dataset_ids, list):
        return "`dataset_ids` should be a list."

    normalized_ids = [dataset_id for dataset_id in dataset_ids if dataset_id]
    kbs = []
    for dataset_id in normalized_ids:
        if not await thread_pool_exec(KnowledgebaseService.accessible, kb_id=dataset_id, user_id=tenant_id):
            return f"You don't own the dataset {dataset_id}"
        matches = await thread_pool_exec(KnowledgebaseService.query, id=dataset_id)
        if not matches:
            return f"You don't own the dataset {dataset_id}"
        kb = matches[0]
        if kb.chunk_num == 0:
            return f"The dataset {dataset_id} doesn't own parsed file"
        kbs.append(kb)

    embd_ids = [TenantLLMService.split_model_name_and_factory(kb.embd_id)[0] for kb in kbs]
    if len(set(embd_ids)) > 1:
        return f'Datasets use different embedding models: {[kb.embd_id for kb in kbs]}'

    return normalized_ids


def _apply_prompt_defaults(req):
    prompt_config = req.setdefault("prompt_config", {})
    for key, value in _DEFAULT_PROMPT_CONFIG.items():
        temp = prompt_config.get(key)
        if (key == "system" and not temp) or key not in prompt_config:
            prompt_config[key] = deepcopy(value)

    if req.get("kb_ids") and not prompt_config.get("parameters") and "{knowledge}" in prompt_config.get("system", ""):
        prompt_config["parameters"] = [{"key": "knowledge", "optional": False}]


@manager.route("/chats", methods=["POST"])  # noqa: F821
@login_required
async def create():
    try:
        req = await get_request_json()
        ok, tenant = TenantService.get_by_id(current_user.id)
        if not ok:
            return get_data_error_result(message="Tenant not found!")

        # Validate tenant_id should not be provided
        if req.get("tenant_id"):
            return get_data_error_result(message="`tenant_id` must not be provided.")

        # Validate name
        name, err = _validate_name(req.get("name"), required=True)
        if err:
            return get_data_error_result(message=err)
        req["name"] = name

        if "dataset_ids" in req:
            kb_ids = await _validate_dataset_ids(req.get("dataset_ids"), current_user.id)
            if isinstance(kb_ids, str):
                return get_data_error_result(message=kb_ids)
            req["kb_ids"] = kb_ids
            req.pop("dataset_ids", None)

        if "llm_id" in req:
            err = await _validate_llm_id(req.get("llm_id"), current_user.id, req.get("llm_setting"))
            if err:
                return get_data_error_result(message=err)

        if "rerank_id" in req:
            err = await _validate_rerank_id(req.get("rerank_id"), current_user.id)
            if err:
                return get_data_error_result(message=err)

        if "prompt_config" in req:
            if not isinstance(req["prompt_config"], dict):
                return get_data_error_result(message="`prompt_config` should be an object.")
            # err = _validate_prompt_config(req["prompt_config"])
            # if err:
            #     return get_data_error_result(message=err)

        req.setdefault("kb_ids", [])
        req.setdefault("llm_id", tenant.llm_id)
        if req["llm_id"] is None:
            req["llm_id"] = tenant.llm_id
        req.setdefault("llm_setting", {})
        req.setdefault("description", "A helpful Assistant")
        req.setdefault("top_n", 6)
        req.setdefault("top_k", 1024)
        req.setdefault("rerank_id", "")
        req.setdefault("similarity_threshold", 0.1)
        req.setdefault("vector_similarity_weight", 0.3)
        req.setdefault("icon", "")
        req.setdefault("memory_mode", "kb_first")
        _apply_prompt_defaults(req)
        # err = _validate_prompt_config(req["prompt_config"])
        # if err:
        #     return get_data_error_result(message=err)

        req = ensure_tenant_model_id_for_params(current_user.id, req)
        req = {field: value for field, value in req.items() if field in _PERSISTED_FIELDS}
        for field in _READONLY_FIELDS:
            req.pop(field, None)

        if DialogService.query(
            name=req["name"],
            tenant_id=current_user.id,
            status=StatusEnum.VALID.value,
        ):
            return get_data_error_result(message="Duplicated chat name in creating chat.")

        req["id"] = get_uuid()
        req["tenant_id"] = current_user.id
        if not DialogService.save(**req):
            return get_data_error_result(message="Failed to create chat.")

        ok, chat = DialogService.get_by_id(req["id"])
        if not ok:
            return get_data_error_result(message="Failed to retrieve created chat.")
        return get_json_result(data=_build_chat_response(chat))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats", methods=["GET"])  # noqa: F821
@login_required
async def list_chats():
    chat_id = request.args.get("id")
    name = request.args.get("name")
    keywords = request.args.get("keywords", "")
    orderby = request.args.get("orderby", "create_time")
    desc = request.args.get("desc", "true").lower() != "false"
    owner_ids = request.args.getlist("owner_ids")
    exact_filters = {"id": chat_id, "name": name}
    if chat_id or name:
        keywords = ""

    try:
        page_number = int(request.args.get("page", 0))
        items_per_page = int(request.args.get("page_size", 0))

        tenants = TenantService.get_joined_tenants_by_user_id(current_user.id)
        authorized_owner_ids = {member["tenant_id"] for member in tenants}
        authorized_owner_ids.add(current_user.id)

        if owner_ids:
            requested_owner_ids = set(owner_ids)
            unauthorized_owner_ids = requested_owner_ids - authorized_owner_ids
            if unauthorized_owner_ids:
                logging.warning(
                    "Rejected list_chats request: user=%s attempted unauthorized owner_ids=%s",
                    current_user.id,
                    sorted(unauthorized_owner_ids),
                )
                return get_json_result(
                    data=False,
                    message="Only authorized owner_ids can be queried.",
                    code=RetCode.OPERATING_ERROR,
                )
            effective_owner_ids = list(requested_owner_ids)
        else:
            effective_owner_ids = list(authorized_owner_ids)

        chats, total = await thread_pool_exec(
            DialogService.get_by_tenant_ids,
            effective_owner_ids, current_user.id, page_number, items_per_page, orderby, desc, keywords, **exact_filters,
        )

        return get_json_result(
            data={"chats": [_build_chat_response(chat) for chat in chats], "total": total}
        )
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>", methods=["GET"])  # noqa: F821
@login_required
async def get_chat(chat_id):
    try:
        tenants = await thread_pool_exec(UserTenantService.query, user_id=current_user.id)
        for tenant in tenants:
            if await thread_pool_exec(
                DialogService.query,
                tenant_id=tenant.tenant_id, id=chat_id, status=StatusEnum.VALID.value,
            ):
                break
        else:
            return get_json_result(
                data=False,
                message="No authorization.",
                code=RetCode.AUTHENTICATION_ERROR,
            )

        ok, chat = await thread_pool_exec(DialogService.get_by_id, chat_id)
        if not ok:
            return get_data_error_result(message="Chat not found!")
        return get_json_result(data=_build_chat_response(chat))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>", methods=["PUT"])  # noqa: F821
@login_required
async def update_chat(chat_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(
            data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR
        )

    try:
        req = await get_request_json()
        ok, tenant = TenantService.get_by_id(current_user.id)
        if not ok:
            return get_data_error_result(message="Tenant not found!")

        ok, current_chat = DialogService.get_by_id(chat_id)
        if not ok:
            return get_data_error_result(message="Chat not found!")
        current_chat = current_chat.to_dict()

        if req.get("tenant_id"):
            return get_data_error_result(message="`tenant_id` must not be provided.")

        if "name" in req:
            name, err = _validate_name(req.get("name"), required=True)
            if err:
                return get_data_error_result(message=err)
            req["name"] = name

        if "dataset_ids" in req:
            kb_ids = await _validate_dataset_ids(req.get("dataset_ids"), current_user.id)
            if isinstance(kb_ids, str):
                return get_data_error_result(message=kb_ids)
            req["kb_ids"] = kb_ids
            req.pop("dataset_ids", None)

        if "llm_id" in req:
            err = await _validate_llm_id(req.get("llm_id"), current_user.id, req.get("llm_setting"))
            if err:
                return get_data_error_result(message=err)

        if "rerank_id" in req:
            err = await _validate_rerank_id(req.get("rerank_id"), current_user.id)
            if err:
                return get_data_error_result(message=err)

        if "prompt_config" in req:
            if not isinstance(req["prompt_config"], dict):
                return get_data_error_result(message="`prompt_config` should be an object.")
            # err = _validate_prompt_config(req["prompt_config"])
            # if err:
            #     return get_data_error_result(message=err)

        # prompt_config = req.get("prompt_config", {})
        # if not prompt_config:
        #     prompt_config = current_chat.get("prompt_config", {})
        # kb_ids = req.get("kb_ids", current_chat.get("kb_ids", []))
        # if not kb_ids and not prompt_config.get("tavily_api_key") and _has_knowledge_placeholder(prompt_config):
        #     return get_data_error_result(message="Please remove `{knowledge}` in system prompt since no dataset / Tavily used here.")

        req = ensure_tenant_model_id_for_params(current_user.id, req)
        req = {field: value for field, value in req.items() if field in _PERSISTED_FIELDS}
        for field in _READONLY_FIELDS:
            req.pop(field, None)

        if (
            "name" in req
            and req["name"].lower() != current_chat["name"].lower()
            and DialogService.query(
                name=req["name"],
                tenant_id=current_user.id,
                status=StatusEnum.VALID.value,
            )
        ):
            return get_data_error_result(message="Duplicated chat name.")

        if not DialogService.update_by_id(chat_id, req):
            return get_data_error_result(message="Chat not found!")

        ok, chat = DialogService.get_by_id(chat_id)
        if not ok:
            return get_data_error_result(message="Failed to retrieve updated chat.")
        return get_json_result(data=_build_chat_response(chat))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>", methods=["PATCH"])  # noqa: F821
@login_required
async def patch_chat(chat_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(
            data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR
        )

    try:
        req = await get_request_json()
        ok, tenant = TenantService.get_by_id(current_user.id)
        if not ok:
            return get_data_error_result(message="Tenant not found!")

        ok, current_chat = DialogService.get_by_id(chat_id)
        if not ok:
            return get_data_error_result(message="Chat not found!")
        current_chat = current_chat.to_dict()

        if "name" in req:
            name, err = _validate_name(req.get("name"), required=False)
            if err:
                return get_data_error_result(message=err)
            if name is not None:
                req["name"] = name

        if "dataset_ids" in req:
            kb_ids = await _validate_dataset_ids(req.get("dataset_ids"), current_user.id)
            if isinstance(kb_ids, str):
                return get_data_error_result(message=kb_ids)
            req["kb_ids"] = kb_ids
            req.pop("dataset_ids", None)

        if "llm_id" in req:
            err = await _validate_llm_id(req.get("llm_id"), current_user.id, req.get("llm_setting"))
            if err:
                return get_data_error_result(message=err)

        if "rerank_id" in req:
            err = await _validate_rerank_id(req.get("rerank_id"), current_user.id)
            if err:
                return get_data_error_result(message=err)

        if "prompt_config" in req:
            if not isinstance(req["prompt_config"], dict):
                return get_data_error_result(message="`prompt_config` should be an object.")
            prompt_config = deepcopy(current_chat.get("prompt_config", {}))
            prompt_config.update(req["prompt_config"])
            req["prompt_config"] = prompt_config
            # err = _validate_prompt_config(prompt_config)
            # if err:
            #     return get_data_error_result(message=err)

        if "llm_setting" in req:
            llm_setting = deepcopy(current_chat.get("llm_setting", {}))
            llm_setting.update(req["llm_setting"])
            req["llm_setting"] = llm_setting

        # if "prompt_config" in req or "kb_ids" in req:
        #     prompt_config = req.get("prompt_config", current_chat.get("prompt_config", {}))
        #     kb_ids = req.get("kb_ids", current_chat.get("kb_ids", []))
        #     if not kb_ids and not prompt_config.get("tavily_api_key") and _has_knowledge_placeholder(prompt_config):
        #         return get_data_error_result(message="Please remove `{knowledge}` in system prompt since no dataset / Tavily used here.")

        req = ensure_tenant_model_id_for_params(current_user.id, req)
        req = {field: value for field, value in req.items() if field in _PERSISTED_FIELDS}
        for field in _READONLY_FIELDS:
            req.pop(field, None)

        if (
            "name" in req
            and req["name"].lower() != current_chat["name"].lower()
            and DialogService.query(
                name=req["name"],
                tenant_id=current_user.id,
                status=StatusEnum.VALID.value,
            )
        ):
            return get_data_error_result(message="Duplicated chat name.")

        if not DialogService.update_by_id(chat_id, req):
            return get_data_error_result(message="Failed to update chat.")

        ok, chat = DialogService.get_by_id(chat_id)
        if not ok:
            return get_data_error_result(message="Failed to retrieve updated chat.")
        return get_json_result(data=_build_chat_response(chat))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>", methods=["DELETE"])  # noqa: F821
@login_required
async def delete_chat(chat_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(
            data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR
        )

    try:
        if not DialogService.update_by_id(chat_id, {"status": StatusEnum.INVALID.value}):
            return get_data_error_result(message=f"Failed to delete chat {chat_id}")
        return get_json_result(data=True)
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats", methods=["DELETE"])  # noqa: F821
@login_required
async def bulk_delete_chats():
    req = await get_request_json()
    if not req:
        return get_json_result(data={})

    ids = req.get("ids")
    if not ids:
        if req.get("delete_all") is True:
            ids = [
                chat.id
                for chat in DialogService.query(
                    tenant_id=current_user.id, status=StatusEnum.VALID.value
                )
            ]
            if not ids:
                return get_json_result(data={})
        else:
            # keep backward compatibility, DELETE with chat_id in request body
            chat_id = req.get("chat_id")
            if chat_id:
                try:
                    if not DialogService.update_by_id(chat_id, {"status": StatusEnum.INVALID.value}):
                        return get_data_error_result(message=f"Failed to delete chat {chat_id}")
                    return get_json_result(data=True)
                except Exception as ex:
                    return server_error_response(ex)
            return get_json_result(data={})

    errors = []
    success_count = 0
    unique_ids, duplicate_messages = check_duplicate_ids(ids, "chat")

    for chat_id in unique_ids:
        if not await _ensure_owned_chat(chat_id):
            errors.append(f"Chat({chat_id}) not found.")
            continue
        success_count += DialogService.update_by_id(chat_id, {"status": StatusEnum.INVALID.value})

    all_errors = errors + duplicate_messages
    if all_errors:
        if success_count > 0:
            return get_json_result(
                data={"success_count": success_count, "errors": all_errors},
                message=f"Partially deleted {success_count} chats with {len(all_errors)} errors",
            )
        return get_data_error_result(message="; ".join(all_errors))

    return get_json_result(data={"success_count": success_count})


@manager.route("/chats/<chat_id>/sessions", methods=["POST"])  # noqa: F821
@login_required
async def create_session(chat_id):
    """Create a new conversation session for the given chat, owned by the authenticated user."""
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        req = await get_request_json()
        ok, dia = DialogService.get_by_id(chat_id)
        if not ok:
            return get_data_error_result(message="Chat not found!")
        name = req.get("name", "New session")
        if not isinstance(name, str) or not name.strip():
            return get_data_error_result(message="`name` can not be empty.")
        name = name.strip()[:255]
        conv = {
            "id": get_uuid(),
            "dialog_id": chat_id,
            "name": name,
            "message": [{"role": "assistant", "content": dia.prompt_config.get("prologue", "")}],
            "user_id": current_user.id,
            "reference": [],
        }
        ConversationService.save(**conv)
        ok, conv_obj = ConversationService.get_by_id(conv["id"])
        if not ok:
            return get_data_error_result(message="Fail to create a session!")
        return get_json_result(data=_build_session_response(conv_obj.to_dict()))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions", methods=["GET"])  # noqa: F821
@login_required
async def list_sessions(chat_id):
    try:
        if not await _ensure_owned_chat(chat_id):
            return get_json_result(
                data=False,
                message="No authorization.",
                code=RetCode.AUTHENTICATION_ERROR,
            )
        page_number = int(request.args.get("page", 1))
        items_per_page = int(request.args.get("page_size", 30))
        orderby = request.args.get("orderby", "create_time")
        desc = request.args.get("desc", "true").lower() != "false"
        session_id = request.args.get("id")
        name = request.args.get("name")
        user_id = request.args.get("user_id")
        convs = ConversationService.get_list(
            chat_id, page_number, items_per_page, orderby, desc, session_id, name, user_id
        )
        if items_per_page == 0:
            convs = []
        return get_json_result(data=[_build_session_response(c) for c in convs])
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions/<session_id>", methods=["GET"])  # noqa: F821
@login_required
async def get_session(chat_id, session_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        ok, conv = await thread_pool_exec(ConversationService.get_by_id, session_id)
        if not ok:
            return get_data_error_result(message="Session not found!")
        if conv.dialog_id != chat_id:
            return get_data_error_result(message="Session does not belong to this chat!")
        dialog = await _ensure_owned_chat(chat_id)
        avatar = dialog[0].icon if dialog else ""
        for ref in conv.reference:
            if isinstance(ref, list):
                continue
            ref["chunks"] = chunks_format(ref)
        result = _build_session_response(conv.to_dict())
        result["avatar"] = avatar
        return get_json_result(data=result)
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions/<session_id>", methods=["PATCH"])  # noqa: F821
@login_required
async def update_session(chat_id, session_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        req = await get_request_json()
        if not ConversationService.query(id=session_id, dialog_id=chat_id):
            return get_data_error_result(message="Session not found!")
        if "message" in req or "messages" in req:
            return get_data_error_result(message="`messages` cannot be changed.")
        if "reference" in req:
            return get_data_error_result(message="`reference` cannot be changed.")
        name = req.get("name")
        if name is not None:
            if not isinstance(name, str) or not name.strip():
                return get_data_error_result(message="`name` can not be empty.")
            req["name"] = name.strip()[:255]
        update_fields = {k: v for k, v in req.items() if k not in {"id", "dialog_id", "chat_id", "user_id"}}
        if not ConversationService.update_by_id(session_id, update_fields):
            return get_data_error_result(message="Session not found!")
        ok, conv = ConversationService.get_by_id(session_id)
        if not ok:
            return get_data_error_result(message="Fail to update a session!")
        return get_json_result(data=_build_session_response(conv.to_dict()))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions", methods=["DELETE"])  # noqa: F821
@login_required
async def delete_sessions(chat_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        req = await get_request_json()
        if not req:
            return get_json_result(data={})

        session_ids = req.get("ids")
        if not session_ids:
            if req.get("delete_all") is True:
                session_ids = [conv.id for conv in ConversationService.query(dialog_id=chat_id)]
                if not session_ids:
                    return get_json_result(data={})
            else:
                return get_json_result(data={})
        unique_ids, duplicate_messages = check_duplicate_ids(session_ids, "session")
        errors = []
        success_count = 0
        for sid in unique_ids:
            if not ConversationService.query(id=sid, dialog_id=chat_id):
                errors.append(f"The chat doesn't own the session {sid}")
                continue
            ok, conv = ConversationService.get_by_id(sid)
            if ok:
                for msg in conv.message or []:
                    for file in msg.get("files") or []:
                        file_id = file.get("id")
                        if not file_id:
                            continue
                        try:
                            settings.STORAGE_IMPL.rm(f"{current_user.id}-downloads", file_id)
                        except Exception:
                            logging.warning("Failed to delete chat upload blob %s/%s", current_user.id, file_id)
            ConversationService.delete_by_id(sid)
            success_count += 1
        all_errors = errors + duplicate_messages
        if all_errors:
            if success_count > 0:
                return get_json_result(
                    data={"success_count": success_count, "errors": all_errors},
                    message=f"Partially deleted {success_count} sessions with {len(all_errors)} errors",
                )
            return get_data_error_result(message="; ".join(all_errors))
        return get_json_result(data=True)
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions/organize", methods=["POST"])  # noqa: F821
@login_required
async def organize_sessions(chat_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        req = await get_request_json()
        session_ids = req.get("ids") or req.get("session_ids") or []
        if not isinstance(session_ids, list) or not session_ids:
            return get_data_error_result(message="`ids` must be a non-empty list.")

        unique_ids, duplicate_messages = check_duplicate_ids(session_ids, "session")
        if len(unique_ids) > _SESSION_ORGANIZE_MAX_SESSIONS:
            return get_data_error_result(
                message=f"Too many sessions selected. Maximum is {_SESSION_ORGANIZE_MAX_SESSIONS}."
            )
        if duplicate_messages:
            return get_data_error_result(message="; ".join(duplicate_messages))

        convs = []
        errors = []
        for session_id in unique_ids:
            ok, conv = ConversationService.get_by_id(session_id)
            if not ok or conv.dialog_id != chat_id:
                errors.append(f"The chat doesn't own the session {session_id}")
                continue
            convs.append(conv.to_dict())
        if errors:
            return get_data_error_result(message="; ".join(errors))

        target_session_id = req.get("target_session_id") or req.get("target_id")
        if target_session_id not in unique_ids:
            target_session_id = unique_ids[0]

        target_conv = next((conv for conv in convs if conv.get("id") == target_session_id), None)
        if not target_conv:
            return get_data_error_result(message="Target session not found.")

        ok, dia = DialogService.get_by_id(chat_id)
        fallback_prologue = dia.prompt_config.get("prologue", "") if ok else ""
        prologue = _session_prologue_message(target_conv, fallback_prologue)
        merged_messages, merged_references, stats = _merge_session_organize_turns(convs)

        target_update = deepcopy(target_conv)
        target_update["message"] = [prologue, *merged_messages]
        target_update["reference"] = merged_references
        ConversationService.update_by_id(target_session_id, target_update)

        removed_session_ids = []
        for session_id in unique_ids:
            if session_id == target_session_id:
                continue
            ConversationService.delete_by_id(session_id)
            removed_session_ids.append(session_id)

        ok, updated_conv = ConversationService.get_by_id(target_session_id)
        data = {
            **stats,
            "target_session_id": target_session_id,
            "removed_session_ids": removed_session_ids,
            "removed_sessions": len(removed_session_ids),
        }
        if ok:
            data["session"] = _build_session_response(updated_conv.to_dict())

        return get_json_result(data=data)
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions/<session_id>/messages/<msg_id>", methods=["DELETE"])  # noqa: F821
@login_required
async def delete_session_message(chat_id, session_id, msg_id):
    if not await _ensure_owned_chat(chat_id):
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        ok, conv = ConversationService.get_by_id(session_id)
        if not ok or conv.dialog_id != chat_id:
            return get_data_error_result(message="Session not found!")
        conv = conv.to_dict()
        deleted_messages = []
        for i, msg in enumerate(conv["message"]):
            if msg_id != msg.get("id", ""):
                continue
            if msg.get("role") != "user":
                return get_data_error_result(message="Only user question messages can be deleted.")
            if i + 1 >= len(conv["message"]) or conv["message"][i + 1].get("id") != msg_id:
                return get_data_error_result(message="Message pair not found.")
            deleted_messages = [conv["message"][i], conv["message"][i + 1]]
            conv["message"].pop(i)
            conv["message"].pop(i)
            reference_index = max(0, i // 2 - 1)
            if 0 <= reference_index < len(conv.get("reference") or []):
                conv["reference"].pop(reference_index)
            break
        if not deleted_messages:
            return get_data_error_result(message="Message not found.")
        ConversationService.update_by_id(conv["id"], conv)
        _write_chat_message_delete_log(chat_id, session_id, msg_id, deleted_messages)
        return get_json_result(data=_build_session_response(conv))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chats/<chat_id>/sessions/<session_id>/messages/<msg_id>/feedback", methods=["PUT"])  # noqa: F821
@login_required
async def update_message_feedback(chat_id, session_id, msg_id):
    owned = await _ensure_owned_chat(chat_id)
    if not owned:
        return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
    try:
        req = await get_request_json()
        ok, conv = ConversationService.get_by_id(session_id)
        if not ok or conv.dialog_id != chat_id:
            return get_data_error_result(message="Session not found!")
        thumb_raw = req.get("thumbup")
        if not isinstance(thumb_raw, bool):
            return get_data_error_result(message="thumbup must be a boolean")
        feedback = req.get("feedback", "")
        conv_dict = conv.to_dict()
        message_index = None
        apply_chunk_feedback = False
        prior_thumb = None
        for i, msg in enumerate(conv_dict["message"]):
            if msg_id == msg.get("id", "") and msg.get("role", "") == "assistant":
                prior_thumb = msg.get("thumbup")
                if thumb_raw is True:
                    msg["thumbup"] = True
                    msg.pop("feedback", None)
                    apply_chunk_feedback = prior_thumb is not True
                else:
                    msg["thumbup"] = False
                    if feedback:
                        msg["feedback"] = feedback
                    apply_chunk_feedback = prior_thumb is not False
                message_index = i
                break

        if message_index is not None and apply_chunk_feedback:
            try:
                ref_index = (message_index - 1) // 2
                if 0 <= ref_index < len(conv_dict.get("reference", [])):
                    reference = conv_dict["reference"][ref_index]
                    if reference:
                        if isinstance(prior_thumb, bool) and prior_thumb != thumb_raw:
                            await thread_pool_exec(
                                ChunkFeedbackService.apply_feedback,
                                tenant_id=current_user.id,
                                reference=reference,
                                is_positive=not prior_thumb,
                            )
                        feedback_result = await thread_pool_exec(
                            ChunkFeedbackService.apply_feedback,
                            tenant_id=current_user.id,
                            reference=reference,
                            is_positive=thumb_raw is True,
                        )
                        logging.debug(
                            "Chunk feedback applied: %s succeeded, %s failed",
                            feedback_result["success_count"],
                            feedback_result["fail_count"],
                        )
            except Exception as e:
                logging.warning("Failed to apply chunk feedback: %s", e)

        await thread_pool_exec(ConversationService.update_by_id, conv_dict["id"], conv_dict)
        return get_json_result(data=_build_session_response(conv_dict))
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chat/audio/speech", methods=["POST"])  # noqa: F821
@login_required
async def tts():
    req = await get_request_json()
    engine_settings = PanythonTTSSettingsService.get_settings()
    if not engine_settings.get("tts_enabled"):
        return get_data_error_result(message="TTS engine is disabled.")
    text = _strip_tts_process_text(str(req.get("text") or ""))
    segments = _split_tts_text(text)
    if not segments:
        return get_data_error_result(message="No text to synthesize.")
    tts_config = req.get("tts_config") if isinstance(req.get("tts_config"), dict) else req
    tts_kwargs = build_tts_kwargs(tts_config, text, engine_settings)
    tenant_id = current_user.id
    _tts_route_log.info(
        "REQUEST | engine=%s | voice_kwargs=%s | segments=%d | chars=%d",
        engine_settings.get("engine"), tts_kwargs, len(segments), sum(len(s) for s in segments),
    )

    def synthesize_audio():
        try:
            return _synthesize_tts_audio(tenant_id, segments, tts_kwargs)
        except Exception as e:
            logging.exception("TTS synthesis failed: %s", e)
            raise

    try:
        audio, mimetype = await thread_pool_exec(synthesize_audio)
    except Exception as e:
        return get_data_error_result(message=str(e))

    resp = Response(audio, mimetype=mimetype)
    resp.headers.add_header("Cache-Control", "no-cache")
    resp.headers.add_header("X-Accel-Buffering", "no")
    return resp


async def _run_tts_sync_job(job_id: str, tenant_id: str, segments: list[str], tts_config: dict, engine_settings: dict):
    try:
        job = _load_tts_sync_job(job_id)
        if not job:
            return
        job["status"] = "running"
        _store_tts_sync_job(job_id, job)

        for index, segment in enumerate(segments):
            try:
                kwargs = build_tts_kwargs(tts_config, segment, engine_settings)
                audio, mimetype = await thread_pool_exec(_synthesize_tts_audio, tenant_id, [segment], kwargs)
                job = _load_tts_sync_job(job_id) or job
                item = job["segments"][index]
                item["status"] = "ready"
                item["mimetype"] = mimetype
                item["audio_hex"] = binascii.hexlify(audio).decode("utf-8")
                _store_tts_sync_job(job_id, job)
            except Exception as exc:  # noqa: BLE001 - keep other segments available
                logging.exception("TTS sync segment failed job=%s index=%s: %s", job_id, index, exc)
                job = _load_tts_sync_job(job_id) or job
                item = job["segments"][index]
                item["status"] = "error"
                item["message"] = str(exc)
                _store_tts_sync_job(job_id, job)

        job = _load_tts_sync_job(job_id) or job
        job["status"] = "complete" if all(seg.get("status") == "ready" for seg in job.get("segments", [])) else "partial"
        _store_tts_sync_job(job_id, job)
    except Exception as exc:  # noqa: BLE001
        logging.exception("TTS sync job failed job=%s: %s", job_id, exc)
        job = _load_tts_sync_job(job_id) or {"job_id": job_id, "segments": []}
        job["status"] = "error"
        job["message"] = str(exc)
        _store_tts_sync_job(job_id, job)


@manager.route("/chat/audio/speech/sync", methods=["POST"])  # noqa: F821
@login_required
async def create_tts_sync_job():
    req = await get_request_json()
    engine_settings = PanythonTTSSettingsService.get_settings()
    if not engine_settings.get("tts_enabled") or not engine_settings.get("supports_sync_caption"):
        return get_data_error_result(message="TTS synchronized caption is disabled.")

    text = _strip_tts_process_text(str(req.get("text") or ""))
    segments = _split_tts_sync_segments(text, engine_settings)
    if not segments:
        return get_data_error_result(message="No text to synthesize.")

    tts_config = req.get("tts_config") if isinstance(req.get("tts_config"), dict) else req
    job_id = get_uuid()
    payload = {
        "job_id": job_id,
        "status": "pending",
        "segments": [
            {"index": index, "text": segment, "status": "pending"}
            for index, segment in enumerate(segments)
        ],
        "poll_interval_ms": 800,
    }
    _store_tts_sync_job(job_id, payload)
    asyncio.create_task(_run_tts_sync_job(job_id, current_user.id, segments, tts_config, engine_settings))
    return get_json_result(data=payload)


@manager.route("/chat/audio/speech/sync/<job_id>", methods=["GET"])  # noqa: F821
@login_required
def get_tts_sync_job(job_id):
    job = _load_tts_sync_job(job_id)
    if not job:
        return get_data_error_result(message="TTS sync job not found or expired.")
    return get_json_result(data=job)


_QWEN3_ASR_URL = "http://127.0.0.1:9900/v1/audio/transcriptions"
_QWEN3_ASR_TIMEOUT = 60.0

_asr_log = logging.getLogger("panython.asr")


async def _call_qwen3_asr(
    audio_bytes: bytes, suffix: str, language: str | None,
    vad: bool = False, punctuation: bool = False,
) -> str:
    """Call Qwen3-ASR-1.7B at port 9900 and return transcript text."""
    import httpx

    data: dict = {"model": "qwen3-asr"}
    if language and language != "auto":
        data["language"] = language
    if vad:
        data["vad"] = "true"
    if punctuation:
        data["punctuation"] = "true"

    try:
        async with httpx.AsyncClient(timeout=_QWEN3_ASR_TIMEOUT) as client:
            resp = await client.post(
                _QWEN3_ASR_URL,
                files={"file": (f"audio{suffix}", audio_bytes, "audio/octet-stream")},
                data=data,
            )
            resp.raise_for_status()
            return resp.json().get("text", "")
    except Exception as exc:
        _asr_log.warning("Qwen3-ASR call failed: %s", exc)
        return ""


def _call_sensevoice_asr(audio_path: str, user_id: str) -> str:
    """Call SenseVoice via the tenant's default SPEECH2TEXT model."""
    try:
        default_asr_model_config = get_tenant_default_model_by_type(user_id, LLMType.SPEECH2TEXT)
        asr_mdl = LLMBundle(user_id, default_asr_model_config)
        return asr_mdl.transcription(audio_path) or ""
    except Exception as exc:
        _asr_log.warning("SenseVoice ASR call failed: %s", exc)
        return ""


def _merge_asr_results(text_a: str, text_b: str, strategy: str) -> str:
    """Merge two ASR results according to the configured merge strategy."""
    a = text_a.strip()
    b = text_b.strip()
    if strategy == "qwen3_primary":
        return a if a else b
    if strategy == "sensevoice_primary":
        return b if b else a
    # "longest" — pick the result with more characters
    return a if len(a) >= len(b) else b


@manager.route("/chat/audio/transcription", methods=["POST"])  # noqa: F821
@login_required
async def transcription():
    req = await request.form
    stream_mode = req.get("stream", "false").lower() == "true"
    files = await request.files
    if "file" not in files:
        return get_data_error_result(message="Missing 'file' in multipart form-data")

    uploaded = files["file"]

    ALLOWED_EXTS = {
        ".wav", ".mp3", ".m4a", ".aac",
        ".flac", ".ogg", ".webm",
        ".opus", ".wma",
    }

    filename = uploaded.filename or ""
    suffix = os.path.splitext(filename)[-1].lower()
    if suffix not in ALLOWED_EXTS:
        return get_data_error_result(
            message=f"Unsupported audio format: {suffix}. Allowed: {', '.join(sorted(ALLOWED_EXTS))}"
        )

    fd, temp_audio_path = tempfile.mkstemp(suffix=suffix)
    os.close(fd)
    await uploaded.save(temp_audio_path)

    try:
        asr_cfg = PanythonASRSettingsService.get_settings()
        mode = asr_cfg.get("mode", "dual")
        single_model = asr_cfg.get("single_model", "qwen3")
        dual_merge = asr_cfg.get("dual_merge", "qwen3_primary")
        language = asr_cfg.get("language", "auto")
        lang_hint = language if language != "auto" else None
        use_vad = bool(asr_cfg.get("vad", False))
        use_punc = bool(asr_cfg.get("punctuation", False))

        audio_bytes = open(temp_audio_path, "rb").read()

        if mode == "single":
            if single_model == "qwen3":
                text = await _call_qwen3_asr(audio_bytes, suffix, lang_hint, vad=use_vad, punctuation=use_punc)
                if not text:
                    # Fallback to SenseVoice if Qwen3-ASR fails
                    text = await asyncio.get_event_loop().run_in_executor(
                        None, _call_sensevoice_asr, temp_audio_path, current_user.id
                    )
            else:
                text = await asyncio.get_event_loop().run_in_executor(
                    None, _call_sensevoice_asr, temp_audio_path, current_user.id
                )
        else:
            # Dual mode: both in parallel; VAD+punc applied inside Qwen3-ASR server
            qwen3_task = asyncio.create_task(
                _call_qwen3_asr(audio_bytes, suffix, lang_hint, vad=use_vad, punctuation=use_punc)
            )
            sv_task = asyncio.get_event_loop().run_in_executor(
                None, _call_sensevoice_asr, temp_audio_path, current_user.id
            )
            qwen3_text, sv_text = await asyncio.gather(qwen3_task, sv_task, return_exceptions=True)
            if isinstance(qwen3_text, Exception):
                qwen3_text = ""
            if isinstance(sv_text, Exception):
                sv_text = ""
            text = _merge_asr_results(str(qwen3_text), str(sv_text), dual_merge)
            _asr_log.info(
                "Dual ASR — qwen3=%d chars, sv=%d chars, merged=%d chars, strategy=%s",
                len(str(qwen3_text)), len(str(sv_text)), len(text), dual_merge,
            )

        _asr_log.info("ASR done — mode=%s, chars=%d", mode, len(text))
    except Exception as exc:
        _asr_log.error("ASR routing failed, falling back to default: %s", exc)
        text = ""
    finally:
        try:
            os.remove(temp_audio_path)
        except Exception as e:
            logging.error(f"Failed to remove temp audio file: {str(e)}")

    if stream_mode:
        result_text = text

        async def event_stream():
            yield f"data: {json.dumps({'event': 'text', 'text': result_text}, ensure_ascii=False)}\n\n"

        return Response(event_stream(), content_type="text/event-stream")

    return get_json_result(data={"text": text})


@manager.route("/chat/mindmap", methods=["POST"])  # noqa: F821
@login_required
@validate_request("question", "kb_ids")
async def mindmap():
    req = await get_request_json()
    search_id = req.get("search_id", "")
    search_app = SearchService.get_detail(search_id) if search_id else {}
    search_config = search_app.get("search_config", {}) if search_app else {}
    kb_ids = search_config.get("kb_ids", [])
    kb_ids.extend(req["kb_ids"])
    kb_ids = list(set(kb_ids))

    mind_map = await gen_mindmap(req["question"], kb_ids, search_app.get("tenant_id", current_user.id), search_config)
    if "error" in mind_map:
        return server_error_response(Exception(mind_map["error"]))
    return get_json_result(data=mind_map)


@manager.route("/chat/recommendation", methods=["POST"])  # noqa: F821
@login_required
@validate_request("question")
async def recommendation():
    req = await get_request_json()

    search_id = req.get("search_id", "")
    search_config = {}
    if search_id:
        if search_app := SearchService.get_detail(search_id):
            search_config = search_app.get("search_config", {})

    question = req["question"]

    chat_id = search_config.get("chat_id", "")
    if chat_id:
        chat_model_config = get_model_config_by_type_and_name(current_user.id, LLMType.CHAT, chat_id)
    else:
        chat_model_config = get_tenant_default_model_by_type(current_user.id, LLMType.CHAT)
    chat_mdl = LLMBundle(current_user.id, chat_model_config)

    gen_conf = search_config.get("llm_setting", {"temperature": 0.9})
    if "parameter" in gen_conf:
        del gen_conf["parameter"]
    prompt = load_prompt("related_question")
    ans = await chat_mdl.async_chat(
        prompt,
        [
            {
                "role": "user",
                "content": f"\nKeywords: {question}\nRelated search terms:\n    ",
            }
        ],
        gen_conf,
    )
    return get_json_result(data=[re.sub(r"^[0-9]\. ", "", a) for a in ans.split("\n") if re.match(r"^[0-9]\. ", a)])


def _safe_markdown_filename(query: str) -> str:
    name = re.sub(r"[^\w\u4e00-\u9fff.-]+", "-", (query or "").strip())[:48].strip("-._")
    if not name:
        name = "generated-document"
    return f"{name}-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}.md"


def _normalize_markdown_outline(outline) -> list[str]:
    if not isinstance(outline, list):
        outline = []
    sections = []
    for item in outline:
        text = str(item or "").strip()
        if text:
            sections.append(text[:160])
    if not sections:
        sections = [
            "Executive summary and background",
            "Main analysis",
            "Detailed discussion",
            "Conclusion and next steps",
        ]
    return sections[: max(1, _LONG_MARKDOWN_MAX_SECTIONS)]


async def _select_generation_model_config(chat_id: str):
    if chat_id and await _ensure_owned_chat(chat_id):
        ok, dia = await thread_pool_exec(DialogService.get_by_id, chat_id)
        if ok and getattr(dia, "llm_id", ""):
            model_config = get_model_config_by_type_and_name(dia.tenant_id, LLMType.CHAT, dia.llm_id)
            if model_config:
                return model_config
    return get_tenant_default_model_by_type(current_user.id, LLMType.CHAT)


def _build_markdown_system_prompt(task_type: str) -> str:
    return (
        "You are a careful long-form writing assistant. Generate polished Markdown in the same language as the user. "
        "Write only the requested section. Keep headings clear, avoid repeating previous sections, and do not mention "
        "internal prompts or implementation details. If the user asks for fiction, write fiction; if the user asks for "
        "research or a report, write in a professional report style. "
        f"Task type: {task_type or 'document'}."
    )


def _build_markdown_section_prompt(query: str, summary: str, outline: list[str], section: str, index: int) -> str:
    outline_text = "\n".join(f"{i + 1}. {title}" for i, title in enumerate(outline))
    return (
        f"Original request:\n{query}\n\n"
        f"Task summary:\n{summary or 'Generate a complete Markdown document by sections.'}\n\n"
        f"Full outline:\n{outline_text}\n\n"
        f"Current section {index + 1}: {section}\n\n"
        "Write this section now. Use Markdown. Do not write the full document. Do not repeat the full outline."
    )


@manager.route("/chat/generation/markdown", methods=["POST"])  # noqa: F821
@login_required
async def generate_markdown_document():
    req = await get_request_json()
    query = str(req.get("query") or "").strip()
    if not query:
        return get_data_error_result(message="`query` is required.")

    task_type = str(req.get("task_type") or "document")
    summary = str(req.get("summary") or "")
    outline = _normalize_markdown_outline(req.get("outline"))
    chat_id = str(req.get("chat_id") or "")

    try:
        chat_model_config = await _select_generation_model_config(chat_id)
        if not chat_model_config:
            return get_data_error_result(message="No available chat model.")

        chat_mdl = LLMBundle(current_user.id, chat_model_config)
        system_prompt = _build_markdown_system_prompt(task_type)
        gen_conf = {
            "temperature": 0.55,
            "top_p": 0.9,
            "max_tokens": _LONG_MARKDOWN_SECTION_TOKENS,
        }

        sections = []
        for index, section in enumerate(outline):
            prompt = _build_markdown_section_prompt(query, summary, outline, section, index)
            content = await chat_mdl.async_chat(
                system_prompt,
                [{"role": "user", "content": prompt}],
                gen_conf,
            )
            sections.append((section, (content or "").strip()))

        title = re.sub(r"\s+", " ", query).strip()[:80] or "Generated document"
        generated_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
        md_parts = [
            f"# {title}",
            "",
            f"> Generated at: {generated_at}",
            f"> Task type: {task_type}",
            "",
            "## Outline",
            "",
            *[f"{i + 1}. {section}" for i, section in enumerate(outline)],
            "",
        ]
        for section, content in sections:
            md_parts.extend([f"## {section}", "", content, ""])

        markdown = "\n".join(md_parts).strip() + "\n"
        file_id = f"generated-markdown-{get_uuid()}.md"
        filename = _safe_markdown_filename(query)
        payload = markdown.encode("utf-8")
        await thread_pool_exec(settings.STORAGE_IMPL.put, current_user.id, file_id, payload)
        return get_json_result(
            data={
                "download": {
                    "doc_id": file_id,
                    "filename": filename,
                    "mime_type": "text/markdown",
                    "size": len(payload),
                },
                "preview": markdown[:1200],
            }
        )
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chat/completions", methods=["POST"])  # noqa: F821
@login_required
async def session_completion(chat_id_in_arg=""):
    """Handle chat completion requests, streaming or non-streaming, scoped to the authenticated user."""
    req = await get_request_json()
    normalized, error = _normalize_completion_messages(req)
    if error:
        return error
    request_messages, request_msg = normalized
    pass_all_history_messages = _get_bool_request_flag(req, "pass_all_history_messages", "pass_all_history", default=False)
    msg = request_msg
    message_id = request_msg[-1].get("id")
    chat_id = req.pop("chat_id", "") or ""
    chat_id = chat_id or chat_id_in_arg
    session_id = req.pop("session_id", "") or req.pop("conversation_id", "") or ""
    chat_model_id = req.pop("llm_id", "")
    selected_kb_ids = req.pop("selected_kb_ids", None)

    chat_model_config = {}
    for model_config in ["temperature", "top_p", "frequency_penalty", "presence_penalty", "max_tokens"]:
        config = req.get(model_config)
        if config:
            chat_model_config[model_config] = config

    try:
        conv = None
        if session_id and not chat_id:
            return get_data_error_result(message="`chat_id` is required when `session_id` is provided.")

        if chat_id:
            if not await _ensure_owned_chat(chat_id):
                return get_json_result(
                    data=False,
                    message="No authorization.",
                    code=RetCode.AUTHENTICATION_ERROR,
                )
            e, dia = await thread_pool_exec(DialogService.get_by_id, chat_id)
            if not e:
                return get_data_error_result(message="Chat not found!")
            if session_id:
                e, conv = await thread_pool_exec(ConversationService.get_by_id, session_id)
                if not e:
                    return get_data_error_result(message="Session not found!")
                if conv.dialog_id != chat_id:
                    return get_data_error_result(message="Session does not belong to this chat!")
            else:
                conv = await _create_session_for_completion(chat_id, dia, current_user.id)
                session_id = conv.id

            if pass_all_history_messages:
                conv.message = deepcopy(request_messages)
                msg = request_msg
            else:
                if not conv.message:
                    conv.message = []
                conv.message.append(deepcopy(request_msg[-1]))
                msg = []
                for m in conv.message:
                    if m["role"] == "system":
                        continue
                    if m["role"] == "assistant" and not msg:
                        continue
                    msg.append(m)
        else:
            dia = _build_default_completion_dialog()
            dia.llm_setting = chat_model_config

        req.pop("messages", None)
        req.pop("question", None)

        if conv is not None:
            if not conv.reference:
                conv.reference = []
            conv.reference = [r for r in conv.reference if r]
            conv.reference.append({"chunks": [], "doc_aggs": []})

        if chat_model_id:
            if not await thread_pool_exec(TenantLLMService.get_api_key, tenant_id=dia.tenant_id, model_name=chat_model_id):
                return get_data_error_result(message=f"Cannot use specified model {chat_model_id}.")
            dia.llm_id = chat_model_id
            dia.llm_setting = chat_model_config

        if selected_kb_ids is not None:
            if not isinstance(selected_kb_ids, list):
                return get_data_error_result(message="`selected_kb_ids` should be a list.")
            validated_kb_ids = await _validate_dataset_ids(selected_kb_ids, current_user.id)
            if isinstance(validated_kb_ids, str):
                return get_data_error_result(message=validated_kb_ids)
            dia = deepcopy(dia)
            dia.kb_ids = validated_kb_ids

        stream_mode = req.pop("stream", True)

        def _format_answer(ans):
            """Wrap a raw answer dict with session and chat identifiers."""
            formatted = structure_answer(conv, ans, message_id, session_id)
            if chat_id:
                formatted["chat_id"] = chat_id
            return formatted

        async def stream():
            """Yield SSE-formatted chunks from the async chat generator."""
            nonlocal dia, msg, req, conv
            context_recovery_attempted = False
            try:
                async for ans in async_chat(dia, msg, True, **req):
                    ans = _format_answer(ans)
                    yield "data:" + json.dumps({"code": 0, "message": "", "data": ans}, ensure_ascii=False) + "\n\n"
                if conv is not None:
                    await thread_pool_exec(ConversationService.update_by_id, conv.id, conv.to_dict())
            except Exception as ex:
                if _is_context_span_error(ex) and not context_recovery_attempted:
                    context_recovery_attempted = True
                    logging.exception(
                        "Context span error reached API stream boundary; waiting for ds4 watchdog recovery before one automatic retry"
                    )
                    yield "data:" + json.dumps(
                        {
                            "code": 0,
                            "message": "",
                            "data": {
                                "answer": "<retrieving>Model KV cache recovery is in progress; retrying this request automatically.\n</retrieving>",
                                "reference": {},
                                "final": False,
                            },
                        },
                        ensure_ascii=False,
                    ) + "\n\n"
                    await asyncio.sleep(max(1, _CONTEXT_RECOVERY_WAIT_SECONDS))
                    try:
                        async for ans in async_chat(dia, msg, True, **req):
                            ans = _format_answer(ans)
                            yield "data:" + json.dumps({"code": 0, "message": "", "data": ans}, ensure_ascii=False) + "\n\n"
                        if conv is not None:
                            await thread_pool_exec(ConversationService.update_by_id, conv.id, conv.to_dict())
                        yield "data:" + json.dumps({"code": 0, "message": "", "data": True}, ensure_ascii=False) + "\n\n"
                        return
                    except Exception as retry_ex:
                        ex = retry_ex
                logging.exception(ex)
                error_text = str(ex)
                normalized_error = error_text
                if error_text.upper().startswith("ERROR:"):
                    normalized_error = error_text.split(":", 1)[1].strip()
                if not normalized_error.startswith("**ERROR**:"):
                    normalized_error = "**ERROR**: " + normalized_error
                yield "data:" + json.dumps({"code": 500, "message": str(ex), "data": {"answer": normalized_error, "reference": []}}, ensure_ascii=False) + "\n\n"
            yield "data:" + json.dumps({"code": 0, "message": "", "data": True}, ensure_ascii=False) + "\n\n"

        if stream_mode:
            resp = Response(stream(), mimetype="text/event-stream")
            resp.headers.add_header("Cache-control", "no-cache")
            resp.headers.add_header("Connection", "keep-alive")
            resp.headers.add_header("X-Accel-Buffering", "no")
            resp.headers.add_header("Content-Type", "text/event-stream; charset=utf-8")
            return resp

        answer = None
        async for ans in async_chat(dia, msg, False, **req):
            answer = _format_answer(ans)
            if conv is not None:
                await thread_pool_exec(ConversationService.update_by_id, conv.id, conv.to_dict())
            break
        return get_json_result(data=answer)
    except Exception as ex:
        return server_error_response(ex)


@manager.route("/chat/memorize", methods=["POST"])  # noqa: F821
@login_required
@validate_request("chat_id", "session_id")
async def memorize_chat_session():
    req = await get_request_json()
    chat_id = req["chat_id"]
    session_id = req["session_id"]
    requested_topic = req.get("topic")

    try:
        owned_chats = await _ensure_owned_chat(chat_id)
        if not owned_chats:
            return get_json_result(data=False, message="No authorization.", code=RetCode.AUTHENTICATION_ERROR)
        chat = owned_chats[0]

        ok, conv = await thread_pool_exec(ConversationService.get_by_id, session_id)
        if not ok or conv.dialog_id != chat_id:
            return get_data_error_result(message="Session does not belong to this chat!")

        transcript = _format_conversation_transcript(conv.message)
        if not transcript:
            return get_data_error_result(message="No conversation messages to memorize.")

        memory_name = _chat_memo_name(chat_id, session_id)
        existing = await thread_pool_exec(MemoryService.query, tenant_id=current_user.id, name=memory_name)
        created = False
        chat_config = None
        if existing:
            memory = existing[0]
        else:
            embd_config = await thread_pool_exec(get_tenant_default_model_by_type, current_user.id, LLMType.EMBEDDING)
            chat_config = await thread_pool_exec(get_tenant_default_model_by_type, current_user.id, LLMType.CHAT)
            success, memory = await thread_pool_exec(
                MemoryService.create_memory,
                current_user.id,
                memory_name,
                _CHAT_MEMO_MEMORY_TYPES,
                embd_config["llm_name"],
                embd_config.get("id"),
                chat_config["llm_name"],
                chat_config.get("id"),
            )
            if not success:
                return get_data_error_result(message=str(memory))
            created = True

        topic = _sanitize_chat_memo_topic(requested_topic) or _sanitize_chat_memo_topic(getattr(memory, "description", ""))
        if not topic:
            topic = _fallback_chat_memo_topic(transcript)
        if topic and topic != (getattr(memory, "description", "") or "").strip():
            await thread_pool_exec(MemoryService.update_memory, current_user.id, memory.id, {"description": topic})

        memo_content = _fallback_chat_memo_content(transcript, topic)
        success, msg = await queue_save_to_memory_task(
            [memory.id],
            {
                "user_id": current_user.id,
                "agent_id": chat_id,
                "session_id": session_id,
                "user_input": memo_content,
                "agent_response": "",
                "memo_topic": topic,
                "related_kb_ids": getattr(chat, "kb_ids", []) or [],
            },
        )
        if not success:
            if created:
                await _cleanup_created_chat_memo(memory)
            return get_json_result(code=RetCode.SERVER_ERROR, message=msg)

        memory_profile_service.invalidate_profile_cache(current_user.id)
        return get_json_result(data={"memory_id": memory.id, "created": created, "topic": topic}, message=msg)
    except Exception as ex:
        return server_error_response(ex)
