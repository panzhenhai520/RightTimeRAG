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

import copy
import hashlib
import json
import logging
import threading
import time
from typing import Any

from common.misc_utils import get_uuid
from rag.utils.redis_conn import REDIS_CONN


class DocumentWriteCoordinatorError(Exception):
    """Structured error for shared document write coordination."""

    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


class AgentDocumentWriteCoordinatorService:
    """Single-writer coordination for shared document updates.

    Agent runs must submit patch proposals against an explicit document version.
    The coordinator applies selected proposals under a per-document write lock,
    checks `expected_version`, stores a new immutable version, and records audit
    data. Long LLM/retrieval work happens before this service is called; only
    the short write transaction is serialized.
    """

    TTL_SECONDS = 30 * 24 * 60 * 60
    MAX_AUDIT_RECORDS = 1000
    _locks: dict[str, threading.Lock] = {}
    _locks_guard = threading.Lock()

    @classmethod
    def _state_key(cls, tenant_id: str, document_id: str) -> str:
        return f"agent_document_write:{tenant_id}:{document_id}:state"

    @classmethod
    def _lock_for(cls, tenant_id: str, document_id: str) -> threading.Lock:
        key = cls._state_key(tenant_id, document_id)
        with cls._locks_guard:
            if key not in cls._locks:
                cls._locks[key] = threading.Lock()
            return cls._locks[key]

    @staticmethod
    def _load_json(key: str, default: Any):
        raw = REDIS_CONN.get(key)
        if not raw:
            return copy.deepcopy(default)
        try:
            return json.loads(raw)
        except Exception:
            logging.warning("AgentDocumentWriteCoordinatorService failed to parse redis payload. key=%s", key)
            return copy.deepcopy(default)

    @staticmethod
    def _canonical_content(content: Any) -> str:
        if isinstance(content, str):
            return content
        return json.dumps(content, ensure_ascii=False, sort_keys=True)

    @classmethod
    def _content_hash(cls, content: Any) -> str:
        return hashlib.sha256(cls._canonical_content(content).encode("utf-8")).hexdigest()

    @staticmethod
    def snapshot_id(document_id: str, version: int) -> str:
        return f"{document_id}:v{int(version)}"

    @classmethod
    def _empty_state(cls, document_id: str) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "document_id": document_id,
            "current_version": 0,
            "versions": {},
            "proposals": {},
            "audit": [],
        }

    @classmethod
    def _load_state(cls, tenant_id: str, document_id: str) -> dict[str, Any]:
        state = cls._load_json(cls._state_key(tenant_id, document_id), cls._empty_state(document_id))
        if not isinstance(state, dict):
            state = cls._empty_state(document_id)
        state.setdefault("schema_version", 1)
        state.setdefault("document_id", document_id)
        state.setdefault("current_version", 0)
        state.setdefault("versions", {})
        state.setdefault("proposals", {})
        state.setdefault("audit", [])
        return state

    @classmethod
    def _save_state(cls, tenant_id: str, document_id: str, state: dict[str, Any]) -> None:
        REDIS_CONN.set_obj(cls._state_key(tenant_id, document_id), state, cls.TTL_SECONDS)

    @classmethod
    def _append_audit(cls, state: dict[str, Any], event: str, payload: dict[str, Any]) -> dict[str, Any]:
        record = {
            "audit_id": payload.get("audit_id") or get_uuid(),
            "event": event,
            "created_at": time.time(),
            **payload,
        }
        audit = state.setdefault("audit", [])
        audit.append(record)
        if len(audit) > cls.MAX_AUDIT_RECORDS:
            del audit[: len(audit) - cls.MAX_AUDIT_RECORDS]
        return record

    @classmethod
    def _version_record(
        cls,
        *,
        document_id: str,
        version: int,
        content: Any,
        metadata: dict[str, Any] | None = None,
        source: str = "",
        audit_id: str = "",
    ) -> dict[str, Any]:
        return {
            "document_id": document_id,
            "version": int(version),
            "snapshot_id": cls.snapshot_id(document_id, int(version)),
            "content": content,
            "content_hash": cls._content_hash(content),
            "metadata": metadata or {},
            "source": source or "",
            "audit_id": audit_id or "",
            "created_at": time.time(),
        }

    @classmethod
    def publish_snapshot(
        cls,
        *,
        tenant_id: str,
        document_id: str,
        content: Any,
        version: int | None = None,
        metadata: dict[str, Any] | None = None,
        source: str = "snapshot_publish",
        audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document_id = str(document_id or "").strip()
        if not tenant_id or not document_id:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "tenant_id and document_id are required.")

        lock = cls._lock_for(str(tenant_id), document_id)
        with lock:
            state = cls._load_state(str(tenant_id), document_id)
            next_version = int(version or (int(state.get("current_version") or 0) + 1))
            if str(next_version) in state["versions"]:
                raise DocumentWriteCoordinatorError(
                    "VERSION_EXISTS",
                    f"Document version already exists: {next_version}",
                    {"document_id": document_id, "version": next_version},
                )
            record = cls._version_record(
                document_id=document_id,
                version=next_version,
                content=content,
                metadata=metadata,
                source=source,
            )
            audit_record = cls._append_audit(
                state,
                "snapshot_published",
                {
                    **(audit or {}),
                    "document_id": document_id,
                    "new_version": next_version,
                    "snapshot_id": record["snapshot_id"],
                    "source": source,
                },
            )
            record["audit_id"] = audit_record["audit_id"]
            state["versions"][str(next_version)] = record
            state["current_version"] = max(int(state.get("current_version") or 0), next_version)
            cls._save_state(str(tenant_id), document_id, state)
            return copy.deepcopy(record)

    create_snapshot = publish_snapshot

    @classmethod
    def get_snapshot(cls, *, tenant_id: str, document_id: str, version: int | None = None) -> dict[str, Any]:
        state = cls._load_state(str(tenant_id), str(document_id))
        selected_version = int(version or state.get("current_version") or 0)
        record = state["versions"].get(str(selected_version))
        if not record:
            raise DocumentWriteCoordinatorError(
                "SNAPSHOT_NOT_FOUND",
                f"Document snapshot not found: {document_id} v{selected_version}",
                {"document_id": document_id, "version": selected_version},
            )
        return copy.deepcopy(record)

    @staticmethod
    def _normalize_patches(patches: Any) -> list[dict[str, Any]]:
        if isinstance(patches, str):
            try:
                patches = json.loads(patches)
            except Exception as exc:
                raise DocumentWriteCoordinatorError("INVALID_PATCH", "patches must be a JSON array.") from exc
        if not isinstance(patches, list) or not patches:
            raise DocumentWriteCoordinatorError("INVALID_PATCH", "patches must contain at least one patch.")
        normalized = []
        for index, item in enumerate(patches):
            if not isinstance(item, dict):
                raise DocumentWriteCoordinatorError("INVALID_PATCH", f"patches[{index}] must be an object.")
            operation = str(item.get("operation") or item.get("op") or "").strip()
            if not operation:
                raise DocumentWriteCoordinatorError("INVALID_PATCH", f"patches[{index}].operation is required.")
            normalized.append({**item, "operation": operation})
        return normalized

    @classmethod
    def build_patch_proposal(
        cls,
        *,
        proposal_id: str | None = None,
        base_document_id: str,
        base_version: int,
        agent_id: str,
        run_id: str,
        patches: list[dict[str, Any]],
        summary: str = "",
        base_snapshot_id: str = "",
        proposal_type: str = "document_patch_proposal",
        confidence: float | int | None = None,
        references: list[dict[str, Any]] | None = None,
        risk_flags: list[str] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        base_document_id = str(base_document_id or "").strip()
        agent_id = str(agent_id or "").strip()
        run_id = str(run_id or "").strip()
        if not base_document_id or not agent_id or not run_id:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "base_document_id, agent_id and run_id are required.")
        base_version = int(base_version)
        if base_version <= 0:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "base_version must be positive.")
        try:
            confidence_value = float(confidence) if confidence is not None else None
        except Exception:
            confidence_value = None
        if confidence_value is not None:
            confidence_value = max(0.0, min(1.0, confidence_value))
        return {
            "type": proposal_type,
            "proposal_id": str(proposal_id or get_uuid()),
            "proposal_type": proposal_type,
            "base_document_id": base_document_id,
            "base_version": base_version,
            "base_snapshot_id": base_snapshot_id or cls.snapshot_id(base_document_id, base_version),
            "agent_id": agent_id,
            "run_id": run_id,
            "summary": str(summary or ""),
            "patches": cls._normalize_patches(patches),
            "confidence": confidence_value,
            "references": references or [],
            "risk_flags": risk_flags or [],
            "metadata": metadata or {},
            "status": "proposed",
            "created_at": time.time(),
        }

    @classmethod
    def submit_patch_proposal(
        cls,
        *,
        tenant_id: str,
        proposal: dict[str, Any],
        authorized_agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(proposal, dict):
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "proposal must be an object.")
        document_id = str(proposal.get("base_document_id") or "").strip()
        proposal_id = str(proposal.get("proposal_id") or "").strip()
        agent_id = str(proposal.get("agent_id") or "").strip()
        base_version = int(proposal.get("base_version") or 0)
        if not document_id or not proposal_id or not agent_id or base_version <= 0:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "proposal_id, base_document_id, agent_id and base_version are required.")
        lock = cls._lock_for(str(tenant_id), document_id)
        with lock:
            state = cls._load_state(str(tenant_id), document_id)
            if authorized_agent_ids is not None and agent_id not in {str(item) for item in authorized_agent_ids}:
                cls._append_audit(
                    state,
                    "permission_denied",
                    {
                        "document_id": document_id,
                        "proposal_id": proposal_id,
                        "agent_id": agent_id,
                        "base_version": base_version,
                        "action": "submit_patch_proposal",
                        "reason": "agent_not_authorized",
                    },
                )
                cls._save_state(str(tenant_id), document_id, state)
                raise DocumentWriteCoordinatorError("PERMISSION_DENIED", "agent is not authorized to submit this proposal.", {"agent_id": agent_id})
            if str(base_version) not in state["versions"]:
                raise DocumentWriteCoordinatorError(
                    "SNAPSHOT_NOT_FOUND",
                    f"Base document version not found: {document_id} v{base_version}",
                    {"document_id": document_id, "base_version": base_version},
                )
            normalized = cls.build_patch_proposal(
                proposal_id=proposal_id,
                base_document_id=document_id,
                base_version=base_version,
                base_snapshot_id=str(proposal.get("base_snapshot_id") or ""),
                agent_id=agent_id,
                run_id=str(proposal.get("run_id") or ""),
                summary=str(proposal.get("summary") or ""),
                patches=proposal.get("patches") or [],
                proposal_type=str(proposal.get("proposal_type") or proposal.get("type") or "document_patch_proposal"),
                confidence=proposal.get("confidence"),
                references=proposal.get("references") if isinstance(proposal.get("references"), list) else [],
                risk_flags=proposal.get("risk_flags") if isinstance(proposal.get("risk_flags"), list) else [],
                metadata=proposal.get("metadata") if isinstance(proposal.get("metadata"), dict) else {},
            )
            state["proposals"][proposal_id] = normalized
            cls._append_audit(
                state,
                "proposal_submitted",
                {
                    "document_id": document_id,
                    "proposal_id": proposal_id,
                    "base_version": base_version,
                    "agent_id": agent_id,
                    "run_id": normalized["run_id"],
                },
            )
            cls._save_state(str(tenant_id), document_id, state)
            return copy.deepcopy(normalized)

    @classmethod
    def _apply_one_patch(cls, content: str, patch: dict[str, Any]) -> str:
        operation = str(patch.get("operation") or "").strip()
        target = str(patch.get("target") or "")
        text = str(patch.get("text") if patch.get("text") is not None else patch.get("replacement") or "")
        if operation == "append":
            return content + text
        if operation == "prepend":
            return text + content
        if operation == "replace":
            if not target or target not in content:
                raise DocumentWriteCoordinatorError("PATCH_TARGET_NOT_FOUND", "replace target was not found.", {"target": target[:120]})
            return content.replace(target, text, 1)
        if operation == "insert_after":
            if not target or target not in content:
                raise DocumentWriteCoordinatorError("PATCH_TARGET_NOT_FOUND", "insert_after target was not found.", {"target": target[:120]})
            return content.replace(target, target + text, 1)
        if operation == "insert_before":
            if not target or target not in content:
                raise DocumentWriteCoordinatorError("PATCH_TARGET_NOT_FOUND", "insert_before target was not found.", {"target": target[:120]})
            return content.replace(target, text + target, 1)
        if operation == "delete":
            if not target or target not in content:
                raise DocumentWriteCoordinatorError("PATCH_TARGET_NOT_FOUND", "delete target was not found.", {"target": target[:120]})
            return content.replace(target, "", 1)
        raise DocumentWriteCoordinatorError("UNSUPPORTED_PATCH_OPERATION", f"Unsupported patch operation: {operation}")

    @classmethod
    def _apply_patches(cls, base_content: Any, proposals: list[dict[str, Any]]) -> str:
        content = cls._canonical_content(base_content)
        for proposal in proposals:
            for patch in proposal.get("patches") or []:
                content = cls._apply_one_patch(content, patch)
        return content

    @classmethod
    def apply_write_request(
        cls,
        *,
        tenant_id: str,
        document_id: str,
        expected_version: int,
        selected_proposals: list[str],
        merge_strategy: str = "single_writer",
        source: str = "write_coordinator",
        audit: dict[str, Any] | None = None,
        authorized_agent_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        document_id = str(document_id or "").strip()
        if not document_id or int(expected_version or 0) <= 0:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "document_id and expected_version are required.")
        if not isinstance(selected_proposals, list) or not selected_proposals:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "selected_proposals must contain at least one proposal id.")
        if merge_strategy != "single_writer":
            raise DocumentWriteCoordinatorError("UNSUPPORTED_MERGE_STRATEGY", f"Unsupported merge_strategy: {merge_strategy}")

        lock = cls._lock_for(str(tenant_id), document_id)
        with lock:
            state = cls._load_state(str(tenant_id), document_id)
            current_version = int(state.get("current_version") or 0)
            expected_version = int(expected_version)
            if current_version != expected_version:
                raise DocumentWriteCoordinatorError(
                    "VERSION_CONFLICT",
                    f"Document version conflict: expected {expected_version}, current {current_version}.",
                    {"document_id": document_id, "expected_version": expected_version, "current_version": current_version},
                )
            base_record = state["versions"].get(str(expected_version))
            if not base_record:
                raise DocumentWriteCoordinatorError("SNAPSHOT_NOT_FOUND", f"Base version not found: {expected_version}")

            proposals = []
            authorized = {str(item) for item in authorized_agent_ids} if authorized_agent_ids is not None else None
            for proposal_id in selected_proposals:
                proposal = state["proposals"].get(str(proposal_id))
                if not proposal:
                    raise DocumentWriteCoordinatorError("PROPOSAL_NOT_FOUND", f"Patch proposal not found: {proposal_id}")
                if proposal.get("base_document_id") != document_id:
                    raise DocumentWriteCoordinatorError("PROPOSAL_DOCUMENT_MISMATCH", f"Proposal belongs to another document: {proposal_id}")
                if int(proposal.get("base_version") or 0) != expected_version:
                    raise DocumentWriteCoordinatorError(
                        "VERSION_CONFLICT",
                        f"Proposal base version does not match expected_version: {proposal_id}",
                        {"proposal_id": proposal_id, "proposal_base_version": proposal.get("base_version"), "expected_version": expected_version},
                    )
                if authorized is not None and str(proposal.get("agent_id")) not in authorized:
                    cls._append_audit(
                        state,
                        "permission_denied",
                        {
                            **(audit or {}),
                            "document_id": document_id,
                            "proposal_id": proposal_id,
                            "agent_id": proposal.get("agent_id"),
                            "base_version": expected_version,
                            "action": "apply_write_request",
                            "reason": "agent_not_authorized",
                        },
                    )
                    cls._save_state(str(tenant_id), document_id, state)
                    raise DocumentWriteCoordinatorError(
                        "PERMISSION_DENIED",
                        "agent is not authorized to apply this proposal.",
                        {"proposal_id": proposal_id, "agent_id": proposal.get("agent_id")},
                    )
                proposals.append(proposal)

            try:
                new_content = cls._apply_patches(base_record["content"], proposals)
            except DocumentWriteCoordinatorError as exc:
                cls._append_audit(
                    state,
                    "write_failed",
                    {
                        **(audit or {}),
                        "document_id": document_id,
                        "base_version": expected_version,
                        "selected_proposals": selected_proposals,
                        "error_code": exc.code,
                        "error": str(exc),
                    },
                )
                cls._save_state(str(tenant_id), document_id, state)
                raise

            new_version = current_version + 1
            audit_record = cls._append_audit(
                state,
                "write_applied",
                {
                    **(audit or {}),
                    "document_id": document_id,
                    "base_version": expected_version,
                    "new_version": new_version,
                    "selected_proposals": selected_proposals,
                    "agent_ids": [proposal.get("agent_id") for proposal in proposals],
                    "run_ids": [proposal.get("run_id") for proposal in proposals],
                    "merge_strategy": merge_strategy,
                    "source": source,
                },
            )
            record = cls._version_record(
                document_id=document_id,
                version=new_version,
                content=new_content,
                metadata={"base_version": expected_version, "selected_proposals": selected_proposals},
                source=source,
                audit_id=audit_record["audit_id"],
            )
            state["versions"][str(new_version)] = record
            state["current_version"] = new_version
            for proposal in proposals:
                proposal["status"] = "applied"
                proposal["applied_version"] = new_version
                proposal["applied_audit_id"] = audit_record["audit_id"]
            cls._save_state(str(tenant_id), document_id, state)
            return {
                "status": "succeeded",
                "document_id": document_id,
                "base_version": expected_version,
                "new_version": new_version,
                "snapshot_id": record["snapshot_id"],
                "content_hash": record["content_hash"],
                "audit_id": audit_record["audit_id"],
                "selected_proposals": selected_proposals,
            }

    @classmethod
    def rollback(
        cls,
        *,
        tenant_id: str,
        document_id: str,
        target_version: int,
        expected_version: int | None = None,
        source: str = "rollback",
        audit: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        document_id = str(document_id or "").strip()
        target_version = int(target_version or 0)
        if not document_id or target_version <= 0:
            raise DocumentWriteCoordinatorError("INVALID_ARGUMENT", "document_id and target_version are required.")

        lock = cls._lock_for(str(tenant_id), document_id)
        with lock:
            state = cls._load_state(str(tenant_id), document_id)
            current_version = int(state.get("current_version") or 0)
            if expected_version is not None and current_version != int(expected_version):
                raise DocumentWriteCoordinatorError(
                    "VERSION_CONFLICT",
                    f"Document version conflict: expected {expected_version}, current {current_version}.",
                    {"document_id": document_id, "expected_version": expected_version, "current_version": current_version},
                )
            target = state["versions"].get(str(target_version))
            if not target:
                raise DocumentWriteCoordinatorError("SNAPSHOT_NOT_FOUND", f"Rollback target not found: {target_version}")
            new_version = current_version + 1
            audit_record = cls._append_audit(
                state,
                "rollback_applied",
                {
                    **(audit or {}),
                    "document_id": document_id,
                    "base_version": current_version,
                    "target_version": target_version,
                    "new_version": new_version,
                    "source": source,
                },
            )
            record = cls._version_record(
                document_id=document_id,
                version=new_version,
                content=target["content"],
                metadata={"rolled_back_to": target_version, "base_version": current_version},
                source=source,
                audit_id=audit_record["audit_id"],
            )
            state["versions"][str(new_version)] = record
            state["current_version"] = new_version
            cls._save_state(str(tenant_id), document_id, state)
            return {
                "status": "succeeded",
                "document_id": document_id,
                "target_version": target_version,
                "new_version": new_version,
                "snapshot_id": record["snapshot_id"],
                "audit_id": audit_record["audit_id"],
            }

    @classmethod
    def list_audit(cls, *, tenant_id: str, document_id: str) -> list[dict[str, Any]]:
        state = cls._load_state(str(tenant_id), str(document_id))
        return copy.deepcopy(state.get("audit") or [])
