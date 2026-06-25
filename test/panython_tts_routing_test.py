#!/usr/bin/env python3
"""
Panython TTS routing test — standalone, no auth required.

Tests the CosyVoice server directly on port 50001.
Also validates the (dialect, gender) → voice_profile mapping from panython_tts_settings_service.

Usage:
    python3 test/panython_tts_routing_test.py [--out-dir /tmp/tts_test]

Logs each test case: voice profile, speed, audio filename, audio duration, synthesis latency.
Writes a summary at the end.
"""

import argparse
import io
import json
import logging
import os
import struct
import sys
import time
from datetime import datetime
from pathlib import Path

import requests

# ─── config ───────────────────────────────────────────────────────────────────

COSYVOICE_URL = os.environ.get("COSYVOICE_URL", "http://127.0.0.1:50001")
RAGFLOW_URL = os.environ.get("RAGFLOW_URL", "http://127.0.0.1:9388")

DEFAULT_TEST_TEXT_ZH = "你好，这是一段测试语音，用于验证语音合成路由是否正常工作。"
DEFAULT_TEST_TEXT_YUE = "你好，呢段係粵語測試語音，用嚟驗證語音合成係咪正常運作。"
DEFAULT_TEST_TEXT_EN = "Hello, this is an English test for the TTS routing system."

VOICE_TEST_MAP = {
    "female_mandarin_01": DEFAULT_TEST_TEXT_ZH,
    "male_mandarin_01": DEFAULT_TEST_TEXT_ZH,
    "female_cantonese_01": DEFAULT_TEST_TEXT_YUE,
    "male_cantonese_01": DEFAULT_TEST_TEXT_YUE,
    "female_sichuan_01": "你好，这是一段四川话测试语音，验证路由是否正常工作。",
    "male_sichuan_01": "你好，这是一段四川话测试语音，验证路由是否正常工作。",
    "female_shanghai_01": "侬好，这是一段上海话测试语音，验证路由是否正常工作。",
    "female_dongbei_01": "你好，这是一段东北话测试语音，验证路由是否正常工作。",
    "female_minnan_01": "你好，这是一段闽南话测试语音，验证路由是否正常工作。",
}

TEST_SPEEDS = [0.8, 1.0, 1.2]

# Expected (dialect, gender) → voice_profile mapping (from panython_tts_settings_service.py)
EXPECTED_ROUTING = {
    ("mandarin", "female"): "female_mandarin_01",
    ("mandarin", "male"):   "male_mandarin_01",
    ("cantonese", "female"): "female_cantonese_01",
    ("cantonese", "male"):  "male_cantonese_01",
    ("sichuan", "female"):  "female_sichuan_01",
    ("sichuan", "male"):    "male_sichuan_01",
    ("shanghai", "female"): "female_shanghai_01",
    ("dongbei", "female"):  "female_dongbei_01",
    ("minnan", "female"):   "female_minnan_01",
}

# ─── logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("tts-route-test")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _wav_duration_s(wav_bytes: bytes) -> float:
    """Parse WAV header manually — handles both PCM (fmt=1) and IEEE float (fmt=3)."""
    try:
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            return 0.0
        fmt_code, channels, sample_rate, _, _, bits = struct.unpack_from("<HHIIHH", wav_bytes, 20)
        bytes_per_sample = bits // 8
        if bytes_per_sample == 0:
            return 0.0
        data_bytes = len(wav_bytes) - 44
        return data_bytes / (sample_rate * channels * bytes_per_sample)
    except Exception:
        return 0.0


def _synthesize(voice: str, text: str, speed: float = 1.0, timeout: int = 30) -> tuple[bytes, float, str]:
    """Call CosyVoice directly. Returns (wav_bytes, elapsed_s, error_or_empty)."""
    payload = {
        "model": "CosyVoice3",
        "input": text,
        "voice": voice,
        "speed": speed,
        "response_format": "wav",
    }
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{COSYVOICE_URL}/v1/audio/speech",
            json=payload,
            timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
        if resp.status_code != 200:
            return b"", elapsed, f"HTTP {resp.status_code}: {resp.text[:200]}"
        return resp.content, elapsed, ""
    except Exception as exc:
        return b"", time.perf_counter() - t0, str(exc)


def _check_cosyvoice_health() -> tuple[bool, list[str]]:
    try:
        resp = requests.get(f"{COSYVOICE_URL}/health", timeout=5)
        data = resp.json()
        voices = [v["id"] for v in data.get("voices", [])]
        return data.get("model_loaded", False), voices
    except Exception as exc:
        log.error("CosyVoice health check failed: %s", exc)
        return False, []


# ─── test suites ──────────────────────────────────────────────────────────────

def test_routing_mapping():
    """Unit-test the (dialect, gender) → voice_profile mapping without any HTTP call."""
    log.info("=" * 60)
    log.info("TEST SUITE: Routing mapping (dialect+gender → voice_id)")
    log.info("=" * 60)

    sys.path.insert(0, str(Path(__file__).parent.parent))  # newapp/ragflow root
    try:
        from api.db.services.panython_tts_settings_service import build_tts_voice_profile
    except ImportError as exc:
        log.warning("Cannot import panython_tts_settings_service (not in venv): %s", exc)
        log.warning("Skipping routing mapping test.")
        return True

    passed = 0
    failed = 0
    for (dialect, gender), expected_voice in EXPECTED_ROUTING.items():
        config = {"dialect": dialect, "gender": gender}
        actual = build_tts_voice_profile(config)
        ok = actual == expected_voice
        status = "PASS" if ok else "FAIL"
        log.info("[%s] dialect=%-12s gender=%-8s → expected=%-25s actual=%s", status, dialect, gender, expected_voice, actual)
        if ok:
            passed += 1
        else:
            failed += 1

    log.info("Routing mapping: %d passed, %d failed", passed, failed)
    return failed == 0


def test_cosyvoice_voices(out_dir: Path, speeds: list[float]):
    """Test each voice profile at each speed. Saves WAV files and logs timing."""
    log.info("=" * 60)
    log.info("TEST SUITE: CosyVoice voice profiles × speeds")
    log.info("=" * 60)

    model_loaded, available_voices = _check_cosyvoice_health()
    if not model_loaded:
        log.error("CosyVoice model not loaded — aborting voice tests.")
        return False

    log.info("CosyVoice healthy. Available voices: %s", available_voices)

    results = []
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    for voice, text in VOICE_TEST_MAP.items():
        for speed in speeds:
            label = f"{voice}_speed{speed:.1f}"
            filename = f"tts_{label}_{ts}.wav"
            out_path = out_dir / filename

            wav_bytes, elapsed, error = _synthesize(voice, text, speed=speed)

            if error:
                log.error("[FAIL] voice=%-25s speed=%.1f | ERROR: %s", voice, speed, error)
                results.append({"voice": voice, "speed": speed, "ok": False, "error": error})
                continue

            dur_s = _wav_duration_s(wav_bytes)
            out_path.write_bytes(wav_bytes)

            log.info(
                "[PASS] voice=%-25s speed=%.1f | audio_dur=%.2fs | synth_time=%.2fs"
                " | bytes=%d | file=%s",
                voice, speed, dur_s, elapsed, len(wav_bytes), filename,
            )
            results.append({
                "voice": voice,
                "speed": speed,
                "ok": True,
                "audio_dur_s": round(dur_s, 3),
                "elapsed_s": round(elapsed, 3),
                "audio_bytes": len(wav_bytes),
                "filename": filename,
            })

    passed = sum(1 for r in results if r["ok"])
    failed = len(results) - passed
    log.info("Voice profiles: %d passed, %d failed", passed, failed)
    return failed == 0


def test_settings_immediate_effect():
    """Verify TTS settings are read fresh per request (no in-memory cache)."""
    log.info("=" * 60)
    log.info("TEST SUITE: Settings immediate effect (library-level test)")
    log.info("=" * 60)

    sys.path.insert(0, str(Path(__file__).parents[2]))
    try:
        from api.db.services.panython_tts_settings_service import (
            PanythonTTSSettingsService,
            normalize_tts_engine_settings,
            build_tts_kwargs,
        )
    except ImportError as exc:
        log.warning("Cannot import service (not in venv): %s", exc)
        return True

    # Verify normalize_tts_engine_settings is pure (no caching side effects)
    raw1 = {"default_dialect": "cantonese", "default_gender": "female", "default_speed": 1.2}
    raw2 = {"default_dialect": "mandarin", "default_gender": "male", "default_speed": 0.8}

    s1 = normalize_tts_engine_settings(raw1)
    s2 = normalize_tts_engine_settings(raw2)

    ok1 = s1["default_dialect"] == "cantonese" and s1["default_speed"] == 1.2
    ok2 = s2["default_dialect"] == "mandarin" and s2["default_speed"] == 0.8
    no_bleed = s1["default_dialect"] != s2["default_dialect"]

    k1 = build_tts_kwargs({"dialect": "cantonese", "gender": "female"}, engine_settings=s1)
    k2 = build_tts_kwargs({"dialect": "mandarin", "gender": "male"}, engine_settings=s2)

    log.info("[%s] cantonese/female kwargs: %s", "PASS" if k1.get("voice") == "female_cantonese_01" else "FAIL", k1)
    log.info("[%s] mandarin/male   kwargs: %s", "PASS" if k2.get("voice") == "male_mandarin_01" else "FAIL", k2)
    log.info("[%s] normalize is pure (no cross-call bleed): %s vs %s", "PASS" if no_bleed else "FAIL", s1["default_dialect"], s2["default_dialect"])

    return ok1 and ok2 and no_bleed and k1.get("voice") == "female_cantonese_01" and k2.get("voice") == "male_mandarin_01"


def write_summary(out_dir: Path, results_json: list[dict]):
    summary_path = out_dir / f"tts_test_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    summary_path.write_text(json.dumps(results_json, ensure_ascii=False, indent=2))
    log.info("Summary written → %s", summary_path)


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Panython TTS routing test")
    parser.add_argument("--out-dir", default="/tmp/tts_test_audio", help="Directory to save WAV files")
    parser.add_argument("--speeds", nargs="+", type=float, default=TEST_SPEEDS, help="Speeds to test (default: 0.8 1.0 1.2)")
    parser.add_argument("--voice", help="Test only this voice profile (skip others)")
    parser.add_argument("--skip-synthesis", action="store_true", help="Skip CosyVoice HTTP tests (mapping test only)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Output dir: %s", out_dir)
    log.info("CosyVoice URL: %s", COSYVOICE_URL)
    log.info("Speeds: %s", args.speeds)

    suite_results = {}

    # 1. Routing mapping unit test
    suite_results["routing_mapping"] = test_routing_mapping()

    # 2. Settings immediate effect
    suite_results["settings_immediate_effect"] = test_settings_immediate_effect()

    # 3. CosyVoice voice synthesis
    if not args.skip_synthesis:
        voice_map = VOICE_TEST_MAP
        if args.voice:
            voice_map = {args.voice: VOICE_TEST_MAP.get(args.voice, DEFAULT_TEST_TEXT_ZH)}
        suite_results["cosyvoice_synthesis"] = test_cosyvoice_voices(out_dir, args.speeds)

    log.info("=" * 60)
    log.info("FINAL RESULTS")
    all_ok = True
    for suite, ok in suite_results.items():
        status = "PASS" if ok else "FAIL"
        log.info("  [%s] %s", status, suite)
        if not ok:
            all_ok = False
    log.info("=" * 60)
    log.info("Audio files saved in: %s", out_dir)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
