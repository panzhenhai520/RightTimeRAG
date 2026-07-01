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

import hashlib
import json
from typing import Any

from api.db.services.agent_security_service import AgentSecurityService


class AgentTurnContextService:
    """Normalize external meeting context into AITeacherTurnContext."""

    CONTEXT_FIELDS = [
        "meeting_id",
        "turn_id",
        "ai_teacher_id",
        "meeting_topic",
        "meeting_goal",
        "student_last_utterance",
        "other_teachers_last_round",
        "round_index",
        "speaker_role",
        "target_audience",
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
    LIST_FIELDS = {"other_teachers_last_round", "dataset_scope", "forbidden_content"}
    DICT_FIELDS = {"output_schema"}
    CONSTRAINT_FIELDS = {
        "god_instruction",
        "current_task",
        "language_style_constraints",
        "forbidden_content",
        "output_schema",
        "reply_to",
        "target_listener",
    }
    ALLOWED_TARGET_PREFIXES = {"teacher:"}
    ALLOWED_TARGETS = {"", "student", "all", "god"}

    @classmethod
    def normalize_request(
        cls,
        *,
        req: dict[str, Any] | None = None,
        inputs: dict[str, Any] | None = None,
        external_context: Any = None,
        query: str = "",
        agent_id: str = "",
    ) -> dict[str, Any]:
        req = req if isinstance(req, dict) else {}
        inputs = inputs if isinstance(inputs, dict) else {}
        external = cls._parse_context(external_context if external_context is not None else req.get("external_context"))
        context_value = cls._parse_context(req.get("context"))
        input_context = cls._parse_context(inputs.get("ai_teacher_turn_context") or inputs.get("context"))

        merged: dict[str, Any] = {}
        for source in (external, context_value, input_context, req, inputs):
            if isinstance(source, dict):
                for field in cls.CONTEXT_FIELDS:
                    if field in source and source[field] not in (None, ""):
                        merged[field] = source[field]

        if agent_id and not merged.get("ai_teacher_id"):
            merged["ai_teacher_id"] = agent_id
        if query and not merged.get("student_last_utterance"):
            merged["student_last_utterance"] = query

        normalized = {}
        for field in cls.CONTEXT_FIELDS:
            value = merged.get(field)
            if field in cls.LIST_FIELDS:
                normalized[field] = cls._as_list(value)
            elif field in cls.DICT_FIELDS:
                normalized[field] = value if isinstance(value, dict) else {}
            elif field == "round_index":
                normalized[field] = cls._as_int(value)
            else:
                normalized[field] = "" if value is None else str(value).strip()

        issues = cls.validate(normalized)
        issues.extend(cls.detect_prompt_injection(normalized))
        context_hash = cls.hash_payload(normalized)
        constraint_hash = cls.hash_payload({field: normalized.get(field) for field in cls.CONSTRAINT_FIELDS})
        return {
            "context": normalized,
            "context_hash": context_hash,
            "constraint_hash": constraint_hash,
            "issues": issues,
            "context_missing": [field for field in ("meeting_topic", "meeting_goal", "current_task") if not normalized.get(field)],
        }

    @classmethod
    def inject_inputs(cls, inputs: dict[str, Any] | None, context_package: dict[str, Any]) -> dict[str, Any]:
        result = dict(inputs or {})
        result["ai_teacher_turn_context"] = context_package["context"]
        result["ai_teacher_context_hash"] = context_package["context_hash"]
        result["ai_teacher_constraint_hash"] = context_package["constraint_hash"]
        result["ai_teacher_context_issues"] = context_package["issues"]
        result["ai_teacher_context_missing"] = context_package["context_missing"]
        return result

    @classmethod
    def validate(cls, context: dict[str, Any]) -> list[dict[str, str]]:
        issues = []
        target = str(context.get("target_listener") or "").strip()
        reply_to = str(context.get("reply_to") or "").strip()
        if target and not cls.is_valid_target(target):
            issues.append({"code": "INVALID_TARGET", "field": "target_listener", "message": f"Invalid target_listener: {target}"})
        if reply_to and not cls.is_valid_target(reply_to):
            issues.append({"code": "INVALID_TARGET", "field": "reply_to", "message": f"Invalid reply_to: {reply_to}"})
        return issues

    @classmethod
    def detect_prompt_injection(cls, context: dict[str, Any]) -> list[dict[str, str]]:
        risks = []
        for field in ("student_last_utterance", "god_instruction", "current_task"):
            for risk in AgentSecurityService.detect_prompt_injection(context.get(field)):
                risks.append({**risk, "field": field})
        for risk in AgentSecurityService.detect_prompt_injection(context.get("other_teachers_last_round")):
            risks.append({**risk, "field": "other_teachers_last_round"})
        return risks

    @classmethod
    def is_valid_target(cls, value: str) -> bool:
        value = str(value or "").strip()
        if value in cls.ALLOWED_TARGETS:
            return True
        return any(value.startswith(prefix) and len(value) > len(prefix) for prefix in cls.ALLOWED_TARGET_PREFIXES)

    @staticmethod
    def hash_payload(payload: Any) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _parse_context(cls, value: Any) -> Any:
        if isinstance(value, str):
            text = value.strip()
            if not text:
                return {}
            try:
                parsed = json.loads(text)
            except Exception:
                return {"student_last_utterance": text}
            return parsed
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _as_list(value: Any) -> list[Any]:
        if value is None or value == "":
            return []
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
                if isinstance(parsed, list):
                    return parsed
            except Exception:
                return [value]
            return [value]
        if isinstance(value, (list, tuple, set)):
            return list(value)
        return [value]

    @staticmethod
    def _as_int(value: Any) -> int:
        try:
            return int(value or 0)
        except Exception:
            return 0
