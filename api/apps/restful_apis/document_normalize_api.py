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
from api.db.services.document_normalize_service import DocumentNormalizeService
from api.db.services.workspace_file_service import WorkspaceFileError
from api.utils.api_utils import add_tenant_id_to_kwargs, get_json_result, get_request_json, server_error_response
from common.constants import RetCode
from common.misc_utils import thread_pool_exec


def _document_normalize_error_response(exc: WorkspaceFileError):
    return get_json_result(data=exc.to_dict(), code=RetCode.DATA_ERROR, message=str(exc))


@manager.route("/workspace/documents/normalize", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def normalize_workspace_document(tenant_id):
    req = await get_request_json()
    try:
        data = await thread_pool_exec(
            DocumentNormalizeService.normalize,
            path=req.get("path", ""),
            root=req.get("root", ""),
            max_bytes=req.get("max_bytes"),
            chunk_chars=req.get("chunk_chars"),
            tenant_id=str(tenant_id),
            user_id=str(req.get("user_id") or tenant_id),
            run_id=str(req.get("run_id") or ""),
        )
        return get_json_result(data=data)
    except WorkspaceFileError as exc:
        return _document_normalize_error_response(exc)
    except Exception as exc:
        return server_error_response(exc)
