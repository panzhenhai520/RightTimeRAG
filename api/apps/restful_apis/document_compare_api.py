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
from api.db.services.document_compare_service import DocumentCompareService
from api.utils.api_utils import get_json_result, get_request_json, server_error_response
from common.constants import RetCode


@manager.route("/workspace/documents/diff", methods=["POST"])  # noqa: F821
@login_required
async def diff_workspace_documents():
    req = await get_request_json()
    try:
        granularity = str(req.get("granularity") or "paragraphs")
        left = req.get("left") if req.get("left") is not None else req.get("left_document")
        right = req.get("right") if req.get("right") is not None else req.get("right_document")
        if granularity == "lines":
            data = DocumentCompareService.diff_lines(left, right)
        elif granularity == "paragraphs":
            data = DocumentCompareService.diff_paragraphs(left, right)
        elif granularity == "sections":
            data = DocumentCompareService.diff_sections(left, right)
        elif granularity == "hash":
            data = DocumentCompareService.diff_hash(left, right)
        else:
            return get_json_result(data={"error_code": "UNSUPPORTED_DIFF_GRANULARITY", "granularity": granularity}, code=RetCode.ARGUMENT_ERROR, message="Unsupported diff granularity.")
        return get_json_result(data=data)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/documents/table-diff", methods=["POST"])  # noqa: F821
@login_required
async def diff_workspace_document_tables():
    req = await get_request_json()
    try:
        left = req.get("left") if req.get("left") is not None else req.get("left_document")
        right = req.get("right") if req.get("right") is not None else req.get("right_document")
        return get_json_result(data=DocumentCompareService.diff_tables(left, right))
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/documents/compare", methods=["POST"])  # noqa: F821
@login_required
async def compare_workspace_document_items():
    req = await get_request_json()
    try:
        left = req.get("left") if req.get("left") is not None else req.get("left_items")
        right = req.get("right") if req.get("right") is not None else req.get("right_items")
        data = DocumentCompareService.compare_items(left, right, min_score=float(req.get("min_score") or 0.2))
        return get_json_result(data=data)
    except Exception as exc:
        return server_error_response(exc)


@manager.route("/workspace/documents/conflicts", methods=["POST"])  # noqa: F821
@login_required
async def detect_workspace_document_conflicts():
    req = await get_request_json()
    try:
        standard = req.get("standard") if req.get("standard") is not None else req.get("standard_items")
        target = req.get("target") if req.get("target") is not None else req.get("target_items")
        data = DocumentCompareService.detect_conflicts(standard, target, min_score=float(req.get("min_score") or 0.18))
        return get_json_result(data=data)
    except Exception as exc:
        return server_error_response(exc)
