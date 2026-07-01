#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus


ALLOWED_TRANSITIONS = {
    AgentTaskStatus.PENDING.value: {
        AgentTaskStatus.READY.value,
        AgentTaskStatus.WAITING_INPUT.value,
        AgentTaskStatus.BLOCKED.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.READY.value: {
        AgentTaskStatus.RUNNING.value,
        AgentTaskStatus.WAITING_INPUT.value,
        AgentTaskStatus.BLOCKED.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.RUNNING.value: {
        AgentTaskStatus.VERIFIED.value,
        AgentTaskStatus.FAILED.value,
        AgentTaskStatus.WAITING_INPUT.value,
        AgentTaskStatus.BLOCKED.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.WAITING_INPUT.value: {
        AgentTaskStatus.READY.value,
        AgentTaskStatus.BLOCKED.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.FAILED.value: {
        AgentTaskStatus.READY.value,
        AgentTaskStatus.BLOCKED.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.VERIFIED.value: {
        AgentTaskStatus.COMPLETED.value,
        AgentTaskStatus.READY.value,
        AgentTaskStatus.BLOCKED.value,
    },
    AgentTaskStatus.BLOCKED.value: {
        AgentTaskStatus.READY.value,
        AgentTaskStatus.CANCELED.value,
    },
    AgentTaskStatus.COMPLETED.value: set(),
    AgentTaskStatus.CANCELED.value: set(),
}


class AgentTaskStateService:
    @classmethod
    def transition(
        cls,
        task_id: str,
        to_status: str,
        *,
        reason: str = "",
        actor: str = "system",
    ) -> dict[str, str]:
        task = AgentTaskModelService.get_task(task_id)
        from_status = task["status"]
        target = AgentTaskModelService.normalize_status(to_status)
        if target == from_status:
            return {"task_id": task_id, "from_status": from_status, "to_status": target, "changed": False}
        if target not in ALLOWED_TRANSITIONS.get(from_status, set()):
            raise AgentTaskError(
                "INVALID_TASK_STATUS_TRANSITION",
                "Invalid task status transition.",
                {"task_id": task_id, "from_status": from_status, "to_status": target},
            )
        before = task
        after = AgentTaskModelService.update_task(task_id, status=target)
        AgentTaskModelService.record_audit(
            goal_id=after["goal_id"],
            task_id=task_id,
            action="task_status_transition",
            actor=actor,
            before={"status": from_status},
            after={"status": target},
            metadata={"reason": reason},
        )
        return {"task_id": task_id, "from_status": before["status"], "to_status": target, "changed": True}

    @classmethod
    def mark_ready(cls, task_id: str, *, reason: str = "") -> dict[str, str]:
        return cls.transition(task_id, AgentTaskStatus.READY.value, reason=reason)

    @classmethod
    def mark_running(cls, task_id: str, *, reason: str = "") -> dict[str, str]:
        return cls.transition(task_id, AgentTaskStatus.RUNNING.value, reason=reason)

    @classmethod
    def mark_blocked(cls, task_id: str, *, reason: str = "") -> dict[str, str]:
        return cls.transition(task_id, AgentTaskStatus.BLOCKED.value, reason=reason)
