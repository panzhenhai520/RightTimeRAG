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
from api.db.services.document_compare_service import DocumentCompareService


class _CompareParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.outputs = {
            "summary": {"value": {}, "type": "JSON"},
        }

    def check(self):
        return


class _CompareComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class DocumentDiffParam(_CompareParam):
    def __init__(self):
        super().__init__()
        self.left_document = ""
        self.right_document = ""
        self.granularity = "paragraphs"
        self.outputs.update(
            {
                "diff": {"value": {}, "type": "JSON"},
                "hunks": {"value": [], "type": "Array<JSON>"},
            }
        )
        self.input_schema = {
            "left_document": {"type": "TextDocument", "required": True},
            "right_document": {"type": "TextDocument", "required": True},
        }


class DocumentDiff(_CompareComponent, ABC):
    component_name = "DocumentDiff"

    def _invoke(self, **kwargs):
        left = self._resolve(self._param.left_document) or kwargs.get("left_document") or kwargs.get("left")
        right = self._resolve(self._param.right_document) or kwargs.get("right_document") or kwargs.get("right")
        granularity = str(self._param.granularity or "paragraphs")
        if granularity == "lines":
            result = DocumentCompareService.diff_lines(left, right)
        elif granularity == "sections":
            result = DocumentCompareService.diff_sections(left, right)
        elif granularity == "hash":
            result = DocumentCompareService.diff_hash(left, right)
        else:
            result = DocumentCompareService.diff_paragraphs(left, right)
        self.set_output("diff", result)
        self.set_output("hunks", result.get("hunks", []))
        self.set_output("summary", result.get("summary", {}))


class TableDiffParam(_CompareParam):
    def __init__(self):
        super().__init__()
        self.left_document = ""
        self.right_document = ""
        self.outputs.update(
            {
                "table_diff": {"value": {}, "type": "JSON"},
                "hunks": {"value": [], "type": "Array<JSON>"},
                "schema_changes": {"value": {}, "type": "JSON"},
            }
        )
        self.input_schema = {
            "left_document": {"type": "TextDocument", "required": True},
            "right_document": {"type": "TextDocument", "required": True},
        }


class TableDiff(_CompareComponent, ABC):
    component_name = "TableDiff"

    def _invoke(self, **kwargs):
        left = self._resolve(self._param.left_document) or kwargs.get("left_document") or kwargs.get("left")
        right = self._resolve(self._param.right_document) or kwargs.get("right_document") or kwargs.get("right")
        result = DocumentCompareService.diff_tables(left, right)
        self.set_output("table_diff", result)
        self.set_output("hunks", result.get("hunks", []))
        self.set_output("schema_changes", result.get("schema_changes", {}))
        self.set_output("summary", result.get("summary", {}))


class DocumentSemanticComparerParam(_CompareParam):
    def __init__(self):
        super().__init__()
        self.left_items = ""
        self.right_items = ""
        self.min_score = 0.2
        self.outputs.update(
            {
                "matches": {"value": [], "type": "Array<JSON>"},
                "missing_in_left": {"value": [], "type": "Array<JSON>"},
                "missing_in_right": {"value": [], "type": "Array<JSON>"},
            }
        )
        self.input_schema = {
            "left_items": {"type": "Array<JSON>", "required": True},
            "right_items": {"type": "Array<JSON>", "required": True},
        }

    def check(self):
        self.check_decimal_float(float(self.min_score), "[DocumentSemanticComparer] Min score")


class DocumentSemanticComparer(_CompareComponent, ABC):
    component_name = "DocumentSemanticComparer"

    def _invoke(self, **kwargs):
        left = self._resolve(self._param.left_items) or kwargs.get("left_items") or kwargs.get("left")
        right = self._resolve(self._param.right_items) or kwargs.get("right_items") or kwargs.get("right")
        result = DocumentCompareService.compare_items(left, right, min_score=float(self._param.min_score or 0.2))
        self.set_output("matches", result.get("matches", []))
        self.set_output("missing_in_left", result.get("missing_in_left", []))
        self.set_output("missing_in_right", result.get("missing_in_right", []))
        self.set_output("summary", result.get("summary", {}))


class DocumentConflictDetectorParam(_CompareParam):
    def __init__(self):
        super().__init__()
        self.standard_items = ""
        self.target_items = ""
        self.min_score = 0.18
        self.outputs.update(
            {
                "conflicts": {"value": [], "type": "Array<JSON>"},
                "missing_requirements": {"value": [], "type": "Array<JSON>"},
                "matches": {"value": [], "type": "Array<JSON>"},
            }
        )
        self.input_schema = {
            "standard_items": {"type": "Array<JSON>", "required": True},
            "target_items": {"type": "Array<JSON>", "required": True},
        }

    def check(self):
        self.check_decimal_float(float(self.min_score), "[DocumentConflictDetector] Min score")


class DocumentConflictDetector(_CompareComponent, ABC):
    component_name = "DocumentConflictDetector"

    def _invoke(self, **kwargs):
        standard = self._resolve(self._param.standard_items) or kwargs.get("standard_items") or kwargs.get("standard")
        target = self._resolve(self._param.target_items) or kwargs.get("target_items") or kwargs.get("target")
        result = DocumentCompareService.detect_conflicts(standard, target, min_score=float(self._param.min_score or 0.18))
        self.set_output("conflicts", result.get("conflicts", []))
        self.set_output("missing_requirements", result.get("missing_requirements", []))
        self.set_output("matches", result.get("matches", []))
        self.set_output("summary", result.get("summary", {}))
