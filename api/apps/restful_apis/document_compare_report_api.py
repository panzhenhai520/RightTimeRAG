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

from agent.artifact_service import ArtifactService
from api.apps import login_required
from api.db.services.document_compare_report_service import DocumentCompareReportService
from api.utils.api_utils import add_tenant_id_to_kwargs, get_json_result, get_request_json, server_error_response


@manager.route("/workspace/documents/report", methods=["POST"])  # noqa: F821
@login_required
@add_tenant_id_to_kwargs
async def compose_workspace_document_report(tenant_id):
    req = await get_request_json()
    try:
        report = DocumentCompareReportService.build_report(
            title=str(req.get("title") or "文档比对报告"),
            files=req.get("files"),
            documents=req.get("documents"),
            diff=req.get("diff"),
            table_diff=req.get("table_diff"),
            matches=req.get("matches"),
            conflicts=req.get("conflicts"),
            missing_requirements=req.get("missing_requirements"),
            risk_points=req.get("risk_points"),
            audit=req.get("audit"),
            run_id=str(req.get("run_id") or ""),
            agent_id=str(req.get("agent_id") or ""),
            generated_by="document_compare_report_api",
        )
        data = {"report": report, "markdown": DocumentCompareReportService.render_markdown(report)}
        if req.get("create_downloads"):
            downloads = []
            formats = req.get("output_formats") or ["markdown", "json"]
            if isinstance(formats, str):
                formats = [item.strip() for item in formats.split(",") if item.strip()]
            for fmt in formats:
                content, mime_type = DocumentCompareReportService.render_bytes(report, str(fmt))
                download = ArtifactService.create_download_info(
                    str(tenant_id),
                    content,
                    DocumentCompareReportService.filename(str(req.get("filename") or "document_compare_report"), str(fmt)),
                    mime_type=mime_type,
                    run_id=str(req.get("run_id") or ""),
                    agent_id=str(req.get("agent_id") or ""),
                    metadata={"kind": "document_compare_report", "format": str(fmt), "risk_level": report.get("risk_level")},
                )
                downloads.append(download)
            report["audit"]["report_artifacts"] = downloads
            data["downloads"] = downloads
            data["markdown"] = DocumentCompareReportService.render_markdown(report)
        return get_json_result(data=data)
    except Exception as exc:
        return server_error_response(exc)
