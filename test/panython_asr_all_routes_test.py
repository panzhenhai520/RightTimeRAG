#!/usr/bin/env python3
"""
Panython ASR — complete routing combination test.

Tests every routing mode × merge strategy × vad/punc flag combination.
Uses TTS (CosyVoice) to generate known-text WAV files, then routes
those WAVs through all ASR paths and prints a comparison table.

Routes under test:
  single/qwen3            - Qwen3-ASR only (SV fallback if empty)
  single/sensevoice       - SenseVoice only
  dual/qwen3_primary      - Both parallel, prefer Qwen3 result
  dual/sensevoice_primary - Both parallel, prefer SenseVoice result
  dual/longest            - Both parallel, pick longer result

Usage:
    python3 test/panython_asr_all_routes_test.py
    python3 test/panython_asr_all_routes_test.py --skip-tts   # reuse existing WAVs in --wav-dir
    python3 test/panython_asr_all_routes_test.py --wav-dir /tmp/asr_test_audio
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

# ─── endpoints ───────────────────────────────────────────────────────────────
QWEN3_URL     = os.environ.get("QWEN3_ASR_URL",   "http://127.0.0.1:9900")
SENSEVOICE_URL= os.environ.get("SENSEVOICE_URL",  "http://127.0.0.1:9997")
COSYVOICE_URL = os.environ.get("COSYVOICE_URL",   "http://127.0.0.1:50001")

# ─── test corpus ─────────────────────────────────────────────────────────────
# Each case: id, voice, reference text, language hint, expected keywords
CORPUS = [
    {
        "id": "mandarin_short",
        "voice": "female_mandarin_01",
        "ref":   "你好，今天天气怎么样？这里是普通话朗读测试。",
        "lang":  "zh",
        "kw":    ["今天", "天气", "普通话"],
    },
    {
        "id": "mandarin_long",
        "voice": "male_mandarin_01",
        "ref":   "人工智能技术正在快速发展，语音识别的准确率越来越高，已经可以媲美人类的识别能力。",
        "lang":  "zh",
        "kw":    ["人工智能", "语音识别", "准确率"],
    },
    {
        "id": "cantonese_short",
        "voice": "female_cantonese_01",
        "ref":   "你好，今日天气点样？呢度係粵語朗讀測試。",
        "lang":  "yue",
        "kw":    ["今日", "天气"],
    },
    {
        "id": "cantonese_long",
        "voice": "male_cantonese_01",
        "ref":   "人工智能技术正在快速发展，粤语识别越来越准确，语音交互已成为日常生活的重要组成部分。",
        "lang":  "yue",
        "kw":    ["人工智能", "粤语", "识别"],
    },
    {
        "id": "sichuan",
        "voice": "female_sichuan_01",
        "ref":   "四川话是中国的一种方言，有着独特的声调和语调特征。",
        "lang":  "zh",
        "kw":    ["四川", "方言"],
    },
    {
        "id": "mixed_num",
        "voice": "female_mandarin_01",
        "ref":   "会议在2026年6月24日召开，共有128名代表出席。",
        "lang":  "zh",
        "kw":    ["会议", "代表"],
    },
]

# Routing modes to test: (mode, merge_strategy_or_model)
ROUTES = [
    ("single", "qwen3"),
    ("single", "sensevoice"),
    ("dual",   "qwen3_primary"),
    ("dual",   "sensevoice_primary"),
    ("dual",   "longest"),
]

# Parameter flag combinations (vad, punctuation)
FLAG_COMBOS = [
    (False, False),   # baseline
    (True,  False),   # VAD only
    (False, True),    # punctuation only
]

# ─── logging ─────────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("asr-all-routes")


# ─── helpers ─────────────────────────────────────────────────────────────────

def _wav_dur(wav_bytes: bytes) -> float:
    try:
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            return 0.0
        _, ch, sr, _, _, bits = struct.unpack_from("<HHIIHH", wav_bytes, 20)
        bps = bits // 8
        return (len(wav_bytes) - 44) / (sr * ch * bps) if bps else 0.0
    except Exception:
        return 0.0


def _tts(voice: str, text: str, timeout: int = 30) -> bytes:
    resp = requests.post(
        f"{COSYVOICE_URL}/v1/audio/speech",
        json={"model": "CosyVoice3", "input": text, "voice": voice, "response_format": "wav"},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.content


def _qwen3(wav: bytes, fname: str, lang: str | None,
           vad: bool, punc: bool, timeout: int = 60) -> tuple[str, float]:
    t0 = time.perf_counter()
    data: dict = {"model": "qwen3-asr"}
    if lang and lang != "auto":
        data["language"] = lang
    if vad:
        data["vad"] = "true"
    if punc:
        data["punctuation"] = "true"
    resp = requests.post(
        f"{QWEN3_URL}/v1/audio/transcriptions",
        files={"file": (fname, wav, "audio/wav")},
        data=data,
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json().get("text", ""), round(time.perf_counter() - t0, 3)


def _sensevoice(wav: bytes, fname: str, timeout: int = 60) -> tuple[str, float]:
    t0 = time.perf_counter()
    try:
        resp = requests.post(
            f"{SENSEVOICE_URL}/v1/audio/transcriptions",
            files={"file": (fname, wav, "audio/wav")},
            data={"model": "SenseVoiceSmall"},
            timeout=timeout,
        )
        resp.raise_for_status()
        return resp.json().get("text", ""), round(time.perf_counter() - t0, 3)
    except Exception as exc:
        return f"[ERROR:{exc}]", round(time.perf_counter() - t0, 3)


def _merge(a: str, b: str, strategy: str) -> str:
    qa, sv = a.strip(), b.strip()
    if strategy == "qwen3_primary":
        return qa if qa else sv
    if strategy == "sensevoice_primary":
        return sv if sv else qa
    return qa if len(qa) >= len(sv) else sv   # longest


def _cer(ref: str, hyp: str) -> float:
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
            dp[j] = prev[j-1] if ref[i-1] == hyp[j-1] else 1 + min(prev[j], dp[j-1], prev[j-1])
    return dp[n] / m


def _kw(text: str, kws: list[str]) -> str:
    hits = sum(1 for k in kws if k in text)
    return f"{hits}/{len(kws)}"


def _short(text: str, maxlen: int = 28) -> str:
    text = text.strip()
    return text if len(text) <= maxlen else text[:maxlen] + "…"


# ─── main test ───────────────────────────────────────────────────────────────

def run_all(wav_dir: Path, skip_tts: bool = False):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")

    # ── Step 1: synthesize or load WAVs ──────────────────────────────────────
    wav_cache: dict[str, bytes] = {}
    log.info("=" * 70)
    log.info("STEP 1: TTS synthesis")
    log.info("=" * 70)
    for case in CORPUS:
        wav_path = wav_dir / f"corpus_{case['id']}_{ts}.wav"
        if skip_tts:
            existing = sorted(wav_dir.glob(f"corpus_{case['id']}_*.wav"))
            if existing:
                wav_path = existing[-1]
                wav_cache[case["id"]] = wav_path.read_bytes()
                log.info("Loaded: %s (%.2fs)", wav_path.name, _wav_dur(wav_cache[case["id"]]))
                continue
        t0 = time.perf_counter()
        try:
            wav_bytes = _tts(case["voice"], case["ref"])
            dur = _wav_dur(wav_bytes)
            wav_path.write_bytes(wav_bytes)
            wav_cache[case["id"]] = wav_bytes
            log.info("[OK] %s | voice=%s | dur=%.2fs | synth=%.2fs | file=%s",
                     case["id"], case["voice"], dur, time.perf_counter() - t0, wav_path.name)
        except Exception as exc:
            log.error("[FAIL] TTS for %s: %s", case["id"], exc)

    # ── Step 2: run all routes × all cases × all flag combos ─────────────────
    log.info("")
    log.info("=" * 70)
    log.info("STEP 2: ASR — %d routes × %d cases × %d flag combos = %d total calls",
             len(ROUTES), len(CORPUS), len(FLAG_COMBOS),
             len(ROUTES) * len(CORPUS) * len(FLAG_COMBOS))
    log.info("=" * 70)

    # results[case_id][route_label][flag_label] = {text, cer, kw, elapsed}
    results: dict = {}

    for case in CORPUS:
        cid = case["id"]
        wav = wav_cache.get(cid)
        if wav is None:
            log.warning("No WAV for %s, skipping", cid)
            continue
        results[cid] = {}
        fname = f"corpus_{cid}.wav"
        lang = case["lang"]
        kws = case["kw"]

        # Pre-fetch both model outputs for each flag combo (avoids calling models twice for dual)
        model_cache: dict = {}   # (vad, punc) → (qwen3_text, qwen3_elapsed, sv_text, sv_elapsed)
        for vad, punc in FLAG_COMBOS:
            try:
                qt, qe = _qwen3(wav, fname, lang, vad, punc)
            except Exception as exc:
                qt, qe = f"[ERROR:{exc}]", 0.0
            try:
                st, se = _sensevoice(wav, fname)
            except Exception as exc:
                st, se = f"[ERROR:{exc}]", 0.0
            model_cache[(vad, punc)] = (qt, qe, st, se)

        for mode, strategy in ROUTES:
            route_label = f"{mode}/{strategy}"
            results[cid][route_label] = {}

            for vad, punc in FLAG_COMBOS:
                flag_label = f"vad={int(vad)},punc={int(punc)}"
                qt, qe, st, se = model_cache[(vad, punc)]

                if mode == "single" and strategy == "qwen3":
                    text = qt if qt else st   # qwen3 with SV fallback
                    elapsed = qe
                    source = "qwen3" if qt else "sv_fallback"
                elif mode == "single" and strategy == "sensevoice":
                    text = st
                    elapsed = se
                    source = "sensevoice"
                else:
                    # dual: parallel (already fetched both)
                    text = _merge(qt, st, strategy)
                    elapsed = max(qe, se)   # parallel = whichever finishes last
                    source = f"dual({strategy})"

                cer = _cer(case["ref"], text)
                results[cid][route_label][flag_label] = {
                    "text": text,
                    "cer": round(cer, 4),
                    "kw": _kw(text, kws),
                    "elapsed_s": elapsed,
                    "source": source,
                    "qwen3": qt,
                    "sensevoice": st,
                }

    # ── Step 3: print comparison tables ──────────────────────────────────────
    for case in CORPUS:
        cid = case["id"]
        if cid not in results:
            continue
        ref = case["ref"]
        log.info("")
        log.info("━" * 90)
        log.info("CASE: %s  |  voice=%s  |  lang=%s", cid, case["voice"], case["lang"])
        log.info("REF:  %s", ref)
        log.info("━" * 90)

        # Header
        flag_labels = [f"vad={int(v)},punc={int(p)}" for v, p in FLAG_COMBOS]
        col_w = 22
        header = f"{'Route':<28}" + "".join(f"{'  CER / kw / text':<{col_w*2}}" for _ in flag_labels)
        log.info("%-28s | %-30s | %-30s | %-30s", "Route", flag_labels[0], flag_labels[1], flag_labels[2])
        log.info("%-28s + %-30s + %-30s + %-30s", "-"*28, "-"*30, "-"*30, "-"*30)

        for mode, strategy in ROUTES:
            route_label = f"{mode}/{strategy}"
            r = results[cid].get(route_label, {})
            cells = []
            for vad, punc in FLAG_COMBOS:
                fl = f"vad={int(vad)},punc={int(punc)}"
                d = r.get(fl, {})
                cer_pct = f"{d.get('cer', 1)*100:.0f}%"
                kw = d.get("kw", "?")
                txt = _short(d.get("text", ""))
                cells.append(f"CER={cer_pct} kw={kw} | {txt}")
            log.info("%-28s | %-30s | %-30s | %-30s", route_label, cells[0], cells[1], cells[2])

        # Show raw qwen3 vs sv for baseline
        baseline = (False, False)
        fl = f"vad={int(baseline[0])},punc={int(baseline[1])}"
        first_route = f"{ROUTES[0][0]}/{ROUTES[0][1]}"
        d0 = results[cid].get(first_route, {}).get(fl, {})
        log.info("")
        log.info("  Qwen3-ASR (baseline): %s", d0.get("qwen3", "N/A"))
        log.info("  SenseVoice (baseline): %s", d0.get("sensevoice", "N/A"))

    # ── Step 4: summary across all cases ─────────────────────────────────────
    log.info("")
    log.info("=" * 90)
    log.info("SUMMARY — average CER per route (baseline vad=0,punc=0)")
    log.info("=" * 90)
    fl = "vad=0,punc=0"
    route_stats: dict[str, list[float]] = {f"{m}/{s}": [] for m, s in ROUTES}
    for cid, route_data in results.items():
        for route_label, flags in route_data.items():
            cer = flags.get(fl, {}).get("cer")
            if cer is not None:
                route_stats[route_label].append(cer)

    for route_label, cers in route_stats.items():
        if not cers:
            continue
        avg_cer = sum(cers) / len(cers)
        best = min(cers)
        worst = max(cers)
        log.info("  %-28s | avg_CER=%4.1f%% | best=%4.1f%% | worst=%4.1f%%",
                 route_label, avg_cer * 100, best * 100, worst * 100)

    log.info("=" * 90)

    # ── Step 5: save JSON for reference ──────────────────────────────────────
    out_path = wav_dir / f"asr_all_routes_{ts}.json"
    out_path.write_text(json.dumps(results, ensure_ascii=False, indent=2))
    log.info("Full results → %s", out_path)

    return results


# ─── entry ───────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--wav-dir", default="/tmp/asr_all_routes", help="Output / WAV cache dir")
    parser.add_argument("--skip-tts", action="store_true", help="Reuse existing WAVs from --wav-dir")
    args = parser.parse_args()

    wav_dir = Path(args.wav_dir)
    wav_dir.mkdir(parents=True, exist_ok=True)

    log.info("WAV dir: %s", wav_dir)
    log.info("Routes: %s", [f"{m}/{s}" for m, s in ROUTES])
    log.info("Flags:  %s", [(v, p) for v, p in FLAG_COMBOS])

    run_all(wav_dir, skip_tts=args.skip_tts)


if __name__ == "__main__":
    main()
