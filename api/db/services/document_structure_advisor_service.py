#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

from __future__ import annotations

import re
from copy import deepcopy
from typing import Any


CONTENT_CATEGORY_RULES = [
    ("background", "背景说明", ("背景", "现状", "问题", "原因", "上下文", "context", "background")),
    ("goal_capability", "目标能力", ("目标", "能力", "做到", "实现", "支持", "具备", "capability", "goal")),
    ("architecture_design", "架构设计", ("架构", "层", "模块", "设计", "链路", "流程", "architecture", "layer")),
    ("development_task", "开发任务", ("开发", "新增", "实现", "接口", "服务", "节点", "api", "service", "node")),
    ("api_design", "API 设计", ("api", "接口", "endpoint", "route", "请求", "响应")),
    ("data_model", "数据模型", ("数据模型", "schema", "表", "字段", "状态", "关系", "model")),
    ("test_task", "测试任务", ("测试", "用例", "回归", "pytest", "验收测试", "test")),
    ("security_requirement", "安全要求", ("安全", "权限", "确认", "越权", "审计", "risk", "permission")),
    ("acceptance_criteria", "达成标准", ("达成标准", "验收", "通过", "完成标准", "criteria")),
    ("implementation_order", "实施顺序", ("阶段", "顺序", "先", "后", "步骤", "phase", "order")),
    ("out_of_scope", "不适合放入当前文档的内容", ("菜单", "旅游", "天气", "股票", "菜谱", "无关", "irrelevant")),
]

TARGET_SECTION_TERMS = {
    "background": ("背景", "现状", "问题"),
    "goal_capability": ("目标", "能力"),
    "architecture_design": ("架构", "设计", "流程", "层"),
    "development_task": ("开发", "任务", "交付", "范围"),
    "api_design": ("接口", "API", "api"),
    "data_model": ("数据", "模型", "schema"),
    "test_task": ("测试", "验收"),
    "security_requirement": ("安全", "权限", "确认", "审计"),
    "acceptance_criteria": ("达成", "验收", "标准"),
    "implementation_order": ("顺序", "阶段", "实施"),
}


class ContentPlacementPlanner:
    @classmethod
    def plan(
        cls,
        *,
        outline: dict[str, Any] | list[dict[str, Any]] | None = None,
        paragraphs: list[dict[str, Any]] | None = None,
        new_content: str = "",
        user_goal: str = "",
        max_heading_level: int = 4,
    ) -> dict[str, Any]:
        sections = cls.normalize_sections(outline)
        categories = cls.classify_content(new_content, user_goal=user_goal)
        insertion_points = [
            cls.insertion_point_for_category(category, sections=sections, max_heading_level=max_heading_level)
            for category in categories
        ]
        merge_strategy = cls.merge_strategy(categories, sections, new_content)
        risk_notes = cls.risk_notes(categories, sections, new_content)
        return {
            "schema_version": 1,
            "content_categories": categories,
            "insertion_points": insertion_points,
            "merge_strategy": merge_strategy,
            "risk_notes": risk_notes,
            "user_review_needed": bool(risk_notes or any(item["category"] == "out_of_scope" for item in categories)),
            "paragraph_context_count": len(paragraphs or []),
        }

    @staticmethod
    def normalize_sections(outline: dict[str, Any] | list[dict[str, Any]] | None) -> list[dict[str, Any]]:
        if isinstance(outline, list):
            raw_sections = outline
        elif isinstance(outline, dict):
            raw_sections = outline.get("sections") or outline.get("document_outlines") or []
        else:
            raw_sections = []
        sections = []
        for index, item in enumerate(raw_sections, start=1):
            if not isinstance(item, dict):
                continue
            if isinstance(item.get("sections"), list) and not item.get("title"):
                sections.extend(ContentPlacementPlanner.normalize_sections(item.get("sections")))
                continue
            title = str(item.get("title") or item.get("name") or "").strip()
            if not title:
                continue
            level = int(item.get("level") or 1)
            sections.append(
                {
                    "section_id": item.get("section_id") or item.get("block_id") or f"section-{index}",
                    "title": title,
                    "level": max(1, min(level, 6)),
                    "section_path": item.get("section_path") if isinstance(item.get("section_path"), list) else [title],
                    "source_ref": item.get("source_ref", ""),
                    "index": index,
                }
            )
        return sections

    @classmethod
    def classify_content(cls, new_content: str, *, user_goal: str = "") -> list[dict[str, Any]]:
        content_text = str(new_content or "").lower()
        text = f"{new_content}\n{user_goal}".lower()
        out_of_scope_rule = next(item for item in CONTENT_CATEGORY_RULES if item[0] == "out_of_scope")
        out_of_scope_matches = [term for term in out_of_scope_rule[2] if term.lower() in content_text]
        if out_of_scope_matches:
            return [
                {
                    "category": "out_of_scope",
                    "label": out_of_scope_rule[1],
                    "confidence": 0.9,
                    "matched_terms": out_of_scope_matches,
                }
            ]
        scored = []
        for category, label, terms in CONTENT_CATEGORY_RULES:
            matched = [term for term in terms if term.lower() in text]
            if matched:
                score = min(0.95, 0.45 + 0.12 * len(matched))
                scored.append({"category": category, "label": label, "confidence": round(score, 2), "matched_terms": matched})
        if not scored:
            scored.append({"category": "out_of_scope", "label": "不适合放入当前文档的内容", "confidence": 0.45, "matched_terms": []})
        scored.sort(key=lambda item: (item["category"] == "out_of_scope", -item["confidence"]))
        return scored[:5]

    @classmethod
    def insertion_point_for_category(cls, category: dict[str, Any], *, sections: list[dict[str, Any]], max_heading_level: int) -> dict[str, Any]:
        category_id = category["category"]
        if category_id == "out_of_scope":
            return {
                "category": category_id,
                "target_section": {},
                "proposed_level": 0,
                "proposed_title": category["label"],
                "placement": "separate_document_or_user_review",
                "reason": "Content does not match the current document categories.",
            }
        target = cls.best_section(category_id, sections)
        if not target:
            proposed_level = 2
            return {
                "category": category_id,
                "target_section": {},
                "proposed_level": proposed_level,
                "proposed_title": category["label"],
                "placement": "create_new_section",
                "reason": "No matching existing section was found.",
            }
        proposed_level = min(max(int(target.get("level", 1)) + 1, 2), max(2, int(max_heading_level or 4)))
        return {
            "category": category_id,
            "target_section": target,
            "proposed_level": proposed_level,
            "proposed_title": category["label"],
            "placement": "insert_under_section",
            "reason": f"Best match is existing section: {target.get('title', '')}.",
        }

    @staticmethod
    def best_section(category_id: str, sections: list[dict[str, Any]]) -> dict[str, Any]:
        terms = TARGET_SECTION_TERMS.get(category_id, ())
        best = None
        best_score = 0
        for section in sections:
            title = str(section.get("title") or "")
            path = " ".join(str(item) for item in section.get("section_path") or [])
            score = sum(2 for term in terms if term in title) + sum(1 for term in terms if term in path)
            if score > best_score:
                best = section
                best_score = score
        return deepcopy(best or {})

    @staticmethod
    def merge_strategy(categories: list[dict[str, Any]], sections: list[dict[str, Any]], new_content: str) -> dict[str, Any]:
        category_ids = [item["category"] for item in categories]
        if "out_of_scope" in category_ids:
            strategy = "separate_or_reject"
        elif len(category_ids) >= 3 or len(re.findall(r"^\s*[-*]\s+", new_content, flags=re.MULTILINE)) >= 3:
            strategy = "insert_as_subsections"
        elif sections:
            strategy = "append_to_matching_section"
        else:
            strategy = "create_new_outline"
        return {
            "strategy": strategy,
            "category_count": len(category_ids),
            "requires_new_heading": strategy in {"insert_as_subsections", "create_new_outline", "separate_or_reject"},
        }

    @staticmethod
    def risk_notes(categories: list[dict[str, Any]], sections: list[dict[str, Any]], new_content: str) -> list[dict[str, Any]]:
        notes = []
        if not sections:
            notes.append({"code": "missing_outline", "message": "No existing outline was provided."})
        if any(item["category"] == "out_of_scope" for item in categories):
            notes.append({"code": "out_of_scope", "message": "Content may not belong in the current document."})
        if len(categories) >= 4:
            notes.append({"code": "mixed_categories", "message": "Content spans many categories and should be split."})
        if len(new_content) > 8000:
            notes.append({"code": "large_insertion", "message": "Large insertion should be reviewed before applying."})
        return notes


class DocumentStructureAdvisor:
    @classmethod
    def advise(
        cls,
        *,
        outline: dict[str, Any] | list[dict[str, Any]] | None = None,
        paragraphs: list[dict[str, Any]] | None = None,
        new_content: str = "",
        user_goal: str = "",
        max_heading_level: int = 4,
    ) -> dict[str, Any]:
        sections = ContentPlacementPlanner.normalize_sections(outline)
        placement = ContentPlacementPlanner.plan(
            outline=sections,
            paragraphs=paragraphs or [],
            new_content=new_content,
            user_goal=user_goal,
            max_heading_level=max_heading_level,
        )
        proposed_outline = cls.proposed_outline(sections, placement["insertion_points"])
        modification_plan = cls.modification_plan(placement["insertion_points"], new_content)
        level_analysis = cls.level_analysis(placement["insertion_points"])
        return {
            "schema_version": 1,
            "content_categories": placement["content_categories"],
            "proposed_outline": proposed_outline,
            "insertion_points": placement["insertion_points"],
            "merge_strategy": placement["merge_strategy"],
            "same_level_analysis": level_analysis,
            "modification_plan": modification_plan,
            "risk_notes": placement["risk_notes"],
            "user_review_needed": placement["user_review_needed"],
            "audit": {
                "mode": "plan_only",
                "writes_file": False,
                "section_count": len(sections),
                "new_content_chars": len(new_content or ""),
            },
        }

    @staticmethod
    def proposed_outline(sections: list[dict[str, Any]], insertion_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result = [
            {
                "title": section["title"],
                "level": section["level"],
                "action": "keep",
                "section_path": section.get("section_path", []),
                "source_ref": section.get("source_ref", ""),
            }
            for section in sections
        ]
        for point in insertion_points:
            if point.get("placement") == "separate_document_or_user_review":
                continue
            result.append(
                {
                    "title": point.get("proposed_title", ""),
                    "level": point.get("proposed_level", 2),
                    "action": "insert",
                    "parent_title": point.get("target_section", {}).get("title", ""),
                    "category": point.get("category", ""),
                    "reason": point.get("reason", ""),
                }
            )
        return result

    @staticmethod
    def modification_plan(insertion_points: list[dict[str, Any]], new_content: str) -> list[dict[str, Any]]:
        operations = []
        for index, point in enumerate(insertion_points, start=1):
            if point.get("placement") == "separate_document_or_user_review":
                operations.append(
                    {
                        "operation": "skip_or_separate",
                        "order": index,
                        "category": point.get("category", ""),
                        "reason": point.get("reason", ""),
                    }
                )
                continue
            operations.append(
                {
                    "operation": "insert_section",
                    "order": index,
                    "parent_section": point.get("target_section", {}).get("title", ""),
                    "heading_level": point.get("proposed_level", 2),
                    "heading_title": point.get("proposed_title", ""),
                    "content_preview": str(new_content or "")[:240],
                    "writes_file": False,
                }
            )
        return operations

    @staticmethod
    def level_analysis(insertion_points: list[dict[str, Any]]) -> list[dict[str, Any]]:
        analysis = []
        for point in insertion_points:
            target = point.get("target_section") or {}
            target_level = int(target.get("level") or 0)
            proposed_level = int(point.get("proposed_level") or 0)
            analysis.append(
                {
                    "category": point.get("category", ""),
                    "target_title": target.get("title", ""),
                    "target_level": target_level,
                    "proposed_level": proposed_level,
                    "same_level": bool(target_level and proposed_level == target_level),
                    "recommendation": "place_as_child" if target_level and proposed_level > target_level else point.get("placement", ""),
                }
            )
        return analysis
