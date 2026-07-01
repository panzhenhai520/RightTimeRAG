#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from pathlib import Path
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_planner_service import TaskNodeFactory
from api.db.services.agent_task_state_service import AgentTaskStateService
from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService


SUPPORTED_PRECONDITIONS = {
    "required_input",
    "file_exists",
    "permission_allowed",
    "document_loaded",
    "schema_available",
    "user_confirmation_required",
    "upstream_task_completed",
    "conflict_resolved",
}


class PreconditionChecker:
    @classmethod
    def check(
        cls,
        task: dict[str, Any],
        *,
        runtime_context: dict[str, Any] | None = None,
        root: str = "",
        roots: list[str | Path] | None = None,
        mark_ready: bool = False,
    ) -> dict[str, Any]:
        runtime = runtime_context if isinstance(runtime_context, dict) else {}
        conditions = task.get("preconditions") if isinstance(task.get("preconditions"), list) else []
        results = [cls.evaluate(condition, task=task, runtime_context=runtime, root=root, roots=roots) for condition in conditions]
        repair_tasks = cls.repair_tasks_for_results(results, task=task)
        ok = all(item["satisfied"] for item in results)
        next_status = AgentTaskStatus.READY.value if ok else cls.next_status(results)
        transition = None
        task_id = str(task.get("task_id") or "")
        if ok and mark_ready and task_id:
            current = task.get("status")
            try:
                current = AgentTaskModelService.get_task(task_id)["status"]
            except Exception:
                pass
            if current == AgentTaskStatus.PENDING.value:
                transition = AgentTaskStateService.mark_ready(task_id, reason="preconditions satisfied")
        return {
            "schema_version": 1,
            "task_id": task_id,
            "ok": ok,
            "next_status": next_status,
            "condition_results": results,
            "repair_tasks": repair_tasks,
            "ready_transition": transition,
        }

    @classmethod
    def check_model_task(
        cls,
        task_id: str,
        *,
        runtime_context: dict[str, Any] | None = None,
        root: str = "",
        roots: list[str | Path] | None = None,
        mark_ready: bool = True,
    ) -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        return cls.check(task, runtime_context=runtime_context, root=root, roots=roots, mark_ready=mark_ready)

    @classmethod
    def evaluate(
        cls,
        condition: dict[str, Any],
        *,
        task: dict[str, Any],
        runtime_context: dict[str, Any],
        root: str = "",
        roots: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        kind = str(condition.get("kind") or "").strip()
        if kind not in SUPPORTED_PRECONDITIONS:
            return cls.result(condition, False, code="unsupported_precondition", message=f"Unsupported precondition: {kind}")
        if kind == "required_input":
            return cls.check_required_input(condition, task=task, runtime_context=runtime_context)
        if kind == "file_exists":
            return cls.check_file_exists(condition, task=task, runtime_context=runtime_context, root=root, roots=roots)
        if kind == "permission_allowed":
            return cls.check_permission_allowed(condition, task=task, runtime_context=runtime_context, root=root, roots=roots)
        if kind == "document_loaded":
            return cls.check_document_loaded(condition, task=task, runtime_context=runtime_context)
        if kind == "schema_available":
            return cls.check_schema_available(condition, task=task, runtime_context=runtime_context)
        if kind == "user_confirmation_required":
            return cls.check_user_confirmation(condition, task=task, runtime_context=runtime_context)
        if kind == "upstream_task_completed":
            return cls.check_upstream_completed(condition, task=task, runtime_context=runtime_context)
        if kind == "conflict_resolved":
            return cls.check_conflict_resolved(condition, task=task, runtime_context=runtime_context)
        return cls.result(condition, False, code="unsupported_precondition", message=f"Unsupported precondition: {kind}")

    @staticmethod
    def result(condition: dict[str, Any], satisfied: bool, *, code: str = "", message: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "kind": condition.get("kind", ""),
            "satisfied": bool(satisfied),
            "code": code or ("ok" if satisfied else "failed"),
            "message": message or ("Precondition satisfied." if satisfied else "Precondition failed."),
            "condition": deepcopy(condition),
            "details": deepcopy(details or {}),
        }

    @classmethod
    def check_required_input(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        field = str(condition.get("field") or condition.get("name") or "").strip()
        if not field:
            return cls.result(condition, False, code="missing_condition_field", message="Required input precondition has no field.")
        value = cls.lookup_value(field, task=task, runtime_context=runtime_context)
        if cls.has_value(value):
            return cls.result(condition, True, details={"field": field})
        return cls.result(condition, False, code="missing_required_input", message=f"Required input is missing: {field}", details={"field": field})

    @classmethod
    def check_file_exists(
        cls,
        condition: dict[str, Any],
        *,
        task: dict[str, Any],
        runtime_context: dict[str, Any],
        root: str = "",
        roots: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        path = cls.condition_path(condition, task=task, runtime_context=runtime_context)
        if not path:
            return cls.result(condition, False, code="missing_file_path", message="File path is missing.")
        try:
            resolved, _ = WorkspaceFileService.resolve(path=str(path), root=root, roots=roots, must_exist=True)
            if not resolved.is_file():
                return cls.result(condition, False, code="not_a_file", message="Path exists but is not a file.", details={"path": str(resolved)})
            return cls.result(condition, True, details={"path": str(resolved)})
        except WorkspaceFileError as exc:
            return cls.result(condition, False, code=exc.code.lower(), message=str(exc), details=exc.details)

    @classmethod
    def check_permission_allowed(
        cls,
        condition: dict[str, Any],
        *,
        task: dict[str, Any],
        runtime_context: dict[str, Any],
        root: str = "",
        roots: list[str | Path] | None = None,
    ) -> dict[str, Any]:
        path = cls.condition_path(condition, task=task, runtime_context=runtime_context) or "."
        try:
            resolved, _ = WorkspaceFileService.resolve(path=str(path), root=root, roots=roots, must_exist=False)
            return cls.result(condition, True, details={"path": str(resolved)})
        except WorkspaceFileError as exc:
            return cls.result(condition, False, code="permission_denied", message=str(exc), details=exc.details)

    @classmethod
    def check_document_loaded(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        field = str(condition.get("field") or "document").strip()
        value = cls.lookup_value(field, task=task, runtime_context=runtime_context)
        if isinstance(value, dict) and (value.get("document_id") or value.get("lines") or value.get("chunks")):
            return cls.result(condition, True, details={"field": field})
        if cls.has_value(value) and condition.get("allow_any"):
            return cls.result(condition, True, details={"field": field})
        return cls.result(condition, False, code="document_not_loaded", message="Document has not been loaded.", details={"field": field})

    @classmethod
    def check_schema_available(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        schema_name = str(condition.get("schema") or condition.get("name") or "").strip()
        schemas = runtime_context.get("schemas") if isinstance(runtime_context.get("schemas"), dict) else {}
        if schema_name and schema_name in schemas:
            return cls.result(condition, True, details={"schema": schema_name})
        if schema_name and schema_name in (task.get("inputs") or {}):
            return cls.result(condition, True, details={"schema": schema_name})
        return cls.result(condition, False, code="schema_missing", message=f"Schema is missing: {schema_name}", details={"schema": schema_name})

    @classmethod
    def check_user_confirmation(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        if not condition.get("required", True):
            return cls.result(condition, True)
        approved = bool(runtime_context.get("user_confirmed") or runtime_context.get("approved") or task.get("inputs", {}).get("user_confirmed"))
        if approved:
            return cls.result(condition, True, details={"user_confirmed": True})
        return cls.result(condition, False, code="user_confirmation_required", message="User confirmation is required before this task can proceed.")

    @classmethod
    def check_upstream_completed(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        upstream_id = str(condition.get("task_id") or condition.get("upstream_task_id") or "").strip()
        if not upstream_id:
            return cls.result(condition, False, code="missing_upstream_task_id", message="Upstream task id is missing.")
        status = None
        upstream_statuses = runtime_context.get("upstream_statuses") if isinstance(runtime_context.get("upstream_statuses"), dict) else {}
        if upstream_id in upstream_statuses:
            status = upstream_statuses[upstream_id]
        else:
            try:
                status = AgentTaskModelService.get_task(upstream_id)["status"]
            except AgentTaskError:
                status = None
        if status in {AgentTaskStatus.COMPLETED.value, AgentTaskStatus.VERIFIED.value}:
            return cls.result(condition, True, details={"upstream_task_id": upstream_id, "status": status})
        return cls.result(
            condition,
            False,
            code="upstream_not_completed",
            message="Upstream task has not completed.",
            details={"upstream_task_id": upstream_id, "status": status},
        )

    @classmethod
    def check_conflict_resolved(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        if bool(runtime_context.get("conflict_resolved") or task.get("inputs", {}).get("conflict_resolved")):
            return cls.result(condition, True)
        unresolved = runtime_context.get("unresolved_conflicts") or task.get("inputs", {}).get("unresolved_conflicts") or []
        if isinstance(unresolved, list) and not unresolved:
            return cls.result(condition, True)
        return cls.result(condition, False, code="conflict_unresolved", message="Conflict must be resolved first.", details={"unresolved_conflicts": unresolved})

    @staticmethod
    def lookup_value(field: str, *, task: dict[str, Any], runtime_context: dict[str, Any]) -> Any:
        if field in runtime_context:
            return runtime_context[field]
        inputs = task.get("inputs") if isinstance(task.get("inputs"), dict) else {}
        if field in inputs:
            return inputs[field]
        if "." in field:
            value: Any = {"task": task, "runtime": runtime_context}
            for part in field.split("."):
                if isinstance(value, dict):
                    value = value.get(part)
                else:
                    return None
            return value
        return None

    @classmethod
    def condition_path(cls, condition: dict[str, Any], *, task: dict[str, Any], runtime_context: dict[str, Any]) -> Any:
        if condition.get("path"):
            return condition.get("path")
        field = str(condition.get("field") or "path")
        return cls.lookup_value(field, task=task, runtime_context=runtime_context)

    @staticmethod
    def has_value(value: Any) -> bool:
        if value is None:
            return False
        if isinstance(value, str):
            return bool(value.strip())
        if isinstance(value, (list, tuple, set, dict)):
            return bool(value)
        return True

    @classmethod
    def repair_tasks_for_results(cls, results: list[dict[str, Any]], *, task: dict[str, Any]) -> list[dict[str, Any]]:
        repairs = []
        for result in results:
            if result.get("satisfied"):
                continue
            repair = cls.repair_task_for_result(result, task=task, index=len(repairs) + 1)
            if repair:
                repairs.append(repair)
        return repairs

    @classmethod
    def repair_task_for_result(cls, result: dict[str, Any], *, task: dict[str, Any], index: int) -> dict[str, Any] | None:
        code = result.get("code")
        node_id = f"repair-{index:03d}"
        parent_id = str(task.get("node_id") or task.get("task_id") or "")
        if code in {"missing_required_input", "missing_file_path", "path_not_found"}:
            field = result.get("details", {}).get("field", "target_document")
            task_type = "find_file" if field in {"target_document", "selected_file", "file", "path", "document_a", "document_b"} else "request_user_input"
            return cls.make_repair(node_id, parent_id, task_type, f"Repair missing {field}", {"missing_field": field})
        if code == "document_not_loaded":
            return cls.make_repair(node_id, parent_id, "read_document", "Repair unloaded document", {"source_task": parent_id})
        if code == "schema_missing":
            return cls.make_repair(node_id, parent_id, "provide_schema", "Repair missing schema", result.get("details", {}))
        if code == "user_confirmation_required":
            return cls.make_repair(node_id, parent_id, "request_user_confirmation", "Request user confirmation", {"source_task": parent_id}, risk_level="high")
        if code == "upstream_not_completed":
            return cls.make_repair(node_id, parent_id, "wait_for_upstream", "Wait for upstream task", result.get("details", {}))
        if code == "permission_denied":
            return cls.make_repair(node_id, parent_id, "request_permission", "Request workspace permission", result.get("details", {}), risk_level="medium")
        if code == "conflict_unresolved":
            return cls.make_repair(node_id, parent_id, "resolve_conflict", "Resolve blocking conflict", result.get("details", {}), risk_level="medium")
        return None

    @staticmethod
    def make_repair(node_id: str, parent_id: str, task_type: str, title: str, inputs: dict[str, Any], *, risk_level: str = "low") -> dict[str, Any]:
        return TaskNodeFactory.make_node(
            node_id=node_id,
            parent_id=parent_id,
            task_type=task_type,
            title=title,
            inputs=inputs,
            outputs={"repair_result": "JSON"},
            preconditions=[],
            completion_criteria=[{"kind": "repair_result_available"}],
            risk_level=risk_level,
            tool_hint=PreconditionChecker.repair_tool_hint(task_type),
            evidence_requirement=[{"kind": "repair_reason", "required": True}],
            metadata={"repair_task": True},
        )

    @staticmethod
    def repair_tool_hint(task_type: str) -> str:
        return {
            "find_file": "RelevantFileResolver",
            "read_document": "DocumentNormalizer",
            "provide_schema": "ManualInput",
            "request_user_confirmation": "ManualApprove",
            "wait_for_upstream": "TaskStateWatcher",
            "request_permission": "ManualApprove",
            "resolve_conflict": "ConflictResolver",
            "request_user_input": "UserFillUp",
        }.get(task_type, "Agent")

    @staticmethod
    def next_status(results: list[dict[str, Any]]) -> str:
        if any(item.get("code") in {"missing_required_input", "user_confirmation_required"} for item in results if not item.get("satisfied")):
            return AgentTaskStatus.WAITING_INPUT.value
        return AgentTaskStatus.BLOCKED.value


class DependencyResolver:
    @classmethod
    def resolve(
        cls,
        task: dict[str, Any],
        *,
        tasks: list[dict[str, Any]] | None = None,
        runtime_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        known_tasks = {str(item.get("task_id") or item.get("node_id")): item for item in (tasks or []) if isinstance(item, dict)}
        dependency_ids = cls.dependency_ids(task)
        dependencies = []
        blocked_by = []
        missing = []
        for dep_id in dependency_ids:
            upstream = known_tasks.get(dep_id)
            if upstream is None:
                try:
                    upstream = AgentTaskModelService.get_task(dep_id)
                except AgentTaskError:
                    upstream = None
            if upstream is None:
                missing.append(dep_id)
                blocked_by.append({"task_id": dep_id, "reason": "missing_dependency"})
                continue
            status = upstream.get("status", "")
            item = {"task_id": dep_id, "status": status, "task_type": upstream.get("task_type", "")}
            dependencies.append(item)
            if status not in {AgentTaskStatus.COMPLETED.value, AgentTaskStatus.VERIFIED.value}:
                blocked_by.append({"task_id": dep_id, "status": status, "reason": "upstream_not_completed"})
        repair_tasks = [
            PreconditionChecker.make_repair(
                f"repair-{index:03d}",
                str(task.get("node_id") or task.get("task_id") or ""),
                "wait_for_upstream" if item.get("reason") == "upstream_not_completed" else "request_user_input",
                "Repair dependency",
                item,
            )
            for index, item in enumerate(blocked_by, start=1)
        ]
        return {
            "schema_version": 1,
            "task_id": str(task.get("task_id") or task.get("node_id") or ""),
            "ok": not blocked_by and not missing,
            "dependencies": dependencies,
            "blocked_by": blocked_by,
            "missing_dependencies": missing,
            "repair_tasks": repair_tasks,
            "runtime_context": deepcopy(runtime_context or {}),
        }

    @staticmethod
    def dependency_ids(task: dict[str, Any]) -> list[str]:
        ids = []
        for dep_id in task.get("depends_on") or []:
            text = str(dep_id or "").strip()
            if text and text not in ids:
                ids.append(text)
        for condition in task.get("preconditions") or []:
            if condition.get("kind") == "upstream_task_completed":
                text = str(condition.get("task_id") or condition.get("upstream_task_id") or "").strip()
                if text and text not in ids:
                    ids.append(text)
        return ids
