#!/usr/bin/env python3
"""
Qwen3-ASR-1.7B  —  OpenAI-compatible audio transcription server
Endpoint: POST /v1/audio/transcriptions
GPU:      CUDA_VISIBLE_DEVICES=1  (set by systemd / startup script)
Port:     9900

FunASR VAD and punctuation are loaded lazily on first use.
"""

import io
import logging
import os
import sys
import time
from contextlib import asynccontextmanager
from typing import Optional

import numpy as np
import soundfile as sf
import torch
import uvicorn
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import JSONResponse

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
log = logging.getLogger("qwen3-asr")

MODEL_PATH = os.environ.get(
    "MODEL_PATH",
    "/home/xsuper/app/newapp/models/Qwen3-ASR-1.7B",
)
PORT = int(os.environ.get("PORT", "9900"))
HOST = os.environ.get("HOST", "0.0.0.0")
# CUDA_VISIBLE_DEVICES=1 makes physical GPU1 appear as cuda:0
DEVICE = "cuda:0"

_model = None
_vad_model = None
_punc_model = None


def _load_model():
    global _model
    log.info("Loading Qwen3-ASR from %s …", MODEL_PATH)
    t0 = time.time()
    from qwen_asr import Qwen3ASRModel
    _model = Qwen3ASRModel.from_pretrained(
        MODEL_PATH,
        dtype=torch.float16,
        device_map=DEVICE,
        max_inference_batch_size=4,
        max_new_tokens=512,
    )
    log.info("Qwen3-ASR ready in %.1fs", time.time() - t0)


def _ensure_vad():
    global _vad_model
    if _vad_model is not None:
        return _vad_model
    try:
        from funasr import AutoModel
        log.info("Loading FunASR VAD model…")
        _vad_model = AutoModel(
            model="fsmn-vad",
            model_revision="v2.0.4",
            disable_update=True,
            device="cpu",
            hub="ms",  # use ModelScope cache
        )
        log.info("FunASR VAD ready")
    except Exception as exc:
        log.warning("FunASR VAD load failed: %s", exc)
        _vad_model = None
    return _vad_model


def _ensure_punc():
    global _punc_model
    if _punc_model is not None:
        return _punc_model
    try:
        from funasr import AutoModel
        log.info("Loading FunASR punctuation model…")
        _punc_model = AutoModel(
            model="ct-punc",
            model_revision="v2.0.4",
            disable_update=True,
            device="cpu",
            hub="ms",
        )
        log.info("FunASR punctuation ready")
    except Exception as exc:
        log.warning("FunASR punctuation load failed: %s", exc)
        _punc_model = None
    return _punc_model


@asynccontextmanager
async def lifespan(app: FastAPI):
    _load_model()
    yield


app = FastAPI(title="Qwen3-ASR", lifespan=lifespan)


def _read_audio(data: bytes) -> tuple[np.ndarray, int]:
    """Decode uploaded audio bytes → (float32 array, sample_rate).

    soundfile handles WAV/FLAC/OGG/MP3 etc.; PyAV is the fallback for
    WebM/Opus and other container formats that libsndfile cannot open.
    """
    buf = io.BytesIO(data)
    try:
        audio, sr = sf.read(buf, dtype="float32", always_2d=False)
        if audio.ndim == 2:
            audio = audio.mean(axis=1)
        return audio, sr
    except Exception:
        pass  # fall through to PyAV

    try:
        import av  # noqa: PLC0415
        buf2 = io.BytesIO(data)
        container = av.open(buf2)
        audio_stream = next((s for s in container.streams if s.type == "audio"), None)
        if audio_stream is None:
            raise ValueError("No audio stream found in file")
        detected_sr = audio_stream.sample_rate
        frames = []
        for frame in container.decode(audio_stream):
            frames.append(frame.to_ndarray())
        container.close()
        if not frames:
            raise ValueError("No audio frames decoded")
        merged = np.concatenate(frames, axis=-1)
        if merged.ndim == 2:
            merged = merged.mean(axis=0)
        audio = merged.astype(np.float32)
        # Normalise from integer PCM range if needed
        if audio.max() > 1.0 or audio.min() < -1.0:
            audio = audio / 32768.0
        return audio, detected_sr
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Cannot decode audio: {exc}") from exc


def _resample(audio: np.ndarray, src_sr: int, tgt_sr: int = 16000) -> np.ndarray:
    if src_sr == tgt_sr:
        return audio
    try:
        import scipy.signal as sps
        return sps.resample(audio, int(len(audio) * tgt_sr / src_sr)).astype(np.float32)
    except Exception:
        return audio


def _apply_vad(audio: np.ndarray, sr: int) -> np.ndarray:
    """Trim leading/trailing silence using FunASR fsmn-vad.

    Returns the trimmed audio (same sample rate).  Falls back to the
    original if VAD fails or returns no speech segments.
    """
    vad = _ensure_vad()
    if vad is None:
        return audio

    try:
        audio16k = _resample(audio, sr, 16000)
        # FunASR expects int16 PCM
        pcm16 = (audio16k * 32767).astype(np.int16)
        result = vad.generate(input=pcm16.tolist(), input_fs=16000)
        segments = result[0].get("value", []) if result else []
        if not segments:
            return audio

        # segments: [[start_ms, end_ms], ...]
        first_ms, last_ms = segments[0][0], segments[-1][1]
        start_sample = int(first_ms / 1000 * sr)
        end_sample = int(last_ms / 1000 * sr)
        trimmed = audio[start_sample:end_sample]
        log.info(
            "VAD: %.2fs → %.2fs (trimmed %.2fs)",
            len(audio) / sr,
            len(trimmed) / sr,
            (len(audio) - len(trimmed)) / sr,
        )
        return trimmed if len(trimmed) > 0 else audio
    except Exception as exc:
        log.warning("VAD processing failed: %s", exc)
        return audio


def _apply_punctuation(text: str) -> str:
    """Add punctuation to text using FunASR ct-punc."""
    if not text.strip():
        return text
    punc = _ensure_punc()
    if punc is None:
        return text
    try:
        result = punc.generate(input=text)
        restored = result[0].get("text", text) if result else text
        log.info("Punctuation: %d → %d chars", len(text), len(restored))
        return restored
    except Exception as exc:
        log.warning("Punctuation processing failed: %s", exc)
        return text


def _transcribe(
    audio: np.ndarray,
    sr: int,
    language: Optional[str] = None,
    vad: bool = False,
    punctuation: bool = False,
) -> str:
    if vad:
        audio = _apply_vad(audio, sr)

    # Qwen3-ASR expects 16 kHz; browser WebM/Opus is typically 48 kHz
    if sr != 16000:
        log.info("Resampling %d Hz → 16000 Hz", sr)
        audio = _resample(audio, sr, 16000)
        sr = 16000

    lang_map = {
        "zh": "Chinese", "yue": "Cantonese", "en": "English",
        "cantonese": "Cantonese", "chinese": "Chinese", "english": "English",
    }
    lang_name = lang_map.get(language.lower(), language) if language else None

    results = _model.transcribe(audio=(audio, sr), language=lang_name)
    text = results[0].text.strip() if results else ""

    if punctuation and text:
        text = _apply_punctuation(text)

    return text


@app.get("/v1/models")
def list_models():
    return {
        "object": "list",
        "data": [{"id": "qwen3-asr", "object": "model", "created": 1767225600, "owned_by": "qwenlm"}],
    }


@app.post("/v1/audio/transcriptions")
async def transcribe(
    file: UploadFile = File(...),
    model: str = Form(default="qwen3-asr"),
    language: Optional[str] = Form(default=None),
    response_format: str = Form(default="json"),
    temperature: float = Form(default=0.0),
    # Panython extensions
    vad: bool = Form(default=False),
    punctuation: bool = Form(default=False),
):
    if _model is None:
        raise HTTPException(status_code=503, detail="Model not loaded")

    t0 = time.time()
    raw = await file.read()
    audio, sr = _read_audio(raw)
    text = _transcribe(audio, sr, language=language, vad=vad, punctuation=punctuation)
    elapsed = time.time() - t0

    log.info(
        "Transcribed %.1fs audio in %.2fs | lang=%s | vad=%s | punc=%s | chars=%d",
        len(audio) / max(sr, 1), elapsed, language or "auto", vad, punctuation, len(text),
    )

    if response_format == "text":
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse(text)

    return JSONResponse({"text": text})


@app.get("/health")
def health():
    ready = _model is not None
    vram_free = -1
    if torch.cuda.is_available():
        props = torch.cuda.mem_get_info(0)
        vram_free = props[0] // (1024 ** 2)
    return {
        "ready": ready,
        "model": "qwen3-asr-1.7b",
        "vram_free_mb": vram_free,
        "funasr_vad": _vad_model is not None,
        "funasr_punc": _punc_model is not None,
    }


if __name__ == "__main__":
    uvicorn.run(app, host=HOST, port=PORT, log_level="info")
