#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#
import sys
import types
import warnings

import pytest

warnings.filterwarnings(
    "ignore",
    message="pkg_resources is deprecated as an API.*",
    category=UserWarning,
)


def _install_cv2_stub_if_unavailable():
    try:
        import cv2  # noqa: F401
        return
    except Exception:
        pass

    stub = types.ModuleType("cv2")
    stub.INTER_LINEAR = 1
    stub.INTER_CUBIC = 2
    stub.BORDER_CONSTANT = 0
    stub.BORDER_REPLICATE = 1
    stub.COLOR_BGR2RGB = 0
    stub.COLOR_BGR2GRAY = 1
    stub.COLOR_GRAY2BGR = 2
    stub.IMREAD_IGNORE_ORIENTATION = 128
    stub.IMREAD_COLOR = 1
    stub.RETR_LIST = 1
    stub.CHAIN_APPROX_SIMPLE = 2

    def _module_getattr(name):
        if name.isupper():
            return 0
        raise RuntimeError(f"cv2.{name} is unavailable in this test environment")

    stub.__getattr__ = _module_getattr
    sys.modules["cv2"] = stub


_install_cv2_stub_if_unavailable()

from api.db.services.dialog_service import (  # noqa: E402
    _build_evidence_audit,
    _classify_evidence_chunk,
    _format_knowledge_chunk,
    _prioritize_evidence_chunks,
    _query_focused_content_excerpt,
    build_compact_evidence_audit,
    build_compact_reference,
    expand_raptor_chunks_for_generation,
    normalize_markdown_table_citations,
    repair_bad_citation_formats,
    settings,
)


@pytest.mark.p2
def test_normalize_markdown_table_citations_keeps_separator_row_valid():
    answer = (
        "总结：三种保障的比较\n"
        "| 条款 | 条件 | 核心保障 |\n"
        "|------|------|----------| [ID:4]\n"
        "| 第28条 | 已履行责任 | 个人责任豁免 |\n"
    )

    normalized = normalize_markdown_table_citations(answer)

    assert "|------|------|----------|\n" in normalized
    assert "|------|------|----------| [ID:4]" not in normalized
    assert "总结：三种保障的比较 [ID:4]" in normalized


@pytest.mark.p2
def test_repair_bad_citation_formats_expands_multi_id_parentheses():
    answer = "受托人可预留资金并免责（ID:1, ID:3）。"
    kbinfos = {"chunks": [{}, {}, {}, {}]}
    idx = set()

    repaired, idx = repair_bad_citation_formats(answer, kbinfos, idx)

    assert "[ID:1] [ID:3]" in repaired
    assert idx == {1, 3}


@pytest.mark.p2
def test_repair_bad_citation_formats_accepts_bare_id_list_used_by_llm():
    answer = "税务优惠（ID0、ID1、ID7），资本入境计划（ID1、ID3、ID7） Fig. 2。"
    kbinfos = {
        "chunks": [
            {"doc_id": f"doc-{i}", "docnm_kwd": f"Doc {i}.pdf", "content_with_weight": f"content {i}"}
            for i in range(8)
        ],
        "doc_aggs": [{"doc_id": f"doc-{i}", "doc_name": f"Doc {i}.pdf", "count": 1} for i in range(8)],
    }

    repaired, idx = repair_bad_citation_formats(answer, kbinfos, set())
    compact_answer, refs, old_to_new = build_compact_reference(repaired, kbinfos, idx)

    assert "[ID:0] [ID:1] [ID:7]" in repaired
    assert idx == {0, 1, 3, 7}
    assert old_to_new == {0: 0, 1: 1, 3: 2, 7: 3}
    assert "[ID:3]" in compact_answer
    assert len(refs["chunks"]) == 4
    assert [doc["doc_id"] for doc in refs["doc_aggs"]] == ["doc-0", "doc-1", "doc-3", "doc-7"]


@pytest.mark.p2
def test_repair_bad_citation_formats_converts_fig_labels_to_backend_ids():
    answer = "根据报告，亚太地区私人财富预计会超过西欧 Fig. 1，并且增长率更高 Figure 2。"
    kbinfos = {
        "chunks": [
            {
                "doc_id": "doc-0",
                "docnm_kwd": "Report.pdf",
                "content_with_weight": "Asia-Pacific private wealth projected to surpass Western Europe.",
            },
            {
                "doc_id": "doc-1",
                "docnm_kwd": "Report.pdf",
                "content_with_weight": "Asia-Pacific private wealth grew 9.5%, Western Europe 3.2%.",
            },
        ],
        "doc_aggs": [{"doc_id": "doc-0", "doc_name": "Report.pdf", "count": 2}],
    }

    repaired, idx = repair_bad_citation_formats(answer, kbinfos, set())
    compact_answer, refs, old_to_new = build_compact_reference(repaired, kbinfos, idx)

    assert "Fig." not in repaired
    assert "Figure" not in repaired
    assert "[ID:0]" in repaired
    assert "[ID:1]" in repaired
    assert idx == {0, 1}
    assert old_to_new == {0: 0, 1: 1}
    assert compact_answer.count("[ID:") == 2
    assert len(refs["chunks"]) == 2
    assert refs["doc_aggs"] == [{"doc_id": "doc-0", "doc_name": "Report.pdf", "count": 2}]


@pytest.mark.p2
def test_build_compact_reference_remaps_sparse_citations_to_contiguous_ids():
    kbinfos = {
        "chunks": [
            {"doc_id": "doc-a", "docnm_kwd": "A.pdf", "content_with_weight": "a", "vector": [1]},
            {"doc_id": "doc-b", "docnm_kwd": "B.pdf", "content_with_weight": "b", "vector": [1]},
            {"doc_id": "doc-c", "docnm_kwd": "C.pdf", "content_with_weight": "c", "vector": [1]},
            {"doc_id": "doc-d", "docnm_kwd": "D.pdf", "content_with_weight": "d", "vector": [1]},
            {"doc_id": "doc-e", "docnm_kwd": "E.pdf", "content_with_weight": "e", "vector": [1]},
            {"doc_id": "doc-f", "docnm_kwd": "F.pdf", "content_with_weight": "f", "vector": [1]},
        ],
        "doc_aggs": [
            {"doc_id": "doc-a", "doc_name": "A.pdf", "count": 1},
            {"doc_id": "doc-d", "doc_name": "D.pdf", "count": 1},
            {"doc_id": "doc-f", "doc_name": "F.pdf", "count": 1},
        ],
    }

    answer, refs, old_to_new = build_compact_reference("A claim [ID:3] and [ID:5].", kbinfos, {3, 5})

    assert answer == "A claim [ID:0] and [ID:1]."
    assert old_to_new == {3: 0, 5: 1}
    assert [chunk["document_name"] for chunk in refs["chunks"]] == ["D.pdf", "F.pdf"]
    assert all("vector" not in chunk for chunk in refs["chunks"])
    assert [doc["doc_id"] for doc in refs["doc_aggs"]] == ["doc-d", "doc-f"]


@pytest.mark.p2
def test_compact_evidence_audit_uses_compact_reference_id_space():
    kbinfos = {
        "chunks": [
            {"doc_id": "doc-a", "docnm_kwd": "A.pdf", "content_with_weight": "title"},
            {"doc_id": "doc-b", "docnm_kwd": "B.pdf", "content_with_weight": "unused"},
            {
                "id": "chunk-c",
                "doc_id": "doc-c",
                "docnm_kwd": "C.pdf",
                "content_with_weight": (
                    "Where a personal representative or trustee liable as such for any rent, "
                    "covenant, or agreement reserved by or contained in any lease shall satisfy all liabilities."
                ),
            },
            {"doc_id": "doc-d", "docnm_kwd": "D.pdf", "content_with_weight": "unused"},
            {
                "id": "chunk-e",
                "doc_id": "doc-e",
                "docnm_kwd": "E.pdf",
                "content_with_weight": (
                    "The trustee may distribute the residuary estate without appropriating a further part "
                    "to meet future liability under the lease or grant."
                ),
            },
        ],
        "doc_aggs": [
            {"doc_id": "doc-c", "doc_name": "C.pdf", "count": 1},
            {"doc_id": "doc-e", "doc_name": "E.pdf", "count": 1},
        ],
    }

    answer, refs, _ = build_compact_reference("Answer cites sparse chunks [ID:2] [ID:4].", kbinfos, {2, 4})
    audit = build_compact_evidence_audit(
        refs,
        "在租金及契诺方面的法律责任的保障有哪些",
        "rent covenant liability protections",
        answer,
    )

    assert answer == "Answer cites sparse chunks [ID:0] [ID:1]."
    assert audit["id_space"] == "compact_reference"
    assert audit["retrieval"]["selected_chunks"] == 2
    assert [item["id"] for item in audit["evidence"]] == [0, 1]
    assert [item["fig_id"] for item in audit["evidence"]] == [0, 1]
    assert audit["answer_basis"][0]["source_ids"] == [0, 1]
    assert audit["answer_basis"][0]["fig_ids"] == [0, 1]


@pytest.mark.p2
def test_structured_metadata_does_not_promote_title_only_chunks():
    chunk = {
        "content_with_weight": "28. 在租金及契诺方面的法律责任的保障",
        "extra": {
            "structured": {
                "evidence_type": "title",
                "clause_id": "28",
                "clause_title": "在租金及契诺方面的法律责任的保障",
            }
        },
    }

    evidence_type, reason = _classify_evidence_chunk(chunk)

    assert evidence_type == "title_only"
    assert "不能单独" in reason


@pytest.mark.p2
def test_structured_metadata_promotes_grounded_clause_and_table_chunks():
    clause_chunk = {
        "content_with_weight": (
            "Where a personal representative or trustee liable as such for any rent, "
            "covenant, or agreement reserved by or contained in any lease shall satisfy "
            "all liabilities under the lease or grant and set apart a sufficient fund."
        ),
        "extra": {
            "structured": {
                "evidence_type": "clause",
                "clause_id": "28",
                "clause_title": "Protection against liability in respect of rents and covenants",
            }
        },
    }
    table_chunk = {
        "content_with_weight": "| 条款 | 条件 | 核心保障 |\n|---|---|---|\n| 第28条 | 已履行责任 | 个人责任豁免 |",
        "extra": {"structured": {"evidence_type": "table"}},
    }

    assert _classify_evidence_chunk(clause_chunk)[0] == "original_text"
    assert _classify_evidence_chunk(table_chunk)[0] == "original_text"

    formatted = _format_knowledge_chunk(clause_chunk, 0)
    assert "EvidenceType: clause" in formatted
    assert "Clause: 28" in formatted
    assert "ClauseTitle: Protection against liability" in formatted


@pytest.mark.p2
def test_prioritize_evidence_chunks_uses_structured_classification():
    title_chunk = {
        "doc_id": "doc-title",
        "content_with_weight": "28. 在租金及契诺方面的法律责任的保障",
        "extra": {"structured": {"evidence_type": "title"}},
    }
    grounded_chunk = {
        "doc_id": "doc-clause",
        "content_with_weight": (
            "Where a personal representative or trustee liable as such for any rent, "
            "covenant, or agreement reserved by or contained in any lease shall satisfy "
            "all liabilities under the lease or grant and set apart a sufficient fund."
        ),
        "extra": {"structured": {"evidence_type": "clause", "clause_id": "28"}},
    }
    kbinfos = {"chunks": [title_chunk, grounded_chunk]}

    _prioritize_evidence_chunks(kbinfos)

    assert kbinfos["chunks"][0]["doc_id"] == "doc-clause"
    assert kbinfos["chunks"][1]["doc_id"] == "doc-title"


@pytest.mark.p2
def test_query_focused_excerpt_removes_unrelated_neighboring_clause_text():
    mixed_chunk = (
        "(1)凡任何遗产代理人以遗产代理人身分或受托人以受托人身分而须对以下各项承担法律责任—"
        "(a)任何租约所保留或所载的租金、契诺或协议；"
        "或(b)根据任何以租费为代价的批地而须缴付的租金、契诺或协议；"
        "或(c)就以上两段所提述的租金、契诺或协议而给予的弥偿。"
        "Section 28 (a)shall not be invalid on the ground that an unsubstantial, "
        "illusory or nominal share only is appointed."
    )

    excerpt = _query_focused_content_excerpt(
        mixed_chunk,
        "在租金及契诺方面的法律责任的保障有哪些？",
    )

    assert "Query-focused excerpt" in excerpt
    assert "租金、契诺" in excerpt
    assert "弥偿" in excerpt
    assert "nominal share" not in excerpt
    assert "shall not be invalid" not in excerpt


@pytest.mark.p2
def test_query_focused_excerpt_requires_combined_rent_and_covenant_context():
    unrelated_chunk = (
        "被评定暂缴薪俸税的人已就该课税年度缴付住宅租金，可容许扣除该等租金。"
        "凡受托人在取得任何财产抵押后贷出款项，按揭人不得违反按揭文书中关于财产保养的契诺。"
    )

    excerpt = _query_focused_content_excerpt(
        unrelated_chunk,
        "在租金及契诺方面的法律责任的保障有哪些？",
    )

    assert excerpt == ""


@pytest.mark.p2
def test_query_focused_excerpt_keeps_section_28_liability_protection_body():
    section_chunk = (
        "28. 在租金及契诺方面的法律责任的保障 "
        "(1)凡任何遗产代理人以遗产代理人身分或受托人以受托人身分而须对以下各项承担法律责任—"
        "(a)任何租约所保留或所载的租金、契诺或协议；"
        "(b)根据任何以租费为代价的批地而须缴付的租金、契诺或协议；"
        "(c)就以上两段中任何一段所提述的租金、契诺或协议而给予的弥偿，"
        "且已履行截至下述转易日期为止的期间内可能已产生及已被申索的所有法律责任，"
        "并已在有需要的情况下，预留一笔足够的基金，以应付日后申索，"
        "则遗产代理人或受托人可将批租或批出财产转易予任何买家，"
        "之后他可分配剩余遗产或信托产业，而无须拨出更多部分以应付日后责任；"
        "即使作出该项分配，他亦无须对其后根据该租约或该项批地而作出的任何申索承担个人法律责任。"
    )

    excerpt = _query_focused_content_excerpt(
        section_chunk,
        "在租金及契诺方面的法律责任的保障有哪些？",
    )

    assert "租金、契诺" in excerpt
    assert "预留一笔足够的基金" in excerpt
    assert "转易予任何买家" in excerpt
    assert "无须对其后" in excerpt
    assert "个人法律责任" in excerpt


class _RaptorSourceRetriever:
    def chunk_list(self, doc_id, tenant_id, kb_ids, max_count=256, fields=None, sort_by_position=True):
        assert doc_id == "doc-r"
        assert tenant_id == "tenant-a"
        assert kb_ids == ["kb-a"]
        assert sort_by_position is True
        return [
            {
                "doc_id": "doc-r",
                "docnm_kwd": "Trustee Ordinance.pdf",
                "content_with_weight": (
                    "Original excerpt about rent and covenant liabilities. "
                    "A personal representative may distribute the estate after setting apart a sufficient fund."
                ),
                "img_id": "image-1",
                "position_int": [1, 2, 3, 4],
                "page_num_int": [29],
            },
            {
                "doc_id": "doc-r",
                "docnm_kwd": "Trustee Ordinance.pdf",
                "content_with_weight": "Unrelated source text.",
                "img_id": "",
                "position_int": [],
                "page_num_int": [30],
            },
        ]


@pytest.mark.p2
def test_compact_reference_expands_raptor_summary_sources(monkeypatch):
    monkeypatch.setattr(settings, "retriever", _RaptorSourceRetriever(), raising=False)
    kbinfos = {
        "tenant_ids": ["tenant-a"],
        "kb_ids": ["kb-a"],
        "chunks": [
            {
                "doc_id": "doc-r",
                "docnm_kwd": "Trustee Ordinance.pdf",
                "content_with_weight": "Summary about rent covenant liabilities and sufficient fund.",
                "raptor_kwd": "raptor",
                "vector": [1],
            }
        ],
        "doc_aggs": [{"doc_id": "doc-r", "doc_name": "Trustee Ordinance.pdf", "count": 1}],
    }

    answer, refs, _ = build_compact_reference("The summary supports this [ID:0].", kbinfos, {0})

    assert answer == "The summary supports this [ID:0]."
    chunk = refs["chunks"][0]
    assert chunk["is_raptor_summary"] is True
    assert chunk["source_chunks"]
    assert "Original excerpt about rent" in chunk["source_chunks"][0]["content"]
    assert chunk["source_chunks"][0]["image_id"] == "image-1"


@pytest.mark.p2
def test_expand_raptor_chunks_for_generation_includes_linked_original_excerpts(monkeypatch):
    monkeypatch.setattr(settings, "retriever", _RaptorSourceRetriever(), raising=False)
    kbinfos = {
        "tenant_ids": ["tenant-a"],
        "kb_ids": ["kb-a"],
        "chunks": [
            {
                "doc_id": "doc-r",
                "docnm_kwd": "Trustee Ordinance.pdf",
                "content_with_weight": "Summary about rent covenant liabilities and sufficient fund.",
                "raptor_kwd": "raptor",
            }
        ],
    }

    expand_raptor_chunks_for_generation(kbinfos)

    expanded = kbinfos["chunks"][0]["content_with_weight"]
    assert "This is a RAPTOR summary chunk" in expanded
    assert "Source excerpt 1:" in expanded
    assert "Original excerpt about rent" in expanded


@pytest.mark.p2
def test_evidence_audit_includes_answer_evidence_plan():
    kbinfos = {
        "chunks": [
            {
                "id": "chunk-title",
                "doc_id": "doc-title",
                "docnm_kwd": "Title.pdf",
                "content_with_weight": "28. 在租金及契诺方面的法律责任的保障",
            },
            {
                "id": "chunk-strong",
                "doc_id": "doc-strong",
                "docnm_kwd": "Trustee Ordinance.pdf",
                "content_with_weight": (
                    "Where a personal representative or trustee liable as such for any rent, "
                    "covenant, or agreement reserved by or contained in any lease shall satisfy "
                    "all liabilities under the lease or grant and set apart a sufficient fund."
                ),
            },
        ],
    }

    audit = _build_evidence_audit(
        kbinfos,
        {0, 1},
        "在租金及契诺方面的法律责任的保障有哪些",
        "rent covenant liability protections",
        "Answer [ID:0] [ID:1]",
        {0: 0, 1: 1},
    )

    plan = audit["answer_evidence_plan"]
    assert len(plan) == 2
    assert plan[0]["evidence_strength"] == "weak"
    assert "不能单独" in plan[0]["missing_evidence_reason"]
    assert plan[1]["evidence_strength"] == "strong"
    assert plan[1]["missing_evidence_reason"] == ""
    assert plan[1]["supporting_chunk_ids"] == ["chunk-strong"]
