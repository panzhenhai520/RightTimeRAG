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
import os
import socket
from typing import Any

from rag.utils.redis_conn import REDIS_CONN


class AgentRunQueueService:
    """Queue boundary for durable Agent runs.

    This service deliberately contains no Canvas execution logic. The API layer
    can enqueue payloads here, and a dedicated agent executor can consume the
    same payload shape later. Keeping the boundary small makes the migration from
    in-process background tasks to Redis Stream workers testable and reversible.
    """

    QUEUE_NAME = os.environ.get("AGENT_RUN_QUEUE_NAME", "agent_run_queue")
    GROUP_NAME = os.environ.get("AGENT_RUN_QUEUE_GROUP", "agent_run_executor")

    REQUIRED_FIELDS = {
        "run_id",
        "tenant_id",
        "agent_id",
        "session_id",
        "message_id",
        "query",
    }

    @classmethod
    def build_payload(
        cls,
        *,
        run_id: str,
        tenant_id: str,
        agent_id: str,
        session_id: str,
        message_id: str,
        query: str,
        workflow_id: str | None = None,
        files: list[dict] | None = None,
        inputs: dict[str, Any] | None = None,
        user_id: str | None = None,
        release: bool = False,
        return_trace: bool = False,
        custom_header: str = "",
        chat_template_kwargs: dict[str, Any] | None = None,
        external_context: str | None = None,
        request_dataset_ids: list[str] | None = None,
        deadline_ms: int | float | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return {
            "schema_version": 1,
            "run_id": run_id,
            "tenant_id": str(tenant_id),
            "agent_id": agent_id,
            "workflow_id": workflow_id or agent_id,
            "session_id": session_id,
            "message_id": message_id,
            "query": query or "",
            "files": files or [],
            "inputs": inputs or {},
            "user_id": str(user_id or tenant_id),
            "release": bool(release),
            "return_trace": bool(return_trace),
            "custom_header": custom_header or "",
            "chat_template_kwargs": chat_template_kwargs,
            "external_context": external_context or "",
            "request_dataset_ids": request_dataset_ids or [],
            "deadline_ms": deadline_ms,
            "metadata": metadata or {},
        }

    @classmethod
    def validate_payload(cls, payload: dict[str, Any]) -> None:
        if not isinstance(payload, dict):
            raise ValueError("Agent run queue payload must be an object.")
        missing = sorted(field for field in cls.REQUIRED_FIELDS if not payload.get(field))
        if missing:
            raise ValueError(f"Agent run queue payload missing required fields: {', '.join(missing)}")
        try:
            json.dumps(payload, ensure_ascii=False)
        except Exception as exc:
            raise ValueError(f"Agent run queue payload must be JSON serializable: {exc}") from exc

    @classmethod
    def enqueue(cls, payload: dict[str, Any]) -> bool:
        cls.validate_payload(payload)
        ok = REDIS_CONN.queue_product(cls.QUEUE_NAME, payload)
        if not ok:
            logging.error("Failed to enqueue agent run. run_id=%s", payload.get("run_id"))
        return bool(ok)

    @classmethod
    def consume(cls, consumer_name: str | None = None, msg_id: bytes | str = b">"):
        consumer = consumer_name or f"agent_executor_{socket.gethostname()}"
        return REDIS_CONN.queue_consumer(cls.QUEUE_NAME, cls.GROUP_NAME, consumer, msg_id)
