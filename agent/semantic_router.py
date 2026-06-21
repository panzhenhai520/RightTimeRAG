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

import json
import re
from typing import Any


AGENT_HISTORY_MAX_CHARS = 12000

AGENT_HISTORY_ERROR_MARKERS = (
    "ERROR:",
    "**ERROR**",
    "CONNECTION_ERROR",
    "INVALID_REQUEST",
    "Traceback",
    "layer-slice token span exceeds context",
    "kv payload staging failed",
)

PROCESS_LINE_PATTERNS = (
    r"^\s*Retrieved\s*$",
    r"^\s*Thought\s*$",
    r"^\s*Analyzing the question\.?\s*$",
    r"^\s*Searching datasets for:",
    r"^\s*Found \d+ relevant passages",
    r"^\s*Preparing retrieved evidence",
    r"^\s*Reviewing retrieved evidence",
)

IMAGE_QUERY_PATTERNS = (
    "图片",
    "图像",
    "照片",
    "截图",
    "这张图",
    "这幅图",
    "看图",
    "识别图",
    "image",
    "photo",
    "picture",
    "screenshot",
    "vision",
)

EXTERNAL_SEARCH_PATTERNS = (
    "最新",
    "今天",
    "昨日",
    "昨天",
    "今年",
    "实时",
    "新闻",
    "股价",
    "股票",
    "行情",
    "外网",
    "联网",
    "搜索网页",
    "查网页",
    "web search",
    "latest",
    "today",
    "news",
    "stock price",
    "tavily",
)

TTS_PATTERNS = (
    "朗读",
    "读出来",
    "念出来",
    "语音",
    "音频",
    "tts",
    "text to speech",
    "read aloud",
    "voice",
    "speak",
)


def _coerce_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, dict):
        for key in ("content", "answer", "text", "output"):
            if value.get(key):
                return _coerce_text(value.get(key))
        try:
            return json.dumps(value, ensure_ascii=False)
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return "\n".join(_coerce_text(item) for item in value if item is not None)
    return value if isinstance(value, str) else str(value)


def sanitize_agent_history_text(text: Any, max_chars: int = AGENT_HISTORY_MAX_CHARS) -> str:
    text = _coerce_text(text)
    if not text:
        return ""

    text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<retrieving>.*?</retrieving>", "", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"data:image/[a-zA-Z0-9.+-]+;base64,[A-Za-z0-9+/=]+", "[image omitted]", text)

    lines: list[str] = []
    for line in text.splitlines():
        if any(marker in line for marker in AGENT_HISTORY_ERROR_MARKERS):
            continue
        if any(re.search(pattern, line, flags=re.IGNORECASE) for pattern in PROCESS_LINE_PATTERNS):
            continue
        lines.append(line)

    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if len(text) > max_chars:
        text = text[:max_chars].rstrip() + "\n[history truncated]"
    return text


def _component_obj(component: Any) -> Any:
    if isinstance(component, dict):
        return component.get("obj", component)
    return component


def _component_name(component: Any) -> str:
    obj = _component_obj(component)
    if isinstance(obj, dict):
        return str(obj.get("component_name") or "")
    return str(getattr(obj, "component_name", "") or "")


def _component_params(component: Any) -> Any:
    obj = _component_obj(component)
    if isinstance(obj, dict):
        return obj.get("params", {})
    return getattr(obj, "_param", None)


def _param_value(params: Any, key: str, default: Any = None) -> Any:
    if isinstance(params, dict):
        return params.get(key, default)
    return getattr(params, key, default)


def _iter_tool_names(params: Any) -> list[str]:
    tools = _param_value(params, "tools", []) or []
    names: list[str] = []
    for tool in tools:
        if isinstance(tool, dict):
            names.append(str(tool.get("component_name") or tool.get("name") or ""))
        else:
            names.append(str(getattr(tool, "component_name", "") or getattr(tool, "name", "") or ""))
    return names


def detect_agent_capabilities(components: dict[str, Any] | None) -> dict[str, Any]:
    components = components or {}
    names: list[str] = []
    tool_names: list[str] = []
    tts_auto_play = False

    for component in components.values():
        name = _component_name(component)
        if name:
            names.append(name)
        params = _component_params(component)
        tool_names.extend(_iter_tool_names(params))
        if name.lower() == "message" and bool(_param_value(params, "auto_play", False)):
            tts_auto_play = True

    searchable_names = [*names, *tool_names]
    lowered = [name.lower() for name in searchable_names]
    capabilities = {
        "component_names": sorted(set(name for name in names if name)),
        "tool_names": sorted(set(name for name in tool_names if name)),
        "retrieval": any("retrieval" in name for name in lowered),
        "tavily": any("tavily" in name for name in lowered),
        "external_search": any(
            token in name
            for name in lowered
            for token in ("tavily", "google", "duckduckgo", "searxng", "wikipedia", "arxiv", "pubmed", "crawler")
        ),
        "vision": any(token in name for name in lowered for token in ("vision", "image", "ocr", "vl", "vlm")),
        "llm_or_agent": any(name in {"llm", "agent", "generate"} for name in lowered),
        "tts": tts_auto_play or any(token in name for name in lowered for token in ("tts", "speech", "audio")),
    }
    return capabilities


def _file_types(files: Any) -> list[str]:
    if not isinstance(files, list):
        return []
    types = []
    for file in files:
        if not isinstance(file, dict):
            continue
        types.append(str(file.get("mime_type") or file.get("type") or ""))
    return types


def _has_image_file(files: Any) -> bool:
    return any(file_type.startswith("image/") or "image" in file_type for file_type in _file_types(files))


def _contains_any(text: str, patterns: tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(pattern.lower() in lowered for pattern in patterns)


def route_agent_intent(
    query: Any,
    components: dict[str, Any] | None = None,
    files: Any = None,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    query_text = _coerce_text(query).strip()
    if not query_text and inputs:
        query_text = _coerce_text(inputs.get("query") or inputs.get("question") or inputs.get("input")).strip()

    capabilities = detect_agent_capabilities(components)
    blocked: list[str] = []
    signals = {
        "has_image_file": _has_image_file(files),
        "mentions_image": _contains_any(query_text, IMAGE_QUERY_PATTERNS),
        "mentions_external_search": _contains_any(query_text, EXTERNAL_SEARCH_PATTERNS),
        "mentions_tts": _contains_any(query_text, TTS_PATTERNS),
        "contains_error_marker": any(marker in query_text for marker in AGENT_HISTORY_ERROR_MARKERS),
    }

    route = "ordinary_text"
    score = 0.35
    reason = "default_text"

    if not query_text:
        route, score, reason = "unknown", 0.0, "empty_query"
    elif signals["contains_error_marker"]:
        route, score, reason = "error_noise", 1.0, "error_marker"
    elif signals["has_image_file"] or signals["mentions_image"]:
        route, score, reason = "needs_visual", 0.9, "image_signal"
        if not signals["has_image_file"]:
            blocked.append("missing_image_file")
        if not (capabilities["vision"] or capabilities["llm_or_agent"]):
            blocked.append("vision_component_not_detected")
    elif signals["mentions_external_search"]:
        route, score = ("needs_tavily", 0.92) if capabilities["tavily"] else ("needs_external_search", 0.86)
        reason = "external_search_signal"
        if not capabilities["external_search"]:
            blocked.append("external_search_component_not_detected")
    elif signals["mentions_tts"]:
        route, score, reason = "needs_tts", 0.82, "tts_signal"
        if not capabilities["tts"]:
            blocked.append("tts_component_not_detected")

    allowed = [
        key
        for key in ("retrieval", "tavily", "external_search", "vision", "llm_or_agent", "tts")
        if capabilities.get(key)
    ]
    return {
        "route": route,
        "score": score,
        "reason": reason,
        "allowed_capabilities": sorted(set(allowed)),
        "blocked_capabilities": sorted(set(blocked)),
        "signals": signals,
        "file_types": _file_types(files),
    }
