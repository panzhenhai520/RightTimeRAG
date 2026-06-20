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

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


MemoLanguage = Literal["zh", "en", "mixed", "unknown"]

MEMO_STRUCTURED_SUMMARY_VERSION = "v1"
MEMO_TITLE_MAX_CHARS = 36
MEMO_FACT_MAX_CHARS = 280
MEMO_PROCESS_BLOCK_PATTERN = re.compile(r"<(?:retrieving|think)>[\s\S]*?</(?:retrieving|think)>", re.I)
MEMO_PROCESS_TAG_PATTERN = re.compile(r"</?(?:retrieving|think)>", re.I)
MEMO_ERROR_MARKERS = (
    "ERROR:",
    "CONNECTION_ERROR",
    "INVALID_REQUEST",
    "Traceback",
    "layer-slice token span exceeds context",
    "kv payload staging failed",
)
MEMO_TITLE_PREFIX_PATTERN = re.compile(
    r"^(我们注意到用户的问题是关于|我们注意到|我注意到|用户的问题是关于|这个问题是关于|"
    r"The user asks about|This question is about)\s*[:：，,]*\s*",
    re.I,
)
MEMO_ROLE_PREFIX_PATTERN = re.compile(r"^(user|assistant|human|ai|用户|助手)\s*[:：]\s*", re.I)


class MemoEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="")
    label: str = Field(default="unknown")
    normalized: str | None = Field(default=None)


class MemoAmount(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="")
    normalized: str | None = Field(default=None)


class MemoFact(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="")
    source_message_ids: list[str] = Field(default_factory=list)


class MemoStructuredSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    version: str = Field(default=MEMO_STRUCTURED_SUMMARY_VERSION)
    display_title: str = Field(default="")
    canonical_topic_candidate: str = Field(default="")
    aliases: list[str] = Field(default_factory=list)
    language: MemoLanguage = Field(default="unknown")
    entities: list[MemoEntity] = Field(default_factory=list)
    dates: list[str] = Field(default_factory=list)
    amounts: list[MemoAmount] = Field(default_factory=list)
    facts: list[MemoFact] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    source_message_ids: list[str] = Field(default_factory=list)
    related_kb_ids: list[str] = Field(default_factory=list)

    @field_validator(
        "aliases",
        "dates",
        "open_questions",
        "source_message_ids",
        "related_kb_ids",
        mode="before",
    )
    @classmethod
    def _normalize_string_list(cls, value: Any) -> list[str]:
        if value is None:
            return []
        if isinstance(value, (str, int, float)):
            value = [value]
        if not isinstance(value, list):
            return []
        normalized = []
        seen = set()
        for item in value:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            normalized.append(text)
        return normalized

    @field_validator("display_title", "canonical_topic_candidate", mode="before")
    @classmethod
    def _clean_short_title(cls, value: Any) -> str:
        return sanitize_memo_title(str(value or ""))


def sanitize_memo_text(value: Any) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        value = str(value)

    text = MEMO_PROCESS_BLOCK_PATTERN.sub("", value)
    text = MEMO_PROCESS_TAG_PATTERN.sub("", text)
    lines = []
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            if lines and lines[-1] != "":
                lines.append("")
            continue
        lower = line.lower()
        if any(marker.lower() in lower for marker in MEMO_ERROR_MARKERS):
            continue
        lines.append(line)
    return "\n".join(lines).strip()


def sanitize_memo_title(value: Any) -> str:
    title = sanitize_memo_text(value)
    title = MEMO_ROLE_PREFIX_PATTERN.sub("", title).strip()
    title = MEMO_TITLE_PREFIX_PATTERN.sub("", title).strip()
    title = re.sub(r"^[#\-\s\"'“”‘’]+|[#\-\s\"'“”‘’。.!！?？]+$", "", title).strip()
    title = re.sub(r"\s+", " ", title)
    if any(marker.lower() in title.lower() for marker in MEMO_ERROR_MARKERS):
        return ""
    if len(title) <= MEMO_TITLE_MAX_CHARS:
        return title
    return title[:MEMO_TITLE_MAX_CHARS].rstrip()


def _infer_language(text: str) -> MemoLanguage:
    has_zh = bool(re.search(r"[\u4e00-\u9fff]", text or ""))
    has_en = bool(re.search(r"[a-zA-Z]", text or ""))
    if has_zh and has_en:
        return "mixed"
    if has_zh:
        return "zh"
    if has_en:
        return "en"
    return "unknown"


def _candidate_lines(text: str) -> list[str]:
    candidates = []
    for raw_line in sanitize_memo_text(text).splitlines():
        line = MEMO_ROLE_PREFIX_PATTERN.sub("", raw_line).strip()
        if not line:
            continue
        candidates.append(line)
    return candidates


def _first_user_like_line(text: str) -> str:
    for raw_line in sanitize_memo_text(text).splitlines():
        line = raw_line.strip()
        if re.match(r"^(user|human|用户)\s*[:：]", line, re.I):
            title = sanitize_memo_title(MEMO_ROLE_PREFIX_PATTERN.sub("", line))
            if title:
                return title
    for line in _candidate_lines(text):
        title = sanitize_memo_title(line)
        if title:
            return title
    return "Chat memo"


def _extract_dates(text: str) -> list[str]:
    patterns = (
        r"\b(?:19|20)\d{2}(?:[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)?\b",
        r"\b\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\s+(?:19|20)\d{2}\b",
    )
    dates = []
    seen = set()
    for pattern in patterns:
        for match in re.findall(pattern, text, re.I):
            value = str(match).strip()
            if value and value not in seen:
                seen.add(value)
                dates.append(value)
    return dates[:20]


def _extract_amounts(text: str) -> list[MemoAmount]:
    pattern = r"(?:HK\$|US\$|RMB|CNY|USD|HKD|\$)\s?[\d,.]+(?:\s?(?:million|billion|万|亿))?|[\d,.]+\s?(?:million|billion|万元|亿元|%|％)"
    amounts = []
    seen = set()
    for match in re.findall(pattern, text, re.I):
        value = str(match).strip()
        if value and value not in seen:
            seen.add(value)
            amounts.append(MemoAmount(text=value, normalized=value))
    return amounts[:20]


def _extract_entities(text: str) -> list[MemoEntity]:
    entities = []
    seen = set()
    patterns = (
        ("organization", r"\b[A-Z][A-Za-z0-9&.\-]*(?:\s+[A-Z][A-Za-z0-9&.\-]*){1,4}\b"),
        ("law", r"《[^》]{2,40}》"),
        ("law", r"\bCap\s+\d+[A-Z]?\b"),
        ("person_or_org", r"[\u4e00-\u9fff]{2,16}(?:公司|集团|银行|家族办公室|信托|条例|报告)"),
    )
    for label, pattern in patterns:
        for match in re.findall(pattern, text, re.I):
            value = str(match).strip()
            if not value or value in seen:
                continue
            seen.add(value)
            entities.append(MemoEntity(text=value, label=label, normalized=value))
            if len(entities) >= 30:
                return entities
    return entities


def _extract_facts(text: str, source_message_ids: list[str]) -> list[MemoFact]:
    facts = []
    for line in _candidate_lines(text):
        if line.endswith(("?", "？")):
            continue
        cleaned = re.sub(r"^\s*[-*•\d.、]+\s*", "", line).strip()
        if not cleaned or len(cleaned) < 8:
            continue
        if len(cleaned) > MEMO_FACT_MAX_CHARS:
            cleaned = cleaned[:MEMO_FACT_MAX_CHARS].rstrip() + "..."
        facts.append(MemoFact(text=cleaned, source_message_ids=source_message_ids))
        if len(facts) >= 8:
            break
    return facts


def _extract_open_questions(text: str) -> list[str]:
    questions = []
    seen = set()
    for line in _candidate_lines(text):
        if not line.endswith(("?", "？")):
            continue
        question = sanitize_memo_title(line)
        if question and question not in seen:
            seen.add(question)
            questions.append(question)
    return questions[:8]


def build_memo_structured_summary(
    transcript: str,
    *,
    display_title: str | None = None,
    source_message_ids: list[str | int] | None = None,
    related_kb_ids: list[str] | None = None,
    aliases: list[str] | None = None,
) -> MemoStructuredSummary:
    clean_text = sanitize_memo_text(transcript)
    source_ids = [str(message_id) for message_id in (source_message_ids or []) if str(message_id or "").strip()]
    title = sanitize_memo_title(display_title) or _first_user_like_line(clean_text)
    canonical_topic_candidate = sanitize_memo_title(title)

    return MemoStructuredSummary(
        display_title=title,
        canonical_topic_candidate=canonical_topic_candidate,
        aliases=aliases or [],
        language=_infer_language(clean_text),
        entities=_extract_entities(clean_text),
        dates=_extract_dates(clean_text),
        amounts=_extract_amounts(clean_text),
        facts=_extract_facts(clean_text, source_ids),
        open_questions=_extract_open_questions(clean_text),
        source_message_ids=source_ids,
        related_kb_ids=related_kb_ids or [],
    )


def memo_structured_summary_to_search_text(summary: MemoStructuredSummary) -> str:
    """Compact text for topic-first memo retrieval and downstream profiling."""
    parts = [
        summary.display_title,
        summary.canonical_topic_candidate,
        " ".join(summary.aliases),
        " ".join(entity.text for entity in summary.entities),
        " ".join(summary.dates),
        " ".join(amount.text for amount in summary.amounts),
        " ".join(fact.text for fact in summary.facts),
        " ".join(summary.open_questions),
    ]
    return "\n".join(part for part in parts if part).strip()


def format_memo_structured_summary_content(summary: MemoStructuredSummary) -> str:
    """Stable text representation stored as a searchable derived memory message."""
    lines = [
        f"Memo structured summary version: {summary.version}",
        f"Title: {summary.display_title}",
        f"Canonical topic: {summary.canonical_topic_candidate}",
        f"Language: {summary.language}",
    ]
    if summary.aliases:
        lines.append("Aliases: " + ", ".join(summary.aliases))
    if summary.entities:
        lines.append("Entities:")
        lines.extend(f"- {entity.text} ({entity.label})" for entity in summary.entities[:20])
    if summary.dates:
        lines.append("Dates: " + ", ".join(summary.dates))
    if summary.amounts:
        lines.append("Amounts: " + ", ".join(amount.text for amount in summary.amounts))
    if summary.facts:
        lines.append("Facts:")
        lines.extend(f"- {fact.text}" for fact in summary.facts[:8])
    if summary.open_questions:
        lines.append("Open questions:")
        lines.extend(f"- {question}" for question in summary.open_questions[:8])
    if summary.source_message_ids:
        lines.append("Source message IDs: " + ", ".join(summary.source_message_ids))
    if summary.related_kb_ids:
        lines.append("Related KB IDs: " + ", ".join(summary.related_kb_ids))
    return "\n".join(line for line in lines if line).strip()


def parse_memo_structured_summary_content(content: str | None) -> MemoStructuredSummary | None:
    text = sanitize_memo_text(content)
    if not text.startswith("Memo structured summary version:"):
        return None

    values: dict[str, Any] = {
        "version": MEMO_STRUCTURED_SUMMARY_VERSION,
        "display_title": "",
        "canonical_topic_candidate": "",
        "aliases": [],
        "language": "unknown",
        "entities": [],
        "dates": [],
        "amounts": [],
        "facts": [],
        "open_questions": [],
        "source_message_ids": [],
        "related_kb_ids": [],
    }
    section = ""
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("Memo structured summary version:"):
            values["version"] = line.split(":", 1)[1].strip() or MEMO_STRUCTURED_SUMMARY_VERSION
            section = ""
        elif line.startswith("Title:"):
            values["display_title"] = line.split(":", 1)[1].strip()
            section = ""
        elif line.startswith("Canonical topic:"):
            values["canonical_topic_candidate"] = line.split(":", 1)[1].strip()
            section = ""
        elif line.startswith("Language:"):
            language = line.split(":", 1)[1].strip()
            values["language"] = language if language in {"zh", "en", "mixed", "unknown"} else "unknown"
            section = ""
        elif line.startswith("Aliases:"):
            values["aliases"] = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            section = ""
        elif line == "Entities:":
            section = "entities"
        elif line.startswith("Dates:"):
            values["dates"] = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            section = ""
        elif line.startswith("Amounts:"):
            values["amounts"] = [
                MemoAmount(text=item.strip(), normalized=item.strip())
                for item in line.split(":", 1)[1].split(",")
                if item.strip()
            ]
            section = ""
        elif line == "Facts:":
            section = "facts"
        elif line == "Open questions:":
            section = "open_questions"
        elif line.startswith("Source message IDs:"):
            values["source_message_ids"] = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            section = ""
        elif line.startswith("Related KB IDs:"):
            values["related_kb_ids"] = [item.strip() for item in line.split(":", 1)[1].split(",") if item.strip()]
            section = ""
        elif line.startswith("- ") and section == "entities":
            body = line[2:].strip()
            match = re.match(r"(?P<text>.*)\s+\((?P<label>[^)]+)\)$", body)
            if match:
                values["entities"].append(
                    MemoEntity(text=match.group("text").strip(), label=match.group("label").strip())
                )
            elif body:
                values["entities"].append(MemoEntity(text=body))
        elif line.startswith("- ") and section == "facts":
            fact = line[2:].strip()
            if fact:
                values["facts"].append(MemoFact(text=fact, source_message_ids=values["source_message_ids"]))
        elif line.startswith("- ") and section == "open_questions":
            question = line[2:].strip()
            if question:
                values["open_questions"].append(question)

    if not values["display_title"] and not values["canonical_topic_candidate"]:
        return None
    if not values["canonical_topic_candidate"]:
        values["canonical_topic_candidate"] = values["display_title"]
    if not values["display_title"]:
        values["display_title"] = values["canonical_topic_candidate"]
    return MemoStructuredSummary(**values)
