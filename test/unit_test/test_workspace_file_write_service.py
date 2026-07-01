from pathlib import Path

import pytest

from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from api.db.services.workspace_file_write_service import WorkspaceFileWriteService


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "alpha.md").write_text("alpha\n", encoding="utf-8")
    return root


def test_workspace_file_write_creates_file_with_audit(tmp_path):
    root = make_workspace(tmp_path)
    WorkspaceFileWriteService.reset()

    result = WorkspaceFileWriteService.write_file(
        path="docs/new.md",
        roots=[root],
        content="# New\n",
        mode="create",
        dry_run=False,
        require_approval=False,
        tenant_id="tenant-1",
        run_id="run-1",
    )

    assert (root / "docs" / "new.md").read_text(encoding="utf-8") == "# New\n"
    assert result["file"]["relative_path"] == "docs/new.md"
    assert result["changed"] is True
    assert result["audit"]["action"] == "write_file"
    assert WorkspaceFileWriteService.list_audit(result["write_id"])[0]["run_id"] == "run-1"


def test_workspace_file_write_dry_run_does_not_touch_file(tmp_path):
    root = make_workspace(tmp_path)

    result = WorkspaceFileWriteService.write_file(
        path="docs/draft.md",
        roots=[root],
        content="draft",
        mode="create",
        dry_run=True,
    )

    assert not (root / "docs" / "draft.md").exists()
    assert result["dry_run"] is True
    assert result["file"]["relative_path"] == "docs/draft.md"
    assert "+draft" in result["diff"]


def test_workspace_file_write_overwrite_checks_expected_hash(tmp_path):
    root = make_workspace(tmp_path)
    current = WorkspaceFileService.read_file(path="docs/alpha.md", roots=[root])["file"]["sha256"]

    result = WorkspaceFileWriteService.write_file(
        path="docs/alpha.md",
        roots=[root],
        content="updated\n",
        mode="overwrite",
        expected_hash=current,
        dry_run=False,
        require_approval=False,
    )

    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "updated\n"
    assert result["before_hash"] == current


def test_workspace_file_write_rejects_hash_mismatch(tmp_path):
    root = make_workspace(tmp_path)

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspaceFileWriteService.write_file(
            path="docs/alpha.md",
            roots=[root],
            content="updated\n",
            mode="overwrite",
            expected_hash="bad",
            dry_run=False,
            require_approval=False,
        )

    assert exc.value.code == "HASH_MISMATCH"
    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "alpha\n"


def test_workspace_file_write_appends_content(tmp_path):
    root = make_workspace(tmp_path)

    WorkspaceFileWriteService.write_file(
        path="docs/alpha.md",
        roots=[root],
        content="beta\n",
        mode="append",
        dry_run=False,
        require_approval=False,
    )

    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "alpha\nbeta\n"


def test_workspace_file_write_rejects_path_traversal_and_absolute_path(tmp_path):
    root = make_workspace(tmp_path)

    with pytest.raises(WorkspaceFileError) as traversal:
        WorkspaceFileWriteService.write_file(path="../escape.md", roots=[root], content="x", dry_run=False)
    with pytest.raises(WorkspaceFileError) as absolute:
        WorkspaceFileWriteService.write_file(path=str(root / "escape.md"), roots=[root], content="x", dry_run=False)

    assert traversal.value.code == "PATH_TRAVERSAL_DENIED"
    assert absolute.value.code == "ABSOLUTE_PATH_DENIED"
