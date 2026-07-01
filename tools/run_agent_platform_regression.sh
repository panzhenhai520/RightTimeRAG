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
  test/unit_test/test_agent_document_write_coordinator_service.py \
  test/unit_test/test_agent_meeting_memory_service.py \
  test/unit_test/test_agent_meeting_scheduler_service.py \
  test/unit_test/test_agent_teacher_registry_service.py \
  test/unit_test/test_agent_turn_context_service.py \
  test/unit_test/test_agent_security_service.py \
  test/unit_test/test_agent_task_model_service.py \
  test/unit_test/test_agent_task_state_service.py \
  test/unit_test/test_agent_task_stack_service.py \
  test/unit_test/test_agent_goal_intent_service.py \
  test/unit_test/test_agent_goal_intent_examples.py \
  test/unit_test/test_agent_task_intent_nodes.py \
  test/unit_test/test_agent_task_context_service.py \
  test/unit_test/test_agent_task_context_nodes.py \
  test/unit_test/test_agent_task_planner_service.py \
  test/unit_test/test_agent_atomic_task_refiner.py \
  test/unit_test/test_agent_task_planner_nodes.py \
  test/unit_test/test_agent_task_precondition_service.py \
  test/unit_test/test_agent_dependency_resolver.py \
  test/unit_test/test_agent_task_precondition_nodes.py \
  test/unit_test/test_agent_task_execution_service.py \
  test/unit_test/test_agent_task_resume_service.py \
  test/unit_test/test_agent_task_execution_nodes.py \
  test/unit_test/test_agent_task_verifier_service.py \
  test/unit_test/test_agent_task_verifier_nodes.py \
  test/unit_test/test_agent_task_taxonomy_service.py \
  test/unit_test/test_agent_task_feedback_service.py \
  test/unit_test/test_agent_task_planning_nodes.py \
  test/unit_test/test_agent_task_approval_service.py \
  test/unit_test/test_agent_task_security_policy.py \
  test/integration/test_agent_codex_like_document_edit_flow.py \
  test/integration/test_agent_task_recovery_flow.py \
  test/unit_test/test_agent_task_budget_service.py \
  test/unit_test/test_agent_task_loop_guard.py \
  test/unit_test/test_agent_run_trace_summary.py \
  test/unit_test/test_agent_component_contract.py \
  test/unit_test/test_agent_file_asset_contract.py \
  test/unit_test/test_agent_file_parser.py \
  test/unit_test/test_workspace_file_service.py \
  test/unit_test/test_agent_workspace_file_nodes.py \
  test/unit_test/test_document_normalize_service.py \
  test/unit_test/test_agent_document_normalizer_node.py \
  test/unit_test/test_document_structure_advisor.py \
  test/unit_test/test_content_placement_planner.py \
  test/unit_test/test_agent_document_structure_nodes.py \
  test/unit_test/test_document_extract_service.py \
  test/unit_test/test_agent_document_extractors.py \
  test/unit_test/test_document_compare_service.py \
  test/unit_test/test_agent_document_compare_nodes.py \
  test/unit_test/test_document_compare_report_service.py \
  test/unit_test/test_agent_document_compare_report_node.py \
  test/unit_test/test_agent_compliance_nodes.py \
  test/unit_test/test_agent_excel_processor.py \
  test/unit_test/test_agent_scoped_db.py \
  test/unit_test/test_agent_teaching_nodes.py \
  test/unit_test/test_agent_voice_nodes.py \
  test/unit_test/test_agent_external_review.py \
  test/unit_test/test_agent_multi_agent_nodes.py \
  test/unit_test/test_agent_output_artifacts.py \
  test/unit_test/test_sql_guard.py \
  test/unit_test/test_agent_validation_service.py \
  test/unit_test/test_agent_builtin_templates.py \
  test/unit_test/test_agent_message_downloads.py \
  test/unit_test/test_agent_public_response_service.py \
  test/unit_test/test_agent_public_dataset_scope.py

"$PYTHON_BIN" -m py_compile \
  api/apps/restful_apis/agent_api.py \
  api/apps/restful_apis/agent_task_api.py \
  api/apps/restful_apis/workspace_file_api.py \
  api/apps/restful_apis/document_normalize_api.py \
  api/apps/restful_apis/document_extract_api.py \
  api/apps/restful_apis/document_compare_api.py \
  api/apps/restful_apis/document_compare_report_api.py \
  api/db/services/agent_public_response_service.py \
  api/db/services/agent_run_queue_service.py \
  api/db/services/agent_run_executor_service.py \
  api/db/services/agent_document_write_coordinator_service.py \
  api/db/services/agent_meeting_memory_service.py \
  api/db/services/agent_meeting_scheduler_service.py \
  api/db/services/agent_teacher_registry_service.py \
  api/db/services/agent_turn_context_service.py \
  api/db/services/agent_security_service.py \
  api/db/services/agent_task_model_service.py \
  api/db/services/agent_task_audit_service.py \
  api/db/services/agent_task_state_service.py \
  api/db/services/agent_task_stack_service.py \
  api/db/services/agent_goal_intent_service.py \
  api/db/services/agent_task_context_service.py \
  api/db/services/agent_task_planner_service.py \
  api/db/services/agent_task_precondition_service.py \
  api/db/services/agent_task_execution_service.py \
  api/db/services/agent_task_verifier_service.py \
  api/db/services/agent_task_taxonomy_service.py \
  api/db/services/agent_task_execution_report_service.py \
  api/db/services/agent_task_approval_service.py \
  api/db/services/agent_codex_like_flow_service.py \
  api/db/services/agent_task_budget_service.py \
  api/db/services/workspace_file_service.py \
  api/db/services/document_normalize_service.py \
  api/db/services/document_structure_advisor_service.py \
  api/db/services/document_extract_service.py \
  api/db/services/document_compare_service.py \
  api/db/services/document_compare_report_service.py \
  agent/canvas.py \
  agent/component/workspace_file.py \
  agent/component/document_normalizer.py \
  agent/component/document_structure.py \
  agent/component/document_extractors.py \
  agent/component/document_compare.py \
  agent/component/document_compare_report.py \
  agent/component/task_intent.py \
  agent/component/task_context.py \
  agent/component/task_planner.py \
  agent/component/task_precondition.py \
  agent/component/task_execution.py \
  agent/component/task_verifier.py \
  agent/component/task_execution_report.py \
  agent/tools/retrieval.py \
  rag/svr/agent_run_executor.py
