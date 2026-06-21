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

import logging
import os
import re
import threading
from copy import deepcopy
from dataclasses import dataclass
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError


EvidenceType = Literal["title", "clause", "table", "definition", "fact", "summary", "unknown"]

STRUCTURED_EXTRACTION_CONFIG_KEY = "structured_extraction"
STRUCTURED_EXTRACTION_EXTRA_KEY = "structured"
MAX_CHUNKS_FOR_LLM_STRUCTURE = 24
MAX_CHARS_PER_CHUNK_FOR_LLM_STRUCTURE = 1400
INSTRUCTOR_DEFAULT_TIMEOUT_SECONDS = 120
INSTRUCTOR_CONCURRENCY = max(1, int(os.getenv("RAGFLOW_STRUCTURED_INSTRUCTOR_CONCURRENCY", "1") or "1"))
_INSTRUCTOR_SEMAPHORE = threading.BoundedSemaphore(INSTRUCTOR_CONCURRENCY)


@dataclass(frozen=True)
class InstructorRetryPolicy:
    context: Literal["online", "background"] = "online"
    max_retries: int = 0
    concurrency: int = INSTRUCTOR_CONCURRENCY


class ExtractedEntity(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(default="", description="Entity text as it appears in the document.")
    label: str = Field(default="unknown", description="Entity type, such as person, organization, date, amount, law, location.")
    normalized: str | None = Field(default=None, description="Optional normalized form.")


class EvidenceSpan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    chunk_id: str | None = Field(default=None)
    page: int | None = Field(default=None)
    start: int | None = Field(default=None)
    end: int | None = Field(default=None)
    quote: str = Field(default="", description="Short source quote or evidence text.")
    evidence_type: EvidenceType = Field(default="unknown")


class LegalClause(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clause_id: str = Field(default="", description="Clause or section number, for example 28 or Article 12.")
    title: str = Field(default="")
    jurisdiction: str | None = Field(default=None)
    source_span: EvidenceSpan | None = Field(default=None)


class TableSummary(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="")
    page: int | None = Field(default=None)
    key_columns: list[str] = Field(default_factory=list)
    summary: str = Field(default="")
    source_span: EvidenceSpan | None = Field(default=None)


class SectionNode(BaseModel):
    model_config = ConfigDict(extra="forbid")

    section_id: str = Field(default="")
    title: str = Field(default="")
    level: int = Field(default=1, ge=1, le=8)
    page_start: int | None = Field(default=None)
    page_end: int | None = Field(default=None)
    parent_id: str | None = Field(default=None)
    summary: str = Field(default="")


class DocumentStructure(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(default="")
    language: str = Field(default="unknown")
    sections: list[SectionNode] = Field(default_factory=list)
    legal_clauses: list[LegalClause] = Field(default_factory=list)
    tables: list[TableSummary] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    evidence_spans: list[EvidenceSpan] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)


def structured_extraction_enabled(parser_config: dict | None) -> bool:
    config = (parser_config or {}).get(STRUCTURED_EXTRACTION_CONFIG_KEY) or {}
    if not isinstance(config, dict):
        return False
    return str(config.get("enabled", "")).strip().lower() in {"1", "true", "yes", "on"}


def resolve_instructor_retry_policy(
    config: dict | None = None,
    *,
    context: Literal["online", "background"] = "online",
) -> InstructorRetryPolicy:
    """Resolve a bounded Instructor retry policy.

    Online request paths must not ask the LLM to repair structure because every
    reask expands latency and live KV pressure. Background parsing may retry
    once, but never more than once on the ds4-server path.
    """
    config = config or {}
    if context == "online":
        return InstructorRetryPolicy(context="online", max_retries=0)

    configured = config.get("max_retries")
    if configured is None:
        configured = 1
    try:
        retries = int(configured)
    except (TypeError, ValueError):
        retries = 1
    return InstructorRetryPolicy(context="background", max_retries=max(0, min(retries, 1)))


def classify_structured_extraction_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        errors = exc.errors()
        if any(error.get("type") == "missing" for error in errors):
            return "missing_field"
        if any(error.get("type") == "extra_forbidden" for error in errors):
            return "illegal_field"
        return "validation_error"
    name = exc.__class__.__name__.lower()
    text = str(exc).lower()
    if "json" in name or "json" in text or "decode" in text or "parse" in text:
        return "json_format_error"
    if "timeout" in name or "timeout" in text:
        return "timeout"
    return "runtime_error"


def _first_chunk_page(chunks: list[dict]) -> int | None:
    for chunk in chunks or []:
        page = _chunk_page(chunk)
        if page is not None:
            return page
    return None


def _chunk_text(chunk: dict) -> str:
    return str(chunk.get("content_with_weight") or chunk.get("text") or chunk.get("content") or "").strip()


def _chunk_page(chunk: dict) -> int | None:
    pages = chunk.get("page_num_int")
    if isinstance(pages, list) and pages:
        try:
            return int(pages[0])
        except (TypeError, ValueError):
            return None
    try:
        return int(chunk.get("page") or chunk.get("page_num"))
    except (TypeError, ValueError):
        return None


def _is_probable_title(text: str) -> bool:
    text = re.sub(r"\s+", " ", text or "").strip()
    if not text or len(text) > 120:
        return False
    if re.search(r"[。！？.!?]\s*$", text):
        return False
    return bool(re.search(r"^(chapter|section|article|part|division|\d+\.|第[一二三四五六七八九十百0-9]+[章节条部])", text, re.I))


def _extract_clause_title(text: str) -> tuple[str, str] | None:
    text = re.sub(r"\s+", " ", text or "").strip()
    patterns = (
        r"^(?P<id>\d+[A-Z]?)\.\s*(?P<title>.{2,120})$",
        r"^section\s+(?P<id>\d+[A-Z]?)\s*[-:.]\s*(?P<title>.{2,120})$",
        r"^article\s+(?P<id>\d+[A-Z]?)\s*[-:.]\s*(?P<title>.{2,120})$",
        r"^第(?P<id>[一二三四五六七八九十百0-9]+)条\s*(?P<title>.{2,120})$",
        r"^(?P<id>\d+[A-Z]?)\.\s*(?P<title>.*租金.*契诺.*|.*rent.*covenant.*)$",
    )
    for pattern in patterns:
        match = re.search(pattern, text, re.I)
        if match:
            return match.group("id"), match.group("title").strip()
    return None


def _infer_language(text: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", text or ""):
        return "zh"
    if re.search(r"[a-zA-Z]", text or ""):
        return "en"
    return "unknown"


def infer_document_structure_from_chunks(chunks: list[dict], title: str = "") -> DocumentStructure:
    """Build a deterministic structure skeleton without calling an LLM."""
    sections: list[SectionNode] = []
    clauses: list[LegalClause] = []
    tables: list[TableSummary] = []
    spans: list[EvidenceSpan] = []
    entities: list[ExtractedEntity] = []
    combined_text = "\n".join(_chunk_text(chunk) for chunk in chunks[:MAX_CHUNKS_FOR_LLM_STRUCTURE])

    for idx, chunk in enumerate(chunks or []):
        text = _chunk_text(chunk)
        if not text:
            continue
        page = _chunk_page(chunk)
        chunk_id = str(chunk.get("id") or chunk.get("chunk_id") or "")
        evidence_type: EvidenceType = "unknown"
        clause = _extract_clause_title(text)
        if clause:
            evidence_type = "clause"
            clauses.append(
                LegalClause(
                    clause_id=clause[0],
                    title=clause[1],
                    source_span=EvidenceSpan(chunk_id=chunk_id or None, page=page, quote=text[:500], evidence_type="clause"),
                )
            )
        elif "<table" in text.lower() or re.search(r"\|.+\|", text):
            evidence_type = "table"
            tables.append(
                TableSummary(
                    title=f"Table on page {page}" if page else "Table",
                    page=page,
                    summary=text[:500],
                    source_span=EvidenceSpan(chunk_id=chunk_id or None, page=page, quote=text[:500], evidence_type="table"),
                )
            )
        elif _is_probable_title(text):
            evidence_type = "title"
            sections.append(
                SectionNode(
                    section_id=str(len(sections) + 1),
                    title=text[:120],
                    level=1,
                    page_start=page,
                    page_end=page,
                    summary="",
                )
            )
        else:
            evidence_type = "fact"

        spans.append(EvidenceSpan(chunk_id=chunk_id or None, page=page, quote=text[:500], evidence_type=evidence_type))

        for amount in re.findall(r"(?:HK\$|US\$|\$|RMB|CNY|USD|HKD)\s?[\d,.]+|[\d,.]+\s?(?:million|billion|万元|亿元)", text, re.I):
            entities.append(ExtractedEntity(text=amount, label="amount", normalized=amount))
        for date in re.findall(r"\b(?:19|20)\d{2}(?:[-/年]\d{1,2}(?:[-/月]\d{1,2}日?)?)?\b", text):
            entities.append(ExtractedEntity(text=date, label="date", normalized=date))

        if idx + 1 >= MAX_CHUNKS_FOR_LLM_STRUCTURE:
            break

    inferred_title = title or (sections[0].title if sections else "")
    return DocumentStructure(
        title=inferred_title,
        language=_infer_language(combined_text),
        sections=sections[:20],
        legal_clauses=clauses[:50],
        tables=tables[:20],
        entities=entities[:80],
        evidence_spans=spans[:80],
        confidence=0.45 if spans else 0.0,
    )


def build_structure_prompt(chunks: list[dict], title: str = "") -> list[dict]:
    snippets = []
    for idx, chunk in enumerate((chunks or [])[:MAX_CHUNKS_FOR_LLM_STRUCTURE], start=1):
        text = _chunk_text(chunk)[:MAX_CHARS_PER_CHUNK_FOR_LLM_STRUCTURE]
        if not text:
            continue
        snippets.append(
            {
                "idx": idx,
                "chunk_id": chunk.get("id") or chunk.get("chunk_id"),
                "page": _chunk_page(chunk),
                "text": text,
            }
        )
    return [
        {
            "role": "system",
            "content": (
                "Extract a concise, source-grounded document structure. "
                "Use only the provided chunks. Do not invent section titles, legal clauses, tables, or entities. "
                "Keep quotes short and preserve chunk_id/page when available."
            ),
        },
        {
            "role": "user",
            "content": f"Document title: {title or '(unknown)'}\nChunks:\n{snippets}",
        },
    ]


def extract_document_structure_with_instructor(
    chunks: list[dict],
    *,
    title: str = "",
    base_url: str,
    api_key: str,
    model: str,
    max_tokens: int = 1024,
    max_retries: int = 0,
) -> DocumentStructure:
    """Use Instructor JSON mode for offline/low-concurrency structure extraction.

    The current ds4-server can return JSON reliably, but validation reask may
    trigger live KV/session instability. Online callers should keep
    max_retries=0. Background parsing is capped to one retry by
    resolve_instructor_retry_policy().
    """
    from openai import OpenAI
    import instructor

    acquired = _INSTRUCTOR_SEMAPHORE.acquire(timeout=INSTRUCTOR_DEFAULT_TIMEOUT_SECONDS)
    if not acquired:
        raise TimeoutError("structured_instructor_concurrency_timeout")
    try:
        client = instructor.from_openai(OpenAI(base_url=base_url, api_key=api_key), mode=instructor.Mode.JSON)
        return client.chat.completions.create(
            model=model,
            response_model=DocumentStructure,
            messages=build_structure_prompt(chunks, title),
            max_tokens=max_tokens,
            temperature=0,
            max_retries=max_retries,
        )
    finally:
        _INSTRUCTOR_SEMAPHORE.release()


def apply_structure_to_chunks(chunks: list[dict], structure: DocumentStructure) -> list[dict]:
    """Return copies of chunks enriched with structured metadata under extra.structured."""
    enriched = []
    span_by_chunk = {span.chunk_id: span for span in structure.evidence_spans if span.chunk_id}
    clauses_by_chunk = {
        clause.source_span.chunk_id: clause
        for clause in structure.legal_clauses
        if clause.source_span and clause.source_span.chunk_id
    }
    for chunk in chunks or []:
        item = deepcopy(chunk)
        chunk_id = str(item.get("id") or item.get("chunk_id") or "")
        span = span_by_chunk.get(chunk_id)
        clause = clauses_by_chunk.get(chunk_id)
        structured = {
            "document_title": structure.title,
            "language": structure.language,
            "confidence": structure.confidence,
            "evidence_type": span.evidence_type if span else "unknown",
        }
        if clause:
            structured["clause_id"] = clause.clause_id
            structured["clause_title"] = clause.title
        if structure.entities:
            structured["entities"] = [entity.model_dump(exclude_none=True) for entity in structure.entities[:20]]
        extra = item.get("extra") if isinstance(item.get("extra"), dict) else {}
        extra[STRUCTURED_EXTRACTION_EXTRA_KEY] = structured
        item["extra"] = extra
        enriched.append(item)
    return enriched


def try_extract_document_structure_with_instructor(
    chunks: list[dict],
    *,
    context: Literal["online", "background"] = "online",
    doc_id: str = "",
    **kwargs,
) -> DocumentStructure:
    policy = resolve_instructor_retry_policy(kwargs, context=context)
    kwargs["max_retries"] = policy.max_retries
    try:
        return extract_document_structure_with_instructor(chunks, **kwargs)
    except Exception as exc:  # noqa: BLE001 - structure extraction must never block parsing
        error_type = classify_structured_extraction_error(exc)
        logging.warning(
            "Structured extraction failed; fallback=deterministic doc=%s title=%s page=%s chunks=%s "
            "context=%s retries=%s error_type=%s error=%s",
            doc_id or "-",
            kwargs.get("title") or "",
            _first_chunk_page(chunks),
            len(chunks or []),
            policy.context,
            policy.max_retries,
            error_type,
            exc,
        )
        return infer_document_structure_from_chunks(chunks, kwargs.get("title") or "")
