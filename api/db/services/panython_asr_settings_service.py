#
#  Copyright 2026 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
import json
from datetime import datetime
from typing import Any

from api.db.db_models import DB, SystemSettings
from common.time_utils import current_timestamp, datetime_format


PANYTHON_ASR_SETTINGS_NAME = "panython.asr.settings"

DEFAULT_ASR_SETTINGS: dict[str, Any] = {
    # Routing
    "mode": "dual",                   # "single" | "dual"
    "single_model": "qwen3",          # "qwen3" | "sensevoice"  (used when mode=single)
    "dual_merge": "qwen3_primary",    # "qwen3_primary" | "sensevoice_primary" | "longest"
    # Language
    "language": "auto",               # "auto" | "zh" | "yue" | "en"
    # Short audio heuristic: if audio duration < threshold → prefer SenseVoice (low latency)
    "short_audio_threshold_ms": 3000,
    # Post-processing (FunASR — exposed now, activated when funasr is installed)
    "punctuation": False,
    "vad": False,
}

_ALLOWED_MODES = {"single", "dual"}
_ALLOWED_SINGLE_MODELS = {"qwen3", "sensevoice"}
_ALLOWED_DUAL_MERGES = {"qwen3_primary", "sensevoice_primary", "longest"}
_ALLOWED_LANGUAGES = {"auto", "zh", "yue", "en"}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    return default


def _clamp_int(value: Any, default: int, lo: int, hi: int) -> int:
    try:
        return min(max(int(value), lo), hi)
    except (TypeError, ValueError):
        return default


def _choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def normalize_asr_settings(raw: dict | None) -> dict:
    raw = raw or {}
    return {
        "mode": _choice(raw.get("mode"), _ALLOWED_MODES, DEFAULT_ASR_SETTINGS["mode"]),
        "single_model": _choice(
            raw.get("single_model"), _ALLOWED_SINGLE_MODELS, DEFAULT_ASR_SETTINGS["single_model"]
        ),
        "dual_merge": _choice(
            raw.get("dual_merge"), _ALLOWED_DUAL_MERGES, DEFAULT_ASR_SETTINGS["dual_merge"]
        ),
        "language": _choice(raw.get("language"), _ALLOWED_LANGUAGES, DEFAULT_ASR_SETTINGS["language"]),
        "short_audio_threshold_ms": _clamp_int(
            raw.get("short_audio_threshold_ms"), DEFAULT_ASR_SETTINGS["short_audio_threshold_ms"], 500, 10000
        ),
        "punctuation": _to_bool(raw.get("punctuation"), DEFAULT_ASR_SETTINGS["punctuation"]),
        "vad": _to_bool(raw.get("vad"), DEFAULT_ASR_SETTINGS["vad"]),
    }


class PanythonASRSettingsService:
    @classmethod
    @DB.connection_context()
    def get_settings(cls) -> dict:
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_ASR_SETTINGS_NAME)
        if not record:
            return dict(DEFAULT_ASR_SETTINGS)
        try:
            raw = json.loads(record.value)
        except Exception:
            raw = {}
        return normalize_asr_settings(raw)

    @classmethod
    @DB.connection_context()
    def save_settings(cls, raw_settings: dict) -> dict:
        settings = normalize_asr_settings(raw_settings)
        now = datetime.now()
        payload = {
            "source": "panython",
            "data_type": "json",
            "value": json.dumps(settings, ensure_ascii=False),
            "update_time": current_timestamp(),
            "update_date": datetime_format(now),
        }
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_ASR_SETTINGS_NAME)
        if record:
            SystemSettings.update(payload).where(SystemSettings.name == PANYTHON_ASR_SETTINGS_NAME).execute()
        else:
            SystemSettings.create(name=PANYTHON_ASR_SETTINGS_NAME, **payload)
        return settings
