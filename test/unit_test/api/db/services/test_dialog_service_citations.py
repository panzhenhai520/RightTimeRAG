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
    _classify_evidence_chunk,
    _format_knowledge_chunk,
    _prioritize_evidence_chunks,
    build_compact_reference,
    expand_raptor_chunks_for_generation,
    normalize_markdown_table_citations,
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
