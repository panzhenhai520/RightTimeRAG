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
import os
import re
from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


COMPLIANCE_STATUS = {"compliant", "non_compliant", "missing", "ambiguous", "not_applicable"}
RISK_LEVELS = {"none", "low", "medium", "high"}
NORMATIVE_TERMS = (
    "应当",
    "应",
    "必须",
    "须",
    "不得",
    "禁止",
    "需要",
    "需",
    "shall",
    "must",
    "should",
    "may not",
    "prohibit",
)
NEGATIVE_TERMS = ("不得", "禁止", "不得约定", "不得低于", "may not", "must not", "prohibit")
RISK_HIGH_TERMS = ("必须", "应当", "不得", "禁止", "责任", "赔偿", "违约", "强制", "罚", "penalty", "liability")
CONFLICT_TERMS = ("不承担", "无需承担", "免除", "概不负责", "自行承担", "低于", "放弃", "不支付")
CLAUSE_TYPE_KEYWORDS = {
    "payment": ("价款", "费用", "金额", "支付", "付款", "结算", "工资", "报酬", "payment", "fee", "amount"),
    "term": ("期限", "有效期", "到期", "终止", "续期", "duration", "term"),
    "liability": ("违约", "赔偿", "责任", "罚", "损失", "liability", "breach", "damage"),
    "confidentiality": ("保密", "秘密", "confidential", "non-disclosure"),
    "termination": ("解除", "终止", "termination", "cancel"),
    "dispute": ("争议", "仲裁", "诉讼", "管辖", "dispute", "arbitration", "jurisdiction"),
    "party": ("甲方", "乙方", "主体", "当事人", "party"),
    "obligation": ("应", "应当", "必须", "负责", "义务", "shall", "must", "obligation"),
}


def _parse_json_like(value: Any, default: Any = None) -> Any:
    if value is None:
        return default
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return value
    return value


def _as_list(value: Any) -> list[Any]:
    value = _parse_json_like(value, value)
    if value is None:
        return []
    if isinstance(value, dict):
        for key in ("references", "matches", "chunks", "clauses", "checklist", "verification_results", "risk_items"):
            if isinstance(value.get(key), list):
                return value[key]
        return [value]
    if isinstance(value, (list, tuple)):
        return list(value)
    if isinstance(value, str):
        return [{"content": value}]
    return []


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False)
    return str(value)


def _source_ref(item: dict[str, Any]) -> str:
    if item.get("source_ref"):
        return str(item["source_ref"])
    name = item.get("document_name") or item.get("docnm_kwd") or item.get("file_name") or item.get("file_id") or "document"
    parts = [str(name)]
    if item.get("page") is not None:
        parts.append(f"page {item.get('page')}")
    elif item.get("page_num_int"):
        page_num = item.get("page_num_int")
        if isinstance(page_num, list) and page_num:
            parts.append(f"page {page_num[0]}")
    chunk_id = item.get("chunk_id") or item.get("id")
    if chunk_id:
        parts.append(f"chunk {chunk_id}")
    article_no = item.get("article_no") or item.get("article_numbers")
    if article_no:
        parts.append(f"article {article_no}")
    return " | ".join(parts)


def _reference_from(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_ref": _source_ref(item),
        "file_id": item.get("file_id") or item.get("document_id") or item.get("doc_id"),
        "document_id": item.get("document_id") or item.get("doc_id") or item.get("file_id"),
        "document_name": item.get("document_name") or item.get("docnm_kwd") or item.get("doc_name") or item.get("name"),
        "chunk_id": item.get("chunk_id") or item.get("id"),
        "page": item.get("page") if item.get("page") is not None else (item.get("page_num_int") or [None])[0],
        "article_no": item.get("article_no") or item.get("article_numbers"),
        "version": item.get("version"),
        "effective_from": item.get("effective_from"),
        "effective_to": item.get("effective_to"),
        "metadata_incomplete": bool(item.get("metadata_incomplete")),
    }


def _resolve(component: ComponentBase, value: Any, fallback: Any = None) -> Any:
    if value in (None, ""):
        return fallback
    if not isinstance(value, str):
        return value
    try:
        if component._canvas.is_reff(value):
            return component._canvas.get_variable_value(value)
        if "@" in value and "{" in value:
            return component._canvas.get_value_with_variable(value)
    except Exception:
        return fallback if fallback is not None else value
    return value


def _terms(text: Any) -> set[str]:
    raw = re.sub(r"\s+", " ", _text(text).lower())
    words = set(re.findall(r"[a-z0-9_]{2,}", raw))
    cn = re.findall(r"[\u4e00-\u9fff]{2,}", raw)
    for segment in cn:
        if len(segment) <= 6:
            words.add(segment)
        for size in (2, 3, 4):
            for idx in range(0, max(len(segment) - size + 1, 0)):
                words.add(segment[idx : idx + size])
    for term_group in CLAUSE_TYPE_KEYWORDS.values():
        for term in term_group:
            if term.lower() in raw:
                words.add(term.lower())
    return {word for word in words if word}


def _infer_clause_type(text: str) -> str:
    lowered = text.lower()
    for clause_type, keywords in CLAUSE_TYPE_KEYWORDS.items():
        if any(keyword.lower() in lowered for keyword in keywords):
            return clause_type
    return "general"


def _split_sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[。；;.!?？])\s*|\n+", text or "")
    return [part.strip(" \t\r\n-•") for part in parts if part and part.strip(" \t\r\n-•")]


class ContractClauseExtractorParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.chunks = ""
        self.content = ""
        self.references = ""
        self.min_clause_chars = 4
        self.outputs = {
            "clause_tree": {"value": {}, "type": "JSON"},
            "clauses": {"value": [], "type": "Array<JSON>"},
            "entities": {"value": {}, "type": "JSON"},
            "references": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "chunks": {"type": "Array<TextChunk>", "required": False},
            "content": {"type": "String", "required": False},
            "references": {"type": "Array<JSON>", "required": False},
        }

    def check(self):
        self.check_positive_integer(self.min_clause_chars, "[ContractClauseExtractor] Min clause chars")


class ContractClauseExtractor(ComponentBase, ABC):
    component_name = "ContractClauseExtractor"
    CLAUSE_HEADING_RE = re.compile(
        r"^\s*((第[一二三四五六七八九十百千万零〇两\d]+[章节条款项])|(\d+(?:\.\d+)*[、.．]?)|([（(][一二三四五六七八九十百千万零〇两\d]+[）)]))\s*(.*)$"
    )

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for field in ("chunks", "content", "references"):
            value = getattr(self._param, field, "")
            if isinstance(value, str):
                for k, o in self.get_input_elements_from_text(value).items():
                    res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def extract_entities(text: str) -> dict[str, Any]:
        return {
            "parties": sorted(set(re.findall(r"[甲乙丙丁]方|买方|卖方|用人单位|劳动者|委托人|受托人", text or ""))),
            "obligations": [sent for sent in _split_sentences(text) if any(term in sent for term in ("应", "须", "负责", "义务", "shall", "must"))],
            "amounts": re.findall(r"(?:人民币|RMB|¥|\$)?\s*\d+(?:,\d{3})*(?:\.\d+)?\s*(?:元|万元|%|美元|人民币)?", text or ""),
            "terms": re.findall(r"\d+\s*(?:日|天|个月|月|年|工作日)|[一二三四五六七八九十百千万]+\s*(?:日|天|个月|月|年|工作日)", text or ""),
            "liabilities": [sent for sent in _split_sentences(text) if any(term in sent for term in ("违约", "赔偿", "责任", "罚", "liability", "breach"))],
        }

    @classmethod
    def _flush_clause(
        cls,
        clauses: list[dict[str, Any]],
        marker: str,
        title: str,
        lines: list[str],
        source: dict[str, Any],
        min_clause_chars: int,
    ) -> None:
        text = "\n".join(line.strip() for line in lines if line and line.strip()).strip()
        if len(text) < min_clause_chars:
            return
        idx = len(clauses) + 1
        clause_id = marker.strip(" 、.．") if marker else f"clause-{idx}"
        ref = _reference_from(source)
        clause = {
            "clause_id": clause_id or f"clause-{idx}",
            "title": (title or text[:60]).strip(),
            "text": text,
            "page": ref.get("page"),
            "source_ref": ref.get("source_ref"),
            "references": [ref],
            "clause_type": _infer_clause_type(text),
            "entities": cls.extract_entities(text),
        }
        clauses.append(clause)

    @classmethod
    def extract_clauses(cls, chunks: Any = None, content: Any = "", references: Any = None, min_clause_chars: int = 4) -> dict[str, Any]:
        raw_chunks = _as_list(chunks)
        refs = _as_list(references)
        if not raw_chunks and content:
            raw_chunks = [{"content": _text(content), "source_ref": "uploaded document"}]
        clauses: list[dict[str, Any]] = []
        for chunk_idx, chunk in enumerate(raw_chunks):
            if not isinstance(chunk, dict):
                chunk = {"content": _text(chunk)}
            text = _text(chunk.get("content") or chunk.get("content_with_weight") or chunk.get("text") or "")
            if not text.strip():
                continue
            source = {**chunk}
            if chunk_idx < len(refs) and isinstance(refs[chunk_idx], dict):
                source = {**refs[chunk_idx], **source}
            marker = ""
            title = ""
            lines: list[str] = []
            for line in text.splitlines():
                stripped = line.strip()
                if not stripped:
                    continue
                match = cls.CLAUSE_HEADING_RE.match(stripped)
                if match and lines:
                    cls._flush_clause(clauses, marker, title, lines, source, min_clause_chars)
                    marker = match.group(1) or ""
                    title = (match.group(5) or stripped).strip()
                    lines = [stripped]
                elif match:
                    marker = match.group(1) or marker
                    title = (match.group(5) or stripped).strip()
                    lines.append(stripped)
                else:
                    lines.append(stripped)
            cls._flush_clause(clauses, marker, title, lines, source, min_clause_chars)
        if not clauses and raw_chunks:
            for chunk in raw_chunks:
                source = chunk if isinstance(chunk, dict) else {"content": _text(chunk)}
                cls._flush_clause(clauses, "", "", [_text(source.get("content") or source)], source, min_clause_chars)

        aggregate_entities = {"parties": set(), "amounts": [], "terms": [], "liabilities": [], "obligations": []}
        for clause in clauses:
            entities = clause.get("entities") or {}
            aggregate_entities["parties"].update(entities.get("parties") or [])
            for key in ("amounts", "terms", "liabilities", "obligations"):
                aggregate_entities[key].extend(entities.get(key) or [])
        normalized_entities = {**aggregate_entities, "parties": sorted(aggregate_entities["parties"])}
        clause_tree = {
            "schema_version": 1,
            "root": [
                {
                    "section_id": "root",
                    "title": "合同条款",
                    "clauses": [clause["clause_id"] for clause in clauses],
                }
            ],
        }
        references_out = [ref for clause in clauses for ref in clause.get("references", [])]
        return {
            "clause_tree": clause_tree,
            "clauses": clauses,
            "entities": normalized_entities,
            "references": references_out,
            "summary": f"Extracted {len(clauses)} clause(s).",
        }

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ContractClauseExtractor processing"):
            return
        result = self.extract_clauses(
            chunks=_resolve(self, self._param.chunks, kwargs.get("chunks")),
            content=_resolve(self, self._param.content, kwargs.get("content")),
            references=_resolve(self, self._param.references, kwargs.get("references")),
            min_clause_chars=int(self._param.min_clause_chars or 4),
        )
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Extracting contract clauses into a structured clause tree."


class ComplianceChecklistGeneratorParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.standards = ""
        self.focus = ""
        self.max_items = 80
        self.outputs = {
            "checklist": {"value": [], "type": "Array<JSON>"},
            "references": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "standards": {"type": "Array<JSON>", "required": True},
            "focus": {"type": "String", "required": False},
        }

    def check(self):
        self.check_positive_integer(self.max_items, "[ComplianceChecklistGenerator] Max items")


class ComplianceChecklistGenerator(ComponentBase, ABC):
    component_name = "ComplianceChecklistGenerator"

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for field in ("standards", "focus"):
            value = getattr(self._param, field, "")
            if isinstance(value, str):
                for k, o in self.get_input_elements_from_text(value).items():
                    res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def generate_checklist(standards: Any, focus: str = "", max_items: int = 80) -> dict[str, Any]:
        items = []
        references = []
        seen = set()
        focus_terms = _terms(focus)
        for standard in _as_list(standards):
            if not isinstance(standard, dict):
                standard = {"content": _text(standard)}
            content = _text(standard.get("content") or standard.get("content_with_weight") or standard.get("text") or "")
            ref = _reference_from(standard)
            if not content.strip():
                continue
            metadata_incomplete = not (ref.get("source_ref") and (ref.get("version") or ref.get("effective_from") or ref.get("article_no")))
            ref["metadata_incomplete"] = bool(ref.get("metadata_incomplete") or metadata_incomplete)
            for sentence in _split_sentences(content):
                if not any(term.lower() in sentence.lower() for term in NORMATIVE_TERMS):
                    continue
                if focus_terms and not (_terms(sentence) & focus_terms):
                    continue
                key = (ref.get("source_ref"), sentence[:120])
                if key in seen:
                    continue
                seen.add(key)
                idx = len(items) + 1
                items.append(
                    {
                        "check_id": f"check-{idx}",
                        "requirement": sentence,
                        "basis_text": sentence,
                        "basis_ref": ref.get("source_ref"),
                        "basis": ref,
                        "applicability_condition": "always",
                        "required_clause_type": _infer_clause_type(sentence),
                        "mandatory": True,
                        "needs_human_review": bool(ref["metadata_incomplete"]),
                    }
                )
                references.append(ref)
                if len(items) >= max_items:
                    break
            if len(items) >= max_items:
                break
        if not items and _as_list(standards):
            standard = _as_list(standards)[0]
            standard = standard if isinstance(standard, dict) else {"content": _text(standard)}
            ref = _reference_from(standard)
            items.append(
                {
                    "check_id": "check-1",
                    "requirement": "未从标准文本中识别出明确的强制性核对要求，需要人工复核。",
                    "basis_text": _text(standard.get("content") or "")[:500],
                    "basis_ref": ref.get("source_ref"),
                    "basis": ref,
                    "applicability_condition": "needs_human_review",
                    "required_clause_type": "general",
                    "mandatory": False,
                    "needs_human_review": True,
                }
            )
            references.append(ref)
        return {
            "checklist": items,
            "references": references,
            "summary": f"Generated {len(items)} compliance check item(s).",
        }

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ComplianceChecklistGenerator processing"):
            return
        result = self.generate_checklist(
            _resolve(self, self._param.standards, kwargs.get("standards")),
            _text(_resolve(self, self._param.focus, kwargs.get("focus"))),
            int(self._param.max_items or 80),
        )
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Generating a compliance checklist from bound knowledge references."


class ClauseMatcherParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.checklist = ""
        self.clauses = ""
        self.min_confidence = 0.28
        self.outputs = {
            "matches": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "checklist": {"type": "Array<JSON>", "required": True},
            "clauses": {"type": "Array<JSON>", "required": True},
        }

    def check(self):
        self.check_decimal_float(self.min_confidence, "[ClauseMatcher] Min confidence")


class ClauseMatcher(ComponentBase, ABC):
    component_name = "ClauseMatcher"

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for field in ("checklist", "clauses"):
            value = getattr(self._param, field, "")
            if isinstance(value, str):
                for k, o in self.get_input_elements_from_text(value).items():
                    res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def score(requirement: dict[str, Any], clause: dict[str, Any]) -> float:
        req_text = " ".join(
            [
                _text(requirement.get("requirement")),
                _text(requirement.get("basis_text")),
                _text(requirement.get("required_clause_type")),
            ]
        )
        clause_text = " ".join([_text(clause.get("title")), _text(clause.get("text")), _text(clause.get("clause_type"))])
        req_terms = _terms(req_text)
        clause_terms = _terms(clause_text)
        if not req_terms or not clause_terms:
            return 0.0
        overlap = len(req_terms & clause_terms) / max(len(req_terms), 1)
        type_bonus = 0.0
        required_type = requirement.get("required_clause_type")
        if required_type and required_type == clause.get("clause_type"):
            type_bonus = 0.25
        return round(min(1.0, overlap + type_bonus), 4)

    @classmethod
    def match(cls, checklist: Any, clauses: Any, min_confidence: float = 0.28) -> dict[str, Any]:
        clause_list = [item for item in _as_list(clauses) if isinstance(item, dict)]
        matches = []
        for item in _as_list(checklist):
            if not isinstance(item, dict):
                continue
            scored = []
            for clause in clause_list:
                confidence = cls.score(item, clause)
                if confidence > 0:
                    scored.append((confidence, clause))
            scored.sort(key=lambda pair: pair[0], reverse=True)
            selected = scored[:3]
            best = selected[0][0] if selected else 0.0
            contract_refs = []
            clause_ids = []
            if best >= min_confidence:
                for confidence, clause in selected:
                    if confidence < min_confidence:
                        continue
                    clause_ids.append(clause.get("clause_id"))
                    contract_refs.extend(clause.get("references") or [{"source_ref": clause.get("source_ref")}])
                status = "matched"
            elif best > 0:
                status = "ambiguous"
            else:
                status = "missing"
            matches.append(
                {
                    "check_id": item.get("check_id"),
                    "matched_clause_ids": [clause_id for clause_id in clause_ids if clause_id],
                    "confidence": best,
                    "match_status": status,
                    "match_reason": "Matched by legal-topic term overlap and clause type." if status == "matched" else "No confident clause match.",
                    "contract_refs": contract_refs,
                }
            )
        return {"matches": matches, "summary": f"Matched {sum(1 for item in matches if item['match_status'] == 'matched')} item(s)."}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ClauseMatcher processing"):
            return
        result = self.match(
            _resolve(self, self._param.checklist, kwargs.get("checklist")),
            _resolve(self, self._param.clauses, kwargs.get("clauses")),
            float(self._param.min_confidence or 0.28),
        )
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Matching compliance checklist items to contract clauses."


class ComplianceVerifierParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.checklist = ""
        self.matches = ""
        self.clauses = ""
        self.min_confidence = 0.28
        self.outputs = {
            "verification_results": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "string"},
            "references": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "checklist": {"type": "Array<JSON>", "required": True},
            "matches": {"type": "Array<JSON>", "required": True},
            "clauses": {"type": "Array<JSON>", "required": True},
        }

    def check(self):
        self.check_decimal_float(self.min_confidence, "[ComplianceVerifier] Min confidence")


class ComplianceVerifier(ComponentBase, ABC):
    component_name = "ComplianceVerifier"

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for field in ("checklist", "matches", "clauses"):
            value = getattr(self._param, field, "")
            if isinstance(value, str):
                for k, o in self.get_input_elements_from_text(value).items():
                    res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def verify(checklist: Any, matches: Any, clauses: Any, min_confidence: float = 0.28) -> dict[str, Any]:
        match_by_check = {item.get("check_id"): item for item in _as_list(matches) if isinstance(item, dict)}
        clause_by_id = {item.get("clause_id"): item for item in _as_list(clauses) if isinstance(item, dict)}
        results = []
        references = []
        for item in _as_list(checklist):
            if not isinstance(item, dict):
                continue
            check_id = item.get("check_id")
            match = match_by_check.get(check_id) or {}
            basis_ref = item.get("basis_ref") or (item.get("basis") or {}).get("source_ref")
            basis = item.get("basis") or {"source_ref": basis_ref}
            matched_ids = match.get("matched_clause_ids") or []
            matched_clauses = [clause_by_id.get(clause_id) for clause_id in matched_ids if clause_by_id.get(clause_id)]
            contract_refs = [ref for clause in matched_clauses for ref in (clause.get("references") or [])]
            evidence_refs = []
            if basis_ref:
                evidence_refs.append(basis)
            evidence_refs.extend(contract_refs)

            if item.get("applicability_condition") == "not_applicable":
                status = "not_applicable"
                reason = "The checklist item is marked as not applicable."
            elif not basis_ref:
                status = "ambiguous"
                reason = "No standard basis reference is available; cannot make a compliance conclusion."
            elif not matched_clauses:
                status = "missing"
                reason = "No matching contract clause was found for this required item."
            elif float(match.get("confidence") or 0) < min_confidence:
                status = "ambiguous"
                reason = "The matched contract clause confidence is below the verification threshold."
            else:
                contract_text = "\n".join(_text(clause.get("text")) for clause in matched_clauses)
                requirement = _text(item.get("requirement") or item.get("basis_text"))
                if any(term in contract_text for term in CONFLICT_TERMS) and any(term in requirement for term in RISK_HIGH_TERMS):
                    status = "non_compliant"
                    reason = "The matched contract clause appears to conflict with a mandatory standard requirement."
                else:
                    status = "compliant"
                    reason = "A matching contract clause and standard basis are both present."

            if status == "compliant" and not (basis_ref and contract_refs):
                status = "ambiguous"
                reason = "A compliant conclusion requires both standard basis and contract clause references."

            suggestion = ""
            if status == "missing":
                suggestion = "补充与该核对项对应的合同条款，并引用标准依据重新核对。"
            elif status == "non_compliant":
                suggestion = "修改冲突条款，使其与标准依据保持一致。"
            elif status == "ambiguous":
                suggestion = "证据不足或匹配置信度不足，建议人工复核。"

            results.append(
                {
                    "check_id": check_id,
                    "check_item": item.get("requirement"),
                    "status": status,
                    "standard_basis": {"text": item.get("basis_text"), "ref": basis_ref},
                    "contract_clause": [
                        {"clause_id": clause.get("clause_id"), "text": clause.get("text"), "ref": clause.get("source_ref")}
                        for clause in matched_clauses
                    ],
                    "confidence": float(match.get("confidence") or 0),
                    "reason": reason,
                    "evidence_refs": evidence_refs,
                    "suggestion": suggestion,
                }
            )
            references.extend(evidence_refs)
        counts = {status: 0 for status in COMPLIANCE_STATUS}
        for result in results:
            counts[result["status"]] = counts.get(result["status"], 0) + 1
        return {
            "verification_results": results,
            "references": references,
            "summary": f"Verified {len(results)} item(s): " + ", ".join(f"{key}={value}" for key, value in counts.items() if value),
        }

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ComplianceVerifier processing"):
            return
        result = self.verify(
            _resolve(self, self._param.checklist, kwargs.get("checklist")),
            _resolve(self, self._param.matches, kwargs.get("matches")),
            _resolve(self, self._param.clauses, kwargs.get("clauses")),
            float(self._param.min_confidence or 0.28),
        )
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Verifying each checklist item against the matched contract clauses."


class RiskScorerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.verification_results = ""
        self.outputs = {
            "risk_items": {"value": [], "type": "Array<JSON>"},
            "risk_summary": {"value": {}, "type": "JSON"},
            "overall_risk_level": {"value": "none", "type": "string"},
        }
        self.input_schema = {"verification_results": {"type": "Array<JSON>", "required": True}}

    def check(self):
        return True


class RiskScorer(ComponentBase, ABC):
    component_name = "RiskScorer"

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        value = self._param.verification_results
        if isinstance(value, str):
            for k, o in self.get_input_elements_from_text(value).items():
                res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def score(verification_results: Any) -> dict[str, Any]:
        risk_items = []
        rank = {"none": 0, "low": 1, "medium": 2, "high": 3}
        overall = "none"
        counts = {level: 0 for level in RISK_LEVELS}
        for result in _as_list(verification_results):
            if not isinstance(result, dict):
                continue
            status = result.get("status")
            text = " ".join([_text(result.get("check_item")), _text(result.get("reason")), _text(result.get("standard_basis"))])
            if status == "non_compliant":
                level = "high" if any(term in text for term in RISK_HIGH_TERMS) else "medium"
            elif status == "missing":
                level = "high" if any(term in text for term in RISK_HIGH_TERMS) else "medium"
            elif status == "ambiguous":
                level = "medium"
            else:
                level = "none"
            counts[level] = counts.get(level, 0) + 1
            if rank[level] > rank[overall]:
                overall = level
            if level != "none":
                risk_items.append(
                    {
                        "check_id": result.get("check_id"),
                        "risk_level": level,
                        "status": status,
                        "reason": result.get("reason"),
                        "suggestion": result.get("suggestion"),
                        "evidence_refs": result.get("evidence_refs") or [],
                    }
                )
        return {
            "risk_items": risk_items,
            "risk_summary": {
                "overall_risk_level": overall,
                "counts": counts,
                "total_risk_items": len(risk_items),
            },
            "overall_risk_level": overall,
        }

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("RiskScorer processing"):
            return
        result = self.score(_resolve(self, self._param.verification_results, kwargs.get("verification_results")))
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Scoring compliance risks."


class ComplianceReportComposerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.title = "文档核对报告"
        self.scope = ""
        self.verification_results = ""
        self.risk_summary = ""
        self.references = ""
        self.outputs = {
            "markdown": {"value": "", "type": "string"},
            "summary": {"value": "", "type": "string"},
            "tables": {"value": {}, "type": "JSON"},
            "references": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "scope": {"type": "String", "required": False},
            "verification_results": {"type": "Array<JSON>", "required": True},
            "risk_summary": {"type": "JSON", "required": False},
            "references": {"type": "Array<JSON>", "required": False},
        }

    def check(self):
        return True


class ComplianceReportComposer(ComponentBase, ABC):
    component_name = "ComplianceReportComposer"

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for field in ("scope", "verification_results", "risk_summary", "references"):
            value = getattr(self._param, field, "")
            if isinstance(value, str):
                for k, o in self.get_input_elements_from_text(value).items():
                    res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def compose(title: str, verification_results: Any, risk_summary: Any = None, references: Any = None, scope: str = "") -> dict[str, Any]:
        results = [item for item in _as_list(verification_results) if isinstance(item, dict)]
        risk = _parse_json_like(risk_summary, risk_summary) or {}
        refs = [item for item in _as_list(references) if isinstance(item, dict)]
        if not refs:
            refs = [ref for result in results for ref in (result.get("evidence_refs") or []) if isinstance(ref, dict)]
        counts: dict[str, int] = {}
        for result in results:
            counts[result.get("status", "unknown")] = counts.get(result.get("status", "unknown"), 0) + 1
        summary = (
            f"共核对 {len(results)} 项；"
            + "，".join(f"{status} {count} 项" for status, count in counts.items())
            + f"；总体风险：{risk.get('overall_risk_level') or risk.get('risk_summary', {}).get('overall_risk_level') or 'none'}。"
        )
        lines = [
            f"# {title or '文档核对报告'}",
            "",
            "## 核对范围",
            scope or "基于用户上传文档与当前智能体绑定知识库进行核对。",
            "",
            "## 标准来源",
        ]
        if refs:
            for idx, ref in enumerate(refs[:80], start=1):
                marker = "（版本信息不足）" if ref.get("metadata_incomplete") else ""
                lines.append(f"{idx}. {ref.get('source_ref') or ref.get('document_name') or 'source'}{marker}")
        else:
            lines.append("未获得可引用的标准来源或合同条款来源。")
        lines.extend(["", "## 总体结论", summary, "", "## 风险汇总"])
        lines.append(json.dumps(risk, ensure_ascii=False, indent=2) if isinstance(risk, dict) else _text(risk))
        lines.extend(
            [
                "",
                "## 逐条核对表",
                "| 编号 | 结论 | 风险/置信度 | 核对项 | 理由 | 建议 |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for result in results:
            lines.append(
                "| {check_id} | {status} | {confidence:.2f} | {item} | {reason} | {suggestion} |".format(
                    check_id=str(result.get("check_id") or ""),
                    status=str(result.get("status") or ""),
                    confidence=float(result.get("confidence") or 0),
                    item=_text(result.get("check_item")).replace("|", "/")[:120],
                    reason=_text(result.get("reason")).replace("|", "/")[:160],
                    suggestion=_text(result.get("suggestion")).replace("|", "/")[:160],
                )
            )
        lines.extend(
            [
                "",
                "## 人工复核提示",
                "本报告为基于上传文档和绑定知识库的文本分析辅助结果，不构成正式法律意见。证据不足、版本信息不足、低置信度或高风险项目应由人工复核。",
            ]
        )
        tables = {
            "verification_results": results,
            "risk_summary": risk,
            "status_counts": counts,
        }
        return {"markdown": "\n".join(lines), "summary": summary, "tables": tables, "references": refs}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("ComplianceReportComposer processing"):
            return
        result = self.compose(
            self._param.title,
            _resolve(self, self._param.verification_results, kwargs.get("verification_results")),
            _resolve(self, self._param.risk_summary, kwargs.get("risk_summary")),
            _resolve(self, self._param.references, kwargs.get("references")),
            _text(_resolve(self, self._param.scope, kwargs.get("scope"))),
        )
        for key, value in result.items():
            self.set_output(key, value)

    def thoughts(self) -> str:
        return "Composing the compliance verification report."
