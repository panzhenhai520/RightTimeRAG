import json
from zipfile import ZipFile
from io import BytesIO

from agent.artifact_service import ArtifactService
from agent.component.output_artifacts import ArtifactPackager, ChartRenderer
from common import settings


class FakeStorage:
    def __init__(self):
        self.saved = {}

    def put(self, tenant_id, doc_id, content):
        self.saved[(tenant_id, doc_id)] = content


def line_chart_spec():
    return {
        "schema_version": 1,
        "type": "line",
        "title": "History Score",
        "data": [
            {"x": "lesson-1", "y": 82},
            {"x": "lesson-2", "y": 88},
        ],
    }


def test_chart_renderer_renders_svg_without_binary_event_payload():
    svg = ChartRenderer.render_svg(line_chart_spec())

    assert svg.startswith("<svg")
    assert "History Score" in svg
    assert "<polyline" in svg
    assert "base64" not in svg


def test_chart_renderer_creates_download_artifact_without_base64(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)

    download = ChartRenderer.create_chart_download(
        tenant_id="tenant-1",
        chart_spec=line_chart_spec(),
        filename="history_score",
        run_id="run-1",
        node_id="ChartRenderer:History",
    )

    assert download["filename"] == "history_score.svg"
    assert download["mime_type"] == "image/svg+xml"
    assert download["metadata"]["kind"] == "chart"
    assert "base64" not in download
    assert storage.saved[("tenant-1", download["doc_id"])].startswith(b"<svg")
    assert ChartRenderer.build_markdown(download, "History Score").startswith("![History Score](")


def test_artifact_packager_builds_zip_with_manifest_and_artifacts(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)
    artifacts = [
        {
            "doc_id": "doc-report",
            "filename": "report.docx",
            "mime_type": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            "size": 10,
        },
        {
            "artifact_id": "doc-chart",
            "file_name": "chart.svg",
            "mime_type": "image/svg+xml",
            "size": 8,
        },
    ]
    fetcher = lambda tenant_id, doc_id: {"doc-report": b"REPORT", "doc-chart": b"<svg/>"}[doc_id]

    download, manifest = ArtifactPackager.create_package_download(
        tenant_id="tenant-1",
        artifacts=artifacts,
        manifest={"activity_id": "lesson-1"},
        filename="lesson_outputs",
        run_id="run-1",
        node_id="ArtifactPackager:Package",
        fetcher=fetcher,
    )

    assert download["filename"] == "lesson_outputs.zip"
    assert download["mime_type"] == "application/zip"
    assert "base64" not in download
    assert manifest["activity_id"] == "lesson-1"
    assert manifest["artifact_count"] == 2

    zip_bytes = storage.saved[("tenant-1", download["doc_id"])]
    with ZipFile(BytesIO(zip_bytes)) as zf:
        assert set(zf.namelist()) == {"manifest.json", "report.docx", "chart.svg"}
        manifest_in_zip = json.loads(zf.read("manifest.json").decode("utf-8"))
        assert manifest_in_zip["artifact_count"] == 2
        assert zf.read("report.docx") == b"REPORT"
        assert zf.read("chart.svg") == b"<svg/>"


def test_artifact_service_knows_report_chart_and_package_mime_types():
    assert ArtifactService.guess_mime_type("chart.svg") == "image/svg+xml"
    assert ArtifactService.guess_mime_type("manifest.json") == "application/json"
    assert ArtifactService.guess_mime_type("outputs.zip") == "application/zip"
