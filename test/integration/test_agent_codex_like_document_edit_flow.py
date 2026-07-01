from pathlib import Path

from api.db.services.agent_codex_like_flow_service import CodexLikeDocumentEditFlowService


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "智能体自定义平台开发改进计划-v4.md").write_text(
        "\n".join(
            [
                "# 智能体自定义平台开发改进计划-v4",
                "",
                "## 背景",
                "需要让智能体具备文件理解能力。",
                "",
                "## 目标能力",
                "支持读取文档和比对文档。",
                "",
                "## 开发任务",
                "已有上下文读取层。",
                "",
                "## 测试任务",
                "每个阶段需要测试。",
            ]
        ),
        encoding="utf-8",
    )
    return root


def test_codex_like_document_edit_flow_outputs_plan_structure_and_report(tmp_path):
    root = make_workspace(tmp_path)

    result = CodexLikeDocumentEditFlowService.run(
        raw_request="找到最近写的智能体计划文档，我要新增任务分解能力",
        roots=[root],
        new_content="新增任务分解层、前置条件分析层、结果核对层，并为每阶段增加测试。",
    )

    assert result["goal_intent"]["goal_type"] == "edit_document"
    assert result["context_bundle"]["candidate_files"][0]["file"]["name"] == "智能体自定义平台开发改进计划-v4.md"
    assert result["task_plan"]["validation"]["ok"] is True
    assert any(task["task_type"] == "classify_content" for task in result["task_plan"]["tasks"])
    assert result["structure_advice"]["modification_plan"]
    assert any(item["recommendation"] == "place_as_child" for item in result["structure_advice"]["same_level_analysis"])
    assert result["verification"]["ok"] is True
    assert "## Plan" in result["markdown"]
    assert result["audit"]["writes_file"] is False
    assert result["audit"]["evidence_count"] >= 1
