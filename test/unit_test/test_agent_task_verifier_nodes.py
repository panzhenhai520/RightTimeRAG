from agent.component.task_verifier import (
    ReplanDecider,
    ReplanDeciderParam,
    TaskReflection,
    TaskReflectionParam,
    TaskResultVerifier,
    TaskResultVerifierParam,
)


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def task_contract():
    return {
        "task_id": "task-1",
        "parent_task_id": "parent-1",
        "task_type": "read_file",
        "outputs": {"content": "String"},
        "completion_criteria": [{"kind": "output_available", "output": "content"}],
        "evidence_requirement": [{"kind": "source_ref", "required": True}],
    }


def test_task_result_verifier_node_outputs_next_action():
    node = TaskResultVerifier.__new__(TaskResultVerifier)
    node._canvas = FakeCanvas({"task_ref": task_contract(), "result_ref": {"content": "ok", "source_ref": "plan.md"}})
    node._param = TaskResultVerifierParam()
    node._param.task = "task_ref"
    node._param.result = "result_ref"

    node._invoke()

    assert node.output("ok") is True
    assert node.output("next_action") == "return_to_parent"


def test_task_reflection_and_replan_decider_nodes():
    verification = {
        "ok": False,
        "check_results": [{"check": "schema_match", "passed": False, "code": "missing_output_keys"}],
    }
    reflection_node = TaskReflection.__new__(TaskReflection)
    reflection_node._canvas = FakeCanvas({"task_ref": task_contract(), "verification_ref": verification})
    reflection_node._param = TaskReflectionParam()
    reflection_node._param.task = "task_ref"
    reflection_node._param.verification = "verification_ref"
    reflection_node._invoke()

    decider_node = ReplanDecider.__new__(ReplanDecider)
    decider_node._canvas = FakeCanvas(
        {
            "task_ref": task_contract(),
            "verification_ref": verification,
            "reflection_ref": reflection_node.output("reflection"),
        }
    )
    decider_node._param = ReplanDeciderParam()
    decider_node._param.task = "task_ref"
    decider_node._param.verification = "verification_ref"
    decider_node._param.reflection = "reflection_ref"
    decider_node._invoke()

    assert reflection_node.output("root_causes") == ["incomplete_output"]
    assert decider_node.output("next_action") == "create_repair_task"
    assert decider_node.output("repair_tasks")[0]["task_type"] == "complete_output"
