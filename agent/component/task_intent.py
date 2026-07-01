#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_goal_intent_service import AgentGoalIntentService


class GoalIntentClassifierParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.request = ""
        self.context = {}
        self.outputs = {
            "goal_intent": {"value": {}, "type": "JSON"},
            "goal_type": {"value": "", "type": "String"},
            "missing_inputs": {"value": [], "type": "Array<String>"},
            "requires_user_confirmation": {"value": False, "type": "Boolean"},
            "confidence": {"value": 0.0, "type": "Number"},
        }
        self.input_schema = {
            "request": {"type": "String", "required": True},
            "context": {"type": "JSON", "required": False},
        }

    def check(self):
        return True


class GoalIntentClassifier(ComponentBase, ABC):
    component_name = "GoalIntentClassifier"

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        request = self._resolve(self._param.request) or kwargs.get("request") or ""
        context = self._resolve(self._param.context) or kwargs.get("context") or {}
        intent = AgentGoalIntentService.classify(str(request), context=context if isinstance(context, dict) else {})
        self.set_output("goal_intent", intent)
        self.set_output("goal_type", intent["goal_type"])
        self.set_output("missing_inputs", intent["missing_inputs"])
        self.set_output("requires_user_confirmation", intent["requires_user_confirmation"])
        self.set_output("confidence", intent["confidence"])


class GoalNormalizerParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.goal_intent = {}
        self.outputs = {
            "goal_intent": {"value": {}, "type": "JSON"},
            "goal_type": {"value": "", "type": "String"},
            "unresolved": {"value": False, "type": "Boolean"},
        }
        self.input_schema = {"goal_intent": {"type": "JSON", "required": True}}

    def check(self):
        return True


class GoalNormalizer(ComponentBase, ABC):
    component_name = "GoalNormalizer"

    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value

    def _invoke(self, **kwargs):
        value = self._resolve(self._param.goal_intent) or kwargs.get("goal_intent") or {}
        intent = AgentGoalIntentService.normalize(value if isinstance(value, dict) else {})
        self.set_output("goal_intent", intent)
        self.set_output("goal_type", intent["goal_type"])
        self.set_output("unresolved", intent["unresolved"])
