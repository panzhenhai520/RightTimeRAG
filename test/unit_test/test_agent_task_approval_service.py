import pytest

from api.db.services.agent_task_approval_service import (
    AgentTaskApprovalError,
    AgentTaskApprovalService,
    AgentTaskSecurityPolicy,
)
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus


def setup_function():
    AgentTaskModelService.reset()
    AgentTaskApprovalService.reset()


def test_approval_service_requires_confirmation_for_write_task():
    goal = AgentTaskModelService.create_goal(raw_request="写文件", goal_type="edit_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="write_file",
        title="Write file",
        risk_level="high",
        status=AgentTaskStatus.WAITING_INPUT.value,
    )

    record = AgentTaskApprovalService.request(task=task, requester_id="user-1")

    assert record["status"] == "pending"
    assert record["assessment"]["requires_confirmation"] is True
    assert "write_requires_confirmation" in record["assessment"]["reasons"]


def test_approval_service_requires_confirmation_for_workspace_write_tasks():
    for task_type in ["workspace_file_write", "workspace_patch_apply"]:
        record = AgentTaskApprovalService.request(task={"task_id": f"task-{task_type}", "task_type": task_type, "risk_level": "high"})

        assert record["status"] == "pending"
        assert record["assessment"]["requires_confirmation"] is True
        assert "write_requires_confirmation" in record["assessment"]["reasons"]


def test_approval_service_approval_moves_waiting_task_to_ready_and_audits():
    goal = AgentTaskModelService.create_goal(raw_request="写文件", goal_type="edit_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="write_file",
        title="Write file",
        risk_level="high",
        status=AgentTaskStatus.WAITING_INPUT.value,
    )
    record = AgentTaskApprovalService.request(task=task, requester_id="user-1")

    decided = AgentTaskApprovalService.decide(record["approval_id"], approved=True, reviewer_id="reviewer-1", reason="ok")

    task_after = AgentTaskModelService.get_task(task["task_id"])
    audit_actions = {item["action"] for item in AgentTaskModelService.list_audit(goal_id=goal["goal_id"])}
    assert decided["status"] == "approved"
    assert task_after["status"] == AgentTaskStatus.READY.value
    assert task_after["metadata"]["approvals"][0]["reviewer_id"] == "reviewer-1"
    assert "approval_requested" in audit_actions
    assert "approval_decided" in audit_actions


def test_approval_service_rejection_cancels_task_and_keeps_alternative_plan():
    goal = AgentTaskModelService.create_goal(raw_request="写文件", goal_type="edit_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="write_file",
        title="Write file",
        risk_level="high",
        status=AgentTaskStatus.WAITING_INPUT.value,
    )
    record = AgentTaskApprovalService.request(task=task)

    AgentTaskApprovalService.decide(
        record["approval_id"],
        approved=False,
        reviewer_id="reviewer-1",
        reason="use report only",
        alternative_plan={"task_type": "generate_report"},
    )

    task_after = AgentTaskModelService.get_task(task["task_id"])
    assert task_after["status"] == AgentTaskStatus.CANCELED.value
    assert task_after["metadata"]["alternative_plan"] == {"task_type": "generate_report"}


def test_approval_service_denies_command_execution_even_if_user_tries_to_approve():
    task = {"task_id": "task-command", "task_type": "run_command", "risk_level": "high"}
    record = AgentTaskApprovalService.request(task=task)

    with pytest.raises(AgentTaskApprovalError) as exc:
        AgentTaskApprovalService.decide(record["approval_id"], approved=True, reviewer_id="reviewer-1")

    assert record["status"] == "denied"
    assert record["assessment"]["denied"] is True
    assert exc.value.code == "ACTION_DENIED_BY_POLICY"


def test_approval_service_enforces_existing_approval_and_allows_low_risk():
    low_risk = {"task_id": "task-read", "task_type": "read_file", "risk_level": "low"}
    high_risk = {"task_id": "task-write", "task_type": "write_file", "risk_level": "high"}
    record = AgentTaskApprovalService.request(task=high_risk)
    AgentTaskApprovalService.decide(record["approval_id"], approved=True, reviewer_id="reviewer-1")

    low = AgentTaskApprovalService.enforce(task=low_risk)
    high = AgentTaskApprovalService.enforce(task=high_risk)

    assert low["allowed"] is True
    assert high["allowed"] is True
    assert high["approval"]["status"] == "approved"


def test_security_policy_respects_external_io_strategy():
    assessment = AgentTaskSecurityPolicy.assess(
        {"task_id": "task-api", "task_type": "call_external_api", "risk_level": "medium"},
        policy={"ask_before_external_io": True},
    )

    assert assessment["allowed"] is False
    assert assessment["requires_confirmation"] is True
    assert "external_io_requires_confirmation" in assessment["reasons"]
