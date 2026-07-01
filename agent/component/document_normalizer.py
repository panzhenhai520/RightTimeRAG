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

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.document_normalize_service import DocumentNormalizeService


class DocumentNormalizerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.path = ""
        self.max_bytes = 1048576
        self.chunk_chars = 2400
        self.outputs = {
            "document": {"value": {}, "type": "TextDocument"},
            "lines": {"value": [], "type": "Array<JSON>"},
            "paragraphs": {"value": [], "type": "Array<JSON>"},
            "sections": {"value": [], "type": "Array<JSON>"},
            "tables": {"value": [], "type": "Array<JSON>"},
            "chunks": {"value": [], "type": "Array<TextChunk>"},
            "metadata": {"value": {}, "type": "JSON"},
            "audit": {"value": {}, "type": "JSON"},
        }

    def check(self):
        self.check_empty(self.path, "[DocumentNormalizer] Path")
        self.check_positive_integer(int(self.max_bytes), "[DocumentNormalizer] Max bytes")
        self.check_positive_integer(int(self.chunk_chars), "[DocumentNormalizer] Chunk chars")


class DocumentNormalizer(ComponentBase, ABC):
    component_name = "DocumentNormalizer"

    def _tenant_id(self) -> str:
        return self._canvas.get_tenant_id() if hasattr(self._canvas, "get_tenant_id") else ""

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        document = DocumentNormalizeService.normalize(
            root=str(self._resolve(self._param.root) or ""),
            path=str(self._resolve(self._param.path) or ""),
            max_bytes=int(self._param.max_bytes or 1048576),
            chunk_chars=int(self._param.chunk_chars or 2400),
            tenant_id=self._tenant_id(),
            run_id=getattr(self._canvas, "_run_id", ""),
        )
        self.set_output("document", document)
        self.set_output("lines", document.get("lines", []))
        self.set_output("paragraphs", document.get("paragraphs", []))
        self.set_output("sections", document.get("sections", []))
        self.set_output("tables", document.get("tables", []))
        self.set_output("chunks", document.get("chunks", []))
        self.set_output("metadata", document.get("metadata", {}))
        self.set_output("audit", document.get("audit", {}))
