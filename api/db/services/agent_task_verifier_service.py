#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_planner_service import TaskNodeFactory
from api.db.services.agent_task_state_service import AgentTaskStateService


SUPPORTED_VERIFICATION_CHECKS = {
    "schema_match",
    "evidence_present",
    "completion_criteria_met",
    "no_unresolved_dependency",
    "no_policy_violation",
    "output_diff_expected",
    "parent_goal_progressed",
}


class TaskResultVerifier:
    @classmethod
    def verify(
        cls,
        *,
        task: dict[str, Any],
        result: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        checks: list[str] | None = None,
        mark_verified: bool = False,
    ) -> dict[str, Any]:
        payload = result if isinstance(result, dict) else {}
        runtime = runtime_context if isinstance(runtime_context, dict) else {}
        selected_checks = checks or [
            "schema_match",
            "evidence_present",
            "completion_criteria_met",
            "no_unresolved_dependency",
            "no_policy_violation",
            "parent_goal_progressed",
        ]
        check_results = [
            cls.run_check(check, task=task, result=payload, runtime_context=runtime)
            for check in selected_checks
            if check in SUPPORTED_VERIFICATION_CHECKS
        ]
        ok = all(item["passed"] for item in check_results)
        if ok and mark_verified and task.get("task_id"):
            cls.mark_verified_if_running(str(task["task_id"]))
        reflection = TaskReflectionService.reflect(task=task, result=payload, verification={"ok": ok, "check_results": check_results})
        decision = ReplanDecider.decide(task=task, verification={"ok": ok, "check_results": check_results}, reflection=reflection)
        return {
            "schema_version": 1,
            "task_id": str(task.get("task_id") or task.get("node_id") or ""),
            "ok": ok,
            "check_results": check_results,
            "failed_checks": [item for item in check_results if not item["passed"]],
            "reflection": reflection,
            "decision": decision,
            "next_action": decision["next_action"],
        }

    @classmethod
    def verify_model_task(
        cls,
        task_id: str,
        *,
        result: dict[str, Any] | None = None,
        runtime_context: dict[str, Any] | None = None,
        checks: list[str] | None = None,
        mark_verified: bool = False,
    ) -> dict[str, Any]:
        task = AgentTaskModelService.get_task(task_id)
        payload = result if isinstance(result, dict) else task.get("outputs", {})
        return cls.verify(task=task, result=payload, runtime_context=runtime_context, checks=checks, mark_verified=mark_verified)

    @classmethod
    def run_check(cls, check: str, *, task: dict[str, Any], result: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        if check == "schema_match":
            return cls.check_schema_match(task, result)
        if check == "evidence_present":
            return cls.check_evidence_present(task, result)
        if check == "completion_criteria_met":
            return cls.check_completion_criteria(task, result)
        if check == "no_unresolved_dependency":
            return cls.check_unresolved_dependencies(result, runtime_context)
        if check == "no_policy_violation":
            return cls.check_policy(result)
        if check == "output_diff_expected":
            return cls.check_output_diff_expected(task, result, runtime_context)
        if check == "parent_goal_progressed":
            return cls.check_parent_goal_progressed(task, result)
        return {"check": check, "passed": False, "code": "unsupported_check", "message": f"Unsupported check: {check}"}

    @staticmethod
    def check_schema_match(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        required_keys = []
        schema = task.get("outputs") if isinstance(task.get("outputs"), dict) else {}
        for key, value in schema.items():
            if isinstance(value, str) and value in {"String", "JSON", "TextDocument", "Array<JSON>", "Boolean", "Number"}:
                required_keys.append(key)
        explicit = task.get("metadata", {}).get("required_output_keys") if isinstance(task.get("metadata"), dict) else None
        if isinstance(explicit, list):
            required_keys = [str(item) for item in explicit]
        missing = [key for key in required_keys if key not in result or result.get(key) in (None, "")]
        return {
            "check": "schema_match",
            "passed": not missing,
            "code": "ok" if not missing else "missing_output_keys",
            "message": "Output schema matched." if not missing else "Required output keys are missing.",
            "details": {"required_keys": required_keys, "missing_keys": missing},
        }

    @staticmethod
    def check_evidence_present(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        requirements = task.get("evidence_requirement") or task.get("evidence") or []
        required = [item for item in requirements if isinstance(item, dict) and item.get("required")]
        evidence_values = [
            result.get("source_ref"),
            result.get("audit"),
            result.get("references"),
            result.get("evidence"),
            result.get("file"),
        ]
        passed = not required or any(bool(value) for value in evidence_values)
        return {
            "check": "evidence_present",
            "passed": passed,
            "code": "ok" if passed else "missing_evidence",
            "message": "Evidence is present." if passed else "Required evidence is missing.",
            "details": {"required_count": len(required)},
        }

    @classmethod
    def check_completion_criteria(cls, task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        criteria = task.get("completion_criteria") if isinstance(task.get("completion_criteria"), list) else []
        failures = []
        for criterion in criteria:
            if not cls.criterion_met(criterion, result):
                failures.append(criterion)
        return {
            "check": "completion_criteria_met",
            "passed": not failures,
            "code": "ok" if not failures else "completion_criteria_unmet",
            "message": "Completion criteria met." if not failures else "Some completion criteria are unmet.",
            "details": {"failed_criteria": failures},
        }

    @staticmethod
    def criterion_met(criterion: dict[str, Any], result: dict[str, Any]) -> bool:
        kind = str(criterion.get("kind") or "")
        if kind == "output_available":
            output = criterion.get("output") or "result"
            return output in result and result.get(output) not in (None, "")
        mapping = {
            "candidate_selected": ("selected_file", "candidate_files"),
            "candidate_files_ranked": ("candidate_files",),
            "document_loaded": ("document", "lines", "chunks"),
            "outline_extracted": ("outline", "sections"),
            "content_classified": ("classified_content", "content_categories"),
            "structure_recommendation_created": ("structure_recommendation", "structure_advice"),
            "revision_plan_created": ("revision_plan",),
            "patch_proposal_created": ("patch_proposal",),
            "diff_review_completed": ("diff_review", "diff"),
            "comparison_completed": ("diff", "matches", "conflicts"),
            "report_created": ("report", "markdown"),
            "items_extracted": ("items", "clauses", "viewpoints", "risk_points"),
            "answer_created": ("answer",),
        }
        keys = mapping.get(kind)
        if keys:
            return any(result.get(key) for key in keys)
        return bool(result)

    @staticmethod
    def check_unresolved_dependencies(result: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        unresolved = result.get("unresolved_context") or result.get("unresolved_dependencies") or []
        dependency_result = runtime_context.get("dependency_result") if isinstance(runtime_context.get("dependency_result"), dict) else {}
        blocked = dependency_result.get("blocked_by") or []
        passed = not unresolved and not blocked
        return {
            "check": "no_unresolved_dependency",
            "passed": passed,
            "code": "ok" if passed else "unresolved_dependency",
            "message": "No unresolved dependency." if passed else "Unresolved dependency remains.",
            "details": {"unresolved": unresolved, "blocked_by": blocked},
        }

    @staticmethod
    def check_policy(result: dict[str, Any]) -> dict[str, Any]:
        violations = result.get("policy_violations") or result.get("violations") or []
        violation = bool(result.get("policy_violation")) or bool(violations)
        return {
            "check": "no_policy_violation",
            "passed": not violation,
            "code": "ok" if not violation else "policy_violation",
            "message": "No policy violation." if not violation else "Policy violation detected.",
            "details": {"violations": violations},
        }

    @staticmethod
    def check_output_diff_expected(task: dict[str, Any], result: dict[str, Any], runtime_context: dict[str, Any]) -> dict[str, Any]:
        expected = runtime_context.get("expected_diff")
        if expected is None:
            expected = task.get("metadata", {}).get("expected_diff") if isinstance(task.get("metadata"), dict) else None
        if expected is None:
            return {"check": "output_diff_expected", "passed": True, "code": "not_required", "message": "No expected diff constraint."}
        changed = result.get("diff", {}).get("summary", {}).get("changed") if isinstance(result.get("diff"), dict) else None
        passed = bool(changed) if expected else not bool(changed)
        return {
            "check": "output_diff_expected",
            "passed": passed,
            "code": "ok" if passed else "unexpected_diff_state",
            "message": "Diff expectation matched." if passed else "Diff expectation did not match.",
            "details": {"expected_diff": expected, "changed": changed},
        }

    @staticmethod
    def check_parent_goal_progressed(task: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
        progressed = bool(result) and not result.get("unresolved_context")
        return {
            "check": "parent_goal_progressed",
            "passed": progressed,
            "code": "ok" if progressed else "goal_not_progressed",
            "message": "Task output can progress the parent goal." if progressed else "Task output does not progress the parent goal.",
        }

    @staticmethod
    def mark_verified_if_running(task_id: str) -> None:
        task = AgentTaskModelService.get_task(task_id)
        if task["status"] == AgentTaskStatus.RUNNING.value:
            AgentTaskStateService.transition(task_id, AgentTaskStatus.VERIFIED.value, reason="result verification passed")


class TaskReflectionService:
    @staticmethod
    def reflect(*, task: dict[str, Any], result: dict[str, Any], verification: dict[str, Any]) -> dict[str, Any]:
        failed = [item for item in verification.get("check_results", []) if not item.get("passed")]
        root_causes = []
        for item in failed:
            code = item.get("code")
            if code in {"missing_output_keys", "completion_criteria_unmet"}:
                root_causes.append("incomplete_output")
            elif code == "missing_evidence":
                root_causes.append("missing_evidence")
            elif code == "unresolved_dependency":
                root_causes.append("unresolved_dependency")
            elif code == "policy_violation":
                root_causes.append("policy_violation")
            elif code == "goal_not_progressed":
                root_causes.append("ambiguous_progress")
        return {
            "summary": "verification passed" if not failed else "verification failed",
            "failed_check_count": len(failed),
            "root_causes": sorted(set(root_causes)),
            "retryable": bool(failed) and not any(item.get("code") == "policy_violation" for item in failed),
            "task_type": task.get("task_type", ""),
            "result_keys": sorted(result.keys()),
        }


class ReplanDecider:
    @classmethod
    def decide(cls, *, task: dict[str, Any], verification: dict[str, Any], reflection: dict[str, Any]) -> dict[str, Any]:
        if verification.get("ok"):
            return {
                "next_action": "return_to_parent" if task.get("parent_task_id") or task.get("parent_id") else "complete_goal",
                "reason": "verification_passed",
                "repair_tasks": [],
            }
        causes = set(reflection.get("root_causes") or [])
        if "policy_violation" in causes:
            return {"next_action": "mark_blocked", "reason": "policy_violation", "repair_tasks": []}
        if "unresolved_dependency" in causes:
            return {"next_action": "create_repair_task", "reason": "unresolved_dependency", "repair_tasks": [cls.repair_task(task, "resolve_dependency")]}
        if "missing_evidence" in causes:
            return {"next_action": "retry_same_task", "reason": "missing_evidence", "repair_tasks": []}
        if "incomplete_output" in causes:
            return {"next_action": "create_repair_task", "reason": "incomplete_output", "repair_tasks": [cls.repair_task(task, "complete_output")]}
        if "ambiguous_progress" in causes:
            return {"next_action": "split_task_further", "reason": "ambiguous_progress", "repair_tasks": [cls.repair_task(task, "split_task")]}
        return {"next_action": "ask_user", "reason": "unknown_verification_failure", "repair_tasks": []}

    @staticmethod
    def repair_task(task: dict[str, Any], repair_kind: str) -> dict[str, Any]:
        parent_id = str(task.get("task_id") or task.get("node_id") or "")
        return TaskNodeFactory.make_node(
            node_id=f"repair-{repair_kind}",
            parent_id=parent_id,
            task_type=repair_kind,
            title=f"Repair {repair_kind}",
            inputs={"source_task": parent_id, "repair_kind": repair_kind},
            outputs={"repair_result": "JSON"},
            preconditions=[],
            completion_criteria=[{"kind": "repair_result_available"}],
            tool_hint="TaskPlanner",
            evidence_requirement=[{"kind": "repair_reason", "required": True}],
            metadata={"repair_task": True},
        )
