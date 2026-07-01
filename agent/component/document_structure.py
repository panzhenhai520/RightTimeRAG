#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from abc import ABC
from typing import Any

from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.document_structure_advisor_service import (
    ContentPlacementPlanner as ContentPlacementPlannerService,
    DocumentStructureAdvisor as DocumentStructureAdvisorService,
)


class _DocumentStructureParam(ComponentParamBase):
    def __init__(self):
        super().__init__()

    def check(self):
        return True


class _DocumentStructureComponent(ComponentBase, ABC):
    def _resolve(self, value: Any) -> Any:
        if isinstance(value, str) and hasattr(self._canvas, "is_reff") and self._canvas.is_reff(value):
            return self._canvas.get_variable_value(value)
        return value


class DocumentStructureAdvisorParam(_DocumentStructureParam):
    def __init__(self):
        super().__init__()
        self.outline = {}
        self.paragraphs = []
        self.new_content = ""
        self.user_goal = ""
        self.max_heading_level = 4
        self.outputs = {
            "structure_advice": {"value": {}, "type": "JSON"},
            "content_categories": {"value": [], "type": "Array<JSON>"},
            "proposed_outline": {"value": [], "type": "Array<JSON>"},
            "insertion_points": {"value": [], "type": "Array<JSON>"},
            "modification_plan": {"value": [], "type": "Array<JSON>"},
            "user_review_needed": {"value": False, "type": "Boolean"},
        }
        self.input_schema = {
            "outline": {"type": "JSON", "required": True},
            "new_content": {"type": "String", "required": True},
            "user_goal": {"type": "String", "required": False},
        }


class DocumentStructureAdvisor(_DocumentStructureComponent, ABC):
    component_name = "DocumentStructureAdvisor"

    def _invoke(self, **kwargs):
        outline = self._resolve(self._param.outline) or kwargs.get("outline") or {}
        paragraphs = self._resolve(self._param.paragraphs) or kwargs.get("paragraphs") or []
        advice = DocumentStructureAdvisorService.advise(
            outline=outline,
            paragraphs=paragraphs if isinstance(paragraphs, list) else [],
            new_content=str(self._resolve(self._param.new_content) or kwargs.get("new_content") or ""),
            user_goal=str(self._resolve(self._param.user_goal) or kwargs.get("user_goal") or ""),
            max_heading_level=int(self._param.max_heading_level or 4),
        )
        self.set_output("structure_advice", advice)
        self.set_output("content_categories", advice["content_categories"])
        self.set_output("proposed_outline", advice["proposed_outline"])
        self.set_output("insertion_points", advice["insertion_points"])
        self.set_output("modification_plan", advice["modification_plan"])
        self.set_output("user_review_needed", advice["user_review_needed"])


class ContentPlacementPlannerParam(_DocumentStructureParam):
    def __init__(self):
        super().__init__()
        self.outline = {}
        self.paragraphs = []
        self.new_content = ""
        self.user_goal = ""
        self.max_heading_level = 4
        self.outputs = {
            "placement_plan": {"value": {}, "type": "JSON"},
            "content_categories": {"value": [], "type": "Array<JSON>"},
            "insertion_points": {"value": [], "type": "Array<JSON>"},
            "merge_strategy": {"value": {}, "type": "JSON"},
            "risk_notes": {"value": [], "type": "Array<JSON>"},
        }
        self.input_schema = {
            "outline": {"type": "JSON", "required": True},
            "new_content": {"type": "String", "required": True},
        }


class ContentPlacementPlanner(_DocumentStructureComponent, ABC):
    component_name = "ContentPlacementPlanner"

    def _invoke(self, **kwargs):
        outline = self._resolve(self._param.outline) or kwargs.get("outline") or {}
        paragraphs = self._resolve(self._param.paragraphs) or kwargs.get("paragraphs") or []
        plan = ContentPlacementPlannerService.plan(
            outline=outline,
            paragraphs=paragraphs if isinstance(paragraphs, list) else [],
            new_content=str(self._resolve(self._param.new_content) or kwargs.get("new_content") or ""),
            user_goal=str(self._resolve(self._param.user_goal) or kwargs.get("user_goal") or ""),
            max_heading_level=int(self._param.max_heading_level or 4),
        )
        self.set_output("placement_plan", plan)
        self.set_output("content_categories", plan["content_categories"])
        self.set_output("insertion_points", plan["insertion_points"])
        self.set_output("merge_strategy", plan["merge_strategy"])
        self.set_output("risk_notes", plan["risk_notes"])
