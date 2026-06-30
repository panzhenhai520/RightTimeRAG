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

import argparse
import asyncio
import logging
import os
import signal
import socket
import time

# LiteLLM may try to fetch model cost metadata during import. Agent workers
# should be able to start in offline/private deployments.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")

from api.apps.restful_apis.agent_api import execute_queued_agent_run
from api.db.db_models import close_connection
from api.db.services.agent_run_executor_service import AgentRunExecutorService
from common.config_utils import show_configs
from common.log_utils import init_root_logger


_STOP_REQUESTED = False


def _request_stop(_signum, _frame):
    global _STOP_REQUESTED
    _STOP_REQUESTED = True


def execute_payload(payload: dict):
    return asyncio.run(execute_queued_agent_run(payload))


def run_loop(consumer_name: str, idle_sleep: float = 1.0, once: bool = False) -> int:
    logging.info("Agent run executor started. consumer=%s once=%s", consumer_name, once)
    recovering_pending = True
    while not _STOP_REQUESTED:
        try:
            consumed = AgentRunExecutorService.run_one(
                execute_payload,
                consumer_name=consumer_name,
                msg_id="0" if recovering_pending else b">",
            )
        except Exception:
            logging.exception("Agent run executor iteration failed.")
            consumed = False
        finally:
            close_connection()

        if once:
            return 0
        if recovering_pending and not consumed:
            recovering_pending = False
            continue
        if not consumed:
            time.sleep(idle_sleep)

    logging.info("Agent run executor stopped. consumer=%s", consumer_name)
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Consume queued RAGFlow Agent runs.")
    parser.add_argument(
        "consumer",
        nargs="?",
        default=f"agent_run_executor_{socket.gethostname()}",
        help="Redis consumer name.",
    )
    parser.add_argument("--once", action="store_true", help="Consume at most one queued run and exit.")
    parser.add_argument("--idle-sleep", type=float, default=1.0, help="Seconds to sleep when the queue is idle.")
    args = parser.parse_args(argv)

    init_root_logger("agent_run_executor")
    show_configs()
    signal.signal(signal.SIGINT, _request_stop)
    signal.signal(signal.SIGTERM, _request_stop)
    return run_loop(args.consumer, idle_sleep=args.idle_sleep, once=args.once)


if __name__ == "__main__":
    raise SystemExit(main())
