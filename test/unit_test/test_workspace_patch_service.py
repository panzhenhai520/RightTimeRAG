from pathlib import Path

import pytest

from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from api.db.services.workspace_patch_service import WorkspacePatchService


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "docs").mkdir()
    (root / "docs" / "alpha.md").write_text("title\nold line\nend\n", encoding="utf-8")
    (root / "docs" / "beta.md").write_text("one\ntwo\n", encoding="utf-8")
    return root


def test_workspace_patch_structured_dry_run_does_not_write(tmp_path):
    root = make_workspace(tmp_path)
    WorkspacePatchService.reset()

    result = WorkspacePatchService.dry_run(
        roots=[root],
        patch={"files": [{"path": "docs/alpha.md", "operations": [{"op": "replace", "old": "old line", "new": "new line"}]}]},
    )

    assert result["can_apply"] is True
    assert result["dry_run"] is True
    assert result["affected_files"][0]["relative_path"] == "docs/alpha.md"
    assert "+new line" in result["diff"]
    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "title\nold line\nend\n"


def test_workspace_patch_apply_and_rollback(tmp_path):
    root = make_workspace(tmp_path)
    WorkspacePatchService.reset()

    result = WorkspacePatchService.apply(
        roots=[root],
        patch={"files": [{"path": "docs/alpha.md", "operations": [{"op": "insert_after", "anchor": "title\n", "content": "inserted\n"}]}]},
        require_approval=False,
        run_id="run-patch",
    )
    rollback = WorkspacePatchService.rollback(rollback_token=result["rollback_token"], roots=[root])

    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "title\nold line\nend\n"
    assert result["rollback_token"]
    assert result["audit"]["action"] == "patch_apply"
    assert rollback["restored_files"][0]["relative_path"] == "docs/alpha.md"
    assert WorkspacePatchService.list_audit(result["patch_id"])[0]["run_id"] == "run-patch"


def test_workspace_patch_unified_diff_applies(tmp_path):
    root = make_workspace(tmp_path)
    diff = """--- a/docs/beta.md
+++ b/docs/beta.md
@@ -1,2 +1,2 @@
 one
-two
+three
"""

    result = WorkspacePatchService.apply(roots=[root], patch=diff, patch_format="unified_diff", require_approval=False)

    assert result["can_apply"] is True
    assert (root / "docs" / "beta.md").read_text(encoding="utf-8") == "one\nthree\n"


def test_workspace_patch_conflict_does_not_partially_write(tmp_path):
    root = make_workspace(tmp_path)

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspacePatchService.apply(
            roots=[root],
            require_approval=False,
            patch={
                "files": [
                    {"path": "docs/alpha.md", "operations": [{"op": "replace", "old": "old line", "new": "changed"}]},
                    {"path": "docs/beta.md", "operations": [{"op": "replace", "old": "missing", "new": "changed"}]},
                ]
            },
        )

    assert exc.value.code == "PATCH_CONFLICT"
    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "title\nold line\nend\n"
    assert (root / "docs" / "beta.md").read_text(encoding="utf-8") == "one\ntwo\n"


def test_workspace_patch_rejects_hash_mismatch(tmp_path):
    root = make_workspace(tmp_path)

    result = WorkspacePatchService.dry_run(
        roots=[root],
        expected_hashes={"docs/alpha.md": "bad"},
        patch={"files": [{"path": "docs/alpha.md", "operations": [{"op": "append", "content": "x"}]}]},
    )

    assert result["can_apply"] is False
    assert result["conflicts"][0]["error_code"] == "HASH_MISMATCH"


def test_workspace_patch_rejects_path_traversal(tmp_path):
    root = make_workspace(tmp_path)

    result = WorkspacePatchService.dry_run(
        roots=[root],
        patch={"files": [{"path": "../escape.md", "operations": [{"op": "append", "content": "x"}]}]},
    )

    assert result["can_apply"] is False
    assert result["conflicts"][0]["error_code"] == "PATH_TRAVERSAL_DENIED"


def test_workspace_patch_rollback_refuses_after_external_change(tmp_path):
    root = make_workspace(tmp_path)
    result = WorkspacePatchService.apply(
        roots=[root],
        require_approval=False,
        patch={"files": [{"path": "docs/alpha.md", "operations": [{"op": "replace", "old": "old line", "new": "new line"}]}]},
    )
    (root / "docs" / "alpha.md").write_text("external\n", encoding="utf-8")

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspacePatchService.rollback(rollback_token=result["rollback_token"], roots=[root])

    assert exc.value.code == "ROLLBACK_HASH_MISMATCH"


def test_workspace_patch_expected_hash_allows_apply(tmp_path):
    root = make_workspace(tmp_path)
    current = WorkspaceFileService.read_file(path="docs/alpha.md", roots=[root])["file"]["sha256"]

    result = WorkspacePatchService.apply(
        roots=[root],
        require_approval=False,
        expected_hashes={"docs/alpha.md": current},
        patch={"files": [{"path": "docs/alpha.md", "operations": [{"op": "delete", "old": "old line\n"}]}]},
    )

    assert result["can_apply"] is True
    assert (root / "docs" / "alpha.md").read_text(encoding="utf-8") == "title\nend\n"
