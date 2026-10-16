"""Escuta local opcional (desligada por padrão): o nome "Sarah" e/ou duas palmas.

O microfone do PC só é aberto quando o modo não é "off". Os quadros de áudio são analisados
em memória e descartados; nada é gravado nem enviado pela rede. Ao detectar, o servidor avisa
a interface aberta no PC, que então grava a pergunta como se o botão 🎤 tivesse sido clicado.
"""
import contextlib
import json
import logging
import queue
import re
import threading
import time
from functools import lru_cache
from collections.abc import Callable

import numpy as np

from . import config, db

log = logging.getLogger("jarvis")
MODES = ("off", "palavra", "palmas", "ambos")
RATE, FRAME = 16000, 1280  # quadros de 80 ms
COOLDOWN_FRAMES = 3 * RATE // FRAME  # ignora novos acionamentos por 3 s
STALL_SECONDS = 5  # sem áudio por 5 s com a escuta ligada = microfone desconectado ou travado


class ClapDetector:
    """Duas palmas: dois estalos que surgem do silêncio e somem em menos de 100 ms,
    separados por 0,15 a 1 s. Fala e música não sobem do nada nem somem tão rápido."""
    WIN = 320  # janelas de 20 ms

    def __init__(self, min_peak: float = 0.2, ratio: float = 6.0):
        self.min_peak, self.ratio = min_peak, ratio
        self.noise = 0.005   # RMS do ruído de fundo, atualizado continuamente
        self.prev = 0.0      # RMS da janela anterior
        self.n = 0           # índice da janela atual
        self.candidate = None  # (janela inicial, rms máximo, pico) de um estalo em confirmação
        self.last_clap = None
        self.peaks: list[float] = []  # pico de cada palma confirmada (usado na calibração)

    def feed(self, samples: np.ndarray) -> bool:
        """samples: float32 entre -1 e 1. Retorna True quando reconhece duas palmas."""
        fired = False
        for i in range(0, len(samples) - self.WIN + 1, self.WIN):
            w = samples[i:i + self.WIN]
            rms, peak = float(np.sqrt(np.mean(w * w))), float(np.max(np.abs(w)))
            prev, self.prev = self.prev, rms
            self.n += 1
            if self.candidate:
                start, top, top_peak = self.candidate
                age = self.n - start
                if age == 1:
                    self.candidate = (start, max(top, rms), max(top_peak, peak))  # o estalo pode cair entre duas janelas
                elif rms > {2: 0.6, 3: 0.45}.get(age, 0.35) * top:
                    self.candidate = None  # som sustentado (fala, música): não é palma
                elif age >= 5:  # foi sumindo até 100 ms depois do estalo (aceita eco de sala)
                    self.candidate = None
                    self.peaks.append(top_peak)
                    if self.last_clap is not None and 7 <= start - self.last_clap <= 50:
                        self.last_clap, fired = None, True
                    else:
                        self.last_clap = start
                continue
            if peak >= self.min_peak and rms >= self.ratio * max(self.noise, prev):
                self.candidate = (self.n, rms, peak)  # subida brusca a partir de silêncio
            else:
                self.noise = 0.98 * self.noise + 0.02 * rms
        return fired


SPOT_MODEL = "base"  # medido em 2026-10-16: 16/17 frases certas, 0 falsos positivos, ~0,5 s por frase (o small leva 1,3 s)
NAME = re.compile(r"^\W*(?:(?:ei|oi|ok|ola|olá)\W+)?sarah?\b[\s,.!?]*", re.I)  # o nome no começo do que foi dito


class NameSpotter:
    """Gatilho "Sarah": separa trechos curtos de fala pelo volume e confere o começo com o Whisper.
    Fala longa (conversa, TV) nem é transcrita: poupa a CPU e evita acionar com "a Sarah disse que..." no meio."""
    MAX_FRAMES, END_QUIET = 40, 6  # até 3,2 s de fala; 0,48 s de silêncio encerra o trecho

    def __init__(self, transcribe: Callable[[np.ndarray], str]):
        self.transcribe = transcribe
        self.noise = 0.005
        self.reset()

    def reset(self) -> None:
        self.frames, self.quiet, self.spoken, self.skipping, self.prev = [], 0, 0, False, None

    def feed(self, frame: np.ndarray) -> tuple[str, np.ndarray] | None:
        """frame: float32 de 80 ms. Ao ouvir o nome, devolve (o que veio depois dele, áudio do trecho)."""
        rms = float(np.sqrt(np.mean(frame * frame)))
        loud = rms > max(2.5 * self.noise, 0.008)
        if not self.frames and not self.skipping:
            if not loud:
                self.noise = 0.95 * self.noise + 0.05 * rms
                self.prev = frame
                return None
            self.frames = [self.prev] if self.prev is not None else []  # guarda o começo da palavra
        self.quiet = 0 if loud else self.quiet + 1
        self.spoken += loud
        if self.skipping:
            if self.quiet >= self.END_QUIET:
                self.reset()
            return None
        self.frames.append(frame)
        if len(self.frames) > self.MAX_FRAMES + self.END_QUIET:
            self.frames, self.skipping = [], True
            return None
        if self.quiet < self.END_QUIET:
            return None
        spoken, audio = self.spoken, np.concatenate(self.frames)
        self.reset()
        if spoken < 3:  # menos de 240 ms alto (palma, porta): não é fala
            return None
        m = NAME.match(self.transcribe(audio))
        return (m.string[m.end():].strip(), audio) if m else None


@lru_cache(1)
def _spot_model():
    from faster_whisper import WhisperModel
    return WhisperModel(SPOT_MODEL, device="cpu", compute_type="int8", cpu_threads=4,
                        download_root=str(config.MODELS_DIR / "whisper"), local_files_only=True)


def spot_transcribe(audio: np.ndarray) -> str:
    segments, _ = _spot_model().transcribe(audio, language="pt", beam_size=1, condition_on_previous_text=False,
                                           without_timestamps=True, vad_filter=True, hotwords="Sarah")
    return " ".join(seg.text.strip() for seg in segments)


def question_after_name(audio: np.ndarray, rough: str) -> str:
    """"Sarah, que horas são?": transcreve de novo com o modelo maior (o base erra o resto da frase)."""
    from . import voice
    try:
        text = voice.transcribe(audio)
    except voice.VoiceUnavailable:
        return rough
    m = NAME.match(text)
    return text[m.end():].strip() if m else rough


def mic() -> int | None:
    """Microfone configurado: número, parte do nome ou padrão do Windows (None).
    O mesmo microfone aparece em vários sistemas de áudio; o primeiro da lista (MME) é o mais compatível."""
    value = db.get_setting("wake_device") or config.WAKE_DEVICE  # escolha feita em Voz (menu ☰) vale mais que o .env
    if value is None or value.isdigit():
        return int(value) if value else None
    import sounddevice as sd
    for i, d in enumerate(sd.query_devices()):
        if d["max_input_channels"] > 0 and value.lower() in d["name"].lower():
            return i
    raise ValueError(f"Microfone '{value}' não encontrado. Escolha outro em Voz → Microfone da escuta (menu ☰).")


def clap_params() -> tuple[float, float]:
    """(pico mínimo, destaque mínimo sobre o ruído): calibração salva em Voz (menu ☰), senão o .env/padrão."""
    saved = db.get_setting("clap")
    if saved:
        p = json.loads(saved)
        return float(p["min_peak"]), float(p["ratio"])
    return config.CLAP_MIN_PEAK, 6.0


def input_devices() -> list[str]:
    """Microfones (sem repetir o mesmo aparelho em vários sistemas de áudio do Windows)."""
    import sounddevice as sd
    mme = next((i for i, h in enumerate(sd.query_hostapis()) if "MME" in h["name"]), None)
    return [d["name"] for d in sd.query_devices()
            if d["max_input_channels"] > 0 and d["hostapi"] == mme and "Mapeador" not in d["name"] and "Mapper" not in d["name"]]


def spotter_available() -> bool:
    return any((config.MODELS_DIR / "whisper").glob(f"models--Systran--faster-whisper-{SPOT_MODEL}/snapshots/*/model.bin"))


class _Recording:
    """Uma pergunta falada: começa na primeira fala e termina em 0,8 s de silêncio (ou nos limites de tempo)."""
    END_QUIET = 10  # quadros de 80 ms

    def __init__(self, wait: float, max_seconds: float):
        self.wait, self.max_frames = wait, int(max_seconds * RATE / FRAME)
        self.frames: list[np.ndarray] = []
        self.heard, self.quiet = False, 0
        self.done = threading.Event()

    def feed(self, samples: np.ndarray, noise: float) -> None:
        self.frames.append(samples)
        loud = float(np.sqrt(np.mean(samples * samples))) > max(3 * noise, 0.01)
        self.heard |= loud
        self.quiet = 0 if loud else self.quiet + 1
        waited = len(self.frames) * FRAME / RATE
        if (self.heard and self.quiet >= self.END_QUIET) or (not self.heard and waited > self.wait) \
                or len(self.frames) >= self.max_frames:
            self.done.set()


class Listener:
    def __init__(self, on_wake: Callable[[str, str], None]):
        self.on_wake = on_wake  # (origem, texto dito junto com o nome)
        self.mode = "off"    # o que está rodando agora
        self.wanted = "off"  # o que o usuário escolheu (se o microfone sumir, a escuta volta sozinha quando ele reaparecer)
        self._lock = threading.Lock()
        self.muted_until = 0.0
        self.noise = 0.005  # ruído de fundo do microfone (para saber quando a pessoa parou de falar)
        self._recording: _Recording | None = None
        self.error = ""
        self._stream = None
        self._queue: queue.Queue = queue.Queue(maxsize=50)
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    def set_mode(self, mode: str) -> None:
        if mode not in MODES:
            raise ValueError(f"Modo inválido: {mode}")
        with self._lock:
            self.wanted = mode
            self._start(mode)

    def _start(self, mode: str) -> None:
        previous_error = self.error
        self.stop()
        self.error = ""
        if mode == "off":
            return
        if mode in ("palavra", "ambos") and not spotter_available():
            self.error = "Gatilho \"Sarah\" indisponível: rode .venv\\Scripts\\python.exe -m jarvis.listener (baixa ~145 MB)."
            if mode == "palavra":
                return
            mode = "palmas"
        try:
            import sounddevice as sd
            self._stream = sd.InputStream(samplerate=RATE, channels=1, dtype="int16", blocksize=FRAME,
                                          device=mic(), callback=self._callback)
            self._stream.start()
        except Exception as e:
            self._stream, self.error = None, f"Não consegui abrir o microfone do PC: {e}"
            if self.error != previous_error:  # a nova tentativa a cada 20 s não enche o log
                log.warning(self.error)
            return
        self.mode = mode
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, args=(mode,), daemon=True)
        self._thread.start()
        log.info("Escuta local ligada: %s", mode)

    def record(self, wait: float = 6, max_seconds: float = 15) -> np.ndarray | None:
        """Grava a pergunta pelo mesmo microfone da escuta (usado quando nenhuma página está aberta no PC).
        Devolve as amostras (float32, 16 kHz) ou None se ninguém falou."""
        if self.mode == "off":
            return None
        rec = _Recording(wait, max_seconds)
        self._recording = rec
        rec.done.wait(wait + max_seconds + 2)
        self._recording = None
        return np.concatenate(rec.frames) if rec.heard else None

    def mute(self, seconds: float) -> None:
        """Não acionar enquanto a própria Sarah fala pelas caixas de som (ela diz o próprio nome)."""
        self.muted_until = max(self.muted_until, time.monotonic()) + seconds

    def healthy(self) -> bool:
        """Está fazendo o que o usuário escolheu? (falso se o microfone sumiu, travou ou não abriu)"""
        return self.wanted == "off" or (self.mode != "off" and self._thread is not None and self._thread.is_alive())

    def recover(self) -> None:
        """Tenta de novo o modo escolhido (chamado periodicamente pelo servidor)."""
        with self._lock:
            if not self.healthy():
                self._start(self.wanted)
                if self.healthy():
                    log.info("Escuta local recuperada: o microfone voltou")

    def stop(self) -> None:
        if self._stream:
            with contextlib.suppress(Exception):  # microfone desconectado: fechar pode falhar, e tudo bem
                self._stream.stop()
                self._stream.close()
            self._stream = None
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=2)
            self._thread = None
        if self.mode != "off":
            log.info("Escuta local desligada")
        self.mode = "off"

    def _callback(self, indata, frames, time_info, status):
        with contextlib.suppress(queue.Full):  # análise atrasada: descarta o quadro em vez de acumular áudio
            self._queue.put_nowait(indata[:, 0].copy())

    def _run(self, mode: str) -> None:
        def frames():
            last = time.monotonic()
            while not self._stop.is_set():
                try:
                    yield self._queue.get(timeout=0.5)
                    last = time.monotonic()
                except queue.Empty:
                    if time.monotonic() - last > STALL_SECONDS:
                        raise RuntimeError("o microfone parou de mandar áudio (desconectado?)") from None
        try:
            self.process_frames(mode, frames())
        except Exception as e:
            self.error = f"A escuta local parou: {e}"
            log.exception("Falha na escuta local")

    def process_frames(self, mode: str, frames) -> None:
        """Separado do microfone para poder ser testado com áudio sintético."""
        spot = NameSpotter(spot_transcribe) if mode in ("palavra", "ambos") else None
        claps = ClapDetector(*clap_params()) if mode in ("palmas", "ambos") else None
        cooldown = 0
        for frame in frames:
            samples = frame.astype(np.float32) / 32768
            rec = self._recording
            if rec is not None and not rec.done.is_set():  # gravando uma pergunta: não procura acionamento
                rec.feed(samples, self.noise)
                continue
            if time.monotonic() < self.muted_until:
                if spot:
                    spot.reset()
                continue
            rms = float(np.sqrt(np.mean(samples * samples)))
            if rms < 3 * self.noise:
                self.noise = 0.98 * self.noise + 0.02 * rms
            source, text = None, ""
            heard = spot.feed(samples) if spot else None
            if heard:
                source, text = "palavra", question_after_name(heard[1], heard[0]) if heard[0] else ""
            if claps and claps.feed(samples):
                source = source or "palmas"
            if cooldown:
                cooldown -= 1
            elif source:
                cooldown = COOLDOWN_FRAMES
                log.info("Acionamento local: %s", source)
                self.on_wake(source, text)


def download() -> None:
    from faster_whisper import WhisperModel
    WhisperModel(SPOT_MODEL, device="cpu", compute_type="int8", download_root=str(config.MODELS_DIR / "whisper"))
    print("Modelo do gatilho \"Sarah\" pronto:", spotter_available())


def analyze(x: np.ndarray) -> dict:
    """Ruído de fundo e os estalos mais fortes de um trecho de áudio (float32 em -1..1), com sugestão de ajuste.
    Medido neste PC: ruído de 0,0156 no microfone bom; com o critério de 6x o ruído, palmas normais não passavam."""
    win = ClapDetector.WIN
    n = len(x) // win
    if n < 10:
        return {"ruido": 0.0, "estalos": [], "sugestao": None}
    w = x[:n * win].reshape(n, win)
    rms, peak = np.sqrt((w * w).mean(axis=1)), np.abs(w).max(axis=1)
    noise = float(np.median(rms)) or 1e-6
    spikes = []
    for i in np.argsort(-rms):  # do mais forte para o mais fraco, com 150 ms entre estalos
        if rms[i] < 3 * noise or len(spikes) >= 8:
            break
        if all(abs(i - j) >= 8 for j, _ in spikes):
            spikes.append((int(i), {"pico": round(float(peak[i]), 4), "destaque": round(float(rms[i] / noise), 1)}))
    found = [s for _, s in sorted(spikes)]
    suggestion = None
    if len(found) >= 2:
        strongest = sorted(found, key=lambda s: -s["destaque"])[:6]  # as palmas são os estalos mais fortes
        suggestion = {"min_peak": round(max(0.5 * float(np.median([s["pico"] for s in strongest])), 0.003), 3),
                      "ratio": round(float(np.clip(0.5 * np.median([s["destaque"] for s in strongest]), 3, 10)), 1)}
    return {"ruido": round(noise, 5), "estalos": found, "sugestao": suggestion}


def measure(seconds: float = 12) -> dict:
    """Ouve o microfone da escuta local por alguns segundos, só em memória, e analisa."""
    import sounddevice as sd
    rec = sd.rec(int(seconds * RATE), samplerate=RATE, channels=1, dtype="float32", device=mic())
    sd.wait()
    result = analyze(rec[:, 0])
    del rec
    result["microfone"] = sd.query_devices(mic(), "input")["name"]
    return result


if __name__ == "__main__":
    import sys
    if sys.argv[1:] == ["calibrar"]:
        print("Bata duas palmas, espere 2 s e bata mais duas (12 s)...", flush=True)
        print(measure())
    else:
        download()
