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
import json
from datetime import datetime
from typing import Any

from api.db.db_models import DB, SystemSettings
from common.time_utils import current_timestamp, datetime_format


PANYTHON_TTS_SETTINGS_NAME = "panython.tts.engine"

DEFAULT_TTS_ENGINE_SETTINGS = {
    "tts_enabled": False,
    "engine": "CosyVoice3",
    "supports_speed": True,
    "supports_emotion": True,
    "supports_dialect": True,
    "supports_voice_profile": True,
    "supports_sync_caption": True,
    "default_speed": 1.0,
    "default_emotion": "professional",
    "default_dialect": "mandarin",
    "default_gender": "female",
    "default_voice_profile": "female_mandarin_01",
    "buffer_ms": 1200,
    "segment_max_chars_zh": 45,
    "segment_max_words_en": 18,
}

DIALECT_INSTRUCTIONS = {
    "mandarin": "Mandarin Chinese",
    "cantonese": "Cantonese Chinese",
    "sichuan": "Sichuan-accented Chinese",
    "shanghai": "Shanghainese-accented Chinese",
    "dongbei": "Northeastern Mandarin",
    "minnan": "Minnan-accented Chinese",
    "tianjin": "Tianjin-accented Chinese",
    "shandong": "Shandong-accented Chinese",
}

EMOTION_INSTRUCTIONS = {
    "professional": "professional, clear, and natural",
    "calm": "calm and steady",
    "friendly": "friendly and warm",
    "formal": "formal and precise",
    "lively": "lively and expressive",
    "serious": "serious and composed",
}

GENDER_INSTRUCTIONS = {
    "female": "female",
    "male": "male",
}


def _to_bool(value: Any, default: bool = False) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.lower() in {"1", "true", "yes", "on"}
    if value is None:
        return default
    return bool(value)


def _to_float(value: Any, default: float, minimum: float, maximum: float) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _to_int(value: Any, default: int, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = default
    return min(max(number, minimum), maximum)


def _normalize_choice(value: Any, allowed: set[str], default: str) -> str:
    text = str(value or "").strip()
    return text if text in allowed else default


def normalize_tts_engine_settings(raw: dict | None) -> dict:
    raw = raw or {}
    settings = dict(DEFAULT_TTS_ENGINE_SETTINGS)
    settings.update({key: raw.get(key, value) for key, value in settings.items()})

    settings["tts_enabled"] = _to_bool(settings.get("tts_enabled"))
    settings["supports_speed"] = _to_bool(settings.get("supports_speed"), True)
    settings["supports_emotion"] = _to_bool(settings.get("supports_emotion"), True)
    settings["supports_dialect"] = _to_bool(settings.get("supports_dialect"), True)
    settings["supports_voice_profile"] = _to_bool(settings.get("supports_voice_profile"), True)
    settings["supports_sync_caption"] = _to_bool(settings.get("supports_sync_caption"), True)
    settings["engine"] = str(settings.get("engine") or "CosyVoice3").strip()[:64]
    settings["default_speed"] = _to_float(settings.get("default_speed"), 1.0, 0.5, 2.0)
    settings["buffer_ms"] = _to_int(settings.get("buffer_ms"), 1200, 300, 5000)
    settings["segment_max_chars_zh"] = _to_int(settings.get("segment_max_chars_zh"), 45, 10, 120)
    settings["segment_max_words_en"] = _to_int(settings.get("segment_max_words_en"), 18, 5, 60)
    settings["default_emotion"] = _normalize_choice(
        settings.get("default_emotion"),
        {"professional", "calm", "friendly", "formal", "lively", "serious"},
        "professional",
    )
    settings["default_dialect"] = _normalize_choice(
        settings.get("default_dialect"),
        {"mandarin", "cantonese", "sichuan", "shanghai", "dongbei", "minnan", "tianjin", "shandong"},
        "mandarin",
    )
    settings["default_gender"] = _normalize_choice(settings.get("default_gender"), {"female", "male"}, "female")
    settings["default_voice_profile"] = str(settings.get("default_voice_profile") or "female_mandarin_01").strip()[:96]
    return settings


def normalize_tts_runtime_config(raw: dict | None, engine_settings: dict | None = None) -> dict:
    engine_settings = normalize_tts_engine_settings(engine_settings)
    raw = raw or {}
    speed_default = engine_settings.get("default_speed", DEFAULT_TTS_ENGINE_SETTINGS["default_speed"])
    emotion_default = engine_settings.get("default_emotion", DEFAULT_TTS_ENGINE_SETTINGS["default_emotion"])
    dialect_default = engine_settings.get("default_dialect", DEFAULT_TTS_ENGINE_SETTINGS["default_dialect"])
    gender_default = engine_settings.get("default_gender", DEFAULT_TTS_ENGINE_SETTINGS["default_gender"])
    voice_default = engine_settings.get("default_voice_profile", DEFAULT_TTS_ENGINE_SETTINGS["default_voice_profile"])
    return {
        "speed": _to_float(raw.get("speed"), speed_default, 0.5, 2.0),
        "emotion": _normalize_choice(raw.get("emotion"), set(EMOTION_INSTRUCTIONS), emotion_default),
        "dialect": _normalize_choice(raw.get("dialect"), set(DIALECT_INSTRUCTIONS), dialect_default),
        "gender": _normalize_choice(raw.get("gender"), set(GENDER_INSTRUCTIONS), gender_default),
        "voice_profile": str(raw.get("voice_profile") or voice_default).strip()[:96],
        "sync_caption": _to_bool(raw.get("sync_caption"), bool(engine_settings.get("supports_sync_caption"))),
    }


def build_tts_instructions(config: dict | None, text: str = "") -> str:
    config = normalize_tts_runtime_config(config)
    dialect = DIALECT_INSTRUCTIONS.get(config["dialect"], DIALECT_INSTRUCTIONS["mandarin"])
    emotion = EMOTION_INSTRUCTIONS.get(config["emotion"], EMOTION_INSTRUCTIONS["professional"])
    gender = GENDER_INSTRUCTIONS.get(config["gender"], GENDER_INSTRUCTIONS["female"])
    has_chinese = any("\u4e00" <= char <= "\u9fff" for char in str(text or ""))
    language_part = f"Read Chinese text in {dialect}" if has_chinese else "Read the text naturally"
    return (
        "You are a helpful assistant. "
        f"{language_part}. Use a {gender} voice with a {emotion} delivery. "
        "Keep pronunciation accurate and pacing natural.<|endofprompt|>"
    )


def build_tts_kwargs(config: dict | None, text: str = "", engine_settings: dict | None = None) -> dict:
    engine_settings = normalize_tts_engine_settings(engine_settings)
    config = normalize_tts_runtime_config(config, engine_settings)
    kwargs = {}
    if engine_settings.get("supports_speed"):
        kwargs["speed"] = config["speed"]
    if engine_settings.get("supports_emotion") or engine_settings.get("supports_dialect"):
        kwargs["instructions"] = build_tts_instructions(config, text)
    if engine_settings.get("supports_voice_profile"):
        kwargs["voice"] = config["voice_profile"]
    return kwargs


class PanythonTTSSettingsService:
    @classmethod
    @DB.connection_context()
    def get_settings(cls) -> dict:
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_TTS_SETTINGS_NAME)
        if not record:
            return dict(DEFAULT_TTS_ENGINE_SETTINGS)
        try:
            raw = json.loads(record.value)
        except Exception:
            raw = {}
        return normalize_tts_engine_settings(raw)

    @classmethod
    @DB.connection_context()
    def save_settings(cls, raw_settings: dict) -> dict:
        settings = normalize_tts_engine_settings(raw_settings)
        now = datetime.now()
        payload = {
            "source": "panython",
            "data_type": "json",
            "value": json.dumps(settings, ensure_ascii=False),
            "update_time": current_timestamp(),
            "update_date": datetime_format(now),
        }
        record = SystemSettings.get_or_none(SystemSettings.name == PANYTHON_TTS_SETTINGS_NAME)
        if record:
            SystemSettings.update(payload).where(SystemSettings.name == PANYTHON_TTS_SETTINGS_NAME).execute()
        else:
            SystemSettings.create(name=PANYTHON_TTS_SETTINGS_NAME, **payload)
        return settings
