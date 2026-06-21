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

from api.utils.canonical_topic import infer_canonical_topic


@pytest.mark.p2
def test_canonical_topic_merges_multilingual_family_office_terms():
    assert infer_canonical_topic("家族办公室经营模式").id == "topic:family-office"
    assert infer_canonical_topic("Family office operating model").id == "topic:family-office"


@pytest.mark.p2
def test_canonical_topic_disambiguates_apple_company_and_fruit():
    assert infer_canonical_topic("苹果公司股票走势和财报").id == "company:apple"
    assert infer_canonical_topic("Apple Inc. earnings and AAPL stock").id == "company:apple"
    assert infer_canonical_topic("苹果水果营养和果汁").id == "fruit:apple"
    assert infer_canonical_topic("apple fruit nutrition").id == "fruit:apple"


@pytest.mark.p2
def test_canonical_topic_normalizes_trust_law_and_zong_qinghou():
    assert infer_canonical_topic("在租金及契诺方面的法律责任的保障有哪些").id == "topic:trust-law"
    assert infer_canonical_topic("trust covenant rent liability protections").id == "topic:trust-law"
    assert infer_canonical_topic("宗庆后相关案件进展").id == "topic:zong-qinghou"
    assert infer_canonical_topic("Zong Qinghou Wahaha case update").id == "topic:zong-qinghou"

