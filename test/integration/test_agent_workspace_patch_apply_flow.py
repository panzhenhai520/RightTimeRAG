from pathlib import Path

import pytest

from api.db.services.agent_task_approval_service import AgentTaskApprovalService
from api.db.services.agent_task_model_service import AgentTaskModelService
from api.db.services.workspace_file_service import WorkspaceFileError, WorkspaceFileService
from api.db.services.workspace_patch_service import WorkspacePatchService


def setup_function():
    AgentTaskModelService.reset()
    AgentTaskApprovalService.reset()
    WorkspacePatchService.reset()


def make_workspace(tmp_path: Path) -> Path:
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "contract.md").write_text("# Contract\nold clause\n", encoding="utf-8")
    return root


@pytest.mark.p1
def test_agent_workspace_patch_apply_review_rollback_flow(tmp_path):
    root = make_workspace(tmp_path)

    read = WorkspaceFileService.read_file(path="contract.md", roots=[root], run_id="run-e2e")
    patch = {
        "files": [
            {
                "path": read["file"]["relative_path"],
                "expected_hash": read["file"]["sha256"],
                "operations": [{"op": "replace", "old": "old clause", "new": "new clause"}],
            }
        ]
    }

    plan = WorkspacePatchService.dry_run(roots=[root], patch=patch, run_id="run-e2e")
    assert plan["can_apply"] is True
    assert "+new clause" in plan["diff"]
    assert (root / "contract.md").read_text(encoding="utf-8") == "# Contract\nold clause\n"

    with pytest.raises(WorkspaceFileError) as blocked:
        WorkspacePatchService.apply(roots=[root], patch=patch, task_id="task-e2e-patch", run_id="run-e2e")
    approval = blocked.value.details["approval"]
    assert approval["status"] == "pending"
    assert (root / "contract.md").read_text(encoding="utf-8") == "# Contract\nold clause\n"

    AgentTaskApprovalService.decide(approval["approval_id"], approved=True, reviewer_id="reviewer-1")
    applied = WorkspacePatchService.apply(
        roots=[root],
        patch=patch,
        task_id="task-e2e-patch",
        approval_id=approval["approval_id"],
        run_id="run-e2e",
    )
    assert applied["can_apply"] is True
    assert (root / "contract.md").read_text(encoding="utf-8") == "# Contract\nnew clause\n"

    rollback = WorkspacePatchService.rollback(
        rollback_token=applied["rollback_token"],
        roots=[root],
        run_id="run-e2e",
    )
    audit_actions = {item["action"] for item in WorkspacePatchService.list_audit(applied["patch_id"])}

    assert rollback["restored_files"][0]["relative_path"] == "contract.md"
    assert (root / "contract.md").read_text(encoding="utf-8") == "# Contract\nold clause\n"
    assert {"patch_apply", "patch_rollback"}.issubset(audit_actions)
