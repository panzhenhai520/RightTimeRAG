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
from abc import ABC
from typing import Any

from agent.artifact_service import ArtifactService
from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.document_compare_report_service import DocumentCompareReportService


class DocumentCompareReportComposerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.title = "文档比对报告"
        self.filename = "document_compare_report"
        self.output_formats = ["markdown", "json", "docx", "xlsx"]
        self.files = ""
        self.documents = ""
        self.diff = ""
        self.table_diff = ""
        self.matches = ""
        self.conflicts = ""
        self.missing_requirements = ""
        self.risk_points = ""
        self.audit = ""
        self.outputs = {
            "report": {"value": {}, "type": "JSON"},
            "markdown": {"value": "", "type": "string"},
            "json": {"value": {}, "type": "JSON"},
            "downloads": {"value": [], "type": "Array<Artifact>"},
            "attachments": {"value": [], "type": "Array<Artifact>"},
            "audit": {"value": {}, "type": "JSON"},
            "summary": {"value": "", "type": "string"},
        }
        self.input_schema = {
            "title": {"type": "String", "required": False},
            "filename": {"type": "String", "required": False},
            "output_formats": {"type": "Any", "required": False},
            "files": {"type": "Array<JSON>", "required": False},
            "documents": {"type": "Any", "required": False},
            "diff": {"type": "JSON", "required": False},
            "table_diff": {"type": "JSON", "required": False},
            "matches": {"type": "Array<JSON>", "required": False},
            "conflicts": {"type": "Array<JSON>", "required": False},
            "missing_requirements": {"type": "Array<JSON>", "required": False},
            "risk_points": {"type": "Array<JSON>", "required": False},
            "audit": {"type": "JSON", "required": False},
        }
        self.runtime_capabilities = {"produces_artifacts": True}

    def check(self):
        return True


class DocumentCompareReportComposer(ComponentBase, ABC):
    component_name = "DocumentCompareReportComposer"

    def _resolve(self, value: Any) -> Any:
        if value in (None, ""):
            return None
        if isinstance(value, str):
            try:
                if self._canvas.is_reff(value):
                    return self._canvas.get_variable_value(value)
                if "@" in value and "{" in value:
                    return self._canvas.get_value_with_variable(value)
            except Exception:
                return value
        return value

    def _tenant_id(self) -> str:
        return self._canvas.get_tenant_id() if hasattr(self._canvas, "get_tenant_id") else ""

    def _agent_id(self) -> str:
        return getattr(self._canvas, "agent_id", "") or getattr(self._canvas, "_agent_id", "")

    def _run_id(self) -> str:
        return getattr(self._canvas, "_run_id", "") or getattr(self._canvas, "run_id", "")

    @staticmethod
    def _formats(value: Any) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return ["markdown"]
            try:
                parsed = json.loads(text)
                if isinstance(parsed, list):
                    value = parsed
                else:
                    value = [text]
            except Exception:
                value = [item.strip() for item in text.split(",") if item.strip()]
        if isinstance(value, (list, tuple, set)):
            result = []
            for item in value:
                fmt = DocumentCompareReportService.normalize_format(str(item))
                if fmt not in result:
                    result.append(fmt)
            return result or ["markdown"]
        return ["markdown"]

    def _invoke(self, **kwargs):
        report = DocumentCompareReportService.build_report(
            title=str(self._resolve(self._param.title) or self._param.title or "文档比对报告"),
            files=self._resolve(self._param.files) or kwargs.get("files"),
            documents=self._resolve(self._param.documents) or kwargs.get("documents"),
            diff=self._resolve(self._param.diff) or kwargs.get("diff"),
            table_diff=self._resolve(self._param.table_diff) or kwargs.get("table_diff"),
            matches=self._resolve(self._param.matches) or kwargs.get("matches"),
            conflicts=self._resolve(self._param.conflicts) or kwargs.get("conflicts"),
            missing_requirements=self._resolve(self._param.missing_requirements) or kwargs.get("missing_requirements"),
            risk_points=self._resolve(self._param.risk_points) or kwargs.get("risk_points"),
            audit=self._resolve(self._param.audit) or kwargs.get("audit"),
            run_id=self._run_id(),
            agent_id=self._agent_id(),
        )
        downloads = []
        for fmt in self._formats(self._param.output_formats):
            content, mime_type = DocumentCompareReportService.render_bytes(report, fmt)
            filename = DocumentCompareReportService.filename(str(self._resolve(self._param.filename) or self._param.filename), fmt)
            download = ArtifactService.create_download_info(
                self._tenant_id(),
                content,
                filename,
                mime_type=mime_type,
                run_id=self._run_id(),
                node_id=getattr(self, "_id", None),
                agent_id=self._agent_id(),
                metadata={"kind": "document_compare_report", "format": fmt, "risk_level": report.get("risk_level")},
            )
            downloads.append(download)
        report["audit"]["report_artifacts"] = [
            {
                "artifact_id": item.get("artifact_id"),
                "filename": item.get("filename"),
                "mime_type": item.get("mime_type"),
                "size": item.get("size"),
                "run_id": item.get("run_id"),
            }
            for item in downloads
        ]
        markdown = DocumentCompareReportService.render_markdown(report)
        self.set_output("report", report)
        self.set_output("markdown", markdown)
        self.set_output("json", report)
        self.set_output("downloads", downloads)
        self.set_output("attachments", [ArtifactService.attachment_from_download(item) for item in downloads])
        self.set_output("audit", report.get("audit", {}))
        self.set_output("summary", report.get("summary", ""))
