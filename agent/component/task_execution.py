#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_execution_service import AgentTaskExecutionService


class _TaskExecutionParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _TaskExecutionComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class TaskExecutorParam(_TaskExecutionParam):
    def __init__(self):
        super().__init__()
        self.task_id = ""
        self.frame_id = ""
        self.parent_frame_id = ""
        self.continuation_pointer = ""
        self.runtime_context = {}
        self.root = ""
        self.max_retry = 1
        self.outputs = {
            "execution_result": {"value": {}, "type": "JSON"},
            "result": {"value": {}, "type": "JSON"},
            "status": {"value": "", "type": "String"},
            "ok": {"value": False, "type": "Boolean"},
        }
        self.input_schema = {
            "task_id": {"type": "String", "required": True},
            "runtime_context": {"type": "JSON", "required": False},
        }


class TaskExecutor(_TaskExecutionComponent, ABC):
    component_name = "TaskExecutor"

    def _invoke(self, **kwargs):
        runtime_context = self._resolve(self._param.runtime_context) or kwargs.get("runtime_context") or {}
        result = AgentTaskExecutionService.execute_leaf_task(
            str(self._resolve(self._param.task_id) or kwargs.get("task_id") or ""),
            frame_id=str(self._resolve(self._param.frame_id) or ""),
            parent_frame_id=str(self._resolve(self._param.parent_frame_id) or ""),
            continuation_pointer=str(self._resolve(self._param.continuation_pointer) or ""),
            runtime_context=runtime_context if isinstance(runtime_context, dict) else {},
            root=str(self._resolve(self._param.root) or ""),
            max_retry=int(self._param.max_retry or 1),
        )
        self.set_output("execution_result", result)
        self.set_output("result", result.get("result", {}))
        self.set_output("status", result.get("status", ""))
        self.set_output("ok", bool(result.get("ok")))


class TaskFrameControllerParam(_TaskExecutionParam):
    def __init__(self):
        super().__init__()
        self.action = "continue"
        self.task_id = ""
        self.child_task_id = ""
        self.frame_id = ""
        self.parent_frame_id = ""
        self.return_to_task_id = ""
        self.continuation_pointer = ""
        self.local_context = {}
        self.reason = ""
        self.outputs = {
            "frame_result": {"value": {}, "type": "JSON"},
            "frame": {"value": {}, "type": "JSON"},
            "status": {"value": "", "type": "String"},
            "continuation_pointer": {"value": "", "type": "String"},
            "local_context": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {
            "action": {"type": "String", "required": True},
            "task_id": {"type": "String", "required": False},
            "frame_id": {"type": "String", "required": False},
        }


class TaskFrameController(_TaskExecutionComponent, ABC):
    component_name = "TaskFrameController"

    def _invoke(self, **kwargs):
        action = str(self._resolve(self._param.action) or kwargs.get("action") or "continue")
        frame_id = str(self._resolve(self._param.frame_id) or "")
        if action == "enter_child":
            local_context = self._resolve(self._param.local_context) or {}
            result = AgentTaskExecutionService.enter_child_task(
                child_task_id=str(self._resolve(self._param.child_task_id) or self._resolve(self._param.task_id) or ""),
                parent_frame_id=str(self._resolve(self._param.parent_frame_id) or ""),
                return_to_task_id=str(self._resolve(self._param.return_to_task_id) or ""),
                continuation_pointer=str(self._resolve(self._param.continuation_pointer) or ""),
                local_context=local_context if isinstance(local_context, dict) else {},
            )
            payload = {"frame": result, "status": result.get("status", "")}
        elif action == "pause":
            result = AgentTaskExecutionService.pause_frame(frame_id, reason=str(self._resolve(self._param.reason) or ""))
            payload = {"frame": result, "status": result.get("status", "")}
        elif action == "resume":
            result = AgentTaskExecutionService.resume_frame(frame_id)
            payload = {"frame": result, "status": result.get("status", "")}
        else:
            result = AgentTaskExecutionService.continue_from_frame(frame_id)
            payload = {"frame": result, "status": result.get("status", "")}
        frame = payload.get("frame", {})
        self.set_output("frame_result", payload)
        self.set_output("frame", frame)
        self.set_output("status", payload.get("status", ""))
        self.set_output("continuation_pointer", frame.get("continuation_pointer", ""))
        self.set_output("local_context", frame.get("local_context", {}))
