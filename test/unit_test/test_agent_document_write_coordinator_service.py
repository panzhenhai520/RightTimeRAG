import json
from concurrent.futures import ThreadPoolExecutor

import pytest

from api.db.services import agent_document_write_coordinator_service
from api.db.services.agent_document_write_coordinator_service import (
    AgentDocumentWriteCoordinatorService,
    DocumentWriteCoordinatorError,
)


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set_obj(self, key, value, ttl=None):
        self.store[key] = json.dumps(value, ensure_ascii=False)
        return True


@pytest.fixture()
def fake_redis(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(agent_document_write_coordinator_service, "REDIS_CONN", redis)
    return redis


def proposal(**overrides):
    payload = AgentDocumentWriteCoordinatorService.build_patch_proposal(
        proposal_id="proposal-a",
        base_document_id="doc-1",
        base_version=1,
        agent_id="teacher-a",
        run_id="run-a",
        summary="补充付款期限",
        patches=[
            {
                "operation": "insert_after",
                "target": "付款条款：",
                "text": "应在验收后30日内支付。",
            }
        ],
        references=[{"doc_id": "std-1", "chunk_id": "chunk-1"}],
        confidence=0.88,
    )
    payload.update(overrides)
    return payload


def test_publish_snapshot_and_get_snapshot(fake_redis):
    snapshot = AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
        metadata={"title": "合同A"},
    )

    loaded = AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")

    assert snapshot["version"] == 1
    assert snapshot["snapshot_id"] == "doc-1:v1"
    assert loaded["content"] == "合同正文\n付款条款：\n"
    assert loaded["content_hash"] == snapshot["content_hash"]
    assert loaded["metadata"]["title"] == "合同A"


def test_submit_patch_proposal_does_not_modify_document(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
    )

    stored = AgentDocumentWriteCoordinatorService.submit_patch_proposal(
        tenant_id="tenant-1",
        proposal=proposal(),
        authorized_agent_ids=["teacher-a"],
    )
    snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")

    assert stored["proposal_id"] == "proposal-a"
    assert stored["base_snapshot_id"] == "doc-1:v1"
    assert snapshot["version"] == 1
    assert snapshot["content"] == "合同正文\n付款条款：\n"


def test_apply_write_request_creates_new_version_and_audit(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
        audit={"operator": "importer"},
    )
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(tenant_id="tenant-1", proposal=proposal())

    result = AgentDocumentWriteCoordinatorService.apply_write_request(
        tenant_id="tenant-1",
        document_id="doc-1",
        expected_version=1,
        selected_proposals=["proposal-a"],
        audit={"meeting_id": "meeting-1", "turn_id": "turn-1", "operator": "god"},
        authorized_agent_ids=["teacher-a"],
    )
    snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")
    audit = AgentDocumentWriteCoordinatorService.list_audit(tenant_id="tenant-1", document_id="doc-1")

    assert result["status"] == "succeeded"
    assert result["new_version"] == 2
    assert snapshot["version"] == 2
    assert "应在验收后30日内支付。" in snapshot["content"]
    assert audit[-1]["event"] == "write_applied"
    assert audit[-1]["meeting_id"] == "meeting-1"
    assert audit[-1]["agent_ids"] == ["teacher-a"]
    assert audit[-1]["run_ids"] == ["run-a"]


def test_apply_write_request_rejects_version_conflict(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
    )
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(tenant_id="tenant-1", proposal=proposal())
    AgentDocumentWriteCoordinatorService.apply_write_request(
        tenant_id="tenant-1",
        document_id="doc-1",
        expected_version=1,
        selected_proposals=["proposal-a"],
    )

    with pytest.raises(DocumentWriteCoordinatorError) as exc:
        AgentDocumentWriteCoordinatorService.apply_write_request(
            tenant_id="tenant-1",
            document_id="doc-1",
            expected_version=1,
            selected_proposals=["proposal-a"],
        )

    assert exc.value.code == "VERSION_CONFLICT"
    assert exc.value.details["current_version"] == 2


def test_same_document_writes_are_serialized_by_version(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
    )
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(tenant_id="tenant-1", proposal=proposal(proposal_id="proposal-a"))
    AgentDocumentWriteCoordinatorService.submit_patch_proposal(
        tenant_id="tenant-1",
        proposal=proposal(
            proposal_id="proposal-b",
            agent_id="teacher-b",
            run_id="run-b",
            patches=[{"operation": "append", "text": "\n争议解决：提交仲裁。"}],
        ),
    )

    def apply(item):
        try:
            return AgentDocumentWriteCoordinatorService.apply_write_request(
                tenant_id="tenant-1",
                document_id="doc-1",
                expected_version=1,
                selected_proposals=[item],
            )
        except DocumentWriteCoordinatorError as exc:
            return exc.to_dict()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(apply, ["proposal-a", "proposal-b"]))

    assert sum(1 for item in results if item.get("status") == "succeeded") == 1
    assert sum(1 for item in results if item.get("error_code") == "VERSION_CONFLICT") == 1
    snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")
    assert snapshot["version"] == 2


def test_different_documents_can_advance_independently(fake_redis):
    for document_id in ("doc-1", "doc-2"):
        AgentDocumentWriteCoordinatorService.publish_snapshot(
            tenant_id="tenant-1",
            document_id=document_id,
            version=1,
            content="正文",
        )
        AgentDocumentWriteCoordinatorService.submit_patch_proposal(
            tenant_id="tenant-1",
            proposal=proposal(
                proposal_id=f"proposal-{document_id}",
                base_document_id=document_id,
                patches=[{"operation": "append", "text": f"\n{document_id}补充"}],
            ),
        )
        AgentDocumentWriteCoordinatorService.apply_write_request(
            tenant_id="tenant-1",
            document_id=document_id,
            expected_version=1,
            selected_proposals=[f"proposal-{document_id}"],
        )

    assert AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")["version"] == 2
    assert AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-2")["version"] == 2


def test_unauthorized_agent_cannot_submit_or_apply(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="合同正文\n付款条款：\n",
    )

    with pytest.raises(DocumentWriteCoordinatorError) as submit_exc:
        AgentDocumentWriteCoordinatorService.submit_patch_proposal(
            tenant_id="tenant-1",
            proposal=proposal(agent_id="teacher-b"),
            authorized_agent_ids=["teacher-a"],
        )

    assert submit_exc.value.code == "PERMISSION_DENIED"
    audit = AgentDocumentWriteCoordinatorService.list_audit(tenant_id="tenant-1", document_id="doc-1")
    assert audit[-1]["event"] == "permission_denied"
    assert audit[-1]["action"] == "submit_patch_proposal"
    assert audit[-1]["agent_id"] == "teacher-b"

    AgentDocumentWriteCoordinatorService.submit_patch_proposal(tenant_id="tenant-1", proposal=proposal(agent_id="teacher-b"))
    with pytest.raises(DocumentWriteCoordinatorError) as apply_exc:
        AgentDocumentWriteCoordinatorService.apply_write_request(
            tenant_id="tenant-1",
            document_id="doc-1",
            expected_version=1,
            selected_proposals=["proposal-a"],
            authorized_agent_ids=["teacher-a"],
        )

    assert apply_exc.value.code == "PERMISSION_DENIED"
    audit = AgentDocumentWriteCoordinatorService.list_audit(tenant_id="tenant-1", document_id="doc-1")
    assert audit[-1]["event"] == "permission_denied"
    assert audit[-1]["action"] == "apply_write_request"
    assert audit[-1]["agent_id"] == "teacher-b"


def test_rollback_creates_new_version_from_old_snapshot(fake_redis):
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=1,
        content="v1",
    )
    AgentDocumentWriteCoordinatorService.publish_snapshot(
        tenant_id="tenant-1",
        document_id="doc-1",
        version=2,
        content="v2",
    )

    result = AgentDocumentWriteCoordinatorService.rollback(
        tenant_id="tenant-1",
        document_id="doc-1",
        target_version=1,
        expected_version=2,
        audit={"operator": "reviewer"},
    )
    snapshot = AgentDocumentWriteCoordinatorService.get_snapshot(tenant_id="tenant-1", document_id="doc-1")
    audit = AgentDocumentWriteCoordinatorService.list_audit(tenant_id="tenant-1", document_id="doc-1")

    assert result["new_version"] == 3
    assert snapshot["content"] == "v1"
    assert snapshot["metadata"]["rolled_back_to"] == 1
    assert audit[-1]["event"] == "rollback_applied"
    assert audit[-1]["operator"] == "reviewer"
