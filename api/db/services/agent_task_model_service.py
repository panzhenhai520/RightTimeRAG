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

from copy import deepcopy
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


class AgentTaskError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


class AgentTaskStatus(StrEnum):
    PENDING = "pending"
    READY = "ready"
    RUNNING = "running"
    WAITING_INPUT = "waiting_input"
    BLOCKED = "blocked"
    FAILED = "failed"
    VERIFIED = "verified"
    COMPLETED = "completed"
    CANCELED = "canceled"


class AgentTaskRelation(StrEnum):
    PARENT = "parent"
    CHILD = "child"
    DEPENDS_ON = "depends_on"
    BLOCKS = "blocks"
    REPAIR_FOR = "repair_for"
    RETURN_TO = "return_to"


class AgentTaskModelService:
    """In-process task model store for planner/executor services."""

    _goals: dict[str, dict[str, Any]] = {}
    _tasks: dict[str, dict[str, Any]] = {}
    _relations: list[dict[str, Any]] = []
    _frames: dict[str, dict[str, Any]] = {}
    _audit: list[dict[str, Any]] = []

    @classmethod
    def reset(cls) -> None:
        cls._goals = {}
        cls._tasks = {}
        cls._relations = []
        cls._frames = {}
        cls._audit = []

    @classmethod
    def now(cls) -> str:
        return datetime.now(timezone.utc).isoformat()

    @classmethod
    def new_id(cls, prefix: str) -> str:
        return f"{prefix}-{uuid4().hex[:12]}"

    @classmethod
    def create_goal(
        cls,
        *,
        raw_request: str,
        goal_type: str = "unknown",
        primary_object: str = "",
        expected_outcome: str = "",
        constraints: list[Any] | None = None,
        risk_level: str = "low",
        requires_user_confirmation: bool = False,
        confidence: float = 0.0,
        metadata: dict[str, Any] | None = None,
        goal_id: str | None = None,
    ) -> dict[str, Any]:
        goal_id = goal_id or cls.new_id("goal")
        if goal_id in cls._goals:
            raise AgentTaskError("GOAL_EXISTS", "Goal already exists.", {"goal_id": goal_id})
        goal = {
            "schema_version": 1,
            "goal_id": goal_id,
            "raw_request": raw_request,
            "goal_type": goal_type,
            "primary_object": primary_object,
            "expected_outcome": expected_outcome,
            "constraints": deepcopy(constraints or []),
            "risk_level": risk_level,
            "requires_user_confirmation": bool(requires_user_confirmation),
            "confidence": float(confidence or 0.0),
            "status": AgentTaskStatus.PENDING.value,
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
            "updated_at": cls.now(),
        }
        cls._goals[goal_id] = goal
        cls.record_audit(goal_id=goal_id, task_id="", action="goal_created", actor="system", before=None, after=goal)
        return deepcopy(goal)

    @classmethod
    def get_goal(cls, goal_id: str) -> dict[str, Any]:
        if goal_id not in cls._goals:
            raise AgentTaskError("GOAL_NOT_FOUND", "Goal not found.", {"goal_id": goal_id})
        return deepcopy(cls._goals[goal_id])

    @classmethod
    def create_task(
        cls,
        *,
        goal_id: str,
        task_type: str,
        title: str,
        parent_task_id: str = "",
        description: str = "",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        preconditions: list[dict[str, Any]] | None = None,
        completion_criteria: list[dict[str, Any]] | None = None,
        risk_level: str = "low",
        tool_hint: str = "",
        evidence: list[dict[str, Any]] | None = None,
        status: str = AgentTaskStatus.PENDING.value,
        metadata: dict[str, Any] | None = None,
        task_id: str | None = None,
    ) -> dict[str, Any]:
        if goal_id not in cls._goals:
            raise AgentTaskError("GOAL_NOT_FOUND", "Cannot create task for missing goal.", {"goal_id": goal_id})
        if parent_task_id and parent_task_id not in cls._tasks:
            raise AgentTaskError("PARENT_TASK_NOT_FOUND", "Parent task not found.", {"parent_task_id": parent_task_id})
        task_id = task_id or cls.new_id("task")
        if task_id in cls._tasks:
            raise AgentTaskError("TASK_EXISTS", "Task already exists.", {"task_id": task_id})
        status_value = cls.normalize_status(status)
        task = {
            "schema_version": 1,
            "task_id": task_id,
            "goal_id": goal_id,
            "parent_task_id": parent_task_id,
            "task_type": task_type,
            "title": title,
            "description": description,
            "inputs": deepcopy(inputs or {}),
            "outputs": deepcopy(outputs or {}),
            "preconditions": deepcopy(preconditions or []),
            "completion_criteria": deepcopy(completion_criteria or []),
            "status": status_value,
            "risk_level": risk_level,
            "tool_hint": tool_hint,
            "evidence": deepcopy(evidence or []),
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
            "updated_at": cls.now(),
        }
        cls._tasks[task_id] = task
        if parent_task_id:
            cls.add_relation(source_task_id=parent_task_id, target_task_id=task_id, relation=AgentTaskRelation.CHILD.value)
            cls.add_relation(source_task_id=task_id, target_task_id=parent_task_id, relation=AgentTaskRelation.PARENT.value)
        cls.record_audit(goal_id=goal_id, task_id=task_id, action="task_created", actor="system", before=None, after=task)
        return deepcopy(task)

    @classmethod
    def get_task(cls, task_id: str) -> dict[str, Any]:
        if task_id not in cls._tasks:
            raise AgentTaskError("TASK_NOT_FOUND", "Task not found.", {"task_id": task_id})
        return deepcopy(cls._tasks[task_id])

    @classmethod
    def update_task(cls, task_id: str, **changes: Any) -> dict[str, Any]:
        if task_id not in cls._tasks:
            raise AgentTaskError("TASK_NOT_FOUND", "Task not found.", {"task_id": task_id})
        before = deepcopy(cls._tasks[task_id])
        allowed = {
            "title",
            "description",
            "inputs",
            "outputs",
            "preconditions",
            "completion_criteria",
            "status",
            "risk_level",
            "tool_hint",
            "evidence",
            "metadata",
        }
        for key, value in changes.items():
            if key not in allowed:
                continue
            cls._tasks[task_id][key] = cls.normalize_status(value) if key == "status" else deepcopy(value)
        cls._tasks[task_id]["updated_at"] = cls.now()
        after = deepcopy(cls._tasks[task_id])
        cls.record_audit(goal_id=after["goal_id"], task_id=task_id, action="task_updated", actor="system", before=before, after=after)
        return after

    @classmethod
    def add_relation(
        cls,
        *,
        source_task_id: str,
        target_task_id: str,
        relation: str,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if source_task_id not in cls._tasks or target_task_id not in cls._tasks:
            raise AgentTaskError("TASK_NOT_FOUND", "Relation endpoint task not found.")
        relation_value = cls.normalize_relation(relation)
        item = {
            "relation_id": cls.new_id("rel"),
            "source_task_id": source_task_id,
            "target_task_id": target_task_id,
            "relation": relation_value,
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
        }
        key = (source_task_id, target_task_id, relation_value)
        for existing in cls._relations:
            if (existing["source_task_id"], existing["target_task_id"], existing["relation"]) == key:
                return deepcopy(existing)
        cls._relations.append(item)
        cls.record_audit(goal_id=cls._tasks[source_task_id]["goal_id"], task_id=source_task_id, action="relation_added", actor="system", before=None, after=item)
        return deepcopy(item)

    @classmethod
    def list_children(cls, task_id: str) -> list[dict[str, Any]]:
        cls.get_task(task_id)
        child_ids = [
            relation["target_task_id"]
            for relation in cls._relations
            if relation["source_task_id"] == task_id and relation["relation"] == AgentTaskRelation.CHILD.value
        ]
        return [cls.get_task(child_id) for child_id in child_ids]

    @classmethod
    def list_relations(cls, task_id: str = "") -> list[dict[str, Any]]:
        if not task_id:
            return deepcopy(cls._relations)
        return [
            deepcopy(item)
            for item in cls._relations
            if item["source_task_id"] == task_id or item["target_task_id"] == task_id
        ]

    @classmethod
    def task_tree(cls, task_id: str) -> dict[str, Any]:
        task = cls.get_task(task_id)
        children = [cls.task_tree(child["task_id"]) for child in cls.list_children(task_id)]
        return {"task": task, "children": children}

    @classmethod
    def tasks_for_goal(cls, goal_id: str) -> list[dict[str, Any]]:
        cls.get_goal(goal_id)
        return [deepcopy(task) for task in cls._tasks.values() if task["goal_id"] == goal_id]

    @classmethod
    def record_audit(
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
        item = {
            "audit_id": cls.new_id("audit"),
            "goal_id": goal_id,
            "task_id": task_id,
            "action": action,
            "actor": actor,
            "before": deepcopy(before),
            "after": deepcopy(after),
            "metadata": deepcopy(metadata or {}),
            "created_at": cls.now(),
        }
        cls._audit.append(item)
        return deepcopy(item)

    @classmethod
    def list_audit(cls, *, goal_id: str = "", task_id: str = "") -> list[dict[str, Any]]:
        return [
            deepcopy(item)
            for item in cls._audit
            if (not goal_id or item["goal_id"] == goal_id) and (not task_id or item["task_id"] == task_id)
        ]

    @staticmethod
    def normalize_status(status: Any) -> str:
        raw = str(status or "").strip()
        try:
            return AgentTaskStatus(raw).value
        except Exception as exc:
            raise AgentTaskError("INVALID_TASK_STATUS", "Invalid task status.", {"status": raw}) from exc

    @staticmethod
    def normalize_relation(relation: Any) -> str:
        raw = str(relation or "").strip()
        try:
            return AgentTaskRelation(raw).value
        except Exception as exc:
            raise AgentTaskError("INVALID_TASK_RELATION", "Invalid task relation.", {"relation": raw}) from exc
