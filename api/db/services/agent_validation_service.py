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

import re
from typing import Any

from agent.sql_guard import prepare_readonly_sqls


class AgentValidationIssue:
    ERROR = "error"
    WARNING = "warning"

    def __init__(self, severity: str, code: str, message: str, component_id: str = "", component_name: str = ""):
        self.severity = severity
        self.code = code
        self.message = message
        self.component_id = component_id
        self.component_name = component_name

    def to_dict(self) -> dict[str, Any]:
        return {
            "severity": self.severity,
            "code": self.code,
            "message": self.message,
            "component_id": self.component_id,
            "component_name": self.component_name,
        }


class AgentValidationService:
    VARIABLE_REF_RE = re.compile(
        r"\{+ *([A-Za-z0-9:_-]+@[A-Za-z0-9_.-]+|sys\.[A-Za-z0-9_.]+|env\.[A-Za-z0-9_.]+) *\}+"
    )
    LLM_COMPONENTS = {"agent", "categorize", "browser", "rewritequestion", "agentwithtools"}
    OUTPUT_COMPONENTS = {"message", "agent", "docgenerator", "excelprocessor", "codeexec"}
    ARTIFACT_COMPONENTS = {"docgenerator", "codeexec"}
    FILE_PROCESSORS = {"fileparser", "excelprocessor", "parser", "tokenizer", "extractor", "docgenerator"}

    @classmethod
    def validate_for_publish(cls, dsl: dict[str, Any] | None) -> dict[str, Any]:
        issues = cls.validate(dsl)
        return {
            "ok": not any(item["severity"] == AgentValidationIssue.ERROR for item in issues),
            "errors": [item for item in issues if item["severity"] == AgentValidationIssue.ERROR],
            "warnings": [item for item in issues if item["severity"] == AgentValidationIssue.WARNING],
            "issues": issues,
        }

    @classmethod
    def validate(cls, dsl: dict[str, Any] | None) -> list[dict[str, Any]]:
        validator = cls(dsl)
        return validator.run()

    def __init__(self, dsl: dict[str, Any] | None):
        self.dsl = dsl if isinstance(dsl, dict) else {}
        self.components = self.dsl.get("components") if isinstance(self.dsl.get("components"), dict) else {}
        self.issues: list[AgentValidationIssue] = []

    def run(self) -> list[dict[str, Any]]:
        self._validate_shape()
        if not self.components:
            return [item.to_dict() for item in self.issues]

        self._validate_begin()
        self._validate_edges()
        self._validate_connectivity()
        self._validate_required_params()
        self._validate_variable_refs()
        self._validate_sql()
        self._validate_file_flow()
        self._validate_artifact_visibility()
        return [item.to_dict() for item in self.issues]

    def _component_name(self, component_id: str) -> str:
        component = self.components.get(component_id) or {}
        obj = component.get("obj") or {}
        return str(obj.get("component_name") or "")

    def _params(self, component_id: str) -> dict[str, Any]:
        component = self.components.get(component_id) or {}
        obj = component.get("obj") or {}
        params = obj.get("params")
        return params if isinstance(params, dict) else {}

    def _add(self, severity: str, code: str, message: str, component_id: str = "") -> None:
        self.issues.append(
            AgentValidationIssue(
                severity=severity,
                code=code,
                message=message,
                component_id=component_id,
                component_name=self._component_name(component_id) if component_id else "",
            )
        )

    def _validate_shape(self) -> None:
        if not isinstance(self.dsl, dict):
            self._add(AgentValidationIssue.ERROR, "invalid_dsl", "Agent DSL must be an object.")
            return
        if not self.components:
            self._add(AgentValidationIssue.ERROR, "empty_components", "Agent workflow must contain at least one node.")

    def _validate_begin(self) -> None:
        begins = [component_id for component_id in self.components if self._component_name(component_id).lower() == "begin"]
        if not begins:
            self._add(AgentValidationIssue.ERROR, "missing_begin", "Agent workflow must contain a Begin node.")
        elif len(begins) > 1:
            self._add(AgentValidationIssue.WARNING, "multiple_begin", "Agent workflow contains multiple Begin nodes.")

    @staticmethod
    def _as_id_list(value: Any) -> list[str]:
        if isinstance(value, list):
            return [str(item) for item in value if item]
        if isinstance(value, str) and value:
            return [value]
        return []

    def _validate_edges(self) -> None:
        known = set(self.components.keys())
        for component_id, component in self.components.items():
            downstream = self._as_id_list(component.get("downstream"))
            upstream = self._as_id_list(component.get("upstream"))
            for target in downstream:
                if target not in known:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "broken_downstream",
                        f"Node references missing downstream node `{target}`.",
                        component_id,
                    )
            for source in upstream:
                if source not in known:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "broken_upstream",
                        f"Node references missing upstream node `{source}`.",
                        component_id,
                    )

    def _validate_connectivity(self) -> None:
        if len(self.components) <= 1:
            return
        for component_id, component in self.components.items():
            name = self._component_name(component_id).lower()
            if name in {"note"}:
                continue
            downstream = self._as_id_list(component.get("downstream"))
            upstream = self._as_id_list(component.get("upstream"))
            if name == "begin" and not downstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "begin_without_downstream",
                    "Begin node has no downstream node.",
                    component_id,
                )
            elif name != "begin" and not upstream and not downstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "isolated_node",
                    "Node is isolated and will not run in the workflow.",
                    component_id,
                )
            elif name != "begin" and not upstream:
                self._add(
                    AgentValidationIssue.WARNING,
                    "node_without_upstream",
                    "Node has no upstream input and may not run.",
                    component_id,
                )

        if not any(
            self._component_name(component_id).lower() in self.OUTPUT_COMPONENTS
            for component_id in self.components
        ):
            self._add(
                AgentValidationIssue.WARNING,
                "missing_output_node",
                "Workflow has no obvious answer or artifact output node.",
            )

    def _validate_required_params(self) -> None:
        for component_id in self.components:
            name = self._component_name(component_id).lower()
            params = self._params(component_id)
            if name in self.LLM_COMPONENTS and not str(params.get("llm_id") or "").strip():
                self._add(
                    AgentValidationIssue.ERROR,
                    "missing_llm",
                    "LLM node must configure a model before publishing.",
                    component_id,
                )
            if name == "docgenerator" and not str(params.get("content") or "").strip():
                self._add(
                    AgentValidationIssue.ERROR,
                    "missing_doc_content",
                    "DocGenerator must configure content before publishing.",
                    component_id,
                )
            if name == "excelprocessor":
                input_files = params.get("input_files")
                operation = str(params.get("operation") or "").lower()
                if operation in {"read", "aggregate"} and not input_files:
                    self._add(
                        AgentValidationIssue.WARNING,
                        "missing_excel_input",
                        "ExcelProcessor has no file input configured.",
                        component_id,
                    )
                if operation in {"output", "export"} and not str(params.get("transform_data") or "").strip():
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_excel_output_data",
                        "ExcelProcessor export must configure a data variable reference.",
                        component_id,
                    )
                if operation == "calculate" and str(params.get("calculation_value") or "").strip() == "":
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_excel_calculation_value",
                        "ExcelProcessor calculate must configure a source value.",
                        component_id,
                    )
            if name == "fileparser":
                input_files = params.get("input_files")
                if not input_files:
                    self._add(
                        AgentValidationIssue.ERROR,
                        "missing_file_parser_input",
                        "FileParser must configure an uploaded file input.",
                        component_id,
                    )

    def _walk_strings(self, value: Any) -> list[str]:
        if isinstance(value, str):
            return [value]
        if isinstance(value, list):
            result = []
            for item in value:
                result.extend(self._walk_strings(item))
            return result
        if isinstance(value, dict):
            result = []
            for item in value.values():
                result.extend(self._walk_strings(item))
            return result
        return []

    def _validate_variable_refs(self) -> None:
        known = set(self.components.keys())
        for component_id in self.components:
            params = self._params(component_id)
            for text in self._walk_strings(params):
                for ref in self.VARIABLE_REF_RE.findall(text):
                    if "@" not in ref:
                        continue
                    source_id, var_name = ref.split("@", 1)
                    if source_id in {"sys", "item", "index"}:
                        continue
                    if source_id not in known:
                        self._add(
                            AgentValidationIssue.ERROR,
                            "missing_variable_source",
                            f"Variable reference `{source_id}@{var_name}` points to a missing node.",
                            component_id,
                        )

    def _validate_sql(self) -> None:
        for component_id in self.components:
            if self._component_name(component_id).lower() != "exesql":
                continue
            sql = self._params(component_id).get("sql") or ""
            if not str(sql).strip():
                self._add(AgentValidationIssue.ERROR, "missing_sql", "ExeSQL must configure SQL.", component_id)
                continue
            try:
                prepare_readonly_sqls(str(sql))
            except Exception as exc:
                self._add(
                    AgentValidationIssue.ERROR,
                    "unsafe_sql",
                    str(exc),
                    component_id,
                )

    def _validate_file_flow(self) -> None:
        begin_has_file_input = False
        for component_id in self.components:
            if self._component_name(component_id).lower() != "begin":
                continue
            params = self._params(component_id)
            inputs = params.get("inputs") or []
            if isinstance(inputs, dict):
                inputs = inputs.values()
            for item in inputs:
                if isinstance(item, dict) and str(item.get("type") or "").lower() == "file":
                    begin_has_file_input = True
                    break

        if not begin_has_file_input:
            return

        has_file_processor = any(
            self._component_name(component_id).lower() in self.FILE_PROCESSORS
            for component_id in self.components
        )
        if not has_file_processor:
            self._add(
                AgentValidationIssue.WARNING,
                "file_input_without_processor",
                "Workflow accepts uploaded files but has no file parsing, Excel, or document output node.",
            )

    def _is_artifact_component(self, component_id: str) -> bool:
        name = self._component_name(component_id).lower()
        if name in self.ARTIFACT_COMPONENTS:
            return True
        if name == "excelprocessor":
            return str(self._params(component_id).get("operation") or "").lower() in {"output", "export"}
        return False

    def _can_reach_message(self, component_id: str) -> bool:
        visited = set()
        queue = self._as_id_list((self.components.get(component_id) or {}).get("downstream"))
        while queue:
            current = queue.pop(0)
            if current in visited:
                continue
            visited.add(current)
            if self._component_name(current).lower() == "message":
                return True
            queue.extend(self._as_id_list((self.components.get(current) or {}).get("downstream")))
        return False

    def _validate_artifact_visibility(self) -> None:
        for component_id in self.components:
            if not self._is_artifact_component(component_id):
                continue
            if not self._can_reach_message(component_id):
                self._add(
                    AgentValidationIssue.WARNING,
                    "artifact_without_message_output",
                    "This node can generate downloadable artifacts, but no downstream Message node will expose them in the answer.",
                    component_id,
                )
