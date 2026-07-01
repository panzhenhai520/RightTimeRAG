from api.db.services.agent_task_execution_service import AgentTaskExecutionService
from api.db.services.agent_task_model_service import AgentTaskModelService
from api.db.services.agent_task_stack_service import AgentTaskStackService


def setup_function():
    AgentTaskModelService.reset()


def test_task_resume_service_keeps_three_level_continuation_stack():
    goal = AgentTaskModelService.create_goal(raw_request="三层任务", goal_type="edit_document")
    root = AgentTaskModelService.create_task(goal_id=goal["goal_id"], task_type="edit_document", title="Root")
    child = AgentTaskModelService.create_task(goal_id=goal["goal_id"], parent_task_id=root["task_id"], task_type="read_document", title="Child")
    leaf = AgentTaskModelService.create_task(goal_id=goal["goal_id"], parent_task_id=child["task_id"], task_type="find_file", title="Leaf")

    root_frame = AgentTaskStackService.push(task_id=root["task_id"], continuation_pointer="root:start")
    child_frame = AgentTaskExecutionService.enter_child_task(
        child_task_id=child["task_id"],
        parent_frame_id=root_frame["frame_id"],
        return_to_task_id=root["task_id"],
        continuation_pointer="root:after_child",
    )
    leaf_frame = AgentTaskExecutionService.enter_child_task(
        child_task_id=leaf["task_id"],
        parent_frame_id=child_frame["frame_id"],
        return_to_task_id=child["task_id"],
        continuation_pointer="child:after_leaf",
    )

    AgentTaskExecutionService.pause_frame(leaf_frame["frame_id"], reason="checkpoint")
    resumed = AgentTaskExecutionService.resume_frame(leaf_frame["frame_id"])
    continuation = AgentTaskExecutionService.continue_from_frame(resumed["frame_id"])

    assert continuation["task_id"] == leaf["task_id"]
    assert continuation["continuation_pointer"] == "child:after_leaf"
    assert len(AgentTaskStackService.stack_for_goal(goal["goal_id"])) == 3
