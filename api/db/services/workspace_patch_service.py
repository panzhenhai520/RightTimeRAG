#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import difflib
import json
from copy import deepcopy
from pathlib import Path
from typing import Any

from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from api.db.services.workspace_file_write_service import WorkspaceFileWriteService
from common.misc_utils import get_uuid


class WorkspacePatchService:
    """Dry-run and apply controlled workspace patches."""

    FORMATS = {"structured", "unified_diff"}
    DEFAULT_MAX_FILES = 20
    DEFAULT_MAX_CHANGED_LINES = 2000
    _records: dict[str, dict[str, Any]] = {}
    _audits: dict[str, list[dict[str, Any]]] = {}
    _rollbacks: dict[str, dict[str, Any]] = {}

    @classmethod
    def reset(cls) -> None:
        cls._records = {}
        cls._audits = {}
        cls._rollbacks = {}

    @classmethod
    def dry_run(
        cls,
        *,
        patch: dict[str, Any] | list[Any] | str,
        patch_format: str = "structured",
        root: str = "",
        roots: list[str | Path] | None = None,
        expected_hashes: dict[str, str] | None = None,
        encoding: str = "utf-8",
        max_files: int | None = None,
        max_changed_lines: int | None = None,
        tenant_id: str = "",
        user_id: str = "",
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        return cls._build_result(
            patch=patch,
            patch_format=patch_format,
            root=root,
            roots=roots,
            expected_hashes=expected_hashes,
            encoding=encoding,
            max_files=max_files,
            max_changed_lines=max_changed_lines,
            dry_run=True,
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            reason=reason,
        )

    @classmethod
    def apply(
        cls,
        *,
        patch: dict[str, Any] | list[Any] | str,
        patch_format: str = "structured",
        root: str = "",
        roots: list[str | Path] | None = None,
        expected_hashes: dict[str, str] | None = None,
        encoding: str = "utf-8",
        require_approval: bool = True,
        approval_id: str = "",
        manual_approved: bool = False,
        task_id: str = "",
        requester_id: str = "",
        policy: dict[str, Any] | None = None,
        max_files: int | None = None,
        max_changed_lines: int | None = None,
        tenant_id: str = "",
        user_id: str = "",
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        result = cls._build_result(
            patch=patch,
            patch_format=patch_format,
            root=root,
            roots=roots,
            expected_hashes=expected_hashes,
            encoding=encoding,
            max_files=max_files,
            max_changed_lines=max_changed_lines,
            dry_run=False,
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            reason=reason,
        )
        if result["conflicts"]:
            raise WorkspaceFileError("PATCH_CONFLICT", "Workspace patch contains conflicts.", {"conflicts": result["conflicts"]})

        approval = WorkspaceFileWriteService._enforce_approval(
            task_type="workspace_patch_apply",
            task_id=task_id or WorkspaceFileWriteService._task_id("workspace_patch_apply", Path(result["affected_files"][0]["path"]), run_id),
            title="Apply workspace patch",
            require_approval=require_approval,
            approval_id=approval_id,
            manual_approved=manual_approved,
            requester_id=requester_id or user_id or tenant_id,
            policy=policy,
            content={
                "affected_files": result["affected_files"],
                "changed_lines": result["changed_lines"],
                "diff": result["diff"],
            },
        )

        rollback_token = get_uuid()
        written: list[dict[str, Any]] = []
        try:
            for item in result["_planned_files"]:
                item["resolved"].write_text(item["after"], encoding=encoding or "utf-8")
                written.append(item)
        except Exception as exc:
            for item in reversed(written):
                item["resolved"].write_text(item["before"], encoding=encoding or "utf-8")
            raise WorkspaceFileError("PATCH_APPLY_FAILED", "Workspace patch failed and written files were restored.") from exc

        cls._rollbacks[rollback_token] = {
            "rollback_token": rollback_token,
            "patch_id": result["patch_id"],
            "files": [
                {
                    "relative_path": item["relative_path"],
                    "root_id": item["root"]["root_id"],
                    "root_path": item["root"]["path"],
                    "before": item["before"],
                    "before_hash": item["before_hash"],
                    "applied_hash": item["after_hash"],
                    "encoding": encoding or "utf-8",
                }
                for item in result["_planned_files"]
            ],
        }
        result["rollback_token"] = rollback_token
        result["approval"] = approval.get("approval")
        result.pop("_planned_files", None)
        cls._records[result["patch_id"]] = deepcopy(result)
        cls._audits[result["patch_id"]] = [deepcopy(result["audit"])]
        return deepcopy(result)

    @classmethod
    def rollback(
        cls,
        *,
        rollback_token: str,
        root: str = "",
        roots: list[str | Path] | None = None,
        tenant_id: str = "",
        user_id: str = "",
        run_id: str = "",
        reason: str = "",
    ) -> dict[str, Any]:
        if rollback_token not in cls._rollbacks:
            raise WorkspaceFileError("ROLLBACK_NOT_FOUND", "Workspace rollback token not found.", {"rollback_token": rollback_token})
        payload = deepcopy(cls._rollbacks[rollback_token])
        restored = []
        for item in payload["files"]:
            resolved, root_info = WorkspaceFileService.resolve(
                path=item["relative_path"],
                root=root or item["root_id"] or item["root_path"],
                roots=roots,
                must_exist=True,
            )
            WorkspaceFileService._require_file(resolved)
            current_hash = WorkspaceFileService._sha256(resolved)
            if current_hash != item["applied_hash"]:
                raise WorkspaceFileError(
                    "ROLLBACK_HASH_MISMATCH",
                    "Workspace file changed after patch apply; rollback refused.",
                    {"path": str(resolved), "expected_hash": item["applied_hash"], "actual_hash": current_hash},
                )
            resolved.write_text(item["before"], encoding=item.get("encoding") or "utf-8")
            restored.append(WorkspaceFileService.file_info(resolved, root_info))
        audit = WorkspaceFileService.audit_record(
            "patch_rollback",
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            path=",".join(item["relative_path"] for item in payload["files"]),
            allowed=True,
            reason=reason,
        )
        cls._audits.setdefault(payload["patch_id"], []).append(deepcopy(audit))
        return {
            "schema_version": 1,
            "rollback_token": rollback_token,
            "patch_id": payload["patch_id"],
            "restored_files": restored,
            "audit": audit,
        }

    @classmethod
    def get_patch(cls, patch_id: str) -> dict[str, Any]:
        if patch_id not in cls._records:
            raise WorkspaceFileError("PATCH_NOT_FOUND", "Workspace patch record not found.", {"patch_id": patch_id})
        return deepcopy(cls._records[patch_id])

    @classmethod
    def list_audit(cls, patch_id: str) -> list[dict[str, Any]]:
        if patch_id not in cls._records:
            raise WorkspaceFileError("PATCH_NOT_FOUND", "Workspace patch record not found.", {"patch_id": patch_id})
        return deepcopy(cls._audits.get(patch_id, []))

    @classmethod
    def _build_result(
        cls,
        *,
        patch: dict[str, Any] | list[Any] | str,
        patch_format: str,
        root: str,
        roots: list[str | Path] | None,
        expected_hashes: dict[str, str] | None,
        encoding: str,
        max_files: int | None,
        max_changed_lines: int | None,
        dry_run: bool,
        tenant_id: str,
        user_id: str,
        run_id: str,
        reason: str,
    ) -> dict[str, Any]:
        patch_format = str(patch_format or "structured").strip().lower()
        if patch_format not in cls.FORMATS:
            raise WorkspaceFileError("INVALID_PATCH_FORMAT", "Unsupported workspace patch format.", {"patch_format": patch_format})

        file_specs = cls._parse_patch(patch, patch_format)
        cls._check_file_limit(file_specs, max_files=max_files)
        planned_files = []
        conflicts = []
        expected_hashes = expected_hashes or {}
        for spec in file_specs:
            path = str(spec.get("path") or "").strip()
            try:
                resolved, root_info = WorkspaceFileWriteService._resolve_write_target(path=path, root=root, roots=roots)
                if not resolved.exists():
                    raise WorkspaceFileError("PATH_NOT_FOUND", "Workspace patch file does not exist.", {"path": str(resolved)})
                WorkspaceFileService._require_file(resolved)
                before = resolved.read_text(encoding=encoding or "utf-8", errors="replace")
                before_hash = WorkspaceFileService._sha256(resolved)
                expected_hash = str(spec.get("expected_hash") or expected_hashes.get(path) or "")
                if expected_hash and before_hash != expected_hash:
                    raise WorkspaceFileError(
                        "HASH_MISMATCH",
                        "Workspace file hash does not match expected_hash.",
                        {"path": str(resolved), "expected_hash": expected_hash, "actual_hash": before_hash},
                    )
                after, item_conflicts = cls._apply_file_spec(before, spec)
                conflicts.extend({"path": path, **item} for item in item_conflicts)
                after_hash = WorkspaceFileWriteService._hash_text(after, encoding=encoding)
                relative_path = WorkspaceFileService.source_ref(resolved, root_info)
                planned_files.append(
                    {
                        "path": str(resolved),
                        "relative_path": relative_path,
                        "root": root_info,
                        "resolved": resolved,
                        "before": before,
                        "after": after,
                        "before_hash": before_hash,
                        "after_hash": after_hash,
                        "changed": before_hash != after_hash,
                        "diff": cls._diff(before, after, path=relative_path),
                    }
                )
            except WorkspaceFileError as exc:
                conflicts.append({"path": path, "error_code": exc.code, "message": str(exc), "details": exc.details})

        changed_lines = sum(cls._changed_line_count(item["diff"]) for item in planned_files)
        changed_limit = cls._positive_limit(max_changed_lines, cls.DEFAULT_MAX_CHANGED_LINES)
        if changed_lines > changed_limit:
            conflicts.append(
                {
                    "path": "",
                    "error_code": "PATCH_TOO_LARGE",
                    "message": "Workspace patch changed line count exceeds max_changed_lines.",
                    "details": {"changed_lines": changed_lines, "max_changed_lines": changed_limit},
                }
            )
        patch_id = get_uuid()
        audit = WorkspaceFileService.audit_record(
            "patch_dry_run" if dry_run else "patch_apply",
            tenant_id=tenant_id,
            user_id=user_id,
            run_id=run_id,
            path=",".join(item["relative_path"] for item in planned_files),
            allowed=not conflicts,
            reason=reason,
        )
        result = {
            "schema_version": 1,
            "patch_id": patch_id,
            "operation": "workspace_patch_apply",
            "patch_format": patch_format,
            "dry_run": bool(dry_run),
            "can_apply": not conflicts,
            "changed": any(item["changed"] for item in planned_files),
            "changed_lines": changed_lines,
            "affected_files": [
                {
                    "path": item["path"],
                    "relative_path": item["relative_path"],
                    "root_id": item["root"]["root_id"],
                    "before_hash": item["before_hash"],
                    "after_hash": item["after_hash"],
                    "changed": item["changed"],
                }
                for item in planned_files
            ],
            "diff": "\n".join(item["diff"] for item in planned_files if item["diff"]),
            "conflicts": conflicts,
            "rollback_token": "",
            "audit": audit,
            "_planned_files": planned_files,
        }
        if dry_run:
            public_result = deepcopy(result)
            public_result.pop("_planned_files", None)
            cls._records[patch_id] = deepcopy(public_result)
            cls._audits[patch_id] = [deepcopy(audit)]
            return public_result
        return result

    @classmethod
    def _parse_patch(cls, patch: dict[str, Any] | list[Any] | str, patch_format: str) -> list[dict[str, Any]]:
        if patch_format == "unified_diff":
            return cls._parse_unified_diff(str(patch or ""))
        if isinstance(patch, str):
            try:
                patch = json.loads(patch)
            except json.JSONDecodeError as exc:
                raise WorkspaceFileError("INVALID_PATCH", "Structured patch string must be valid JSON.") from exc
        if isinstance(patch, dict):
            files = patch.get("files", [])
        elif isinstance(patch, list):
            files = patch
        else:
            files = []
        if not files:
            raise WorkspaceFileError("EMPTY_PATCH", "Workspace patch does not contain any file operations.")
        return [dict(item) for item in files if isinstance(item, dict)]

    @classmethod
    def _parse_unified_diff(cls, diff_text: str) -> list[dict[str, Any]]:
        files = []
        current: dict[str, Any] | None = None
        current_hunk: list[str] | None = None
        for line in diff_text.splitlines():
            if line.startswith("+++ "):
                path = cls._strip_diff_path(line[4:].strip())
                current = {"path": path, "operations": [{"op": "unified_hunks", "hunks": []}]}
                current_hunk = None
                files.append(current)
                continue
            if current is None:
                continue
            if line.startswith("@@"):
                current_hunk = []
                current["operations"][0]["hunks"].append(current_hunk)
                continue
            if current_hunk is not None and line[:1] in {" ", "+", "-"}:
                current_hunk.append(line)
        if not files:
            raise WorkspaceFileError("EMPTY_PATCH", "Unified diff does not contain any target files.")
        return files

    @staticmethod
    def _strip_diff_path(path: str) -> str:
        if path in {"/dev/null", "dev/null"}:
            raise WorkspaceFileError("UNSUPPORTED_PATCH", "Creating or deleting files via unified diff is not supported.")
        if path.startswith("a/") or path.startswith("b/"):
            return path[2:]
        return path

    @classmethod
    def _apply_file_spec(cls, before: str, spec: dict[str, Any]) -> tuple[str, list[dict[str, Any]]]:
        text = before
        conflicts = []
        operations = spec.get("operations") or spec.get("ops") or []
        if not operations:
            conflicts.append({"error_code": "EMPTY_OPERATIONS", "message": "Patch file has no operations.", "details": {}})
            return text, conflicts
        for index, operation in enumerate(operations):
            op = str(operation.get("op") or operation.get("type") or "").strip().lower()
            if op == "append":
                text += str(operation.get("content") or "")
            elif op == "prepend":
                text = str(operation.get("content") or "") + text
            elif op == "replace":
                old = str(operation.get("old") if operation.get("old") is not None else operation.get("text") or "")
                new = str(operation.get("new") if operation.get("new") is not None else operation.get("content") or "")
                text, conflict = cls._replace_text(text, old=old, new=new, operation_index=index, op=op)
                if conflict:
                    conflicts.append(conflict)
            elif op in {"insert_after", "insert_before"}:
                anchor = str(operation.get("anchor") or "")
                content = str(operation.get("content") or "")
                if not anchor or anchor not in text:
                    conflicts.append({"operation_index": index, "error_code": "ANCHOR_NOT_FOUND", "message": "Patch anchor was not found.", "details": {"anchor": anchor}})
                    continue
                text = text.replace(anchor, f"{anchor}{content}" if op == "insert_after" else f"{content}{anchor}", 1)
            elif op == "delete":
                old = str(operation.get("old") if operation.get("old") is not None else operation.get("text") or "")
                text, conflict = cls._replace_text(text, old=old, new="", operation_index=index, op=op)
                if conflict:
                    conflicts.append(conflict)
            elif op == "unified_hunks":
                text, item_conflicts = cls._apply_unified_hunks(text, operation.get("hunks") or [])
                conflicts.extend(item_conflicts)
            else:
                conflicts.append({"operation_index": index, "error_code": "UNSUPPORTED_OPERATION", "message": "Unsupported patch operation.", "details": {"op": op}})
        return text, conflicts

    @staticmethod
    def _replace_text(text: str, *, old: str, new: str, operation_index: int, op: str) -> tuple[str, dict[str, Any] | None]:
        if not old or old not in text:
            return text, {"operation_index": operation_index, "error_code": "TEXT_NOT_FOUND", "message": "Patch text was not found.", "details": {"op": op}}
        return text.replace(old, new, 1), None

    @classmethod
    def _apply_unified_hunks(cls, before: str, hunks: list[list[str]]) -> tuple[str, list[dict[str, Any]]]:
        lines = before.splitlines()
        conflicts = []
        for hunk_index, hunk in enumerate(hunks):
            old_block = [line[1:] for line in hunk if line.startswith((" ", "-"))]
            new_block = [line[1:] for line in hunk if line.startswith((" ", "+"))]
            start = cls._find_block(lines, old_block)
            if start < 0:
                conflicts.append({"operation_index": hunk_index, "error_code": "HUNK_NOT_FOUND", "message": "Unified diff hunk context was not found.", "details": {}})
                continue
            lines = lines[:start] + new_block + lines[start + len(old_block) :]
        suffix = "\n" if before.endswith("\n") else ""
        return "\n".join(lines) + suffix, conflicts

    @staticmethod
    def _find_block(lines: list[str], block: list[str]) -> int:
        if not block:
            return -1
        for index in range(0, len(lines) - len(block) + 1):
            if lines[index : index + len(block)] == block:
                return index
        return -1

    @staticmethod
    def _diff(before: str, after: str, *, path: str) -> str:
        return "\n".join(
            difflib.unified_diff(
                before.splitlines(),
                after.splitlines(),
                fromfile=f"a/{path}",
                tofile=f"b/{path}",
                lineterm="",
            )
        )

    @staticmethod
    def _changed_line_count(diff: str) -> int:
        return sum(1 for line in diff.splitlines() if line.startswith(("+", "-")) and not line.startswith(("+++", "---")))

    @classmethod
    def _check_file_limit(cls, file_specs: list[dict[str, Any]], *, max_files: int | None) -> None:
        limit = cls._positive_limit(max_files, cls.DEFAULT_MAX_FILES)
        if len(file_specs) > limit:
            raise WorkspaceFileError("PATCH_TOO_MANY_FILES", "Workspace patch affects too many files.", {"count": len(file_specs), "max_files": limit})

    @staticmethod
    def _positive_limit(value: int | None, default: int) -> int:
        try:
            return max(1, min(int(value or default), default))
        except Exception:
            return default
