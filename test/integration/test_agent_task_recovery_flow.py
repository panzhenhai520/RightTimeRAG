from pathlib import Path

from api.db.services.agent_codex_like_flow_service import CodexLikeDocumentEditFlowService


def test_codex_like_flow_returns_repair_decision_when_context_is_missing(tmp_path: Path):
    root = tmp_path / "empty_workspace"
    root.mkdir()

    result = CodexLikeDocumentEditFlowService.run(
        raw_request="找到最近写的智能体计划文档，我要新增任务分解能力",
        roots=[root],
        new_content="新增任务分解层。",
    )

    assert result["context_bundle"]["summary"]["candidate_file_count"] == 0
    assert result["context_bundle"]["unresolved_context"][0]["kind"] == "no_candidate_files"
    assert result["verification"]["ok"] is False
    assert result["decision"]["next_action"] == "create_repair_task"
    assert result["decision"]["repair_tasks"][0]["metadata"]["repair_task"] is True
    assert result["report"]["audit"]["writes_file"] is False
