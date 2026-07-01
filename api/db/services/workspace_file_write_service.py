#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import difflib
import hashlib
from copy import deepcopy
from pathlib import Path
from typing import Any

from api.db.services.agent_task_approval_service import AgentTaskApprovalError, AgentTaskApprovalService
from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from common.misc_utils import get_uuid


class WorkspaceFileWriteService:
    """Controlled workspace writes behind the same allowlist used by reads."""

    MODES = {"create", "overwrite", "append"}
    DEFAULT_MAX_WRITE_BYTES = 2 * 1024 * 1024
    _records: dict[str, dict[str, Any]] = {}
    _audits: dict[str, list[dict[str, Any]]] = {}

    @classmethod
    def reset(cls) -> None:
        cls._records = {}
        cls._audits = {}

    @classmethod
    def write_file(
        cls,
        *,
        path: str,
        root: str = "",
        roots: list[str | Path] | None = None,
        content: str = "",
        mode: str = "create",
        encoding: str = "utf-8",
        expected_hash: str = "",
        dry_run: bool = False,
        require_approval: bool = True,
        approval_id: str = "",
        manual_approved: bool = False,
        task_id: str = "",
        requester_id: str = "",
        policy: dict[str, Any] | None = None,
        max_bytes: int | None = None,
        tenant_id: str = "",
        user_id: str = "",
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        mode = str(mode or "create").strip().lower()
        if mode not in cls.MODES:
            raise WorkspaceFileError("INVALID_WRITE_MODE", "Unsupported workspace write mode.", {"mode": mode})
        resolved, root_info = cls._resolve_write_target(path=path, root=root, roots=roots)
        content = str(content or "")
        cls._check_size(content, encoding=encoding, max_bytes=max_bytes)

        exists = resolved.exists()
        if mode == "create" and exists:
            raise WorkspaceFileError("PATH_EXISTS", "Workspace file already exists.", {"path": str(resolved)})
        if mode in {"overwrite", "append"} and not exists:
            raise WorkspaceFileError("PATH_NOT_FOUND", "Workspace file does not exist.", {"path": str(resolved)})
        if exists and not resolved.is_file():
            raise WorkspaceFileError("NOT_A_FILE", "Workspace path is not a file.", {"path": str(resolved)})

        before = resolved.read_text(encoding=encoding or "utf-8", errors="replace") if exists else ""
        before_hash = cls._hash_text(before, encoding=encoding)
        if expected_hash and before_hash != expected_hash:
            raise WorkspaceFileError(
                "HASH_MISMATCH",
                "Workspace file hash does not match expected_hash.",
                {"path": str(resolved), "expected_hash": expected_hash, "actual_hash": before_hash},
            )
        after = before + content if mode == "append" else content
        after_hash = cls._hash_text(after, encoding=encoding)
        diff = cls._diff(before, after, path=WorkspaceFileService.source_ref(resolved, root_info))
        write_id = get_uuid()
        approval = cls._enforce_approval(
            task_type="workspace_file_write",
            task_id=task_id or cls._task_id("workspace_file_write", resolved, run_id),
            title=f"Write workspace file {WorkspaceFileService.source_ref(resolved, root_info)}",
            require_approval=require_approval,
            approval_id=approval_id,
            manual_approved=manual_approved,
            requester_id=requester_id or user_id or tenant_id,
            policy=policy,
            content={
                "path": WorkspaceFileService.source_ref(resolved, root_info),
                "mode": mode,
                "before_hash": before_hash,
                "after_hash": after_hash,
                "dry_run": bool(dry_run),
                "diff": diff,
            },
        ) if not dry_run else {"allowed": True, "approval": None, "assessment": None}
        audit = WorkspaceFileService.audit_record(
            "write_file_dry_run" if dry_run else "write_file",
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            path=str(resolved),
            allowed=True,
            reason=reason,
        )
        changed = (not exists) or before_hash != after_hash

        if not dry_run and changed:
            resolved.write_text(after, encoding=encoding or "utf-8")

        file_info = WorkspaceFileService.file_info(resolved, root_info) if resolved.exists() else cls._planned_file_info(resolved, root_info, after, encoding)
        record = {
            "schema_version": 1,
            "write_id": write_id,
            "operation": "workspace_file_write",
            "mode": mode,
            "root": root_info,
            "path": str(resolved),
            "relative_path": WorkspaceFileService.source_ref(resolved, root_info),
            "encoding": encoding or "utf-8",
            "dry_run": bool(dry_run),
            "changed": changed,
            "before_hash": before_hash,
            "after_hash": after_hash,
            "expected_hash": expected_hash or "",
            "bytes": len(after.encode(encoding or "utf-8", errors="replace")),
            "file": file_info,
            "diff": diff,
            "approval": approval.get("approval"),
            "audit": audit,
        }
        cls._records[write_id] = deepcopy(record)
        cls._audits[write_id] = [deepcopy(audit)]
        return deepcopy(record)

    @classmethod
    def get_write(cls, write_id: str) -> dict[str, Any]:
        if write_id not in cls._records:
            raise WorkspaceFileError("WRITE_NOT_FOUND", "Workspace write record not found.", {"write_id": write_id})
        return deepcopy(cls._records[write_id])

    @classmethod
    def list_audit(cls, write_id: str) -> list[dict[str, Any]]:
        if write_id not in cls._records:
            raise WorkspaceFileError("WRITE_NOT_FOUND", "Workspace write record not found.", {"write_id": write_id})
        return deepcopy(cls._audits.get(write_id, []))

    @classmethod
    def _enforce_approval(
        cls,
        *,
        task_type: str,
        task_id: str,
        title: str,
        require_approval: bool,
        approval_id: str = "",
        manual_approved: bool = False,
        requester_id: str = "",
        policy: dict[str, Any] | None = None,
        content: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if not require_approval:
            return {"allowed": True, "approval": None, "assessment": {"requires_confirmation": False}}
        if manual_approved:
            return {"allowed": True, "approval": {"status": "approved", "source": "manual_approve"}, "assessment": {"requires_confirmation": True}}
        task = {
            "task_id": task_id,
            "task_type": task_type,
            "title": title,
            "risk_level": "high",
            "requires_user_confirmation": True,
        }
        if approval_id:
            try:
                approval = AgentTaskApprovalService.get(approval_id)
            except AgentTaskApprovalError as exc:
                raise WorkspaceFileError(exc.code, str(exc), exc.details) from exc
            if approval.get("task_id") not in {"", task_id}:
                raise WorkspaceFileError("APPROVAL_TASK_MISMATCH", "Approval does not belong to this workspace action.", {"approval_id": approval_id, "task_id": task_id})
            if approval.get("status") == "approved":
                return {"allowed": True, "approval": approval, "assessment": approval.get("assessment")}
            raise WorkspaceFileError("APPROVAL_REQUIRED", "Workspace action requires approved manual review.", {"approval": approval})

        enforcement = AgentTaskApprovalService.enforce(task=task, policy=policy)
        if enforcement["allowed"]:
            return enforcement
        approval = enforcement.get("approval")
        if not approval:
            approval = AgentTaskApprovalService.request(
                task=task,
                requester_id=requester_id,
                policy=policy,
                content=content or {},
            )
        raise WorkspaceFileError(
            "APPROVAL_REQUIRED",
            "Workspace action requires approved manual review.",
            {"approval": approval, "assessment": enforcement.get("assessment")},
        )

    @staticmethod
    def _task_id(task_type: str, path: Path, run_id: str) -> str:
        source = f"{task_type}:{run_id}:{path}"
        return f"{task_type}:{hashlib.sha1(source.encode('utf-8')).hexdigest()[:16]}"

    @classmethod
    def _resolve_write_target(
        cls,
        *,
        path: str,
        root: str,
        roots: list[str | Path] | None,
    ) -> tuple[Path, dict[str, Any]]:
        raw = str(path or "").strip()
        if not raw:
            raise WorkspaceFileError("PATH_REQUIRED", "Workspace write path is required.")
        candidate = Path(raw).expanduser()
        if candidate.is_absolute():
            raise WorkspaceFileError("ABSOLUTE_PATH_DENIED", "Workspace writes require a relative path.", {"path": raw})
        if any(part == ".." for part in candidate.parts):
            raise WorkspaceFileError("PATH_TRAVERSAL_DENIED", "Workspace write path cannot contain '..'.", {"path": raw})
        resolved, root_info = WorkspaceFileService.resolve(path=raw, root=root, roots=roots, must_exist=False)
        root_path = Path(root_info["path"]).resolve()
        parent = resolved.parent.resolve(strict=False)
        if not WorkspaceFileService._is_relative_to(parent, root_path):
            raise WorkspaceFileError("PATH_OUTSIDE_ROOT", "Workspace write parent is outside configured roots.", {"path": raw})
        if not parent.exists():
            raise WorkspaceFileError("PARENT_NOT_FOUND", "Workspace write parent directory does not exist.", {"path": str(parent)})
        if not parent.is_dir():
            raise WorkspaceFileError("PARENT_NOT_DIRECTORY", "Workspace write parent is not a directory.", {"path": str(parent)})
        return resolved, root_info

    @classmethod
    def _check_size(cls, content: str, *, encoding: str, max_bytes: int | None) -> None:
        limit = WorkspaceFileService._limit(max_bytes, cls.DEFAULT_MAX_WRITE_BYTES)
        size = len(content.encode(encoding or "utf-8", errors="replace"))
        if size > limit:
            raise WorkspaceFileError("WRITE_TOO_LARGE", "Workspace write content exceeds max_bytes.", {"size": size, "max_bytes": limit})

    @staticmethod
    def _hash_text(text: str, encoding: str = "utf-8") -> str:
        return hashlib.sha256(text.encode(encoding or "utf-8", errors="replace")).hexdigest()

    @staticmethod
    def _diff(before: str, after: str, *, path: str) -> str:
        lines = difflib.unified_diff(
            before.splitlines(),
            after.splitlines(),
            fromfile=f"a/{path}",
            tofile=f"b/{path}",
            lineterm="",
        )
        return "\n".join(lines)

    @classmethod
    def _planned_file_info(cls, path: Path, root_info: dict[str, Any], content: str, encoding: str) -> dict[str, Any]:
        rel = str(path.relative_to(root_info["path"])) if WorkspaceFileService._is_relative_to(path, Path(root_info["path"])) else path.name
        return {
            "name": path.name,
            "path": str(path),
            "relative_path": rel,
            "root_id": root_info["root_id"],
            "type": "file",
            "size": len(content.encode(encoding or "utf-8", errors="replace")),
            "modified_at": 0,
            "mime_type": "",
            "extension": path.suffix.lower(),
            "sha256": cls._hash_text(content, encoding=encoding),
        }
