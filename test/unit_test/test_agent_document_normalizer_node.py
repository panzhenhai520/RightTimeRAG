from pathlib import Path

from agent.component.document_normalizer import DocumentNormalizer, DocumentNormalizerParam


class FakeCanvas:
    _run_id = "run-normalize"

    def __init__(self, variables=None):
        self.variables = variables or {}

    def get_tenant_id(self):
        return "tenant-1"

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def test_document_normalizer_node_outputs_document_blocks(tmp_path, monkeypatch):
    root = tmp_path / "workspace"
    root.mkdir()
    (root / "contract.txt").write_text("第一条 合同有效。\n\n第二条 按时付款。\n", encoding="utf-8")
    monkeypatch.setenv("AGENT_WORKSPACE_ROOTS", str(root))

    node = DocumentNormalizer.__new__(DocumentNormalizer)
    node._canvas = FakeCanvas({"selected_path": "contract.txt"})
    node._param = DocumentNormalizerParam()
    node._param.path = "selected_path"
    node._param.chunk_chars = 200

    node._invoke()

    assert node.output("document")["filename"] == "contract.txt"
    assert len(node.output("paragraphs")) == 2
    assert "按时付款" in node.output("chunks")[0]["text"]
    assert node.output("audit")["run_id"] == "run-normalize"
