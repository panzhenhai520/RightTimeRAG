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

from typing import Any, Callable

from api.db.services.agent_meeting_memory_service import AgentMeetingMemoryService
from api.db.services.agent_run_queue_service import AgentRunQueueService
from api.db.services.agent_run_service import AgentRunService, AgentRunStatus
from common.misc_utils import get_uuid


class AgentMeetingSchedulerService:
    """Fan-out/fan-in boundary for meeting-scoped multi-agent runs."""

    MAX_AGENTS_PER_TURN = 8

    @classmethod
    def normalize_agents(cls, agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
        if not isinstance(agents, list) or not agents:
            raise ValueError("agents must contain at least one agent.")
        if len(agents) > cls.MAX_AGENTS_PER_TURN:
            raise ValueError(f"agents cannot exceed {cls.MAX_AGENTS_PER_TURN} per meeting turn.")

        normalized = []
        seen = set()
        for index, item in enumerate(agents):
            if isinstance(item, str):
                item = {"agent_id": item}
            if not isinstance(item, dict):
                raise ValueError(f"agents[{index}] must be an object.")
            agent_id = str(item.get("agent_id") or "").strip()
            if not agent_id:
                raise ValueError(f"agents[{index}].agent_id is required.")
            if agent_id in seen:
                raise ValueError(f"duplicate agent_id in meeting turn: {agent_id}")
            seen.add(agent_id)
            normalized.append(
                {
                    "agent_id": agent_id,
                    "workflow_id": str(item.get("workflow_id") or agent_id).strip(),
                    "session_id": str(item.get("session_id") or "").strip(),
                    "message_id": str(item.get("message_id") or "").strip(),
                    "role": str(item.get("role") or item.get("name") or "").strip(),
                    "memory": item.get("memory") if isinstance(item.get("memory"), list) else [],
                    "inputs": item.get("inputs") if isinstance(item.get("inputs"), dict) else {},
                    "deadline_ms": item.get("deadline_ms"),
                    "chat_template_kwargs": item.get("chat_template_kwargs"),
                    "custom_header": str(item.get("custom_header") or ""),
                }
            )
        return normalized

    @classmethod
    def build_dispatch_payloads(
        cls,
        *,
        tenant_id: str,
        meeting_id: str,
        turn_id: str,
        query: str,
        agents: list[dict[str, Any]],
        files: list[dict[str, Any]] | None = None,
        shared_context: str = "",
        shared_memory: list[dict[str, Any]] | None = None,
        base_inputs: dict[str, Any] | None = None,
        user_id: str | None = None,
        release: bool = True,
        return_trace: bool = True,
        uuid_factory: Callable[[], str] = get_uuid,
    ) -> list[dict[str, Any]]:
        tenant_id = str(tenant_id)
        meeting_id = str(meeting_id or uuid_factory())
        turn_id = str(turn_id or uuid_factory())
        normalized_agents = cls.normalize_agents(agents)
        shared_memory = shared_memory or []
        base_inputs = base_inputs or {}
        files = files or []

        payloads = []
        for spec in normalized_agents:
            agent_id = spec["agent_id"]
            session_id = spec["session_id"] or uuid_factory()
            message_id = spec["message_id"] or uuid_factory()
            run_id = uuid_factory()
            persisted_context = AgentMeetingMemoryService.get_context(tenant_id, meeting_id, agent_id)
            agent_memory = [*persisted_context["agent"], *spec["memory"]]
            merged_shared_memory = [*persisted_context["shared"], *shared_memory]
            injection = AgentMeetingMemoryService.build_injection(
                meeting_id=meeting_id,
                turn_id=turn_id,
                agent_id=agent_id,
                role=spec["role"],
                query=query,
                shared_memory=merged_shared_memory,
                agent_memory=agent_memory,
            )
            meeting_inputs = {
                **base_inputs,
                **spec["inputs"],
                "meeting_id": meeting_id,
                "meeting_turn_id": turn_id,
                "meeting_agent_id": agent_id,
                "meeting_agent_role": spec["role"],
                "meeting_context": shared_context,
                "meeting_memory": injection,
                "meeting_memory_prompt": injection["prompt"],
            }
            metadata = {
                "meeting_id": meeting_id,
                "turn_id": turn_id,
                "agent_id": agent_id,
                "workflow_id": spec.get("workflow_id") or agent_id,
                "role": spec["role"],
                "deadline_ms": spec.get("deadline_ms"),
                "memory_namespace": {
                    "shared": f"{tenant_id}:{meeting_id}:shared",
                    "agent": f"{tenant_id}:{meeting_id}:{agent_id}",
                },
            }
            payload = AgentRunQueueService.build_payload(
                run_id=run_id,
                tenant_id=tenant_id,
                agent_id=agent_id,
                workflow_id=spec.get("workflow_id") or agent_id,
                session_id=session_id,
                message_id=message_id,
                query=query,
                files=files,
                inputs=meeting_inputs,
                user_id=user_id or tenant_id,
                release=release,
                return_trace=return_trace,
                custom_header=spec["custom_header"],
                chat_template_kwargs=spec["chat_template_kwargs"],
                deadline_ms=spec.get("deadline_ms"),
                metadata=metadata,
            )
            payloads.append(payload)
        return payloads

    @classmethod
    def start_parallel_runs(
        cls,
        *,
        tenant_id: str,
        meeting_id: str,
        turn_id: str,
        query: str,
        agents: list[dict[str, Any]],
        files: list[dict[str, Any]] | None = None,
        shared_context: str = "",
        shared_memory: list[dict[str, Any]] | None = None,
        base_inputs: dict[str, Any] | None = None,
        user_id: str | None = None,
        release: bool = True,
        return_trace: bool = True,
        enqueue: bool = True,
        uuid_factory: Callable[[], str] = get_uuid,
    ) -> dict[str, Any]:
        payloads = cls.build_dispatch_payloads(
            tenant_id=tenant_id,
            meeting_id=meeting_id,
            turn_id=turn_id,
            query=query,
            agents=agents,
            files=files,
            shared_context=shared_context,
            shared_memory=shared_memory,
            base_inputs=base_inputs,
            user_id=user_id,
            release=release,
            return_trace=return_trace,
            uuid_factory=uuid_factory,
        )

        runs = []
        for payload in payloads:
            metadata = payload.get("metadata") or {}
            AgentRunService.start(
                payload["tenant_id"],
                payload["run_id"],
                payload["agent_id"],
                payload["session_id"],
                payload["message_id"],
                "",
                payload["query"],
                status=AgentRunStatus.QUEUED,
                mode="meeting_queue",
                metadata=metadata,
            )
            if enqueue and not AgentRunQueueService.enqueue(payload):
                AgentRunService.fail(payload["tenant_id"], payload["run_id"], "Failed to enqueue meeting Agent run.")
                runs.append(
                    {
                        "run_id": payload["run_id"],
                        "agent_id": payload["agent_id"],
                        "session_id": payload["session_id"],
                        "message_id": payload["message_id"],
                        "status": AgentRunStatus.FAILED,
                        "queued": False,
                        "metadata": metadata,
                    }
                )
                continue
            runs.append(
                {
                    "run_id": payload["run_id"],
                    "agent_id": payload["agent_id"],
                    "session_id": payload["session_id"],
                    "message_id": payload["message_id"],
                    "status": AgentRunStatus.QUEUED,
                    "queued": bool(enqueue),
                    "metadata": metadata,
                }
            )

        return {
            "meeting_id": payloads[0]["metadata"]["meeting_id"] if payloads else meeting_id,
            "turn_id": payloads[0]["metadata"]["turn_id"] if payloads else turn_id,
            "runs": runs,
        }

    @classmethod
    def summarize_turn_results(cls, *, tenant_id: str, run_ids: list[str]) -> dict[str, Any]:
        results = []
        for run_id in run_ids:
            state = AgentRunService.get_state(tenant_id, run_id)
            trace = AgentRunService.get_trace(tenant_id, run_id) if state else None
            results.append(
                {
                    "run_id": run_id,
                    "agent_id": (state or {}).get("agent_id"),
                    "status": (state or {}).get("status"),
                    "metadata": (state or {}).get("metadata") or {},
                    "progress": (state or {}).get("progress") or {},
                    "downloads": (trace or {}).get("downloads", []),
                    "errors": (trace or {}).get("errors", []),
                    "messages": (trace or {}).get("messages", []),
                }
            )
        return {"runs": results}
