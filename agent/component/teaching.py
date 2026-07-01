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


DEFAULT_PRONUNCIATION_DIMENSIONS = [
    {"key": "pronunciation", "label": "发音准确率", "weight": 0.25},
    {"key": "word_completeness", "label": "单词完整度", "weight": 0.15},
    {"key": "fluency", "label": "流利度", "weight": 0.15},
    {"key": "rhythm", "label": "节奏", "weight": 0.15},
    {"key": "stress", "label": "重音", "weight": 0.10},
    {"key": "intonation", "label": "语调", "weight": 0.10},
    {"key": "completion", "label": "跟读完成度", "weight": 0.10},
]


def _parse_json_like(value: Any, default: Any = None) -> Any:
    if isinstance(value, str):
        text = value.strip()
        if not text:
            return default
        try:
            return json.loads(text)
        except Exception:
            return default
    return value if value is not None else default


def _number(value: Any, field: str, min_value: float = 0.0, max_value: float = 100.0) -> float:
    try:
        result = float(value)
    except Exception as exc:
        raise ValueError(f"{field} must be numeric") from exc
    if result < min_value or result > max_value:
        raise ValueError(f"{field} must be in range [{min_value:g}, {max_value:g}]")
    return result


class PromptTemplateParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.template = ""
        self.variables = {}
        self.outputs = {"prompt": {"value": "", "type": "string"}}

    def check(self):
        return True


class PromptTemplate(ComponentBase, ABC):
    component_name = "PromptTemplate"

    @staticmethod
    def render_template(template: str, variables: dict[str, Any]) -> str:
        variables = variables or {}

        def repl(match):
            key = match.group(1).strip()
            value = variables.get(key, "")
            if isinstance(value, (dict, list)):
                return json.dumps(value, ensure_ascii=False)
            return str(value)

        return re.sub(r"\{\{\s*([A-Za-z0-9_.-]+)\s*\}\}", repl, str(template or ""))

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        variables = _parse_json_like(self._param.variables, {}) or {}
        template = self._param.template
        if isinstance(template, str) and "@" in template and "{" in template:
            template = self._canvas.get_value_with_variable(template)
        self.set_output("prompt", self.render_template(template, variables if isinstance(variables, dict) else {}))


class ScoreRubricBuilderParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.dimensions = DEFAULT_PRONUNCIATION_DIMENSIONS
        self.outputs = {
            "rubric": {"value": {}, "type": "ScoreRubric"},
            "dimensions": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": "", "type": "string"},
        }

    def check(self):
        return True


class ScoreRubricBuilder(ComponentBase, ABC):
    component_name = "ScoreRubricBuilder"

    @staticmethod
    def build_rubric(dimensions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        dimensions = dimensions or DEFAULT_PRONUNCIATION_DIMENSIONS
        cleaned = []
        for item in dimensions:
            if not isinstance(item, dict):
                continue
            key = str(item.get("key") or "").strip()
            if not key:
                continue
            cleaned.append({"key": key, "label": str(item.get("label") or key), "weight": float(item.get("weight", 0))})
        if not cleaned:
            raise ValueError("Score rubric must contain at least one dimension")
        return {"schema_version": 1, "dimensions": cleaned}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        dimensions = _parse_json_like(self._param.dimensions, DEFAULT_PRONUNCIATION_DIMENSIONS)
        rubric = self.build_rubric(dimensions if isinstance(dimensions, list) else DEFAULT_PRONUNCIATION_DIMENSIONS)
        self.set_output("rubric", rubric)
        self.set_output("dimensions", rubric["dimensions"])
        self.set_output("summary", f"Built score rubric with {len(rubric['dimensions'])} dimension(s).")


class PronunciationJudgeParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.structured_result = ""
        self.rubric = ""
        self.required_dimensions = []
        self.outputs = {
            "score_result": {"value": {}, "type": "ScoreResult"},
            "self_score": {"value": 0, "type": "number"},
            "rubric_scores": {"value": {}, "type": "JSON"},
            "feedback": {"value": "", "type": "string"},
            "valid": {"value": False, "type": "boolean"},
        }
        self.input_schema = {
            "structured_result": {"type": "JSON", "required": True},
            "rubric": {"type": "ScoreRubric", "required": False},
        }

    def check(self):
        return True


class PronunciationJudge(ComponentBase, ABC):
    component_name = "PronunciationJudge"

    @staticmethod
    def _required_dimensions(rubric: dict[str, Any] | None = None, required_dimensions: list[str] | None = None) -> list[str]:
        if required_dimensions:
            return [str(item) for item in required_dimensions if str(item).strip()]
        dimensions = (rubric or {}).get("dimensions") or DEFAULT_PRONUNCIATION_DIMENSIONS
        return [str(item.get("key")) for item in dimensions if isinstance(item, dict) and item.get("key")]

    @classmethod
    def validate_result(
        cls,
        payload: dict[str, Any],
        rubric: dict[str, Any] | None = None,
        required_dimensions: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(payload, dict):
            raise ValueError("structured_result must be a JSON object")
        for field in ("teacher_plan", "teaching_steps", "self_score", "rubric_scores", "feedback", "next_step"):
            if field not in payload:
                raise ValueError(f"structured_result missing required field `{field}`")
        if not isinstance(payload.get("teaching_steps"), list):
            raise ValueError("teaching_steps must be an array")
        if not isinstance(payload.get("rubric_scores"), dict):
            raise ValueError("rubric_scores must be an object")

        self_score = _number(payload.get("self_score"), "self_score")
        rubric_scores = {}
        for key in cls._required_dimensions(rubric, required_dimensions):
            if key not in payload["rubric_scores"]:
                raise ValueError(f"rubric_scores missing required dimension `{key}`")
            rubric_scores[key] = _number(payload["rubric_scores"][key], f"rubric_scores.{key}")

        return {
            "schema_version": 1,
            "teacher_plan": str(payload.get("teacher_plan") or ""),
            "teaching_steps": payload.get("teaching_steps"),
            "self_score": self_score,
            "rubric_scores": rubric_scores,
            "feedback": str(payload.get("feedback") or ""),
            "next_step": str(payload.get("next_step") or ""),
            "valid": True,
        }

    def _resolve_value(self, value: Any) -> Any:
        if isinstance(value, str) and value:
            try:
                if self._canvas.is_reff(value):
                    return self._canvas.get_variable_value(value)
                if "@" in value and "{" in value:
                    return self._canvas.get_value_with_variable(value)
            except Exception:
                return value
        return value

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        payload = _parse_json_like(self._resolve_value(self._param.structured_result), {})
        rubric = _parse_json_like(self._resolve_value(self._param.rubric), {})
        required = _parse_json_like(self._param.required_dimensions, [])
        score_result = self.validate_result(
            payload if isinstance(payload, dict) else {},
            rubric if isinstance(rubric, dict) else {},
            required if isinstance(required, list) else [],
        )
        self.set_output("score_result", score_result)
        self.set_output("self_score", score_result["self_score"])
        self.set_output("rubric_scores", score_result["rubric_scores"])
        self.set_output("feedback", score_result["feedback"])
        self.set_output("valid", True)


class SummaryNodeParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.content = ""
        self.max_chars = 800
        self.outputs = {"summary": {"value": "", "type": "string"}}

    def check(self):
        self.check_positive_integer(self.max_chars, "[SummaryNode] Max chars")


class SummaryNode(ComponentBase, ABC):
    component_name = "SummaryNode"

    @staticmethod
    def summarize(content: Any, max_chars: int = 800) -> str:
        text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)
        text = re.sub(r"\s+", " ", text or "").strip()
        return text[:max_chars]

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        content = self._param.content
        if isinstance(content, str) and self._canvas.is_reff(content):
            content = self._canvas.get_variable_value(content)
        self.set_output("summary", self.summarize(content, self._param.max_chars))


class ReportComposerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.title = "报告"
        self.sections = {}
        self.outputs = {"markdown": {"value": "", "type": "string"}}

    def check(self):
        return True


class ReportComposer(ComponentBase, ABC):
    component_name = "ReportComposer"

    @staticmethod
    def compose_markdown(title: str, sections: dict[str, Any]) -> str:
        lines = [f"# {title or '报告'}"]
        for key, value in (sections or {}).items():
            lines.extend(["", f"## {key}"])
            if isinstance(value, (dict, list)):
                lines.append(json.dumps(value, ensure_ascii=False, indent=2))
            else:
                lines.append(str(value or ""))
        return "\n".join(lines)

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        sections = _parse_json_like(self._param.sections, {})
        self.set_output("markdown", self.compose_markdown(self._param.title, sections if isinstance(sections, dict) else {}))
