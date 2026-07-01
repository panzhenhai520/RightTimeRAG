from api.db.services.document_structure_advisor_service import DocumentStructureAdvisor


def sample_outline():
    return {
        "sections": [
            {"title": "一、背景", "level": 2, "section_path": ["背景"], "source_ref": "v3.md | line 3"},
            {"title": "二、目标能力", "level": 2, "section_path": ["目标能力"], "source_ref": "v3.md | line 12"},
            {"title": "三、开发任务", "level": 2, "section_path": ["开发任务"], "source_ref": "v3.md | line 30"},
            {"title": "四、测试任务", "level": 2, "section_path": ["测试任务"], "source_ref": "v3.md | line 80"},
        ]
    }


def test_document_structure_advisor_places_development_content_as_child_section():
    advice = DocumentStructureAdvisor.advise(
        outline=sample_outline(),
        new_content="新增意图识别层、任务分解层、上下文读取层，并开发 TaskPlanner 接口和节点。",
        user_goal="把这些开发任务补充进 v4 计划",
    )

    categories = {item["category"] for item in advice["content_categories"]}
    development_point = next(item for item in advice["insertion_points"] if item["category"] == "development_task")
    development_level = next(item for item in advice["same_level_analysis"] if item["category"] == "development_task")

    assert "development_task" in categories
    assert "architecture_design" in categories
    assert development_point["target_section"]["title"] == "三、开发任务"
    assert development_point["proposed_level"] == 3
    assert development_level["same_level"] is False
    assert development_level["recommendation"] == "place_as_child"
    assert advice["audit"]["writes_file"] is False


def test_document_structure_advisor_outputs_executable_modification_plan():
    advice = DocumentStructureAdvisor.advise(
        outline=sample_outline(),
        new_content="测试任务：每个阶段完成后运行单元测试和回归测试，失败时停止下一阶段。",
        user_goal="拆出测试任务",
    )

    test_point = next(item for item in advice["insertion_points"] if item["category"] == "test_task")
    operation = next(item for item in advice["modification_plan"] if item.get("heading_title") == "测试任务")

    assert test_point["target_section"]["title"] == "四、测试任务"
    assert operation["operation"] == "insert_section"
    assert operation["writes_file"] is False
    assert "回归测试" in operation["content_preview"]


def test_document_structure_advisor_identifies_out_of_scope_content():
    advice = DocumentStructureAdvisor.advise(
        outline=sample_outline(),
        new_content="新增餐厅菜单和旅游天气安排。",
        user_goal="更新智能体开发计划",
    )

    assert advice["content_categories"][0]["category"] == "out_of_scope"
    assert advice["insertion_points"][0]["placement"] == "separate_document_or_user_review"
    assert advice["modification_plan"][0]["operation"] == "skip_or_separate"
    assert advice["user_review_needed"] is True


def test_document_structure_advisor_stable_schema_without_outline():
    advice = DocumentStructureAdvisor.advise(outline={}, new_content="新增 API 接口和数据模型。")

    assert set(
        [
            "schema_version",
            "content_categories",
            "proposed_outline",
            "insertion_points",
            "merge_strategy",
            "same_level_analysis",
            "modification_plan",
            "risk_notes",
            "user_review_needed",
            "audit",
        ]
    ).issubset(advice.keys())
    assert any(item["code"] == "missing_outline" for item in advice["risk_notes"])
