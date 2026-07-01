from agent.artifact_service import ArtifactService
from agent.artifact_registry_service import AgentArtifactRegistryService, ArtifactPermissionError
from agent import artifact_registry_service
from common import settings
import json

import pytest


class FakeRedis:
    def __init__(self):
        self.store = {}

    def get(self, key):
        return self.store.get(key)

    def set_obj(self, key, value, ttl=None):
        self.store[key] = json.dumps(value, ensure_ascii=False)
        return True


class FakeStorage:
    def __init__(self):
        self.saved = {}

    def put(self, tenant_id, doc_id, content):
        self.saved[(tenant_id, doc_id)] = content


def test_artifact_service_creates_compatible_download_info(monkeypatch):
    storage = FakeStorage()
    redis = FakeRedis()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)
    monkeypatch.setattr(artifact_registry_service, "REDIS_CONN", redis)

    info = ArtifactService.create_download_info(
        "tenant-1",
        b"hello",
        "report.docx",
        run_id="run-1",
        node_id="DocGenerator:Report",
        metadata={"kind": "report"},
    )

    assert info["artifact_id"] == info["doc_id"]
    assert info["filename"] == "report.docx"
    assert info["mime_type"] == "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    assert info["size"] == 5
    assert info["download_url"].endswith(f"{info['doc_id']}&run_id=run-1")
    assert info["run_id"] == "run-1"
    assert info["node_id"] == "DocGenerator:Report"
    assert info["metadata"] == {
        "kind": "report",
        "run_id": "run-1",
        "node_id": "DocGenerator:Report",
    }
    assert storage.saved[("tenant-1", info["doc_id"])] == b"hello"
    record = AgentArtifactRegistryService.get(tenant_id="tenant-1", artifact_id=info["doc_id"])
    assert record["run_id"] == "run-1"
    assert record["node_id"] == "DocGenerator:Report"


def test_artifact_attachment_keeps_legacy_and_new_identifiers():
    attachment = ArtifactService.attachment_from_download(
        {
            "artifact_id": "artifact-1",
            "doc_id": "doc-1",
            "filename": "report.xlsx",
            "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            "size": 10,
            "download_url": "/v1/agents/download?id=doc-1",
        }
    )

    assert attachment == {
        "artifact_id": "artifact-1",
        "doc_id": "doc-1",
        "format": "xlsx",
        "file_name": "report.xlsx",
        "mime_type": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "size": 10,
        "download_url": "/v1/agents/download?id=doc-1",
    }


def test_artifact_registry_rejects_wrong_run_and_audits(monkeypatch):
    redis = FakeRedis()
    monkeypatch.setattr(artifact_registry_service, "REDIS_CONN", redis)
    AgentArtifactRegistryService.register(
        tenant_id="tenant-1",
        artifact_id="artifact-1",
        filename="report.docx",
        run_id="run-1",
    )

    with pytest.raises(ArtifactPermissionError) as exc:
        AgentArtifactRegistryService.authorize_download(
            tenant_id="tenant-1",
            artifact_id="artifact-1",
            requested_run_id="run-2",
        )

    assert exc.value.code == "PERMISSION_DENIED"
    record = AgentArtifactRegistryService.get(tenant_id="tenant-1", artifact_id="artifact-1")
    assert record["audit"][-1]["event"] == "permission_denied"
    assert record["audit"][-1]["reason"] == "run_id_mismatch"
