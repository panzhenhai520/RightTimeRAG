import os
from pathlib import Path

from api.db.services.agent_goal_intent_service import AgentGoalIntentService
from api.db.services.agent_task_context_service import RecentArtifactFinder, RelevantFileResolver, TaskContextCollector


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "old_plan.md").write_text("# 旧计划\n普通内容\n", encoding="utf-8")
    (root / "new_plan.md").write_text("# 新计划\n这里包含任务分解和执行闭环。\n", encoding="utf-8")
    (root / "notes.txt").write_text("临时笔记\n", encoding="utf-8")
    os.utime(root / "old_plan.md", (1000, 1000))
    os.utime(root / "notes.txt", (2000, 2000))
    os.utime(root / "new_plan.md", (3000, 3000))
    return root


def test_relevant_file_resolver_ranks_recent_and_content_matches(tmp_path):
    root = make_workspace(tmp_path)
    intent = AgentGoalIntentService.classify("找到最近写的计划文档，内容关于任务分解")

    result = RelevantFileResolver.resolve(goal_intent=intent, roots=[root], max_candidates=3)

    assert result["candidate_files"][0]["file"]["name"] == "new_plan.md"
    assert any(reason.startswith("content_match") for reason in result["candidate_files"][0]["reasons"])
    assert "任务分解" in result["query_terms"]


def test_task_context_collector_returns_bundle_and_unresolved_when_no_candidates(tmp_path):
    root = make_workspace(tmp_path)
    intent = AgentGoalIntentService.classify("找到最近写的计划文档")
    bundle = TaskContextCollector.collect(goal_intent=intent, roots=[root], max_candidates=2)
    empty = TaskContextCollector.collect(goal_intent=intent, roots=[root], extensions=[".pdf"], max_candidates=2)

    assert bundle["summary"]["candidate_file_count"] == 2
    assert bundle["evidence"][0]["source_ref"].endswith("new_plan.md")
    assert empty["summary"]["unresolved_count"] == 1
    assert empty["unresolved_context"][0]["kind"] == "no_candidate_files"


def test_recent_artifact_finder_filters_and_sorts():
    artifacts = [
        {"filename": "old_report.md", "created_at": 1},
        {"filename": "compare_report.md", "created_at": 3},
        {"filename": "compare_report.json", "created_at": 2},
    ]

    result = RecentArtifactFinder.find(artifacts, query="compare", max_results=2)

    assert [item["filename"] for item in result] == ["compare_report.md", "compare_report.json"]
