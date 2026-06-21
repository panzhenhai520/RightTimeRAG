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

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Any

from api.apps.services.memory_api_service import (
    _compact_memory_preview,
    _extract_structured_summary_from_message,
    _joined_tenant_ids,
    _memory_topic_text,
)
from api.db.services.memory_service import MemoryService
from api.utils.canonical_topic import extract_topic_keywords, infer_canonical_topic, normalize_topic_text
from api.utils.memory_utils import get_memory_display_name, get_memory_type_human, is_chat_memo_name
from common.misc_utils import thread_pool_exec
from memory.services.messages import MessageService
from rag.utils.redis_conn import REDIS_CONN


PROFILE_VERSION = "memo-thought-profile-v1"
PROFILE_CACHE_TTL_SECONDS = 7 * 24 * 3600
PROFILE_BUILD_LOCK_TTL_SECONDS = 20 * 60
PROFILE_MAX_MEMORIES = 500
PROFILE_MAX_EVENTS = 120
PROFILE_STALE_SECONDS = 6 * 3600
TOPIC_VECTOR_MODEL = "semantic-hashing-v1"
TOPIC_VECTOR_DIMENSIONS = 96
TOPIC_VECTOR_CACHE_TTL_SECONDS = PROFILE_CACHE_TTL_SECONDS
TOPIC_CACHE_VERSION = "memo-profile-topic-cache-v1"
TOPIC_CACHE_MAX_TOPICS = 240
TOPIC_CACHE_SEMANTIC_MATCH_THRESHOLD = 0.56
TOPIC_MERGE_VERSION = "memo-topic-merge-v1"
TOPIC_MERGE_SUGGESTION_THRESHOLD = 0.5
INTERNAL_EVENT_KEYS = {"terms", "semantic_vector"}


DOMAIN_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("math", ("数学", "方程", "函数", "算法", "模型", "量化", "linear", "equation", "model", "algorithm")),
    ("finance", ("理财", "资产", "投资", "薪酬", "财富", "金融", "portfolio", "investment", "wealth", "salary")),
    ("law", ("法律", "信托", "契诺", "条例", "责任", "租金", "trust", "law", "liability", "covenant")),
    ("enterprise", ("企业", "家族企业", "经营", "治理", "传承", "family enterprise", "governance", "succession")),
    ("industry", ("化工", "行业", "制造", "供应链", "chemical", "industry", "manufacturing")),
    ("ai", ("ai", "人工智能", "大模型", "智能体", "算法", "llm", "agent", "embedding")),
)

INTENT_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("learning", ("学习", "解释", "是什么", "介绍", "理解", "learn", "explain", "what is")),
    ("compare", ("比较", "区别", "对比", "哪个", "compare", "difference", "versus")),
    ("decision", ("怎么做", "如何", "方案", "建议", "选择", "决策", "strategy", "recommend", "should")),
    ("risk", ("风险", "责任", "合规", "保障", "限制", "risk", "liability", "compliance")),
    ("execution", ("配置", "部署", "运行", "测试", "安装", "执行", "deploy", "configure", "run")),
    ("research", ("研究", "报告", "分析", "总结", "趋势", "research", "report", "analysis")),
    ("writing", ("写", "生成", "小说", "文档", "draft", "write", "generate")),
)

DOMAIN_LABELS = {
    "math": "数学/模型",
    "finance": "金融/财富",
    "law": "法律/信托",
    "enterprise": "企业治理",
    "industry": "行业知识",
    "ai": "AI/工具",
    "general": "综合主题",
}

INTENT_LABELS = {
    "learning": "学习理解",
    "compare": "比较判断",
    "decision": "决策研究",
    "risk": "风险排查",
    "execution": "执行落地",
    "research": "研究分析",
    "writing": "写作生成",
    "general": "综合探索",
}


@dataclass(frozen=True)
class TopicCluster:
    id: str
    label: str
    domain: str
    event_ids: list[str]
    keywords: list[str]
    score: float
    source_topic_ids: list[str]


def _snapshot_key(user_id: str) -> str:
    return f"memo:thought_profile:snapshot:{user_id}"


def _lock_key(user_id: str) -> str:
    return f"memo:thought_profile:building:{user_id}"


def _status_key(user_id: str) -> str:
    return f"memo:thought_profile:status:{user_id}"


def _topic_vector_key(text_hash: str) -> str:
    return f"memo:thought_profile:topic_vector:{TOPIC_VECTOR_MODEL}:{text_hash}"


def _topic_cache_key(user_id: str) -> str:
    return f"memo:thought_profile:topic_cache:{user_id}"


def _topic_merge_key(user_id: str) -> str:
    return f"memo:thought_profile:topic_merges:{user_id}"


def _delete_key(key: str) -> None:
    try:
        redis_client = getattr(REDIS_CONN, "REDIS", None)
        if redis_client:
            redis_client.delete(key)
            return
        store = getattr(REDIS_CONN, "store", None)
        if isinstance(store, dict):
            store.pop(key, None)
    except Exception as exc:
        logging.warning("Memo profile cache delete failed key=%s err=%s", key, exc)


def _json_get(key: str) -> dict | None:
    raw = REDIS_CONN.get(key)
    if not raw:
        return None
    try:
        return json.loads(raw)
    except Exception:
        return None


def _json_set(key: str, value: dict, ttl: int = PROFILE_CACHE_TTL_SECONDS) -> bool:
    return REDIS_CONN.set_obj(key, value, exp=ttl)


def _empty_topic_merges() -> dict:
    return {"version": TOPIC_MERGE_VERSION, "rules": {}, "updated_at": 0}


def disabled_topic_merges() -> dict:
    payload = _empty_topic_merges()
    payload["feature_enabled"] = False
    return payload


def disabled_profile_snapshot() -> dict:
    return {
        "version": PROFILE_VERSION,
        "status": "disabled",
        "feature_enabled": False,
        "generated_at": 0,
        "stale": False,
        "memory_count": 0,
        "event_count": 0,
        "summary": {
            "headline": "Memo profile is disabled.",
            "trajectory": "",
            "next_direction": "",
            "focus_domains": [],
        },
        "events": [],
        "topics": [],
        "topic_merges": disabled_topic_merges(),
        "topic_merge_suggestions": [],
        "edges": [],
        "predictions": [],
        "algorithm_notes": [],
    }


def _load_topic_merges(user_id: str) -> dict:
    payload = _json_get(_topic_merge_key(user_id)) or {}
    rules = payload.get("rules") if isinstance(payload, dict) else {}
    if not isinstance(rules, dict):
        rules = {}
    return {
        "version": payload.get("version") or TOPIC_MERGE_VERSION,
        "rules": {
            str(source): rule
            for source, rule in rules.items()
            if isinstance(rule, dict) and rule.get("target_topic_id")
        },
        "updated_at": int(payload.get("updated_at") or 0),
    }


def _save_topic_merges(user_id: str, payload: dict) -> dict:
    payload = {
        "version": TOPIC_MERGE_VERSION,
        "rules": payload.get("rules") or {},
        "updated_at": int(time.time()),
    }
    _json_set(_topic_merge_key(user_id), payload)
    _delete_key(_snapshot_key(user_id))
    return payload


def _clean_text(value: Any) -> str:
    text = str(value or "")
    text = re.sub(r"<(?:retrieving|think)>[\s\S]*?</(?:retrieving|think)>", " ", text, flags=re.I)
    text = re.sub(r"</?(?:retrieving|think)>", " ", text, flags=re.I)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def _normalize_topic_id(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ":" in text:
        return text[:120]
    normalized = normalize_topic_text(text).replace(" ", "-")
    return f"topic:{normalized}" if normalized else ""


def _short_label(value: Any, fallback: str = "") -> str:
    label = _clean_text(value) or fallback
    return label[:80]


def get_topic_merges(user_id: str) -> dict:
    return _load_topic_merges(user_id)


def upsert_topic_merge(
    user_id: str,
    source_topic_ids: list[str],
    target_topic_id: str,
    target_label: str = "",
    reason: str = "",
) -> dict:
    target_id = _normalize_topic_id(target_topic_id)
    if not target_id:
        raise ValueError("target_topic_id is required")
    sources = []
    for source in source_topic_ids or []:
        source_id = _normalize_topic_id(source)
        if source_id and source_id != target_id and source_id not in sources:
            sources.append(source_id)
    if not sources:
        raise ValueError("source_topic_ids must contain at least one topic different from target_topic_id")

    payload = _load_topic_merges(user_id)
    rules = dict(payload.get("rules") or {})
    for source_id in sources:
        rules[source_id] = {
            "target_topic_id": target_id,
            "target_label": _short_label(target_label, fallback=target_id),
            "reason": _short_label(reason, fallback="manual merge"),
            "created_at": int(time.time()),
        }
    payload["rules"] = rules
    return _save_topic_merges(user_id, payload)


def delete_topic_merge(
    user_id: str,
    source_topic_ids: list[str] | None = None,
    target_topic_id: str | None = None,
) -> dict:
    payload = _load_topic_merges(user_id)
    rules = dict(payload.get("rules") or {})
    sources = [_normalize_topic_id(source) for source in (source_topic_ids or [])]
    target_id = _normalize_topic_id(target_topic_id)

    if sources:
        for source_id in sources:
            rules.pop(source_id, None)
    elif target_id:
        rules = {
            source_id: rule
            for source_id, rule in rules.items()
            if _normalize_topic_id(rule.get("target_topic_id")) != target_id
        }
    else:
        rules = {}
    payload["rules"] = rules
    return _save_topic_merges(user_id, payload)


def _resolve_topic_merge(topic_id: str, rules: dict[str, dict]) -> dict | None:
    source_id = _normalize_topic_id(topic_id)
    visited = set()
    current_id = source_id
    current_rule = None
    for _ in range(10):
        if not current_id or current_id in visited:
            break
        visited.add(current_id)
        rule = rules.get(current_id)
        if not rule:
            break
        current_rule = rule
        next_id = _normalize_topic_id(rule.get("target_topic_id"))
        if not next_id or next_id == current_id:
            break
        current_id = next_id
    if not current_rule or current_id == source_id:
        return None
    return {
        "target_topic_id": current_id,
        "target_label": _short_label(current_rule.get("target_label"), fallback=current_id),
        "reason": _short_label(current_rule.get("reason"), fallback="manual merge"),
    }


def _apply_topic_merges(events: list[dict], merge_payload: dict | None) -> list[dict]:
    rules = (merge_payload or {}).get("rules") or {}
    if not rules:
        return events
    merged = []
    for event in events:
        rule = _resolve_topic_merge(event.get("topic_id", ""), rules)
        if not rule:
            merged.append(event)
            continue
        next_event = dict(event)
        next_event["original_topic_id"] = event.get("topic_id")
        next_event["original_topic_label"] = event.get("topic_label")
        next_event["topic_id"] = rule["target_topic_id"]
        next_event["topic_label"] = rule["target_label"]
        next_event["topic_merge"] = {
            "type": "manual",
            "reason": rule["reason"],
            "source_topic_id": event.get("topic_id"),
        }
        merged.append(next_event)
    return merged


def _terms(text: str) -> list[str]:
    text = normalize_topic_text(_clean_text(text))
    terms = re.findall(r"[a-z][a-z0-9.-]{2,}|[\u4e00-\u9fff]{2,}", text)
    chinese_chars = re.findall(r"[\u4e00-\u9fff]", text)
    for size in (2, 3, 4):
        for idx in range(max(0, len(chinese_chars) - size + 1)):
            terms.append("".join(chinese_chars[idx : idx + size]))
    stop = {"用户", "助手", "问题", "关于", "什么", "如何", "哪些", "the", "and", "with", "this"}
    seen = set()
    res = []
    for term in terms:
        if term in stop or term in seen:
            continue
        seen.add(term)
        res.append(term)
    return res


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / max(1, len(left_set | right_set))


def _semantic_text_hash(text: str) -> str:
    normalized = normalize_topic_text(_clean_text(text))
    return hashlib.sha256(normalized.encode("utf-8", "ignore")).hexdigest()[:32]


def _semantic_token_weight(term: str) -> float:
    # Longer domain terms carry slightly more signal while staying bounded.
    return 1.0 + min(2.0, math.log1p(len(term)))


def _build_semantic_vector_uncached(text: str) -> list[float]:
    vector = [0.0] * TOPIC_VECTOR_DIMENSIONS
    terms = _terms(text)
    if not terms:
        return vector
    for term in terms:
        digest = hashlib.blake2b(term.encode("utf-8", "ignore"), digest_size=16).digest()
        weight = _semantic_token_weight(term)
        for offset in (0, 4):
            bucket = int.from_bytes(digest[offset : offset + 4], "big") % TOPIC_VECTOR_DIMENSIONS
            sign = 1.0 if digest[offset + 8] % 2 else -1.0
            vector[bucket] += sign * weight
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _semantic_vector(text: str) -> tuple[list[float], bool]:
    text_hash = _semantic_text_hash(text)
    if not text_hash:
        return [0.0] * TOPIC_VECTOR_DIMENSIONS, False
    key = _topic_vector_key(text_hash)
    cached = _json_get(key)
    if cached and cached.get("model") == TOPIC_VECTOR_MODEL and isinstance(cached.get("vector"), list):
        try:
            vector = [float(value) for value in cached["vector"]]
            if len(vector) == TOPIC_VECTOR_DIMENSIONS:
                return vector, True
        except Exception:
            pass
    vector = _build_semantic_vector_uncached(text)
    _json_set(
        key,
        {"model": TOPIC_VECTOR_MODEL, "text_hash": text_hash, "vector": vector},
        ttl=TOPIC_VECTOR_CACHE_TTL_SECONDS,
    )
    return vector, False


def _cosine_vectors(left: list[float] | None, right: list[float] | None) -> float:
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    if size <= 0:
        return 0.0
    score = sum(float(left[idx]) * float(right[idx]) for idx in range(size))
    return max(0.0, min(1.0, score))


def _average_vectors(vectors: list[list[float]]) -> list[float]:
    valid = [vector for vector in vectors if vector]
    if not valid:
        return [0.0] * TOPIC_VECTOR_DIMENSIONS
    size = min(TOPIC_VECTOR_DIMENSIONS, min(len(vector) for vector in valid))
    averaged = [sum(vector[idx] for vector in valid) / len(valid) for idx in range(size)]
    if size < TOPIC_VECTOR_DIMENSIONS:
        averaged.extend([0.0] * (TOPIC_VECTOR_DIMENSIONS - size))
    norm = math.sqrt(sum(value * value for value in averaged))
    if norm <= 0:
        return averaged
    return [round(value / norm, 6) for value in averaged]


def _topic_source_signature(source_topic_ids: list[str]) -> str:
    normalized = sorted({ _normalize_topic_id(topic_id) for topic_id in source_topic_ids if _normalize_topic_id(topic_id) })
    return "|".join(normalized)


def _stable_topic_id(user_id: str, cluster: TopicCluster) -> str:
    signature = _topic_source_signature(cluster.source_topic_ids) or normalize_topic_text(cluster.label)
    digest = hashlib.sha256(f"{user_id}:{signature}".encode("utf-8", "ignore")).hexdigest()[:16]
    return f"profile-topic:{digest}"


def _load_topic_cache(user_id: str) -> dict:
    payload = _json_get(_topic_cache_key(user_id)) or {}
    topics = payload.get("topics") if isinstance(payload, dict) else []
    if not isinstance(topics, list):
        topics = []
    return {
        "version": payload.get("version") or TOPIC_CACHE_VERSION,
        "semantic_model": payload.get("semantic_model") or TOPIC_VECTOR_MODEL,
        "updated_at": int(payload.get("updated_at") or 0),
        "topics": [
            topic
            for topic in topics
            if isinstance(topic, dict) and topic.get("id") and isinstance(topic.get("source_topic_ids"), list)
        ],
    }


def _save_topic_cache(user_id: str, clusters: list[TopicCluster], events_by_id: dict[str, dict]) -> dict:
    topics = []
    for cluster in clusters[:TOPIC_CACHE_MAX_TOPICS]:
        topics.append(
            {
                "id": cluster.id,
                "label": cluster.label,
                "domain": cluster.domain,
                "keywords": cluster.keywords,
                "source_topic_ids": cluster.source_topic_ids,
                "source_signature": _topic_source_signature(cluster.source_topic_ids),
                "vector": _cluster_vector(cluster, events_by_id),
                "score": round(cluster.score, 3),
                "event_count": len(cluster.event_ids),
                "updated_at": int(time.time()),
            }
        )
    payload = {
        "version": TOPIC_CACHE_VERSION,
        "semantic_model": TOPIC_VECTOR_MODEL,
        "updated_at": int(time.time()),
        "topics": topics,
    }
    _json_set(_topic_cache_key(user_id), payload)
    return payload


def _cached_topic_by_semantic_similarity(
    cluster: TopicCluster,
    cluster_vector: list[float],
    cached_topics: list[dict],
    used_cache_ids: set[str],
) -> dict | None:
    best_topic = None
    best_score = 0.0
    for topic in cached_topics:
        topic_id = str(topic.get("id") or "")
        if not topic_id or topic_id in used_cache_ids:
            continue
        score = _cosine_vectors(cluster_vector, topic.get("vector") or [])
        keyword_score = _jaccard(cluster.keywords, topic.get("keywords") or [])
        combined = max(score, keyword_score)
        if combined > best_score:
            best_topic = topic
            best_score = combined
    if best_topic and best_score >= TOPIC_CACHE_SEMANTIC_MATCH_THRESHOLD:
        return best_topic
    return None


def _stabilize_topic_clusters(
    user_id: str,
    clusters: list[TopicCluster],
    events_by_id: dict[str, dict],
) -> list[TopicCluster]:
    topic_cache = _load_topic_cache(user_id)
    cached_topics = topic_cache.get("topics") or []
    cached_by_source = {
        str(topic.get("source_signature") or _topic_source_signature(topic.get("source_topic_ids") or [])): topic
        for topic in cached_topics
        if topic.get("id")
    }
    stabilized = []
    used_cache_ids: set[str] = set()
    for cluster in clusters:
        source_signature = _topic_source_signature(cluster.source_topic_ids)
        cluster_vector = _cluster_vector(cluster, events_by_id)
        cached_topic = cached_by_source.get(source_signature) if source_signature else None
        if not cached_topic:
            cached_topic = _cached_topic_by_semantic_similarity(cluster, cluster_vector, cached_topics, used_cache_ids)

        stable_id = str(cached_topic.get("id")) if cached_topic else _stable_topic_id(user_id, cluster)
        if stable_id in used_cache_ids:
            stable_id = _stable_topic_id(user_id, cluster)
        used_cache_ids.add(stable_id)
        label = _short_label(cached_topic.get("label"), fallback=cluster.label) if cached_topic else cluster.label
        stabilized.append(
            TopicCluster(
                id=stable_id,
                label=label,
                domain=cluster.domain,
                event_ids=cluster.event_ids,
                keywords=cluster.keywords,
                score=cluster.score,
                source_topic_ids=cluster.source_topic_ids,
            )
        )
    _save_topic_cache(user_id, stabilized, events_by_id)
    return stabilized


def _public_event(event: dict) -> dict:
    return {key: value for key, value in event.items() if key not in INTERNAL_EVENT_KEYS}


def _classify_from_rules(text: str, rules: tuple[tuple[str, tuple[str, ...]], ...], fallback: str) -> str:
    normalized = normalize_topic_text(text)
    scores = []
    for index, (name, patterns) in enumerate(rules):
        score = sum(1 for pattern in patterns if normalize_topic_text(pattern) in normalized)
        if score:
            scores.append((score, -index, name))
    if not scores:
        return fallback
    scores.sort(reverse=True)
    return scores[0][2]


def _infer_source_kind(memory: dict) -> str:
    if not memory.get("is_chat_memo"):
        return "memory"
    agent_id = str(memory.get("latest_agent_id") or "")
    if agent_id.startswith("search-"):
        return "search"
    if agent_id.startswith("canvas-") or agent_id.startswith("agent-"):
        return "agent"
    return "chat"


def _fetch_profile_memories(user_id: str) -> list[dict]:
    allowed_tenant_ids = _joined_tenant_ids(user_id)
    memory_list, _ = MemoryService.get_by_filter(
        {"accessible_user_id": user_id, "tenant_id": list(allowed_tenant_ids)},
        "",
        page=1,
        page_size=PROFILE_MAX_MEMORIES,
    )
    enriched = []
    for memory in memory_list:
        message_count = 0
        latest_content_preview = ""
        latest_agent_id = ""
        latest_session_id = ""
        structured_summary = {}
        try:
            message_page = MessageService.list_message(memory["tenant_id"], memory["id"], page=1, page_size=1)
            message_count = message_page.get("total_count", 0)
            latest_messages = message_page.get("message_list") or []
            if latest_messages:
                latest_message = latest_messages[0]
                latest_content_preview = _compact_memory_preview(latest_message.get("content"))
                latest_agent_id = latest_message.get("agent_id") or ""
                latest_session_id = latest_message.get("session_id") or ""
                structured_summary = _extract_structured_summary_from_message(latest_message)
        except Exception as exc:
            logging.warning("Memo profile message read failed memory=%s err=%s", memory.get("id"), exc)

        display_name = get_memory_display_name(memory.get("name"), memory.get("description"))
        memory.update(
            {
                "memory_type": get_memory_type_human(memory["memory_type"]),
                "is_chat_memo": is_chat_memo_name(memory.get("name")),
                "display_name": display_name,
                "message_count": message_count,
                "latest_content_preview": latest_content_preview,
                "latest_agent_id": latest_agent_id,
                "latest_session_id": latest_session_id,
                "structured_summary": structured_summary,
            }
        )
        topic_text = _memory_topic_text(memory, structured_summary, display_name, latest_content_preview)
        memory["canonical_topic"] = infer_canonical_topic(topic_text).to_dict()
        enriched.append(memory)
    return enriched


def _memory_timestamp(memory: dict) -> int:
    timestamp = memory.get("create_time") or 0
    try:
        timestamp = int(timestamp)
    except Exception:
        timestamp = 0
    if timestamp > 10_000_000_000:
        return timestamp
    if timestamp > 0:
        return timestamp * 1000
    return int(time.time() * 1000)


def _build_events(memories: list[dict]) -> list[dict]:
    events = []
    for memory in memories[:PROFILE_MAX_EVENTS]:
        structured = memory.get("structured_summary") or {}
        canonical = memory.get("canonical_topic") or {}
        title = (
            structured.get("display_title")
            or canonical.get("label")
            or memory.get("display_name")
            or memory.get("description")
            or memory.get("name")
            or "memo"
        )
        summary = (
            memory.get("latest_content_preview")
            or " ".join(f.get("text", "") for f in structured.get("facts") or [] if isinstance(f, dict))
            or memory.get("description")
            or title
        )
        evidence_text = "\n".join(
            part
            for part in [
                title,
                summary,
                " ".join(structured.get("aliases") or []),
                " ".join(entity.get("text", "") for entity in structured.get("entities") or [] if isinstance(entity, dict)),
                " ".join(fact.get("text", "") for fact in structured.get("facts") or [] if isinstance(fact, dict)),
                " ".join(canonical.get("aliases") or []),
                canonical.get("label"),
            ]
            if part
        )
        keywords = list(
            dict.fromkeys(
                [
                    *extract_topic_keywords(evidence_text, 10),
                    *(structured.get("aliases") or []),
                    *(canonical.get("aliases") or []),
                ]
            )
        )[:12]
        domain = _classify_from_rules(evidence_text, DOMAIN_RULES, "general")
        intent = _classify_from_rules(evidence_text, INTENT_RULES, "general")
        topic_id = canonical.get("id") or f"topic:{normalize_topic_text(title).replace(' ', '-')}"
        semantic_text = "\n".join(
            part
            for part in [
                evidence_text,
                " ".join(keywords),
                " ".join(structured.get("dates") or []),
                " ".join(
                    amount.get("text", "")
                    for amount in structured.get("amounts") or []
                    if isinstance(amount, dict)
                ),
            ]
            if part
        )
        semantic_vector, semantic_cache_hit = _semantic_vector(semantic_text)
        event_id = f"event:{memory['id']}"
        events.append(
            {
                "id": event_id,
                "memory_id": memory["id"],
                "title": str(title)[:80],
                "summary": str(summary)[:700],
                "created_at": _memory_timestamp(memory),
                "topic_id": topic_id,
                "topic_label": canonical.get("label") or title,
                "domain": domain,
                "domain_label": DOMAIN_LABELS.get(domain, domain),
                "intent": intent,
                "intent_label": INTENT_LABELS.get(intent, intent),
                "keywords": keywords,
                "terms": _terms(evidence_text),
                "semantic_model": TOPIC_VECTOR_MODEL,
                "semantic_cache_hit": semantic_cache_hit,
                "semantic_vector": semantic_vector,
                "turns": max(1, int(memory.get("message_count") or 1)),
                "source_kind": _infer_source_kind(memory),
                "assistant_id": memory.get("latest_agent_id") or "",
                "session_id": memory.get("latest_session_id") or "",
                "related_kb_ids": structured.get("related_kb_ids") or [],
                "evidence": [
                    {"type": "memo", "memory_id": memory["id"], "title": str(title)[:80], "snippet": str(summary)[:220]}
                ],
                "confidence": canonical.get("confidence") or 0.45,
            }
        )
    return sorted(events, key=lambda item: item["created_at"])


def _cluster_events(events: list[dict]) -> list[TopicCluster]:
    clusters: list[list[dict]] = []
    for event in events:
        best_idx = -1
        best_score = 0.0
        for idx, cluster in enumerate(clusters):
            centroid_terms = list(dict.fromkeys(term for item in cluster for term in item["terms"]))
            lexical_score = _jaccard(event["terms"], centroid_terms)
            same_topic = event["topic_id"] in {item["topic_id"] for item in cluster}
            semantic_score = _cosine_vectors(
                event.get("semantic_vector"),
                _average_vectors([item.get("semantic_vector") or [] for item in cluster]),
            )
            score = max(lexical_score, 0.9 if same_topic else 0.0, semantic_score)
            accepted = same_topic or lexical_score >= 0.12 or semantic_score >= 0.42
            if accepted and score > best_score:
                best_idx, best_score = idx, score
        if best_idx >= 0:
            clusters[best_idx].append(event)
        else:
            clusters.append([event])

    df = Counter()
    for cluster in clusters:
        for term in set(term for event in cluster for term in event["terms"]):
            df[term] += 1

    topic_clusters = []
    cluster_count = max(1, len(clusters))
    for idx, cluster in enumerate(clusters):
        tf = Counter(term for event in cluster for term in event["terms"])
        scored_terms = []
        for term, count in tf.items():
            idf = math.log((1 + cluster_count) / (1 + df[term])) + 1
            scored_terms.append((count * idf, term))
        scored_terms.sort(reverse=True)
        keywords = [term for _, term in scored_terms[:8]]
        latest = sorted(cluster, key=lambda item: item["created_at"])[-1]
        domain_counts = Counter(event["domain"] for event in cluster)
        domain = domain_counts.most_common(1)[0][0] if domain_counts else "general"
        label = latest["topic_label"] or (keywords[0] if keywords else f"Topic {idx + 1}")
        topic_clusters.append(
            TopicCluster(
                id=f"cluster:{idx + 1}",
                label=str(label)[:50],
                domain=domain,
                event_ids=[event["id"] for event in cluster],
                keywords=keywords,
                score=sum(event["turns"] for event in cluster) + len(cluster),
                source_topic_ids=sorted(
                    set(
                        topic_id
                        for event in cluster
                        for topic_id in [
                            event.get("original_topic_id") or event.get("topic_id"),
                            event.get("topic_id"),
                        ]
                        if topic_id
                    )
                ),
            )
        )
    return sorted(topic_clusters, key=lambda item: item.score, reverse=True)


def _time_proximity_score(left: dict, right: dict) -> float:
    days = abs(right["created_at"] - left["created_at"]) / (24 * 3600 * 1000)
    if days <= 1:
        return 1.0
    if days <= 7:
        return 0.7
    if days <= 30:
        return 0.35
    return 0.1


def _edge_type(left: dict, right: dict, shared: list[str], score_parts: dict[str, float]) -> str:
    if left["topic_id"] == right["topic_id"]:
        return "continuation"
    if left["domain"] in {"math", "ai"} and right["domain"] in {"finance", "enterprise", "industry"}:
        return "tool"
    if right["intent"] == "decision" or left["intent"] == "decision":
        return "decision"
    if score_parts.get("kb", 0) > 0:
        return "evidence"
    if left["domain"] == right["domain"]:
        return "extension"
    if score_parts.get("semantic", 0) >= 0.52:
        return "bridge"
    if shared:
        return "bridge"
    return "association"


def _build_edges(events: list[dict]) -> list[dict]:
    edges = []
    for i, left in enumerate(events):
        for right in events[i + 1 :]:
            if len(edges) > 160:
                break
            keyword_overlap = _jaccard(left["terms"], right["terms"])
            shared_terms = sorted(set(left["terms"]) & set(right["terms"]))[:8]
            time_score = _time_proximity_score(left, right)
            same_domain = 1.0 if left["domain"] == right["domain"] else 0.0
            same_intent = 1.0 if left["intent"] == right["intent"] else 0.0
            same_kb = 1.0 if set(left["related_kb_ids"]) & set(right["related_kb_ids"]) else 0.0
            same_topic = 1.0 if left["topic_id"] == right["topic_id"] else 0.0
            semantic_score = _cosine_vectors(left.get("semantic_vector"), right.get("semantic_vector"))
            score_parts = {
                "keywords": round(keyword_overlap, 3),
                "time": round(time_score, 3),
                "domain": same_domain,
                "intent": same_intent,
                "kb": same_kb,
                "topic": same_topic,
                "semantic": round(semantic_score, 3),
            }
            score = (
                keyword_overlap * 0.25
                + time_score * 0.15
                + same_kb * 0.15
                + same_intent * 0.1
                + max(same_domain, same_topic) * 0.2
                + semantic_score * 0.15
                + (0.15 if left["domain"] in {"math", "ai"} and right["domain"] in {"finance", "enterprise", "industry"} else 0.0)
            )
            if score < 0.32 and same_topic <= 0 and same_kb <= 0 and semantic_score < 0.45:
                continue
            relation = _edge_type(left, right, shared_terms, score_parts)
            edges.append(
                {
                    "id": f"{left['id']}->{right['id']}",
                    "source_event_id": left["id"],
                    "target_event_id": right["id"],
                    "source_topic_id": left["topic_id"],
                    "target_topic_id": right["topic_id"],
                    "type": relation,
                    "weight": round(score, 3),
                    "shared_signals": shared_terms,
                    "evidence_event_ids": [left["id"], right["id"]],
                    "reason": _edge_reason(left, right, relation, shared_terms, score_parts),
                    "score_parts": score_parts,
                }
            )
    return sorted(edges, key=lambda item: item["weight"], reverse=True)[:100]


def _edge_reason(left: dict, right: dict, relation: str, shared_terms: list[str], score_parts: dict[str, float]) -> str:
    relation_labels = {
        "continuation": "两个备忘录属于同一归一化主题，表示持续关注。",
        "tool": "前一主题更像方法或工具，后一主题更像应用对象或决策场景。",
        "decision": "两个主题都指向同一类决策或行动问题。",
        "evidence": "两个备忘录关联到相同知识库或文档来源。",
        "extension": "两个备忘录处于同一领域，表示主题扩展。",
        "bridge": "两个备忘录共享关键词或实体，形成跨主题桥接。",
        "association": "两个备忘录在时间与语义信号上接近。",
    }
    shared_text = f" 共享线索：{', '.join(shared_terms[:5])}。" if shared_terms else ""
    semantic_text = " 语义向量相似度较高。" if score_parts.get("semantic", 0) >= 0.52 else ""
    return f"{relation_labels.get(relation, relation_labels['association'])}{shared_text}{semantic_text}"


def _build_summary(events: list[dict], clusters: list[TopicCluster], edges: list[dict]) -> dict:
    if not events:
        return {
            "headline": "暂无足够备忘录形成思维画像。",
            "trajectory": "",
            "next_direction": "",
            "focus_domains": [],
        }
    domain_counts = Counter(event["domain"] for event in events)
    focus_domains = [
        {"id": domain, "label": DOMAIN_LABELS.get(domain, domain), "count": count}
        for domain, count in domain_counts.most_common(5)
    ]
    top_labels = [cluster.label for cluster in clusters[:4]]
    if len(top_labels) >= 2:
        headline = f"你近期的思考集中在{'、'.join(top_labels[:3])}，并开始形成跨主题关联。"
    else:
        headline = f"你近期主要关注{top_labels[0] if top_labels else '备忘录主题'}。"
    strongest = edges[0] if edges else None
    trajectory = "主题之间的关联还较弱，建议继续保存更多对话以形成路径。"
    if strongest:
        left = next((event for event in events if event["id"] == strongest["source_event_id"]), None)
        right = next((event for event in events if event["id"] == strongest["target_event_id"]), None)
        if left and right:
            trajectory = f"最明显的路径是从“{left['title']}”走向“{right['title']}”，关系为 {strongest['type']}。"
    next_direction = "可继续围绕高频主题提出更具体的问题，系统会逐步形成更可靠的趋势预测。"
    if len(focus_domains) >= 2:
        next_direction = f"可继续探索{focus_domains[0]['label']}与{focus_domains[1]['label']}之间的应用关系。"
    return {
        "headline": headline,
        "trajectory": trajectory,
        "next_direction": next_direction,
        "focus_domains": focus_domains,
    }


def _build_predictions(events: list[dict], clusters: list[TopicCluster], edges: list[dict]) -> list[dict]:
    predictions = []
    top_clusters = clusters[:4]
    if len(top_clusters) >= 2:
        first, second = top_clusters[0], top_clusters[1]
        predictions.append(
            {
                "question": f"{first.label} 和 {second.label} 之间是否存在可落地的应用关系？",
                "reason": "这两个主题在近期备忘录中活跃度较高，适合进一步追问它们的连接方式。",
                "evidence_event_ids": list(dict.fromkeys([*first.event_ids[:2], *second.event_ids[:2]])),
                "topics": [first.label, second.label],
            }
        )
    tool_edges = [edge for edge in edges if edge["type"] in {"tool", "decision"}]
    if tool_edges:
        edge = tool_edges[0]
        left = next((event for event in events if event["id"] == edge["source_event_id"]), None)
        right = next((event for event in events if event["id"] == edge["target_event_id"]), None)
        if left and right:
            predictions.append(
                {
                    "question": f"如何把“{left['topic_label']}”用于解决“{right['topic_label']}”中的具体问题？",
                    "reason": edge["reason"],
                    "evidence_event_ids": edge["evidence_event_ids"],
                    "topics": [left["topic_label"], right["topic_label"]],
                }
            )
    for cluster in top_clusters[:2]:
        predictions.append(
            {
                "question": f"围绕“{cluster.label}”，下一步最值得验证的风险或机会是什么？",
                "reason": "该主题在备忘录中出现频率较高，适合转化为下一轮可验证问题。",
                "evidence_event_ids": cluster.event_ids[:3],
                "topics": [cluster.label],
            }
        )
    return predictions[:5]


def _cluster_to_dict(cluster: TopicCluster, events_by_id: dict[str, dict]) -> dict:
    cluster_events = [events_by_id[event_id] for event_id in cluster.event_ids if event_id in events_by_id]
    return {
        "id": cluster.id,
        "label": cluster.label,
        "domain": cluster.domain,
        "domain_label": DOMAIN_LABELS.get(cluster.domain, cluster.domain),
        "event_ids": cluster.event_ids,
        "source_topic_ids": cluster.source_topic_ids,
        "keywords": cluster.keywords,
        "memo_count": len(cluster.event_ids),
        "turn_count": sum(event.get("turns", 1) for event in cluster_events),
        "first_seen": min((event["created_at"] for event in cluster_events), default=0),
        "last_seen": max((event["created_at"] for event in cluster_events), default=0),
        "activity_score": round(cluster.score, 3),
    }


def _cluster_vector(cluster: TopicCluster, events_by_id: dict[str, dict]) -> list[float]:
    return _average_vectors(
        [
            events_by_id[event_id].get("semantic_vector") or []
            for event_id in cluster.event_ids
            if event_id in events_by_id
        ]
    )


def _build_topic_merge_suggestions(clusters: list[TopicCluster], events_by_id: dict[str, dict]) -> list[dict]:
    suggestions = []
    for idx, left in enumerate(clusters):
        left_vector = _cluster_vector(left, events_by_id)
        for right in clusters[idx + 1 :]:
            if set(left.source_topic_ids) & set(right.source_topic_ids):
                continue
            semantic_score = _cosine_vectors(left_vector, _cluster_vector(right, events_by_id))
            keyword_score = _jaccard(left.keywords, right.keywords)
            confidence = max(semantic_score, keyword_score)
            if confidence < TOPIC_MERGE_SUGGESTION_THRESHOLD:
                continue
            shared_signals = sorted(set(left.keywords) & set(right.keywords))[:8]
            target = left if left.score >= right.score else right
            source = right if target is left else left
            reason_parts = []
            if semantic_score >= TOPIC_MERGE_SUGGESTION_THRESHOLD:
                reason_parts.append(f"semantic={semantic_score:.2f}")
            if keyword_score >= 0.12:
                reason_parts.append(f"keywords={keyword_score:.2f}")
            suggestions.append(
                {
                    "source_topic_ids": source.source_topic_ids,
                    "target_topic_id": target.source_topic_ids[0] if target.source_topic_ids else target.id,
                    "target_label": target.label,
                    "source_label": source.label,
                    "semantic_score": round(semantic_score, 3),
                    "keyword_score": round(keyword_score, 3),
                    "confidence": round(confidence, 3),
                    "shared_signals": shared_signals,
                    "evidence_event_ids": list(dict.fromkeys([*source.event_ids[:2], *target.event_ids[:2]])),
                    "reason": " / ".join(reason_parts) or "similar topic signals",
                }
            )
    return sorted(suggestions, key=lambda item: item["confidence"], reverse=True)[:20]


def build_profile_snapshot(user_id: str) -> dict:
    started_at = time.time()
    memories = _fetch_profile_memories(user_id)
    topic_merges = _load_topic_merges(user_id)
    events = _apply_topic_merges(_build_events(memories), topic_merges)
    clusters = _cluster_events(events)
    events_by_id = {event["id"]: event for event in events}
    clusters = _stabilize_topic_clusters(user_id, clusters, events_by_id)
    edges = _build_edges(events)
    topics = [_cluster_to_dict(cluster, events_by_id) for cluster in clusters]
    merge_suggestions = _build_topic_merge_suggestions(clusters, events_by_id)
    snapshot = {
        "version": PROFILE_VERSION,
        "status": "ready" if events else "empty",
        "semantic_model": TOPIC_VECTOR_MODEL,
        "topic_cache": {
            "version": TOPIC_CACHE_VERSION,
            "semantic_model": TOPIC_VECTOR_MODEL,
            "topic_count": len(clusters),
        },
        "topic_merges": topic_merges,
        "topic_merge_suggestions": merge_suggestions,
        "generated_at": int(time.time()),
        "duration_ms": int((time.time() - started_at) * 1000),
        "memory_count": len(memories),
        "event_count": len(events),
        "summary": _build_summary(events, clusters, edges),
        "events": [_public_event(event) for event in events],
        "topics": topics,
        "edges": edges,
        "predictions": _build_predictions(events, clusters, edges),
        "algorithm_notes": [
            {
                "title": "BERTopic: Neural topic modeling with a class-based TF-IDF procedure",
                "authors": "Maarten Grootendorst",
                "borrowed": "借鉴 embedding 聚类后再用 c-TF-IDF 生成可读主题词的思想；当前实现使用可缓存语义签名向量参与主题合并，保留后续接入 BGE-M3 embedding 的适配层。",
            },
            {
                "title": "The Dynamic Embedded Topic Model",
                "authors": "Adji B. Dieng, Francisco J. R. Ruiz, David M. Blei",
                "borrowed": "借鉴主题随时间形成轨迹的思想，用时间顺序和主题泳道表达学习路径。",
            },
            {
                "title": "Explainable Reasoning over Knowledge Graphs for Recommendation",
                "authors": "Xiang Wang, Dingxian Wang, Canran Xu, Xiangnan He, Yixin Cao, Tat-Seng Chua",
                "borrowed": "借鉴路径可解释推荐思想，每条连线和推荐问题都带证据事件。",
            },
            {
                "title": "GraphRAG-Induced Dual Knowledge Structure Graphs for Personalized Learning Path Recommendation",
                "authors": "Xinghe Cheng, Zihan Zhang, Jiapu Wang, Liangda Fang, Chaobo He, Quanlong Guan, Shirui Pan, Weiqi Luo",
                "borrowed": "借鉴先后路径和相似关系双结构图思想，同时保留时间顺序和主题相似关系。",
            },
        ],
    }
    _json_set(_snapshot_key(user_id), snapshot)
    REDIS_CONN.set(_status_key(user_id), "ready", exp=PROFILE_CACHE_TTL_SECONDS)
    return snapshot


async def _background_build(user_id: str) -> None:
    try:
        REDIS_CONN.set(_status_key(user_id), "building", exp=PROFILE_BUILD_LOCK_TTL_SECONDS)
        await thread_pool_exec(build_profile_snapshot, user_id)
    except Exception as exc:
        logging.exception("Memo thought profile build failed user=%s err=%s", user_id, exc)
        REDIS_CONN.set(_status_key(user_id), f"error:{exc}", exp=PROFILE_BUILD_LOCK_TTL_SECONDS)
    finally:
        try:
            if getattr(REDIS_CONN, "REDIS", None):
                REDIS_CONN.REDIS.delete(_lock_key(user_id))
        except Exception as exc:
            logging.warning("Memo thought profile lock release failed user=%s err=%s", user_id, exc)


def _start_background_build(user_id: str, force: bool = False) -> bool:
    lock_key = _lock_key(user_id)
    if not force and REDIS_CONN.exist(lock_key):
        return False
    REDIS_CONN.set(lock_key, str(time.time()), exp=PROFILE_BUILD_LOCK_TTL_SECONDS)
    try:
        loop = asyncio.get_running_loop()
        loop.create_task(_background_build(user_id))
        return True
    except RuntimeError:
        build_profile_snapshot(user_id)
        return True


async def get_profile_snapshot(user_id: str, refresh: bool = False) -> dict:
    snapshot = None if refresh else _json_get(_snapshot_key(user_id))
    now = int(time.time())
    if snapshot:
        snapshot["stale"] = now - int(snapshot.get("generated_at") or 0) > PROFILE_STALE_SECONDS
        if snapshot["stale"]:
            _start_background_build(user_id)
        return snapshot

    started = _start_background_build(user_id, force=refresh)
    status = REDIS_CONN.get(_status_key(user_id)) or ("building" if started else "pending")
    return {
        "version": PROFILE_VERSION,
        "status": "building" if str(status).startswith("building") else "pending",
        "generated_at": 0,
        "stale": True,
        "memory_count": 0,
        "event_count": 0,
        "summary": {
            "headline": "正在分析已保存备忘录。",
            "trajectory": "",
            "next_direction": "",
            "focus_domains": [],
        },
        "events": [],
        "topics": [],
        "topic_merges": _empty_topic_merges(),
        "topic_merge_suggestions": [],
        "edges": [],
        "predictions": [],
        "algorithm_notes": [],
    }
