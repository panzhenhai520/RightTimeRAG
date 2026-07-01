from pathlib import Path

import pytest

from api.db.services.agent_task_approval_service import AgentTaskApprovalService
from api.db.services.agent_task_model_service import AgentTaskModelService
from api.db.services.workspace_file_service import WorkspaceFileError
from api.db.services.workspace_file_write_service import WorkspaceFileWriteService
from api.db.services.workspace_patch_service import WorkspacePatchService


def setup_function():
    AgentTaskModelService.reset()
    AgentTaskApprovalService.reset()
    WorkspaceFileWriteService.reset()
    WorkspacePatchService.reset()


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "alpha.md").write_text("old\n", encoding="utf-8")
    return root


def test_workspace_file_write_requires_approval_before_real_write(tmp_path):
    root = make_workspace(tmp_path)

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspaceFileWriteService.write_file(
            path="new.md",
            roots=[root],
            content="new\n",
            mode="create",
            dry_run=False,
            task_id="task-workspace-write",
            requester_id="user-1",
        )

    approval = exc.value.details["approval"]
    assert exc.value.code == "APPROVAL_REQUIRED"
    assert approval["status"] == "pending"
    assert not (root / "new.md").exists()

    AgentTaskApprovalService.decide(approval["approval_id"], approved=True, reviewer_id="reviewer-1")
    result = WorkspaceFileWriteService.write_file(
        path="new.md",
        roots=[root],
        content="new\n",
        mode="create",
        dry_run=False,
        task_id="task-workspace-write",
        approval_id=approval["approval_id"],
    )

    assert (root / "new.md").read_text(encoding="utf-8") == "new\n"
    assert result["approval"]["status"] == "approved"


def test_workspace_patch_apply_requires_approval_before_real_write(tmp_path):
    root = make_workspace(tmp_path)
    patch = {"files": [{"path": "alpha.md", "operations": [{"op": "replace", "old": "old", "new": "new"}]}]}

    with pytest.raises(WorkspaceFileError) as exc:
        WorkspacePatchService.apply(
            roots=[root],
            patch=patch,
            task_id="task-workspace-patch",
            requester_id="user-1",
        )

    approval = exc.value.details["approval"]
    assert exc.value.code == "APPROVAL_REQUIRED"
    assert approval["status"] == "pending"
    assert (root / "alpha.md").read_text(encoding="utf-8") == "old\n"

    AgentTaskApprovalService.decide(approval["approval_id"], approved=True, reviewer_id="reviewer-1")
    result = WorkspacePatchService.apply(
        roots=[root],
        patch=patch,
        task_id="task-workspace-patch",
        approval_id=approval["approval_id"],
    )

    assert (root / "alpha.md").read_text(encoding="utf-8") == "new\n"
    assert result["approval"]["status"] == "approved"


def test_workspace_write_manual_approve_flag_allows_component_style_flow(tmp_path):
    root = make_workspace(tmp_path)

    result = WorkspaceFileWriteService.write_file(
        path="manual.md",
        roots=[root],
        content="ok\n",
        mode="create",
        dry_run=False,
        manual_approved=True,
    )

    assert (root / "manual.md").read_text(encoding="utf-8") == "ok\n"
    assert result["approval"]["source"] == "manual_approve"
