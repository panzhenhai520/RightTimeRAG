#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

from copy import deepcopy
from typing import Any

from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskRelation


REQUIRED_TASK_FIELDS = {
    "task_type",
    "inputs",
    "outputs",
    "preconditions",
    "completion_criteria",
    "risk_level",
    "tool_hint",
    "evidence_requirement",
}

VAGUE_ACTION_TERMS = ("handle", "process", "analyze many", "deal with", "处理一下", "分析很多")


class TaskPlanningError(Exception):
    def __init__(self, code: str, message: str, details: dict[str, Any] | None = None):
        super().__init__(message)
        self.code = code
        self.details = details or {}

    def to_dict(self) -> dict[str, Any]:
        return {"error_code": self.code, "message": str(self), "details": self.details}


class TaskNodeFactory:
    @staticmethod
    def make_node(
        *,
        node_id: str,
        task_type: str,
        title: str,
        parent_id: str = "",
        description: str = "",
        inputs: dict[str, Any] | None = None,
        outputs: dict[str, Any] | None = None,
        preconditions: list[dict[str, Any]] | None = None,
        completion_criteria: list[dict[str, Any]] | None = None,
        risk_level: str = "low",
        tool_hint: str = "",
        evidence_requirement: list[dict[str, Any]] | None = None,
        depends_on: list[str] | None = None,
        execution_mode: str = "serial",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "node_id": node_id,
            "parent_id": parent_id,
            "task_type": task_type,
            "title": title,
            "description": description,
            "inputs": deepcopy(inputs or {}),
            "outputs": deepcopy(outputs or {}),
            "preconditions": deepcopy(preconditions or []),
            "completion_criteria": deepcopy(completion_criteria or []),
            "risk_level": risk_level,
            "tool_hint": tool_hint,
            "evidence_requirement": deepcopy(evidence_requirement or []),
            "depends_on": list(depends_on or []),
            "execution_mode": execution_mode if execution_mode in {"serial", "parallel"} else "serial",
            "children": [],
            "metadata": deepcopy(metadata or {}),
        }


class AtomicTaskRefiner:
    """Refine task leaves until each leaf has a clear tool-sized contract."""

    @classmethod
    def refine_plan(cls, plan: dict[str, Any], *, max_depth: int = 4) -> dict[str, Any]:
        result = deepcopy(plan)
        tasks = result.get("tasks") if isinstance(result.get("tasks"), list) else []
        for task in tasks:
            if task.get("children"):
                task.setdefault("metadata", {})["atomic"] = False
                continue
            cls.ensure_atomic_contract(task)
            task.setdefault("metadata", {})["atomic"] = cls.is_atomic(task)
        result["atomic_tasks"] = [deepcopy(task) for task in tasks if task.get("metadata", {}).get("atomic")]
        result["validation"] = TaskPlanner.validate_plan(result, max_depth=max_depth)
        return result

    @classmethod
    def ensure_atomic_contract(cls, task: dict[str, Any]) -> None:
        if not isinstance(task.get("inputs"), dict):
            task["inputs"] = {}
        if not isinstance(task.get("outputs"), dict) or not task.get("outputs"):
            task["outputs"] = {"result": "JSON"}
        if not isinstance(task.get("preconditions"), list):
            task["preconditions"] = []
        if not task.get("risk_level"):
            task["risk_level"] = "low"
        if not task.get("tool_hint"):
            task["tool_hint"] = "Agent"
        if not isinstance(task.get("evidence_requirement"), list):
            task["evidence_requirement"] = [{"kind": "task_output", "required": True}]
        if not isinstance(task.get("completion_criteria"), list):
            task["completion_criteria"] = [{"kind": "output_available", "output": next(iter(task["outputs"].keys()), "result")}]
        if not task["completion_criteria"]:
            task["completion_criteria"] = [{"kind": "output_available", "output": next(iter(task["outputs"].keys()), "result")}]
        if not task["evidence_requirement"]:
            task["evidence_requirement"] = [{"kind": "task_output", "required": True}]

    @staticmethod
    def is_atomic(task: dict[str, Any]) -> bool:
        if task.get("children"):
            return False
        title = str(task.get("title") or "").lower()
        description = str(task.get("description") or "").lower()
        if any(term in title or term in description for term in VAGUE_ACTION_TERMS):
            return False
        return all(
            [
                isinstance(task.get("inputs"), dict),
                isinstance(task.get("outputs"), dict) and bool(task.get("outputs")),
                bool(task.get("completion_criteria")),
                bool(task.get("tool_hint")),
                bool(task.get("evidence_requirement")),
            ]
        )


class TaskDecomposer:
    """Deterministic decomposer for the first v4 planner boundary."""

    @classmethod
    def decompose(
        cls,
        *,
        goal_intent: dict[str, Any] | None,
        context_bundle: dict[str, Any] | None = None,
        max_child_tasks: int = 20,
    ) -> dict[str, Any]:
        intent = AgentGoalIntentService.normalize(goal_intent or {})
        context = context_bundle if isinstance(context_bundle, dict) else {}
        goal_type = intent["goal_type"]
        root = cls.root_node(intent)
        children = cls.template_children(goal_type, intent, context)
        if len(children) > int(max_child_tasks or 20):
            children = children[: int(max_child_tasks or 20)]
        root["children"] = [child["node_id"] for child in children]
        tasks = [root] + children
        relations = cls.dependency_relations(tasks)
        tree = cls.build_tree(tasks, root["node_id"])
        return {
            "root_task": root,
            "tasks": tasks,
            "relations": relations,
            "tree": tree,
            "parallel_groups": cls.parallel_groups(tasks),
        }

    @staticmethod
    def root_node(intent: dict[str, Any]) -> dict[str, Any]:
        return TaskNodeFactory.make_node(
            node_id="root",
            task_type=intent["goal_type"],
            title=f"Plan {intent['goal_type']} goal",
            description=intent.get("raw_request", ""),
            inputs={"goal_intent": "GoalIntent", "context_bundle": "TaskContextBundle"},
            outputs={"task_plan": "TaskPlan"},
            preconditions=[{"kind": "goal_intent_available"}],
            completion_criteria=[{"kind": "plan_validated"}],
            risk_level=intent.get("risk_level", "low"),
            tool_hint="TaskPlanner",
            evidence_requirement=[{"kind": "plan_validation", "required": True}],
            metadata={"atomic": False, "goal_id": intent.get("goal_id", "")},
        )

    @classmethod
    def template_children(cls, goal_type: str, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        if goal_type == "edit_document":
            return cls.edit_document_tasks(intent, context)
        if goal_type == "compare_documents":
            return cls.compare_document_tasks(intent, context)
        if goal_type == "find_file":
            return cls.find_file_tasks(intent, context)
        if goal_type == "read_document":
            return cls.read_document_tasks(intent, context)
        if goal_type == "extract_information":
            return cls.extract_information_tasks(intent, context)
        if goal_type == "generate_report":
            return cls.generate_report_tasks(intent, context)
        if goal_type == "run_workflow":
            return cls.run_workflow_tasks(intent, context)
        return cls.answer_question_tasks(intent, context)

    @staticmethod
    def base_inputs(intent: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
        return {
            "goal_id": intent.get("goal_id", ""),
            "raw_request": intent.get("raw_request", ""),
            "primary_object": intent.get("primary_object", ""),
            "candidate_files": context.get("candidate_files", []),
            "unresolved_context": context.get("unresolved_context", []),
        }

    @classmethod
    def edit_document_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        inputs = cls.base_inputs(intent, context)
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="find_file",
                title="Find target document",
                inputs=inputs,
                outputs={"candidate_files": "Array<JSON>", "selected_file": "JSON"},
                preconditions=[{"kind": "required_input", "field": "raw_request"}],
                completion_criteria=[{"kind": "candidate_selected"}],
                tool_hint="RelevantFileResolver",
                evidence_requirement=[{"kind": "file_candidate_reasons", "required": True}],
            ),
            TaskNodeFactory.make_node(
                node_id="task-002",
                parent_id="root",
                task_type="read_document",
                title="Read target document",
                inputs={"selected_file": "{task-001.outputs.selected_file}"},
                outputs={"document": "TextDocument", "line_map": "Array<JSON>"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "document_loaded"}],
                tool_hint="DocumentNormalizer",
                evidence_requirement=[{"kind": "source_line_refs", "required": True}],
                depends_on=["task-001"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-003",
                parent_id="root",
                task_type="analyze_document_structure",
                title="Extract document outline",
                inputs={"document": "{task-002.outputs.document}"},
                outputs={"outline": "JSON", "sections": "Array<JSON>"},
                preconditions=[{"kind": "document_loaded", "task_id": "task-002"}],
                completion_criteria=[{"kind": "outline_extracted"}],
                tool_hint="DocumentStructureAnalyzer",
                evidence_requirement=[{"kind": "section_refs", "required": True}],
                depends_on=["task-002"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-004",
                parent_id="root",
                task_type="classify_content",
                title="Classify new content",
                inputs={"raw_request": intent.get("raw_request", ""), "outline": "{task-003.outputs.outline}"},
                outputs={"classified_content": "Array<JSON>"},
                preconditions=[{"kind": "required_input", "field": "raw_request"}],
                completion_criteria=[{"kind": "content_classified"}],
                tool_hint="ContentClassifier",
                evidence_requirement=[{"kind": "classification_reason", "required": True}],
                depends_on=["task-003"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-005",
                parent_id="root",
                task_type="recommend_structure",
                title="Generate structure recommendation",
                inputs={"outline": "{task-003.outputs.outline}", "classified_content": "{task-004.outputs.classified_content}"},
                outputs={"structure_recommendation": "JSON"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-004"}],
                completion_criteria=[{"kind": "structure_recommendation_created"}],
                tool_hint="DocumentStructurePlanner",
                evidence_requirement=[{"kind": "placement_reason", "required": True}],
                depends_on=["task-004"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-006",
                parent_id="root",
                task_type="plan_document_revision",
                title="Generate revision plan",
                inputs={"document": "{task-002.outputs.document}", "structure_recommendation": "{task-005.outputs.structure_recommendation}"},
                outputs={"revision_plan": "JSON"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-005"}],
                completion_criteria=[{"kind": "revision_plan_created"}],
                risk_level="medium",
                tool_hint="DocumentRevisionPlanner",
                evidence_requirement=[{"kind": "planned_change_refs", "required": True}],
                depends_on=["task-005"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-007",
                parent_id="root",
                task_type="propose_patch",
                title="Prepare patch proposal",
                inputs={"revision_plan": "{task-006.outputs.revision_plan}"},
                outputs={"patch_proposal": "JSON"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-006"}],
                completion_criteria=[{"kind": "patch_proposal_created"}],
                risk_level="medium",
                tool_hint="PatchProposalBuilder",
                evidence_requirement=[{"kind": "diff_preview", "required": True}],
                depends_on=["task-006"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-008",
                parent_id="root",
                task_type="verify_diff",
                title="Check proposed diff",
                inputs={"patch_proposal": "{task-007.outputs.patch_proposal}"},
                outputs={"diff_review": "JSON"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-007"}],
                completion_criteria=[{"kind": "diff_review_completed"}],
                tool_hint="DocumentDiff",
                evidence_requirement=[{"kind": "diff_hunks", "required": True}],
                depends_on=["task-007"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-009",
                parent_id="root",
                task_type="generate_report",
                title="Output planning report",
                inputs={"diff_review": "{task-008.outputs.diff_review}", "revision_plan": "{task-006.outputs.revision_plan}"},
                outputs={"report": "JSON", "markdown": "String"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-008"}],
                completion_criteria=[{"kind": "report_created"}],
                tool_hint="ReportComposer",
                evidence_requirement=[{"kind": "audit_summary", "required": True}],
                depends_on=["task-008"],
            ),
        ]

    @classmethod
    def compare_document_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        inputs = cls.base_inputs(intent, context)
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="resolve_document_pair",
                title="Resolve document pair",
                inputs=inputs,
                outputs={"left_file": "JSON", "right_file": "JSON"},
                preconditions=[{"kind": "required_input", "field": "document_pair"}],
                completion_criteria=[{"kind": "document_pair_resolved"}],
                tool_hint="RelevantFileResolver",
                evidence_requirement=[{"kind": "file_candidate_reasons", "required": True}],
            ),
            TaskNodeFactory.make_node(
                node_id="task-002",
                parent_id="root",
                task_type="read_left_document",
                title="Read left document",
                inputs={"file": "{task-001.outputs.left_file}"},
                outputs={"left_document": "TextDocument"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "document_loaded"}],
                tool_hint="DocumentNormalizer",
                evidence_requirement=[{"kind": "source_line_refs", "required": True}],
                depends_on=["task-001"],
                execution_mode="parallel",
                metadata={"parallel_group": "normalize_documents"},
            ),
            TaskNodeFactory.make_node(
                node_id="task-003",
                parent_id="root",
                task_type="read_right_document",
                title="Read right document",
                inputs={"file": "{task-001.outputs.right_file}"},
                outputs={"right_document": "TextDocument"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "document_loaded"}],
                tool_hint="DocumentNormalizer",
                evidence_requirement=[{"kind": "source_line_refs", "required": True}],
                depends_on=["task-001"],
                execution_mode="parallel",
                metadata={"parallel_group": "normalize_documents"},
            ),
            TaskNodeFactory.make_node(
                node_id="task-004",
                parent_id="root",
                task_type="extract_comparable_items",
                title="Extract comparable items",
                inputs={"left_document": "{task-002.outputs.left_document}", "right_document": "{task-003.outputs.right_document}"},
                outputs={"left_items": "Array<JSON>", "right_items": "Array<JSON>"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-002"}, {"kind": "upstream_task_completed", "task_id": "task-003"}],
                completion_criteria=[{"kind": "items_extracted"}],
                tool_hint="ClauseExtractor",
                evidence_requirement=[{"kind": "item_refs", "required": True}],
                depends_on=["task-002", "task-003"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-005",
                parent_id="root",
                task_type="compare_documents",
                title="Compare documents and detect conflicts",
                inputs={"left_items": "{task-004.outputs.left_items}", "right_items": "{task-004.outputs.right_items}"},
                outputs={"matches": "Array<JSON>", "conflicts": "Array<JSON>", "missing_requirements": "Array<JSON>"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-004"}],
                completion_criteria=[{"kind": "comparison_completed"}],
                risk_level="medium",
                tool_hint="DocumentConflictDetector",
                evidence_requirement=[{"kind": "conflict_reasoning", "required": True}],
                depends_on=["task-004"],
            ),
            TaskNodeFactory.make_node(
                node_id="task-006",
                parent_id="root",
                task_type="generate_report",
                title="Compose comparison report",
                inputs={"conflicts": "{task-005.outputs.conflicts}", "matches": "{task-005.outputs.matches}"},
                outputs={"report": "JSON", "markdown": "String"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-005"}],
                completion_criteria=[{"kind": "report_created"}],
                tool_hint="DocumentCompareReportComposer",
                evidence_requirement=[{"kind": "audit_summary", "required": True}],
                depends_on=["task-005"],
            ),
        ]

    @classmethod
    def find_file_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="find_file",
                title="Find matching files",
                inputs=cls.base_inputs(intent, context),
                outputs={"candidate_files": "Array<JSON>"},
                preconditions=[{"kind": "required_input", "field": "raw_request"}],
                completion_criteria=[{"kind": "candidate_files_ranked"}],
                tool_hint="RelevantFileResolver",
                evidence_requirement=[{"kind": "file_candidate_reasons", "required": True}],
            )
        ]

    @classmethod
    def read_document_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        tasks = cls.find_file_tasks(intent, context)
        tasks.append(
            TaskNodeFactory.make_node(
                node_id="task-002",
                parent_id="root",
                task_type="read_document",
                title="Read selected document",
                inputs={"selected_file": "{task-001.outputs.candidate_files[0]}"},
                outputs={"document": "TextDocument", "line_map": "Array<JSON>"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "document_loaded"}],
                tool_hint="DocumentNormalizer",
                evidence_requirement=[{"kind": "source_line_refs", "required": True}],
                depends_on=["task-001"],
            )
        )
        return tasks

    @classmethod
    def extract_information_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        tasks = cls.read_document_tasks(intent, context)
        tasks.append(
            TaskNodeFactory.make_node(
                node_id="task-003",
                parent_id="root",
                task_type="extract_information",
                title="Extract requested information",
                inputs={"document": "{task-002.outputs.document}", "raw_request": intent.get("raw_request", "")},
                outputs={"items": "Array<JSON>", "references": "Array<JSON>"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-002"}],
                completion_criteria=[{"kind": "items_extracted"}],
                tool_hint="ViewpointExtractor",
                evidence_requirement=[{"kind": "source_refs", "required": True}],
                depends_on=["task-002"],
            )
        )
        return tasks

    @classmethod
    def generate_report_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="collect_report_inputs",
                title="Collect report inputs",
                inputs=cls.base_inputs(intent, context),
                outputs={"report_inputs": "JSON"},
                preconditions=[{"kind": "required_input", "field": "raw_request"}],
                completion_criteria=[{"kind": "report_inputs_collected"}],
                tool_hint="TaskContextCollector",
                evidence_requirement=[{"kind": "input_refs", "required": True}],
            ),
            TaskNodeFactory.make_node(
                node_id="task-002",
                parent_id="root",
                task_type="generate_report",
                title="Compose report",
                inputs={"report_inputs": "{task-001.outputs.report_inputs}"},
                outputs={"report": "JSON", "markdown": "String"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "report_created"}],
                tool_hint="ReportComposer",
                evidence_requirement=[{"kind": "audit_summary", "required": True}],
                depends_on=["task-001"],
            ),
        ]

    @classmethod
    def run_workflow_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="request_user_confirmation",
                title="Confirm workflow execution",
                inputs=cls.base_inputs(intent, context),
                outputs={"confirmation": "Boolean"},
                preconditions=[{"kind": "user_confirmation_required"}],
                completion_criteria=[{"kind": "confirmation_recorded"}],
                risk_level="high",
                tool_hint="ManualApprove",
                evidence_requirement=[{"kind": "approval_record", "required": True}],
            ),
            TaskNodeFactory.make_node(
                node_id="task-002",
                parent_id="root",
                task_type="plan_workflow_execution",
                title="Plan workflow execution",
                inputs={"confirmation": "{task-001.outputs.confirmation}", "raw_request": intent.get("raw_request", "")},
                outputs={"execution_plan": "JSON"},
                preconditions=[{"kind": "upstream_task_completed", "task_id": "task-001"}],
                completion_criteria=[{"kind": "execution_plan_created"}],
                risk_level="high",
                tool_hint="TaskPlanner",
                evidence_requirement=[{"kind": "risk_summary", "required": True}],
                depends_on=["task-001"],
            ),
        ]

    @classmethod
    def answer_question_tasks(cls, intent: dict[str, Any], context: dict[str, Any]) -> list[dict[str, Any]]:
        return [
            TaskNodeFactory.make_node(
                node_id="task-001",
                parent_id="root",
                task_type="answer_question",
                title="Answer user question",
                inputs=cls.base_inputs(intent, context),
                outputs={"answer": "String"},
                preconditions=[{"kind": "required_input", "field": "raw_request"}],
                completion_criteria=[{"kind": "answer_created"}],
                tool_hint="Agent",
                evidence_requirement=[{"kind": "reasoning_summary", "required": True}],
            )
        ]

    @staticmethod
    def dependency_relations(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        relations = []
        existing_ids = {task["node_id"] for task in tasks}
        for task in tasks:
            for dep_id in task.get("depends_on", []):
                if dep_id in existing_ids:
                    relations.append(
                        {
                            "source_node_id": task["node_id"],
                            "target_node_id": dep_id,
                            "relation": AgentTaskRelation.DEPENDS_ON.value,
                        }
                    )
        return relations

    @staticmethod
    def build_tree(tasks: list[dict[str, Any]], root_id: str) -> dict[str, Any]:
        by_id = {task["node_id"]: deepcopy(task) for task in tasks}
        for task in by_id.values():
            task["children"] = []
        for task in tasks:
            parent_id = task.get("parent_id")
            if parent_id and parent_id in by_id:
                by_id[parent_id]["children"].append(by_id[task["node_id"]])
        return by_id[root_id]

    @staticmethod
    def parallel_groups(tasks: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: dict[str, list[str]] = {}
        for task in tasks:
            group = task.get("metadata", {}).get("parallel_group")
            if group:
                groups.setdefault(str(group), []).append(task["node_id"])
        return [{"group_id": group_id, "node_ids": node_ids} for group_id, node_ids in groups.items() if len(node_ids) > 1]


class TaskPlanner:
    @classmethod
    def plan(
        cls,
        *,
        goal_intent: dict[str, Any] | None,
        context_bundle: dict[str, Any] | None = None,
        max_depth: int = 4,
        max_child_tasks: int = 20,
        persist: bool = False,
    ) -> dict[str, Any]:
        decomposed = TaskDecomposer.decompose(
            goal_intent=goal_intent,
            context_bundle=context_bundle,
            max_child_tasks=max_child_tasks,
        )
        plan = {
            "schema_version": 1,
            "plan_id": AgentTaskModelService.new_id("plan"),
            "goal_id": AgentGoalIntentService.normalize(goal_intent or {}).get("goal_id", ""),
            "root_task": decomposed["root_task"],
            "tasks": decomposed["tasks"],
            "relations": decomposed["relations"],
            "tree": decomposed["tree"],
            "dag": {
                "nodes": [task["node_id"] for task in decomposed["tasks"]],
                "edges": decomposed["relations"],
            },
            "parallel_groups": decomposed["parallel_groups"],
            "persisted": False,
        }
        plan = AtomicTaskRefiner.refine_plan(plan, max_depth=max_depth)
        if persist:
            plan["persisted"] = True
            plan["persisted_tasks"] = cls.persist_plan(plan, goal_intent=goal_intent)
        return plan

    @classmethod
    def persist_plan(cls, plan: dict[str, Any], *, goal_intent: dict[str, Any] | None = None) -> dict[str, Any]:
        intent = AgentGoalIntentService.normalize(goal_intent or {})
        goal_id = intent.get("goal_id") or plan.get("goal_id") or AgentTaskModelService.new_id("goal")
        try:
            AgentTaskModelService.get_goal(goal_id)
        except Exception:
            AgentTaskModelService.create_goal(
                goal_id=goal_id,
                raw_request=intent.get("raw_request", ""),
                goal_type=intent.get("goal_type", "needs_clarification"),
                primary_object=intent.get("primary_object", ""),
                expected_outcome=intent.get("expected_outcome", ""),
                constraints=intent.get("constraints", []),
                risk_level=intent.get("risk_level", "low"),
                requires_user_confirmation=intent.get("requires_user_confirmation", False),
                confidence=intent.get("confidence", 0.0),
            )
        node_to_task = {}
        for node in plan.get("tasks", []):
            parent_task_id = node_to_task.get(node.get("parent_id"), "")
            task = AgentTaskModelService.create_task(
                goal_id=goal_id,
                task_type=node.get("task_type", ""),
                title=node.get("title", ""),
                parent_task_id=parent_task_id,
                description=node.get("description", ""),
                inputs=node.get("inputs", {}),
                outputs=node.get("outputs", {}),
                preconditions=node.get("preconditions", []),
                completion_criteria=node.get("completion_criteria", []),
                risk_level=node.get("risk_level", "low"),
                tool_hint=node.get("tool_hint", ""),
                evidence=node.get("evidence_requirement", []),
                metadata={"plan_node_id": node.get("node_id"), **node.get("metadata", {})},
            )
            node_to_task[node["node_id"]] = task["task_id"]
        for relation in plan.get("relations", []):
            source_task_id = node_to_task.get(relation.get("source_node_id"))
            target_task_id = node_to_task.get(relation.get("target_node_id"))
            if source_task_id and target_task_id:
                AgentTaskModelService.add_relation(
                    source_task_id=source_task_id,
                    target_task_id=target_task_id,
                    relation=AgentTaskRelation.DEPENDS_ON.value,
                )
        return {"goal_id": goal_id, "node_to_task": node_to_task}

    @classmethod
    def validate_plan(cls, plan: dict[str, Any], *, max_depth: int = 4) -> dict[str, Any]:
        tasks = plan.get("tasks") if isinstance(plan.get("tasks"), list) else []
        issues = []
        by_id = {}
        for task in tasks:
            node_id = task.get("node_id")
            if not node_id:
                issues.append({"code": "missing_node_id", "message": "Task node has no node_id."})
                continue
            if node_id in by_id:
                issues.append({"code": "duplicate_node_id", "message": "Duplicate task node id.", "node_id": node_id})
            by_id[node_id] = task
            missing_fields = sorted(field for field in REQUIRED_TASK_FIELDS if field not in task)
            if missing_fields:
                issues.append({"code": "missing_required_fields", "node_id": node_id, "fields": missing_fields})
            if not task.get("children") and not task.get("completion_criteria"):
                issues.append({"code": "leaf_without_completion_criteria", "node_id": node_id})
            if not task.get("children") and not AtomicTaskRefiner.is_atomic(task):
                issues.append({"code": "non_atomic_leaf", "node_id": node_id})
        root_ids = [task.get("node_id") for task in tasks if not task.get("parent_id")]
        if len(root_ids) != 1:
            issues.append({"code": "invalid_root_count", "count": len(root_ids)})
        for task in tasks:
            parent_id = task.get("parent_id")
            if parent_id and parent_id not in by_id:
                issues.append({"code": "orphan_task", "node_id": task.get("node_id"), "parent_id": parent_id})
            for dep_id in task.get("depends_on", []):
                if dep_id not in by_id:
                    issues.append({"code": "missing_dependency", "node_id": task.get("node_id"), "dependency": dep_id})
        if cls.has_cycle(tasks):
            issues.append({"code": "dependency_cycle", "message": "Task dependency graph has a cycle."})
        depth = cls.max_tree_depth(tasks)
        if depth > int(max_depth or 4):
            issues.append({"code": "max_depth_exceeded", "depth": depth, "max_depth": int(max_depth or 4)})
        return {
            "ok": not issues,
            "issues": issues,
            "task_count": len(tasks),
            "atomic_task_count": len([task for task in tasks if task.get("metadata", {}).get("atomic")]),
            "max_depth": depth,
        }

    @staticmethod
    def has_cycle(tasks: list[dict[str, Any]]) -> bool:
        graph: dict[str, list[str]] = {task["node_id"]: list(task.get("depends_on", [])) for task in tasks if task.get("node_id")}
        visiting: set[str] = set()
        visited: set[str] = set()

        def visit(node_id: str) -> bool:
            if node_id in visiting:
                return True
            if node_id in visited:
                return False
            visiting.add(node_id)
            for dep_id in graph.get(node_id, []):
                if dep_id in graph and visit(dep_id):
                    return True
            visiting.remove(node_id)
            visited.add(node_id)
            return False

        return any(visit(node_id) for node_id in graph)

    @staticmethod
    def max_tree_depth(tasks: list[dict[str, Any]]) -> int:
        by_parent: dict[str, list[dict[str, Any]]] = {}
        roots = []
        for task in tasks:
            parent_id = task.get("parent_id") or ""
            if not parent_id:
                roots.append(task)
            by_parent.setdefault(parent_id, []).append(task)

        def depth(task: dict[str, Any], current: int) -> int:
            children = by_parent.get(task.get("node_id"), [])
            if not children:
                return current
            return max(depth(child, current + 1) for child in children)

        return max((depth(root, 1) for root in roots), default=0)
