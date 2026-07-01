from agent.component.task_precondition import (
    DependencyResolver,
    DependencyResolverParam,
    PreconditionChecker,
    PreconditionCheckerParam,
)
from api.db.services.agent_task_model_service import AgentTaskStatus


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def test_precondition_checker_node_outputs_repair_tasks():
    task = {
        "task_id": "task-edit",
        "inputs": {},
        "preconditions": [{"kind": "required_input", "field": "target_document"}],
        "status": AgentTaskStatus.PENDING.value,
    }
    node = PreconditionChecker.__new__(PreconditionChecker)
    node._canvas = FakeCanvas({"task_ref": task})
    node._param = PreconditionCheckerParam()
    node._param.task = "task_ref"

    node._invoke()

    assert node.output("ready") is False
    assert node.output("next_status") == AgentTaskStatus.WAITING_INPUT.value
    assert node.output("repair_tasks")[0]["task_type"] == "find_file"


def test_dependency_resolver_node_outputs_blockers():
    upstream = {"node_id": "task-001", "task_type": "find_file", "status": AgentTaskStatus.COMPLETED.value}
    task = {"node_id": "task-002", "task_type": "read_document", "depends_on": ["task-001"]}
    node = DependencyResolver.__new__(DependencyResolver)
    node._canvas = FakeCanvas({"task_ref": task, "tasks_ref": [upstream]})
    node._param = DependencyResolverParam()
    node._param.task = "task_ref"
    node._param.tasks = "tasks_ref"

    node._invoke()

    assert node.output("ready") is True
    assert node.output("blocked_by") == []
    assert node.output("dependencies")[0]["task_id"] == "task-001"
