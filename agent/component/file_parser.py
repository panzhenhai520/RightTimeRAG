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

import os
import re
from abc import ABC

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.file_service import FileService
from api.utils.api_utils import timeout


FILE_PARSER_LAYOUT_RECOGNIZE_OPTIONS = [
    {"label": "Plain Text", "value": "Plain Text", "description": "Use embedded PDF/text extraction without OCR."},
    {"label": "DeepDOC", "value": "DeepDOC", "description": "Use local OCR and layout recognition models."},
    {"label": "Docling", "value": "Docling", "description": "Use the configured Docling parser service."},
    {"label": "OpenDataLoader", "value": "OpenDataLoader", "description": "Use the configured OpenDataLoader OCR service."},
    {"label": "TCADP Parser", "value": "TCADP Parser", "description": "Use the configured TCADP parser."},
]


def _default_layout_recognize() -> str:
    value = os.environ.get("AGENT_FILE_PARSER_LAYOUT_RECOGNIZE", "Plain Text")
    return value.strip() or "Plain Text"


class FileParserParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.input_files = ["sys.file_assets"]
        self.query = "{sys.query}"
        self.parser_id = "auto"
        self.layout_recognize = _default_layout_recognize()
        self.chunk_token_num = 1200
        self.from_page = 0
        self.to_page = 100000
        self.top_n = 12
        self.context_window = 0
        self.max_content_chars = 12000
        self.outputs = {
            "chunks": {"type": "Array<TextChunk>", "value": []},
            "matches": {"type": "Array<TextChunk>", "value": []},
            "references": {"type": "Array<JSON>", "value": []},
            "file_info": {"type": "Array<JSON>", "value": []},
            "content": {"type": "string", "value": ""},
            "summary": {"type": "string", "value": ""},
        }
        self.config_schema = {
            "layout_recognize": {
                "type": "string",
                "ui": "select-with-search",
                "label": "Layout recognize",
                "default": self.layout_recognize,
                "allow_custom": True,
                "options": FILE_PARSER_LAYOUT_RECOGNIZE_OPTIONS,
                "health_check": {
                    "type": "local_ocr_deepdoc",
                    "method": "GET",
                    "endpoint": "/api/v1/agents/file-parser/health",
                    "param": "layout_recognize",
                },
            },
            "parser_id": {
                "type": "string",
                "ui": "select",
                "label": "Parser",
                "default": self.parser_id,
                "options": [
                    {"label": "Auto", "value": "auto"},
                    {"label": "Naive", "value": "naive"},
                    {"label": "Laws", "value": "laws"},
                    {"label": "Paper", "value": "paper"},
                    {"label": "Book", "value": "book"},
                    {"label": "Manual", "value": "manual"},
                    {"label": "One", "value": "one"},
                ],
            },
        }

    def check(self):
        if not isinstance(self.layout_recognize, str) or not self.layout_recognize.strip():
            raise ValueError("[FileParser] Layout recognize should be a non-empty string")
        self.check_positive_integer(self.chunk_token_num, "[FileParser] Chunk token number")
        self.check_positive_integer(self.top_n, "[FileParser] Top N")
        self.check_nonnegative_number(self.context_window, "[FileParser] Context window")
        if int(self.context_window) != self.context_window or self.context_window > 5:
            raise ValueError("[FileParser] Context window should be an integer in range [0, 5]")
        self.check_positive_integer(self.max_content_chars, "[FileParser] Max content chars")


class FileParser(ComponentBase, ABC):
    component_name = "FileParser"
    _local_deepdoc_layouts = {"deepdoc"}
    _deepdoc_required_files = (
        "det.onnx",
        "rec.onnx",
        "ocr.res",
        "layout.onnx",
        "tsr.onnx",
        "updown_concat_xgb.model",
    )
    _noise_terms = {
        "有关",
        "相关",
        "关于",
        "一下",
        "请问",
        "是否",
        "有没有",
        "什么",
        "哪些",
        "怎么",
        "如何",
        "找出",
        "出来",
        "提取",
        "解析",
        "分析",
        "报告",
        "生成",
        "上传",
        "文件",
        "内容",
        "材料",
    }
    _topic_expansion_groups = (
        (
            ("婚姻", "夫妻", "结婚", "离婚", "婚姻家庭"),
            ("婚姻家庭", "夫妻", "配偶", "结婚", "离婚", "子女", "抚养", "共同财产", "亲子", "收养"),
        ),
        (
            ("继承", "遗产", "遗嘱"),
            ("继承", "遗产", "遗嘱", "继承人", "遗赠", "法定继承", "遗嘱继承"),
        ),
        (
            ("监护", "未成年", "无民事行为能力", "限制民事行为能力"),
            ("监护", "监护人", "未成年", "无民事行为能力", "限制民事行为能力", "民事行为能力"),
        ),
        (
            ("合同", "协议", "违约", "履行"),
            ("合同", "协议", "违约", "履行", "解除", "终止", "赔偿", "责任", "义务", "权利"),
        ),
        (
            ("公司", "股东", "董事", "章程"),
            ("公司", "股东", "董事", "监事", "章程", "出资", "股权", "表决权"),
        ),
        (
            ("税", "税务", "纳税"),
            ("税", "税务", "纳税", "免税", "征收", "扣缴", "申报", "税率"),
        ),
    )
    _cn_number_map = {
        "零": 0,
        "〇": 0,
        "一": 1,
        "二": 2,
        "两": 2,
        "三": 3,
        "四": 4,
        "五": 5,
        "六": 6,
        "七": 7,
        "八": 8,
        "九": 9,
    }
    _cn_unit_map = {"十": 10, "百": 100, "千": 1000, "万": 10000}

    def get_input_form(self) -> dict[str, dict]:
        res = {}
        for ref in self._param.input_files or []:
            if isinstance(ref, str):
                for k, o in self.get_input_elements_from_text(ref).items():
                    res[k] = {"name": o.get("name", ""), "type": "file"}
        if self._param.query:
            for k, o in self.get_input_elements_from_text(self._param.query).items():
                res[k] = {"name": o.get("name", ""), "type": "line"}
        return res

    @staticmethod
    def _normalize_layout_recognize(layout_recognize) -> str:
        if isinstance(layout_recognize, bool):
            return "DeepDOC" if layout_recognize else "Plain Text"
        return str(layout_recognize or _default_layout_recognize()).strip() or "Plain Text"

    @classmethod
    def local_ocr_deepdoc_health(cls, layout_recognize: str = "DeepDOC", deep: bool = False) -> dict:
        layout = cls._normalize_layout_recognize(layout_recognize)
        layout_key = layout.lower()
        layout_type = os.environ.get("LAYOUT_RECOGNIZER_TYPE", "onnx").strip().lower() or "onnx"
        checks: list[dict] = []

        def add_check(name: str, ok: bool, message: str, severity: str = "error", details: dict | None = None):
            item = {"name": name, "ok": bool(ok), "message": message, "severity": severity}
            if details:
                item["details"] = details
            checks.append(item)

        if layout_key in {"plain text", "plaintext"}:
            add_check("layout_mode", True, "Plain Text does not use local OCR or DeepDOC.", "info")
            return {
                "status": "ok",
                "healthy": True,
                "layout_recognize": layout,
                "local_ocr_required": False,
                "checks": checks,
                "env": {"LAYOUT_RECOGNIZER_TYPE": layout_type},
            }

        if layout_key not in cls._local_deepdoc_layouts:
            add_check("layout_mode", True, f"{layout} is not the local DeepDOC parser; use its own service/provider check.", "info")
            return {
                "status": "not_applicable",
                "healthy": True,
                "layout_recognize": layout,
                "local_ocr_required": False,
                "checks": checks,
                "env": {"LAYOUT_RECOGNIZER_TYPE": layout_type},
            }

        try:
            import importlib

            importlib.import_module("deepdoc.parser.pdf_parser")
            vision_module = importlib.import_module("deepdoc.vision")
            for attr in ("OCR", "LayoutRecognizer", "TableStructureRecognizer"):
                getattr(vision_module, attr)
            add_check("deepdoc_imports", True, "DeepDOC parser and vision classes are importable.", "error")
        except Exception as exc:
            add_check("deepdoc_imports", False, f"DeepDOC import failed: {exc}", "error")

        add_check(
            "layout_recognizer_type",
            layout_type in {"onnx", "ascend"},
            f"LAYOUT_RECOGNIZER_TYPE={layout_type}",
            "error",
        )

        if os.environ.get("DEEPDOC_URL") or os.environ.get("TENSORRT_DLA_SVR"):
            add_check(
                "layout_service_mode",
                True,
                "Remote DLA layout service is configured; OCR still uses local DeepDOC resources.",
                "warning",
                {
                    "DEEPDOC_URL": bool(os.environ.get("DEEPDOC_URL")),
                    "TENSORRT_DLA_SVR": bool(os.environ.get("TENSORRT_DLA_SVR")),
                },
            )

        try:
            from common.file_utils import get_project_base_directory

            model_dir = os.path.join(get_project_base_directory(), "rag/res/deepdoc")
            missing = [name for name in cls._deepdoc_required_files if not os.path.exists(os.path.join(model_dir, name))]
            add_check(
                "local_model_files",
                not missing,
                "All required DeepDOC local model files are present." if not missing else "Missing DeepDOC local model files.",
                "error",
                {"model_dir": model_dir, "missing": missing},
            )
        except Exception as exc:
            missing = cls._deepdoc_required_files
            add_check("local_model_files", False, f"Could not inspect DeepDOC model files: {exc}", "error")

        if deep:
            if missing:
                add_check(
                    "deep_probe",
                    False,
                    "Skipped model instantiation because local files are missing; instantiation may trigger an external download.",
                    "error",
                )
            else:
                try:
                    from deepdoc.vision import LayoutRecognizer, OCR, TableStructureRecognizer

                    OCR()
                    if layout_type == "onnx":
                        LayoutRecognizer("layout")
                    TableStructureRecognizer()
                    add_check("deep_probe", True, "Local OCR, layout, and table models instantiated successfully.", "error")
                except Exception as exc:
                    add_check("deep_probe", False, f"Local DeepDOC model instantiation failed: {exc}", "error")

        failed = [check for check in checks if not check["ok"] and check["severity"] == "error"]
        return {
            "status": "ok" if not failed else "unhealthy",
            "healthy": not failed,
            "layout_recognize": layout,
            "local_ocr_required": True,
            "checks": checks,
            "env": {
                "LAYOUT_RECOGNIZER_TYPE": layout_type,
                "AGENT_FILE_PARSER_LAYOUT_RECOGNIZE": os.environ.get("AGENT_FILE_PARSER_LAYOUT_RECOGNIZE", ""),
            },
        }

    @staticmethod
    def _text_chunks(text: str, filename: str, file_id: str = "") -> list[dict]:
        text = str(text or "").strip()
        if not text:
            return []
        size = 2400
        chunks = []
        for idx, start in enumerate(range(0, len(text), size)):
            content = text[start:start + size].strip()
            if not content:
                continue
            chunk_id = f"{file_id or filename}:text:{idx}"
            chunks.append(
                {
                    "id": chunk_id,
                    "chunk_id": chunk_id,
                    "document_id": file_id,
                    "docnm_kwd": filename,
                    "document_name": filename,
                    "content": content,
                    "content_with_weight": content,
                    "page_num_int": [],
                    "page": None,
                    "source_index": idx,
                }
            )
        return chunks

    @classmethod
    def _is_noise_term(cls, term: str) -> bool:
        if not term:
            return True
        if term in cls._noise_terms:
            return True
        if len(term) <= 1:
            return True
        return False

    @classmethod
    def _topic_expansions(cls, query: str) -> set[str]:
        normalized = str(query or "").lower()
        expansions = set()
        for triggers, terms in cls._topic_expansion_groups:
            if any(trigger.lower() in normalized for trigger in triggers):
                expansions.update(terms)
        return expansions

    @staticmethod
    def _keywords(query: str) -> list[str]:
        query = str(query or "").lower()
        terms = set()
        for token in re.findall(r"[a-z0-9_]+|[\u4e00-\u9fff]{2,}", query):
            if len(token) < 2:
                continue
            terms.add(token)
            if re.fullmatch(r"[\u4e00-\u9fff]+", token):
                for n in (2, 3, 4):
                    for idx in range(0, max(0, len(token) - n + 1)):
                        terms.add(token[idx:idx + n])
        terms.update(FileParser._topic_expansions(query))
        terms = {term for term in terms if not FileParser._is_noise_term(term)}
        return sorted(terms, key=len, reverse=True)

    @classmethod
    def _source_ref(cls, chunk: dict) -> str:
        document_name = chunk.get("document_name") or chunk.get("docnm_kwd") or "document"
        chunk_id = chunk.get("chunk_id") or chunk.get("id") or chunk.get("source_index")
        page = chunk.get("page")
        page_nums = chunk.get("page_num_int") or []
        if page is None and page_nums:
            page = page_nums[0] if len(page_nums) == 1 else ",".join(str(item) for item in page_nums)
        articles = chunk.get("article_numbers")
        if articles is None:
            articles = cls._article_numbers(chunk.get("content") or chunk.get("content_with_weight") or "")

        parts = [str(document_name)]
        if page is not None:
            parts.append(f"page {page}")
        if chunk_id is not None:
            parts.append(f"chunk {chunk_id}")
        if articles:
            parts.append("article " + ",".join(str(item) for item in articles))
        return " | ".join(parts)

    @classmethod
    def _compact_chunk(cls, chunk: dict) -> dict:
        content = chunk.get("content") or chunk.get("content_with_weight") or ""
        article_numbers = chunk.get("article_numbers")
        if article_numbers is None:
            article_numbers = cls._article_numbers(content)
        page = chunk.get("page")
        page_num_int = chunk.get("page_num_int") or []
        if page is None and page_num_int:
            page = page_num_int[0]
        return {
            "id": chunk.get("id") or chunk.get("chunk_id"),
            "chunk_id": chunk.get("chunk_id") or chunk.get("id"),
            "file_id": chunk.get("file_id") or chunk.get("document_id"),
            "document_id": chunk.get("document_id") or chunk.get("file_id"),
            "document_name": chunk.get("document_name") or chunk.get("docnm_kwd"),
            "docnm_kwd": chunk.get("docnm_kwd") or chunk.get("document_name"),
            "page": page,
            "page_num_int": page_num_int,
            "article_numbers": article_numbers,
            "content": content,
            "content_with_weight": chunk.get("content_with_weight") or chunk.get("content") or "",
            "score": chunk.get("score", 0),
            "source_index": chunk.get("source_index", 0),
            "source_ref": cls._source_ref({**chunk, "page": page, "article_numbers": article_numbers}),
        }

    @staticmethod
    def _source_index(chunk: dict) -> int | None:
        try:
            return int(chunk.get("source_index"))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _document_key(chunk: dict) -> str:
        return str(
            chunk.get("document_id")
            or chunk.get("file_id")
            or chunk.get("document_name")
            or chunk.get("docnm_kwd")
            or ""
        )

    @classmethod
    def _chunk_key(cls, chunk: dict) -> tuple:
        return (
            cls._document_key(chunk),
            chunk.get("chunk_id") or chunk.get("id") or "",
            cls._source_index(chunk),
            str(chunk.get("content") or chunk.get("content_with_weight") or "")[:80],
        )

    @staticmethod
    def _is_toc_like(text: str) -> bool:
        text = str(text or "")
        if not text:
            return False

        head = text[:160]
        if "目录" in head or "目 录" in head:
            return True

        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if not lines:
            return False

        leader_count = sum(
            1
            for line in lines
            if re.search(r"([\.．·…]\s*){3,}", line)
            or re.search(r"\s\d{1,4}\s*$", line)
        )
        return leader_count >= 3 and leader_count / max(len(lines), 1) >= 0.25

    @staticmethod
    def _legal_article_count(text: str) -> int:
        return len(re.findall(r"第[一二三四五六七八九十百千万零〇\d]+条", str(text or "")))

    @classmethod
    def _parse_article_number(cls, value: str) -> int | None:
        text = str(value or "").strip()
        if not text:
            return None
        if text.isdigit():
            return int(text)
        total = 0
        section = 0
        number = 0
        for ch in text:
            if ch in cls._cn_number_map:
                number = cls._cn_number_map[ch]
                continue
            unit = cls._cn_unit_map.get(ch)
            if not unit:
                return None
            if unit == 10000:
                section = (section + number) * unit
                total += section
                section = 0
            else:
                section += (number or 1) * unit
            number = 0
        return total + section + number

    @classmethod
    def _article_numbers(cls, text: str) -> list[int]:
        nums = []
        for raw in re.findall(r"第([一二三四五六七八九十百千万零〇两\d]+)条", str(text or "")):
            parsed = cls._parse_article_number(raw)
            if parsed is not None:
                nums.append(parsed)
        return nums

    @classmethod
    def _query_article_ranges(cls, query: str) -> list[tuple[int, int]]:
        text = str(query or "")
        num = r"[一二三四五六七八九十百千万零〇两\d]+"
        ranges = []
        for start, end in re.findall(
            rf"第?({num})条?\s*(?:至|到|—|-|－|~|～)\s*第?({num})条",
            text,
        ):
            start_num = cls._parse_article_number(start)
            end_num = cls._parse_article_number(end)
            if start_num is None or end_num is None:
                continue
            if start_num > end_num:
                start_num, end_num = end_num, start_num
            ranges.append((start_num, end_num))

        for single in re.findall(rf"第({num})条", text):
            parsed = cls._parse_article_number(single)
            if parsed is not None and all(not (start <= parsed <= end) for start, end in ranges):
                ranges.append((parsed, parsed))
        return ranges

    @classmethod
    def _match_article_ranges(cls, chunks: list[dict], ranges: list[tuple[int, int]]) -> list[dict]:
        if not ranges:
            return []
        matched = []
        for chunk in chunks:
            text = str(chunk.get("content") or chunk.get("content_with_weight") or "")
            article_numbers = cls._article_numbers(text)
            if not article_numbers:
                continue
            hits = [
                article
                for article in article_numbers
                if any(start <= article <= end for start, end in ranges)
            ]
            if not hits:
                continue
            item = dict(chunk)
            item["score"] = 100000 + len(hits) * 100 + min(hits)
            item["article_numbers"] = hits
            matched.append(item)
        matched.sort(
            key=lambda item: (
                item.get("document_name") or item.get("docnm_kwd") or "",
                item.get("source_index", 0),
            )
        )
        return matched

    @staticmethod
    def _is_legal_or_policy_query(query: str) -> bool:
        return bool(
            re.search(
                r"法律|法规|条例|办法|规定|政策|条款|条文|合同|协议|民法典|婚姻|继承|监护|税务|公司|信托",
                str(query or ""),
            )
        )

    def _resolve_query(self) -> str:
        query = self._param.query or ""
        if not isinstance(query, str):
            return str(query)
        elements = self.get_input_elements_from_text(query)
        if not elements:
            return query
        values = {k: str(v.get("value") or "") for k, v in elements.items()}
        return self.string_format(query, values)

    def _iter_assets(self):
        for ref in self._param.input_files or []:
            value = self._canvas.get_variable_value(ref) if isinstance(ref, str) else ref
            if value is None:
                continue
            if isinstance(value, list):
                for item in value:
                    yield item
            else:
                yield value

    @staticmethod
    def _asset_info(asset) -> dict:
        if isinstance(asset, str):
            return {
                "id": "",
                "name": "text_input",
                "created_by": "",
                "mime_type": "text/plain",
                "size": len(asset.encode("utf-8")),
                "source": "inline_text",
            }
        if not isinstance(asset, dict):
            return {
                "id": "",
                "name": "uploaded_file",
                "created_by": "",
                "mime_type": "",
                "size": 0,
                "source": type(asset).__name__,
            }
        return {
            "id": asset.get("id") or asset.get("file_id") or "",
            "name": asset.get("name") or asset.get("filename") or "uploaded_file",
            "created_by": asset.get("created_by") or asset.get("tenant_id") or "",
            "mime_type": asset.get("mime_type") or asset.get("type") or "",
            "size": asset.get("size") or asset.get("file_size") or 0,
            "source": "file_asset",
        }

    def _parse_asset(self, asset) -> list[dict]:
        if isinstance(asset, str):
            return self._text_chunks(asset, "text_input")
        if not isinstance(asset, dict):
            return []

        filename = asset.get("name") or asset.get("filename") or "uploaded_file"
        file_id = asset.get("id") or asset.get("file_id") or ""
        created_by = asset.get("created_by") or self._canvas.get_tenant_id()

        if file_id and created_by:
            blob = FileService.get_blob(created_by, file_id)
            chunks = FileService.parse_file_to_chunks(
                filename,
                blob,
                tenant_id=created_by,
                layout_recognize=self._param.layout_recognize,
                parser_id=self._param.parser_id,
                chunk_token_num=self._param.chunk_token_num,
                from_page=self._param.from_page,
                to_page=self._param.to_page,
            )
        else:
            chunks = self._text_chunks(asset.get("text") or asset.get("parsed_text") or "", filename, file_id)

        for idx, chunk in enumerate(chunks):
            chunk["file_id"] = file_id
            chunk["document_id"] = chunk.get("document_id") or file_id
            chunk["id"] = chunk.get("id") or f"{file_id or filename}:{idx}"
            chunk["chunk_id"] = chunk.get("chunk_id") or chunk["id"]
            chunk["source_index"] = idx
        return chunks

    def _select_matches(self, chunks: list[dict], query: str) -> list[dict]:
        article_ranges = self._query_article_ranges(query)
        article_matches = self._match_article_ranges(chunks, article_ranges)
        if article_matches:
            selected = article_matches[: self._param.top_n]
            return self._expand_context_matches(chunks, selected)

        terms = self._keywords(query)
        if not terms:
            return chunks[: self._param.top_n]

        scored = []
        is_legal_or_policy_query = self._is_legal_or_policy_query(query)
        for chunk in chunks:
            text = str(chunk.get("content") or chunk.get("content_with_weight") or "").lower()
            score = 0
            for term in terms:
                if term and term in text:
                    score += max(1, len(term) - 1) * text.count(term)
            if score > 0:
                item = dict(chunk)
                if is_legal_or_policy_query:
                    article_count = self._legal_article_count(text)
                    if article_count:
                        score += min(article_count, 8) * 8
                    if self._is_toc_like(text):
                        score = max(1, score * 0.15)
                item["score"] = score
                scored.append(item)
        scored.sort(key=lambda item: item.get("score", 0), reverse=True)
        selected = scored[: self._param.top_n]
        selected = self._expand_context_matches(chunks, selected)
        if is_legal_or_policy_query or int(getattr(self._param, "context_window", 0) or 0) > 0:
            selected.sort(
                key=lambda item: (
                    item.get("document_name") or item.get("docnm_kwd") or "",
                    item.get("source_index", 0),
                )
            )
        return selected

    def _expand_context_matches(self, chunks: list[dict], selected: list[dict]) -> list[dict]:
        context_window = int(getattr(self._param, "context_window", 0) or 0)
        if context_window <= 0 or not selected:
            return selected

        by_doc_and_index: dict[str, dict[int, dict]] = {}
        for chunk in chunks:
            doc_key = self._document_key(chunk)
            source_index = self._source_index(chunk)
            if not doc_key or source_index is None:
                continue
            by_doc_and_index.setdefault(doc_key, {})[source_index] = chunk

        selected_by_key = {self._chunk_key(chunk): chunk for chunk in selected}
        expanded = []
        seen = set()

        for match in selected:
            doc_key = self._document_key(match)
            source_index = self._source_index(match)
            nearby = []
            if doc_key and source_index is not None:
                doc_chunks = by_doc_and_index.get(doc_key, {})
                for index in range(source_index - context_window, source_index + context_window + 1):
                    chunk = doc_chunks.get(index)
                    if chunk is not None:
                        nearby.append(chunk)
            else:
                nearby.append(match)

            for chunk in nearby:
                key = self._chunk_key(chunk)
                if key in seen:
                    continue
                seen.add(key)
                expanded.append(dict(selected_by_key.get(key, chunk)))

        return expanded

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        if self.check_if_canceled("FileParser processing"):
            return

        chunks = []
        file_info = []
        for asset in self._iter_assets():
            if self.check_if_canceled("FileParser parsing"):
                return
            file_info.append(self._asset_info(asset))
            chunks.extend(self._parse_asset(asset))

        query = self._resolve_query()
        matches = self._select_matches(chunks, query)
        compact_matches = [self._compact_chunk(chunk) for chunk in matches]
        compact_chunks = [self._compact_chunk(chunk) for chunk in chunks]

        content_parts = []
        used_chars = 0
        for idx, chunk in enumerate(compact_matches, start=1):
            text = chunk.get("content", "")
            prefix = f"[Chunk {idx} | {chunk.get('source_ref') or chunk.get('document_name')}]\n"
            block = prefix + text
            if used_chars + len(block) > self._param.max_content_chars:
                break
            content_parts.append(block)
            used_chars += len(block)

        doc_infos = {}
        for chunk in compact_matches:
            name = chunk.get("document_name") or chunk.get("docnm_kwd") or "file"
            doc_infos[name] = {
                "doc_id": chunk.get("document_id") or chunk.get("file_id") or name,
                "doc_name": name,
                "count": doc_infos.get(name, {}).get("count", 0) + 1,
            }
        if compact_matches:
            self._canvas.add_reference(compact_matches, list(doc_infos.values()))

        summary = f"Parsed {len(chunks)} chunk(s); selected {len(compact_matches)} chunk(s)."
        self.set_output("chunks", compact_chunks)
        self.set_output("matches", compact_matches)
        self.set_output("file_info", file_info)
        self.set_output(
            "references",
            [
                {
                    "source_ref": chunk.get("source_ref"),
                    "file_id": chunk.get("file_id") or chunk.get("document_id"),
                    "document_id": chunk.get("document_id"),
                    "document_name": chunk.get("document_name"),
                    "chunk_id": chunk.get("chunk_id"),
                    "page": chunk.get("page"),
                    "page_num_int": chunk.get("page_num_int"),
                    "article_numbers": chunk.get("article_numbers"),
                    "score": chunk.get("score"),
                }
                for chunk in compact_matches
            ],
        )
        self.set_output("content", "\n\n".join(content_parts))
        self.set_output("summary", summary)

    def thoughts(self) -> str:
        return "Parsing uploaded files and selecting relevant chunks."
