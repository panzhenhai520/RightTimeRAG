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

import re
from typing import Any


class AgentSecurityService:
    """Small security utilities for public Agent boundaries."""

    PROMPT_INJECTION_PATTERNS = [
        r"ignore\s+(all\s+)?(previous|above|system)\s+instructions",
        r"reveal\s+(the\s+)?(system\s+)?prompt",
        r"show\s+(me\s+)?(the\s+)?(hidden|system|developer)\s+(prompt|instruction)",
        r"泄露.*(系统|隐藏|开发者).*(提示|指令)",
        r"(忽略|无视).*(之前|上面|系统).*(指令|提示)",
        r"(显示|输出|告诉我).*(系统|隐藏|开发者).*(提示词|指令)",
        r"不要遵守.*(知识库|系统|规则)",
    ]

    @classmethod
    def detect_prompt_injection(cls, value: Any) -> list[dict[str, str]]:
        text = cls._to_text(value)
        if not text:
            return []
        risks = []
        for pattern in cls.PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, text, flags=re.IGNORECASE | re.DOTALL):
                risks.append(
                    {
                        "code": "PROMPT_INJECTION_RISK",
                        "pattern": pattern,
                        "message": "Potential prompt-injection instruction detected.",
                    }
                )
        return risks

    @classmethod
    def redact_sensitive_text(cls, value: Any, max_chars: int = 500) -> str:
        text = cls._to_text(value)
        text = re.sub(r"(?i)(api[_-]?key|authorization|password|secret|token)\s*[:=]\s*\S+", r"\1=***", text)
        if len(text) > max_chars:
            return text[:max_chars] + "..."
        return text

    @staticmethod
    def _to_text(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, str):
            return value
        if isinstance(value, dict):
            return " ".join(AgentSecurityService._to_text(item) for item in value.values())
        if isinstance(value, (list, tuple, set)):
            return " ".join(AgentSecurityService._to_text(item) for item in value)
        return str(value)

