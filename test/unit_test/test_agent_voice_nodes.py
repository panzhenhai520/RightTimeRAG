import io
import wave

from agent.component.voice_nodes import ASRTranscribe, TTSGenerate, VoiceReplyOutput, wav_duration_s


def make_wav(duration_s=0.1, rate=16000):
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(b"\x00\x00" * int(duration_s * rate))
    return buf.getvalue()


def test_tts_generate_payload_and_audio_asset_exclude_binary():
    payload = TTSGenerate.build_payload("hello", "female_mandarin_01", 1.2)
    audio = TTSGenerate.audio_asset_from_download(
        {"doc_id": "doc-1", "filename": "tts.wav", "mime_type": "audio/wav", "url": "/download/doc-1"},
        1.5,
        "female_mandarin_01",
        1.2,
    )

    assert payload == {
        "model": "CosyVoice3",
        "input": "hello",
        "voice": "female_mandarin_01",
        "speed": 1.2,
        "response_format": "wav",
    }
    assert audio["duration"] == 1.5
    assert audio["voice_profile"] == "female_mandarin_01"
    assert "bytes" not in audio


def test_asr_transcribe_builds_local_service_payloads():
    qwen3 = ASRTranscribe.build_form_data("qwen3", language="zh", vad=True, punctuation=True)
    sensevoice = ASRTranscribe.build_form_data("sensevoice")

    assert qwen3 == {
        "model": "qwen3-asr",
        "language": "zh",
        "vad": "true",
        "punctuation": "true",
    }
    assert sensevoice == {"model": "SenseVoiceSmall"}
    assert ASRTranscribe.endpoint_for("qwen3") == "http://127.0.0.1:9900"
    assert ASRTranscribe.endpoint_for("sensevoice") == "http://127.0.0.1:9997"


def test_voice_reply_output_and_wav_duration_are_metadata_only():
    wav_bytes = make_wav(0.2)
    reply = VoiceReplyOutput.build_voice_reply(
        "hello",
        {"file_id": "audio-1", "name": "student.wav", "mime_type": "audio/wav", "duration": 0.2},
    )

    assert 0.15 <= wav_duration_s(wav_bytes) <= 0.25
    assert reply["type"] == "voice_reply"
    assert reply["audio"]["file_id"] == "audio-1"
    assert "bytes" not in reply["audio"]
