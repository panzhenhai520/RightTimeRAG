from agent.component.task_planner import (
    AtomicTaskRefiner,
    AtomicTaskRefinerParam,
    TaskDecomposer,
    TaskDecomposerParam,
    TaskPlanner,
    TaskPlannerParam,
)
from api.db.services.agent_goal_intent_service import AgentGoalIntentService


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def test_task_planner_node_outputs_valid_plan():
    intent = AgentGoalIntentService.classify("修改文档并新增内容")
    node = TaskPlanner.__new__(TaskPlanner)
    node._canvas = FakeCanvas({"intent_ref": intent, "context_ref": {"candidate_files": []}})
    node._param = TaskPlannerParam()
    node._param.goal_intent = "intent_ref"
    node._param.context_bundle = "context_ref"

    node._invoke()

    assert node.output("validation")["ok"] is True
    assert node.output("tasks")[0]["task_type"] == "edit_document"
    assert len(node.output("atomic_tasks")) == 9


def test_task_decomposer_and_atomic_refiner_nodes():
    intent = AgentGoalIntentService.classify("比较两份合同文件差异")
    decomposer = TaskDecomposer.__new__(TaskDecomposer)
    decomposer._canvas = FakeCanvas({"intent_ref": intent})
    decomposer._param = TaskDecomposerParam()
    decomposer._param.goal_intent = "intent_ref"
    decomposer._invoke()

    refiner = AtomicTaskRefiner.__new__(AtomicTaskRefiner)
    refiner._canvas = FakeCanvas(
        {
            "plan_ref": {
                "tasks": decomposer.output("tasks"),
                "relations": decomposer.output("relations"),
            }
        }
    )
    refiner._param = AtomicTaskRefinerParam()
    refiner._param.task_plan = "plan_ref"
    refiner._invoke()

    assert decomposer.output("parallel_groups")[0]["node_ids"] == ["task-002", "task-003"]
    assert refiner.output("validation")["ok"] is True
    assert all(task["metadata"]["atomic"] for task in refiner.output("atomic_tasks"))
