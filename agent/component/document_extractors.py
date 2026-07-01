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
from api.db.services.document_extract_service import DocumentExtractService


class _BaseExtractorParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.document = ""
        self.content = ""
        self.min_chars = 4
        self.outputs = {
            "items": {"value": [], "type": "Array<JSON>"},
            "references": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "String"},
        }
        self.input_schema = {
            "document": {"type": "TextDocument", "required": False},
            "content": {"type": "String", "required": False},
        }

    def check(self):
        self.check_positive_integer(int(self.min_chars), f"[{getattr(self, '_name', 'Extractor')}] Min chars")


class _BaseExtractor(ComponentBase, ABC):
    extractor_method = ""
    output_key = "items"

    def _resolve(self, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _input_value(self) -> Any:
        return self._resolve(self._param.document) or self._resolve(self._param.content) or ""

    def _invoke(self, **kwargs):
        method = getattr(DocumentExtractService, self.extractor_method)
        if self.extractor_method in {"extract_clauses", "extract_obligations", "extract_definitions", "extract_viewpoints", "extract_risks"}:
            result = method(self._input_value(), min_chars=int(self._param.min_chars or 4))
        else:
            result = method(self._input_value())
        self.set_output("items", result.get("items", []))
        self.set_output("references", result.get("references", []))
        self.set_output("summary", result.get("summary", ""))
        self.set_output(self.output_key, result.get("items", []))


class ClauseExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.outputs["clauses"] = {"value": [], "type": "Array<JSON>"}


class ClauseExtractor(_BaseExtractor, ABC):
    component_name = "ClauseExtractor"
    extractor_method = "extract_clauses"
    output_key = "clauses"


class ObligationExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.outputs["obligations"] = {"value": [], "type": "Array<JSON>"}


class ObligationExtractor(_BaseExtractor, ABC):
    component_name = "ObligationExtractor"
    extractor_method = "extract_obligations"
    output_key = "obligations"


class DefinitionExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.outputs["definitions"] = {"value": [], "type": "Array<JSON>"}


class DefinitionExtractor(_BaseExtractor, ABC):
    component_name = "DefinitionExtractor"
    extractor_method = "extract_definitions"
    output_key = "definitions"


class ViewpointExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.min_chars = 8
        self.outputs["viewpoints"] = {"value": [], "type": "Array<JSON>"}


class ViewpointExtractor(_BaseExtractor, ABC):
    component_name = "ViewpointExtractor"
    extractor_method = "extract_viewpoints"
    output_key = "viewpoints"


class RiskPointExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.outputs["risk_points"] = {"value": [], "type": "Array<JSON>"}


class RiskPointExtractor(_BaseExtractor, ABC):
    component_name = "RiskPointExtractor"
    extractor_method = "extract_risks"
    output_key = "risk_points"


class TableFactExtractorParam(_BaseExtractorParam):
    def __init__(self):
        super().__init__()
        self.outputs["table_facts"] = {"value": [], "type": "Array<JSON>"}


class TableFactExtractor(_BaseExtractor, ABC):
    component_name = "TableFactExtractor"
    extractor_method = "extract_table_facts"
    output_key = "table_facts"
