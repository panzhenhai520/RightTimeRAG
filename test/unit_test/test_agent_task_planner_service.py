from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_model_service import AgentTaskModelService, AgentTaskRelation
from api.db.services.agent_task_planner_service import TaskPlanner


def setup_function():
    AgentTaskModelService.reset()


def assert_plan_contract(plan):
    ids = {task["node_id"] for task in plan["tasks"]}
    assert plan["validation"]["ok"] is True
    assert plan["root_task"]["node_id"] == "root"
    assert plan["tree"]["node_id"] == "root"
    for task in plan["tasks"]:
        assert task["node_id"] in ids
        if task["node_id"] != "root":
            assert task["parent_id"] in ids
        for field in (
            "task_type",
            "inputs",
            "outputs",
            "preconditions",
            "completion_criteria",
            "risk_level",
            "tool_hint",
            "evidence_requirement",
        ):
            assert field in task
        if not task["children"]:
            assert task["completion_criteria"]
            assert task["metadata"]["atomic"] is True


def test_task_planner_edit_document_golden_case():
    intent = AgentGoalIntentService.classify("把最近上次写的某文档找出来，我需要调整，新增任务分解和测试内容")
    context = {
        "candidate_files": [
            {
                "file": {"name": "智能体自定义平台开发改进计划-v4.md", "relative_path": "智能体自定义平台开发改进计划-v4.md"},
                "score": 8.5,
                "reasons": ["recent_hint", "name_match"],
            }
        ],
        "unresolved_context": [],
    }

    plan = TaskPlanner.plan(goal_intent=intent, context_bundle=context, max_depth=4)

    assert_plan_contract(plan)
    task_types = [task["task_type"] for task in plan["tasks"]]
    assert task_types == [
        "edit_document",
        "find_file",
        "read_document",
        "analyze_document_structure",
        "classify_content",
        "recommend_structure",
        "plan_document_revision",
        "propose_patch",
        "verify_diff",
        "generate_report",
    ]
    assert plan["dag"]["nodes"] == [task["node_id"] for task in plan["tasks"]]
    assert {"source_node_id": "task-002", "target_node_id": "task-001", "relation": "depends_on"} in plan["relations"]
    assert plan["validation"]["max_depth"] <= 4


def test_task_planner_compare_documents_has_parallel_normalization_group():
    intent = AgentGoalIntentService.classify("比较两份合同文件，分析法律条款和合同条款冲突并输出报告")

    plan = TaskPlanner.plan(goal_intent=intent, context_bundle={}, max_depth=4)

    assert_plan_contract(plan)
    assert plan["root_task"]["task_type"] == "compare_documents"
    assert plan["parallel_groups"] == [{"group_id": "normalize_documents", "node_ids": ["task-002", "task-003"]}]
    assert any(task["task_type"] == "compare_documents" for task in plan["tasks"])


def test_task_planner_detects_dependency_cycle():
    intent = AgentGoalIntentService.classify("修改文档并新增内容")
    plan = TaskPlanner.plan(goal_intent=intent, context_bundle={}, max_depth=4)
    for task in plan["tasks"]:
        if task["node_id"] == "task-001":
            task["depends_on"] = ["task-009"]

    validation = TaskPlanner.validate_plan(plan, max_depth=4)

    assert validation["ok"] is False
    assert any(issue["code"] == "dependency_cycle" for issue in validation["issues"])


def test_task_planner_persist_creates_model_tree_and_dependency_relations():
    intent = AgentGoalIntentService.classify("修改文档并新增内容")

    plan = TaskPlanner.plan(goal_intent=intent, context_bundle={}, persist=True)

    persisted = plan["persisted_tasks"]
    root_task_id = persisted["node_to_task"]["root"]
    tree = AgentTaskModelService.task_tree(root_task_id)
    relations = AgentTaskModelService.list_relations()

    assert plan["persisted"] is True
    assert tree["task"]["task_type"] == "edit_document"
    assert len(tree["children"]) == 9
    assert any(relation["relation"] == AgentTaskRelation.DEPENDS_ON.value for relation in relations)
