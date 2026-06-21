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

import os
import re
from typing import Any

from common.config_utils import get_base_config


FEATURE_DEFAULTS: dict[str, bool] = {
    "memo_spacetime": True,
    "memo_profile": True,
    "memory_context": True,
    "evidence_audit": True,
    "structured_extraction": True,
    "semantic_router": True,
    "topic_embedding_cache": True,
}

FEATURE_ALIASES: dict[str, str] = {
    "memoSpacetime": "memo_spacetime",
    "memoProfile": "memo_profile",
    "memoryContext": "memory_context",
    "evidenceAudit": "evidence_audit",
    "structuredExtraction": "structured_extraction",
    "semanticRouter": "semantic_router",
    "topicEmbeddingCache": "topic_embedding_cache",
}


def _normalize_feature_name(name: str) -> str:
    if name in FEATURE_ALIASES:
        return FEATURE_ALIASES[name]
    normalized = re.sub(r"(?<!^)([A-Z])", r"_\1", str(name or "")).lower()
    return normalized.replace("-", "_").strip("_")


def _to_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _configured_features() -> dict[str, Any]:
    config = get_base_config("panython_features", None)
    if config is None:
        config = get_base_config("feature_flags", {})
    return config if isinstance(config, dict) else {}


def feature_enabled(name: str, default: bool | None = None) -> bool:
    key = _normalize_feature_name(name)
    fallback = FEATURE_DEFAULTS.get(key, True if default is None else default)
    config = _configured_features()

    configured_value = config.get(key)
    if configured_value is None:
        configured_value = config.get(name)
    if configured_value is None:
        configured_value = config.get(FEATURE_ALIASES.get(name, ""))

    env_key = f"RAGFLOW_FEATURE_{key.upper()}"
    env_value = os.getenv(env_key)
    if env_value is not None:
        return _to_bool(env_value, fallback)
    return _to_bool(configured_value, fallback)


def get_feature_flags() -> dict[str, bool]:
    flags = {
        key: feature_enabled(key, default)
        for key, default in FEATURE_DEFAULTS.items()
    }
    flags.update(
        {
            camel_key: flags[snake_key]
            for camel_key, snake_key in FEATURE_ALIASES.items()
        }
    )
    return flags
