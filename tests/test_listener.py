"""Escuta local com áudio sintético (sem microfone real)."""
import numpy as np
import pytest

from jarvis import listener, voice

RATE = 16000
rng = np.random.default_rng(42)


def silence(sec, level=0.003):
    return (rng.standard_normal(int(RATE * sec)) * level).astype(np.float32)


def clap(amp=0.6):
    n = int(RATE * 0.05)
    env = np.exp(-np.arange(n) / (RATE * 0.008))  # decai em ~8 ms, como uma palma
    env[:32] *= np.linspace(0, 1, 32)  # subida de 2 ms
    return (rng.standard_normal(n) * env * amp).clip(-1, 1).astype(np.float32)


def seq(*parts):
    return np.concatenate([silence(0.5), *parts, silence(0.5)])


def count_triggers(audio, min_peak=0.2):
    det = listener.ClapDetector(min_peak=min_peak)
    return sum(det.feed(audio[i:i + listener.FRAME]) for i in range(0, len(audio), listener.FRAME))


def test_two_claps_trigger_once():
    assert count_triggers(seq(clap(), silence(0.35), clap())) == 1


def test_single_clap_does_not_trigger():
    assert count_triggers(seq(clap())) == 0


def test_claps_too_far_apart():
    assert count_triggers(seq(clap(), silence(1.2), clap())) == 0


def test_claps_too_close():
    assert count_triggers(seq(clap(), silence(0.05), clap())) == 0


def test_quiet_claps_below_threshold():
    assert count_triggers(seq(clap(0.05), silence(0.35), clap(0.05))) == 0


def test_sustained_tones_do_not_trigger():
    t = np.arange(int(RATE * 0.2)) / RATE
    beep = (0.5 * np.sin(2 * np.pi * 440 * t)).astype(np.float32)
    assert count_triggers(seq(beep, silence(0.3), beep, silence(0.3), beep)) == 0


@pytest.mark.skipif(not voice.status()["tts"], reason="Kokoro não baixado")
def test_loud_speech_does_not_trigger():
    samples, sr = voice._kokoro().create("Pá! Bate o pé, toca o tambor, tchau, pode parar, até já.",
                                         voice="pm_alex", lang="pt-br")
    speech = np.interp(np.linspace(0, len(samples) - 1, int(len(samples) * RATE / sr)), np.arange(len(samples)), samples)
    speech = (speech / np.abs(speech).max() * 0.9).astype(np.float32)  # o mais alto possível sem saturar
    assert count_triggers(seq(speech, silence(0.3), speech)) == 0


def frames_of(audio):
    pcm = (audio * 32767).astype(np.int16)
    return [pcm[i:i + listener.FRAME] for i in range(0, len(pcm) - listener.FRAME + 1, listener.FRAME)]


def test_listener_cooldown_and_callback():
    calls = []
    lst = listener.Listener(on_wake=lambda source, text="": calls.append(source))
    audio = seq(clap(), silence(0.35), clap(), silence(0.3), clap(), silence(0.35), clap())
    lst.process_frames("palmas", frames_of(audio))
    assert calls == ["palmas"]  # o segundo par cai dentro dos 3 s de espera


def test_muted_while_sarah_speaks():
    calls = []
    lst = listener.Listener(on_wake=lambda source, text="": calls.append(source))
    lst.mute(30)
    lst.process_frames("palmas", frames_of(seq(clap(), silence(0.35), clap())))
    assert calls == []


def voice_like(sec, amp=0.15):
    """'Fala' sintética: ruído modulado como sílabas (o transcritor é simulado nestes testes)."""
    t = np.arange(int(RATE * sec)) / RATE
    return (rng.standard_normal(len(t)) * amp * (0.6 + 0.4 * np.sin(2 * np.pi * 4 * t))).astype(np.float32)


def spot(audio, says):
    heard, calls = [], []

    def fake(a):
        calls.append(len(a) / RATE)
        return says
    s = listener.NameSpotter(fake)
    for f in frames_of(audio):
        r = s.feed(f.astype(np.float32) / 32768)
        if r:
            heard.append(r[0])
    return heard, calls


def test_name_spotter_short_phrases_only():
    heard, calls = spot(np.concatenate([silence(1), voice_like(0.6), silence(1)]), "Sarah.")
    assert heard == [""] and len(calls) == 1 and 0.6 <= calls[0] < 1.4  # só o trecho de fala (com sobras curtas)
    heard, _ = spot(np.concatenate([silence(1), voice_like(1.8), silence(1)]), "Sarah, que horas são?")
    assert heard == ["que horas são?"]
    heard, calls = spot(np.concatenate([silence(1), voice_like(6), silence(1)]), "Sarah")
    assert heard == [] and calls == []  # fala longa (conversa, TV) nem é transcrita
    heard, calls = spot(np.concatenate([silence(1), clap(), silence(1)]), "Sarah")
    assert calls == []  # estalo curto não é fala
    heard, calls = spot(silence(3), "Sarah")
    assert calls == []


def test_name_must_open_the_phrase():
    for text, want in [("Sarah", ""), ("Sara!", ""), ("Oi, Sarah.", ""), ("Ei Sarah, abre o YouTube", "abre o YouTube"),
                       ("A Sarah chegou", None), ("Sarinha", None), ("Sala de estar", None), ("Será que chove?", None)]:
        m = listener.NAME.match(text)
        assert (text[m.end():].strip() if m else None) == want, text


@pytest.mark.skipif(not (listener.spotter_available() and voice.status()["stt"] and voice.status()["tts"]),
                    reason="modelos de voz não baixados")
def test_real_models_hear_sarah_and_the_question():
    samples, sr = voice._kokoro().create("Sarah, que horas são?", voice="pf_dora", lang="pt-br")
    a = np.interp(np.linspace(0, len(samples) - 1, int(len(samples) * RATE / sr)), np.arange(len(samples)), samples)
    calls = []
    listener.Listener(on_wake=lambda source, text="": calls.append((source, text))).process_frames(
        "palavra", frames_of(np.concatenate([silence(1), a.astype(np.float32), silence(1.5)])))
    assert len(calls) == 1 and calls[0][0] == "palavra" and "horas" in calls[0][1].lower()


def test_invalid_mode_rejected():
    with pytest.raises(ValueError):
        listener.Listener(on_wake=print).set_mode("sempre")


# ---------- API ----------
import sys

from fastapi.testclient import TestClient

from jarvis import auth
from jarvis.main import app, local_clients

from .conftest import ORIGIN, PASSWORD, WS


class FakeStream:
    def __init__(self, **kwargs):
        self.started = False

    def start(self):
        self.started = True

    def stop(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_mic(monkeypatch):
    monkeypatch.setitem(sys.modules, "sounddevice", type(sys)("sounddevice"))
    sys.modules["sounddevice"].InputStream = FakeStream


def test_wake_status_default_off(logged):
    w = logged.get("/api/wake").json()
    assert w["mode"] == "off" and w["can_change"] is True and w["available"]["palmas"] is True


def test_wake_mode_change_local(logged, fake_mic):
    assert logged.post("/api/wake", json={"mode": "palmas"}).json()["mode"] == "palmas"
    assert logged.get("/api/status").json()["wake"] == "palmas"
    assert logged.post("/api/wake", json={"mode": "off"}).json()["mode"] == "off"
    actions = [a["action"] for a in logged.get("/api/audit").json()]
    assert actions.count("escuta_local") == 2


def test_wake_invalid_mode(logged):
    assert logged.post("/api/wake", json={"mode": "sempre"}).status_code == 422


def test_remote_session_cannot_enable_pc_mic(client, fake_mic):
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.post("/api/wake", json={"mode": "palmas"}).status_code == 403
    assert client.get("/api/wake").json()["can_change"] is False


def test_wake_event_reaches_local_ui(logged):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": ""})
        ws.receive_json()  # garante que o servidor já registrou a conexão
        app.state.listener.on_wake("palmas")
        assert ws.receive_json() == {"type": "wake", "source": "palmas"}
    assert not local_clients


def test_remote_ui_does_not_receive_wake(client):
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    with client.websocket_connect(WS, headers={"origin": ORIGIN}) as ws:
        ws.send_json({"type": "chat", "text": ""})
        assert ws.receive_json()["type"] == "error"  # garante que o servidor já processou a conexão
        assert not local_clients


def test_wake_mode_survives_restart(logged, fake_mic):
    assert logged.post("/api/wake", json={"mode": "palmas"}).json()["mode"] == "palmas"
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as restarted:  # novo lifespan
        restarted.post("/api/login", json={"password": PASSWORD})
        assert restarted.get("/api/wake").json()["mode"] == "palmas"
        restarted.post("/api/wake", json={"mode": "off"})


# ---------- Calibração das palmas ----------

def test_calibration_suggests_settings_that_catch_weak_claps():
    """Palmas fracas que o ajuste padrão (0,2 / 6x) perde passam a ser reconhecidas com a sugestão."""
    def noisy(sec):
        return silence(sec, level=0.005)
    pair = [clap(0.06), noisy(0.35), clap(0.06)]
    audio = np.concatenate([noisy(1), *pair, noisy(2), *pair, noisy(1)])
    r = listener.analyze(audio)
    assert len(r["estalos"]) >= 4 and r["sugestao"]
    assert count_triggers(audio) == 0  # ajuste padrão
    det = listener.ClapDetector(r["sugestao"]["min_peak"], r["sugestao"]["ratio"])
    assert sum(det.feed(audio[i:i + listener.FRAME]) for i in range(0, len(audio), listener.FRAME)) == 2


def test_calibration_silent_or_no_claps():
    assert listener.analyze(np.zeros(RATE * 12, dtype=np.float32))["sugestao"] is None  # microfone mudo
    assert listener.analyze(silence(12))["sugestao"] is None


def test_measure_uses_chosen_mic(monkeypatch, fake_mic):
    sd = sys.modules["sounddevice"]
    sd.query_devices = lambda *a: ({"name": "Microfone (High Definition Audio)"} if a
                                   else [{"name": "Microfone (2- USB Audio)", "max_input_channels": 1},
                                         {"name": "Microfone (High Definition Audio)", "max_input_channels": 2}])
    used = {}

    def rec(n, **kw):
        used["device"] = kw["device"]
        return seq(clap(), silence(0.35), clap()).reshape(-1, 1)
    sd.rec, sd.wait = rec, lambda: None
    from jarvis import db
    db.set_setting("wake_device", "High Definition")
    r = listener.measure()
    assert used["device"] == 1 and r["microfone"] == "Microfone (High Definition Audio)" and len(r["estalos"]) == 2


def test_wake_settings_api(logged, fake_mic, monkeypatch):
    w = logged.get("/api/wake").json()
    assert w["clap"] == {"min_peak": 0.2, "ratio": 6.0} and w["device"] == ""
    w = logged.post("/api/wake/settings", json={"device": "High Definition", "min_peak": 0.05, "ratio": 3.5}).json()
    assert w["device"] == "High Definition" and listener.clap_params() == (0.05, 3.5)
    assert logged.post("/api/wake/settings", json={"min_peak": 5, "ratio": 3}).status_code == 422
    monkeypatch.setattr(listener, "measure", lambda s: {"ruido": 0.01, "estalos": [], "sugestao": None, "microfone": "X"})
    logged.post("/api/wake/settings", json={"device": ""})  # volta ao padrão (o sounddevice falso não lista aparelhos)
    logged.post("/api/wake", json={"mode": "palmas"})
    assert logged.post("/api/wake/calibrate").json()["microfone"] == "X"
    assert logged.get("/api/wake").json()["mode"] == "palmas"  # a escuta volta depois da medição
    logged.post("/api/wake", json={"mode": "off"})
    actions = [a["action"] for a in logged.get("/api/audit").json()]
    assert {"escuta_ajustada", "palmas_calibradas"} <= set(actions)


def test_phone_cannot_calibrate_or_change_mic(client):
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.post("/api/wake/calibrate").status_code == 403
    assert client.post("/api/wake/settings", json={"device": "X"}).status_code == 403
    assert "devices" not in client.get("/api/wake").json()


def test_wake_with_question_reaches_local_ui(logged):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": ""})
        ws.receive_json()
        app.state.listener.on_wake("palavra", "que horas são?")
        assert ws.receive_json() == {"type": "wake", "source": "palavra", "text": "que horas são?"}


def test_tts_on_pc_mutes_listener_but_phone_does_not(logged, client, monkeypatch):
    import io
    import time
    import soundfile as sf
    from jarvis import voice as v
    buf = io.BytesIO()
    sf.write(buf, np.zeros(24000 * 2, np.float32), 24000, format="WAV", subtype="PCM_16")  # 2 s de fala
    monkeypatch.setattr(v, "synthesize", lambda *a: buf.getvalue())
    app.state.listener.muted_until = 0
    assert logged.post("/api/tts", json={"text": "Oi, eu sou a Sarah."}).status_code == 200
    assert 2.5 < app.state.listener.muted_until - time.monotonic() < 3.5
    app.state.listener.muted_until = 0
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.post("/api/tts", json={"text": "Oi."}).status_code == 200  # toca no celular, não nas caixas do PC
    assert app.state.listener.muted_until == 0


# ---------- Microfone que some, volta ou trava ----------

def test_listener_recovers_when_mic_comes_back(fake_mic, monkeypatch):
    """O microfone escolhido sumiu do Windows: avisa, e volta a ouvir sozinho quando ele reaparece."""
    from jarvis import db
    sd = sys.modules["sounddevice"]
    devices = []
    sd.query_devices = lambda *a: devices
    db.set_setting("wake_device", "High Definition")
    lst = listener.Listener(on_wake=lambda *a: None)
    lst.set_mode("palmas")
    assert lst.mode == "off" and lst.wanted == "palmas" and not lst.healthy() and "não encontrado" in lst.error
    lst.recover()  # ainda sem o microfone
    assert not lst.healthy()
    devices.append({"name": "Microfone (High Definition Audio)", "max_input_channels": 2})
    lst.recover()
    assert lst.healthy() and lst.mode == "palmas" and lst.error == ""
    lst.set_mode("off")
    assert lst.healthy()  # desligada de propósito também é "saudável"


def test_listener_notices_a_frozen_mic(fake_mic, monkeypatch):
    """Sem áudio nenhum por alguns segundos (cabo solto, driver travado): a escuta para e marca erro para ser reaberta."""
    import time
    monkeypatch.setattr(listener, "STALL_SECONDS", 0.6)
    lst = listener.Listener(on_wake=lambda *a: None)
    lst.set_mode("palmas")  # o FakeStream nunca manda áudio
    assert lst.healthy()
    time.sleep(1.8)
    assert not lst.healthy() and "parou de mandar áudio" in lst.error
    lst.set_mode("off")


def test_status_reports_listener_problem(logged, fake_mic):
    from jarvis import db
    sys.modules["sounddevice"].query_devices = lambda *a: []
    db.set_setting("wake_device", "Inexistente")
    logged.post("/api/wake", json={"mode": "palmas"})
    s = logged.get("/api/status").json()
    assert s["wake"] == "off" and s["wake_wanted"] == "palmas" and "não encontrado" in s["wake_error"]
    logged.post("/api/wake", json={"mode": "off"})
