from api.db.services.agent_task_planner_service import AtomicTaskRefiner, TaskNodeFactory, TaskPlanner


def test_atomic_task_refiner_adds_missing_atomic_contract_defaults():
    task = TaskNodeFactory.make_node(
        node_id="task-001",
        parent_id="root",
        task_type="collect_input",
        title="Collect input",
    )
    task["outputs"] = {}
    task["completion_criteria"] = []
    plan = {
        "tasks": [
            TaskNodeFactory.make_node(
                node_id="root",
                task_type="ask_question",
                title="Root",
                outputs={"task_plan": "JSON"},
                completion_criteria=[{"kind": "plan_validated"}],
                tool_hint="TaskPlanner",
                evidence_requirement=[{"kind": "plan_validation", "required": True}],
                metadata={"atomic": False},
            ),
            task,
        ],
        "relations": [],
    }
    plan["tasks"][0]["children"] = ["task-001"]

    refined = AtomicTaskRefiner.refine_plan(plan, max_depth=4)

    leaf = refined["tasks"][1]
    assert leaf["outputs"] == {"result": "JSON"}
    assert leaf["completion_criteria"] == [{"kind": "output_available", "output": "result"}]
    assert leaf["metadata"]["atomic"] is True
    assert refined["validation"]["ok"] is True


def test_atomic_task_refiner_flags_vague_leaf_as_non_atomic():
    root = TaskNodeFactory.make_node(
        node_id="root",
        task_type="ask_question",
        title="Root",
        outputs={"task_plan": "JSON"},
        completion_criteria=[{"kind": "plan_validated"}],
        tool_hint="TaskPlanner",
        evidence_requirement=[{"kind": "plan_validation", "required": True}],
        metadata={"atomic": False},
    )
    leaf = TaskNodeFactory.make_node(
        node_id="task-001",
        parent_id="root",
        task_type="generic",
        title="Process stuff",
        outputs={"result": "JSON"},
        completion_criteria=[{"kind": "output_available", "output": "result"}],
        tool_hint="Agent",
        evidence_requirement=[{"kind": "task_output", "required": True}],
    )
    root["children"] = ["task-001"]
    refined = AtomicTaskRefiner.refine_plan({"tasks": [root, leaf], "relations": []}, max_depth=4)

    assert refined["validation"]["ok"] is False
    assert any(issue["code"] == "non_atomic_leaf" for issue in refined["validation"]["issues"])


def test_validate_plan_detects_orphan_task():
    root = TaskNodeFactory.make_node(
        node_id="root",
        task_type="ask_question",
        title="Root",
        outputs={"task_plan": "JSON"},
        completion_criteria=[{"kind": "plan_validated"}],
        tool_hint="TaskPlanner",
        evidence_requirement=[{"kind": "plan_validation", "required": True}],
    )
    orphan = TaskNodeFactory.make_node(
        node_id="task-001",
        parent_id="missing",
        task_type="answer_question",
        title="Answer",
        outputs={"answer": "String"},
        completion_criteria=[{"kind": "answer_created"}],
        tool_hint="Agent",
        evidence_requirement=[{"kind": "reasoning_summary", "required": True}],
    )

    validation = TaskPlanner.validate_plan({"tasks": [root, orphan], "relations": []}, max_depth=4)

    assert validation["ok"] is False
    assert any(issue["code"] == "orphan_task" for issue in validation["issues"])
