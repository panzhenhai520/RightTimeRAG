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
from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.utils.api_utils import timeout


class CitationFormatterParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.references = ""
        self.content = ""
        self.include_content = False
        self.max_items = 80
        self.outputs = {
            "citations": {"value": [], "type": "Array<JSON>"},
            "references": {"value": [], "type": "Array<JSON>"},
            "markdown": {"value": "", "type": "string"},
            "content": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "references": {"type": "Array<JSON>", "required": True},
            "content": {"type": "string", "required": False},
        }

    def check(self):
        self.check_positive_integer(self.max_items, "[CitationFormatter] Max items")


class CitationFormatter(ComponentBase, ABC):
    component_name = "CitationFormatter"

    def get_input_form(self) -> dict[str, dict]:
        return {
            "references": {"name": "References", "type": "line"},
            "content": {"name": "Content", "type": "line"},
        }

    @staticmethod
    def _first_page(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, list):
            return value[0] if value else None
        return value

    @classmethod
    def _source_ref(cls, citation: dict[str, Any]) -> str:
        document_name = citation.get("document_name") or citation.get("docnm_kwd") or citation.get("doc_name") or "document"
        parts = [str(document_name)]
        page = cls._first_page(citation.get("page") if citation.get("page") is not None else citation.get("page_num_int"))
        chunk_id = citation.get("chunk_id") or citation.get("id")
        articles = citation.get("article_numbers") or []
        if page is not None:
            parts.append(f"page {page}")
        if chunk_id:
            parts.append(f"chunk {chunk_id}")
        if articles:
            if not isinstance(articles, list):
                articles = [articles]
            parts.append("article " + ",".join(str(item) for item in articles))
        return " | ".join(parts)

    @classmethod
    def _iter_reference_items(cls, value: Any):
        if value is None:
            return
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return
            try:
                parsed = json.loads(text)
            except Exception:
                yield {"content": text}
                return
            yield from cls._iter_reference_items(parsed)
            return
        if isinstance(value, dict):
            if isinstance(value.get("references"), list):
                yield from cls._iter_reference_items(value.get("references"))
                return
            if isinstance(value.get("matches"), list):
                yield from cls._iter_reference_items(value.get("matches"))
                return
            chunks = value.get("chunks")
            if isinstance(chunks, dict):
                yield from cls._iter_reference_items(list(chunks.values()))
                return
            if isinstance(chunks, list):
                yield from cls._iter_reference_items(chunks)
                return
            yield value
            return
        if isinstance(value, (list, tuple)):
            for item in value:
                yield from cls._iter_reference_items(item)

    @classmethod
    def normalize_references(cls, value: Any, max_items: int = 80) -> list[dict[str, Any]]:
        citations = []
        seen = set()
        for item in cls._iter_reference_items(value) or []:
            if not isinstance(item, dict):
                continue
            content = str(item.get("content") or item.get("content_with_weight") or "").strip()
            document_id = item.get("document_id") or item.get("file_id") or item.get("doc_id")
            file_id = item.get("file_id") or document_id
            document_name = item.get("document_name") or item.get("docnm_kwd") or item.get("doc_name") or item.get("name")
            page = cls._first_page(item.get("page") if item.get("page") is not None else item.get("page_num_int"))
            page_num_int = item.get("page_num_int")
            if page_num_int is None and page is not None:
                page_num_int = [page]
            chunk_id = item.get("chunk_id") or item.get("id")
            citation = {
                "file_id": file_id,
                "document_id": document_id,
                "document_name": document_name,
                "chunk_id": chunk_id,
                "page": page,
                "page_num_int": page_num_int or [],
                "article_numbers": item.get("article_numbers") or [],
                "score": item.get("score"),
                "content": content,
            }
            citation["source_ref"] = item.get("source_ref") or cls._source_ref(citation)
            key = (
                str(citation.get("file_id") or ""),
                str(citation.get("chunk_id") or ""),
                str(citation.get("source_ref") or ""),
                content[:120],
            )
            if key in seen:
                continue
            seen.add(key)
            citations.append(citation)
            if len(citations) >= max_items:
                break
        return citations

    @staticmethod
    def format_markdown(citations: list[dict[str, Any]], include_content: bool = False) -> str:
        lines = []
        for idx, citation in enumerate(citations, start=1):
            source_ref = citation.get("source_ref") or citation.get("document_name") or "document"
            lines.append(f"{idx}. {source_ref}")
            file_id = citation.get("file_id")
            if file_id:
                lines.append(f"   - file_id: {file_id}")
            if include_content and citation.get("content"):
                lines.append(f"   - content: {citation['content']}")
        return "\n".join(lines)

    def _resolve_value(self, value: Any, fallback: Any = None) -> Any:
        if value in (None, ""):
            return fallback
        if not isinstance(value, str):
            return value
        try:
            if self._canvas.is_reff(value):
                return self._canvas.get_variable_value(value)
            if "@" in value and "{" in value:
                return self._canvas.get_value_with_variable(value)
        except Exception:
            return fallback if fallback is not None else value
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("CitationFormatter processing"):
            return
        references = self._resolve_value(self._param.references, kwargs.get("references"))
        content = self._resolve_value(self._param.content, kwargs.get("content")) or ""
        citations = self.normalize_references(references, max_items=int(self._param.max_items or 80))
        markdown = self.format_markdown(citations, include_content=bool(self._param.include_content))
        self.set_output("citations", citations)
        self.set_output("references", citations)
        self.set_output("markdown", markdown)
        self.set_output("content", str(content))

    def thoughts(self) -> str:
        return "Formatting source citations."
