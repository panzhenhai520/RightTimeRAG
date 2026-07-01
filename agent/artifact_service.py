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

import base64
import mimetypes
import os
from typing import Any
from urllib.parse import quote

from agent.artifact_registry_service import AgentArtifactRegistryService
from common import settings
from common.misc_utils import get_uuid


_MIME_TYPES = {
    "csv": "text/csv",
    "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "html": "text/html",
    "json": "application/json",
    "markdown": "text/markdown",
    "md": "text/markdown",
    "pdf": "application/pdf",
    "svg": "image/svg+xml",
    "txt": "text/plain",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "zip": "application/zip",
}


class ArtifactService:
    @staticmethod
    def guess_mime_type(filename: str = "", extension: str = "", fallback: str = "application/octet-stream") -> str:
        ext = (extension or os.path.splitext(filename or "")[1].lstrip(".")).lower()
        if ext in _MIME_TYPES:
            return _MIME_TYPES[ext]
        guessed, _ = mimetypes.guess_type(filename or f"file.{ext}")
        return guessed or fallback

    @staticmethod
    def create_download_info(
        tenant_id: str,
        content: bytes,
        filename: str,
        mime_type: str | None = None,
        run_id: str | None = None,
        node_id: str | None = None,
        include_base64: bool = False,
        include_download_info_in_content: bool = False,
        metadata: dict[str, Any] | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(content, bytes):
            raise TypeError("Artifact content must be bytes.")
        if not filename:
            filename = "artifact.bin"

        doc_id = get_uuid()
        settings.STORAGE_IMPL.put(tenant_id, doc_id, content)
        artifact_metadata = dict(metadata or {})
        if run_id:
            artifact_metadata["run_id"] = run_id
        if node_id:
            artifact_metadata["node_id"] = node_id
        download_url = f"/v1/agents/download?id={quote(doc_id)}"
        if run_id:
            download_url += f"&run_id={quote(str(run_id))}"
        if session_id:
            download_url += f"&session_id={quote(str(session_id))}"
        info = {
            "artifact_id": doc_id,
            "doc_id": doc_id,
            "filename": filename,
            "mime_type": mime_type or ArtifactService.guess_mime_type(filename),
            "size": len(content),
            "download_url": download_url,
        }
        if run_id:
            info["run_id"] = run_id
        if session_id:
            info["session_id"] = session_id
        if agent_id:
            info["agent_id"] = agent_id
        if node_id:
            info["node_id"] = node_id
        if include_base64:
            info["base64"] = base64.b64encode(content).decode("utf-8")
        if include_download_info_in_content:
            info["include_download_info_in_content"] = True
        if artifact_metadata:
            info["metadata"] = artifact_metadata
        try:
            AgentArtifactRegistryService.register(
                tenant_id=tenant_id,
                artifact_id=doc_id,
                filename=filename,
                mime_type=info["mime_type"],
                size=len(content),
                run_id=run_id,
                session_id=session_id,
                agent_id=agent_id,
                node_id=node_id,
                metadata=artifact_metadata,
            )
        except Exception:
            # Artifact generation must not fail only because the audit registry is unavailable.
            pass
        return info

    @staticmethod
    def attachment_from_download(download_info: dict[str, Any]) -> dict[str, Any]:
        filename = download_info.get("filename") or "artifact.bin"
        return {
            "artifact_id": download_info.get("artifact_id") or download_info.get("doc_id"),
            "doc_id": download_info.get("doc_id"),
            "format": filename.split(".")[-1].lower() if "." in filename else "",
            "file_name": filename,
            "mime_type": download_info.get("mime_type"),
            "size": download_info.get("size"),
            "download_url": download_info.get("download_url"),
        }
