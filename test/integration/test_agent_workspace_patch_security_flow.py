from pathlib import Path

import pytest

from api.db.services.agent_task_approval_service import AgentTaskApprovalService
from api.db.services.agent_task_model_service import AgentTaskModelService
from api.db.services.workspace_file_service import WorkspaceFileError
from api.db.services.workspace_patch_service import WorkspacePatchService


def setup_function():
    AgentTaskModelService.reset()
    AgentTaskApprovalService.reset()
    WorkspacePatchService.reset()


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "alpha.md").write_text("alpha old\n", encoding="utf-8")
    (root / "beta.md").write_text("beta old\n", encoding="utf-8")
    return root


@pytest.mark.p1
def test_workspace_patch_security_rejects_escape_and_conflict(tmp_path):
    root = make_workspace(tmp_path)

    escaped = WorkspacePatchService.dry_run(
        roots=[root],
        patch={"files": [{"path": "../outside.md", "operations": [{"op": "append", "content": "x"}]}]},
    )
    assert escaped["can_apply"] is False
    assert escaped["conflicts"][0]["error_code"] == "PATH_TRAVERSAL_DENIED"

    with pytest.raises(WorkspaceFileError) as conflict:
        WorkspacePatchService.apply(
            roots=[root],
            require_approval=False,
            patch={
                "files": [
                    {"path": "alpha.md", "operations": [{"op": "replace", "old": "alpha old", "new": "alpha new"}]},
                    {"path": "beta.md", "operations": [{"op": "replace", "old": "missing", "new": "beta new"}]},
                ]
            },
        )

    assert conflict.value.code == "PATCH_CONFLICT"
    assert (root / "alpha.md").read_text(encoding="utf-8") == "alpha old\n"
    assert (root / "beta.md").read_text(encoding="utf-8") == "beta old\n"


@pytest.mark.p1
def test_workspace_patch_security_refuses_over_limit_patch(tmp_path):
    root = make_workspace(tmp_path)

    result = WorkspacePatchService.dry_run(
        roots=[root],
        max_changed_lines=1,
        patch={
            "files": [
                {
                    "path": "alpha.md",
                    "operations": [{"op": "replace", "old": "alpha old", "new": "alpha new\nsecond line"}],
                }
            ]
        },
    )

    assert result["can_apply"] is False
    assert any(item["error_code"] == "PATCH_TOO_LARGE" for item in result["conflicts"])
    assert (root / "alpha.md").read_text(encoding="utf-8") == "alpha old\n"
