from agent.component.document_extractors import (
    ClauseExtractor,
    ClauseExtractorParam,
    DefinitionExtractor,
    DefinitionExtractorParam,
    RiskPointExtractor,
    RiskPointExtractorParam,
    TableFactExtractor,
    TableFactExtractorParam,
)


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def sample_document():
    return {
        "document_id": "doc-1",
        "paragraphs": [
            {"text": "第一条 甲方应在收到发票后三十日内付款。", "source_ref": "a.md | line 1"},
            {"text": "第二条 乙方不得泄露商业秘密。", "source_ref": "a.md | line 2"},
            {"text": "本协议所称服务费是指客户支付的费用。", "source_ref": "a.md | line 3"},
        ],
        "tables": [{"headers": ["name"], "rows": [{"row_index": 2, "values": {"name": "alice"}}], "source_ref": "a.csv | table"}],
    }


def test_clause_extractor_node_outputs_clause_items():
    node = ClauseExtractor.__new__(ClauseExtractor)
    node._canvas = FakeCanvas({"document_ref": sample_document()})
    node._param = ClauseExtractorParam()
    node._param.document = "document_ref"

    node._invoke()

    assert len(node.output("clauses")) == 2
    assert node.output("clauses")[0]["item_type"] == "clause"
    assert node.output("references")[0]["source_ref"] == "a.md | line 1"


def test_definition_extractor_node_outputs_definition_items():
    node = DefinitionExtractor.__new__(DefinitionExtractor)
    node._canvas = FakeCanvas({"document_ref": sample_document()})
    node._param = DefinitionExtractorParam()
    node._param.document = "document_ref"

    node._invoke()

    assert node.output("definitions")[0]["item_type"] == "definition"
    assert node.output("definitions")[0]["term"] == "本协议所称服务费"


def test_risk_and_table_extractors_output_dedicated_keys():
    risk = RiskPointExtractor.__new__(RiskPointExtractor)
    risk._canvas = FakeCanvas({"document_ref": sample_document()})
    risk._param = RiskPointExtractorParam()
    risk._param.document = "document_ref"
    risk._invoke()

    table = TableFactExtractor.__new__(TableFactExtractor)
    table._canvas = FakeCanvas({"document_ref": sample_document()})
    table._param = TableFactExtractorParam()
    table._param.document = "document_ref"
    table._invoke()

    assert risk.output("risk_points")[0]["severity"] == "high"
    assert table.output("table_facts")[0]["values"]["name"] == "alice"
