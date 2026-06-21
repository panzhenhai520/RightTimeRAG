#!/usr/bin/env python3
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

import argparse
import importlib.util
import json
import math
import re
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


REPORT_NAME = "memo_topic_model_evaluation.md"
SAMPLES_NAME = "memo_topic_samples.sanitized.json"
RESULT_NAME = "memo_topic_model_evaluation.json"

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "about",
    "from",
    "this",
    "that",
    "user",
    "assistant",
    "demo",
    "seed",
    "what",
    "which",
    "how",
    "why",
    "用户",
    "问题",
    "关于",
    "什么",
    "哪些",
    "如何",
    "是否",
    "可以",
    "需要",
    "进行",
    "分析",
    "总结",
    "你好",
    "助理",
    "根据",
    "提供",
    "知识库",
    "内容",
    "帮助",
}


@dataclass(frozen=True)
class TopicSample:
    id: str
    created_at: int
    topic_id: str
    topic_label: str
    domain: str
    intent: str
    turns: int
    summary: str
    keywords: list[str]
    source_kind: str

    def text_for_model(self) -> str:
        return " ".join(
            part
            for part in [
                self.topic_label,
                self.domain,
                self.intent,
                self.summary,
                " ".join(self.keywords),
            ]
            if part
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "created_at": self.created_at,
            "topic_id": self.topic_id,
            "topic_label": self.topic_label,
            "domain": self.domain,
            "intent": self.intent,
            "turns": self.turns,
            "summary": self.summary,
            "keywords": self.keywords,
            "source_kind": self.source_kind,
        }


def normalize_text(text: Any) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[_\s]+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fffa-z0-9\s.-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def tokenize(text: Any) -> list[str]:
    raw = str(text or "")
    matches = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9.-]{2,}", raw)
    terms: list[str] = []
    seen = set()
    for match in matches:
        term = normalize_text(match)
        if not term or term in STOP_WORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
    return terms


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _short_text(value: Any, limit: int = 320) -> str:
    text = re.sub(r"\s+", " ", str(value or "")).strip()
    return text[:limit].rstrip()


def _keywords(value: Any, fallback_text: str = "", limit: int = 12) -> list[str]:
    items = value if isinstance(value, list) else []
    terms = []
    seen = set()
    for item in [*items, *tokenize(fallback_text)]:
        term = normalize_text(item)
        if not term or term in STOP_WORDS or term in seen:
            continue
        seen.add(term)
        terms.append(term)
        if len(terms) >= limit:
            break
    return terms


def collect_sanitized_samples(payload: Any, limit: int = 500) -> list[TopicSample]:
    """Extract non-sensitive memo topic samples from a profile snapshot or sample list.

    The output intentionally excludes evidence snippets, raw message content,
    semantic vectors, and internal process fields. It keeps only compact summary
    text and keywords that are sufficient for offline topic-model comparison.
    """
    if isinstance(payload, dict):
        raw_events = payload.get("events") or payload.get("samples") or []
    elif isinstance(payload, list):
        raw_events = payload
    else:
        raw_events = []

    samples: list[TopicSample] = []
    for index, event in enumerate(raw_events):
        if not isinstance(event, dict):
            continue
        title = _short_text(event.get("title") or event.get("topic_label") or event.get("display_name"), 160)
        summary = _short_text(event.get("summary") or event.get("description") or title, 320)
        topic_label = _short_text(event.get("topic_label") or title or f"Topic {index + 1}", 80)
        keywords = _keywords(event.get("keywords"), " ".join([topic_label, summary]), limit=12)
        sample = TopicSample(
            id=str(event.get("id") or event.get("memory_id") or f"sample-{index + 1}"),
            created_at=_to_int(event.get("created_at") or event.get("create_time") or 0),
            topic_id=str(event.get("topic_id") or ""),
            topic_label=topic_label,
            domain=str(event.get("domain") or "general"),
            intent=str(event.get("intent") or "general"),
            turns=max(1, _to_int(event.get("turns") or event.get("message_count") or 1, 1)),
            summary=summary,
            keywords=keywords,
            source_kind=str(event.get("source_kind") or "unknown"),
        )
        samples.append(sample)
        if len(samples) >= limit:
            break
    return samples


def _jaccard(left: list[str], right: list[str]) -> float:
    left_set = set(left)
    right_set = set(right)
    if not left_set or not right_set:
        return 0.0
    return len(left_set & right_set) / len(left_set | right_set)


def evaluate_lightweight_ctfidf(samples: list[TopicSample]) -> dict[str, Any]:
    started_at = time.time()
    clusters: list[list[TopicSample]] = []
    cluster_terms: list[list[str]] = []

    for sample in sorted(samples, key=lambda item: item.created_at):
        terms = _keywords(sample.keywords, sample.text_for_model(), limit=20)
        best_index = -1
        best_score = 0.0
        for index, existing_terms in enumerate(cluster_terms):
            same_topic = sample.topic_id and any(item.topic_id == sample.topic_id for item in clusters[index])
            score = max(_jaccard(terms, existing_terms), 0.9 if same_topic else 0.0)
            if score >= 0.14 and score > best_score:
                best_index = index
                best_score = score
        if best_index >= 0:
            clusters[best_index].append(sample)
            cluster_terms[best_index] = list(dict.fromkeys([*cluster_terms[best_index], *terms]))
        else:
            clusters.append([sample])
            cluster_terms.append(terms)

    df = Counter()
    for terms in cluster_terms:
        for term in set(terms):
            df[term] += 1
    cluster_count = max(1, len(clusters))
    topic_rows = []
    for index, cluster in enumerate(clusters):
        tf = Counter(term for sample in cluster for term in _keywords(sample.keywords, sample.text_for_model(), limit=20))
        scored = []
        for term, count in tf.items():
            idf = math.log((1 + cluster_count) / (1 + df[term])) + 1
            scored.append((count * idf, term))
        scored.sort(reverse=True)
        latest = sorted(cluster, key=lambda item: item.created_at)[-1]
        topic_rows.append(
            {
                "id": f"lightweight:{index + 1}",
                "label": latest.topic_label or (scored[0][1] if scored else f"Topic {index + 1}"),
                "sample_count": len(cluster),
                "turn_count": sum(sample.turns for sample in cluster),
                "keywords": [term for _, term in scored[:8]],
                "domain_counts": dict(Counter(sample.domain for sample in cluster)),
                "first_seen": min((sample.created_at for sample in cluster), default=0),
                "last_seen": max((sample.created_at for sample in cluster), default=0),
            }
        )
    topic_rows.sort(key=lambda item: (item["turn_count"], item["sample_count"]), reverse=True)
    return {
        "status": "ok",
        "sample_count": len(samples),
        "topic_count": len(topic_rows),
        "duration_ms": int((time.time() - started_at) * 1000),
        "topics": topic_rows,
        "notes": "Greedy lexical/canonical-topic clustering plus c-TF-IDF-readable keywords; mirrors the current production approach without raw content.",
    }


def _missing_modules(names: list[str]) -> list[str]:
    return [name for name in names if importlib.util.find_spec(name) is None]


def evaluate_bertopic(samples: list[TopicSample]) -> dict[str, Any]:
    started_at = time.time()
    missing = _missing_modules(["bertopic", "hdbscan"])
    if missing:
        return {
            "status": "missing_dependency",
            "missing": missing,
            "sample_count": len(samples),
            "duration_ms": int((time.time() - started_at) * 1000),
            "notes": "BERTopic is not installed in the production venv. Keep it in an isolated evaluation environment before considering production integration.",
        }
    if len(samples) < 8:
        return {
            "status": "skipped",
            "sample_count": len(samples),
            "duration_ms": int((time.time() - started_at) * 1000),
            "notes": "Too few samples for a meaningful BERTopic run. Use at least 30-50 sanitized memo samples.",
        }

    try:
        from bertopic import BERTopic
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer
        from sklearn.preprocessing import normalize

        docs = [sample.text_for_model() for sample in samples]
        vectors = TfidfVectorizer(max_features=2048, ngram_range=(1, 2)).fit_transform(docs)
        dims = max(2, min(32, vectors.shape[0] - 1, vectors.shape[1] - 1))
        embeddings = normalize(TruncatedSVD(n_components=dims, random_state=42).fit_transform(vectors))
        topic_model = BERTopic(
            embedding_model=None,
            min_topic_size=max(2, min(8, len(samples) // 5 or 2)),
            calculate_probabilities=False,
            verbose=False,
        )
        topics, _ = topic_model.fit_transform(docs, embeddings=embeddings)
        info = topic_model.get_topic_info()
        rows = []
        for row in info.to_dict("records"):
            topic_id = row.get("Topic")
            if topic_id == -1:
                continue
            words = [word for word, _ in topic_model.get_topic(topic_id)[:8]]
            rows.append(
                {
                    "id": f"bertopic:{topic_id}",
                    "label": row.get("Name") or " / ".join(words[:3]),
                    "sample_count": int(row.get("Count") or 0),
                    "keywords": words,
                }
            )
        return {
            "status": "ok",
            "sample_count": len(samples),
            "topic_count": len(set(topic for topic in topics if topic != -1)),
            "duration_ms": int((time.time() - started_at) * 1000),
            "topics": rows,
            "notes": "BERTopic ran with local TF-IDF/SVD embeddings to avoid downloading sentence-transformer models.",
        }
    except Exception as exc:  # noqa: BLE001 - evaluation must report and continue
        return {
            "status": "failed",
            "sample_count": len(samples),
            "duration_ms": int((time.time() - started_at) * 1000),
            "error": f"{exc.__class__.__name__}: {exc}",
            "notes": "BERTopic failed in this environment; keep evaluation isolated from production.",
        }


def evaluate_dynamic_topic_model(samples: list[TopicSample], lightweight_result: dict[str, Any]) -> dict[str, Any]:
    if not samples:
        return {
            "status": "empty",
            "sample_count": 0,
            "notes": "No memo samples available.",
        }

    buckets: dict[str, Counter] = defaultdict(Counter)
    for sample in samples:
        ts = sample.created_at / 1000 if sample.created_at > 10_000_000_000 else sample.created_at
        if ts <= 0:
            bucket = "unknown"
        else:
            dt = datetime.fromtimestamp(ts, tz=timezone.utc)
            year, week, _ = dt.isocalendar()
            bucket = f"{year}-W{week:02d}"
        label = sample.topic_label or (sample.keywords[0] if sample.keywords else "memo")
        buckets[bucket][label] += sample.turns

    ordered_buckets = [
        {
            "bucket": bucket,
            "top_topics": [{"label": label, "score": score} for label, score in counter.most_common(5)],
        }
        for bucket, counter in sorted(buckets.items())
    ]
    dominant_sequence = [row["top_topics"][0]["label"] for row in ordered_buckets if row["top_topics"]]
    shifts = sum(1 for idx in range(1, len(dominant_sequence)) if dominant_sequence[idx] != dominant_sequence[idx - 1])
    status = "pilot_ready" if len(samples) >= 50 and len(ordered_buckets) >= 4 else "insufficient_samples"
    return {
        "status": status,
        "sample_count": len(samples),
        "bucket_count": len(ordered_buckets),
        "topic_count": lightweight_result.get("topic_count", 0),
        "dominant_topic_shifts": shifts,
        "buckets": ordered_buckets,
        "notes": (
            "Dynamic topic modeling becomes useful when there are enough samples across time. "
            "For this product, the first production step should remain a cached temporal trajectory over memo topics; "
            "full Dynamic Embedded Topic Model training is not justified until sample volume is much larger."
        ),
    }


def build_decision_summary(lightweight: dict[str, Any], bertopic: dict[str, Any], dynamic: dict[str, Any]) -> dict[str, Any]:
    sample_count = int(lightweight.get("sample_count") or 0)
    recommendation = "continue_current_algorithm"
    if bertopic.get("status") == "ok" and sample_count >= 80:
        recommendation = "pilot_bertopic_offline"
    if sample_count >= 200 and dynamic.get("bucket_count", 0) >= 8:
        recommendation = "pilot_dynamic_topic_model"
    return {
        "recommendation": recommendation,
        "rationale": [
            "Current algorithm already uses canonical-topic rules, cached embeddings, semantic similarity, and c-TF-IDF-readable labels.",
            "BERTopic can improve unsupervised topic discovery, but needs additional dependencies and enough samples to be stable.",
            "Dynamic topic models are valuable for longitudinal learning-path analysis, but require substantially more time-distributed samples.",
        ],
    }


def _markdown_table(rows: list[list[str]]) -> str:
    if not rows:
        return ""
    head = "| " + " | ".join(rows[0]) + " |"
    sep = "| " + " | ".join(["---"] * len(rows[0])) + " |"
    body = ["| " + " | ".join(row) + " |" for row in rows[1:]]
    return "\n".join([head, sep, *body])


def build_report(result: dict[str, Any]) -> str:
    lightweight = result["lightweight_ctfidf"]
    bertopic = result["bertopic"]
    dynamic = result["dynamic_topic"]
    decision = result["decision"]
    comparison_rows = [
        ["方案", "状态", "资源需求", "准确性收益", "维护成本", "建议"],
        [
            "当前轻量算法",
            lightweight.get("status", ""),
            "低；复用现有 embedding 和 Redis 缓存",
            "稳定，适合小样本和可解释路径",
            "低",
            "继续作为线上默认",
        ],
        [
            "BERTopic",
            bertopic.get("status", ""),
            "中到高；需要 bertopic/hdbscan，可选 sentence-transformers",
            "样本足够时主题发现更强，小样本可能不稳定",
            "中",
            "先离线试点，不进生产",
        ],
        [
            "动态主题模型",
            dynamic.get("status", ""),
            "高；需要较多跨时间样本和训练/缓存策略",
            "适合长期学习路径变化分析",
            "高",
            "样本规模足够后再评估",
        ],
    ]
    top_topics = lightweight.get("topics", [])[:8]
    topic_rows = [["主题", "样本数", "轮次", "关键词"]]
    for topic in top_topics:
        topic_rows.append(
            [
                str(topic.get("label", "")),
                str(topic.get("sample_count", 0)),
                str(topic.get("turn_count", 0)),
                ", ".join(topic.get("keywords", [])[:6]),
            ]
        )

    return "\n\n".join(
        [
            "# Memo Topic Model Evaluation",
            f"- Generated at: `{result['generated_at']}`",
            f"- Sanitized sample count: `{result['sample_count']}`",
            f"- Recommendation: `{decision['recommendation']}`",
            "## Comparison",
            _markdown_table(comparison_rows),
            "## Current Lightweight Topics",
            _markdown_table(topic_rows),
            "## BERTopic Evaluation",
            f"- Status: `{bertopic.get('status')}`",
            f"- Missing dependencies: `{', '.join(bertopic.get('missing', [])) or 'none'}`",
            f"- Notes: {bertopic.get('notes', '')}",
            "## Dynamic Topic Model Evaluation",
            f"- Status: `{dynamic.get('status')}`",
            f"- Buckets: `{dynamic.get('bucket_count', 0)}`",
            f"- Dominant topic shifts: `{dynamic.get('dominant_topic_shifts', 0)}`",
            f"- Notes: {dynamic.get('notes', '')}",
            "## Decision Rationale",
            "\n".join(f"- {item}" for item in decision["rationale"]),
            "## Boundary",
            "- This report is offline-only.",
            "- It excludes raw evidence snippets, raw messages, and semantic vectors.",
            "- It does not add BERTopic or dynamic topic-model dependencies to production.",
        ]
    )


def evaluate_payload(payload: Any, sample_limit: int = 500) -> dict[str, Any]:
    samples = collect_sanitized_samples(payload, limit=sample_limit)
    lightweight = evaluate_lightweight_ctfidf(samples)
    bertopic = evaluate_bertopic(samples)
    dynamic = evaluate_dynamic_topic_model(samples, lightweight)
    decision = build_decision_summary(lightweight, bertopic, dynamic)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "sample_count": len(samples),
        "samples": [sample.to_dict() for sample in samples],
        "lightweight_ctfidf": lightweight,
        "bertopic": bertopic,
        "dynamic_topic": dynamic,
        "decision": decision,
    }


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, value: Any) -> None:
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Evaluate memo topic models offline with sanitized samples.")
    parser.add_argument("--profile-json", required=True, help="Path to a memo profile snapshot or sanitized sample JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory where sanitized samples and reports will be written.")
    parser.add_argument("--sample-limit", type=int, default=500, help="Maximum number of memo samples to evaluate.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    input_path = Path(args.profile_json)
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    result = evaluate_payload(read_json(input_path), sample_limit=args.sample_limit)
    write_json(output_dir / SAMPLES_NAME, result["samples"])
    write_json(output_dir / RESULT_NAME, {key: value for key, value in result.items() if key != "samples"})
    (output_dir / REPORT_NAME).write_text(build_report(result), encoding="utf-8")

    print(f"Wrote sanitized samples: {output_dir / SAMPLES_NAME}")
    print(f"Wrote evaluation result: {output_dir / RESULT_NAME}")
    print(f"Wrote report: {output_dir / REPORT_NAME}")
    print(f"Recommendation: {result['decision']['recommendation']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
