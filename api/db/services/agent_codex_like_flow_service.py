#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_context_service import TaskContextCollector
from api.db.services.agent_task_execution_report_service import TaskExecutionReportService
from api.db.services.agent_task_planner_service import TaskPlanner
from api.db.services.agent_task_verifier_service import TaskResultVerifier
from api.db.services.document_structure_advisor_service import DocumentStructureAdvisor


class CodexLikeDocumentEditFlowService:
    @classmethod
    def run(
        cls,
        *,
        raw_request: str,
        root: str = "",
        roots: list[str | Path] | None = None,
        path: str = ".",
        new_content: str = "",
        max_candidates: int = 8,
    ) -> dict[str, Any]:
        intent = AgentGoalIntentService.classify(raw_request)
        context = TaskContextCollector.collect(
            goal_intent=intent,
            root=root,
            roots=roots,
            path=path,
            query=raw_request,
            max_candidates=max_candidates,
            normalize_top=1,
        )
        plan = TaskPlanner.plan(goal_intent=intent, context_bundle=context, max_depth=4)
        structure = DocumentStructureAdvisor.advise(
            outline=context,
            paragraphs=[],
            new_content=new_content,
            user_goal=raw_request,
        )
        verification_task = {
            "task_id": "codex-like-structure-plan",
            "parent_task_id": "codex-like-root",
            "task_type": "recommend_structure",
            "outputs": {"structure_advice": "JSON"},
            "completion_criteria": [{"kind": "structure_recommendation_created"}],
            "evidence_requirement": [{"kind": "placement_reason", "required": True}],
        }
        verification_result = {
            "structure_advice": structure,
            "source_ref": cls.source_ref(context),
            "evidence": context.get("evidence", []),
            "unresolved_context": context.get("unresolved_context", []),
        }
        verification = TaskResultVerifier.verify(
            task=verification_task,
            result=verification_result,
            runtime_context={"dependency_result": {"blocked_by": context.get("unresolved_context", [])}},
        )
        report = TaskExecutionReportService.compose(
            title="Codex-like document edit planning report",
            goal_intent=intent,
            context_bundle=context,
            task_plan=plan,
            verification=verification,
            decision=verification["decision"],
            structure_advice=structure,
        )
        return {
            "schema_version": 1,
            "goal_intent": intent,
            "context_bundle": context,
            "task_plan": plan,
            "structure_advice": structure,
            "verification": verification,
            "decision": verification["decision"],
            "report": report["report"],
            "markdown": report["markdown"],
            "audit": {
                "mode": "plan_only",
                "writes_file": False,
                "evidence_count": len(context.get("evidence", [])),
                "unresolved_count": len(context.get("unresolved_context", [])),
            },
        }

    @staticmethod
    def source_ref(context: dict[str, Any]) -> str:
        if context.get("evidence"):
            return str(context["evidence"][0].get("source_ref") or "")
        if context.get("candidate_files"):
            file_info = context["candidate_files"][0].get("file", {})
            return str(file_info.get("relative_path") or file_info.get("path") or "")
        return ""
