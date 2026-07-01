#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService


class AgentTaskStackService:
    @classmethod
    def push(
        cls,
        *,
        task_id: str,
        parent_frame_id: str = "",
        return_to_task_id: str = "",
        continuation_pointer: str = "",
        local_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        if parent_frame_id and parent_frame_id not in AgentTaskModelService._frames:
            raise AgentTaskError("FRAME_NOT_FOUND", "Parent frame not found.", {"parent_frame_id": parent_frame_id})
        frame_id = AgentTaskModelService.new_id("frame")
        frame = {
            "frame_id": frame_id,
            "goal_id": task["goal_id"],
            "task_id": task_id,
            "parent_frame_id": parent_frame_id,
            "return_to_task_id": return_to_task_id,
            "continuation_pointer": continuation_pointer,
            "local_context": deepcopy(local_context or {}),
            "return_value": {},
            "status": "running",
            "created_at": AgentTaskModelService.now(),
            "updated_at": AgentTaskModelService.now(),
        }
        AgentTaskModelService._frames[frame_id] = frame
        AgentTaskModelService.record_audit(goal_id=task["goal_id"], task_id=task_id, action="stack_push", after=frame)
        return deepcopy(frame)

    @classmethod
    def get_frame(cls, frame_id: str) -> dict[str, Any]:
        if frame_id not in AgentTaskModelService._frames:
            raise AgentTaskError("FRAME_NOT_FOUND", "Frame not found.", {"frame_id": frame_id})
        return deepcopy(AgentTaskModelService._frames[frame_id])

    @classmethod
    def stack_for_goal(cls, goal_id: str) -> list[dict[str, Any]]:
        AgentTaskModelService.get_goal(goal_id)
        return [
            deepcopy(frame)
            for frame in AgentTaskModelService._frames.values()
            if frame["goal_id"] == goal_id
        ]

    @classmethod
    def return_from_frame(cls, frame_id: str, *, return_value: dict[str, Any] | None = None) -> dict[str, Any]:
        frame = cls.get_frame(frame_id)
        frame["return_value"] = deepcopy(return_value or {})
        frame["status"] = "returned"
        frame["updated_at"] = AgentTaskModelService.now()
        AgentTaskModelService._frames[frame_id] = frame
        parent_frame = None
        if frame.get("parent_frame_id"):
            parent_frame = AgentTaskModelService._frames.get(frame["parent_frame_id"])
            if parent_frame:
                parent_frame = deepcopy(parent_frame)
                parent_frame.setdefault("local_context", {})[f"return:{frame['task_id']}"] = deepcopy(return_value or {})
                parent_frame["updated_at"] = AgentTaskModelService.now()
                AgentTaskModelService._frames[parent_frame["frame_id"]] = parent_frame
        AgentTaskModelService.record_audit(
            goal_id=frame["goal_id"],
            task_id=frame["task_id"],
            action="stack_return",
            after={"frame": frame, "parent_frame": parent_frame},
        )
        return {"frame": deepcopy(frame), "parent_frame": deepcopy(parent_frame)}

    @classmethod
    def update_frame(
        cls,
        frame_id: str,
        *,
        status: str | None = None,
        continuation_pointer: str | None = None,
        local_context: dict[str, Any] | None = None,
        checkpoint: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        frame = cls.get_frame(frame_id)
        before = deepcopy(frame)
        if status is not None:
            frame["status"] = str(status)
        if continuation_pointer is not None:
            frame["continuation_pointer"] = str(continuation_pointer)
        if local_context is not None:
            frame["local_context"] = deepcopy(local_context)
        if checkpoint is not None:
            frame.setdefault("local_context", {})["checkpoint"] = deepcopy(checkpoint)
        frame["updated_at"] = AgentTaskModelService.now()
        AgentTaskModelService._frames[frame_id] = frame
        AgentTaskModelService.record_audit(
            goal_id=frame["goal_id"],
            task_id=frame["task_id"],
            action="stack_update",
            before=before,
            after=frame,
        )
        return deepcopy(frame)

    @classmethod
    def pause(cls, frame_id: str, *, reason: str = "") -> dict[str, Any]:
        frame = cls.update_frame(frame_id, status="paused", checkpoint={"reason": reason, "paused_at": AgentTaskModelService.now()})
        AgentTaskModelService.record_audit(
            goal_id=frame["goal_id"],
            task_id=frame["task_id"],
            action="stack_pause",
            after={"frame_id": frame_id, "reason": reason},
        )
        return frame

    @classmethod
    def resume(cls, frame_id: str) -> dict[str, Any]:
        frame = cls.update_frame(frame_id, status="running")
        AgentTaskModelService.record_audit(
            goal_id=frame["goal_id"],
            task_id=frame["task_id"],
            action="stack_resume",
            after={"frame_id": frame_id, "continuation_pointer": frame.get("continuation_pointer", "")},
        )
        return frame

    @classmethod
    def pop(cls, frame_id: str) -> dict[str, Any]:
        frame = cls.get_frame(frame_id)
        del AgentTaskModelService._frames[frame_id]
        AgentTaskModelService.record_audit(goal_id=frame["goal_id"], task_id=frame["task_id"], action="stack_pop", after=frame)
        return frame
