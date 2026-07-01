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
from common.constants import RetCode
from api.db.services.document_extract_service import DocumentExtractService
from api.utils.api_utils import get_json_result, get_request_json, server_error_response


EXTRACT_METHODS = {
    "clauses": DocumentExtractService.extract_clauses,
    "obligations": DocumentExtractService.extract_obligations,
    "definitions": DocumentExtractService.extract_definitions,
    "viewpoints": DocumentExtractService.extract_viewpoints,
    "risks": DocumentExtractService.extract_risks,
    "table_facts": DocumentExtractService.extract_table_facts,
}


@manager.route("/workspace/documents/extract", methods=["POST"])  # noqa: F821
@login_required
async def extract_workspace_document_items():
    req = await get_request_json()
    kind = str(req.get("kind") or "clauses")
    method = EXTRACT_METHODS.get(kind)
    if method is None:
        return get_json_result(data={"error_code": "UNSUPPORTED_EXTRACT_KIND", "kind": kind}, code=RetCode.ARGUMENT_ERROR, message="Unsupported extract kind.")
    try:
        value = req.get("document") if req.get("document") is not None else req.get("content", "")
        if kind in {"clauses", "obligations", "definitions", "viewpoints", "risks"}:
            data = method(value, min_chars=int(req.get("min_chars") or 4))
        else:
            data = method(value)
        return get_json_result(data=data)
    except Exception as exc:
        return server_error_response(exc)
