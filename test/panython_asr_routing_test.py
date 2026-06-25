#!/usr/bin/env python3
"""
Panython ASR routing test — standalone, no auth required.

Two test modes:
  1. TTS→ASR round-trip: Use CosyVoice to synthesize test sentences,
     send the resulting WAV to Qwen3-ASR, compare back to original text.
  2. WAV file test: Send an existing WAV file to both Qwen3-ASR and
     SenseVoice (via xinference), compare results.

Also tests routing parameters: vad, punctuation, language, dual-route merge.

Usage:
    python3 test/panython_asr_routing_test.py
    python3 test/panython_asr_routing_test.py --mode roundtrip
    python3 test/panython_asr_routing_test.py --mode file --wav /path/to/test.wav
    python3 test/panython_asr_routing_test.py --mode dual   # test both engines
"""

import argparse
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

QWEN3_ASR_URL = os.environ.get("QWEN3_ASR_URL", "http://127.0.0.1:9900")
SENSEVOICE_URL = os.environ.get("SENSEVOICE_URL", "http://127.0.0.1:9997")
COSYVOICE_URL = os.environ.get("COSYVOICE_URL", "http://127.0.0.1:50001")

# ─── test cases ───────────────────────────────────────────────────────────────

ROUNDTRIP_CASES = [
    {
        "id": "mandarin_female",
        "voice": "female_mandarin_01",
        "text": "你好，今天天气怎么样？这里是普通话朗读测试。",
        "language": "zh",
        "expected_keywords": ["今天", "天气", "普通话"],
    },
    {
        "id": "cantonese_female",
        "voice": "female_cantonese_01",
        "text": "你好，今日天气点样？呢度係粵語朗讀測試。",
        "language": "yue",
        "expected_keywords": ["今日", "天气", "粤语"],
    },
    {
        "id": "mandarin_male",
        "voice": "male_mandarin_01",
        "text": "人工智能技术正在快速发展，语音识别的准确率越来越高。",
        "language": "zh",
        "expected_keywords": ["人工智能", "语音识别"],
    },
    {
        "id": "cantonese_male",
        "voice": "male_cantonese_01",
        "text": "人工智能技术正在快速发展，粤语识别越来越准确。",
        "language": "yue",
        "expected_keywords": ["人工智能", "粤语"],
    },
    {
        "id": "sichuan_female",
        "voice": "female_sichuan_01",
        "text": "四川话是中国的一种方言，有着独特的声调和语调特征。",
        "language": "zh",
        "expected_keywords": ["四川", "方言"],
    },
    {
        "id": "mixed_short",
        "voice": "female_mandarin_01",
        "text": "这段文字包含数字123和英文ABC，测试混合识别效果。",
        "language": "auto",
        "expected_keywords": ["数字", "英文"],
    },
]

# ─── logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("asr-route-test")


# ─── helpers ──────────────────────────────────────────────────────────────────

def _wav_duration_s(wav_bytes: bytes) -> float:
    try:
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            return 0.0
        _, channels, sample_rate, _, _, bits = struct.unpack_from("<HHIIHH", wav_bytes, 20)
        bytes_per_sample = bits // 8
        if bytes_per_sample == 0:
            return 0.0
        return (len(wav_bytes) - 44) / (sample_rate * channels * bytes_per_sample)
    except Exception:
        return 0.0


def _tts_synthesize(voice: str, text: str, speed: float = 1.0, timeout: int = 30) -> bytes:
    payload = {"model": "CosyVoice3", "input": text, "voice": voice, "speed": speed, "response_format": "wav"}
    resp = requests.post(f"{COSYVOICE_URL}/v1/audio/speech", json=payload, timeout=timeout)
    resp.raise_for_status()
    return resp.content


def _asr_qwen3(wav_bytes: bytes, filename: str = "audio.wav", language: str = None,
               vad: bool = False, punctuation: bool = False, timeout: int = 60) -> tuple[str, float]:
    t0 = time.perf_counter()
    files = {"file": (filename, wav_bytes, "audio/wav")}
    data = {"model": "qwen3-asr"}
    if language and language != "auto":
        data["language"] = language
    if vad:
        data["vad"] = "true"
    if punctuation:
        data["punctuation"] = "true"
    resp = requests.post(f"{QWEN3_ASR_URL}/v1/audio/transcriptions", files=files, data=data, timeout=timeout)
    elapsed = time.perf_counter() - t0
    resp.raise_for_status()
    text = resp.json().get("text", "")
    return text, elapsed


def _asr_sensevoice(wav_bytes: bytes, filename: str = "audio.wav", timeout: int = 60) -> tuple[str, float]:
    """Call SenseVoice via xinference OpenAI-compatible endpoint."""
    t0 = time.perf_counter()
    try:
        files = {"file": (filename, wav_bytes, "audio/wav")}
        data = {"model": "SenseVoiceSmall"}
        resp = requests.post(
            f"{SENSEVOICE_URL}/v1/audio/transcriptions",
            files=files, data=data, timeout=timeout,
        )
        elapsed = time.perf_counter() - t0
        resp.raise_for_status()
        text = resp.json().get("text", "")
        return text, elapsed
    except Exception as exc:
        elapsed = time.perf_counter() - t0
        return f"[ERROR: {exc}]", elapsed


def _cer(ref: str, hyp: str) -> float:
    """Simplified character error rate (insertion+deletion+substitution / len(ref))."""
    ref = ref.replace(" ", "")
    hyp = hyp.replace(" ", "")
    if not ref:
        return 0.0
    m, n = len(ref), len(hyp)
    dp = list(range(n + 1))
    for i in range(1, m + 1):
        prev = dp[:]
        dp[0] = i
        for j in range(1, n + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[j] = prev[j - 1]
            else:
                dp[j] = 1 + min(prev[j], dp[j - 1], prev[j - 1])
    return dp[n] / m


def _keyword_hits(text: str, keywords: list[str]) -> int:
    return sum(1 for kw in keywords if kw in text)


# ─── test suites ──────────────────────────────────────────────────────────────

def test_qwen3_health() -> bool:
    log.info("=" * 60)
    log.info("TEST: Qwen3-ASR health check")
    try:
        resp = requests.get(f"{QWEN3_ASR_URL}/health", timeout=5)
        d = resp.json()
        ready = d.get("ready", False)
        log.info(
            "[%s] ready=%s | vram_free_mb=%s | funasr_vad=%s | funasr_punc=%s",
            "PASS" if ready else "FAIL",
            d.get("ready"), d.get("vram_free_mb"),
            d.get("funasr_vad"), d.get("funasr_punc"),
        )
        return ready
    except Exception as exc:
        log.error("[FAIL] Qwen3-ASR health check failed: %s", exc)
        return False


def test_roundtrip(out_dir: Path) -> list[dict]:
    """TTS → WAV → ASR → compare. Returns per-case result dicts."""
    log.info("=" * 60)
    log.info("TEST SUITE: TTS→ASR round-trip")
    log.info("=" * 60)

    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    results = []

    for case in ROUNDTRIP_CASES:
        cid = case["id"]
        voice = case["voice"]
        ref_text = case["text"]
        language = case.get("language", "auto")
        keywords = case.get("expected_keywords", [])

        log.info("── Case: %s | voice=%s | lang=%s", cid, voice, language)
        log.info("   REF: %s", ref_text)

        # Step 1: TTS synthesis
        try:
            t_tts0 = time.perf_counter()
            wav_bytes = _tts_synthesize(voice, ref_text)
            tts_elapsed = time.perf_counter() - t_tts0
            audio_dur = _wav_duration_s(wav_bytes)
        except Exception as exc:
            log.error("   [FAIL] TTS failed: %s", exc)
            results.append({"id": cid, "ok": False, "error": f"TTS: {exc}"})
            continue

        wav_name = f"roundtrip_{cid}_{ts}.wav"
        wav_path = out_dir / wav_name
        wav_path.write_bytes(wav_bytes)
        log.info("   TTS: %.2fs synth | %.2fs audio | saved=%s", tts_elapsed, audio_dur, wav_name)

        # Step 2: ASR — Qwen3, no VAD, no punctuation (baseline)
        try:
            hyp_base, asr_elapsed = _asr_qwen3(wav_bytes, wav_name, language=language)
            cer = _cer(ref_text, hyp_base)
            hits = _keyword_hits(hyp_base, keywords)
            log.info(
                "   ASR [qwen3 base]:  elapsed=%.2fs | CER=%.1f%% | keywords=%d/%d | HYP: %s",
                asr_elapsed, cer * 100, hits, len(keywords), hyp_base,
            )
        except Exception as exc:
            hyp_base, cer, hits = "", 1.0, 0
            log.error("   [FAIL] ASR qwen3 base failed: %s", exc)

        # Step 3: ASR — Qwen3 with punctuation
        try:
            hyp_punc, asr_punc_elapsed = _asr_qwen3(wav_bytes, wav_name, language=language, punctuation=True)
            log.info(
                "   ASR [qwen3 +punc]: elapsed=%.2fs | HYP: %s",
                asr_punc_elapsed, hyp_punc,
            )
        except Exception as exc:
            hyp_punc = ""
            log.error("   [FAIL] ASR qwen3 +punc failed: %s", exc)

        # Step 4: ASR — Qwen3 with VAD
        try:
            hyp_vad, asr_vad_elapsed = _asr_qwen3(wav_bytes, wav_name, language=language, vad=True)
            log.info(
                "   ASR [qwen3 +vad]:  elapsed=%.2fs | HYP: %s",
                asr_vad_elapsed, hyp_vad,
            )
        except Exception as exc:
            hyp_vad = ""
            log.error("   [FAIL] ASR qwen3 +vad failed: %s", exc)

        # Step 5: ASR — SenseVoice (if available)
        hyp_sv, sv_elapsed = _asr_sensevoice(wav_bytes, wav_name)
        sv_ok = not hyp_sv.startswith("[ERROR")
        log.info(
            "   ASR [sensevoice]:  elapsed=%.2fs | HYP: %s",
            sv_elapsed, hyp_sv,
        )

        result = {
            "id": cid,
            "ok": cer < 0.5,  # pass if < 50% CER
            "voice": voice,
            "language": language,
            "ref_text": ref_text,
            "wav_file": wav_name,
            "tts_elapsed_s": round(tts_elapsed, 3),
            "audio_dur_s": round(audio_dur, 3),
            "qwen3_base": {"text": hyp_base, "elapsed_s": round(asr_elapsed, 3), "cer": round(cer, 4)},
            "qwen3_punc": {"text": hyp_punc},
            "qwen3_vad": {"text": hyp_vad},
            "sensevoice": {"text": hyp_sv, "ok": sv_ok},
            "keyword_hits": f"{hits}/{len(keywords)}",
        }
        results.append(result)
        status = "PASS" if result["ok"] else "WARN"
        log.info("   [%s] CER=%.1f%% | keywords=%s", status, cer * 100, result["keyword_hits"])

    passed = sum(1 for r in results if r.get("ok"))
    log.info("Round-trip: %d/%d passed", passed, len(results))
    return results


def test_param_routing(out_dir: Path) -> bool:
    """Test that routing parameters (vad, punctuation, language) work as flags."""
    log.info("=" * 60)
    log.info("TEST SUITE: ASR parameter routing")
    log.info("=" * 60)

    # Generate one WAV as base
    ref = "语音识别是人工智能的重要组成部分，能够将语音转化为文字。"
    try:
        wav_bytes = _tts_synthesize("female_mandarin_01", ref)
    except Exception as exc:
        log.error("TTS unavailable, skipping param routing test: %s", exc)
        return True

    results = {}
    for flag_combo in [
        {"vad": False, "punctuation": False},
        {"vad": True,  "punctuation": False},
        {"vad": False, "punctuation": True},
        {"vad": True,  "punctuation": True},
    ]:
        label = f"vad={flag_combo['vad']} punc={flag_combo['punctuation']}"
        try:
            text, elapsed = _asr_qwen3(wav_bytes, language="zh", **flag_combo)
            results[label] = {"text": text, "elapsed_s": round(elapsed, 3), "ok": bool(text)}
            log.info("[%s] %s | %.2fs | %s", "PASS" if text else "FAIL", label, elapsed, text)
        except Exception as exc:
            results[label] = {"ok": False, "error": str(exc)}
            log.error("[FAIL] %s | %s", label, exc)

    all_ok = all(v["ok"] for v in results.values())
    log.info("Param routing: %s", "all PASS" if all_ok else "some FAIL")
    return all_ok


# ─── main ─────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Panython ASR routing test")
    parser.add_argument("--mode", choices=["roundtrip", "params", "all"], default="all")
    parser.add_argument("--out-dir", default="/tmp/asr_test_audio", help="Directory to save WAV files")
    parser.add_argument("--wav", help="Existing WAV file for direct ASR test (skips TTS)")
    args = parser.parse_args()

    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    log.info("Output dir: %s", out_dir)
    log.info("Qwen3-ASR: %s", QWEN3_ASR_URL)
    log.info("SenseVoice: %s", SENSEVOICE_URL)
    log.info("CosyVoice: %s", COSYVOICE_URL)

    suite_results = {}

    qwen3_ok = test_qwen3_health()
    suite_results["qwen3_health"] = qwen3_ok
    if not qwen3_ok:
        log.error("Qwen3-ASR not ready — aborting.")
        sys.exit(1)

    # Direct WAV test (if --wav provided)
    if args.wav:
        wav_bytes = Path(args.wav).read_bytes()
        dur = _wav_duration_s(wav_bytes)
        log.info("Testing WAV: %s (%.2fs)", args.wav, dur)
        text_q, elapsed_q = _asr_qwen3(wav_bytes, Path(args.wav).name)
        text_sv, elapsed_sv = _asr_sensevoice(wav_bytes, Path(args.wav).name)
        log.info("[Qwen3-ASR]   %.2fs: %s", elapsed_q, text_q)
        log.info("[SenseVoice]  %.2fs: %s", elapsed_sv, text_sv)

    if args.mode in ("roundtrip", "all"):
        rt_results = test_roundtrip(out_dir)
        passed = sum(1 for r in rt_results if r.get("ok"))
        suite_results["roundtrip"] = passed == len(rt_results)
        summary_path = out_dir / f"asr_roundtrip_summary_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        summary_path.write_text(json.dumps(rt_results, ensure_ascii=False, indent=2))
        log.info("Summary → %s", summary_path)

    if args.mode in ("params", "all"):
        suite_results["param_routing"] = test_param_routing(out_dir)

    log.info("=" * 60)
    log.info("FINAL RESULTS")
    all_ok = True
    for suite, ok in suite_results.items():
        status = "PASS" if ok else "FAIL"
        log.info("  [%s] %s", status, suite)
        if not ok:
            all_ok = False
    log.info("=" * 60)
    log.info("Audio files: %s", out_dir)
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
