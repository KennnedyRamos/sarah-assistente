import os

os.environ["JARVIS_NO_DOTENV"] = "1"  # antes de importar o jarvis: testes não dependem do .env do usuário

import pytest
from fastapi.testclient import TestClient

from jarvis import auth, config, db, llm
from jarvis import main as jarvis_main
from jarvis.main import app

ORIGIN = "http://localhost:8765"
WS = "ws://localhost:8765/ws/chat"  # URL completa: o TestClient ignora base_url no WebSocket
PASSWORD = "senha-de-teste-123"


@pytest.fixture(autouse=True)
def isolated(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "DATA_DIR", tmp_path)
    monkeypatch.setattr(jarvis_main.remote, "status", lambda: {"installed": False, "online": False})
    auth._failures.clear()
    jarvis_main._hits.clear()
    db.init()


@pytest.fixture
def fake_llm(monkeypatch):
    """Substitui o Ollama: registra as mensagens recebidas e responde com tokens fixos."""
    calls = []

    async def chat(messages, tools=None):
        calls.append(messages)
        for t in ["Olá", ", ", "tudo bem?"]:
            yield {"type": "token", "text": t}

    monkeypatch.setattr(llm, "chat", chat)
    return calls


@pytest.fixture
def client():
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as c:
        yield c


@pytest.fixture
def logged(client):
    auth.set_password(PASSWORD)
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 200
    return client
