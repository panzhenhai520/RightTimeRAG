from pathlib import Path

from agent.component.task_execution import (
    TaskExecutor,
    TaskExecutorParam,
    TaskFrameController,
    TaskFrameControllerParam,
)
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskStatus
from api.db.services.agent_task_stack_service import AgentTaskStackService


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def setup_function():
    AgentTaskModelService.reset()


def test_task_executor_node_runs_read_file(tmp_path: Path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "plan.md").write_text("# Plan\nnode execution\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root))
    goal = AgentTaskModelService.create_goal(raw_request="读取文件", goal_type="read_document")
    task = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="read_file",
        title="Read",
        inputs={"path": "plan.md"},
    )
    node = TaskExecutor.__new__(TaskExecutor)
    node._canvas = FakeCanvas({"task_id_ref": task["task_id"]})
    node._param = TaskExecutorParam()
    node._param.task_id = "task_id_ref"

    node._invoke()

    assert node.output("ok") is True
    assert node.output("status") == AgentTaskStatus.COMPLETED.value
    assert "node execution" in node.output("result")["content"]


def test_task_frame_controller_node_pauses_and_resumes_frame():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question")
    task = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="find_file", title="Find")
    frame = AgentTaskStackService.push(task_id=task["task_id"], continuation_pointer="after_find")

    pause_node = TaskFrameController.__new__(TaskFrameController)
    pause_node._canvas = FakeCanvas({"frame_ref": frame["frame_id"]})
    pause_node._param = TaskFrameControllerParam()
    pause_node._param.action = "pause"
    pause_node._param.frame_id = "frame_ref"
    pause_node._invoke()

    resume_node = TaskFrameController.__new__(TaskFrameController)
    resume_node._canvas = FakeCanvas({"frame_ref": frame["frame_id"]})
    resume_node._param = TaskFrameControllerParam()
    resume_node._param.action = "resume"
    resume_node._param.frame_id = "frame_ref"
    resume_node._invoke()

    assert pause_node.output("status") == "paused"
    assert resume_node.output("status") == "running"
    assert resume_node.output("continuation_pointer") == "after_find"
