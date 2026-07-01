import pytest

from api.db.services.agent_task_model_service import (
    AgentTaskError,
    AgentTaskModelService,
    AgentTaskRelation,
)


def setup_function():
    AgentTaskModelService.reset()


def test_agent_task_model_service_creates_goal_task_tree_and_audit():
    goal = AgentTaskModelService.create_goal(
        raw_request="找到最近写的文档并调整结构",
        goal_type="edit_document",
        primary_object="最近文档",
        expected_outcome="revision_plan",
        confidence=0.86,
    )
    root = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        task_type="edit_document",
        title="调整文档",
        completion_criteria=[{"kind": "report_created"}],
    )
    child = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        parent_task_id=root["task_id"],
        task_type="find_file",
        title="找到目标文档",
        tool_hint="WorkspaceFileSearch",
    )

    children = AgentTaskModelService.list_children(root["task_id"])
    tree = AgentTaskModelService.task_tree(root["task_id"])
    relations = AgentTaskModelService.list_relations(root["task_id"])
    audit = AgentTaskModelService.list_audit(goal_id=goal["goal_id"])

    assert goal["goal_type"] == "edit_document"
    assert children[0]["task_id"] == child["task_id"]
    assert tree["children"][0]["task"]["task_type"] == "find_file"
    assert any(item["relation"] == AgentTaskRelation.CHILD.value for item in relations)
    assert any(item["action"] == "goal_created" for item in audit)
    assert any(item["action"] == "task_created" for item in audit)


def test_agent_task_model_service_rejects_missing_parent_and_invalid_relation():
    goal = AgentTaskModelService.create_goal(raw_request="任务", goal_type="ask_question")

    with pytest.raises(AgentTaskError) as exc:
        AgentTaskModelService.create_task(
            goal_id=goal["goal_id"],
            parent_task_id="missing",
            task_type="find_file",
            title="找文件",
        )
    assert exc.value.code == "PARENT_TASK_NOT_FOUND"

    task_a = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="a", title="A")
    task_b = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="b", title="B")
    with pytest.raises(AgentTaskError) as exc:
        AgentTaskModelService.add_relation(source_task_id=task_a["task_id"], target_task_id=task_b["task_id"], relation="unknown")
    assert exc.value.code == "INVALID_TASK_RELATION"
