from pathlib import Path

from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_precondition_service import PreconditionChecker


def setup_function():
    AgentTaskModelService.reset()


def test_precondition_checker_missing_required_document_generates_find_file_repair():
    task = {
        "task_id": "task-edit",
        "inputs": {},
        "preconditions": [{"kind": "required_input", "field": "target_document"}],
        "status": AgentTaskStatus.PENDING.value,
    }

    result = PreconditionChecker.check(task)

    assert result["ok"] is False
    assert result["next_status"] == AgentTaskStatus.WAITING_INPUT.value
    assert result["condition_results"][0]["code"] == "missing_required_input"
    assert result["repair_tasks"][0]["task_type"] == "find_file"


def test_precondition_checker_missing_file_generates_find_file_repair(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    task = {
        "task_id": "task-read",
        "inputs": {"path": "missing.md"},
        "preconditions": [{"kind": "file_exists", "field": "path"}],
        "status": AgentTaskStatus.PENDING.value,
    }

    result = PreconditionChecker.check(task, roots=[root])

    assert result["ok"] is False
    assert result["condition_results"][0]["code"] == "path_not_found"
    assert result["repair_tasks"][0]["task_type"] == "find_file"


def test_precondition_checker_permission_denied_generates_permission_repair(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()
    outside = tmp_path / "outside.md"
    outside.write_text("# secret\n", encoding="utf-8")
    task = {
        "task_id": "task-read",
        "inputs": {"path": str(outside)},
        "preconditions": [{"kind": "permission_allowed", "field": "path"}],
        "status": AgentTaskStatus.PENDING.value,
    }

    result = PreconditionChecker.check(task, roots=[root])

    assert result["ok"] is False
    assert result["condition_results"][0]["code"] == "permission_denied"
    assert result["repair_tasks"][0]["task_type"] == "request_permission"


def test_precondition_checker_document_not_loaded_generates_read_document_repair():
    task = {
        "task_id": "task-outline",
        "inputs": {"selected_file": {"relative_path": "plan.md"}},
        "preconditions": [{"kind": "document_loaded", "field": "document"}],
        "status": AgentTaskStatus.PENDING.value,
    }

    result = PreconditionChecker.check(task)

    assert result["ok"] is False
    assert result["condition_results"][0]["code"] == "document_not_loaded"
    assert result["repair_tasks"][0]["task_type"] == "read_document"


def test_precondition_checker_requires_user_confirmation_for_high_risk_task():
    task = {
        "task_id": "task-write",
        "inputs": {},
        "preconditions": [{"kind": "user_confirmation_required"}],
        "status": AgentTaskStatus.PENDING.value,
        "risk_level": "high",
    }

    blocked = PreconditionChecker.check(task)
    ready = PreconditionChecker.check(task, runtime_context={"user_confirmed": True})

    assert blocked["ok"] is False
    assert blocked["repair_tasks"][0]["task_type"] == "request_user_confirmation"
    assert ready["ok"] is True


def test_precondition_checker_marks_pending_task_ready_when_conditions_satisfied():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question")
    upstream = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="find_file",
        title="Find file",
        status=AgentTaskStatus.COMPLETED.value,
    )
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_document",
        title="Read file",
        preconditions=[{"kind": "upstream_task_completed", "task_id": upstream["task_id"]}],
        status=AgentTaskStatus.PENDING.value,
    )

    result = PreconditionChecker.check_model_task(task["task_id"], mark_ready=True)

    assert result["ok"] is True
    assert result["ready_transition"]["to_status"] == AgentTaskStatus.READY.value
    assert AgentTaskModelService.get_task(task["task_id"])["status"] == AgentTaskStatus.READY.value
