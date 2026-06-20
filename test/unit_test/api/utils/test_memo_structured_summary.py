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
from pydantic import ValidationError

from api.utils.memo_structured_summary import (
    MemoStructuredSummary,
    build_memo_structured_summary,
    memo_structured_summary_to_search_text,
    sanitize_memo_text,
    sanitize_memo_title,
)


pytestmark = pytest.mark.p1


def test_sanitize_memo_text_removes_process_and_error_noise():
    text = """
<retrieving>Searching datasets for: rent covenant</retrieving>
User: 在租金及契诺方面的法律责任的保障有哪些？
<think>模型内部分析，不应进入备忘录。</think>
Assistant: 根据《受托人条例》第28条，受托人满足条件后可免除后续个人责任。
ERROR: INVALID_REQUEST - layer-slice token span exceeds context
"""

    clean = sanitize_memo_text(text)

    assert "Searching datasets" not in clean
    assert "模型内部分析" not in clean
    assert "ERROR:" not in clean
    assert "在租金及契诺方面" in clean
    assert "第28条" in clean


def test_sanitize_memo_title_strips_explanatory_prefix_and_limits_length():
    title = sanitize_memo_title("我们注意到用户的问题是关于：2023年家族办公室薪资上调人员占比，具体询问高管和员工的比例。")

    assert not title.startswith("我们注意到")
    assert len(title) <= 36
    assert "家族办公室薪资" in title


def test_build_memo_structured_summary_extracts_core_fields():
    transcript = """
User: 2023年家族办公室薪资上调人员占比是多少？
Assistant: Morgan Stanley 2023 report mentioned CEO base salary and staff compensation. HK$1,200,000 was referenced.
User: 高管和员工的比例分别是多少？
Assistant: 已确认需要继续核对报告表格。
"""

    summary = build_memo_structured_summary(
        transcript,
        source_message_ids=[101, "102"],
        related_kb_ids=["kb-family-office"],
    )

    assert summary.display_title == "2023年家族办公室薪资上调人员占比是多少"
    assert summary.canonical_topic_candidate == summary.display_title
    assert summary.language == "mixed"
    assert summary.source_message_ids == ["101", "102"]
    assert summary.related_kb_ids == ["kb-family-office"]
    assert "2023" in summary.dates
    assert [amount.text for amount in summary.amounts] == ["HK$1,200,000"]
    assert any(entity.text == "Morgan Stanley" for entity in summary.entities)
    assert any("CEO base salary" in fact.text for fact in summary.facts)
    assert any("高管和员工" in question for question in summary.open_questions)


def test_build_memo_structured_summary_prefers_explicit_display_title():
    summary = build_memo_structured_summary(
        "User: 请比较苹果公司和Apple Inc.的季度收入\nAssistant: 两者指向同一家公司。",
        display_title="Apple Inc. 与苹果公司季度收入",
        aliases=["苹果", "Apple Inc.", "AAPL", "苹果"],
    )

    assert summary.display_title == "Apple Inc. 与苹果公司季度收入"
    assert summary.aliases == ["苹果", "Apple Inc.", "AAPL"]


def test_memo_structured_summary_forbids_unknown_fields():
    with pytest.raises(ValidationError):
        MemoStructuredSummary(display_title="测试", unexpected="not allowed")


def test_memo_structured_summary_to_search_text_is_topic_first():
    summary = build_memo_structured_summary(
        "User: 宗庆后相关案件进展\nAssistant: 娃哈哈集团相关公开报道需要继续核查。",
        aliases=["Zong Qinghou", "娃哈哈"],
    )

    search_text = memo_structured_summary_to_search_text(summary)

    assert search_text.splitlines()[0] == "宗庆后相关案件进展"
    assert "Zong Qinghou" in search_text
    assert "娃哈哈" in search_text
