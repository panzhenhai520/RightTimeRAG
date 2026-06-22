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

from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class CanonicalTopic:
    id: str
    label: str
    aliases: list[str]
    language: str
    confidence: float

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class TopicRule:
    id: str
    label: str
    aliases: list[str]
    language: str
    triggers: tuple[re.Pattern, ...]
    positive_context: tuple[re.Pattern, ...] = ()
    negative_context: tuple[re.Pattern, ...] = ()


def _compile(pattern: str) -> re.Pattern:
    return re.compile(pattern, re.I)


TOPIC_RULES: tuple[TopicRule, ...] = (
    TopicRule(
        id="company:apple",
        label="Apple Inc.",
        aliases=["Apple", "Apple Inc.", "苹果", "苹果公司", "AAPL"],
        language="multi",
        triggers=(_compile(r"apple\b"), _compile(r"苹果公司?"), _compile(r"\baapl\b")),
        positive_context=(
            _compile(r"公司|企业|股票|股价|财报|市值|iphone|ipad|macbook|aapl"),
            _compile(r"inc\.?|company|stock|share|earnings|market cap|iphone|ipad|macbook"),
        ),
        negative_context=(
            _compile(r"水果|果汁|果园|吃|食物|营养"),
            _compile(r"fruit|juice|orchard|eat|food"),
        ),
    ),
    TopicRule(
        id="fruit:apple",
        label="Apple fruit",
        aliases=["apple", "苹果", "苹果水果"],
        language="multi",
        triggers=(_compile(r"apple\b"), _compile(r"苹果")),
        positive_context=(
            _compile(r"水果|果汁|果园|吃|食物|营养"),
            _compile(r"fruit|juice|orchard|eat|food"),
        ),
        negative_context=(_compile(r"公司|股票|股价|财报|iphone|ipad|macbook|aapl"),),
    ),
    TopicRule(
        id="topic:family-office",
        label="Family office",
        aliases=["Family office", "家族办公室", "家办", "单一家族办公室"],
        language="multi",
        triggers=(_compile(r"family office"), _compile(r"家族办公室|家办|单一家族办公室")),
    ),
    TopicRule(
        id="topic:trust-law",
        label="Trust law",
        aliases=["Trust law", "Trust Ordinance", "Trustee Ordinance", "trust", "信托", "信托法", "信托条例", "受托人", "受托人条例"],
        language="multi",
        triggers=(
            _compile(r"trustee|trust law|trust ordinance|covenant|rentcharge"),
            _compile(r"信托|受托人|契诺|租金|批地|租约"),
        ),
        positive_context=(
            _compile(r"法律|条例|责任|契诺|租金|租约|批地|受托人"),
            _compile(r"law|ordinance|liability|covenant|rent|lease|trustee"),
        ),
    ),
    TopicRule(
        id="topic:zong-qinghou",
        label="宗庆后",
        aliases=["宗庆后", "Zong Qinghou", "Wahaha", "娃哈哈"],
        language="multi",
        triggers=(_compile(r"宗庆后|娃哈哈"), _compile(r"zong qinghou|wahaha")),
    ),
)

STOP_WORDS = {
    "the",
    "and",
    "for",
    "with",
    "about",
    "this",
    "that",
    "from",
    "into",
    "what",
    "which",
    "how",
    "why",
    "are",
    "was",
    "were",
    "请问",
    "关于",
    "什么",
    "哪些",
    "如何",
    "是否",
    "这个",
    "那个",
    "用户",
    "问题",
}


def normalize_topic_text(text: str | None) -> str:
    text = str(text or "").lower()
    text = re.sub(r"[_\s]+", " ", text)
    text = re.sub(r"[^\u4e00-\u9fffa-z0-9\s.-]", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def extract_topic_keywords(text: str | None, limit: int = 10) -> list[str]:
    matches = re.findall(r"[\u4e00-\u9fff]{2,}|[A-Za-z][A-Za-z0-9.-]{2,}", str(text or ""))
    keywords = []
    seen = set()
    for match in matches:
        keyword = normalize_topic_text(match)
        if len(keyword) <= 1 or keyword in STOP_WORDS or keyword in seen:
            continue
        seen.add(keyword)
        keywords.append(keyword)
        if len(keywords) >= limit:
            break
    return keywords


def _rule_matches(rule: TopicRule, text: str) -> bool:
    if not any(trigger.search(text) for trigger in rule.triggers):
        return False
    if any(pattern.search(text) for pattern in rule.negative_context):
        return False
    if not rule.positive_context:
        return True
    return any(pattern.search(text) for pattern in rule.positive_context)


def infer_canonical_topic(text: str | None) -> CanonicalTopic:
    normalized = normalize_topic_text(text)
    for rule in TOPIC_RULES:
        if _rule_matches(rule, normalized):
            return CanonicalTopic(
                id=rule.id,
                label=rule.label,
                aliases=list(rule.aliases),
                language=rule.language,
                confidence=0.9,
            )

    keywords = extract_topic_keywords(normalized, 4)
    label = keywords[0] if keywords else "memo"
    topic_id = re.sub(r"\s+", "-", normalize_topic_text(label)) or "memo"
    return CanonicalTopic(
        id=f"topic:{topic_id}",
        label=label,
        aliases=keywords,
        language="zh" if re.search(r"[\u4e00-\u9fff]", normalized) else "en",
        confidence=0.45,
    )
