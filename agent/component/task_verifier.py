#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_verifier_service import (
    ReplanDecider as ReplanDeciderService,
    TaskReflectionService,
    TaskResultVerifier as TaskResultVerifierService,
)


class _TaskVerifierParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _TaskVerifierComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class TaskResultVerifierParam(_TaskVerifierParam):
    def __init__(self):
        super().__init__()
        self.task = {}
        self.result = {}
        self.runtime_context = {}
        self.checks = []
        self.outputs = {
            "verification": {"value": {}, "type": "JSON"},
            "ok": {"value": False, "type": "Boolean"},
            "failed_checks": {"value": [], "type": "Array<JSON>"},
            "next_action": {"value": "", "type": "String"},
            "repair_tasks": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "task": {"type": "JSON", "required": True},
            "result": {"type": "JSON", "required": True},
        }


class TaskResultVerifier(_TaskVerifierComponent, ABC):
    component_name = "TaskResultVerifier"

    def _invoke(self, **kwargs):
        task = self._resolve(self._param.task) or kwargs.get("task") or {}
        result = self._resolve(self._param.result) or kwargs.get("result") or {}
        runtime_context = self._resolve(self._param.runtime_context) or kwargs.get("runtime_context") or {}
        verification = TaskResultVerifierService.verify(
            task=task if isinstance(task, dict) else {},
            result=result if isinstance(result, dict) else {},
            runtime_context=runtime_context if isinstance(runtime_context, dict) else {},
            checks=self._resolve(self._param.checks) or [],
        )
        self.set_output("verification", verification)
        self.set_output("ok", verification["ok"])
        self.set_output("failed_checks", verification["failed_checks"])
        self.set_output("next_action", verification["next_action"])
        self.set_output("repair_tasks", verification["decision"]["repair_tasks"])


class TaskReflectionParam(_TaskVerifierParam):
    def __init__(self):
        super().__init__()
        self.task = {}
        self.result = {}
        self.verification = {}
        self.outputs = {
            "reflection": {"value": {}, "type": "JSON"},
            "root_causes": {"value": [], "type": "Array<String>"},
            "retryable": {"value": False, "type": "Boolean"},
        }
        self.input_schema = {"verification": {"type": "JSON", "required": True}}


class TaskReflection(_TaskVerifierComponent, ABC):
    component_name = "TaskReflection"

    def _invoke(self, **kwargs):
        task = self._resolve(self._param.task) or kwargs.get("task") or {}
        result = self._resolve(self._param.result) or kwargs.get("result") or {}
        verification = self._resolve(self._param.verification) or kwargs.get("verification") or {}
        reflection = TaskReflectionService.reflect(
            task=task if isinstance(task, dict) else {},
            result=result if isinstance(result, dict) else {},
            verification=verification if isinstance(verification, dict) else {},
        )
        self.set_output("reflection", reflection)
        self.set_output("root_causes", reflection["root_causes"])
        self.set_output("retryable", reflection["retryable"])


class ReplanDeciderParam(_TaskVerifierParam):
    def __init__(self):
        super().__init__()
        self.task = {}
        self.verification = {}
        self.reflection = {}
        self.outputs = {
            "decision": {"value": {}, "type": "JSON"},
            "next_action": {"value": "", "type": "String"},
            "repair_tasks": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "verification": {"type": "JSON", "required": True},
            "reflection": {"type": "JSON", "required": True},
        }


class ReplanDecider(_TaskVerifierComponent, ABC):
    component_name = "ReplanDecider"

    def _invoke(self, **kwargs):
        task = self._resolve(self._param.task) or kwargs.get("task") or {}
        verification = self._resolve(self._param.verification) or kwargs.get("verification") or {}
        reflection = self._resolve(self._param.reflection) or kwargs.get("reflection") or {}
        decision = ReplanDeciderService.decide(
            task=task if isinstance(task, dict) else {},
            verification=verification if isinstance(verification, dict) else {},
            reflection=reflection if isinstance(reflection, dict) else {},
        )
        self.set_output("decision", decision)
        self.set_output("next_action", decision["next_action"])
        self.set_output("repair_tasks", decision["repair_tasks"])
