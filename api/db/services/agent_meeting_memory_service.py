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

import json
import logging
import time
from typing import Any

from rag.utils.redis_conn import REDIS_CONN


class AgentMeetingMemoryService:
    """Meeting-scoped memory storage for multi-agent orchestration.

    The namespace is deliberately explicit:
    - shared memory: tenant + meeting
    - agent memory: tenant + meeting + agent

    This prevents four agents in the same meeting turn from overwriting each
    other's role-specific memory while still allowing a shared meeting context.
    """

    TTL_SECONDS = 7 * 24 * 60 * 60
    MAX_ITEMS = 80

    @classmethod
    def _shared_key(cls, tenant_id: str, meeting_id: str) -> str:
        return f"agent_meeting:{tenant_id}:{meeting_id}:shared"

    @classmethod
    def _agent_key(cls, tenant_id: str, meeting_id: str, agent_id: str) -> str:
        return f"agent_meeting:{tenant_id}:{meeting_id}:agent:{agent_id}"

    @staticmethod
    def _load_json(key: str, default: Any):
        raw = REDIS_CONN.get(key)
        if not raw:
            return default
        try:
            return json.loads(raw)
        except Exception:
            logging.warning("AgentMeetingMemoryService failed to parse redis payload. key=%s", key)
            return default

    @classmethod
    def _append(cls, key: str, item: dict[str, Any]) -> dict[str, Any]:
        items = cls._load_json(key, [])
        if not isinstance(items, list):
            items = []
        record = {
            "created_at": time.time(),
            **item,
        }
        items.append(record)
        items = items[-cls.MAX_ITEMS :]
        REDIS_CONN.set_obj(key, items, cls.TTL_SECONDS)
        return record

    @classmethod
    def append_shared(
        cls,
        tenant_id: str,
        meeting_id: str,
        *,
        turn_id: str,
        content: str,
        source: str = "system",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cls._append(
            cls._shared_key(tenant_id, meeting_id),
            {
                "scope": "shared",
                "turn_id": turn_id,
                "source": source,
                "content": content or "",
                "metadata": metadata or {},
            },
        )

    @classmethod
    def append_agent(
        cls,
        tenant_id: str,
        meeting_id: str,
        agent_id: str,
        *,
        turn_id: str,
        content: str,
        run_id: str | None = None,
        role: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return cls._append(
            cls._agent_key(tenant_id, meeting_id, agent_id),
            {
                "scope": "agent",
                "turn_id": turn_id,
                "agent_id": agent_id,
                "run_id": run_id,
                "role": role,
                "content": content or "",
                "metadata": metadata or {},
            },
        )

    @classmethod
    def get_context(
        cls,
        tenant_id: str,
        meeting_id: str,
        agent_id: str,
        *,
        limit: int = 12,
    ) -> dict[str, list[dict[str, Any]]]:
        limit = max(1, min(int(limit or 12), cls.MAX_ITEMS))
        shared = cls._load_json(cls._shared_key(tenant_id, meeting_id), [])
        agent = cls._load_json(cls._agent_key(tenant_id, meeting_id, agent_id), [])
        if not isinstance(shared, list):
            shared = []
        if not isinstance(agent, list):
            agent = []
        return {
            "shared": shared[-limit:],
            "agent": agent[-limit:],
        }

    @classmethod
    def build_injection(
        cls,
        *,
        meeting_id: str,
        turn_id: str,
        agent_id: str,
        role: str,
        query: str,
        shared_memory: list[dict[str, Any]] | None = None,
        agent_memory: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        shared_memory = shared_memory or []
        agent_memory = agent_memory or []
        return {
            "meeting_id": meeting_id,
            "turn_id": turn_id,
            "agent_id": agent_id,
            "role": role or "",
            "query": query or "",
            "shared_memory": shared_memory,
            "agent_memory": agent_memory,
            "prompt": cls._format_prompt(
                meeting_id=meeting_id,
                turn_id=turn_id,
                agent_id=agent_id,
                role=role,
                shared_memory=shared_memory,
                agent_memory=agent_memory,
            ),
        }

    @staticmethod
    def _format_memory_lines(items: list[dict[str, Any]]) -> str:
        lines = []
        for item in items:
            turn_id = item.get("turn_id") or ""
            source = item.get("source") or item.get("role") or item.get("agent_id") or "memory"
            content = str(item.get("content") or "").strip()
            if content:
                lines.append(f"- [{turn_id}] {source}: {content}")
        return "\n".join(lines) if lines else "- none"

    @classmethod
    def _format_prompt(
        cls,
        *,
        meeting_id: str,
        turn_id: str,
        agent_id: str,
        role: str,
        shared_memory: list[dict[str, Any]],
        agent_memory: list[dict[str, Any]],
    ) -> str:
        return (
            f"Meeting: {meeting_id}\n"
            f"Turn: {turn_id}\n"
            f"Agent: {agent_id}\n"
            f"Role: {role or 'unspecified'}\n\n"
            "Shared meeting memory:\n"
            f"{cls._format_memory_lines(shared_memory)}\n\n"
            "This agent's private memory:\n"
            f"{cls._format_memory_lines(agent_memory)}"
        )
