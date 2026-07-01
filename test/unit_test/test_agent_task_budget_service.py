import time

from api.db.services.agent_task_budget_service import AgentTaskBudgetService
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus


def setup_function():
    AgentTaskModelService.reset()


def test_task_budget_service_detects_plan_depth_and_child_limit():
    plan = {
        "tasks": [
            {"node_id": "root"},
            {"node_id": "a", "parent_id": "root"},
            {"node_id": "b", "parent_id": "root"},
            {"node_id": "c", "parent_id": "a"},
            {"node_id": "d", "parent_id": "c"},
        ]
    }

    result = AgentTaskBudgetService.check_plan_budget(plan, config={"max_plan_depth": 3, "max_child_tasks": 1})
    codes = {issue["code"] for issue in result["issues"]}

    assert result["ok"] is False
    assert "max_plan_depth_exceeded" in codes
    assert "max_child_tasks_exceeded" in codes


def test_task_budget_service_detects_context_and_execution_time_limits():
    context = {"chunks": ["x" * 200]}
    context_result = AgentTaskBudgetService.check_context_budget(context, config={"max_context_bytes": 20})
    time_result = AgentTaskBudgetService.check_execution_time(started_at=time.time() - 5, config={"max_execution_seconds": 1})

    assert context_result["ok"] is False
    assert context_result["issues"][0]["code"] == "max_context_bytes_exceeded"
    assert time_result["ok"] is False
    assert time_result["issues"][0]["code"] == "max_execution_seconds_exceeded"


def test_task_budget_service_blocks_task_and_records_audit():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question")
    task = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="find_file", title="Find")
    check = AgentTaskBudgetService.check_plan_budget(
        {"tasks": [{"node_id": "root"}, {"node_id": "a", "parent_id": "root"}, {"node_id": "b", "parent_id": "root"}]},
        config={"max_child_tasks": 1},
    )

    result = AgentTaskBudgetService.block_task_if_needed(task["task_id"], check, recovery_suggestion="reduce child tasks")

    audit_actions = {item["action"] for item in AgentTaskModelService.list_audit(goal_id=goal["goal_id"])}
    assert result["blocked"] is True
    assert AgentTaskModelService.get_task(task["task_id"])["status"] == AgentTaskStatus.BLOCKED.value
    assert "task_budget_blocked" in audit_actions


def test_task_budget_service_detects_retry_budget():
    task = {"metadata": {"execution": {"retry_count": 3}}}

    result = AgentTaskBudgetService.check_retry_budget(task, config={"max_retry_per_task": 2})

    assert result["ok"] is False
    assert result["issues"][0]["code"] == "max_retry_per_task_exceeded"
