from api.db.services.agent_task_taxonomy_service import TaskFeedbackService


def setup_function():
    TaskFeedbackService.reset()


def test_task_feedback_service_records_and_filters_feedback():
    first = TaskFeedbackService.record(
        run_id="run-1",
        task_id="task-1",
        taxonomy_name="task_type",
        taxonomy_version="v1",
        input_text="修改文档",
        predicted_category="edit_document",
        correct=True,
        user_id="user-1",
    )
    TaskFeedbackService.record(
        run_id="run-1",
        task_id="task-2",
        taxonomy_name="task_type",
        taxonomy_version="v1",
        input_text="找文件",
        predicted_category="edit_document",
        correct=False,
        suggested_category="find_file",
        reason="用户实际想找文件",
    )

    by_task = TaskFeedbackService.list(task_id="task-1")
    by_run = TaskFeedbackService.list(run_id="run-1")

    assert by_task[0]["feedback_id"] == first["feedback_id"]
    assert len(by_run) == 2
    assert by_run[1]["suggested_category"] == "find_file"


def test_task_feedback_service_summarizes_feedback():
    TaskFeedbackService.record(
        run_id="run-1",
        task_id="task-1",
        taxonomy_name="task_type",
        taxonomy_version="v1",
        predicted_category="edit_document",
        correct=True,
    )
    TaskFeedbackService.record(
        run_id="run-2",
        task_id="task-2",
        taxonomy_name="task_type",
        taxonomy_version="v1",
        predicted_category="edit_document",
        correct=False,
        suggested_category="find_file",
    )

    summary = TaskFeedbackService.summarize(taxonomy_name="task_type", taxonomy_version="v1")

    assert summary["total"] == 2
    assert summary["correct"] == 1
    assert summary["incorrect"] == 1
    assert summary["accuracy_from_feedback"] == 0.5
    assert summary["suggested_categories"] == {"find_file": 1}
