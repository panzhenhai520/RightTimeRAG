#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
"""Question boundary parsing and constraint-aware retrieval planning.

This module keeps boundary extraction separate from dialog orchestration.  The
first implementation is deterministic and schema-based so it can run before
every retrieval without adding another model call.  A guarded LLM merge hook is
left in place for later slot-filling expansion.
"""

from __future__ import annotations

import json
import logging
import os
import re
from copy import deepcopy
from datetime import date, datetime
from hashlib import sha1
from typing import Any

from api.utils.cross_language_utils import normalize_cross_language
from api.utils.cross_language_utils import infer_query_language

logger = logging.getLogger(__name__)

BOUNDARY_SLOT_KEYS = (
    "time",
    "space",
    "document",
    "event",
    "entity",
    "industry",
    "organization",
    "version",
    "law_article",
    "effective_range",
)

BOUNDARY_TYPES = {"time", "space", "document", "event", "version", "law_article", "effective_range"}
TOPIC_TYPES = {"industry", "organization", "entity"}
MAX_QUERY_TERMS = 64
MAX_QUERY_CHARS = 900

CN_DIGITS = {
    "零": 0,
    "〇": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
}
CN_UNITS = {"十": 10, "百": 100, "千": 1000}
CN_DIGIT_TEXT = "零一二三四五六七八九"

SPACE_CATALOG = {
    "香港": {
        "canonical": "Hong Kong",
        "aliases": ["香港", "Hong Kong", "HK", "Hong Kong SAR", "香港特别行政区", "香港特区"],
        "near_miss": ["新加坡", "Singapore", "内地", "中国内地", "Mainland China"],
    },
    "新加坡": {
        "canonical": "Singapore",
        "aliases": ["新加坡", "Singapore", "SG"],
        "near_miss": ["香港", "Hong Kong", "HK"],
    },
    "亚太": {
        "canonical": "Asia-Pacific",
        "aliases": ["亚太", "亚太地区", "Asia-Pacific", "Asia Pacific", "APAC"],
        "near_miss": ["西欧", "Western Europe", "欧洲", "Europe"],
    },
    "西欧": {
        "canonical": "Western Europe",
        "aliases": ["西欧", "Western Europe"],
        "near_miss": ["亚太", "亚太地区", "Asia-Pacific", "APAC"],
    },
    "中国内地": {
        "canonical": "Mainland China",
        "aliases": ["中国内地", "内地", "大陆", "Mainland China"],
        "near_miss": ["香港", "Hong Kong", "新加坡", "Singapore"],
    },
    "中国": {
        "canonical": "China",
        "aliases": ["中国", "China", "PRC", "中华人民共和国"],
        "near_miss": [],
    },
    "境内": {
        "canonical": "domestic",
        "aliases": ["境内", "国内", "domestic", "onshore"],
        "near_miss": ["境外", "海外", "offshore", "overseas"],
    },
    "境外": {
        "canonical": "overseas",
        "aliases": ["境外", "海外", "offshore", "overseas"],
        "near_miss": ["境内", "国内", "domestic", "onshore"],
    },
}

DOMAIN_TOPIC_CATALOG = {
    "家族办公室": {
        "canonical": "家族办公室",
        "aliases": ["家族办公室", "家办", "家辦", "family office", "family offices", "单一家族办公室"],
    },
    "信托行业": {
        "canonical": "信托行业",
        "aliases": ["信托行业", "信托", "信托公司", "信托业务", "trust industry"],
    },
    "私人财富": {
        "canonical": "私人财富",
        "aliases": ["私人财富", "private wealth", "wealth management"],
    },
}

SIMPLIFIED_TRADITIONAL_MAP = {
    "党的": "黨的",
    "关于": "關於",
    "信托": "信託",
    "行业": "行業",
    "报告": "報告",
    "政策": "政策",
    "论述": "論述",
    "观点": "觀點",
    "发展": "發展",
    "怎么讲": "怎麼講",
    "讲": "講",
    "是什么": "是什麼",
    "怎么": "怎麼",
    "怎样": "怎樣",
    "有什么": "有什麼",
    "回答": "回答",
    "中国共产党第十九次全国代表大会": "中國共產黨第十九次全國代表大會",
    "中国共产党第十八次全国代表大会": "中國共產黨第十八次全國代表大會",
    "中国共产党第二十次全国代表大会": "中國共產黨第二十次全國代表大會",
}

ENGLISH_LANGUAGE_HINTS = {
    "中国共产党第十九次全国代表大会报告": "the report of the 19th National Congress of the Communist Party of China",
    "党的十九大报告": "the report of the 19th National Congress of the Communist Party of China",
    "中国共产党第十九次全国代表大会": "the 19th National Congress of the Communist Party of China",
    "中国共产党第十八次全国代表大会报告": "the report of the 18th National Congress of the Communist Party of China",
    "党的十八大报告": "the report of the 18th National Congress of the Communist Party of China",
    "中国共产党第十八次全国代表大会": "the 18th National Congress of the Communist Party of China",
    "中国共产党第二十次全国代表大会报告": "the report of the 20th National Congress of the Communist Party of China",
    "党的二十大报告": "the report of the 20th National Congress of the Communist Party of China",
    "中国共产党第二十次全国代表大会": "the 20th National Congress of the Communist Party of China",
    "信托行业": "the trust industry",
    "信托": "trust",
    "报告": "report",
    "政策": "policies",
    "论述": "discussions",
    "观点": "viewpoints",
    "发展": "development",
    "关于": "about",
    "是怎么讲的": "what does it say",
    "怎么讲": "what does it say",
    "有什么观点": "what viewpoints are given",
    "讲": "say",
}

DOC_SUFFIX_RE = (
    r"(?:报告|白皮书|合同|条约|协议|方案|规划|指引|准则|通知|办法|条例|法律|"
    r"年报|年度报告|研究报告|政策文件)"
)


def _clean_text(text: str | None) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip()


def _compact_text(text: str | None) -> str:
    return re.sub(r"\s+", "", str(text or "")).lower()


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    deduped = []
    for value in values:
        value = _clean_text(value)
        if not value:
            continue
        key = value.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(value)
    return deduped


def _add_slot(slots: dict[str, list[dict[str, Any]]], slot_type: str, surface: str, **extra):
    surface = _clean_text(surface)
    if not surface or slot_type not in slots:
        return
    key = surface.lower()
    for item in slots[slot_type]:
        if str(item.get("surface", "")).lower() == key:
            item.update({k: v for k, v in extra.items() if v is not None})
            return
    slot = {"surface": surface, "hard": bool(extra.pop("hard", True)), **extra}
    slots[slot_type].append(slot)


def _cn_to_int(text: str | None) -> int | None:
    text = _clean_text(text)
    if not text:
        return None
    if text.isdigit():
        return int(text)
    total = 0
    current = 0
    unit_seen = False
    for ch in text:
        if ch in CN_DIGITS:
            current = CN_DIGITS[ch]
        elif ch in CN_UNITS:
            unit_seen = True
            unit = CN_UNITS[ch]
            if current == 0:
                current = 1
            total += current * unit
            current = 0
        else:
            return None
    total += current
    if total == 0 and not unit_seen:
        return CN_DIGITS.get(text)
    return total if total > 0 else None


def _int_to_cn(num: int) -> str:
    if num < 0 or num >= 100:
        return str(num)
    if num < 10:
        return CN_DIGIT_TEXT[num]
    if num == 10:
        return "十"
    if num < 20:
        return "十" + CN_DIGIT_TEXT[num % 10]
    tens, ones = divmod(num, 10)
    return CN_DIGIT_TEXT[tens] + "十" + (CN_DIGIT_TEXT[ones] if ones else "")


def _congress_year(ordinal: int | None) -> int | None:
    if not ordinal or ordinal < 1 or ordinal > 40:
        return None
    # The modern CPC national congress cadence is five years.  Use known
    # anchor 18th=2012 for robust ordinal-derived temporal hints.
    if ordinal >= 11:
        return 2012 + (ordinal - 18) * 5
    return None


def _extract_time_slots(text: str, slots: dict[str, list[dict[str, Any]]], today: date):
    occupied_spans: list[tuple[int, int]] = []
    for m in re.finditer(r"(?<!\d)(19\d{2}|20\d{2})\s*年?\s*(?:底|末|年底|年末)", text):
        year = int(m.group(1))
        _add_slot(
            slots,
            "time",
            m.group(0),
            kind="year_end",
            year=year,
            normalized=f"{year}-12-31",
            operator="as_of",
            hard=True,
        )
        occupied_spans.append(m.span())

    for m in re.finditer(r"(?<!\d)(19\d{2}|20\d{2})\s*年?\s*(?:至|到|-|—|–)\s*(19\d{2}|20\d{2})\s*年?", text):
        start, end = int(m.group(1)), int(m.group(2))
        if start <= end:
            _add_slot(
                slots,
                "time",
                m.group(0),
                kind="year_range",
                start_year=start,
                end_year=end,
                normalized=[f"{start}-01-01", f"{end}-12-31"],
                operator="between",
                hard=True,
            )
            occupied_spans.append(m.span())

    def _inside_occupied(index: int) -> bool:
        return any(start <= index < end for start, end in occupied_spans)

    for m in re.finditer(r"(?<!\d)(19\d{2}|20\d{2})\s*年?", text):
        if _inside_occupied(m.start()):
            continue
        year = int(m.group(1))
        _add_slot(
            slots,
            "time",
            m.group(0),
            kind="year",
            year=year,
            normalized=[f"{year}-01-01", f"{year}-12-31"],
            operator="during",
            hard=True,
        )

    relative_map = {
        "去年": today.year - 1,
        "今年": today.year,
        "明年": today.year + 1,
    }
    for surface, year in relative_map.items():
        if surface in text:
            _add_slot(
                slots,
                "time",
                surface,
                kind="relative_year",
                year=year,
                normalized=[f"{year}-01-01", f"{year}-12-31"],
                operator="during",
                hard=True,
            )

    for m in re.finditer(r"近\s*([一二三四五六七八九十\d]{1,3})\s*年", text):
        years = _cn_to_int(m.group(1))
        if years:
            _add_slot(
                slots,
                "time",
                m.group(0),
                kind="rolling_years",
                years=years,
                normalized=[f"{today.year - years + 1}-01-01", today.isoformat()],
                operator="rolling",
                hard=True,
            )


def _extract_event_and_document_slots(text: str, slots: dict[str, list[dict[str, Any]]]):
    congress_patterns = [
        r"((?:党(?:的)?|中共)?\s*([一二三四五六七八九十百\d]{1,6})\s*大)(报告)?",
        r"(第\s*([一二三四五六七八九十百\d]{1,6})\s*次全国代表大会)(报告)?",
    ]
    for pattern in congress_patterns:
        for m in re.finditer(pattern, text):
            surface = _clean_text(m.group(1))
            ordinal = _cn_to_int(m.group(2))
            if not surface or not ordinal:
                continue
            _add_slot(slots, "event", surface, kind="congress", ordinal=ordinal, hard=True)
            if m.group(3) or surface.endswith("报告"):
                _add_slot(slots, "document", surface if surface.endswith("报告") else surface + "报告", kind="report", ordinal=ordinal, hard=True)

    for m in re.finditer(r"《([^》]{2,80})》", text):
        title = _clean_text(m.group(1))
        if not title:
            continue
        if re.search(r"(法|条例|办法|规定|准则|指引)$", title):
            _add_slot(slots, "law_article", title, kind="law_name", hard=True)
        else:
            _add_slot(slots, "document", title, kind="quoted_title", hard=True)

    doc_pattern = rf"([\u4e00-\u9fffA-Za-z0-9·（）()、\- ]{{2,48}}?{DOC_SUFFIX_RE})"
    for m in re.finditer(doc_pattern, text):
        surface = _clean_text(m.group(1)).strip("，。？?：:；; ")
        if len(surface) < 3:
            continue
        if any(surface.endswith(suffix) for suffix in ("有哪些报告", "什么报告")):
            continue
        _add_slot(slots, "document", surface, kind="document_title", hard=True)


def _extract_law_slots(text: str, slots: dict[str, list[dict[str, Any]]]):
    law_name = r"《?([\u4e00-\u9fffA-Za-z0-9·]{2,40}(?:法|条例|办法|规定|准则|指引))》?"
    article = r"第\s*([一二三四五六七八九十百\d]{1,5})\s*(条|章|款|节)"
    for m in re.finditer(law_name + r"\s*" + article, text):
        article_no = _cn_to_int(m.group(2))
        _add_slot(
            slots,
            "law_article",
            m.group(0),
            kind="law_article",
            law_name=m.group(1),
            article_no=article_no,
            article_unit=m.group(3),
            hard=True,
        )
    for m in re.finditer(article, text):
        article_no = _cn_to_int(m.group(1))
        _add_slot(
            slots,
            "law_article",
            m.group(0),
            kind="article_reference",
            article_no=article_no,
            article_unit=m.group(2),
            hard=True,
        )


def _extract_space_slots(text: str, slots: dict[str, list[dict[str, Any]]]):
    compact = _compact_text(text)
    for label, spec in SPACE_CATALOG.items():
        aliases = spec.get("aliases", [])
        if any(_compact_text(alias) in compact for alias in aliases):
            _add_slot(slots, "space", label, kind="geo", canonical=spec["canonical"], hard=True)

    for m in re.finditer(r"([\u4e00-\u9fff]{2,12}(?:地区|省|市|自治区|特别行政区|特区))", text):
        surface = m.group(1)
        if surface in {"哪些地区", "什么地区"}:
            continue
        surface_key = _compact_text(surface)
        if any(surface_key in _compact_text(item.get("surface")) or _compact_text(item.get("surface")) in surface_key for item in slots.get("space", [])):
            continue
        _add_slot(slots, "space", surface, kind="geo_text", hard=True)


def _extract_version_slots(text: str, slots: dict[str, list[dict[str, Any]]]):
    version_terms = {
        "新版": {"aliases": ["新版", "新版本", "最新版本", "new version"], "hard": True},
        "旧版": {"aliases": ["旧版", "旧版本", "原版本", "old version"], "hard": True},
        "现行有效": {"aliases": ["现行有效", "现行版本", "current effective", "current version"], "hard": False},
        "修订版": {"aliases": ["修订版", "修正版", "revised version", "amended version"], "hard": True},
        "废止": {"aliases": ["废止", "失效", "abolished", "repealed"], "hard": True},
    }
    lower = text.lower()
    for label, spec in version_terms.items():
        aliases = spec["aliases"]
        if any(alias.lower() in lower for alias in aliases):
            _add_slot(slots, "version", label, kind="version_label", aliases=aliases, hard=bool(spec["hard"]))
    for m in re.finditer(r"(?<!\d)(19\d{2}|20\d{2})\s*(?:年)?\s*(?:版|修订版|修正版|版本)", text):
        year = int(m.group(1))
        _add_slot(slots, "version", m.group(0), kind="version_year", year=year, hard=True)


def _extract_topic_slots(text: str, slots: dict[str, list[dict[str, Any]]]):
    compact = _compact_text(text)
    for label, spec in DOMAIN_TOPIC_CATALOG.items():
        aliases = spec.get("aliases", [])
        if any(_compact_text(alias) in compact for alias in aliases):
            slot_type = "industry" if label.endswith("行业") or "财富" in label else "entity"
            _add_slot(slots, slot_type, label, kind="domain_topic", aliases=aliases, hard=False)

    for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9·]{2,24}(?:行业|产业|领域|市场|业务))", text):
        surface = m.group(1)
        if "关于" in surface:
            surface = surface.split("关于")[-1]
        if "有关" in surface:
            surface = surface.split("有关")[-1]
        surface = surface.strip("的了在和与及、，。？?：:；; ")
        if surface in {"哪些行业", "什么行业", "相关业务"}:
            continue
        if len(surface) > 12 and re.search(r"(报告|文件|问题|什么|哪些)", surface):
            continue
        _add_slot(slots, "industry", surface, kind="topic_phrase", hard=False)

    for m in re.finditer(r"([\u4e00-\u9fffA-Za-z0-9·]{2,40}(?:委员会|协会|集团|公司|银行|政府|基金会|监管局|管理局|证监会|金管局|银保监会|投资推广署))", text):
        _add_slot(slots, "organization", m.group(1), kind="organization", hard=False)


def _guess_answer_type(question: str) -> str:
    normalized = _compact_text(question)
    if any(term in normalized for term in ("有没有", "是否", "会不会", "能不能", "有没有关于")):
        return "existence_check"
    if any(term in normalized for term in ("区别", "对比", "比较", "差异", "vs", "versus")):
        return "comparison"
    if any(term in normalized for term in ("有哪些", "列举", "包括哪些", "什么措施")):
        return "enumeration"
    if any(term in normalized for term in ("怎么", "如何", "怎样", "流程", "步骤")):
        return "process"
    if any(term in normalized for term in ("为什么", "原因", "影响")):
        return "analysis"
    return "fact_answer"


def _query_core(question: str, slots: dict[str, list[dict[str, Any]]]) -> str:
    core = str(question or "")
    for items in slots.values():
        for item in items:
            surface = str(item.get("surface") or "")
            if surface:
                core = core.replace(surface, " ")
    core = re.sub(r"[，。？！、；：,.?!;:()\[\]（）【】《》]", " ", core)
    core = re.sub(r"\s+", " ", core).strip()
    if len(core) < 4:
        core = _clean_text(question)
    return core


async def _try_llm_boundary_parse(question: str, chat_mdl) -> dict[str, Any] | None:
    if not chat_mdl or os.environ.get("RAGFLOW_BOUNDARY_LLM_PARSE", "").lower() not in {"1", "true", "yes"}:
        return None
    system = (
        "Extract a compact JSON semantic frame for retrieval boundary constraints. "
        "Return JSON only. Slots: time, space, document, event, entity, industry, "
        "organization, version, law_article, effective_range. Mark only explicit "
        "or deterministically implied boundaries as hard."
    )
    user = (
        "Question:\n"
        f"{question}\n\n"
        "JSON schema:\n"
        '{"intent":"rag_question","answer_type":"fact_answer","query_core":"","slots":'
        '{"time":[],"space":[],"document":[],"event":[],"entity":[],"industry":[],'
        '"organization":[],"version":[],"law_article":[],"effective_range":[]},"confidence":0.0}'
    )
    try:
        raw = await chat_mdl.async_chat(system, [{"role": "user", "content": user}], {"temperature": 0.0, "max_tokens": 800})
        match = re.search(r"\{.*\}", str(raw or ""), flags=re.S)
        if not match:
            return None
        parsed = json.loads(match.group(0))
        return parsed if isinstance(parsed, dict) else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("BoundaryParser LLM parse failed: %s", exc)
        return None


def _merge_llm_slots(slots: dict[str, list[dict[str, Any]]], llm_frame: dict[str, Any] | None):
    if not llm_frame:
        return
    llm_slots = llm_frame.get("slots") or {}
    if not isinstance(llm_slots, dict):
        return
    for slot_type in BOUNDARY_SLOT_KEYS:
        values = llm_slots.get(slot_type) or []
        if not isinstance(values, list):
            continue
        for value in values[:8]:
            if isinstance(value, str):
                _add_slot(slots, slot_type, value, kind="llm", hard=slot_type in BOUNDARY_TYPES)
            elif isinstance(value, dict):
                surface = value.get("surface") or value.get("value") or value.get("canonical")
                if surface:
                    _add_slot(
                        slots,
                        slot_type,
                        str(surface),
                        kind=value.get("kind") or "llm",
                        hard=bool(value.get("hard", slot_type in BOUNDARY_TYPES)),
                    )


async def parse_question_boundary(
    original_question: str,
    expanded_question: str | None = None,
    chat_mdl=None,
    now: date | datetime | None = None,
) -> dict[str, Any]:
    """Parse a user question into an intent + slot frame.

    The parser is intentionally conservative: explicit boundaries are hard,
    topic words are soft until combined into a retrieval plan.
    """
    today = (now.date() if isinstance(now, datetime) else now) or date.today()
    source_question = _clean_text(original_question)
    combined = _clean_text(f"{original_question or ''}\n{expanded_question or ''}")
    slots = {key: [] for key in BOUNDARY_SLOT_KEYS}

    _extract_time_slots(source_question, slots, today)
    _extract_event_and_document_slots(source_question, slots)
    _extract_law_slots(source_question, slots)
    _extract_space_slots(source_question, slots)
    _extract_version_slots(source_question, slots)
    _extract_topic_slots(combined, slots)

    llm_frame = await _try_llm_boundary_parse(source_question, chat_mdl)
    _merge_llm_slots(slots, llm_frame)

    hard_count = sum(1 for slot_type in BOUNDARY_TYPES for item in slots[slot_type] if item.get("hard"))
    confidence = 0.72 + min(0.2, hard_count * 0.04)
    if llm_frame:
        confidence = max(confidence, min(0.95, float(llm_frame.get("confidence") or confidence)))

    return {
        "intent": "rag_question",
        "answer_type": _guess_answer_type(source_question),
        "query_core": _query_core(source_question, slots),
        "slots": slots,
        "confidence": round(confidence, 3),
        "requires_knowledge": True,
    }


def _constraint(
    constraint_type: str,
    surface: str,
    canonical: str | None = None,
    aliases: list[str] | None = None,
    hard: bool = True,
    confidence: float = 0.9,
    **extra,
) -> dict[str, Any]:
    alias_values = _dedupe([surface, canonical or "", *(aliases or [])])
    return {
        "type": constraint_type,
        "surface": surface,
        "canonical": canonical or surface,
        "aliases": alias_values,
        "hard": hard,
        "confidence": confidence,
        **extra,
    }


def _normalize_time_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    aliases = [surface]
    year = slot.get("year")
    if year:
        aliases.extend([str(year), f"{year}年"])
    if slot.get("start_year") and slot.get("end_year"):
        aliases.extend([str(slot["start_year"]), str(slot["end_year"]), f"{slot['start_year']}年", f"{slot['end_year']}年"])
    return _constraint(
        "time",
        surface,
        canonical=str(slot.get("normalized") or year or surface),
        aliases=aliases,
        hard=bool(slot.get("hard", True)),
        kind=slot.get("kind"),
        year=year,
        start_year=slot.get("start_year"),
        end_year=slot.get("end_year"),
        operator=slot.get("operator"),
    )


def _normalize_event_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    ordinal = slot.get("ordinal")
    cn = _int_to_cn(int(ordinal)) if ordinal else ""
    aliases = [surface]
    canonical = surface
    year = None
    if ordinal and slot.get("kind") == "congress":
        canonical = f"中国共产党第{cn}次全国代表大会"
        aliases.extend(
            [
                f"{cn}大",
                f"党的{cn}大",
                f"中共{cn}大",
                f"第{cn}次全国代表大会",
                canonical,
            ]
        )
        year = _congress_year(int(ordinal))
        if year:
            aliases.append(str(year))
    return _constraint(
        "event",
        surface,
        canonical=canonical,
        aliases=aliases,
        hard=bool(slot.get("hard", True)),
        kind=slot.get("kind"),
        ordinal=ordinal,
        derived_year=year,
    )


def _normalize_document_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    ordinal = slot.get("ordinal")
    aliases = [surface]
    canonical = surface
    year = None
    if ordinal:
        cn = _int_to_cn(int(ordinal))
        canonical = f"中国共产党第{cn}次全国代表大会报告"
        aliases.extend(
            [
                f"{cn}大报告",
                f"党的{cn}大报告",
                f"中共{cn}大报告",
                f"第{cn}次全国代表大会报告",
                canonical,
            ]
        )
        year = _congress_year(int(ordinal))
    return _constraint(
        "document",
        surface,
        canonical=canonical,
        aliases=aliases,
        hard=bool(slot.get("hard", True)),
        kind=slot.get("kind"),
        ordinal=ordinal,
        derived_year=year,
    )


def _normalize_space_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    spec = SPACE_CATALOG.get(surface)
    if spec:
        return _constraint(
            "space",
            surface,
            canonical=spec["canonical"],
            aliases=spec.get("aliases", []),
            hard=bool(slot.get("hard", True)),
            kind=slot.get("kind"),
            near_miss=spec.get("near_miss", []),
        )
    return _constraint("space", surface, aliases=[surface], hard=bool(slot.get("hard", True)), kind=slot.get("kind"))


def _normalize_version_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    aliases = slot.get("aliases") or [surface]
    year = slot.get("year")
    if year:
        aliases.extend([str(year), f"{year}版", f"{year}年版"])
    return _constraint("version", surface, aliases=aliases, hard=bool(slot.get("hard", True)), kind=slot.get("kind"), year=year)


def _normalize_law_slot(slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    aliases = [surface]
    law_name = slot.get("law_name")
    article_no = slot.get("article_no")
    unit = slot.get("article_unit")
    if law_name:
        aliases.append(str(law_name))
    if article_no and unit:
        aliases.extend([f"第{article_no}{unit}", f"第{_int_to_cn(int(article_no))}{unit}"])
    return _constraint(
        "law_article",
        surface,
        aliases=aliases,
        hard=bool(slot.get("hard", True)),
        kind=slot.get("kind"),
        law_name=law_name,
        article_no=article_no,
        article_unit=unit,
    )


def _normalize_topic_slot(slot_type: str, slot: dict[str, Any]) -> dict[str, Any]:
    surface = str(slot.get("surface") or "")
    spec = DOMAIN_TOPIC_CATALOG.get(surface)
    aliases = list(slot.get("aliases") or [])
    canonical = surface
    if spec:
        canonical = spec["canonical"]
        aliases.extend(spec.get("aliases", []))
    return _constraint(slot_type, surface, canonical=canonical, aliases=aliases, hard=False, kind=slot.get("kind"), confidence=0.78)


def normalize_boundary_slots(boundary_frame: dict[str, Any], now: date | datetime | None = None) -> dict[str, Any]:
    slots = (boundary_frame or {}).get("slots") or {}
    constraints: list[dict[str, Any]] = []

    for slot in slots.get("time") or []:
        constraints.append(_normalize_time_slot(slot))
    for slot in slots.get("space") or []:
        constraints.append(_normalize_space_slot(slot))
    for slot in slots.get("document") or []:
        constraints.append(_normalize_document_slot(slot))
    for slot in slots.get("event") or []:
        constraints.append(_normalize_event_slot(slot))
    for slot in slots.get("version") or []:
        constraints.append(_normalize_version_slot(slot))
    for slot in slots.get("law_article") or []:
        constraints.append(_normalize_law_slot(slot))
    for slot_type in TOPIC_TYPES:
        for slot in slots.get(slot_type) or []:
            constraints.append(_normalize_topic_slot(slot_type, slot))

    deduped = []
    seen = set()
    for constraint in constraints:
        key = (constraint.get("type"), _compact_text(constraint.get("canonical")))
        if key in seen:
            continue
        seen.add(key)
        deduped.append(constraint)

    frame = deepcopy(boundary_frame or {})
    frame["constraints"] = deduped
    return frame


def _constraint_alias_group(constraint: dict[str, Any]) -> list[str]:
    return _dedupe([constraint.get("canonical") or "", *(constraint.get("aliases") or [])])


def _build_metadata_filters(hard_constraints: list[dict[str, Any]]) -> dict[str, Any]:
    years = set()
    title_terms = []
    for constraint in hard_constraints:
        if constraint.get("type") in {"time", "version"}:
            if constraint.get("year"):
                years.add(int(constraint["year"]))
            if constraint.get("start_year") and constraint.get("end_year"):
                years.update(range(int(constraint["start_year"]), int(constraint["end_year"]) + 1))
        if constraint.get("derived_year"):
            years.add(int(constraint["derived_year"]))
        if constraint.get("type") == "document":
            title_terms.extend((constraint.get("aliases") or [])[:5])
    filters = {}
    if years:
        filters["year"] = sorted(years)
    if title_terms:
        filters["doc_title_contains_any"] = _dedupe(title_terms)
    return filters


def _generate_near_miss_terms(hard_constraints: list[dict[str, Any]]) -> list[str]:
    terms: list[str] = []
    for constraint in hard_constraints:
        ctype = constraint.get("type")
        if ctype == "event" and constraint.get("ordinal"):
            ordinal = int(constraint["ordinal"])
            for near in (ordinal - 1, ordinal + 1):
                if near > 0:
                    cn = _int_to_cn(near)
                    terms.extend([f"{cn}大", f"党的{cn}大", f"第{cn}次全国代表大会"])
        elif ctype == "document" and constraint.get("ordinal"):
            ordinal = int(constraint["ordinal"])
            for near in (ordinal - 1, ordinal + 1):
                if near > 0:
                    cn = _int_to_cn(near)
                    terms.extend([f"{cn}大报告", f"党的{cn}大报告", f"第{cn}次全国代表大会报告"])
        elif ctype == "time" and constraint.get("year"):
            year = int(constraint["year"])
            terms.extend([str(year - 1), str(year + 1), f"{year - 1}年", f"{year + 1}年"])
        elif ctype == "space":
            terms.extend(constraint.get("near_miss") or [])
        elif ctype == "version":
            surface = _compact_text(constraint.get("surface"))
            if "新版" in surface or "新版本" in surface:
                terms.extend(["旧版", "旧版本", "原版本"])
            if "旧版" in surface or "旧版本" in surface:
                terms.extend(["新版", "新版本", "最新版本"])
        elif ctype == "law_article" and constraint.get("article_no"):
            no = int(constraint["article_no"])
            unit = constraint.get("article_unit") or "条"
            if no > 1:
                terms.append(f"第{no - 1}{unit}")
            terms.append(f"第{no + 1}{unit}")
    return _dedupe(terms)


def _compact_query(parts: list[str]) -> str:
    terms = []
    for part in parts:
        for term in re.split(r"[\s,，;；]+", str(part or "")):
            term = term.strip()
            if term:
                terms.append(term)
    terms = _dedupe(terms)
    query = " ".join(terms[:MAX_QUERY_TERMS])
    return query[:MAX_QUERY_CHARS].rstrip()


def _build_canonical_retrieval_expression(boundary_frame: dict[str, Any], original_question: str) -> str:
    return _build_standardized_retrieval_expression(boundary_frame, original_question, "Chinese")


def _english_ordinal(num: int) -> str:
    if 10 <= num % 100 <= 20:
        suffix = "th"
    else:
        suffix = {1: "st", 2: "nd", 3: "rd"}.get(num % 10, "th")
    return f"{num}{suffix}"


def _constraint_alias_for_language(constraint: dict[str, Any], language: str) -> str:
    aliases = _constraint_alias_group(constraint)
    if not aliases:
        return ""
    if language == "Chinese":
        for alias in aliases:
            if re.search(r"[\u4e00-\u9fff]", alias):
                return alias
        return aliases[0]
    if language == "Chinese (Traditional)":
        return _simplified_to_traditional(_constraint_alias_for_language(constraint, "Chinese"))
    if language == "English":
        for alias in aliases:
            if re.search(r"[A-Za-z]", alias):
                return alias
        return ""
    return aliases[0]


def _english_phrase_for_constraint(constraint: dict[str, Any]) -> str:
    ctype = constraint.get("type")
    surface = _clean_text(constraint.get("surface"))
    if ctype == "document":
        ordinal = constraint.get("ordinal")
        if ordinal:
            return f"the report of the {_english_ordinal(int(ordinal))} National Congress of the Communist Party of China"
        alias = _constraint_alias_for_language(constraint, "English")
        if alias:
            return alias
    elif ctype == "event":
        ordinal = constraint.get("ordinal")
        if ordinal:
            return f"the {_english_ordinal(int(ordinal))} National Congress of the Communist Party of China"
        alias = _constraint_alias_for_language(constraint, "English")
        if alias:
            return alias
    elif ctype == "time":
        year = constraint.get("year") or constraint.get("derived_year")
        start_year = constraint.get("start_year")
        end_year = constraint.get("end_year")
        operator = constraint.get("operator")
        if operator == "as_of" and year:
            return f"by the end of {year}"
        if operator == "between" and start_year and end_year:
            return f"from {start_year} to {end_year}"
        if operator in {"during", "rolling"} and year:
            return f"in {year}"
        if year:
            return f"in {year}"
        if surface:
            return _translate_known_english(surface)
    elif ctype == "version":
        alias = _constraint_alias_for_language(constraint, "English")
        if alias:
            return alias
        if "新版" in surface or "新版本" in surface or "最新" in surface:
            return "new version"
        if "旧版" in surface or "旧版本" in surface or "原版本" in surface:
            return "old version"
        if "现行" in surface:
            return "current version"
        if "修订" in surface or "修正版" in surface:
            return "revised version"
    elif ctype == "law_article":
        article_no = constraint.get("article_no")
        law_name = _constraint_alias_for_language(constraint, "English") or _translate_known_english(constraint.get("law_name") or surface)
        if article_no and law_name:
            return f"Article {article_no} of {law_name}"
        if article_no:
            return f"Article {article_no}"
        if law_name:
            return law_name
    alias = _constraint_alias_for_language(constraint, "English")
    if alias:
        return alias
    if surface:
        return _translate_known_english(surface)
    return ""


def _translate_known_english(text: str | None) -> str:
    result = _clean_text(text)
    for simplified, english in sorted(ENGLISH_LANGUAGE_HINTS.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(simplified, english)
    result = re.sub(r"\s+", " ", result).strip()
    return result


def _build_standardized_retrieval_expression(
    boundary_frame: dict[str, Any],
    original_question: str,
    language: str,
) -> str:
    constraints = list((boundary_frame or {}).get("constraints") or [])
    doc_terms: list[str] = []
    topic_terms: list[str] = []
    event_terms: list[str] = []
    time_terms: list[str] = []
    space_terms: list[str] = []
    version_terms: list[str] = []
    law_terms: list[str] = []
    for constraint in constraints:
        ctype = constraint.get("type")
        if language == "English":
            term = _english_phrase_for_constraint(constraint)
        else:
            term = _constraint_alias_for_language(constraint, language)
        if ctype == "document":
            if term:
                doc_terms.append(term)
        elif ctype == "event":
            if term:
                event_terms.append(term)
        elif ctype in {"industry", "entity", "organization"}:
            if term:
                topic_terms.append(term)
        elif ctype == "time":
            if term:
                time_terms.append(term)
        elif ctype == "space":
            if term:
                space_terms.append(term)
        elif ctype == "version":
            if term:
                version_terms.append(term)
        elif ctype == "law_article":
            if term:
                law_terms.append(term)

    doc_term = doc_terms[0] if doc_terms else ""
    event_term = event_terms[0] if event_terms else ""
    topic_term = topic_terms[0] if topic_terms else ""
    time_term = time_terms[0] if time_terms else ""
    space_term = space_terms[0] if space_terms else ""
    version_term = version_terms[0] if version_terms else ""
    law_term = law_terms[0] if law_terms else ""
    intent = str((boundary_frame or {}).get("answer_type") or "")
    if language == "English":
        if intent in {"existence_check", "fact_answer"}:
            intent_phrase = "policy discussions viewpoints"
        elif intent == "process":
            intent_phrase = "what does it say viewpoints"
        elif intent == "enumeration":
            intent_phrase = "what policies or discussions are there"
        elif intent == "comparison":
            intent_phrase = "comparison differences"
        elif intent == "analysis":
            intent_phrase = "reasons and impacts"
        else:
            intent_phrase = "policy discussions viewpoints"
    else:
        if intent in {"existence_check", "fact_answer"}:
            intent_phrase = "政策 论述 观点"
        elif intent == "process":
            intent_phrase = "怎么讲 观点"
        elif intent == "enumeration":
            intent_phrase = "有哪些 政策 论述"
        elif intent == "comparison":
            intent_phrase = "对比 区别"
        elif intent == "analysis":
            intent_phrase = "原因 影响"
        else:
            intent_phrase = "政策 论述 观点"

    if language == "English":
        parts = []
        base_term = doc_term or event_term
        if base_term:
            parts.append(base_term)
        if topic_term:
            if parts:
                parts.append("about")
            parts.append(topic_term)
        if space_term:
            parts.extend(["in", space_term])
        if time_term:
            parts.append(time_term)
        if version_term:
            parts.append(version_term)
        if law_term:
            parts.append(law_term)
        parts.append(intent_phrase)
    else:
        parts = [doc_term or event_term]
        if time_term:
            parts.append(time_term)
        if space_term:
            parts.append(space_term)
        if topic_term:
            if parts and parts[-1]:
                parts.append("关于")
            parts.append(topic_term)
        if version_term:
            parts.append(version_term)
        if law_term:
            parts.append(law_term)
        parts.append(intent_phrase)

    canonical = _compact_query(parts)
    return canonical or _clean_text(original_question)


def _simplified_to_traditional(text: str) -> str:
    result = str(text or "")
    for simplified, traditional in sorted(SIMPLIFIED_TRADITIONAL_MAP.items(), key=lambda item: len(item[0]), reverse=True):
        result = result.replace(simplified, traditional)
    return result


def _build_language_queries(canonical_query: str, target_languages: list[str] | None) -> dict[str, str]:
    normalized_targets = [normalize_cross_language(lang) for lang in (target_languages or [])]
    normalized_targets = [lang for lang in normalized_targets if lang and lang != "Multilingual/Auto"]
    language_queries: dict[str, str] = {}
    source_language = infer_query_language(canonical_query)
    if source_language:
        normalized_targets.append(source_language)
    if not normalized_targets:
        return language_queries

    simplified_query = _clean_text(canonical_query)
    traditional_query = _simplified_to_traditional(simplified_query)
    english_query = _translate_known_english(canonical_query)
    if not english_query:
        english_query = canonical_query
    english_query = re.sub(r"\s+", " ", english_query).strip()

    for language in _dedupe(normalized_targets):
        if language == "Chinese":
            language_queries["Chinese"] = simplified_query
            language_queries.setdefault("Chinese (Traditional)", traditional_query)
        elif language == "Chinese (Traditional)":
            language_queries["Chinese (Traditional)"] = traditional_query
        elif language == "English":
            language_queries["English"] = english_query
        else:
            # Keep unsupported languages available as a fallback key while
            # allowing the LLM cross-language expander to rewrite them later.
            language_queries[language] = simplified_query
    return language_queries


def build_retrieval_plan(
    original_question: str,
    expanded_question: str | None,
    normalized_boundary: dict[str, Any],
    target_languages: list[str] | None = None,
) -> dict[str, Any]:
    constraints = list((normalized_boundary or {}).get("constraints") or [])
    has_boundary = any(c.get("hard") and c.get("type") in BOUNDARY_TYPES for c in constraints)
    hard_constraints = [
        c
        for c in constraints
        if c.get("hard") and c.get("type") in BOUNDARY_TYPES
    ]

    hard_constraints = [c for c in hard_constraints if _constraint_alias_group(c)]
    must_groups = []
    seen_groups = set()
    for constraint in hard_constraints:
        group = _constraint_alias_group(constraint)
        key = tuple(_compact_text(alias) for alias in group)
        if not group or key in seen_groups:
            continue
        seen_groups.add(key)
        must_groups.append(group)

    query_core = str((normalized_boundary or {}).get("query_core") or original_question or "")
    primary_parts = [query_core, expanded_question or original_question or ""]
    for constraint in hard_constraints:
        aliases = _constraint_alias_group(constraint)
        primary_parts.extend(aliases[:3])
    primary_query = _compact_query(primary_parts) or _clean_text(expanded_question or original_question)

    query_variants = [primary_query]
    for group in must_groups[:6]:
        query_variants.append(_compact_query([query_core, " ".join(group[:3])]))
    if len(must_groups) >= 2:
        query_variants.append(_compact_query([query_core, " ".join(must_groups[0][:2]), " ".join(must_groups[1][:2])]))
    query_variants = _dedupe([q for q in query_variants if q])

    canonical_query = _build_canonical_retrieval_expression(normalized_boundary or {}, original_question)
    language_queries = _build_language_queries(canonical_query, target_languages)
    if language_queries:
        query_variants = _dedupe([*query_variants, *language_queries.values()])

    should_terms = []
    for constraint in constraints:
        if constraint not in hard_constraints:
            should_terms.extend(_constraint_alias_group(constraint)[:3])

    plan = {
        "enabled": True,
        "boundary_frame": normalized_boundary,
        "canonical_query": canonical_query,
        "primary_query": primary_query,
        "query_variants": query_variants,
        "language_queries": language_queries,
        "must_groups": must_groups,
        "must_constraints": [
            {
                "type": c.get("type"),
                "surface": c.get("surface"),
                "canonical": c.get("canonical"),
                "aliases": _constraint_alias_group(c),
            }
            for c in hard_constraints
        ],
        "should_terms": _dedupe(should_terms),
        "near_miss_terms": _generate_near_miss_terms(hard_constraints),
        "metadata_filters": _build_metadata_filters(hard_constraints),
        "evidence_policy": "direct_evidence_only" if must_groups else "standard",
    }
    plan["plan_hash"] = boundary_plan_hash(plan)
    return plan


def boundary_plan_hash(plan: dict[str, Any] | None) -> str:
    if not plan:
        return "none"
    payload = {
        "must_groups": plan.get("must_groups") or [],
        "near_miss_terms": plan.get("near_miss_terms") or [],
        "metadata_filters": plan.get("metadata_filters") or {},
        "evidence_policy": plan.get("evidence_policy"),
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return sha1(raw.encode("utf-8", "ignore")).hexdigest()[:16]


def _chunk_value(chunk: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = chunk.get(key)
        if value is not None:
            return str(value)
    return ""


def _chunk_constraint_text(chunk: dict[str, Any]) -> str:
    parts = [
        _chunk_value(chunk, "docnm_kwd", "document_name"),
        _chunk_value(chunk, "content", "content_with_weight"),
        _chunk_value(chunk, "title", "url"),
    ]
    meta = chunk.get("document_metadata") or chunk.get("metadata") or {}
    if isinstance(meta, dict):
        parts.extend(str(v) for v in meta.values() if v is not None)
    extra = chunk.get("extra")
    if isinstance(extra, dict):
        parts.extend(str(v) for v in extra.values() if isinstance(v, (str, int, float)))
    return "\n".join(parts)


def _contains_alias(text: str, alias: str) -> bool:
    if not alias:
        return False
    compact_text = _compact_text(text)
    compact_alias = _compact_text(alias)
    if not compact_alias:
        return False
    return compact_alias in compact_text


def classify_chunk_by_constraints(chunk: dict[str, Any], retrieval_plan: dict[str, Any]) -> dict[str, Any]:
    text = _chunk_constraint_text(chunk)
    must_groups = retrieval_plan.get("must_groups") or []
    near_miss_terms = retrieval_plan.get("near_miss_terms") or []

    satisfied = []
    missing = []
    for group in must_groups:
        hits = [alias for alias in group if _contains_alias(text, alias)]
        if hits:
            satisfied.append(hits[:5])
        else:
            missing.append(group[:5])

    near_hits = [term for term in near_miss_terms if _contains_alias(text, term)]

    if not must_groups:
        status = "standard"
        usable = True
    elif not missing:
        status = "direct_evidence"
        usable = True
    elif near_hits:
        status = "near_miss"
        usable = False
    elif satisfied:
        status = "partial_evidence"
        usable = False
    else:
        status = "unrelated"
        usable = False

    return {
        "status": status,
        "usable_for_answer": usable,
        "satisfied_groups": satisfied,
        "missing_groups": missing,
        "near_miss_hits": _dedupe(near_hits),
    }


def enforce_boundary_constraints(kbinfos: dict[str, Any], retrieval_plan: dict[str, Any] | None) -> dict[str, Any]:
    if not retrieval_plan or retrieval_plan.get("evidence_policy") != "direct_evidence_only":
        return kbinfos

    chunks = [chunk for chunk in (kbinfos.get("chunks") or []) if isinstance(chunk, dict)]
    if not chunks:
        kbinfos["boundary_constraints"] = {
            "enabled": True,
            "status": "no_chunks",
            "plan_hash": retrieval_plan.get("plan_hash"),
            "must_constraints": retrieval_plan.get("must_constraints") or [],
            "stats": {"direct_evidence": 0, "partial_evidence": 0, "near_miss": 0, "unrelated": 0},
        }
        return kbinfos

    direct = []
    rejected = []
    stats = {"direct_evidence": 0, "partial_evidence": 0, "near_miss": 0, "unrelated": 0, "standard": 0}

    for chunk in chunks:
        result = classify_chunk_by_constraints(chunk, retrieval_plan)
        chunk["constraint_result"] = result
        status = result["status"]
        stats[status] = stats.get(status, 0) + 1
        if result["usable_for_answer"]:
            direct.append(chunk)
        else:
            rejected.append(chunk)

    if direct:
        kbinfos["chunks"] = direct
        kbinfos["constraint_audit_chunks"] = rejected
        status = "has_direct_evidence"
    else:
        kbinfos["chunks"] = []
        kbinfos["constraint_audit_chunks"] = rejected
        kbinfos["doc_aggs"] = []
        kbinfos["total"] = 0
        status = "no_direct_evidence"

    direct_doc_ids = {chunk.get("doc_id") or chunk.get("document_id") for chunk in direct}
    if direct_doc_ids:
        kbinfos["doc_aggs"] = [
            doc
            for doc in (kbinfos.get("doc_aggs") or [])
            if (doc.get("doc_id") or doc.get("id") or doc.get("document_id")) in direct_doc_ids
        ]

    kbinfos["boundary_constraints"] = {
        "enabled": True,
        "status": status,
        "plan_hash": retrieval_plan.get("plan_hash"),
        "must_constraints": retrieval_plan.get("must_constraints") or [],
        "near_miss_terms": retrieval_plan.get("near_miss_terms") or [],
        "metadata_filters": retrieval_plan.get("metadata_filters") or {},
        "stats": stats,
    }
    return kbinfos


def format_boundary_guidance(retrieval_plan: dict[str, Any] | None, kbinfos: dict[str, Any] | None = None, chinese: bool = True) -> str:
    if not retrieval_plan or retrieval_plan.get("evidence_policy") != "direct_evidence_only":
        return ""
    constraints = retrieval_plan.get("must_constraints") or []
    if not constraints:
        return ""
    labels = [str(item.get("canonical") or item.get("surface")) for item in constraints if item.get("canonical") or item.get("surface")]
    status = ((kbinfos or {}).get("boundary_constraints") or {}).get("status")
    if chinese:
        return (
            "\n\n### 边界约束指引\n"
            "用户问题包含硬性边界约束。只能使用已标记为 direct_evidence 的知识库片段作为回答依据。"
            "不要把 near_miss、partial_evidence、background_only 或 unrelated 片段作为结论证据引用。"
            "如果没有 direct_evidence，必须说明知识库中未找到同时满足这些边界约束的直接证据。"
            f"\n硬性约束：{'；'.join(labels[:12])}"
            + (f"\n当前约束覆盖状态：{status}" if status else "")
        )
    return (
        "\n\n### Boundary constraint guidance\n"
        "The user question contains hard boundary constraints. Use only chunks marked direct_evidence as answer evidence. "
        "Do not cite near_miss, partial_evidence, background_only, or unrelated chunks as proof. "
        "If no direct_evidence exists, state that the selected knowledge base has no direct evidence satisfying all constraints."
        f"\nHard constraints: {'; '.join(labels[:12])}"
        + (f"\nConstraint coverage status: {status}" if status else "")
    )


def format_boundary_no_evidence_response(question: str, retrieval_plan: dict[str, Any] | None) -> str:
    if not retrieval_plan or retrieval_plan.get("evidence_policy") != "direct_evidence_only":
        return ""
    constraints = retrieval_plan.get("must_constraints") or []
    if not constraints:
        return ""
    labels = [str(item.get("canonical") or item.get("surface")) for item in constraints if item.get("canonical") or item.get("surface")]
    if re.search(r"[\u4e00-\u9fff]", question or ""):
        return (
            "知识库中未找到同时满足以下边界约束的直接证据，因此不能基于知识库给出带引用的结论："
            + "；".join(labels[:12])
            + "。当前召回材料即使涉及相近主题，也不能作为该问题的直接依据。"
        )
    return (
        "No direct evidence satisfying all boundary constraints was found in the selected knowledge base: "
        + "; ".join(labels[:12])
        + ". Retrieved near-miss or partial materials were not used as answer evidence."
    )
