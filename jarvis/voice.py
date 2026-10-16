"""Voz local na CPU: transcrição (faster-whisper) e síntese (Kokoro ONNX).

Baixar os modelos (uma vez, ~600 MB): .venv\\Scripts\\python.exe -m jarvis.voice
Depois disso tudo funciona offline.
"""
import io
import re
import threading
import urllib.request
from functools import lru_cache

import soundfile as sf

from . import config

KOKORO_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/"
KOKORO_FILES = {"kokoro-v1.0.int8.onnx": 92_361_271, "voices-v1.0.bin": 28_214_398}
VOICES = {"pf_dora": "Dora (feminina)", "pm_alex": "Alex (masculina)", "pm_santa": "Santa (masculina)"}
MAX_AUDIO_BYTES = 10_000_000
MAX_TTS_CHARS = 1000
_stt_lock, _tts_lock = threading.Lock(), threading.Lock()  # uma inferência por vez: evita picos de RAM


class VoiceUnavailable(Exception):
    pass


def _dir(name: str):
    return config.MODELS_DIR / name


def status() -> dict:
    kokoro = all((_dir("kokoro") / f).exists() for f in KOKORO_FILES)
    whisper = any(_dir("whisper").glob(f"models--Systran--faster-whisper-{config.WHISPER_MODEL}/snapshots/*/model.bin"))
    return {"stt": whisper, "tts": kokoro, "whisper_model": config.WHISPER_MODEL, "voices": VOICES}


@lru_cache(1)
def _whisper():
    from faster_whisper import WhisperModel
    try:
        return WhisperModel(config.WHISPER_MODEL, device="cpu", compute_type="int8",
                            download_root=str(_dir("whisper")), local_files_only=True)
    except Exception as e:
        raise VoiceUnavailable("Modelo de transcrição não encontrado. Rode: .venv\\Scripts\\python.exe -m jarvis.voice") from e


@lru_cache(1)
def _kokoro():
    from kokoro_onnx import Kokoro
    d = _dir("kokoro")
    if not all((d / f).exists() for f in KOKORO_FILES):
        raise VoiceUnavailable("Modelo de voz não encontrado. Rode: .venv\\Scripts\\python.exe -m jarvis.voice")
    return Kokoro(str(d / "kokoro-v1.0.int8.onnx"), str(d / "voices-v1.0.bin"))


def transcribe(audio) -> str:
    """Áudio em bytes (webm/opus, ogg, wav, mp4: o que o FFmpeg embutido no PyAV entender)
    ou amostras float32 a 16 kHz (usado pela escuta local)."""
    source = io.BytesIO(audio) if isinstance(audio, bytes | bytearray) else audio
    with _stt_lock:
        segments, _ = _whisper().transcribe(source, language="pt", beam_size=1,
                                            vad_filter=True, condition_on_previous_text=False,
                                            initial_prompt="Sarah")  # o nome dela: ajuda o Whisper a escrever certo
        return " ".join(s.text.strip() for s in segments).strip()


def clean_for_speech(text: str) -> str:
    text = re.sub(r"```[\s\S]*?(```|$)", " (trecho de código omitido) ", text)
    text = re.sub(r"https?://\S+", " link ", text)
    text = re.sub(r"[*_`#>|~]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def synthesize(text: str, voice: str = "pf_dora", speed: float = 1.0) -> bytes:
    """Retorna WAV. Texto vazio após a limpeza retorna b''."""
    text = clean_for_speech(text)
    if not text:
        return b""
    if voice not in VOICES:
        raise ValueError(f"Voz desconhecida: {voice}")
    with _tts_lock:
        samples, rate = _kokoro().create(text, voice=voice, speed=min(max(speed, 0.5), 2.0), lang="pt-br")
    buf = io.BytesIO()
    sf.write(buf, samples, rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


def play(wav: bytes) -> float:
    """Toca um WAV na saída de áudio padrão do Windows e espera terminar. Devolve a duração em segundos."""
    import sounddevice as sd
    data, rate = sf.read(io.BytesIO(wav), dtype="float32")
    sd.play(data, rate)
    sd.wait()
    return len(data) / rate


def stop_playback() -> None:
    """Interrompe a fala que está tocando no PC (ex.: tarefa parada pelo celular)."""
    import sounddevice as sd
    sd.stop()


def beep() -> None:
    """Bipe curto de "estou ouvindo" (o mesmo da página)."""
    import numpy as np
    import sounddevice as sd
    t = np.arange(int(16000 * 0.15)) / 16000
    sd.play((0.15 * np.sin(2 * np.pi * 880 * t) * np.exp(-t * 25)).astype(np.float32), 16000)
    sd.wait()


def download() -> None:
    d = _dir("kokoro")
    d.mkdir(parents=True, exist_ok=True)
    for name, size in KOKORO_FILES.items():
        target = d / name
        if target.exists() and target.stat().st_size == size:
            print(f"ok  {name}")
            continue
        print(f"baixando {name} ({size / 1e6:.0f} MB)...")
        urllib.request.urlretrieve(KOKORO_URL + name, target.with_suffix(".part"))
        if target.with_suffix(".part").stat().st_size != size:
            raise SystemExit(f"Tamanho inesperado em {name}; download corrompido. Tente de novo.")
        target.with_suffix(".part").replace(target)
    from faster_whisper import WhisperModel

    from .listener import SPOT_MODEL
    for name in dict.fromkeys([config.WHISPER_MODEL, SPOT_MODEL]):  # transcrição e gatilho "Sarah"
        print(f"baixando Whisper '{name}' (pode levar alguns minutos)...")
        WhisperModel(name, device="cpu", compute_type="int8", download_root=str(_dir("whisper")))
    print("Modelos de voz prontos:", status())


if __name__ == "__main__":
    download()
