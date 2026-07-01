import pytest

from api.db.services.agent_task_taxonomy_service import TaskTaxonomyError, TaskTaxonomyService


def setup_function():
    TaskTaxonomyService.reset()


def test_task_taxonomy_service_crud_freeze_and_fork_versions():
    created = TaskTaxonomyService.create_taxonomy(
        name="custom_task",
        version="v1",
        categories={"edit_document": ["修改", "新增"], "find_file": ["找到"]},
    )
    TaskTaxonomyService.add_example(
        name="custom_task",
        version="v1",
        category="edit_document",
        text="修改文档",
    )
    frozen = TaskTaxonomyService.freeze_version(name="custom_task", version="v1")

    with pytest.raises(TaskTaxonomyError) as exc:
        TaskTaxonomyService.add_example(name="custom_task", version="v1", category="edit_document", text="新增内容")

    forked = TaskTaxonomyService.fork_version(name="custom_task", from_version="v1", new_version="v2")
    TaskTaxonomyService.add_example(name="custom_task", version="v2", category="find_file", text="找到最近文档")

    v1 = TaskTaxonomyService.get_taxonomy(name="custom_task", version="v1")
    v2 = TaskTaxonomyService.get_taxonomy(name="custom_task", version="v2")

    assert created["status"] == "draft"
    assert frozen["status"] == "frozen"
    assert exc.value.code == "TAXONOMY_VERSION_FROZEN"
    assert forked["metadata"]["forked_from"] == "v1"
    assert len(v1["examples"]["positive"]) == 1
    assert len(v2["examples"]["positive"]) == 2


def test_task_taxonomy_service_classifies_with_versioned_examples():
    TaskTaxonomyService.create_taxonomy(
        name="custom_task",
        version="v1",
        categories={"edit_document": ["修改"], "find_file": ["找到"]},
    )
    TaskTaxonomyService.add_example(
        name="custom_task",
        version="v1",
        category="find_file",
        text="最近写的计划",
    )

    result = TaskTaxonomyService.classify(name="custom_task", version="v1", text="帮我把最近写的计划找出来")

    assert result["category"] == "find_file"
    assert result["taxonomy_version"] == "v1"
    assert result["confidence"] > 0.5


def test_task_taxonomy_service_evaluates_examples():
    TaskTaxonomyService.create_taxonomy(
        name="custom_task",
        version="v1",
        categories={"edit_document": ["修改", "新增"], "find_file": ["找到"], "needs_clarification": []},
    )
    examples = [
        {"text": "修改 v4 文档", "expected_category": "edit_document"},
        {"text": "找到最近文档", "expected_category": "find_file"},
        {"text": "完全无关", "expected_category": "needs_clarification"},
    ]

    evaluation = TaskTaxonomyService.evaluate(name="custom_task", version="v1", examples=examples)

    assert evaluation["total"] == 3
    assert evaluation["accuracy"] == 1.0
    assert evaluation["needs_clarification_rate"] == 0.3333


def test_task_taxonomy_service_default_taxonomy_is_frozen_and_classifies():
    result = TaskTaxonomyService.classify(name="task_type", text="比较两个合同有没有冲突")
    taxonomy = TaskTaxonomyService.get_taxonomy(name="task_type", version=result["taxonomy_version"])

    assert result["category"] == "compare_documents"
    assert taxonomy["status"] == "frozen"
