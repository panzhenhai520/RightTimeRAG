#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_execution_report_service import TaskExecutionReportService


class TaskExecutionReportComposerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.title = "Task execution report"
        self.goal_intent = {}
        self.context_bundle = {}
        self.task_plan = {}
        self.precondition_result = {}
        self.execution_result = {}
        self.verification = {}
        self.decision = {}
        self.structure_advice = {}
        self.outputs = {
            "report": {"value": {}, "type": "JSON"},
            "markdown": {"value": "", "type": "String"},
            "audit": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {
            "goal_intent": {"type": "JSON", "required": False},
            "context_bundle": {"type": "JSON", "required": False},
            "task_plan": {"type": "JSON", "required": False},
            "verification": {"type": "JSON", "required": False},
            "decision": {"type": "JSON", "required": False},
        }

    def check(self):
        return True


class TaskExecutionReportComposer(ComponentBase, ABC):
    component_name = "TaskExecutionReportComposer"

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        result = TaskExecutionReportService.compose(
            title=str(self._resolve(self._param.title) or "Task execution report"),
            goal_intent=self._json_param("goal_intent", kwargs),
            context_bundle=self._json_param("context_bundle", kwargs),
            task_plan=self._json_param("task_plan", kwargs),
            precondition_result=self._json_param("precondition_result", kwargs),
            execution_result=self._json_param("execution_result", kwargs),
            verification=self._json_param("verification", kwargs),
            decision=self._json_param("decision", kwargs),
            structure_advice=self._json_param("structure_advice", kwargs),
        )
        self.set_output("report", result["report"])
        self.set_output("markdown", result["markdown"])
        self.set_output("audit", result["audit"])

    def _json_param(self, name: str, kwargs: dict[str, Any]) -> dict[str, Any]:
        value = self._resolve(getattr(self._param, name, {})) or kwargs.get(name) or {}
        return value if isinstance(value, dict) else {}
