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
import json
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.workspace_patch_service import WorkspacePatchService
from api.db.services.workspace_file_service import WorkspaceFileService
from api.db.services.workspace_file_write_service import WorkspaceFileWriteService


def _as_list(value: Any) -> list[Any]:
    if value is None or value == "":
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, str) and "," in value:
        return [item.strip() for item in value.split(",") if item.strip()]
    return [value]


def _as_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _canvas_agent_workspace_roots(canvas) -> list | None:
    workspace = getattr(canvas, "dsl", {}).get("workspace") if hasattr(canvas, "dsl") else {}
    if not isinstance(workspace, dict) or not workspace.get("managed"):
        return None
    agent_id = str(getattr(canvas, "_id", "") or "").strip()
    return WorkspaceFileService.agent_workspace_roots(agent_id) if agent_id else None


class WorkspaceFileListParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.path = "."
        self.recursive = False
        self.include_dirs = True
        self.extensions = []
        self.pattern = ""
        self.regex = ""
        self.max_results = 100
        self.outputs = {
            "files": {"value": [], "type": "Array<JSON>"},
            "count": {"value": 0, "type": "Number"},
            "truncated": {"value": False, "type": "Boolean"},
            "audit": {"value": {}, "type": "JSON"},
        }

    def check(self):
        self.check_positive_integer(int(self.max_results), "[WorkspaceFileList] Max results")


class WorkspaceFileList(ComponentBase, ABC):
    component_name = "WorkspaceFileList"

    def _tenant_id(self) -> str:
        return self._canvas.get_tenant_id() if hasattr(self._canvas, "get_tenant_id") else ""

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        result = WorkspaceFileService.list_files(
            root=str(self._resolve(self._param.root) or ""),
            roots=_canvas_agent_workspace_roots(self._canvas),
            path=str(self._resolve(self._param.path) or "."),
            recursive=bool(self._param.recursive),
            include_dirs=bool(self._param.include_dirs),
            extensions=_as_list(self._resolve(self._param.extensions)),
            pattern=str(self._resolve(self._param.pattern) or ""),
            regex=str(self._resolve(self._param.regex) or ""),
            max_results=int(self._param.max_results or 100),
            tenant_id=self._tenant_id(),
            run_id=getattr(self._canvas, "_run_id", ""),
        )
        self.set_output("files", result["files"])
        self.set_output("count", result["count"])
        self.set_output("truncated", result["truncated"])
        self.set_output("audit", result["audit"])


class WorkspaceFileSearchParam(WorkspaceFileListParam):
    def __init__(self):
        super().__init__()
        self.query = ""
        self.recursive = True


class WorkspaceFileSearch(WorkspaceFileList, ABC):
    component_name = "WorkspaceFileSearch"

    def _invoke(self, **kwargs):
        result = WorkspaceFileService.search_files(
            query=str(self._resolve(self._param.query) or ""),
            root=str(self._resolve(self._param.root) or ""),
            roots=_canvas_agent_workspace_roots(self._canvas),
            path=str(self._resolve(self._param.path) or "."),
            extensions=_as_list(self._resolve(self._param.extensions)),
            pattern=str(self._resolve(self._param.pattern) or ""),
            regex=str(self._resolve(self._param.regex) or ""),
            max_results=int(self._param.max_results or 100),
            tenant_id=self._tenant_id(),
            run_id=getattr(self._canvas, "_run_id", ""),
        )
        self.set_output("files", result["files"])
        self.set_output("count", result["count"])
        self.set_output("truncated", result["truncated"])
        self.set_output("audit", result["audit"])


class WorkspaceFileReadParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.path = ""
        self.encoding = "utf-8"
        self.max_bytes = 65536
        self.start_line = 0
        self.end_line = 0
        self.outputs = {
            "file": {"value": {}, "type": "JSON"},
            "content": {"value": "", "type": "String"},
            "lines": {"value": [], "type": "Array<JSON>"},
            "line_count": {"value": 0, "type": "Number"},
            "truncated": {"value": False, "type": "Boolean"},
            "source_ref": {"value": "", "type": "String"},
            "audit": {"value": {}, "type": "JSON"},
        }

    def check(self):
        self.check_empty(self.path, "[WorkspaceFileRead] Path")
        self.check_positive_integer(int(self.max_bytes), "[WorkspaceFileRead] Max bytes")


class WorkspaceFileRead(ComponentBase, ABC):
    component_name = "WorkspaceFileRead"

    def _tenant_id(self) -> str:
        return self._canvas.get_tenant_id() if hasattr(self._canvas, "get_tenant_id") else ""

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        start_line = int(self._param.start_line or 0)
        end_line = int(self._param.end_line or 0)
        common = {
            "root": str(self._resolve(self._param.root) or ""),
            "roots": _canvas_agent_workspace_roots(self._canvas),
            "path": str(self._resolve(self._param.path) or ""),
            "encoding": str(self._param.encoding or "utf-8"),
            "max_bytes": int(self._param.max_bytes or 65536),
            "tenant_id": self._tenant_id(),
            "run_id": getattr(self._canvas, "_run_id", ""),
        }
        if start_line > 0 or end_line > 0:
            result = WorkspaceFileService.read_range(
                **common,
                start_line=start_line or 1,
                end_line=end_line if end_line > 0 else None,
            )
            lines = result.get("lines", [])
            self.set_output("lines", lines)
            self.set_output("line_count", len(lines))
        else:
            result = WorkspaceFileService.read_file(**common)
            self.set_output("lines", [])
            self.set_output("line_count", result.get("line_count", 0))
        self.set_output("file", result["file"])
        self.set_output("content", result.get("content", ""))
        self.set_output("truncated", result.get("truncated", False))
        self.set_output("source_ref", result.get("source_ref", ""))
        self.set_output("audit", result["audit"])


class WorkspaceFileWriteParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.path = ""
        self.content = ""
        self.mode = "create"
        self.encoding = "utf-8"
        self.expected_hash = ""
        self.dry_run = True
        self.require_approval = True
        self.approval_id = ""
        self.approved = False
        self.task_id = ""
        self.max_bytes = 2097152
        self.reason = ""
        self.outputs = {
            "write": {"value": {}, "type": "JSON"},
            "file": {"value": {}, "type": "JSON"},
            "diff": {"value": "", "type": "String"},
            "changed": {"value": False, "type": "Boolean"},
            "dry_run": {"value": True, "type": "Boolean"},
            "approval": {"value": {}, "type": "JSON"},
            "audit": {"value": {}, "type": "JSON"},
        }
        self.category = "file"
        self.risk_level = "high"
        self.requires_service = ["workspace_files"]
        self.runtime_capabilities = {"uses_external_io": True}
        self.input_schema = {
            "root": {"type": "String", "required": False},
            "path": {"type": "String", "required": True},
            "content": {"type": "String", "required": True},
            "mode": {"type": "String", "required": False},
            "expected_hash": {"type": "String", "required": False},
            "dry_run": {"type": "Boolean", "required": False},
            "require_approval": {"type": "Boolean", "required": False},
            "approval_id": {"type": "String", "required": False},
            "approved": {"type": "Boolean", "required": False},
            "task_id": {"type": "String", "required": False},
            "reason": {"type": "String", "required": False},
        }

    def check(self):
        self.check_empty(self.path, "[WorkspaceFileWrite] Path")
        self.check_valid_value(str(self.mode or "").lower(), "[WorkspaceFileWrite] Mode", ["create", "overwrite", "append"])
        self.check_positive_integer(int(self.max_bytes), "[WorkspaceFileWrite] Max bytes")


class WorkspaceFileWrite(WorkspaceFileRead, ABC):
    component_name = "WorkspaceFileWrite"

    def _invoke(self, **kwargs):
        result = WorkspaceFileWriteService.write_file(
            root=str(self._resolve(self._param.root) or ""),
            roots=_canvas_agent_workspace_roots(self._canvas),
            path=str(self._resolve(self._param.path) or ""),
            content=str(self._resolve(self._param.content) or ""),
            mode=str(self._resolve(self._param.mode) or "create"),
            encoding=str(self._param.encoding or "utf-8"),
            expected_hash=str(self._resolve(self._param.expected_hash) or ""),
            dry_run=bool(self._param.dry_run),
            require_approval=bool(self._param.require_approval),
            approval_id=str(self._resolve(self._param.approval_id) or ""),
            manual_approved=bool(self._resolve(self._param.approved)),
            task_id=str(self._resolve(self._param.task_id) or ""),
            requester_id=self._tenant_id(),
            max_bytes=int(self._param.max_bytes or 2097152),
            tenant_id=self._tenant_id(),
            run_id=getattr(self._canvas, "_run_id", ""),
            reason=str(self._resolve(self._param.reason) or ""),
        )
        self.set_output("write", result)
        self.set_output("file", result.get("file", {}))
        self.set_output("diff", result.get("diff", ""))
        self.set_output("changed", result.get("changed", False))
        self.set_output("dry_run", result.get("dry_run", False))
        self.set_output("approval", result.get("approval") or {})
        self.set_output("audit", result.get("audit", {}))


class WorkspacePatchApplyParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.patch = {}
        self.patch_format = "structured"
        self.expected_hashes = {}
        self.encoding = "utf-8"
        self.dry_run = True
        self.require_approval = True
        self.approval_id = ""
        self.approved = False
        self.task_id = ""
        self.max_files = 20
        self.max_changed_lines = 2000
        self.reason = ""
        self.outputs = {
            "patch_result": {"value": {}, "type": "JSON"},
            "affected_files": {"value": [], "type": "Array<JSON>"},
            "diff": {"value": "", "type": "String"},
            "conflicts": {"value": [], "type": "Array<JSON>"},
            "can_apply": {"value": False, "type": "Boolean"},
            "rollback_token": {"value": "", "type": "String"},
            "dry_run": {"value": True, "type": "Boolean"},
            "approval": {"value": {}, "type": "JSON"},
            "audit": {"value": {}, "type": "JSON"},
        }
        self.category = "file"
        self.risk_level = "high"
        self.requires_service = ["workspace_files"]
        self.runtime_capabilities = {"uses_external_io": True}
        self.input_schema = {
            "root": {"type": "String", "required": False},
            "patch": {"type": "Any", "required": True},
            "patch_format": {"type": "String", "required": False},
            "expected_hashes": {"type": "JSON", "required": False},
            "dry_run": {"type": "Boolean", "required": False},
            "require_approval": {"type": "Boolean", "required": False},
            "approval_id": {"type": "String", "required": False},
            "approved": {"type": "Boolean", "required": False},
            "task_id": {"type": "String", "required": False},
            "reason": {"type": "String", "required": False},
        }

    def check(self):
        self.check_valid_value(str(self.patch_format or "").lower(), "[WorkspacePatchApply] Patch format", ["structured", "unified_diff"])
        self.check_positive_integer(int(self.max_files), "[WorkspacePatchApply] Max files")
        self.check_positive_integer(int(self.max_changed_lines), "[WorkspacePatchApply] Max changed lines")


class WorkspacePatchApply(WorkspaceFileRead, ABC):
    component_name = "WorkspacePatchApply"

    def _invoke(self, **kwargs):
        payload = {
            "patch": self._resolve(self._param.patch),
            "patch_format": str(self._resolve(self._param.patch_format) or "structured"),
            "root": str(self._resolve(self._param.root) or ""),
            "roots": _canvas_agent_workspace_roots(self._canvas),
            "expected_hashes": _as_dict(self._resolve(self._param.expected_hashes)),
            "encoding": str(self._param.encoding or "utf-8"),
            "max_files": int(self._param.max_files or 20),
            "max_changed_lines": int(self._param.max_changed_lines or 2000),
            "tenant_id": self._tenant_id(),
            "run_id": getattr(self._canvas, "_run_id", ""),
            "reason": str(self._resolve(self._param.reason) or ""),
        }
        if self._param.dry_run:
            result = WorkspacePatchService.dry_run(**payload)
        else:
            payload.update(
                {
                    "require_approval": bool(self._param.require_approval),
                    "approval_id": str(self._resolve(self._param.approval_id) or ""),
                    "manual_approved": bool(self._resolve(self._param.approved)),
                    "task_id": str(self._resolve(self._param.task_id) or ""),
                    "requester_id": self._tenant_id(),
                }
            )
            result = WorkspacePatchService.apply(**payload)
        self.set_output("patch_result", result)
        self.set_output("affected_files", result.get("affected_files", []))
        self.set_output("diff", result.get("diff", ""))
        self.set_output("conflicts", result.get("conflicts", []))
        self.set_output("can_apply", result.get("can_apply", False))
        self.set_output("rollback_token", result.get("rollback_token", ""))
        self.set_output("dry_run", result.get("dry_run", False))
        self.set_output("approval", result.get("approval") or {})
        self.set_output("audit", result.get("audit", {}))


class WorkspaceTableReadParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.root = ""
        self.path = ""
        self.sheet_name = ""
        self.header_row = 1
        self.start_row = 0
        self.max_rows = 100
        self.max_cells = 5000
        self.encoding = "utf-8"
        self.outputs = {
            "table": {"value": {}, "type": "TableData"},
            "headers": {"value": [], "type": "Array<String>"},
            "rows": {"value": [], "type": "Array<JSON>"},
            "file": {"value": {}, "type": "JSON"},
            "truncated": {"value": False, "type": "Boolean"},
            "source_ref": {"value": "", "type": "String"},
            "audit": {"value": {}, "type": "JSON"},
        }

    def check(self):
        self.check_empty(self.path, "[WorkspaceTableRead] Path")
        self.check_positive_integer(int(self.max_rows), "[WorkspaceTableRead] Max rows")
        self.check_positive_integer(int(self.max_cells), "[WorkspaceTableRead] Max cells")


class WorkspaceTableRead(ComponentBase, ABC):
    component_name = "WorkspaceTableRead"

    def _tenant_id(self) -> str:
        return self._canvas.get_tenant_id() if hasattr(self._canvas, "get_tenant_id") else ""

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        result = WorkspaceFileService.read_table(
            root=str(self._resolve(self._param.root) or ""),
            roots=_canvas_agent_workspace_roots(self._canvas),
            path=str(self._resolve(self._param.path) or ""),
            sheet_name=str(self._resolve(self._param.sheet_name) or ""),
            header_row=int(self._param.header_row or 1),
            start_row=int(self._param.start_row or 0) or None,
            max_rows=int(self._param.max_rows or 100),
            max_cells=int(self._param.max_cells or 5000),
            encoding=str(self._param.encoding or "utf-8"),
            tenant_id=self._tenant_id(),
            run_id=getattr(self._canvas, "_run_id", ""),
        )
        self.set_output("table", result)
        self.set_output("headers", result.get("headers", []))
        self.set_output("rows", result.get("rows", []))
        self.set_output("file", result.get("file", {}))
        self.set_output("truncated", result.get("truncated", False))
        self.set_output("source_ref", result.get("source_ref", ""))
        self.set_output("audit", result.get("audit", {}))
