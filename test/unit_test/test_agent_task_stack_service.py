from api.db.services.agent_task_model_service import AgentTaskModelService
from api.db.services.agent_task_stack_service import AgentTaskStackService


def setup_function():
    AgentTaskModelService.reset()


def test_agent_task_stack_service_push_return_and_pop():
    goal = AgentTaskModelService.create_goal(raw_request="修改文档", goal_type="edit_document")
    parent = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="edit_document", title="父任务")
    child = AgentTaskModelService.create_task(
        goal_id=goal["goal_id"],
        parent_task_id=parent["task_id"],
        task_type="find_file",
        title="子任务",
    )

    parent_frame = AgentTaskStackService.push(task_id=parent["task_id"], continuation_pointer="start")
    child_frame = AgentTaskStackService.push(
        task_id=child["task_id"],
        parent_frame_id=parent_frame["frame_id"],
        return_to_task_id=parent["task_id"],
        continuation_pointer="after_find_file",
    )
    returned = AgentTaskStackService.return_from_frame(child_frame["frame_id"], return_value={"path": "plan.md"})
    stack = AgentTaskStackService.stack_for_goal(goal["goal_id"])
    popped = AgentTaskStackService.pop(child_frame["frame_id"])
    audit = AgentTaskModelService.list_audit(goal_id=goal["goal_id"])

    assert returned["frame"]["status"] == "returned"
    assert returned["parent_frame"]["local_context"][f"return:{child['task_id']}"] == {"path": "plan.md"}
    assert len(stack) == 2
    assert popped["frame_id"] == child_frame["frame_id"]
    assert any(item["action"] == "stack_push" for item in audit)
    assert any(item["action"] == "stack_return" for item in audit)
