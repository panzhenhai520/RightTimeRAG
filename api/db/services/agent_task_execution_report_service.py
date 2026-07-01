#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


class TaskExecutionReportService:
    @classmethod
    def compose(
        cls,
        *,
        title: str = "Task execution report",
        goal_intent: dict[str, Any] | None = None,
        context_bundle: dict[str, Any] | None = None,
        task_plan: dict[str, Any] | None = None,
        precondition_result: dict[str, Any] | None = None,
        execution_result: dict[str, Any] | None = None,
        verification: dict[str, Any] | None = None,
        decision: dict[str, Any] | None = None,
        structure_advice: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        goal = goal_intent if isinstance(goal_intent, dict) else {}
        context = context_bundle if isinstance(context_bundle, dict) else {}
        plan = task_plan if isinstance(task_plan, dict) else {}
        preconditions = precondition_result if isinstance(precondition_result, dict) else {}
        execution = execution_result if isinstance(execution_result, dict) else {}
        verify = verification if isinstance(verification, dict) else {}
        decide = decision if isinstance(decision, dict) else {}
        structure = structure_advice if isinstance(structure_advice, dict) else {}
        report = {
            "schema_version": 1,
            "title": title or "Task execution report",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "goal": {
                "goal_id": goal.get("goal_id", ""),
                "goal_type": goal.get("goal_type", ""),
                "primary_object": goal.get("primary_object", ""),
                "expected_outcome": goal.get("expected_outcome", ""),
                "risk_level": goal.get("risk_level", ""),
            },
            "context_summary": context.get("summary", {}),
            "plan_summary": {
                "task_count": len(plan.get("tasks") or []),
                "atomic_task_count": len(plan.get("atomic_tasks") or []),
                "validation": plan.get("validation", {}),
            },
            "precondition_summary": {
                "ok": preconditions.get("ok"),
                "next_status": preconditions.get("next_status", ""),
                "repair_task_count": len(preconditions.get("repair_tasks") or []),
            },
            "execution_summary": {
                "ok": execution.get("ok"),
                "status": execution.get("status", ""),
                "error": execution.get("error", ""),
            },
            "verification_summary": {
                "ok": verify.get("ok"),
                "failed_check_count": len(verify.get("failed_checks") or []),
                "next_action": verify.get("next_action", ""),
            },
            "decision": decide,
            "structure_summary": {
                "category_count": len(structure.get("content_categories") or []),
                "user_review_needed": structure.get("user_review_needed", False),
            },
            "audit": {"mode": "report_only", "writes_file": False},
        }
        return {"report": report, "markdown": cls.render_markdown(report), "audit": report["audit"]}

    @staticmethod
    def render_markdown(report: dict[str, Any]) -> str:
        lines = [
            f"# {report.get('title') or 'Task execution report'}",
            "",
            f"- generated_at: {report.get('generated_at', '')}",
            f"- goal_type: {report.get('goal', {}).get('goal_type', '')}",
            f"- expected_outcome: {report.get('goal', {}).get('expected_outcome', '')}",
            f"- risk_level: {report.get('goal', {}).get('risk_level', '')}",
            "",
            "## Context",
            "",
        ]
        for key, value in (report.get("context_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Plan", ""])
        for key, value in (report.get("plan_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Preconditions", ""])
        for key, value in (report.get("precondition_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Execution", ""])
        for key, value in (report.get("execution_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Verification", ""])
        for key, value in (report.get("verification_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        lines.extend(["", "## Decision", ""])
        decision = report.get("decision") or {}
        lines.append(f"- next_action: {decision.get('next_action', '')}")
        lines.append(f"- reason: {decision.get('reason', '')}")
        lines.extend(["", "## Structure", ""])
        for key, value in (report.get("structure_summary") or {}).items():
            lines.append(f"- {key}: {value}")
        return "\n".join(lines).strip() + "\n"
