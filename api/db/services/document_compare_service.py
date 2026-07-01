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

import difflib
import hashlib
import json
import re
from typing import Any


PROHIBITION_TERMS = ("不得", "禁止", "严禁", "不得约定", "may not", "must not", "prohibit", "forbidden")
PERMISSION_TERMS = ("可以", "可", "允许", "有权", "无需", "不需要", "不承担", "免除", "may", "permit", "allow")
LIABILITY_TERMS = ("责任", "赔偿", "违约", "罚", "损失", "liability", "penalty", "damage")
PAYMENT_TERMS = ("付款", "支付", "价款", "费用", "payment", "pay", "fee")
DISCLOSURE_TERMS = ("泄露", "披露", "公开", "透露", "disclose", "disclosure")


class DocumentCompareService:
    """Deterministic document diff, semantic matching, and conflict checks."""

    @classmethod
    def diff_lines(cls, left: Any, right: Any) -> dict[str, Any]:
        return cls.diff_text(left, right, granularity="lines")

    @classmethod
    def diff_paragraphs(cls, left: Any, right: Any) -> dict[str, Any]:
        return cls.diff_text(left, right, granularity="paragraphs")

    @classmethod
    def diff_hash(cls, left: Any, right: Any) -> dict[str, Any]:
        left_hash = cls.hash_document(left)
        right_hash = cls.hash_document(right)
        changed_parts = [
            key
            for key in ("content_hash", "paragraph_hash", "line_hash", "table_hash", "section_hash")
            if left_hash.get(key) != right_hash.get(key)
        ]
        return {
            "schema_version": 1,
            "kind": "hash_diff",
            "left": left_hash,
            "right": right_hash,
            "same": not changed_parts,
            "changed_parts": changed_parts,
            "summary": {
                "same": not changed_parts,
                "changed_part_count": len(changed_parts),
                "changed_parts": changed_parts,
            },
        }

    @classmethod
    def diff_sections(cls, left: Any, right: Any) -> dict[str, Any]:
        left_items = cls._section_blocks(left)
        right_items = cls._section_blocks(right)
        left_keys = [cls.normalize_text(item.get("text", "")) for item in left_items]
        right_keys = [cls.normalize_text(item.get("text", "")) for item in right_items]
        matcher = difflib.SequenceMatcher(a=left_keys, b=right_keys, autojunk=False)
        hunks = []
        counts = {"equal": 0, "insert": 0, "delete": 0, "replace": 0}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            counts[tag] += max(i2 - i1, j2 - j1)
            hunks.append(
                {
                    "op": tag,
                    "left_range": [i1 + 1, i2],
                    "right_range": [j1 + 1, j2],
                    "left": left_items[i1:i2],
                    "right": right_items[j1:j2],
                }
            )
        return {
            "schema_version": 1,
            "kind": "section_diff",
            "hunks": hunks,
            "summary": {
                "left_count": len(left_items),
                "right_count": len(right_items),
                "equal": counts["equal"],
                "insert": counts["insert"],
                "delete": counts["delete"],
                "replace": counts["replace"],
                "changed": counts["insert"] + counts["delete"] + counts["replace"],
            },
        }

    @classmethod
    def hash_document(cls, value: Any) -> dict[str, Any]:
        document = cls._as_document(value)
        paragraphs = [item.get("text", "") for item in cls._text_blocks(document, "paragraphs")]
        lines = [item.get("text", "") for item in cls._text_blocks(document, "lines")]
        sections = [item.get("text", "") for item in cls._section_blocks(document)]
        tables = [item.get("text", "") for item in cls._table_rows(document)]
        content = "\n".join(paragraphs or lines)
        return {
            "content_hash": cls._sha256(content),
            "paragraph_hash": cls._sha256("\n".join(paragraphs)),
            "line_hash": cls._sha256("\n".join(lines)),
            "table_hash": cls._sha256("\n".join(tables)),
            "section_hash": cls._sha256("\n".join(sections)),
            "paragraph_count": len(paragraphs),
            "line_count": len(lines),
            "table_row_count": len(tables),
            "section_count": len(sections),
        }

    @classmethod
    def diff_text(cls, left: Any, right: Any, *, granularity: str = "paragraphs") -> dict[str, Any]:
        if granularity not in {"lines", "paragraphs"}:
            granularity = "paragraphs"
        left_items = cls._text_blocks(left, granularity)
        right_items = cls._text_blocks(right, granularity)
        left_keys = [cls.normalize_text(item.get("text", "")) for item in left_items]
        right_keys = [cls.normalize_text(item.get("text", "")) for item in right_items]
        matcher = difflib.SequenceMatcher(a=left_keys, b=right_keys, autojunk=False)
        hunks = []
        counts = {"equal": 0, "insert": 0, "delete": 0, "replace": 0}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            counts[tag] += max(i2 - i1, j2 - j1)
            hunks.append(
                {
                    "op": tag,
                    "left_range": [i1 + 1, i2],
                    "right_range": [j1 + 1, j2],
                    "left": left_items[i1:i2],
                    "right": right_items[j1:j2],
                }
            )
        changed = counts["insert"] + counts["delete"] + counts["replace"]
        return {
            "schema_version": 1,
            "kind": "text_diff",
            "granularity": granularity,
            "hunks": hunks,
            "summary": {
                "left_count": len(left_items),
                "right_count": len(right_items),
                "equal": counts["equal"],
                "insert": counts["insert"],
                "delete": counts["delete"],
                "replace": counts["replace"],
                "changed": changed,
            },
        }

    @classmethod
    def diff_tables(cls, left: Any, right: Any) -> dict[str, Any]:
        left_rows = cls._table_rows(left)
        right_rows = cls._table_rows(right)
        left_keys = [cls.normalize_text(row.get("text", "")) for row in left_rows]
        right_keys = [cls.normalize_text(row.get("text", "")) for row in right_rows]
        matcher = difflib.SequenceMatcher(a=left_keys, b=right_keys, autojunk=False)
        hunks = []
        counts = {"equal": 0, "insert": 0, "delete": 0, "replace": 0}
        for tag, i1, i2, j1, j2 in matcher.get_opcodes():
            counts[tag] += max(i2 - i1, j2 - j1)
            hunks.append(
                {
                    "op": tag,
                    "left_range": [i1 + 1, i2],
                    "right_range": [j1 + 1, j2],
                    "left": left_rows[i1:i2],
                    "right": right_rows[j1:j2],
                }
            )
        left_headers = cls._table_headers(left)
        right_headers = cls._table_headers(right)
        return {
            "schema_version": 1,
            "kind": "table_diff",
            "hunks": hunks,
            "schema_changes": {
                "added_headers": sorted(right_headers - left_headers),
                "removed_headers": sorted(left_headers - right_headers),
            },
            "summary": {
                "left_count": len(left_rows),
                "right_count": len(right_rows),
                "equal": counts["equal"],
                "insert": counts["insert"],
                "delete": counts["delete"],
                "replace": counts["replace"],
                "changed": counts["insert"] + counts["delete"] + counts["replace"],
            },
        }

    @classmethod
    def compare_items(cls, left: Any, right: Any, *, min_score: float = 0.2) -> dict[str, Any]:
        left_items = cls._as_items(left)
        right_items = cls._as_items(right)
        matches = []
        matched_right = set()
        for left_index, left_item in enumerate(left_items):
            scored = []
            for right_index, right_item in enumerate(right_items):
                score = cls.similarity(left_item, right_item)
                if score >= min_score:
                    scored.append((score, right_index, right_item))
            scored.sort(key=lambda item: item[0], reverse=True)
            if not scored:
                matches.append(
                    {
                        "match_id": f"match-{len(matches) + 1}",
                        "relation": "missing_in_b",
                        "score": 0.0,
                        "left_item": left_item,
                        "right_item": None,
                        "evidence": {"left": cls._evidence(left_item), "right": None},
                    }
                )
                continue
            score, right_index, right_item = scored[0]
            matched_right.add(right_index)
            matches.append(
                {
                    "match_id": f"match-{len(matches) + 1}",
                    "relation": cls.relation(left_item, right_item, score),
                    "score": score,
                    "left_index": left_index + 1,
                    "right_index": right_index + 1,
                    "left_item": left_item,
                    "right_item": right_item,
                    "evidence": {"left": cls._evidence(left_item), "right": cls._evidence(right_item)},
                }
            )
        for right_index, right_item in enumerate(right_items):
            if right_index in matched_right:
                continue
            matches.append(
                    {
                        "match_id": f"match-{len(matches) + 1}",
                    "relation": "missing_in_a",
                    "score": 0.0,
                    "left_item": None,
                    "right_index": right_index + 1,
                    "right_item": right_item,
                    "evidence": {"left": None, "right": cls._evidence(right_item)},
                }
            )
        missing_left = [item for item in matches if item["relation"] in {"missing_in_a", "missing_in_left"}]
        missing_right = [item for item in matches if item["relation"] in {"missing_in_b", "missing_in_right"}]
        return {
            "schema_version": 1,
            "kind": "semantic_compare",
            "matches": matches,
            "missing_in_left": missing_left,
            "missing_in_right": missing_right,
            "summary": {
                "left_count": len(left_items),
                "right_count": len(right_items),
                "matched": len(matches) - len(missing_left) - len(missing_right),
                "missing_in_left": len(missing_left),
                "missing_in_right": len(missing_right),
            },
        }

    @classmethod
    def detect_conflicts(cls, standard: Any, target: Any, *, min_score: float = 0.18) -> dict[str, Any]:
        compare = cls.compare_items(standard, target, min_score=min_score)
        conflicts = []
        for match in compare["matches"]:
            left_item = match.get("left_item")
            right_item = match.get("right_item")
            if not left_item or not right_item:
                continue
            conflict = cls._conflict(left_item, right_item)
            if not conflict:
                continue
            conflicts.append(
                {
                    "conflict_id": f"conflict-{len(conflicts) + 1}",
                    "relation": "conflict",
                    "severity": conflict["severity"],
                    "reason_code": conflict["reason_code"],
                    "reason": conflict["reason"],
                    "confidence": round(max(match.get("score", 0.0), conflict["confidence"]), 4),
                    "standard_item": left_item,
                    "target_item": right_item,
                    "evidence": match.get("evidence", {}),
                }
            )
        missing_requirements = [match for match in compare["matches"] if match["relation"] in {"missing_in_b", "missing_in_right"}]
        return {
            "schema_version": 1,
            "kind": "conflict_detection",
            "conflicts": conflicts,
            "missing_requirements": missing_requirements,
            "matches": compare["matches"],
            "summary": {
                "conflict_count": len(conflicts),
                "missing_requirement_count": len(missing_requirements),
                "checked_match_count": compare["summary"]["matched"],
            },
        }

    @staticmethod
    def normalize_text(text: Any) -> str:
        raw = str(text or "").lower()
        raw = re.sub(r"\s+", "", raw)
        raw = re.sub(r"[，,。；;：:、.．!?！？（）()\[\]【】\"'“”‘’]", "", raw)
        return raw

    @staticmethod
    def _sha256(text: str) -> str:
        return hashlib.sha256(str(text or "").encode("utf-8")).hexdigest()

    @classmethod
    def similarity(cls, left: Any, right: Any) -> float:
        left_text = cls._item_text(left)
        right_text = cls._item_text(right)
        left_norm = cls.normalize_text(left_text)
        right_norm = cls.normalize_text(right_text)
        if not left_norm or not right_norm:
            return 0.0
        if left_norm == right_norm:
            return 1.0
        if left_norm in right_norm or right_norm in left_norm:
            return 0.92
        left_terms = cls._terms(left_text)
        right_terms = cls._terms(right_text)
        if not left_terms or not right_terms:
            return round(difflib.SequenceMatcher(a=left_norm, b=right_norm, autojunk=False).ratio(), 4)
        overlap = len(left_terms & right_terms)
        jaccard = overlap / max(len(left_terms | right_terms), 1)
        coverage = overlap / max(min(len(left_terms), len(right_terms)), 1)
        ratio = difflib.SequenceMatcher(a=left_norm, b=right_norm, autojunk=False).ratio()
        return round(max(jaccard, coverage * 0.92, ratio * 0.8), 4)

    @classmethod
    def relation(cls, left: Any, right: Any, score: float) -> str:
        left_norm = cls.normalize_text(cls._item_text(left))
        right_norm = cls.normalize_text(cls._item_text(right))
        if left_norm and left_norm == right_norm:
            return "same"
        if left_norm and right_norm and right_norm in left_norm:
            return "a_contains_b"
        if left_norm and right_norm and left_norm in right_norm:
            return "b_contains_a"
        if score >= 0.72:
            return "equivalent"
        if score >= 0.2:
            return "ambiguous"
        return "unmatched"

    @classmethod
    def _conflict(cls, standard_item: Any, target_item: Any) -> dict[str, Any] | None:
        standard_text = cls._item_text(standard_item)
        target_text = cls._item_text(target_item)
        if cls._same_topic(standard_text, target_text, PAYMENT_TERMS):
            standard_days = cls._deadline_days(standard_text)
            target_days = cls._deadline_days(target_text)
            if standard_days and target_days and target_days > standard_days:
                return {
                    "reason_code": "deadline_longer_than_allowed",
                    "reason": f"Target deadline {target_days} days is longer than standard deadline {standard_days} days.",
                    "severity": "medium",
                    "confidence": 0.82,
                }
        if cls._has_prohibition(standard_text) and cls._has_permission(target_text):
            if cls._same_topic(standard_text, target_text, DISCLOSURE_TERMS) or cls.similarity(standard_item, target_item) >= 0.28:
                return {
                    "reason_code": "prohibited_action_permitted",
                    "reason": "Standard prohibits the action while target text permits or exempts it.",
                    "severity": "high",
                    "confidence": 0.86,
                }
        if cls._has_liability(standard_text) and cls._has_liability_exemption(target_text):
            return {
                "reason_code": "liability_exempted",
                "reason": "Standard keeps liability while target text exempts or removes liability.",
                "severity": "high",
                "confidence": 0.84,
            }
        return None

    @classmethod
    def _text_blocks(cls, value: Any, granularity: str) -> list[dict[str, Any]]:
        document = cls._as_document(value)
        key = "lines" if granularity == "lines" else "paragraphs"
        blocks = document.get(key) or []
        if not blocks and granularity == "paragraphs":
            blocks = document.get("chunks") or document.get("lines") or []
        if not blocks and granularity == "lines":
            blocks = document.get("paragraphs") or document.get("chunks") or []
        result = []
        for index, block in enumerate(blocks):
            if isinstance(block, dict):
                text = str(block.get("text") or block.get("content") or "").strip()
                source_ref = block.get("source_ref", "")
                line_start = block.get("line_start") or block.get("line_number")
                line_end = block.get("line_end") or block.get("line_number")
            else:
                text = str(block).strip()
                source_ref = ""
                line_start = None
                line_end = None
            if not text:
                continue
            result.append(
                {
                    "index": len(result) + 1,
                    "text": text,
                    "normalized_text": cls.normalize_text(text),
                    "source_ref": source_ref,
                    "line_start": line_start,
                    "line_end": line_end,
                    "paragraph_index": block.get("paragraph_index") if isinstance(block, dict) else None,
                }
            )
        if not result and isinstance(value, str):
            source_lines = value.splitlines() if granularity == "lines" else re.split(r"\n\s*\n+", value)
            for text in source_lines:
                text = text.strip()
                if text:
                    result.append({"index": len(result) + 1, "text": text, "normalized_text": cls.normalize_text(text), "source_ref": "input"})
        return result

    @classmethod
    def _table_rows(cls, value: Any) -> list[dict[str, Any]]:
        document = cls._as_document(value)
        rows = []
        for table_index, table in enumerate(document.get("tables") or [], start=1):
            headers = [str(item) for item in table.get("headers") or []]
            for row in table.get("rows") or []:
                values = row.get("values") if isinstance(row, dict) else {}
                text = "; ".join(f"{header}: {values.get(header, '')}" for header in headers)
                rows.append(
                    {
                        "index": len(rows) + 1,
                        "table_index": table_index,
                        "row_index": row.get("row_index") if isinstance(row, dict) else None,
                        "headers": headers,
                        "values": values,
                        "text": text,
                        "normalized_text": cls.normalize_text(text),
                        "source_ref": f"{table.get('source_ref', 'table')} | row {row.get('row_index', '')}" if isinstance(row, dict) else table.get("source_ref", "table"),
                    }
                )
        return rows

    @classmethod
    def _table_headers(cls, value: Any) -> set[str]:
        document = cls._as_document(value)
        headers = set()
        for table in document.get("tables") or []:
            headers.update(str(item) for item in table.get("headers") or [])
        return headers

    @classmethod
    def _section_blocks(cls, value: Any) -> list[dict[str, Any]]:
        document = cls._as_document(value)
        sections = []
        for index, section in enumerate(document.get("sections") or []):
            if not isinstance(section, dict):
                continue
            title = str(section.get("title") or section.get("heading") or section.get("text") or "").strip()
            section_path = section.get("section_path") or section.get("path") or ([title] if title else [])
            text = " / ".join(str(item) for item in section_path if item) or title
            if not text:
                continue
            sections.append(
                {
                    "index": len(sections) + 1,
                    "title": title or text,
                    "section_path": section_path,
                    "text": text,
                    "normalized_text": cls.normalize_text(text),
                    "source_ref": section.get("source_ref", ""),
                    "line_start": section.get("line_start"),
                    "line_end": section.get("line_end"),
                }
            )
        if sections:
            return sections
        heading_re = re.compile(r"^\s*(#{1,6}\s+.+|第[一二三四五六七八九十百千万零〇\d]+[章节]\s*.+|\d+(?:\.\d+)*\s+.+)")
        for block in cls._text_blocks(document, "paragraphs"):
            text = block.get("text", "")
            if not heading_re.match(text):
                continue
            sections.append(
                {
                    "index": len(sections) + 1,
                    "title": text.lstrip("# ").strip(),
                    "section_path": [text.lstrip("# ").strip()],
                    "text": text,
                    "normalized_text": cls.normalize_text(text),
                    "source_ref": block.get("source_ref", ""),
                    "line_start": block.get("line_start"),
                    "line_end": block.get("line_end"),
                }
            )
        return sections

    @classmethod
    def _as_items(cls, value: Any) -> list[dict[str, Any]]:
        parsed = cls._parse_json(value)
        if isinstance(parsed, dict):
            for key in ("items", "clauses", "obligations", "risk_points", "viewpoints", "table_facts", "paragraphs", "chunks", "lines"):
                if isinstance(parsed.get(key), list):
                    return [cls._coerce_item(item, index + 1) for index, item in enumerate(parsed[key])]
            if parsed.get("text") or parsed.get("content"):
                return [cls._coerce_item(parsed, 1)]
            return []
        if isinstance(parsed, list):
            return [cls._coerce_item(item, index + 1) for index, item in enumerate(parsed)]
        if isinstance(parsed, str) and parsed.strip():
            return [cls._coerce_item({"text": parsed, "source_ref": "input"}, 1)]
        return []

    @classmethod
    def _as_document(cls, value: Any) -> dict[str, Any]:
        parsed = cls._parse_json(value)
        if isinstance(parsed, dict):
            return parsed
        if isinstance(parsed, list):
            return {"paragraphs": [cls._coerce_item(item, index + 1) for index, item in enumerate(parsed)]}
        if isinstance(parsed, str) and parsed.strip():
            lines = [{"line_number": index + 1, "text": text, "source_ref": f"input | line {index + 1}"} for index, text in enumerate(parsed.splitlines()) if text.strip()]
            return {"paragraphs": [{"paragraph_index": 1, "text": parsed.strip(), "source_ref": "input"}], "lines": lines}
        return {}

    @staticmethod
    def _parse_json(value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ""
            try:
                return json.loads(text)
            except Exception:
                return value
        return value

    @classmethod
    def _coerce_item(cls, item: Any, index: int) -> dict[str, Any]:
        if isinstance(item, dict):
            text = cls._item_text(item)
            return {**item, "item_id": item.get("item_id") or item.get("clause_id") or f"item-{index}", "text": text, "normalized_text": item.get("normalized_text") or cls.normalize_text(text)}
        text = str(item or "")
        return {"item_id": f"item-{index}", "text": text, "normalized_text": cls.normalize_text(text), "evidence": {"source_ref": "input"}}

    @staticmethod
    def _item_text(item: Any) -> str:
        if isinstance(item, dict):
            value = item.get("text") or item.get("content") or item.get("requirement") or item.get("basis_text") or item.get("claim")
            if value is not None:
                return str(value)
            return json.dumps(item, ensure_ascii=False)
        return str(item or "")

    @classmethod
    def _evidence(cls, item: Any) -> dict[str, Any]:
        if not isinstance(item, dict):
            return {"source_ref": ""}
        evidence = item.get("evidence") if isinstance(item.get("evidence"), dict) else {}
        return {
            "source_ref": evidence.get("source_ref") or item.get("source_ref", ""),
            "page": evidence.get("page") or item.get("page"),
            "line_start": evidence.get("line_start") or item.get("line_start") or item.get("line_number"),
            "line_end": evidence.get("line_end") or item.get("line_end") or item.get("line_number"),
            "paragraph_index": evidence.get("paragraph_index") or item.get("paragraph_index"),
        }

    @staticmethod
    def _terms(text: Any) -> set[str]:
        raw = re.sub(r"\s+", " ", str(text or "").lower())
        terms = set(re.findall(r"[a-z0-9_]{2,}", raw))
        for segment in re.findall(r"[\u4e00-\u9fff]{2,}", raw):
            if len(segment) <= 8:
                terms.add(segment)
            for size in (2, 3, 4):
                for idx in range(0, max(len(segment) - size + 1, 0)):
                    terms.add(segment[idx : idx + size])
        for term in PAYMENT_TERMS + DISCLOSURE_TERMS + LIABILITY_TERMS + PROHIBITION_TERMS + PERMISSION_TERMS:
            if term.lower() in raw:
                terms.add(term.lower())
        return {term for term in terms if term}

    @classmethod
    def _same_topic(cls, left: str, right: str, topic_terms: tuple[str, ...]) -> bool:
        left_lower = left.lower()
        right_lower = right.lower()
        has_topic = any(term.lower() in left_lower for term in topic_terms) and any(term.lower() in right_lower for term in topic_terms)
        if has_topic:
            return True
        left_terms = cls._terms(left)
        right_terms = cls._terms(right)
        return len(left_terms & right_terms) >= 3

    @staticmethod
    def _has_prohibition(text: str) -> bool:
        lowered = text.lower()
        return any(term.lower() in lowered for term in PROHIBITION_TERMS)

    @staticmethod
    def _has_permission(text: str) -> bool:
        lowered = text.lower()
        return any(term.lower() in lowered for term in PERMISSION_TERMS)

    @staticmethod
    def _has_liability(text: str) -> bool:
        lowered = text.lower()
        return any(term.lower() in lowered for term in LIABILITY_TERMS)

    @staticmethod
    def _has_liability_exemption(text: str) -> bool:
        lowered = text.lower()
        return any(term in lowered for term in ("不承担", "无需承担", "免除", "概不负责", "自行承担", "waive", "exempt"))

    @classmethod
    def _deadline_days(cls, text: str) -> int | None:
        matches = re.findall(r"(\d+|[一二三四五六七八九十两百千万零〇]+)\s*(工作日|日|天|个月|月|年)", text or "")
        days = []
        for raw_number, unit in matches:
            number = cls._number_value(raw_number)
            if not number:
                continue
            if unit in {"日", "天", "工作日"}:
                days.append(number)
            elif unit in {"月", "个月"}:
                days.append(number * 30)
            elif unit == "年":
                days.append(number * 365)
        return min(days) if days else None

    @staticmethod
    def _number_value(value: str) -> int:
        value = str(value or "").strip()
        if not value:
            return 0
        if value.isdigit():
            return int(value)
        digits = {"零": 0, "〇": 0, "一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8, "九": 9}
        units = {"十": 10, "百": 100, "千": 1000, "万": 10000}
        total = 0
        section = 0
        number = 0
        for char in value:
            if char in digits:
                number = digits[char]
            elif char in units:
                unit = units[char]
                if unit == 10000:
                    section = (section + number) * unit
                    total += section
                    section = 0
                else:
                    section += (number or 1) * unit
                number = 0
        return total + section + number
