import pytest

from api.db.services.agent_task_model_service import AgentTaskError, AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_state_service import AgentTaskStateService


def setup_function():
    AgentTaskModelService.reset()


def make_task():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="edit_document")
    return AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="find_file", title="找文件")


def test_agent_task_state_service_allows_valid_flow_and_audits():
    task = make_task()

    assert AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.READY.value)["changed"] is True
    assert AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.RUNNING.value)["from_status"] == "ready"
    assert AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.VERIFIED.value)["to_status"] == "verified"
    assert AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.COMPLETED.value)["to_status"] == "completed"

    stored = AgentTaskModelService.get_task(task["task_id"])
    audit = AgentTaskModelService.list_audit(task_id=task["task_id"])
    assert stored["status"] == "completed"
    assert any(item["action"] == "task_status_transition" for item in audit)


def test_agent_task_state_service_rejects_invalid_transition():
    task = make_task()
    AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.READY.value)
    AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.RUNNING.value)
    AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.VERIFIED.value)
    AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.COMPLETED.value)

    with pytest.raises(AgentTaskError) as exc:
        AgentTaskStateService.transition(task["task_id"], AgentTaskStatus.RUNNING.value)

    assert exc.value.code == "INVALID_TASK_STATUS_TRANSITION"
