#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import re
from typing import Any

from api.db.services.agent_task_model_service import AgentTaskModelService


GOAL_TYPES = {
    "find_file",
    "read_document",
    "edit_document",
    "compare_documents",
    "extract_information",
    "generate_report",
    "run_workflow",
    "ask_question",
    "needs_clarification",
}


class AgentGoalIntentService:
    """Deterministic goal intent classifier for v4 task planning."""

    TYPE_RULES = [
        ("compare_documents", ("比对", "比较", "差异", "diff", "冲突", "合同", "条款冲突", "compare")),
        ("edit_document", ("修改", "调整", "新增", "补充", "重组", "改写", "完善", "写入", "更新文档", "edit")),
        ("find_file", ("找出", "找到", "查找", "最近", "上次写", "文件名", "search file", "find file")),
        ("read_document", ("读取", "打开", "查看", "阅读", "读一下", "open file", "read file")),
        ("extract_information", ("抽取", "提炼", "总结要点", "要点", "观点", "条款", "extract")),
        ("generate_report", ("生成报告", "输出报告", "报告", "审计报告", "report")),
        ("run_workflow", ("运行", "执行", "跑测试", "命令", "代码", "脚本", "workflow", "command", "execute")),
    ]
    HIGH_RISK_TERMS = ("写入", "删除", "覆盖", "运行", "执行", "命令", "代码", "apply_patch", "rm ", "delete", "command")
    DOCUMENT_TERMS = ("文档", "文件", "计划", "报告", "合同", "制度", "md", "docx", "pdf", "txt", "xlsx", "csv")

    @classmethod
    def classify(cls, raw_request: str, *, context: dict[str, Any] | None = None) -> dict[str, Any]:
        text = str(raw_request or "").strip()
        context = context or {}
        goal_type = cls.detect_goal_type(text)
        missing_inputs = cls.missing_inputs(text, goal_type)
        if not text:
            goal_type = "needs_clarification"
            missing_inputs = ["raw_request"]
        risk_level = cls.risk_level(text, goal_type)
        intent = {
            "schema_version": 1,
            "goal_id": context.get("goal_id") or AgentTaskModelService.new_id("goal"),
            "raw_request": text,
            "goal_type": goal_type,
            "primary_object": cls.primary_object(text, goal_type),
            "expected_outcome": cls.expected_outcome(goal_type),
            "constraints": cls.constraints(text),
            "missing_inputs": missing_inputs,
            "risk_level": risk_level,
            "requires_user_confirmation": cls.requires_confirmation(text, goal_type, risk_level),
            "confidence": cls.confidence(text, goal_type, missing_inputs),
            "unresolved": bool(missing_inputs or goal_type == "needs_clarification"),
            "reasoning_summary": cls.reasoning_summary(goal_type, missing_inputs, risk_level),
        }
        return cls.normalize(intent)

    @classmethod
    def normalize(cls, value: dict[str, Any] | None) -> dict[str, Any]:
        data = dict(value or {})
        goal_type = str(data.get("goal_type") or "needs_clarification")
        if goal_type not in GOAL_TYPES:
            goal_type = "needs_clarification"
        missing_inputs = data.get("missing_inputs")
        if isinstance(missing_inputs, str):
            missing_inputs = [missing_inputs]
        if not isinstance(missing_inputs, list):
            missing_inputs = []
        confidence = max(0.0, min(1.0, float(data.get("confidence") or 0.0)))
        risk_level = str(data.get("risk_level") or "low").lower()
        if risk_level not in {"low", "medium", "high"}:
            risk_level = "low"
        return {
            "schema_version": int(data.get("schema_version") or 1),
            "goal_id": str(data.get("goal_id") or AgentTaskModelService.new_id("goal")),
            "raw_request": str(data.get("raw_request") or ""),
            "goal_type": goal_type,
            "primary_object": str(data.get("primary_object") or ""),
            "expected_outcome": str(data.get("expected_outcome") or cls.expected_outcome(goal_type)),
            "constraints": data.get("constraints") if isinstance(data.get("constraints"), list) else [],
            "missing_inputs": missing_inputs,
            "risk_level": risk_level,
            "requires_user_confirmation": bool(data.get("requires_user_confirmation") or risk_level == "high"),
            "confidence": confidence,
            "unresolved": bool(data.get("unresolved") or missing_inputs or goal_type == "needs_clarification"),
            "reasoning_summary": str(data.get("reasoning_summary") or ""),
        }

    @classmethod
    def detect_goal_type(cls, text: str) -> str:
        lowered = text.lower()
        scores: dict[str, int] = {}
        for goal_type, terms in cls.TYPE_RULES:
            scores[goal_type] = sum(1 for term in terms if term.lower() in lowered)
        if scores["compare_documents"] and ("比对" in text or "比较" in text or "冲突" in text or "diff" in lowered):
            if ("根据比对结果" in text or "基于比对结果" in text) and ("生成报告" in text or "输出报告" in text):
                return "generate_report"
            return "compare_documents"
        if "生成报告" in text or "输出报告" in text or ("report" in lowered and any(term in lowered for term in ("generate", "create"))):
            return "generate_report"
        if scores["edit_document"] and any(term in text for term in ("文档", "计划", "文件", "报告")):
            return "edit_document"
        best = max(scores.items(), key=lambda item: item[1])
        if best[1] <= 0:
            return "ask_question" if text else "needs_clarification"
        return best[0]

    @classmethod
    def missing_inputs(cls, text: str, goal_type: str) -> list[str]:
        if goal_type == "needs_clarification":
            return ["raw_request"]
        has_path = bool(re.search(r"[\w\u4e00-\u9fff./\\-]+\.(?:md|txt|docx|pdf|xlsx|csv|json|py|ts|tsx)", text, re.IGNORECASE))
        has_recent_hint = any(term in text for term in ("最近", "上次", "刚才", "最新"))
        has_document_hint = has_path or has_recent_hint or any(term in text for term in cls.DOCUMENT_TERMS)
        if goal_type == "compare_documents":
            file_mentions = re.findall(r"[\w\u4e00-\u9fff./\\-]+\.(?:md|txt|docx|pdf|xlsx|csv|json)", text, re.IGNORECASE)
            return [] if len(file_mentions) >= 2 or ("两个" in text or "两份" in text) else ["document_a", "document_b"]
        if goal_type in {"find_file", "read_document", "edit_document"} and not has_document_hint:
            return ["target_document"]
        if goal_type == "run_workflow" and not any(term in text for term in ("测试", "脚本", "命令", "workflow", "代码")):
            return ["workflow_or_command"]
        return []

    @classmethod
    def primary_object(cls, text: str, goal_type: str) -> str:
        quoted = re.findall(r"[`《“\"]([^`》”\"]{1,120})[`》”\"]", text)
        if quoted:
            return quoted[0]
        path = re.search(r"([\w\u4e00-\u9fff./\\-]+\.(?:md|txt|docx|pdf|xlsx|csv|json|py|ts|tsx))", text, re.IGNORECASE)
        if path:
            return path.group(1)
        if goal_type in {"find_file", "edit_document", "read_document"}:
            return "target_document"
        if goal_type == "compare_documents":
            return "document_pair"
        if goal_type == "run_workflow":
            return "workflow_or_command"
        return ""

    @staticmethod
    def expected_outcome(goal_type: str) -> str:
        return {
            "find_file": "file_candidates",
            "read_document": "text_document",
            "edit_document": "revision_plan",
            "compare_documents": "comparison_report",
            "extract_information": "structured_items",
            "generate_report": "report_artifact",
            "run_workflow": "execution_plan",
            "ask_question": "answer",
            "needs_clarification": "clarification_request",
        }.get(goal_type, "answer")

    @classmethod
    def constraints(cls, text: str) -> list[str]:
        constraints = []
        if "不要" in text or "不能" in text:
            constraints.append("negative_instruction_present")
        if "只读" in text or "不要修改" in text:
            constraints.append("read_only")
        if "测试通过" in text:
            constraints.append("must_pass_tests")
        return constraints

    @classmethod
    def risk_level(cls, text: str, goal_type: str) -> str:
        if goal_type == "run_workflow" or any(term.lower() in text.lower() for term in cls.HIGH_RISK_TERMS):
            return "high"
        if goal_type in {"edit_document", "compare_documents", "generate_report"}:
            return "medium"
        return "low"

    @staticmethod
    def requires_confirmation(text: str, goal_type: str, risk_level: str) -> bool:
        if "自动" in text and risk_level != "high":
            return False
        return risk_level == "high" or goal_type == "run_workflow"

    @staticmethod
    def confidence(text: str, goal_type: str, missing_inputs: list[str]) -> float:
        if goal_type == "needs_clarification":
            return 0.2
        base = 0.72
        if missing_inputs:
            base -= 0.25
        if len(text) >= 12:
            base += 0.12
        return round(max(0.1, min(0.95, base)), 2)

    @staticmethod
    def reasoning_summary(goal_type: str, missing_inputs: list[str], risk_level: str) -> str:
        parts = [f"classified as {goal_type}", f"risk={risk_level}"]
        if missing_inputs:
            parts.append("missing: " + ", ".join(missing_inputs))
        return "; ".join(parts)
