#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_planner_service import (
    AtomicTaskRefiner as AtomicTaskRefinerService,
    TaskDecomposer as TaskDecomposerService,
    TaskPlanner as TaskPlannerService,
)


class _TaskPlannerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _TaskPlannerComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class TaskPlannerParam(_TaskPlannerParam):
    def __init__(self):
        super().__init__()
        self.goal_intent = {}
        self.context_bundle = {}
        self.max_depth = 4
        self.max_child_tasks = 20
        self.persist = False
        self.outputs = {
            "task_plan": {"value": {}, "type": "JSON"},
            "tasks": {"value": [], "type": "Array<JSON>"},
            "relations": {"value": [], "type": "Array<JSON>"},
            "validation": {"value": {}, "type": "JSON"},
            "atomic_tasks": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "goal_intent": {"type": "JSON", "required": True},
            "context_bundle": {"type": "JSON", "required": False},
        }


class TaskPlanner(_TaskPlannerComponent, ABC):
    component_name = "TaskPlanner"

    def _invoke(self, **kwargs):
        goal_intent = self._resolve(self._param.goal_intent) or kwargs.get("goal_intent") or {}
        context_bundle = self._resolve(self._param.context_bundle) or kwargs.get("context_bundle") or {}
        plan = TaskPlannerService.plan(
            goal_intent=goal_intent if isinstance(goal_intent, dict) else {},
            context_bundle=context_bundle if isinstance(context_bundle, dict) else {},
            max_depth=int(self._param.max_depth or 4),
            max_child_tasks=int(self._param.max_child_tasks or 20),
            persist=bool(self._param.persist),
        )
        self.set_output("task_plan", plan)
        self.set_output("tasks", plan["tasks"])
        self.set_output("relations", plan["relations"])
        self.set_output("validation", plan["validation"])
        self.set_output("atomic_tasks", plan["atomic_tasks"])


class TaskDecomposerParam(_TaskPlannerParam):
    def __init__(self):
        super().__init__()
        self.goal_intent = {}
        self.context_bundle = {}
        self.max_child_tasks = 20
        self.outputs = {
            "root_task": {"value": {}, "type": "JSON"},
            "tasks": {"value": [], "type": "Array<JSON>"},
            "relations": {"value": [], "type": "Array<JSON>"},
            "tree": {"value": {}, "type": "JSON"},
            "parallel_groups": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "goal_intent": {"type": "JSON", "required": True},
            "context_bundle": {"type": "JSON", "required": False},
        }


class TaskDecomposer(_TaskPlannerComponent, ABC):
    component_name = "TaskDecomposer"

    def _invoke(self, **kwargs):
        goal_intent = self._resolve(self._param.goal_intent) or kwargs.get("goal_intent") or {}
        context_bundle = self._resolve(self._param.context_bundle) or kwargs.get("context_bundle") or {}
        result = TaskDecomposerService.decompose(
            goal_intent=goal_intent if isinstance(goal_intent, dict) else {},
            context_bundle=context_bundle if isinstance(context_bundle, dict) else {},
            max_child_tasks=int(self._param.max_child_tasks or 20),
        )
        self.set_output("root_task", result["root_task"])
        self.set_output("tasks", result["tasks"])
        self.set_output("relations", result["relations"])
        self.set_output("tree", result["tree"])
        self.set_output("parallel_groups", result["parallel_groups"])


class AtomicTaskRefinerParam(_TaskPlannerParam):
    def __init__(self):
        super().__init__()
        self.task_plan = {}
        self.max_depth = 4
        self.outputs = {
            "task_plan": {"value": {}, "type": "JSON"},
            "atomic_tasks": {"value": [], "type": "Array<JSON>"},
            "validation": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {"task_plan": {"type": "JSON", "required": True}}


class AtomicTaskRefiner(_TaskPlannerComponent, ABC):
    component_name = "AtomicTaskRefiner"

    def _invoke(self, **kwargs):
        value = self._resolve(self._param.task_plan) or kwargs.get("task_plan") or {}
        plan = AtomicTaskRefinerService.refine_plan(
            value if isinstance(value, dict) else {},
            max_depth=int(self._param.max_depth or 4),
        )
        self.set_output("task_plan", plan)
        self.set_output("atomic_tasks", plan.get("atomic_tasks", []))
        self.set_output("validation", plan.get("validation", {}))
