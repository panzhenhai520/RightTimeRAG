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

import pytest

from rag.structured_extraction import (
    apply_structure_to_chunks,
    infer_document_structure_from_chunks,
    structured_extraction_enabled,
)


def _task_executor_module():
    import warnings

    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", message="Tensorflow not installed.*", category=ImportWarning)
        from rag.svr import task_executor

    return task_executor


@pytest.mark.p2
def test_structured_extraction_enabled_is_explicit_opt_in():
    assert structured_extraction_enabled({"structured_extraction": {"enabled": True}})
    assert structured_extraction_enabled({"structured_extraction": {"enabled": "yes"}})
    assert not structured_extraction_enabled({})
    assert not structured_extraction_enabled({"structured_extraction": {"enabled": False}})


@pytest.mark.p2
def test_structured_extraction_enriches_clause_and_table_metadata():
    chunks = [
        {
            "id": "chunk-28",
            "content_with_weight": "28. 在租金及契诺方面的法律责任的保障",
            "page_num_int": [29],
        },
        {
            "id": "chunk-table",
            "content_with_weight": "| 条款 | 条件 |\n|---|---|\n| 第28条 | 已履行责任 |",
            "page_num_int": [30],
        },
    ]

    structure = infer_document_structure_from_chunks(chunks, title="Trustee Ordinance.pdf")
    enriched = apply_structure_to_chunks(chunks, structure)

    assert enriched[0]["extra"]["structured"]["evidence_type"] == "clause"
    assert enriched[0]["extra"]["structured"]["clause_id"] == "28"
    assert "租金及契诺" in enriched[0]["extra"]["structured"]["clause_title"]
    assert enriched[1]["extra"]["structured"]["evidence_type"] == "table"
    assert enriched[0] is not chunks[0]


@pytest.mark.p2
def test_task_executor_leaves_chunks_unchanged_when_structured_extraction_disabled():
    task_executor = _task_executor_module()
    chunks = [{"id": "chunk-1", "content_with_weight": "28. 在租金及契诺方面的法律责任的保障"}]
    task = {"doc_id": "doc-1", "parser_config": {}}

    result = task_executor.maybe_apply_structured_extraction(task, chunks, lambda *args, **kwargs: None)

    assert result is chunks
    assert "extra" not in chunks[0]


@pytest.mark.p2
def test_task_executor_enriches_chunks_when_structured_extraction_enabled():
    task_executor = _task_executor_module()
    chunks = [{"id": "chunk-28", "content_with_weight": "28. 在租金及契诺方面的法律责任的保障"}]
    task = {
        "doc_id": "doc-1",
        "name": "Trustee Ordinance.pdf",
        "parser_config": {"structured_extraction": {"enabled": True}},
    }
    progress_messages = []

    result = task_executor.maybe_apply_structured_extraction(
        task,
        chunks,
        lambda *args, **kwargs: progress_messages.append(kwargs.get("msg") or (args[1] if len(args) > 1 else "")),
    )

    assert result is not chunks
    assert "extra" not in chunks[0]
    assert result[0]["extra"]["structured"]["evidence_type"] == "clause"
    assert result[0]["extra"]["structured"]["clause_id"] == "28"
    assert any("Structured evidence extraction" in message for message in progress_messages)


@pytest.mark.p2
def test_task_executor_falls_back_to_original_chunks_when_enrichment_fails(monkeypatch):
    task_executor = _task_executor_module()
    chunks = [{"id": "chunk-28", "content_with_weight": "28. 在租金及契诺方面的法律责任的保障"}]
    task = {
        "doc_id": "doc-1",
        "parser_config": {"structured_extraction": {"enabled": True}},
    }

    def fail_structure(*args, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr(task_executor, "infer_document_structure_from_chunks", fail_structure)

    result = task_executor.maybe_apply_structured_extraction(task, chunks, lambda *args, **kwargs: None)

    assert result is chunks
