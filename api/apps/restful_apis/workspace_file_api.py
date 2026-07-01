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

from api.apps import login_required
from api.db.services.workspace_patch_service import WorkspacePatchService
from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from api.db.services.workspace_file_write_service import WorkspaceFileWriteService
from api.utils.api_utils import add_tenant_id_to_kwargs, get_json_result, get_request_json, server_error_response
from common.constants import RetCode
from common.misc_utils import thread_pool_exec
from quart import request


def _workspace_error_response(exc: WorkspaceFileError):
    code = RetCode.ARGUMENT_ERROR if exc.code in {"INVALID_RANGE", "ROOT_NOT_ALLOWED"} else RetCode.DATA_ERROR
    return get_json_result(data=exc.to_dict(), code=code, message=str(exc))


def _agent_workspace_roots(agent_id):
    agent_id = str(agent_id or "").strip()
    return WorkspaceFileService.agent_workspace_roots(agent_id) if agent_id else None


@manager.route("/workspace/roots", methods=["GET"])  # noqa: F821
@login_required
def list_workspace_roots():
    try:
        return get_json_result(data={"roots": WorkspaceFileService.list_roots(agent_id=request.args.get("agent_id", ""))})
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/list", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def list_workspace_files(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.list_files,
            path=req.get("path", "."),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            recursive=bool(req.get("recursive", False)),
            include_dirs=bool(req.get("include_dirs", True)),
            extensions=req.get("extensions"),
            pattern=str(req.get("pattern") or ""),
            regex=str(req.get("regex") or ""),
            max_results=req.get("max_results"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/search", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def search_workspace_files(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.search_files,
            query=str(req.get("query") or ""),
            path=req.get("path", "."),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            extensions=req.get("extensions"),
            pattern=str(req.get("pattern") or ""),
            regex=str(req.get("regex") or ""),
            max_results=req.get("max_results"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/stat", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def stat_workspace_file(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.stat,
            path=req.get("path", "."),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/read", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def read_workspace_file(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.read_file,
            path=req.get("path", ""),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            encoding=str(req.get("encoding") or "utf-8"),
            max_bytes=req.get("max_bytes"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/read-range", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def read_workspace_file_range(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.read_range,
            path=req.get("path", ""),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            start_line=int(req.get("start_line") or 1),
            end_line=int(req.get("end_line")) if req.get("end_line") is not None else None,
            encoding=str(req.get("encoding") or "utf-8"),
            max_bytes=req.get("max_bytes"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/read-table", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def read_workspace_table(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileService.read_table,
            path=req.get("path", ""),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            sheet_name=str(req.get("sheet_name") or ""),
            header_row=int(req.get("header_row") or 1),
            start_row=int(req.get("start_row")) if req.get("start_row") is not None else None,
            max_rows=req.get("max_rows"),
            max_cells=req.get("max_cells"),
            encoding=str(req.get("encoding") or "utf-8"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/files/write", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def write_workspace_file(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspaceFileWriteService.write_file,
            path=req.get("path", ""),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            content=str(req.get("content") or ""),
            mode=str(req.get("mode") or "create"),
            encoding=str(req.get("encoding") or "utf-8"),
            expected_hash=str(req.get("expected_hash") or ""),
            dry_run=bool(req.get("dry_run", False)),
            require_approval=bool(req.get("require_approval", True)),
            approval_id=str(req.get("approval_id") or ""),
            manual_approved=bool(req.get("manual_approved", False)),
            task_id=str(req.get("task_id") or ""),
            requester_id=str(req.get("requester_id") or req.get("user_id") or tenant_id),
            policy=req.get("policy") if isinstance(req.get("policy"), dict) else {},
            max_bytes=req.get("max_bytes"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
            reason=str(req.get("reason") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/writes/<write_id>", methods=["GET"])  # noqa: F821
@login_required
def get_workspace_write(write_id):
    try:
        return get_json_result(data=WorkspaceFileWriteService.get_write(str(write_id)))
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/writes/<write_id>/audit", methods=["GET"])  # noqa: F821
@login_required
def get_workspace_write_audit(write_id):
    try:
        return get_json_result(data={"items": WorkspaceFileWriteService.list_audit(str(write_id))})
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/patches/dry-run", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def dry_run_workspace_patch(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspacePatchService.dry_run,
            patch=req.get("patch"),
            patch_format=str(req.get("patch_format") or "structured"),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            expected_hashes=req.get("expected_hashes") or {},
            encoding=str(req.get("encoding") or "utf-8"),
            max_files=req.get("max_files"),
            max_changed_lines=req.get("max_changed_lines"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
            reason=str(req.get("reason") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/patches/apply", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def apply_workspace_patch(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspacePatchService.apply,
            patch=req.get("patch"),
            patch_format=str(req.get("patch_format") or "structured"),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            expected_hashes=req.get("expected_hashes") or {},
            encoding=str(req.get("encoding") or "utf-8"),
            require_approval=bool(req.get("require_approval", True)),
            approval_id=str(req.get("approval_id") or ""),
            manual_approved=bool(req.get("manual_approved", False)),
            task_id=str(req.get("task_id") or ""),
            requester_id=str(req.get("requester_id") or req.get("user_id") or tenant_id),
            policy=req.get("policy") if isinstance(req.get("policy"), dict) else {},
            max_files=req.get("max_files"),
            max_changed_lines=req.get("max_changed_lines"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
            reason=str(req.get("reason") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/patches/rollback", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def rollback_workspace_patch(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            WorkspacePatchService.rollback,
            rollback_token=str(req.get("rollback_token") or ""),
            root=req.get("root", ""),
            roots=_agent_workspace_roots(req.get("agent_id")),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
            reason=str(req.get("reason") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/patches/<patch_id>", methods=["GET"])  # noqa: F821
@login_required
def get_workspace_patch(patch_id):
    try:
        return get_json_result(data=WorkspacePatchService.get_patch(str(patch_id)))
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/patches/<patch_id>/audit", methods=["GET"])  # noqa: F821
@login_required
def get_workspace_patch_audit(patch_id):
    try:
        return get_json_result(data={"items": WorkspacePatchService.list_audit(str(patch_id))})
    except WorkspaceFileError as exc:
        return _workspace_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
