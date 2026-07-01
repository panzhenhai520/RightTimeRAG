from api.db.services.agent_task_budget_service import AgentTaskLoopGuard
from api.db.services.agent_task_model_service import AgentTaskModelService


def setup_function():
    AgentTaskModelService.reset()
    AgentTaskLoopGuard.reset()


def test_task_loop_guard_detects_repeated_same_plan():
    tasks = [{"node_id": "root", "task_type": "edit_document", "title": "Edit"}, {"node_id": "a", "parent_id": "root", "task_type": "find_file", "title": "Find"}]

    first = AgentTaskLoopGuard.record_plan(goal_id="goal-1", tasks=tasks, config={"max_replan_count": 2})
    second = AgentTaskLoopGuard.record_plan(goal_id="goal-1", tasks=tasks, config={"max_replan_count": 2})
    third = AgentTaskLoopGuard.record_plan(goal_id="goal-1", tasks=tasks, config={"max_replan_count": 2})

    assert first["loop_detected"] is False
    assert second["loop_detected"] is False
    assert third["loop_detected"] is True
    assert third["failure_strategy"] == "mark_blocked"


def test_task_loop_guard_detects_repeated_precondition_failure():
    condition = {"kind": "required_input", "code": "missing_required_input"}

    AgentTaskLoopGuard.record_precondition_failure(goal_id="goal-1", task_id="task-1", condition_result=condition, config={"max_replan_count": 1})
    result = AgentTaskLoopGuard.record_precondition_failure(goal_id="goal-1", task_id="task-1", condition_result=condition, config={"max_replan_count": 1})

    assert result["loop_detected"] is True
    assert result["failure_strategy"] == "ask_user"
    assert "Ask the user" in result["recovery_suggestion"]


def test_task_loop_guard_detects_repeated_verifier_failure_and_audits():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question", goal_id="goal-1")
    failed_checks = [{"check": "schema_match", "code": "missing_output_keys"}]

    AgentTaskLoopGuard.record_verifier_failure(goal_id=goal["goal_id"], task_id="task-1", failed_checks=failed_checks, config={"max_replan_count": 1})
    result = AgentTaskLoopGuard.record_verifier_failure(goal_id=goal["goal_id"], task_id="task-1", failed_checks=failed_checks, config={"max_replan_count": 1})
    audit = AgentTaskModelService.list_audit(goal_id=goal["goal_id"])

    assert result["loop_detected"] is True
    assert result["failure_strategy"] == "split_task_further"
    assert any(item["action"] == "task_loop_guard_event" for item in audit)
