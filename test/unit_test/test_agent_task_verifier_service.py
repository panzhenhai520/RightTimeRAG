from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_verifier_service import ReplanDecider, TaskReflectionService, TaskResultVerifier


def setup_function():
    AgentTaskModelService.reset()


def task_contract(**overrides):
    task = {
        "task_id": "task-1",
        "parent_task_id": "parent-1",
        "task_type": "read_file",
        "outputs": {"content": "String", "source_ref": "String"},
        "completion_criteria": [{"kind": "output_available", "output": "content"}],
        "evidence_requirement": [{"kind": "source_ref", "required": True}],
        "metadata": {},
    }
    task.update(overrides)
    return task


def test_task_result_verifier_passes_and_returns_to_parent():
    result = {"content": "hello", "source_ref": "plan.md", "audit": {"allowed": True}}

    verification = TaskResultVerifier.verify(task=task_contract(), result=result)

    assert verification["ok"] is True
    assert verification["next_action"] == "return_to_parent"
    assert verification["failed_checks"] == []


def test_task_result_verifier_creates_repair_task_for_incomplete_output():
    result = {"source_ref": "plan.md", "audit": {"allowed": True}}

    verification = TaskResultVerifier.verify(task=task_contract(), result=result)

    assert verification["ok"] is False
    assert verification["next_action"] == "create_repair_task"
    assert verification["decision"]["repair_tasks"][0]["task_type"] == "complete_output"
    assert "incomplete_output" in verification["reflection"]["root_causes"]


def test_task_result_verifier_retries_when_evidence_is_missing():
    result = {"content": "hello", "source_ref": ""}

    verification = TaskResultVerifier.verify(task=task_contract(), result=result)

    assert verification["ok"] is False
    assert verification["next_action"] == "retry_same_task"
    assert "missing_evidence" in verification["reflection"]["root_causes"]


def test_task_result_verifier_blocks_policy_violation():
    result = {"content": "hello", "source_ref": "plan.md", "policy_violation": True}

    verification = TaskResultVerifier.verify(task=task_contract(), result=result)

    assert verification["ok"] is False
    assert verification["next_action"] == "mark_blocked"
    assert "policy_violation" in verification["reflection"]["root_causes"]


def test_task_result_verifier_marks_running_model_task_verified_when_requested():
    goal = AgentTaskModelService.create_goal(raw_request="读文件", goal_type="read_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_file",
        title="Read",
        outputs={"content": "String"},
        completion_criteria=[{"kind": "output_available", "output": "content"}],
        status=AgentTaskStatus.RUNNING.value,
    )

    verification = TaskResultVerifier.verify_model_task(
        task["task_id"],
        result={"content": "ok"},
        checks=["schema_match", "completion_criteria_met", "no_policy_violation"],
        mark_verified=True,
    )

    assert verification["ok"] is True
    assert AgentTaskModelService.get_task(task["task_id"])["status"] == AgentTaskStatus.VERIFIED.value


def test_reflection_and_replan_decider_split_ambiguous_result():
    verification = {
        "ok": False,
        "check_results": [{"check": "parent_goal_progressed", "passed": False, "code": "goal_not_progressed"}],
    }
    reflection = TaskReflectionService.reflect(task=task_contract(), result={}, verification=verification)
    decision = ReplanDecider.decide(task=task_contract(), verification=verification, reflection=reflection)

    assert reflection["root_causes"] == ["ambiguous_progress"]
    assert decision["next_action"] == "split_task_further"
