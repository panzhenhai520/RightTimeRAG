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

import logging
from collections.abc import Callable
from typing import Any

from api.db.services.agent_run_queue_service import AgentRunQueueService
from api.db.services.agent_run_service import AgentRunService


class AgentRunExecutorService:
    """Small worker boundary for queued Agent runs.

    The actual Canvas execution function is injected so this service can be
    tested without importing the REST API module or constructing a full canvas.
    """

    @classmethod
    def run_one(
        cls,
        execute_payload: Callable[[dict[str, Any]], Any],
        consumer_name: str | None = None,
        msg_id: bytes | str = b">",
    ) -> bool:
        redis_msg = AgentRunQueueService.consume(consumer_name=consumer_name, msg_id=msg_id)
        if not redis_msg:
            return False

        payload = redis_msg.get_message()
        AgentRunQueueService.validate_payload(payload)
        tenant_id = str(payload["tenant_id"])
        run_id = str(payload["run_id"])
        AgentRunService.mark_running(tenant_id, run_id)

        try:
            execute_payload(payload)
        except Exception as exc:
            logging.exception("Queued agent run failed. run_id=%s", run_id)
            AgentRunService.fail(tenant_id, run_id, str(exc))
            redis_msg.ack()
            return False

        redis_msg.ack()
        return True
