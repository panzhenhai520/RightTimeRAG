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

import hashlib
import re
from pathlib import Path
from typing import Any

from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService


class DocumentNormalizeService:
    """Normalize workspace files into line/paragraph/section/table/chunk blocks."""

    DEFAULT_MAX_BYTES = 1024 * 1024
    DEFAULT_CHUNK_CHARS = 2400

    @classmethod
    def normalize(
        cls,
        *,
        path: str,
        root: str = "",
        roots: list[str | Path] | None = None,
        max_bytes: int | None = None,
        chunk_chars: int | None = None,
        tenant_id: str = "",
        user_id: str = "",
        run_id: str = "",
    ) -> dict[str, Any]:
        resolved, root_info = WorkspaceFileService.resolve(path=path, root=root, roots=roots, must_exist=True)
        WorkspaceFileService._require_file(resolved)
        file_info = WorkspaceFileService.file_info(resolved, root_info)
        suffix = resolved.suffix.lower()
        max_bytes = max(1, min(int(max_bytes or cls.DEFAULT_MAX_BYTES), cls.DEFAULT_MAX_BYTES))
        chunk_chars = max(200, min(int(chunk_chars or cls.DEFAULT_CHUNK_CHARS), 20000))

        pages: list[dict[str, Any]] = []
        tables: list[dict[str, Any]] = []
        text = ""
        if suffix in {".csv", ".tsv", ".xlsx"}:
            table = WorkspaceFileService.read_table(
                path=str(resolved),
                roots=[Path(root_info["path"])],
                max_rows=1000,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
            )
            tables.append(cls._table_block(table, file_info))
            text = cls._table_to_text(tables[0])
        elif suffix == ".docx":
            text = cls._docx_text(resolved)
        elif suffix == ".pdf":
            pages, text = cls._pdf_pages(resolved)
        else:
            text = WorkspaceFileService.read_file(
                path=str(resolved),
                roots=[Path(root_info["path"])],
                max_bytes=max_bytes,
                tenant_id=tenant_id,
                user_id=user_id,
                run_id=run_id,
            )["content"]

        document_id = cls.document_id(file_info)
        line_blocks = cls.build_lines(document_id, file_info, text)
        sections = cls.build_sections(document_id, file_info, line_blocks, suffix=suffix)
        paragraphs = cls.build_paragraphs(document_id, file_info, line_blocks, sections)
        chunks = [cls._chunk_from_table(document_id, file_info, tables[0])] if tables else cls.build_chunks(document_id, file_info, paragraphs, chunk_chars=chunk_chars)
        audit = WorkspaceFileService.audit_record(
            "document_normalize",
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            path=str(resolved),
            allowed=True,
        )
        return {
            "schema_version": 1,
            "document_id": document_id,
            "filename": file_info["name"],
            "mime_type": file_info.get("mime_type", ""),
            "source_path": file_info["path"],
            "relative_path": file_info["relative_path"],
            "file": file_info,
            "pages": pages,
            "sections": sections,
            "paragraphs": paragraphs,
            "lines": line_blocks,
            "tables": tables,
            "chunks": chunks,
            "metadata": {
                "extension": suffix,
                "line_count": len(line_blocks),
                "paragraph_count": len(paragraphs),
                "section_count": len(sections),
                "table_count": len(tables),
                "chunk_count": len(chunks),
            },
            "audit": audit,
        }

    @staticmethod
    def document_id(file_info: dict[str, Any]) -> str:
        seed = file_info.get("sha256") or f"{file_info.get('relative_path')}:{file_info.get('size')}:{file_info.get('modified_at')}"
        return hashlib.sha1(str(seed).encode("utf-8")).hexdigest()[:16]

    @classmethod
    def build_lines(cls, document_id: str, file_info: dict[str, Any], text: str) -> list[dict[str, Any]]:
        lines = text.splitlines()
        return [
            {
                "block_id": f"{document_id}:l{index}",
                "document_id": document_id,
                "block_type": "line",
                "text": line,
                "normalized_text": cls.normalize_text(line),
                "line_number": index,
                "source_ref": f"{file_info['relative_path']} | line {index}",
            }
            for index, line in enumerate(lines, start=1)
        ]

    @classmethod
    def build_sections(
        cls,
        document_id: str,
        file_info: dict[str, Any],
        lines: list[dict[str, Any]],
        *,
        suffix: str = "",
    ) -> list[dict[str, Any]]:
        sections = []
        heading_stack: list[str] = []
        for line in lines:
            text = str(line.get("text") or "").strip()
            level = 0
            title = ""
            if suffix == ".md":
                match = re.match(r"^(#{1,6})\s+(.+?)\s*$", text)
                if match:
                    level = len(match.group(1))
                    title = match.group(2).strip()
            else:
                match = re.match(r"^((第[一二三四五六七八九十百千万零〇\d]+[章节条])|(\d+(?:\.\d+)*[、.)]?))\s*(.+)$", text)
                if match and len(text) <= 120:
                    level = 1 + text.count(".")
                    title = text
            if not title:
                continue
            heading_stack = heading_stack[: max(0, level - 1)]
            heading_stack.append(title)
            sections.append(
                {
                    "block_id": f"{document_id}:s{len(sections) + 1}",
                    "document_id": document_id,
                    "block_type": "section",
                    "title": title,
                    "level": level,
                    "section_path": list(heading_stack),
                    "line_start": line["line_number"],
                    "line_end": line["line_number"],
                    "source_ref": f"{file_info['relative_path']} | line {line['line_number']}",
                }
            )
        return sections

    @classmethod
    def build_paragraphs(
        cls,
        document_id: str,
        file_info: dict[str, Any],
        lines: list[dict[str, Any]],
        sections: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        section_by_line = cls._section_path_by_line(sections)
        paragraphs = []
        buffer: list[dict[str, Any]] = []

        def flush():
            if not buffer:
                return
            text = "\n".join(item["text"] for item in buffer).strip()
            if not text:
                buffer.clear()
                return
            line_start = buffer[0]["line_number"]
            line_end = buffer[-1]["line_number"]
            paragraphs.append(
                {
                    "block_id": f"{document_id}:p{len(paragraphs) + 1}",
                    "document_id": document_id,
                    "block_type": "paragraph",
                    "text": text,
                    "normalized_text": cls.normalize_text(text),
                    "paragraph_index": len(paragraphs) + 1,
                    "line_start": line_start,
                    "line_end": line_end,
                    "section_path": section_by_line.get(line_start, []),
                    "source_ref": f"{file_info['relative_path']} | lines {line_start}-{line_end}",
                }
            )
            buffer.clear()

        for line in lines:
            if str(line.get("text") or "").strip():
                buffer.append(line)
            else:
                flush()
        flush()
        return paragraphs

    @classmethod
    def build_chunks(
        cls,
        document_id: str,
        file_info: dict[str, Any],
        paragraphs: list[dict[str, Any]],
        *,
        chunk_chars: int,
    ) -> list[dict[str, Any]]:
        chunks = []
        current: list[dict[str, Any]] = []
        current_len = 0

        def flush():
            nonlocal current, current_len
            if not current:
                return
            text = "\n\n".join(item["text"] for item in current)
            chunks.append(
                {
                    "block_id": f"{document_id}:c{len(chunks) + 1}",
                    "chunk_id": f"{document_id}:c{len(chunks) + 1}",
                    "document_id": document_id,
                    "block_type": "chunk",
                    "text": text,
                    "content": text,
                    "normalized_text": cls.normalize_text(text),
                    "paragraph_start": current[0]["paragraph_index"],
                    "paragraph_end": current[-1]["paragraph_index"],
                    "line_start": current[0]["line_start"],
                    "line_end": current[-1]["line_end"],
                    "section_path": current[0].get("section_path", []),
                    "source_ref": f"{file_info['relative_path']} | paragraphs {current[0]['paragraph_index']}-{current[-1]['paragraph_index']}",
                }
            )
            current = []
            current_len = 0

        for paragraph in paragraphs:
            length = len(paragraph.get("text") or "")
            if current and current_len + length > chunk_chars:
                flush()
            current.append(paragraph)
            current_len += length
        flush()
        return chunks

    @staticmethod
    def normalize_text(text: str) -> str:
        text = re.sub(r"\s+", " ", str(text or "")).strip()
        return text

    @staticmethod
    def _section_path_by_line(sections: list[dict[str, Any]]) -> dict[int, list[str]]:
        result = {}
        current: list[str] = []
        sorted_sections = sorted(sections, key=lambda item: item.get("line_start") or 0)
        section_iter = iter(sorted_sections)
        next_section = next(section_iter, None)
        max_line = max([item.get("line_start") or 0 for item in sorted_sections], default=0)
        for line_number in range(1, max_line + 10000):
            while next_section and int(next_section.get("line_start") or 0) <= line_number:
                current = list(next_section.get("section_path") or [])
                next_section = next(section_iter, None)
            if current:
                result[line_number] = list(current)
            if not next_section and line_number > max_line:
                break
        return result

    @staticmethod
    def _table_block(table: dict[str, Any], file_info: dict[str, Any]) -> dict[str, Any]:
        return {
            "table_id": f"{file_info['relative_path']}:t1",
            "block_type": "table",
            "sheet_name": table.get("sheet_name", ""),
            "headers": table.get("headers", []),
            "rows": table.get("rows", []),
            "row_count": table.get("row_count", len(table.get("rows", []))),
            "truncated": table.get("truncated", False),
            "source_ref": f"{file_info['relative_path']} | table",
        }

    @staticmethod
    def _table_to_text(table: dict[str, Any]) -> str:
        headers = [str(item) for item in table.get("headers") or []]
        lines = [",".join(headers)] if headers else []
        for row in table.get("rows") or []:
            values = row.get("values") if isinstance(row, dict) else {}
            lines.append(",".join(str(values.get(header, "")) for header in headers))
        return "\n".join(lines)

    @staticmethod
    def _chunk_from_table(document_id: str, file_info: dict[str, Any], table: dict[str, Any]) -> dict[str, Any]:
        text = DocumentNormalizeService._table_to_text(table)
        return {
            "block_id": f"{document_id}:c1",
            "chunk_id": f"{document_id}:c1",
            "document_id": document_id,
            "block_type": "chunk",
            "text": text,
            "content": text,
            "normalized_text": DocumentNormalizeService.normalize_text(text),
            "paragraph_start": 0,
            "paragraph_end": 0,
            "line_start": 0,
            "line_end": 0,
            "section_path": [],
            "source_ref": f"{file_info['relative_path']} | table",
        }

    @staticmethod
    def _docx_text(path: Path) -> str:
        try:
            from docx import Document
        except Exception as exc:
            raise WorkspaceFileError("DOCX_READER_UNAVAILABLE", "python-docx is required to read docx files.") from exc
        document = Document(path)
        return "\n\n".join(paragraph.text for paragraph in document.paragraphs if paragraph.text.strip())

    @staticmethod
    def _pdf_pages(path: Path) -> tuple[list[dict[str, Any]], str]:
        try:
            from pypdf import PdfReader
        except Exception as exc:
            raise WorkspaceFileError("PDF_READER_UNAVAILABLE", "pypdf is required to read pdf files.") from exc
        reader = PdfReader(str(path))
        pages = []
        texts = []
        for index, page in enumerate(reader.pages, start=1):
            text = page.extract_text() or ""
            pages.append({"page": index, "text": text, "source_ref": f"{path.name} | page {index}"})
            texts.append(text)
        return pages, "\n\n".join(texts)
