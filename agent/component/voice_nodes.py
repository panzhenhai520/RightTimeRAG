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

import os
import struct
from abc import ABC
from typing import Any

from agent.artifact_service import ArtifactService
from agent.component.base import ComponentBase, ComponentParamBase
from api.db.services.file_service import FileService
from api.utils.api_utils import timeout


DEFAULT_COSYVOICE_URL = os.environ.get("COSYVOICE_URL", "http://127.0.0.1:50001")
DEFAULT_QWEN3_ASR_URL = os.environ.get("QWEN3_ASR_URL", "http://127.0.0.1:9900")
DEFAULT_SENSEVOICE_URL = os.environ.get("SENSEVOICE_URL", "http://127.0.0.1:9997")


def wav_duration_s(wav_bytes: bytes) -> float:
    try:
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            return 0.0
        _, channels, sample_rate, _, _, bits = struct.unpack_from("<HHIIHH", wav_bytes, 20)
        bytes_per_sample = bits // 8
        if not channels or not sample_rate or not bytes_per_sample:
            return 0.0
        return max(0.0, (len(wav_bytes) - 44) / (sample_rate * channels * bytes_per_sample))
    except Exception:
        return 0.0


class AudioInputParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.audio = ""
        self.outputs = {"audio": {"value": {}, "type": "AudioAsset"}}

    def check(self):
        return True


class AudioInput(ComponentBase, ABC):
    component_name = "AudioInput"

    @staticmethod
    def normalize_audio_asset(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return {
                "type": "audio",
                "file_id": value.get("file_id") or value.get("id"),
                "name": value.get("name") or value.get("filename") or "audio.wav",
                "mime_type": value.get("mime_type") or "audio/wav",
                "created_by": value.get("created_by"),
                "duration": value.get("duration"),
                "engine": value.get("engine"),
            }
        if isinstance(value, str):
            return {"type": "audio", "file_id": value, "name": "audio.wav", "mime_type": "audio/wav"}
        return {"type": "audio", "name": "audio.wav", "mime_type": "audio/wav"}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        value = self._param.audio
        if isinstance(value, str) and self._canvas.is_reff(value):
            value = self._canvas.get_variable_value(value)
        self.set_output("audio", self.normalize_audio_asset(value))


class TTSGenerateParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.voice_profile = "female_mandarin_01"
        self.speed = 1.0
        self.endpoint = DEFAULT_COSYVOICE_URL
        self.timeout = 30
        self.outputs = {
            "audio": {"value": {}, "type": "AudioAsset"},
            "voice": {"value": {}, "type": "VoiceReply"},
            "duration": {"value": 0, "type": "number"},
            "engine": {"value": "CosyVoice3", "type": "string"},
        }

    def check(self):
        self.check_positive_number(float(self.speed), "[TTSGenerate] Speed")
        self.check_positive_integer(int(self.timeout), "[TTSGenerate] Timeout")


class TTSGenerate(ComponentBase, ABC):
    component_name = "TTSGenerate"

    @staticmethod
    def build_payload(text: str, voice_profile: str, speed: float) -> dict[str, Any]:
        return {
            "model": "CosyVoice3",
            "input": text,
            "voice": voice_profile,
            "speed": float(speed),
            "response_format": "wav",
        }

    @staticmethod
    def audio_asset_from_download(download_info: dict[str, Any], duration: float, voice_profile: str, speed: float) -> dict[str, Any]:
        return {
            "type": "audio",
            "artifact": ArtifactService.attachment_from_download(download_info),
            "mime_type": "audio/wav",
            "duration": duration,
            "engine": "CosyVoice3",
            "voice_profile": voice_profile,
            "speed": speed,
        }

    def _resolve_text(self) -> str:
        text = self._param.text
        if isinstance(text, str) and self._canvas.is_reff(text):
            text = self._canvas.get_variable_value(text)
        return str(text or "").strip()

    def _post(self, url: str, payload: dict[str, Any], timeout: int):
        import requests

        return requests.post(f"{url.rstrip('/')}/v1/audio/speech", json=payload, timeout=timeout)

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        text = self._resolve_text()
        if not text:
            raise ValueError("TTSGenerate requires non-empty text")
        payload = self.build_payload(text, self._param.voice_profile, self._param.speed)
        try:
            resp = self._post(self._param.endpoint, payload, int(self._param.timeout))
        except Exception as exc:
            raise RuntimeError(f"CosyVoice3 unavailable at {self._param.endpoint}: {exc}") from exc
        if getattr(resp, "status_code", 500) != 200:
            raise RuntimeError(f"CosyVoice3 error {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
        wav_bytes = resp.content
        duration = wav_duration_s(wav_bytes)
        download = ArtifactService.create_download_info(
            self._canvas.get_tenant_id(),
            wav_bytes,
            "tts.wav",
            mime_type="audio/wav",
            run_id=getattr(self._canvas, "_run_id", None),
            node_id=getattr(self, "_id", None),
        )
        audio = self.audio_asset_from_download(download, duration, self._param.voice_profile, float(self._param.speed))
        voice = {"text": text, "audio": audio, "engine": "CosyVoice3"}
        self.set_output("audio", audio)
        self.set_output("voice", voice)
        self.set_output("duration", duration)
        self.set_output("engine", "CosyVoice3")


class ASRTranscribeParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.audio = ""
        self.engine = "qwen3"
        self.language = "auto"
        self.endpoint = ""
        self.timeout = 60
        self.vad = False
        self.punctuation = False
        self.outputs = {
            "text": {"value": "", "type": "string"},
            "transcript": {"value": "", "type": "string"},
            "confidence": {"value": 0, "type": "number"},
            "language": {"value": "auto", "type": "string"},
            "duration": {"value": 0, "type": "number"},
            "engine": {"value": "", "type": "string"},
        }

    def check(self):
        self.check_valid_value(self.engine, "[ASRTranscribe] Engine", ["qwen3", "sensevoice"])
        self.check_positive_integer(int(self.timeout), "[ASRTranscribe] Timeout")


class ASRTranscribe(ComponentBase, ABC):
    component_name = "ASRTranscribe"

    @staticmethod
    def build_form_data(engine: str, language: str = "auto", vad: bool = False, punctuation: bool = False) -> dict[str, str]:
        data = {"model": "qwen3-asr" if engine == "qwen3" else "SenseVoiceSmall"}
        if engine == "qwen3":
            if language and language != "auto":
                data["language"] = language
            if vad:
                data["vad"] = "true"
            if punctuation:
                data["punctuation"] = "true"
        return data

    @staticmethod
    def endpoint_for(engine: str, configured: str = "") -> str:
        if configured:
            return configured.rstrip("/")
        return DEFAULT_QWEN3_ASR_URL if engine == "qwen3" else DEFAULT_SENSEVOICE_URL

    def _resolve_audio_asset(self) -> dict[str, Any]:
        audio = self._param.audio
        if isinstance(audio, str) and self._canvas.is_reff(audio):
            audio = self._canvas.get_variable_value(audio)
        return AudioInput.normalize_audio_asset(audio)

    def _audio_bytes(self, asset: dict[str, Any]) -> tuple[bytes, str, str]:
        file_id = asset.get("file_id")
        created_by = asset.get("created_by") or self._canvas.get_tenant_id()
        if not file_id:
            raise ValueError("ASRTranscribe requires an audio FileAsset or AudioAsset with file_id")
        return FileService.get_blob(created_by, file_id), asset.get("name") or "audio.wav", asset.get("mime_type") or "audio/wav"

    def _post(self, endpoint: str, files: dict[str, Any], data: dict[str, str], timeout: int):
        import requests

        return requests.post(f"{endpoint.rstrip('/')}/v1/audio/transcriptions", files=files, data=data, timeout=timeout)

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        asset = self._resolve_audio_asset()
        audio_bytes, filename, mime_type = self._audio_bytes(asset)
        endpoint = self.endpoint_for(self._param.engine, self._param.endpoint)
        data = self.build_form_data(self._param.engine, self._param.language, self._param.vad, self._param.punctuation)
        try:
            resp = self._post(endpoint, {"file": (filename, audio_bytes, mime_type)}, data, int(self._param.timeout))
        except Exception as exc:
            raise RuntimeError(f"ASR service unavailable at {endpoint}: {exc}") from exc
        if getattr(resp, "status_code", 500) != 200:
            raise RuntimeError(f"ASR service error {resp.status_code}: {str(getattr(resp, 'text', ''))[:200]}")
        body = resp.json()
        text = body.get("text", "")
        self.set_output("text", text)
        self.set_output("transcript", text)
        self.set_output("confidence", float(body.get("confidence") or 0))
        self.set_output("language", body.get("language") or self._param.language)
        self.set_output("duration", float(body.get("duration") or asset.get("duration") or wav_duration_s(audio_bytes)))
        self.set_output("engine", self._param.engine)


class VoiceReplyOutputParam(ComponentParamBase):
    def __init__(self):
        super().__init__()
        self.text = ""
        self.audio = ""
        self.outputs = {
            "voice": {"value": {}, "type": "VoiceReply"},
            "audio": {"value": {}, "type": "AudioAsset"},
        }

    def check(self):
        return True


class VoiceReplyOutput(ComponentBase, ABC):
    component_name = "VoiceReplyOutput"

    @staticmethod
    def build_voice_reply(text: str, audio: dict[str, Any]) -> dict[str, Any]:
        return {"text": str(text or ""), "audio": AudioInput.normalize_audio_asset(audio), "type": "voice_reply"}

    @timeout(int(os.environ.get("COMPONENT_EXEC_TIMEOUT", 10 * 60)))
    def _invoke(self, **kwargs):
        text = self._param.text
        audio = self._param.audio
        if isinstance(text, str) and self._canvas.is_reff(text):
            text = self._canvas.get_variable_value(text)
        if isinstance(audio, str) and self._canvas.is_reff(audio):
            audio = self._canvas.get_variable_value(audio)
        voice = self.build_voice_reply(text, audio if isinstance(audio, dict) else {})
        self.set_output("voice", voice)
        self.set_output("audio", voice["audio"])
