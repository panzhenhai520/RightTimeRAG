from pathlib import Path

from agent.component.workspace_file import (
    WorkspaceFileRead,
    WorkspaceFileReadParam,
    WorkspaceFileSearch,
    WorkspaceFileSearchParam,
    WorkspaceFileWrite,
    WorkspaceFileWriteParam,
    WorkspacePatchApply,
    WorkspacePatchApplyParam,
    WorkspaceTableRead,
    WorkspaceTableReadParam,
)


class FakeCanvas:
    _run_id = "run-workspace"

    def __init__(self, variables=None):
        self.variables = variables or {}

    def get_tenant_id(self):
        return "tenant-1"

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "alpha.md").write_text("first\nsecond\nthird\n", encoding="utf-8")
    (root / "scores.csv").write_text("name,score\nalice,91\n", encoding="utf-8")
    return root


def test_workspace_file_search_node_uses_configured_root(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = WorkspaceFileSearch.__new__(WorkspaceFileSearch)
    node._canvas = FakeCanvas()
    node._param = WorkspaceFileSearchParam()
    node._param.query = "alpha"
    node._param.extensions = ["md"]

    node._invoke()

    assert node.output("count") == 1
    assert node.output("files")[0]["relative_path"] == "alpha.md"
    assert node.output("audit")["run_id"] == "run-workspace"


def test_workspace_file_read_node_reads_line_range_from_variable_path(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = WorkspaceFileRead.__new__(WorkspaceFileRead)
    node._canvas = FakeCanvas({"selected_path": "alpha.md"})
    node._param = WorkspaceFileReadParam()
    node._param.path = "selected_path"
    node._param.start_line = 2
    node._param.end_line = 3

    node._invoke()

    assert node.output("content") == "second\nthird"
    assert node.output("line_count") == 2
    assert node.output("source_ref").endswith("lines 2-3")


def test_workspace_table_read_node_outputs_structured_rows(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = WorkspaceTableRead.__new__(WorkspaceTableRead)
    node._canvas = FakeCanvas()
    node._param = WorkspaceTableReadParam()
    node._param.path = "scores.csv"

    node._invoke()

    assert node.output("headers") == ["name", "score"]
    assert node.output("rows")[0]["values"]["name"] == "alice"
    assert node.output("file")["relative_path"] == "scores.csv"


def test_workspace_file_write_node_defaults_to_dry_run(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = WorkspaceFileWrite.__new__(WorkspaceFileWrite)
    node._canvas = FakeCanvas({"write_path": "planned.md"})
    node._param = WorkspaceFileWriteParam()
    node._param.path = "write_path"
    node._param.content = "planned"

    node._invoke()

    assert not (root / "planned.md").exists()
    assert node.output("dry_run") is True
    assert node.output("file")["relative_path"] == "planned.md"


def test_workspace_patch_apply_node_defaults_to_dry_run(tmp_path, monkeypatch):
    root = make_workspace(tmp_path)
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = WorkspacePatchApply.__new__(WorkspacePatchApply)
    node._canvas = FakeCanvas()
    node._param = WorkspacePatchApplyParam()
    node._param.patch = {
        "files": [
            {
                "path": "alpha.md",
                "operations": [{"op": "replace", "old": "second", "new": "updated"}],
            }
        ]
    }

    node._invoke()

    assert (root / "alpha.md").read_text(encoding="utf-8") == "first\nsecond\nthird\n"
    assert node.output("dry_run") is True
    assert node.output("can_apply") is True
    assert "+updated" in node.output("diff")
