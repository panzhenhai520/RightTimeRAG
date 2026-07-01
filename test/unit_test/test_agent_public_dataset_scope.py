from agent.tools.retrieval import Retrieval


def test_request_dataset_scope_keeps_configured_ids_when_request_scope_is_empty():
    assert Retrieval._apply_request_dataset_scope(["kb-a", "kb-b"], []) == ["kb-a", "kb-b"]


def test_request_dataset_scope_uses_request_scope_when_node_has_no_configured_ids():
    assert Retrieval._apply_request_dataset_scope([], ["kb-a", "kb-a", "kb-b"]) == ["kb-a", "kb-b"]


def test_request_dataset_scope_intersects_configured_and_request_ids():
    assert Retrieval._apply_request_dataset_scope(["kb-a", "kb-b"], ["kb-b", "kb-c"]) == ["kb-b"]


def test_request_dataset_scope_empty_intersection_does_not_fallback_to_configured_ids():
    assert Retrieval._apply_request_dataset_scope(["kb-a"], ["kb-b"]) == []


def test_retrieval_enriches_standard_metadata_from_document_metadata():
    chunk = {
        "content": "用人单位应当按时足额支付劳动报酬。",
        "document_metadata": {
            "standard_type": "law",
            "jurisdiction": "CN",
            "effective_from": "2024-01-01",
            "article_no": "第50条",
            "version": "2024",
        },
    }

    enriched = Retrieval._enrich_standard_metadata(chunk)

    assert enriched["standard_metadata"]["standard_type"] == "law"
    assert enriched["article_no"] == "第50条"
    assert enriched["metadata_incomplete"] is False


def test_retrieval_marks_standard_metadata_incomplete_when_version_fields_missing():
    chunk = {"content": "合同应当包含争议解决条款。", "document_metadata": {"standard_type": "policy"}}

    enriched = Retrieval._enrich_standard_metadata(chunk)

    assert enriched["standard_metadata"]["standard_type"] == "policy"
    assert enriched["metadata_incomplete"] is True
