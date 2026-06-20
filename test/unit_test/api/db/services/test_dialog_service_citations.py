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
    build_compact_reference,
    normalize_markdown_table_citations,
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
