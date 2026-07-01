#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.agent_task_context_service import (
    RecentArtifactFinder as RecentArtifactFinderService,
    RelevantFileResolver as RelevantFileResolverService,
    TaskContextCollector as TaskContextCollectorService,
)


class _TaskContextParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _TaskContextComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class TaskContextCollectorParam(_TaskContextParam):
    def __init__(self):
        super().__init__()
        self.goal_intent = {}
        self.root = ""
        self.path = "."
        self.query = ""
        self.extensions = []
        self.max_candidates = 8
        self.outputs = {
            "context_bundle": {"value": {}, "type": "JSON"},
            "candidate_files": {"value": [], "type": "Array<JSON>"},
            "document_outlines": {"value": [], "type": "Array<JSON>"},
            "unresolved_context": {"value": [], "type": "Array<JSON>"},
            "summary": {"value": {}, "type": "JSON"},
        }
        self.input_schema = {
            "goal_intent": {"type": "JSON", "required": True},
            "root": {"type": "String", "required": False},
            "path": {"type": "String", "required": False},
            "query": {"type": "String", "required": False},
        }


class TaskContextCollector(_TaskContextComponent, ABC):
    component_name = "TaskContextCollector"

    def _invoke(self, **kwargs):
        goal_intent = self._resolve(self._param.goal_intent) or kwargs.get("goal_intent") or {}
        bundle = TaskContextCollectorService.collect(
            goal_intent=goal_intent if isinstance(goal_intent, dict) else {},
            root=str(self._resolve(self._param.root) or ""),
            path=str(self._resolve(self._param.path) or "."),
            query=str(self._resolve(self._param.query) or ""),
            extensions=self._resolve(self._param.extensions) or [],
            max_candidates=int(self._param.max_candidates or 8),
        )
        self.set_output("context_bundle", bundle)
        self.set_output("candidate_files", bundle["candidate_files"])
        self.set_output("document_outlines", bundle["document_outlines"])
        self.set_output("unresolved_context", bundle["unresolved_context"])
        self.set_output("summary", bundle["summary"])


class RelevantFileResolverParam(_TaskContextParam):
    def __init__(self):
        super().__init__()
        self.goal_intent = {}
        self.root = ""
        self.path = "."
        self.query = ""
        self.extensions = []
        self.max_candidates = 8
        self.outputs = {
            "candidate_files": {"value": [], "type": "Array<JSON>"},
            "query_terms": {"value": [], "type": "Array<String>"},
            "unresolved_context": {"value": [], "type": "Array<JSON>"},
        }


class RelevantFileResolver(_TaskContextComponent, ABC):
    component_name = "RelevantFileResolver"

    def _invoke(self, **kwargs):
        goal_intent = self._resolve(self._param.goal_intent) or kwargs.get("goal_intent") or {}
        result = RelevantFileResolverService.resolve(
            goal_intent=goal_intent if isinstance(goal_intent, dict) else {},
            root=str(self._resolve(self._param.root) or ""),
            path=str(self._resolve(self._param.path) or "."),
            query=str(self._resolve(self._param.query) or ""),
            extensions=self._resolve(self._param.extensions) or [],
            max_candidates=int(self._param.max_candidates or 8),
        )
        self.set_output("candidate_files", result["candidate_files"])
        self.set_output("query_terms", result["query_terms"])
        self.set_output("unresolved_context", result["unresolved_context"])


class RecentArtifactFinderParam(_TaskContextParam):
    def __init__(self):
        super().__init__()
        self.artifacts = []
        self.query = ""
        self.max_results = 5
        self.outputs = {"candidate_artifacts": {"value": [], "type": "Array<JSON>"}}


class RecentArtifactFinder(_TaskContextComponent, ABC):
    component_name = "RecentArtifactFinder"

    def _invoke(self, **kwargs):
        artifacts = self._resolve(self._param.artifacts) or kwargs.get("artifacts") or []
        result = RecentArtifactFinderService.find(
            artifacts if isinstance(artifacts, list) else [],
            query=str(self._resolve(self._param.query) or ""),
            max_results=int(self._param.max_results or 5),
        )
        self.set_output("candidate_artifacts", result)
