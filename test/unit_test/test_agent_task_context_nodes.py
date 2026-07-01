from pathlib import Path

from agent.component.task_context import (
    RecentArtifactFinder,
    RecentArtifactFinderParam,
    RelevantFileResolver,
    RelevantFileResolverParam,
    TaskContextCollector,
    TaskContextCollectorParam,
)
from api.db.services.agent_goal_intent_service import AgentGoalIntentService


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "plan.md").write_text("# Plan\n任务分解\n", encoding="utf-8")
    return root


def test_relevant_file_resolver_node_outputs_candidates(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root))
    intent = AgentGoalIntentService.classify("找到任务分解计划文档")

    node = RelevantFileResolver.__new__(RelevantFileResolver)
    node._canvas = FakeCanvas({"intent_ref": intent})
    node._param = RelevantFileResolverParam()
    node._param.goal_intent = "intent_ref"
    node._param.query = "任务分解"

    node._invoke()

    assert node.output("candidate_files")[0]["file"]["name"] == "plan.md"
    assert "任务分解" in node.output("query_terms")


def test_task_context_collector_and_artifact_finder_nodes(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOT", str(root))
    intent = AgentGoalIntentService.classify("找到计划文档")

    collector = TaskContextCollector.__new__(TaskContextCollector)
    collector._canvas = FakeCanvas({"intent_ref": intent})
    collector._param = TaskContextCollectorParam()
    collector._param.goal_intent = "intent_ref"
    collector._param.query = "plan"
    collector._invoke()

    finder = RecentArtifactFinder.__new__(RecentArtifactFinder)
    finder._canvas = FakeCanvas({"artifacts_ref": [{"filename": "task_report.md", "created_at": 2}]})
    finder._param = RecentArtifactFinderParam()
    finder._param.artifacts = "artifacts_ref"
    finder._param.query = "task"
    finder._invoke()

    assert collector.output("summary")["candidate_file_count"] == 1
    assert finder.output("candidate_artifacts")[0]["filename"] == "task_report.md"
