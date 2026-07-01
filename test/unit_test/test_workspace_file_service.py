from pathlib import Path

import pytest

from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "alpha.md").write_text("# Alpha\nline two\nline three\n", encoding="utf-8")
    (root / "docs" / "beta.txt").write_text("beta one\nbeta two\n", encoding="utf-8")
    (root / "table.csv").write_text("name,score\nalice,91\nbob,88\n", encoding="utf-8")
    return root


def test_workspace_file_service_lists_and_searches_allowed_files(tmp_path):
    root = make_workspace(tmp_path)

    listed = WorkspaceFileService.list_files(path="docs", roots=[root], extensions=[".md"], include_dirs=False)
    searched = WorkspaceFileService.search_files(query="beta", roots=[root], extensions="txt")

    assert listed["count"] == 1
    assert listed["files"][0]["relative_path"] == "docs/alpha.md"
    assert searched["count"] == 1
    assert searched["files"][0]["name"] == "beta.txt"
    assert listed["audit"]["allowed"] is True


def test_workspace_file_service_rejects_path_traversal(tmp_path):
    root = make_workspace(tmp_path)
    outside = tmp_path / "secret.txt"
    outside.write_text("secret", encoding="utf-8")

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspaceFileService.read_file(path="../secret.txt", roots=[root])

    assert exc.value.code == "PATH_OUTSIDE_ROOT"


def test_workspace_file_service_reads_file_and_line_range(tmp_path):
    root = make_workspace(tmp_path)

    full = WorkspaceFileService.read_file(path="docs/alpha.md", roots=[root])
    partial = WorkspaceFileService.read_range(path="docs/alpha.md", roots=[root], start_line=2, end_line=3)

    assert "line three" in full["content"]
    assert full["file"]["sha256"]
    assert partial["content"] == "line two\nline three"
    assert [item["line_number"] for item in partial["lines"]] == [2, 3]
    assert "lines 2-3" in partial["source_ref"]


def test_workspace_file_service_reads_csv_as_table(tmp_path):
    root = make_workspace(tmp_path)

    table = WorkspaceFileService.read_table(path="table.csv", roots=[root], max_rows=10)

    assert table["headers"] == ["name", "score"]
    assert table["rows"][0]["row_index"] == 2
    assert table["rows"][0]["values"] == {"name": "alice", "score": "91"}
    assert table["file"]["relative_path"] == "table.csv"


def test_workspace_file_service_rejects_unsupported_table_format(tmp_path):
    root = make_workspace(tmp_path)

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspaceFileService.read_table(path="docs/alpha.md", roots=[root])

    assert exc.value.code == "UNSUPPORTED_TABLE_FORMAT"
