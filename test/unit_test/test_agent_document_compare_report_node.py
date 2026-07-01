from agent.component.document_compare_report import DocumentCompareReportComposer, DocumentCompareReportComposerParam
from common import settings


class FakeStorage:
    def __init__(self):
        self.saved = {}

    def put(self, tenant_id, doc_id, content):
        self.saved[(tenant_id, doc_id)] = content


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}
        self._run_id = "run-1"
        self.agent_id = "agent-1"

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)

    def get_tenant_id(self):
        return "tenant-1"


def test_document_compare_report_composer_creates_downloads_and_audit(monkeypatch):
    storage = FakeStorage()
    monkeypatch.setattr(settings, "STORAGE_IMPL", storage)
    node = DocumentCompareReportComposer.__new__(DocumentCompareReportComposer)
    node._canvas = FakeCanvas(
        {
            "documents_ref": [
                {
                    "document_id": "doc-a",
                    "filename": "law.md",
                    "source_path": "/safe/law.md",
                    "paragraphs": [{"text": "甲方应在三十日内付款。"}],
                    "audit": {"audit_id": "audit-1", "path": "/safe/law.md", "action": "read", "allowed": True},
                }
            ],
            "diff_ref": {"summary": {"replace": 1}},
            "conflicts_ref": {
                "conflicts": [
                    {
                        "severity": "high",
                        "reason_code": "deadline_longer_than_allowed",
                        "reason": "Target deadline 90 days is longer than standard deadline 30 days.",
                        "standard_item": {"text": "甲方应在三十日内付款。"},
                        "target_item": {"text": "甲方应在90日内付款。"},
                        "evidence": {"left": {"source_ref": "law.md | line 1"}, "right": {"source_ref": "contract.md | line 1"}},
                    }
                ]
            },
        }
    )
    node._id = "DocumentCompareReportComposer:Report"
    node._param = DocumentCompareReportComposerParam()
    node._param.documents = "documents_ref"
    node._param.diff = "diff_ref"
    node._param.conflicts = "conflicts_ref"
    node._param.output_formats = ["markdown", "json"]
    node._param.filename = "compare_report"

    node._invoke()

    assert node.output("report")["risk_level"] == "high"
    assert len(node.output("downloads")) == 2
    assert len(node.output("audit")["report_artifacts"]) == 2
    assert "Target deadline 90 days" in node.output("markdown")
    assert {item["filename"] for item in node.output("downloads")} == {"compare_report.md", "compare_report.json"}
    assert len(storage.saved) == 2
