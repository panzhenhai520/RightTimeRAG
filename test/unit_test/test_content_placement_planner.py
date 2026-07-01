from api.db.services.document_structure_advisor_service import ContentPlacementPlanner


def outline():
    return [
        {"title": "架构设计", "level": 2, "section_path": ["架构设计"], "source_ref": "doc.md | line 10"},
        {"title": "API 设计", "level": 2, "section_path": ["API 设计"], "source_ref": "doc.md | line 20"},
        {"title": "实施顺序", "level": 2, "section_path": ["实施顺序"], "source_ref": "doc.md | line 30"},
    ]


def test_content_placement_planner_classifies_and_places_api_content():
    plan = ContentPlacementPlanner.plan(
        outline=outline(),
        new_content="新增 /agents/tasks/plan API endpoint，返回 task_plan、relations 和 validation。",
    )

    categories = [item["category"] for item in plan["content_categories"]]
    api_point = next(item for item in plan["insertion_points"] if item["category"] == "api_design")

    assert "api_design" in categories
    assert api_point["target_section"]["title"] == "API 设计"
    assert api_point["placement"] == "insert_under_section"
    assert plan["merge_strategy"]["strategy"] in {"append_to_matching_section", "insert_as_subsections"}


def test_content_placement_planner_suggests_new_section_when_no_match():
    plan = ContentPlacementPlanner.plan(
        outline=[{"title": "背景", "level": 2}],
        new_content="新增 schema 字段和状态关系模型。",
    )
    data_point = next(item for item in plan["insertion_points"] if item["category"] == "data_model")

    assert data_point["placement"] == "create_new_section"
    assert data_point["proposed_title"] == "数据模型"


def test_content_placement_planner_marks_mixed_categories_for_split():
    plan = ContentPlacementPlanner.plan(
        outline=outline(),
        new_content="- 架构层设计\n- API 接口\n- 数据模型\n- 测试用例\n- 安全权限",
    )

    assert plan["merge_strategy"]["strategy"] == "insert_as_subsections"
    assert any(note["code"] == "mixed_categories" for note in plan["risk_notes"])
    assert plan["user_review_needed"] is True
