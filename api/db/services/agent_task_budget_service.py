#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import json
import time
from copy import deepcopy
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_state_service import AgentTaskStateService


DEFAULT_TASK_BUDGET = {
    "max_plan_depth": 4,
    "max_child_tasks": 20,
    "max_replan_count": 3,
    "max_retry_per_task": 2,
    "max_execution_seconds": 60,
    "max_context_bytes": 512 * 1024,
}


class AgentTaskBudgetService:
    @classmethod
    def resolve_config(cls, config: dict[str, Any] | None = None) -> dict[str, int]:
        merged = {**DEFAULT_TASK_BUDGET, **(config or {})}
        return {key: max(1, int(value or DEFAULT_TASK_BUDGET[key])) for key, value in merged.items() if key in DEFAULT_TASK_BUDGET}

    @classmethod
    def check_plan_budget(cls, plan: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = cls.resolve_config(config)
        validation = plan.get("validation") if isinstance(plan.get("validation"), dict) else {}
        depth = int(validation.get("max_depth") or cls.max_depth(plan.get("tasks") or []))
        root_children = len([task for task in plan.get("tasks", []) if task.get("parent_id") == "root"])
        issues = []
        if depth > cfg["max_plan_depth"]:
            issues.append({"code": "max_plan_depth_exceeded", "value": depth, "limit": cfg["max_plan_depth"]})
        if root_children > cfg["max_child_tasks"]:
            issues.append({"code": "max_child_tasks_exceeded", "value": root_children, "limit": cfg["max_child_tasks"]})
        return cls.result("plan_budget", not issues, issues, cfg)

    @classmethod
    def check_context_budget(cls, context_bundle: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = cls.resolve_config(config)
        size = len(json.dumps(context_bundle or {}, ensure_ascii=False, default=str).encode("utf-8"))
        issues = []
        if size > cfg["max_context_bytes"]:
            issues.append({"code": "max_context_bytes_exceeded", "value": size, "limit": cfg["max_context_bytes"]})
        return cls.result("context_budget", not issues, issues, cfg, details={"context_bytes": size})

    @classmethod
    def check_retry_budget(cls, task: dict[str, Any], *, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = cls.resolve_config(config)
        retry_count = int((task.get("metadata") or {}).get("execution", {}).get("retry_count") or 0)
        issues = []
        if retry_count > cfg["max_retry_per_task"]:
            issues.append({"code": "max_retry_per_task_exceeded", "value": retry_count, "limit": cfg["max_retry_per_task"]})
        return cls.result("retry_budget", not issues, issues, cfg, details={"retry_count": retry_count})

    @classmethod
    def check_execution_time(cls, *, started_at: float, config: dict[str, Any] | None = None) -> dict[str, Any]:
        cfg = cls.resolve_config(config)
        elapsed = max(0.0, time.time() - float(started_at or time.time()))
        issues = []
        if elapsed > cfg["max_execution_seconds"]:
            issues.append({"code": "max_execution_seconds_exceeded", "value": round(elapsed, 4), "limit": cfg["max_execution_seconds"]})
        return cls.result("execution_time_budget", not issues, issues, cfg, details={"elapsed_seconds": round(elapsed, 4)})

    @classmethod
    def block_task_if_needed(
        cls,
        task_id: str,
        check_result: dict[str, Any],
        *,
        recovery_suggestion: str = "",
    ) -> dict[str, Any]:
        if check_result.get("ok"):
            return {"blocked": False, "task_id": task_id, "check": check_result}
        task = AgentTaskModelService.get_task(task_id)
        metadata = deepcopy(task.get("metadata") or {})
        metadata.setdefault("budget_blocks", []).append(
            {
                "check": check_result.get("check"),
                "issues": check_result.get("issues", []),
                "recovery_suggestion": recovery_suggestion,
                "created_at": AgentTaskModelService.now(),
            }
        )
        AgentTaskModelService.update_task(task_id, metadata=metadata)
        if task["status"] != AgentTaskStatus.BLOCKED.value:
            AgentTaskStateService.transition(task_id, AgentTaskStatus.BLOCKED.value, reason="budget exceeded")
        AgentTaskModelService.record_audit(
            goal_id=task["goal_id"],
            task_id=task_id,
            action="task_budget_blocked",
            after={"check": check_result, "recovery_suggestion": recovery_suggestion},
        )
        return {"blocked": True, "task_id": task_id, "check": check_result, "recovery_suggestion": recovery_suggestion}

    @staticmethod
    def result(check: str, ok: bool, issues: list[dict[str, Any]], config: dict[str, Any], details: dict[str, Any] | None = None) -> dict[str, Any]:
        return {"schema_version": 1, "check": check, "ok": ok, "issues": issues, "config": config, "details": details or {}}

    @staticmethod
    def max_depth(tasks: list[dict[str, Any]]) -> int:
        by_parent: dict[str, list[dict[str, Any]]] = {}
        roots = []
        for task in tasks:
            parent_id = task.get("parent_id") or ""
            if not parent_id:
                roots.append(task)
            by_parent.setdefault(parent_id, []).append(task)

        def depth(task: dict[str, Any], current: int) -> int:
            children = by_parent.get(task.get("node_id"), [])
            if not children:
                return current
            return max(depth(child, current + 1) for child in children)

        return max((depth(root, 1) for root in roots), default=0)


class AgentTaskLoopGuard:
    _events: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls._events = []

    @classmethod
    def record_plan(cls, *, goal_id: str, tasks: list[dict[str, Any]], config: dict[str, Any] | None = None) -> dict[str, Any]:
        signature = cls.plan_signature(tasks)
        return cls.record_event(
            goal_id=goal_id,
            event_type="plan_generated",
            signature=signature,
            config=config,
            failure_strategy="mark_blocked",
        )

    @classmethod
    def record_precondition_failure(
        cls,
        *,
        goal_id: str,
        task_id: str,
        condition_result: dict[str, Any],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        signature = f"{task_id}:{condition_result.get('kind')}:{condition_result.get('code')}"
        return cls.record_event(
            goal_id=goal_id,
            task_id=task_id,
            event_type="precondition_failed",
            signature=signature,
            config=config,
            failure_strategy="ask_user",
        )

    @classmethod
    def record_verifier_failure(
        cls,
        *,
        goal_id: str,
        task_id: str,
        failed_checks: list[dict[str, Any]],
        config: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        codes = ",".join(sorted(str(item.get("code") or item.get("check") or "") for item in failed_checks))
        signature = f"{task_id}:{codes}"
        return cls.record_event(
            goal_id=goal_id,
            task_id=task_id,
            event_type="verifier_failed",
            signature=signature,
            config=config,
            failure_strategy="split_task_further",
        )

    @classmethod
    def record_event(
        cls,
        *,
        goal_id: str,
        event_type: str,
        signature: str,
        task_id: str = "",
        config: dict[str, Any] | None = None,
        failure_strategy: str = "mark_blocked",
    ) -> dict[str, Any]:
        cfg = AgentTaskBudgetService.resolve_config(config)
        event = {
            "event_id": AgentTaskModelService.new_id("loop"),
            "goal_id": goal_id,
            "task_id": task_id,
            "event_type": event_type,
            "signature": signature,
            "created_at": AgentTaskModelService.now(),
        }
        cls._events.append(event)
        count = len([item for item in cls._events if item["goal_id"] == goal_id and item["event_type"] == event_type and item["signature"] == signature])
        loop_detected = count > cfg["max_replan_count"]
        result = {
            "schema_version": 1,
            "loop_detected": loop_detected,
            "event": event,
            "repeat_count": count,
            "limit": cfg["max_replan_count"],
            "failure_strategy": failure_strategy if loop_detected else "",
            "recovery_suggestion": cls.recovery_suggestion(failure_strategy) if loop_detected else "",
        }
        AgentTaskModelService.record_audit(
            goal_id=goal_id,
            task_id=task_id,
            action="task_loop_guard_event",
            after=result,
        )
        return result

    @staticmethod
    def plan_signature(tasks: list[dict[str, Any]]) -> str:
        parts = []
        for task in tasks:
            parts.append(
                ":".join(
                    [
                        str(task.get("parent_id") or ""),
                        str(task.get("task_type") or ""),
                        str(task.get("title") or ""),
                    ]
                )
            )
        return "|".join(sorted(parts))

    @staticmethod
    def recovery_suggestion(strategy: str) -> str:
        return {
            "split_task_further": "Split the task into smaller atomic tasks before retrying.",
            "ask_user": "Ask the user for the missing or conflicting input.",
            "mark_blocked": "Mark the task blocked and show the repeated condition.",
            "fallback_report": "Generate a fallback report with the last known state.",
        }.get(strategy, "Stop and report the repeated state.")
