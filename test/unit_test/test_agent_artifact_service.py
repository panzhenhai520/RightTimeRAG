from agent.artifact_service import ArtifactService
from common import settings


class FakeStorage:
    def __init__(self):
        self.saved = {}

    def put(self, tenant_id, doc_id, content):
        self.saved[(tenant_id, doc_id)] = content


def test_artifact_service_creates_compatible_download_info(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)

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
    assert info["download_url"].endswith(info["doc_id"])
    assert info["run_id"] == "run-1"
    assert info["node_id"] == "DocGenerator:Report"
    assert info["metadata"] == {
        "kind": "report",
        "run_id": "run-1",
        "node_id": "DocGenerator:Report",
    }
    assert storage.saved[("tenant-1", info["doc_id"])] == b"hello"


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
