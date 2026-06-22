#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#

import re
from collections.abc import Iterable


LANGUAGE_ALIASES = {
    "zh": "Chinese",
    "zh-cn": "Chinese",
    "zh_cn": "Chinese",
    "zh-hans": "Chinese",
    "zh_hans": "Chinese",
    "cn": "Chinese",
    "chinese": "Chinese",
    "中文": "Chinese",
    "汉语": "Chinese",
    "簡體中文": "Chinese",
    "简体中文": "Chinese",
    "en": "English",
    "en-us": "English",
    "en_us": "English",
    "english": "English",
    "英文": "English",
}

MULTILINGUAL_LANGUAGE_VALUES = {
    "auto",
    "multilingual",
    "multi-lingual",
    "multi",
    "mixed",
    "multilingual/auto",
    "auto/multilingual",
    "multilingual-auto",
    "auto multilingual",
    "多语言",
    "多語言",
    "混合",
    "自动",
    "自動",
    "自动识别",
    "自動識別",
}

DEFAULT_MULTILINGUAL_TARGETS = ("Chinese", "English")


def normalize_cross_language(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    lowered = raw.lower()
    if lowered in MULTILINGUAL_LANGUAGE_VALUES:
        return "Multilingual/Auto"
    return LANGUAGE_ALIASES.get(lowered, raw)


def is_multilingual_language(value: str | None) -> bool:
    return normalize_cross_language(value) == "Multilingual/Auto"


def infer_query_language(question: str) -> str:
    if re.search(r"[\u4e00-\u9fff]", question or ""):
        return "Chinese"
    if re.search(r"[A-Za-z]", question or ""):
        return "English"
    return ""


def _iter_languages(values) -> Iterable[str]:
    if values is None:
        return []
    if isinstance(values, str):
        return [values]
    if isinstance(values, Iterable):
        return values
    return [str(values)]


def resolve_auto_cross_languages(
    kb_ids: list[str] | None,
    question: str,
    configured_languages: list[str] | str | None,
    *,
    kb_loader=None,
) -> list[str]:
    """Resolve final cross-language expansion targets from explicit config and KB language.

    The original query already participates in retrieval. Therefore Chinese
    queries against Multilingual/Auto datasets only need an English rewrite,
    English queries only need a Chinese rewrite, and unknown-language queries
    expand to both Chinese and English.
    """

    languages: list[str] = []
    seen: set[str] = set()
    query_language = infer_query_language(question)

    def add_language(language: str | None) -> None:
        normalized = normalize_cross_language(language)
        if not normalized:
            return
        if normalized == "Multilingual/Auto":
            for target in DEFAULT_MULTILINGUAL_TARGETS:
                add_language(target)
            return
        if normalized == query_language or normalized in seen:
            return
        seen.add(normalized)
        languages.append(normalized)

    for language in _iter_languages(configured_languages):
        add_language(language)

    if kb_loader is None:
        from api.db.services.knowledgebase_service import KnowledgebaseService

        def kb_loader(kb_id):
            ok, kb = KnowledgebaseService.get_by_id(kb_id)
            return kb if ok else None

    for kb_id in kb_ids or []:
        try:
            kb = kb_loader(kb_id)
        except Exception:
            kb = None
        if kb:
            add_language(getattr(kb, "language", None))

    return languages
