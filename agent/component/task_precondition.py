#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_precondition_service import (
    DependencyResolver as DependencyResolverService,
    PreconditionChecker as PreconditionCheckerService,
)


class _TaskPreconditionParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _TaskPreconditionComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class PreconditionCheckerParam(_TaskPreconditionParam):
    def __init__(self):
        super().__init__()
        self.task = {}
        self.runtime_context = {}
        self.root = ""
        self.mark_ready = False
        self.outputs = {
            "precondition_result": {"value": {}, "type": "JSON"},
            "ready": {"value": False, "type": "Boolean"},
            "next_status": {"value": "", "type": "String"},
            "condition_results": {"value": [], "type": "Array<JSON>"},
            "repair_tasks": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "task": {"type": "JSON", "required": True},
            "runtime_context": {"type": "JSON", "required": False},
            "root": {"type": "String", "required": False},
        }


class PreconditionChecker(_TaskPreconditionComponent, ABC):
    component_name = "PreconditionChecker"

    def _invoke(self, **kwargs):
        task = self._resolve(self._param.task) or kwargs.get("task") or {}
        runtime_context = self._resolve(self._param.runtime_context) or kwargs.get("runtime_context") or {}
        result = PreconditionCheckerService.check(
            task if isinstance(task, dict) else {},
            runtime_context=runtime_context if isinstance(runtime_context, dict) else {},
            root=str(self._resolve(self._param.root) or ""),
            mark_ready=bool(self._param.mark_ready),
        )
        self.set_output("precondition_result", result)
        self.set_output("ready", result["ok"])
        self.set_output("next_status", result["next_status"])
        self.set_output("condition_results", result["condition_results"])
        self.set_output("repair_tasks", result["repair_tasks"])


class DependencyResolverParam(_TaskPreconditionParam):
    def __init__(self):
        super().__init__()
        self.task = {}
        self.tasks = []
        self.runtime_context = {}
        self.outputs = {
            "dependency_result": {"value": {}, "type": "JSON"},
            "ready": {"value": False, "type": "Boolean"},
            "dependencies": {"value": [], "type": "Array<JSON>"},
            "blocked_by": {"value": [], "type": "Array<JSON>"},
            "repair_tasks": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "task": {"type": "JSON", "required": True},
            "tasks": {"type": "Array<JSON>", "required": False},
            "runtime_context": {"type": "JSON", "required": False},
        }


class DependencyResolver(_TaskPreconditionComponent, ABC):
    component_name = "DependencyResolver"

    def _invoke(self, **kwargs):
        task = self._resolve(self._param.task) or kwargs.get("task") or {}
        tasks = self._resolve(self._param.tasks) or kwargs.get("tasks") or []
        runtime_context = self._resolve(self._param.runtime_context) or kwargs.get("runtime_context") or {}
        result = DependencyResolverService.resolve(
            task if isinstance(task, dict) else {},
            tasks=tasks if isinstance(tasks, list) else [],
            runtime_context=runtime_context if isinstance(runtime_context, dict) else {},
        )
        self.set_output("dependency_result", result)
        self.set_output("ready", result["ok"])
        self.set_output("dependencies", result["dependencies"])
        self.set_output("blocked_by", result["blocked_by"])
        self.set_output("repair_tasks", result["repair_tasks"])
