from agent.component.task_execution_report import TaskExecutionReportComposer, TaskExecutionReportComposerParam


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def test_task_execution_report_composer_node_outputs_markdown():
    node = TaskExecutionReportComposer.__new__(TaskExecutionReportComposer)
    node._canvas = FakeCanvas(
        {
            "intent_ref": {"goal_type": "edit_document", "expected_outcome": "revision_plan", "risk_level": "medium"},
            "plan_ref": {"tasks": [{"node_id": "root"}], "atomic_tasks": [{"node_id": "task-1"}], "validation": {"ok": True}},
            "verify_ref": {"ok": True, "failed_checks": [], "next_action": "return_to_parent"},
            "decision_ref": {"next_action": "return_to_parent", "reason": "verification_passed"},
        }
    )
    node._param = TaskExecutionReportComposerParam()
    node._param.goal_intent = "intent_ref"
    node._param.task_plan = "plan_ref"
    node._param.verification = "verify_ref"
    node._param.decision = "decision_ref"

    node._invoke()

    assert node.output("report")["goal"]["goal_type"] == "edit_document"
    assert "## Verification" in node.output("markdown")
    assert node.output("audit")["writes_file"] is False
