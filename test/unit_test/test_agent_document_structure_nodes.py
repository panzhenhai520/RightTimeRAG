from agent.component.document_structure import (
    ContentPlacementPlanner,
    ContentPlacementPlannerParam,
    DocumentStructureAdvisor,
    DocumentStructureAdvisorParam,
)


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def outline():
    return {
        "sections": [
            {"title": "开发任务", "level": 2, "section_path": ["开发任务"]},
            {"title": "测试任务", "level": 2, "section_path": ["测试任务"]},
        ]
    }


def test_document_structure_advisor_node_outputs_modification_plan():
    node = DocumentStructureAdvisor.__new__(DocumentStructureAdvisor)
    node._canvas = FakeCanvas({"outline_ref": outline(), "content_ref": "新增开发任务：实现任务执行服务。"})
    node._param = DocumentStructureAdvisorParam()
    node._param.outline = "outline_ref"
    node._param.new_content = "content_ref"

    node._invoke()

    assert node.output("content_categories")[0]["category"] == "development_task"
    assert node.output("modification_plan")[0]["operation"] == "insert_section"
    assert node.output("user_review_needed") is False


def test_content_placement_planner_node_outputs_insertion_points():
    node = ContentPlacementPlanner.__new__(ContentPlacementPlanner)
    node._canvas = FakeCanvas({"outline_ref": outline()})
    node._param = ContentPlacementPlannerParam()
    node._param.outline = "outline_ref"
    node._param.new_content = "新增测试用例和回归测试。"

    node._invoke()

    assert node.output("content_categories")[0]["category"] == "test_task"
    assert node.output("insertion_points")[0]["target_section"]["title"] == "测试任务"
    assert node.output("merge_strategy")["requires_new_heading"] is False
