#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

PYTHON_BIN="${PYTHON_BIN:-}"
if [[ -z "$PYTHON_BIN" ]]; then
  if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
  else
    PYTHON_BIN="python"
  fi
fi

"$PYTHON_BIN" -m pytest -q \
  test/unit_test/test_agent_artifact_service.py \
  test/unit_test/test_agent_run_executor_service.py \
  test/unit_test/test_agent_run_queue_service.py \
  test/unit_test/test_agent_meeting_memory_service.py \
  test/unit_test/test_agent_meeting_scheduler_service.py \
  test/unit_test/test_agent_run_trace_summary.py \
  test/unit_test/test_agent_component_contract.py \
  test/unit_test/test_agent_file_asset_contract.py \
  test/unit_test/test_agent_file_parser.py \
  test/unit_test/test_agent_excel_processor.py \
  test/unit_test/test_sql_guard.py \
  test/unit_test/test_agent_validation_service.py \
  test/unit_test/test_agent_builtin_templates.py \
  test/unit_test/test_agent_message_downloads.py

"$PYTHON_BIN" -m py_compile \
  api/apps/restful_apis/agent_api.py \
  api/db/services/agent_run_queue_service.py \
  api/db/services/agent_run_executor_service.py \
  api/db/services/agent_meeting_memory_service.py \
  api/db/services/agent_meeting_scheduler_service.py \
  rag/svr/agent_run_executor.py
