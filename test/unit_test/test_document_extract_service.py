from api.db.services.document_extract_service import DocumentExtractService


def sample_document():
    return {
        "document_id": "doc-1",
        "paragraphs": [
            {
                "text": "第一条 甲方应在收到发票后三十日内付款人民币10000元。",
                "paragraph_index": 1,
                "line_start": 1,
                "line_end": 1,
                "source_ref": "contract.md | lines 1-1",
            },
            {
                "text": "第二条 乙方不得泄露甲方商业秘密，否则应承担赔偿责任。",
                "paragraph_index": 2,
                "line_start": 3,
                "line_end": 3,
                "source_ref": "contract.md | lines 3-3",
            },
            {
                "text": "项目经理建议在上线前完成安全复核。",
                "paragraph_index": 3,
                "line_start": 5,
                "line_end": 5,
                "source_ref": "meeting.md | lines 5-5",
            },
            {
                "text": "本合同所称服务费是指甲方为乙方服务支付的费用。",
                "paragraph_index": 4,
                "line_start": 7,
                "line_end": 7,
                "source_ref": "contract.md | lines 7-7",
            },
        ],
        "tables": [
            {
                "headers": ["项目", "金额"],
                "rows": [{"row_index": 2, "values": {"项目": "服务费", "金额": "10000"}}],
                "source_ref": "quote.csv | table",
            }
        ],
    }


def test_document_extract_service_extracts_clauses_with_evidence():
    result = DocumentExtractService.extract_clauses(sample_document())

    assert len(result["items"]) == 2
    first = result["items"][0]
    assert first["subject"] == "甲方"
    assert first["action"] == "付款"
    assert first["amount"] == "10000元"
    assert first["evidence"]["source_ref"] == "contract.md | lines 1-1"


def test_document_extract_service_extracts_obligations_and_risks():
    obligations = DocumentExtractService.extract_obligations(sample_document())
    risks = DocumentExtractService.extract_risks(sample_document())

    assert len(obligations["items"]) == 2
    assert risks["items"][0]["severity"] == "high"
    assert "不得" in risks["items"][0]["risk_terms"]


def test_document_extract_service_extracts_viewpoints_and_table_facts():
    viewpoints = DocumentExtractService.extract_viewpoints(sample_document())
    facts = DocumentExtractService.extract_table_facts(sample_document())

    assert viewpoints["items"][0]["item_type"] == "viewpoint"
    assert "建议" in viewpoints["items"][0]["claim"]
    assert facts["items"][0]["values"]["金额"] == "10000"
    assert facts["items"][0]["evidence"]["source_ref"] == "quote.csv | table | row 2"


def test_document_extract_service_extracts_definitions():
    definitions = DocumentExtractService.extract_definitions(sample_document())

    assert definitions["items"][0]["item_type"] == "definition"
    assert definitions["items"][0]["term"] == "本合同所称服务费"
    assert "甲方为乙方服务支付的费用" in definitions["items"][0]["definition"]
