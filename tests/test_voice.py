import io

import numpy as np
import pytest
import soundfile as sf

from jarvis import voice

ready = voice.status()
needs_models = pytest.mark.skipif(not (ready["stt"] and ready["tts"]),
                                  reason="Modelos de voz não baixados (python -m jarvis.voice)")


def test_voice_endpoints_require_session(client):
    assert client.get("/api/voice/status").status_code == 401
    assert client.post("/api/stt", content=b"x").status_code == 401
    assert client.post("/api/tts", json={"text": "oi"}).status_code == 401


def test_clean_for_speech():
    assert voice.clean_for_speech("**Olá**! Veja `x` em https://a.b/c\n```py\nprint(1)\n```") == \
        "Olá! Veja x em link (trecho de código omitido)"


def test_tts_validation(logged):
    assert logged.post("/api/tts", json={"text": "oi", "voice": "inexistente"}).status_code == 422
    assert logged.post("/api/tts", json={"text": "x" * (voice.MAX_TTS_CHARS + 1)}).status_code == 422
    assert logged.post("/api/tts", json={"text": "oi", "speed": 5}).status_code == 422


def test_stt_rejects_empty_and_oversized(logged):
    assert logged.post("/api/stt", content=b"").status_code == 400
    assert logged.post("/api/stt", content=b"0" * (voice.MAX_AUDIO_BYTES + 1)).status_code == 413


@needs_models
def test_tts_returns_wav_and_204_for_symbols(logged):
    r = logged.post("/api/tts", json={"text": "Bom dia!", "voice": "pm_alex"})
    assert r.status_code == 200 and r.headers["content-type"] == "audio/wav"
    data, rate = sf.read(io.BytesIO(r.content))
    assert rate == 24000 and len(data) / rate > 0.3
    assert logged.post("/api/tts", json={"text": "***"}).status_code == 204


@needs_models
def test_speech_round_trip(logged):
    wav = logged.post("/api/tts", json={"text": "Qual é a previsão do tempo para amanhã?"}).content
    text = logged.post("/api/stt", content=wav, headers={"content-type": "audio/wav"}).json()["text"]
    assert "previsão do tempo" in text.lower()


@needs_models
def test_stt_silence_is_empty(logged):
    buf = io.BytesIO()
    sf.write(buf, np.zeros(16000 * 2, dtype="float32"), 16000, format="WAV")
    assert logged.post("/api/stt", content=buf.getvalue()).json() == {"text": ""}


@needs_models
def test_stt_garbage_audio(logged):
    assert logged.post("/api/stt", content=b"isto nao e audio" * 100).status_code == 400
