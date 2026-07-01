from agent.component.task_intent import (
    GoalIntentClassifier,
    GoalIntentClassifierParam,
    GoalNormalizer,
    GoalNormalizerParam,
)


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def test_goal_intent_classifier_node_outputs_goal_fields():
    node = GoalIntentClassifier.__new__(GoalIntentClassifier)
    node._canvas = FakeCanvas({"request_ref": "比对 a.md 和 b.md 的差异"})
    node._param = GoalIntentClassifierParam()
    node._param.request = "request_ref"

    node._invoke()

    assert node.output("goal_type") == "compare_documents"
    assert node.output("goal_intent")["expected_outcome"] == "comparison_report"
    assert isinstance(node.output("missing_inputs"), list)


def test_goal_normalizer_node_normalizes_goal_payload():
    node = GoalNormalizer.__new__(GoalNormalizer)
    node._canvas = FakeCanvas({"intent_ref": {"goal_type": "bad", "confidence": -2}})
    node._param = GoalNormalizerParam()
    node._param.goal_intent = "intent_ref"

    node._invoke()

    assert node.output("goal_type") == "needs_clarification"
    assert node.output("goal_intent")["confidence"] == 0.0
    assert node.output("unresolved") is True
