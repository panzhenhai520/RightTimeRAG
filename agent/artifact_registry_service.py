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

from __future__ import annotations

import copy
import json
import logging
import time
from typing import Any

from common.misc_utils import get_uuid

REDIS_CONN = None


def _redis_conn():
    global REDIS_CONN
    if REDIS_CONN is not None:
        return REDIS_CONN
    from rag.utils.redis_conn import REDIS_CONN as conn

    return conn


class ArtifactPermissionError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


class AgentArtifactRegistryService:
    """Records generated Agent artifacts so downloads can be authorized and audited."""

    TTL_SECONDS = 30 * 24 * 60 * 60
    MAX_AUDIT_RECORDS = 500

    @classmethod
    def _key(cls, tenant_id: str, artifact_id: str) -> str:
        return f"agent_artifact:{tenant_id}:{artifact_id}"

    @staticmethod
    def _load_json(key: str, default: Any):
        raw = _redis_conn().get(key)
        if not raw:
            return copy.deepcopy(default)
        try:
            return json.loads(raw)
        except Exception:
            logging.warning("AgentArtifactRegistryService failed to parse redis payload. key=%s", key)
            return copy.deepcopy(default)

    @classmethod
    def _save(cls, tenant_id: str, artifact_id: str, record: dict[str, Any]) -> None:
        _redis_conn().set_obj(cls._key(str(tenant_id), str(artifact_id)), record, cls.TTL_SECONDS)

    @classmethod
    def register(
        cls,
        *,
        tenant_id: str,
        artifact_id: str,
        filename: str,
        mime_type: str = "",
        size: int | None = None,
        run_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        node_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        tenant_id = str(tenant_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        if not tenant_id or not artifact_id:
            raise ArtifactPermissionError("INVALID_ARGUMENT", "tenant_id and artifact_id are required.")
        record = {
            "artifact_id": artifact_id,
            "doc_id": artifact_id,
            "tenant_id": tenant_id,
            "filename": str(filename or "artifact.bin"),
            "mime_type": str(mime_type or ""),
            "size": int(size or 0),
            "run_id": str(run_id or ""),
            "session_id": str(session_id or ""),
            "agent_id": str(agent_id or ""),
            "node_id": str(node_id or ""),
            "metadata": metadata if isinstance(metadata, dict) else {},
            "created_at": time.time(),
            "audit": [],
        }
        cls._append_audit(record, "artifact_registered", {"run_id": record["run_id"], "node_id": record["node_id"]})
        cls._save(tenant_id, artifact_id, record)
        return copy.deepcopy(record)

    @classmethod
    def get(cls, *, tenant_id: str, artifact_id: str) -> dict[str, Any] | None:
        tenant_id = str(tenant_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        if not tenant_id or not artifact_id:
            return None
        record = cls._load_json(cls._key(tenant_id, artifact_id), None)
        return record if isinstance(record, dict) else None

    @classmethod
    def record_audit(
        cls,
        *,
        tenant_id: str,
        artifact_id: str,
        event: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        record = cls.get(tenant_id=tenant_id, artifact_id=artifact_id)
        if not record:
            return None
        audit = cls._append_audit(record, event, payload or {})
        cls._save(str(tenant_id), str(artifact_id), record)
        return audit

    @classmethod
    def _append_audit(cls, record: dict[str, Any], event: str, payload: dict[str, Any]) -> dict[str, Any]:
        audit_record = {
            "audit_id": payload.get("audit_id") or get_uuid(),
            "event": event,
            "created_at": time.time(),
            **payload,
        }
        audit = record.setdefault("audit", [])
        audit.append(audit_record)
        if len(audit) > cls.MAX_AUDIT_RECORDS:
            del audit[: len(audit) - cls.MAX_AUDIT_RECORDS]
        return audit_record

    @classmethod
    def authorize_download(
        cls,
        *,
        tenant_id: str,
        artifact_id: str,
        requested_run_id: str | None = None,
        requested_session_id: str | None = None,
        allow_legacy: bool = True,
    ) -> dict[str, Any]:
        tenant_id = str(tenant_id or "").strip()
        artifact_id = str(artifact_id or "").strip()
        requested_run_id = str(requested_run_id or "").strip()
        requested_session_id = str(requested_session_id or "").strip()
        if not tenant_id or not artifact_id:
            raise ArtifactPermissionError("INVALID_ARGUMENT", "tenant_id and artifact_id are required.")

        record = cls.get(tenant_id=tenant_id, artifact_id=artifact_id)
        if not record:
            if allow_legacy and not requested_run_id and not requested_session_id:
                return {"artifact_id": artifact_id, "doc_id": artifact_id, "tenant_id": tenant_id, "legacy": True}
            raise ArtifactPermissionError(
                "ARTIFACT_NOT_FOUND",
                "Artifact is not registered for this tenant.",
                {"artifact_id": artifact_id, "requested_run_id": requested_run_id},
            )

        bound_run_id = str(record.get("run_id") or "")
        if bound_run_id and requested_run_id != bound_run_id:
            cls.record_audit(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                event="permission_denied",
                payload={
                    "action": "artifact_download",
                    "reason": "run_id_mismatch",
                    "requested_run_id": requested_run_id,
                    "bound_run_id": bound_run_id,
                },
            )
            raise ArtifactPermissionError(
                "PERMISSION_DENIED",
                "Artifact does not belong to the requested run.",
                {"artifact_id": artifact_id, "requested_run_id": requested_run_id, "bound_run_id": bound_run_id},
            )

        bound_session_id = str(record.get("session_id") or "")
        if bound_session_id and requested_session_id and requested_session_id != bound_session_id:
            cls.record_audit(
                tenant_id=tenant_id,
                artifact_id=artifact_id,
                event="permission_denied",
                payload={
                    "action": "artifact_download",
                    "reason": "session_id_mismatch",
                    "requested_session_id": requested_session_id,
                    "bound_session_id": bound_session_id,
                },
            )
            raise ArtifactPermissionError(
                "PERMISSION_DENIED",
                "Artifact does not belong to the requested session.",
                {"artifact_id": artifact_id, "requested_session_id": requested_session_id, "bound_session_id": bound_session_id},
            )
        return copy.deepcopy(record)
