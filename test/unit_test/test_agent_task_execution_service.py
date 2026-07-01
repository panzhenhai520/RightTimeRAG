from pathlib import Path

from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_execution_service import AgentTaskExecutionService
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_stack_service import AgentTaskStackService


def setup_function():
    AgentTaskModelService.reset()


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "plan.md").write_text("# Plan\n任务执行栈\n", encoding="utf-8")
    return root


def test_task_execution_service_executes_find_file_and_returns_to_parent(tmp_path):
    root = make_workspace(tmp_path)
    goal = AgentTaskModelService.create_goal(raw_request="找到 plan 文档", goal_type="find_file")
    parent = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="edit_document", title="Parent")
    child = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        parent_task_id=parent["task_id"],
        task_type="find_file",
        title="Find plan",
        inputs={"goal_intent": AgentGoalIntentService.classify("找到 plan 文档"), "query": "plan"},
    )
    parent_frame = AgentTaskStackService.push(task_id=parent["task_id"], continuation_pointer="start")

    result = AgentTaskExecutionService.execute_leaf_task(
        child["task_id"],
        parent_frame_id=parent_frame["frame_id"],
        continuation_pointer="after_find",
        roots=[root],
    )

    parent_after = AgentTaskModelService.get_task(parent["task_id"])
    child_after = AgentTaskModelService.get_task(child["task_id"])
    assert result["ok"] is True
    assert result["result"]["selected_file"]["name"] == "plan.md"
    assert child_after["status"] == AgentTaskStatus.COMPLETED.value
    assert parent_after["metadata"]["local_context"][f"return:{child['task_id']}"]["selected_file"]["name"] == "plan.md"


def test_task_execution_service_executes_read_file(tmp_path):
    root = make_workspace(tmp_path)
    goal = AgentTaskModelService.create_goal(raw_request="读取文件", goal_type="read_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_file",
        title="Read plan",
        inputs={"path": "plan.md"},
    )

    result = AgentTaskExecutionService.execute_leaf_task(task["task_id"], roots=[root])

    assert result["ok"] is True
    assert "任务执行栈" in result["result"]["content"]
    assert AgentTaskModelService.get_task(task["task_id"])["status"] == AgentTaskStatus.COMPLETED.value


def test_task_execution_service_blocks_after_retry_budget_exceeded(tmp_path):
    root = make_workspace(tmp_path)
    goal = AgentTaskModelService.create_goal(raw_request="读取缺失文件", goal_type="read_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_file",
        title="Read missing",
        inputs={"path": "missing.md"},
    )

    result = AgentTaskExecutionService.execute_leaf_task(task["task_id"], roots=[root], max_retry=0)

    task_after = AgentTaskModelService.get_task(task["task_id"])
    assert result["ok"] is False
    assert result["status"] == AgentTaskStatus.BLOCKED.value
    assert task_after["status"] == AgentTaskStatus.BLOCKED.value
    assert task_after["metadata"]["execution"]["retry_count"] == 1


def test_task_execution_service_failed_task_can_be_moved_to_ready_for_retry(tmp_path):
    root = make_workspace(tmp_path)
    goal = AgentTaskModelService.create_goal(raw_request="读取缺失文件", goal_type="read_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_file",
        title="Read missing",
        inputs={"path": "missing.md"},
    )

    failed = AgentTaskExecutionService.execute_leaf_task(task["task_id"], roots=[root], max_retry=1)
    retry = AgentTaskExecutionService.retry_task(task["task_id"], max_retry=1)

    assert failed["status"] == AgentTaskStatus.FAILED.value
    assert retry["retry_allowed"] is True
    assert AgentTaskModelService.get_task(task["task_id"])["status"] == AgentTaskStatus.READY.value


def test_task_execution_service_pause_resume_and_continue_from_frame():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question")
    task = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="find_file", title="Find")
    frame = AgentTaskStackService.push(task_id=task["task_id"], continuation_pointer="after_find", local_context={"a": 1})

    paused = AgentTaskExecutionService.pause_frame(frame["frame_id"], reason="manual pause")
    continued = AgentTaskExecutionService.continue_from_frame(frame["frame_id"])
    resumed = AgentTaskExecutionService.resume_frame(frame["frame_id"])

    assert paused["status"] == "paused"
    assert continued["continuation_pointer"] == "after_find"
    assert continued["local_context"]["a"] == 1
    assert resumed["status"] == "running"
