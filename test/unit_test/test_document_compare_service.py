from api.db.services.document_compare_service import DocumentCompareService


def left_document():
    return {
        "document_id": "left",
        "paragraphs": [
            {"text": "# 付款条款", "source_ref": "left.md | lines 0-0"},
            {"text": "第一条 甲方应在收到发票后三十日内付款。", "source_ref": "left.md | lines 1-1"},
            {"text": "第二条 乙方不得泄露商业秘密。", "source_ref": "left.md | lines 2-2"},
        ],
        "sections": [{"title": "付款条款", "section_path": ["付款条款"], "source_ref": "left.md | lines 0-0"}],
        "tables": [
            {
                "headers": ["项目", "金额"],
                "rows": [{"row_index": 2, "values": {"项目": "服务费", "金额": "10000"}}],
                "source_ref": "left.csv | table",
            }
        ],
    }


def right_document():
    return {
        "document_id": "right",
        "paragraphs": [
            {"text": "# 结算条款", "source_ref": "right.md | lines 0-0"},
            {"text": "第一条 甲方应在收到发票后90日内付款。", "source_ref": "right.md | lines 1-1"},
            {"text": "第二条 乙方不得泄露商业秘密。", "source_ref": "right.md | lines 2-2"},
            {"text": "第三条 本合同自签署日起生效。", "source_ref": "right.md | lines 3-3"},
        ],
        "sections": [{"title": "结算条款", "section_path": ["结算条款"], "source_ref": "right.md | lines 0-0"}],
        "tables": [
            {
                "headers": ["项目", "金额", "备注"],
                "rows": [{"row_index": 2, "values": {"项目": "服务费", "金额": "12000", "备注": "调整"}}],
                "source_ref": "right.csv | table",
            }
        ],
    }


def test_document_compare_service_diffs_paragraphs():
    result = DocumentCompareService.diff_paragraphs(left_document(), right_document())

    assert result["summary"]["replace"] == 2
    assert result["summary"]["insert"] == 1
    assert any(hunk["op"] == "replace" for hunk in result["hunks"])
    assert any(item["source_ref"] == "left.md | lines 1-1" for hunk in result["hunks"] for item in hunk["left"])


def test_document_compare_service_diffs_hash_and_sections():
    hash_result = DocumentCompareService.diff_hash(left_document(), right_document())
    section_result = DocumentCompareService.diff_sections(left_document(), right_document())

    assert hash_result["same"] is False
    assert "content_hash" in hash_result["changed_parts"]
    assert section_result["kind"] == "section_diff"
    assert section_result["summary"]["replace"] == 1


def test_document_compare_service_diffs_tables():
    result = DocumentCompareService.diff_tables(left_document(), right_document())

    assert result["summary"]["replace"] == 1
    assert result["schema_changes"]["added_headers"] == ["备注"]
    assert result["hunks"][0]["right"][0]["values"]["金额"] == "12000"


def test_document_compare_service_matches_containment_and_missing():
    left = [
        {"item_id": "a1", "text": "甲方应在三十日内付款。", "evidence": {"source_ref": "law.md | line 1"}},
        {"item_id": "a2", "text": "乙方应提交验收报告。", "evidence": {"source_ref": "law.md | line 2"}},
    ]
    right = [{"item_id": "b1", "text": "甲方应在收到发票后三十日内付款并完成结算。", "evidence": {"source_ref": "contract.md | line 1"}}]

    result = DocumentCompareService.compare_items(left, right, min_score=0.2)

    assert result["matches"][0]["relation"] in {"b_contains_a", "equivalent", "ambiguous"}
    assert result["matches"][0]["evidence"]["left"]["source_ref"] == "law.md | line 1"
    assert result["summary"]["missing_in_right"] == 1


def test_document_compare_service_detects_deadline_and_prohibition_conflicts():
    standard = [
        {"item_id": "s1", "text": "甲方应在收到发票后三十日内付款。", "evidence": {"source_ref": "law.md | line 1"}},
        {"item_id": "s2", "text": "乙方不得泄露商业秘密。", "evidence": {"source_ref": "law.md | line 2"}},
    ]
    target = [
        {"item_id": "t1", "text": "甲方应在收到发票后90日内付款。", "evidence": {"source_ref": "contract.md | line 1"}},
        {"item_id": "t2", "text": "乙方可以向第三方披露商业秘密。", "evidence": {"source_ref": "contract.md | line 2"}},
    ]

    result = DocumentCompareService.detect_conflicts(standard, target)
    reason_codes = {item["reason_code"] for item in result["conflicts"]}

    assert result["summary"]["conflict_count"] == 2
    assert "deadline_longer_than_allowed" in reason_codes
    assert "prohibited_action_permitted" in reason_codes
