#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

from __future__ import annotations

import copy
from typing import Any


class AgentTeacherRegistryService:
    """Stable built-in AI teacher registry for external schedulers.

    These records are configuration contracts. Actual workflow canvases can be
    imported or created later, but the ids, roles, context expectations, and
    output schema should remain stable for `voice-project`.
    """

    STANDARD_OUTPUT_SCHEMA = {
        "type": "object",
        "required": ["answer", "intention", "target", "confidence"],
        "properties": {
            "answer": {"type": "string"},
            "intention": {
                "type": "string",
                "enum": [
                    "propose",
                    "question",
                    "challenge",
                    "support",
                    "supplement",
                    "summarize",
                    "teach",
                    "correct",
                    "defer",
                ],
            },
            "target": {"type": "string"},
            "reply_to": {"type": "string"},
            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            "knowledge_used": {"type": "array"},
            "suggested_next_action": {"type": "string"},
            "trace_summary": {"type": "object"},
        },
    }

    DEFAULT_TEACHERS = [
        {
            "agent_id": "ai_teacher_lead",
            "workflow_id": "ai_teacher_lead_workflow",
            "name": "主持老师",
            "role": "lead_teacher",
            "speaker_role": "lead_teacher",
            "persona": "负责组织课堂节奏、总结共识、把多个老师观点收束成学生能理解的任务。",
            "language_style": "清晰、克制、结构化，优先给出下一步行动。",
            "default_intentions": ["summarize", "propose", "question"],
            "dataset_roles": ["course_shared", "lesson_plan", "student_record"],
        },
        {
            "agent_id": "ai_teacher_phonetics",
            "workflow_id": "ai_teacher_phonetics_workflow",
            "name": "发音老师",
            "role": "phonetics_teacher",
            "speaker_role": "phonetics_teacher",
            "persona": "负责听辨、发音、跟读和口语节奏训练，重点发现学生发音错误。",
            "language_style": "短句、可跟读、示范感强，避免长篇解释。",
            "default_intentions": ["teach", "correct", "supplement"],
            "dataset_roles": ["teacher_private", "course_shared", "textbook"],
        },
        {
            "agent_id": "ai_teacher_grammar",
            "workflow_id": "ai_teacher_grammar_workflow",
            "name": "表达老师",
            "role": "grammar_teacher",
            "speaker_role": "grammar_teacher",
            "persona": "负责句型、语法、表达准确性和可迁移语言结构。",
            "language_style": "准确、简明、带例句，优先解释可复用规则。",
            "default_intentions": ["teach", "correct", "challenge"],
            "dataset_roles": ["teacher_private", "course_shared", "textbook"],
        },
        {
            "agent_id": "ai_teacher_coach",
            "workflow_id": "ai_teacher_coach_workflow",
            "name": "学习教练",
            "role": "learning_coach",
            "speaker_role": "learning_coach",
            "persona": "负责学习反馈、情绪支持、练习安排和长期学习建议。",
            "language_style": "温和、具体、鼓励，但必须指出下一步可执行练习。",
            "default_intentions": ["support", "supplement", "defer"],
            "dataset_roles": ["course_shared", "student_record"],
        },
    ]

    REQUIRED_TEACHER_FIELDS = {
        "agent_id",
        "workflow_id",
        "name",
        "role",
        "speaker_role",
        "persona",
        "language_style",
        "default_intentions",
        "dataset_roles",
    }

    @classmethod
    def list_default_teachers(cls) -> list[dict[str, Any]]:
        return [cls.normalize_teacher(item) for item in cls.DEFAULT_TEACHERS]

    @classmethod
    def get_default_teacher(cls, agent_id: str) -> dict[str, Any] | None:
        for item in cls.list_default_teachers():
            if item["agent_id"] == agent_id:
                return item
        return None

    @classmethod
    def normalize_teacher(cls, teacher: dict[str, Any]) -> dict[str, Any]:
        item = copy.deepcopy(teacher)
        item["agent_id"] = str(item.get("agent_id") or "").strip()
        item["workflow_id"] = str(item.get("workflow_id") or item["agent_id"]).strip()
        item["default_intentions"] = cls._as_string_list(item.get("default_intentions"))
        item["dataset_roles"] = cls._as_string_list(item.get("dataset_roles"))
        item["output_schema"] = copy.deepcopy(cls.STANDARD_OUTPUT_SCHEMA)
        item["context_fields"] = [
            "meeting_topic",
            "meeting_goal",
            "student_last_utterance",
            "other_teachers_last_round",
            "round_index",
            "god_instruction",
            "current_task",
            "teacher_personality_summary",
            "language_style_constraints",
            "dataset_scope",
            "forbidden_content",
            "output_schema",
            "reply_to",
            "target_listener",
        ]
        return item

    @classmethod
    def validate_teacher(cls, teacher: dict[str, Any]) -> list[str]:
        errors = []
        if not isinstance(teacher, dict):
            return ["teacher must be an object"]
        normalized = cls.normalize_teacher(teacher)
        for field in sorted(cls.REQUIRED_TEACHER_FIELDS):
            if not normalized.get(field):
                errors.append(f"{field} is required")
        if not normalized["default_intentions"]:
            errors.append("default_intentions must contain at least one intention")
        if not normalized["dataset_roles"]:
            errors.append("dataset_roles must contain at least one role")
        return errors

    @classmethod
    def validate_registry(cls) -> dict[str, Any]:
        teachers = cls.list_default_teachers()
        errors = []
        seen_agent_ids = set()
        seen_workflow_ids = set()
        for teacher in teachers:
            errors.extend([f"{teacher.get('agent_id')}: {error}" for error in cls.validate_teacher(teacher)])
            agent_id = teacher["agent_id"]
            workflow_id = teacher["workflow_id"]
            if agent_id in seen_agent_ids:
                errors.append(f"duplicate agent_id: {agent_id}")
            if workflow_id in seen_workflow_ids:
                errors.append(f"duplicate workflow_id: {workflow_id}")
            seen_agent_ids.add(agent_id)
            seen_workflow_ids.add(workflow_id)
        return {"ok": not errors, "errors": errors, "total": len(teachers)}

    @classmethod
    def build_smoke_context(cls, teacher: dict[str, Any], query: str = "教学生读一句英文。") -> dict[str, Any]:
        normalized = cls.normalize_teacher(teacher)
        return {
            "meeting_topic": "零基础英语跟读训练",
            "meeting_goal": "让学生能准确跟读一句英文",
            "student_last_utterance": query,
            "other_teachers_last_round": [],
            "round_index": 1,
            "god_instruction": "请按自己的老师角色给出本轮建议。",
            "current_task": normalized["default_intentions"][0],
            "teacher_personality_summary": normalized["persona"],
            "language_style_constraints": normalized["language_style"],
            "dataset_scope": normalized["dataset_roles"],
            "forbidden_content": [],
            "output_schema": copy.deepcopy(cls.STANDARD_OUTPUT_SCHEMA),
            "reply_to": "",
            "target_listener": "student",
        }

    @staticmethod
    def _as_string_list(value: Any) -> list[str]:
        if isinstance(value, str):
            values = [value]
        elif isinstance(value, (list, tuple, set)):
            values = list(value)
        else:
            values = []
        result = []
        seen = set()
        for item in values:
            text = str(item or "").strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

