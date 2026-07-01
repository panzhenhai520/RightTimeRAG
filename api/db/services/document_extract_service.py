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

import json
import re
import uuid
from typing import Any


NORMATIVE_TERMS = ("应当", "应", "必须", "须", "不得", "禁止", "shall", "must", "should", "may not")
RISK_TERMS = ("不得", "禁止", "违约", "赔偿", "责任", "罚", "解除", "终止", "逾期", "冲突", "liability", "penalty")
VIEWPOINT_TERMS = ("认为", "建议", "结论", "观点", "recommend", "suggest", "conclude", "opinion")
DEFINITION_TERMS = ("是指", "定义", "以下简称", "称为", "means", "refers to", "defined as")


class DocumentExtractService:
    """Deterministic structured extraction from normalized documents."""

    @classmethod
    def extract_clauses(cls, value: Any, *, min_chars: int = 4) -> dict[str, Any]:
        items = []
        for block in cls.iter_text_blocks(value):
            text = str(block.get("text") or block.get("content") or "").strip()
            if len(text) < min_chars:
                continue
            if not cls._looks_like_clause(text):
                continue
            item = cls._base_item(block, "clause", len(items) + 1)
            item.update(cls._clause_fields(text))
            items.append(item)
        return cls._result("clauses", items)

    @classmethod
    def extract_obligations(cls, value: Any, *, min_chars: int = 4) -> dict[str, Any]:
        clauses = cls.extract_clauses(value, min_chars=min_chars)["items"]
        items = []
        for clause in clauses:
            if any(term.lower() in clause["normalized_text"].lower() for term in NORMATIVE_TERMS):
                item = {**clause, "item_type": "obligation", "item_id": f"obligation-{len(items) + 1}"}
                items.append(item)
        return cls._result("obligations", items)

    @classmethod
    def extract_definitions(cls, value: Any, *, min_chars: int = 4) -> dict[str, Any]:
        items = []
        for block in cls.iter_text_blocks(value):
            text = str(block.get("text") or block.get("content") or "").strip()
            if len(text) < min_chars:
                continue
            if not any(term.lower() in text.lower() for term in DEFINITION_TERMS):
                continue
            item = cls._base_item(block, "definition", len(items) + 1)
            item.update(cls._definition_fields(text))
            items.append(item)
        return cls._result("definitions", items)

    @classmethod
    def extract_viewpoints(cls, value: Any, *, min_chars: int = 8) -> dict[str, Any]:
        items = []
        for block in cls.iter_text_blocks(value):
            text = str(block.get("text") or block.get("content") or "").strip()
            if len(text) < min_chars:
                continue
            if not any(term.lower() in text.lower() for term in VIEWPOINT_TERMS):
                continue
            item = cls._base_item(block, "viewpoint", len(items) + 1)
            item["claim"] = text
            items.append(item)
        return cls._result("viewpoints", items)

    @classmethod
    def extract_risks(cls, value: Any, *, min_chars: int = 4) -> dict[str, Any]:
        items = []
        for block in cls.iter_text_blocks(value):
            text = str(block.get("text") or block.get("content") or "").strip()
            if len(text) < min_chars:
                continue
            matched = [term for term in RISK_TERMS if term.lower() in text.lower()]
            if not matched:
                continue
            item = cls._base_item(block, "risk_point", len(items) + 1)
            item["risk_terms"] = matched
            item["severity"] = "high" if any(term in matched for term in ("不得", "禁止", "赔偿", "违约", "liability", "penalty")) else "medium"
            items.append(item)
        return cls._result("risk_points", items)

    @classmethod
    def extract_table_facts(cls, value: Any) -> dict[str, Any]:
        document = cls._as_document(value)
        items = []
        for table in document.get("tables") or []:
            headers = [str(item) for item in table.get("headers") or []]
            for row in table.get("rows") or []:
                values = row.get("values") if isinstance(row, dict) else {}
                text = "; ".join(f"{header}: {values.get(header, '')}" for header in headers)
                item = {
                    "item_id": f"table_fact-{len(items) + 1}",
                    "document_id": document.get("document_id", ""),
                    "item_type": "table_fact",
                    "text": text,
                    "normalized_text": cls.normalize_text(text),
                    "headers": headers,
                    "values": values,
                    "evidence": {
                        "source_ref": f"{table.get('source_ref', 'table')} | row {row.get('row_index', '')}",
                        "row_index": row.get("row_index"),
                    },
                    "confidence": 1.0,
                }
                items.append(item)
        return cls._result("table_facts", items)

    @classmethod
    def iter_text_blocks(cls, value: Any):
        document = cls._as_document(value)
        blocks = document.get("paragraphs") or document.get("chunks") or document.get("lines") or []
        for block in blocks:
            if isinstance(block, dict):
                yield {**block, "document_id": block.get("document_id") or document.get("document_id", "")}
        if not blocks and isinstance(value, str):
            yield {"text": value, "source_ref": "input"}

    @staticmethod
    def normalize_text(text: str) -> str:
        return re.sub(r"\s+", " ", str(text or "")).strip()

    @staticmethod
    def _as_document(value: Any) -> dict[str, Any]:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
                return parsed if isinstance(parsed, dict) else {"paragraphs": [{"text": text, "source_ref": "input"}]}
            except Exception:
                return {"paragraphs": [{"text": text, "source_ref": "input"}]}
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _looks_like_clause(text: str) -> bool:
        if any(term.lower() in text.lower() for term in NORMATIVE_TERMS):
            return True
        return bool(re.match(r"^\s*(第[一二三四五六七八九十百千万零〇\d]+[条章节款项]|\d+(?:\.\d+)*[、.．]?)", text))

    @classmethod
    def _base_item(cls, block: dict[str, Any], item_type: str, index: int) -> dict[str, Any]:
        text = str(block.get("text") or block.get("content") or "").strip()
        return {
            "item_id": f"{item_type}-{index}",
            "document_id": block.get("document_id", ""),
            "item_type": item_type,
            "text": text,
            "normalized_text": cls.normalize_text(text),
            "evidence": {
                "source_ref": block.get("source_ref", ""),
                "page": block.get("page"),
                "paragraph_index": block.get("paragraph_index"),
                "line_start": block.get("line_start") or block.get("line_number"),
                "line_end": block.get("line_end") or block.get("line_number"),
                "section_path": block.get("section_path") or [],
            },
            "confidence": 0.8,
        }

    @classmethod
    def _clause_fields(cls, text: str) -> dict[str, Any]:
        subject = cls._first_match(text, r"(甲方|乙方|丙方|丁方|用人单位|劳动者|承包人|发包人|买方|卖方)")
        deadline = cls._first_match(text, r"(\d+\s*(?:日|天|个月|月|年|工作日)|[一二三四五六七八九十百千万]+\s*(?:日|天|个月|月|年|工作日))")
        amount = cls._first_match(text, r"(?:人民币|RMB|¥|\$)?\s*(\d+(?:,\d{3})*(?:\.\d+)?\s*(?:元|万元|%|美元|人民币)?)")
        action = cls._first_match(text, r"(支付|付款|赔偿|交付|提供|保密|解除|终止|承担|履行|通知)")
        return {
            "subject": subject,
            "action": action,
            "object": "",
            "condition": cls._condition(text),
            "deadline": deadline,
            "amount": amount,
            "legal_effect": "prohibition" if any(term in text for term in ("不得", "禁止")) else ("obligation" if any(term in text for term in ("应", "必须", "须")) else "statement"),
        }

    @classmethod
    def _definition_fields(cls, text: str) -> dict[str, Any]:
        term = cls._first_match(text, r"[“\"']?([^“”\"'，,。；;]{2,40}?)[”\"']?\s*(?:是指|定义为|means|refers to|defined as)")
        definition = ""
        match = re.search(r"(?:是指|指|定义为|means|refers to|defined as)[:：]?\s*(.+)", text or "", flags=re.IGNORECASE)
        if match:
            definition = match.group(1).strip(" 。；;")
        alias = cls._first_match(text, r"以下简称[“\"']?([^”\"'。；;，,]{1,30})")
        if not term:
            term = f"definition-{uuid.uuid5(uuid.NAMESPACE_URL, text).hex[:8]}"
        return {
            "term": term,
            "definition": definition or text,
            "alias": alias,
            "legal_effect": "definition",
        }

    @staticmethod
    def _first_match(text: str, pattern: str) -> str:
        match = re.search(pattern, text or "", flags=re.IGNORECASE)
        return match.group(1).strip() if match else ""

    @staticmethod
    def _condition(text: str) -> str:
        match = re.search(r"(?:在|于|自|收到|发生)([^。；;，,]{2,40})(?:时|后|前|之日起)?", text or "")
        return match.group(0).strip() if match else ""

    @staticmethod
    def _result(kind: str, items: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "kind": kind,
            "items": items,
            kind: items,
            "references": [item.get("evidence", {}) for item in items],
            "summary": f"{len(items)} {kind} extracted.",
        }
