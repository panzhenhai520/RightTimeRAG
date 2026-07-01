from agent.component.document_compare import (
    DocumentConflictDetector,
    DocumentConflictDetectorParam,
    DocumentDiff,
    DocumentDiffParam,
    DocumentSemanticComparer,
    DocumentSemanticComparerParam,
    TableDiff,
    TableDiffParam,
)


class FakeCanvas:
    def __init__(self, variables=None):
        self.variables = variables or {}

    def is_reff(self, value):
        return isinstance(value, str) and value in self.variables

    def get_variable_value(self, value):
        return self.variables.get(value)


def left_document():
    return {
        "paragraphs": [
            {"text": "甲方应在三十日内付款。", "source_ref": "left.md | line 1"},
            {"text": "乙方不得泄露商业秘密。", "source_ref": "left.md | line 2"},
        ],
        "tables": [{"headers": ["name"], "rows": [{"row_index": 2, "values": {"name": "alice"}}], "source_ref": "left.csv | table"}],
    }


def right_document():
    return {
        "paragraphs": [
            {"text": "甲方应在90日内付款。", "source_ref": "right.md | line 1"},
            {"text": "乙方可以向第三方披露商业秘密。", "source_ref": "right.md | line 2"},
        ],
        "tables": [{"headers": ["name"], "rows": [{"row_index": 2, "values": {"name": "bob"}}], "source_ref": "right.csv | table"}],
    }


def test_document_diff_node_outputs_hunks():
    node = DocumentDiff.__new__(DocumentDiff)
    node._canvas = FakeCanvas({"left_ref": left_document(), "right_ref": right_document()})
    node._param = DocumentDiffParam()
    node._param.left_document = "left_ref"
    node._param.right_document = "right_ref"

    node._invoke()

    assert node.output("summary")["replace"] == 2
    assert node.output("hunks")[0]["op"] == "replace"


def test_table_diff_node_outputs_schema_and_hunks():
    node = TableDiff.__new__(TableDiff)
    node._canvas = FakeCanvas({"left_ref": left_document(), "right_ref": right_document()})
    node._param = TableDiffParam()
    node._param.left_document = "left_ref"
    node._param.right_document = "right_ref"

    node._invoke()

    assert node.output("summary")["replace"] == 1
    assert node.output("hunks")[0]["right"][0]["values"]["name"] == "bob"


def test_semantic_comparer_and_conflict_detector_nodes():
    standard = [
        {"item_id": "s1", "text": "甲方应在三十日内付款。"},
        {"item_id": "s2", "text": "乙方不得泄露商业秘密。"},
    ]
    target = [
        {"item_id": "t1", "text": "甲方应在90日内付款。"},
        {"item_id": "t2", "text": "乙方可以向第三方披露商业秘密。"},
    ]

    comparer = DocumentSemanticComparer.__new__(DocumentSemanticComparer)
    comparer._canvas = FakeCanvas({"standard_ref": standard, "target_ref": target})
    comparer._param = DocumentSemanticComparerParam()
    comparer._param.left_items = "standard_ref"
    comparer._param.right_items = "target_ref"
    comparer._invoke()

    detector = DocumentConflictDetector.__new__(DocumentConflictDetector)
    detector._canvas = FakeCanvas({"standard_ref": standard, "target_ref": target})
    detector._param = DocumentConflictDetectorParam()
    detector._param.standard_items = "standard_ref"
    detector._param.target_items = "target_ref"
    detector._invoke()

    assert comparer.output("summary")["matched"] == 2
    assert {item["reason_code"] for item in detector.output("conflicts")} == {
        "deadline_longer_than_allowed",
        "prohibited_action_permitted",
    }
