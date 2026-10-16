"""Sarah sem a página aberta no PC: ouve, responde e fala pelas caixas de som; e a inicialização com o Windows."""
import asyncio
import io

import numpy as np
import pytest
import soundfile as sf

from jarvis import autostart, auth, db, llm, main, voice

from .conftest import PASSWORD


@pytest.fixture
def speaker(monkeypatch, fake_llm):
    """Fala e microfone simulados: registra o que seria falado nas caixas de som."""
    spoken = []
    buf = io.BytesIO()
    sf.write(buf, np.zeros(2400, np.float32), 24000, format="WAV")
    monkeypatch.setattr(voice, "synthesize", lambda text, *a: spoken.append(text) or buf.getvalue())
    monkeypatch.setattr(voice, "play", lambda wav: 0.1)
    monkeypatch.setattr(voice, "beep", lambda: spoken.append("<bipe>"))
    return spoken


def run_hands_free(text=""):
    async def go():
        main.app.state.listener = main.listener.Listener(on_wake=lambda *a: None)
        await main.hands_free(text)
    asyncio.run(go())


def test_question_said_with_the_name_is_answered_out_loud(speaker):
    run_hands_free("Sarah, tudo bem?")
    assert speaker == ["Olá, tudo bem?"]  # resposta falada (o modelo simulado responde "Olá, tudo bem?")
    rows = db.query("select role, content from messages order by id")
    assert rows[0] == {"role": "user", "content": "Sarah, tudo bem?"} and rows[-1]["role"] == "assistant"
    assert not main.TASKS and main._hands_free_busy is False
    assert "maos_livres" in [a["action"] for a in db.query("select action from audit")]


def test_name_alone_listens_then_answers(speaker, monkeypatch):
    monkeypatch.setattr(main.listener.Listener, "record", lambda self, *a: np.ones(16000, np.float32))
    monkeypatch.setattr(voice, "transcribe", lambda audio: "que horas são?")
    run_hands_free()
    assert speaker[0] == "<bipe>" and speaker[1] == "Olá, tudo bem?"
    assert db.query("select content from messages where role = 'user'")[0]["content"] == "que horas são?"


def test_silence_after_the_name_does_nothing(speaker, monkeypatch):
    monkeypatch.setattr(main.listener.Listener, "record", lambda self, *a: None)
    run_hands_free()
    assert speaker == ["<bipe>"] and not db.query("select 1 from messages")


def test_long_answers_are_spoken_sentence_by_sentence(speaker, monkeypatch):
    async def chat(messages, tools=None):
        for t in ["Primeira frase. Segunda ", "frase! Terceira **com** markdown"]:
            yield {"type": "token", "text": t}
    monkeypatch.setattr(llm, "chat", chat)
    run_hands_free("conta três frases")
    assert speaker == ["Primeira frase.", "Segunda frase!", "Terceira com markdown"]


def test_wake_without_pc_page_goes_hands_free(monkeypatch):
    calls = []

    async def fake(text=""):
        calls.append(text)
    monkeypatch.setattr(main, "hands_free", fake)

    async def go():
        await main.broadcast_wake("palavra", "que horas são?")
        await asyncio.sleep(0)
    main.local_clients.clear()
    asyncio.run(go())
    assert calls == ["que horas são?"]


def test_conversation_continues_within_30_minutes(speaker):
    old = db.execute("insert into conversations(title) values ('antiga')")
    db.execute("insert into messages(conversation_id, role, content, created_at) values (?, 'user', 'x', datetime('now', '-2 hours'))", (old,))
    recent = db.execute("insert into conversations(title) values ('recente')")
    db.execute("insert into messages(conversation_id, role, content) values (?, 'user', 'oi')", (recent,))
    assert main._recent_conversation() == recent
    db.execute("update messages set created_at = datetime('now', '-1 hour')")
    assert main._recent_conversation() is None  # muito tempo parada: conversa nova


def test_autostart_toggle(logged, client, tmp_path, monkeypatch):
    monkeypatch.setattr(autostart, "STARTUP", tmp_path / "Inicializar")
    assert logged.get("/api/autostart").json() == {"ligado": False, "can_change": True}
    assert logged.post("/api/autostart", json={"ligar": True}).json()["ligado"] is True
    assert (tmp_path / "Inicializar" / autostart.LINK_NAME).is_file()  # atalho de verdade, criado pelo Windows
    assert logged.post("/api/autostart", json={"ligar": False}).json()["ligado"] is False
    assert not (tmp_path / "Inicializar" / autostart.LINK_NAME).exists()
    assert "inicio_automatico" in [a["action"] for a in logged.get("/api/audit").json()]
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.post("/api/autostart", json={"ligar": True}).status_code == 403
