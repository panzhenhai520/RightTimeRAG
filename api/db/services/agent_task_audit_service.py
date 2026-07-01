#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from typing import Any

from api.db.services.agent_task_model_service import AgentTaskModelService


class AgentTaskAuditService:
    @classmethod
    def record(
        cls,
        *,
        goal_id: str,
        task_id: str = "",
        action: str,
        actor: str = "system",
        before: Any = None,
        after: Any = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return AgentTaskModelService.record_audit(
            goal_id=goal_id,
            task_id=task_id,
            action=action,
            actor=actor,
            before=before,
            after=after,
            metadata=metadata,
        )

    @classmethod
    def list(cls, *, goal_id: str = "", task_id: str = "") -> list[dict[str, Any]]:
        return AgentTaskModelService.list_audit(goal_id=goal_id, task_id=task_id)
