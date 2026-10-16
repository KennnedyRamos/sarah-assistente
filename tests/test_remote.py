"""Fase 7: tarefas visíveis entre aparelhos, aprovações remotas, limite de requisições e Tailscale."""
import asyncio

import pytest
from fastapi.testclient import TestClient

from jarvis import config, llm, remote, tools
from jarvis import main as jarvis_main
from jarvis.main import app

from .conftest import ORIGIN, PASSWORD, WS


@pytest.fixture
def phone(logged):
    """Segunda sessão, vinda pelo Tailscale (cabeçalho de encaminhamento). Depende de logged (senha definida)."""
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as c:
        c.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.7"})
        assert c.get("/api/me").json()["remote"] is True
        yield c


@pytest.fixture
def slow_llm(monkeypatch):
    async def chat(messages, tools_=None):
        yield {"type": "token", "text": "pensando"}
        await asyncio.sleep(30)
        yield {"type": "token", "text": "nunca"}
    monkeypatch.setattr(llm, "chat", chat)


@pytest.fixture
def trash_llm(monkeypatch):
    tools.save_settings("normal", [])
    monkeypatch.setattr(tools, "send_to_recycle_bin", lambda p: None)
    (tools.workspace() / "a.txt").write_text("x")

    async def chat(messages, tools_=None):
        if messages[-1]["role"] == "tool":
            yield {"type": "token", "text": messages[-1]["content"][:30]}
        else:
            yield {"type": "tool_calls", "calls": [{"function": {"name": "mover_para_lixeira", "arguments": {"caminho": "a.txt"}}}]}
    monkeypatch.setattr(llm, "chat", chat)


def test_task_visible_and_stoppable_from_phone(logged, phone, slow_llm):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "Tarefa longa"})
        start = ws.receive_json()
        assert start["type"] == "start" and start["task_id"]
        ws.receive_json()  # token
        tasks = phone.get("/api/tasks").json()
        assert [(t["text"], t["origin"]) for t in tasks] == [("Tarefa longa", "local")]
        assert phone.post(f"/api/tasks/{tasks[0]['id']}/stop").status_code == 200
        assert ws.receive_json()["interrupted"] is True
    assert phone.get("/api/tasks").json() == []


def test_approval_answered_from_other_device(logged, trash_llm):
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as pc2:
        pc2.post("/api/login", json={"password": PASSWORD})
        with logged.websocket_connect(WS) as ws:
            ws.send_json({"type": "chat", "text": "Apague a.txt"})
            while (ev := ws.receive_json())["type"] != "approval":
                pass
            pending = pc2.get("/api/tasks").json()[0]["approvals"]
            assert [a["id"] for a in pending] == [ev["id"]] and "a.txt" in pending[0]["summary"]
            assert pc2.post(f"/api/approvals/{ev['id']}", json={"ok": False}).status_code == 200
            assert ws.receive_json() == {"type": "approval_closed", "id": ev["id"], "ok": False}
            end = ws.receive_json()
            assert end["type"] == "tool_end" and end["ok"] is False


def test_phone_can_reject_but_not_approve_by_default(logged, phone, trash_llm):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "Apague a.txt"})
        while (ev := ws.receive_json())["type"] != "approval":
            pass
        r = phone.post(f"/api/approvals/{ev['id']}", json={"ok": True})
        assert r.status_code == 403 and "JARVIS_REMOTE_TOOLS_ALL" in r.json()["detail"]
        assert phone.post(f"/api/approvals/{ev['id']}", json={"ok": False}).status_code == 200
        assert ws.receive_json()["ok"] is False


def test_phone_can_approve_when_enabled(logged, phone, trash_llm, monkeypatch):
    monkeypatch.setattr(config, "REMOTE_TOOLS_ALL", True)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "Apague a.txt"})
        while (ev := ws.receive_json())["type"] != "approval":
            pass
        assert phone.post(f"/api/approvals/{ev['id']}", json={"ok": True}).status_code == 200
        assert ws.receive_json()["ok"] is True


def test_answering_unknown_or_finished_approval(logged):
    assert logged.post("/api/approvals/naoexiste", json={"ok": True}).status_code == 404
    assert logged.post("/api/tasks/naoexiste/stop").status_code == 404


def test_tasks_and_approvals_require_session(client):
    assert client.get("/api/tasks").status_code == 401
    assert client.post("/api/approvals/x", json={"ok": True}).status_code == 401
    assert client.get("/api/remote").status_code == 401


def test_rate_limit(logged, monkeypatch):
    monkeypatch.setattr(jarvis_main, "RATE_LIMIT", 5)
    jarvis_main._hits.clear()  # o login da fixture também conta
    codes = [logged.get("/api/me").status_code for _ in range(7)]
    assert codes[:5] == [200] * 5 and codes[5:] == [429, 429]
    assert logged.get("/").status_code == 200  # a página em si não é limitada


def test_tailnet_host_allowed_after_detection(logged, monkeypatch):
    name = "meupc.tail1234.ts.net"
    assert logged.get("/api/me", headers={"host": name}).status_code == 400
    monkeypatch.setattr(remote, "status", lambda: {"installed": True, "online": True, "name": name,
                                                   "url": f"https://{name}", "serving": True})
    monkeypatch.setattr(config, "ALLOWED_HOSTS", set(config.ALLOWED_HOSTS))
    r = logged.get("/api/remote").json()
    assert r["serving"] and r["remote_tools_all"] is False
    assert logged.get("/api/me", headers={"host": name}).status_code == 200


def test_remote_status_without_tailscale(monkeypatch):
    monkeypatch.setattr(remote, "TAILSCALE", "C:\\nao\\existe\\tailscale.exe")
    assert remote.status() == {"installed": False, "online": False}


def test_wake_listening_still_local_only(phone):
    assert phone.post("/api/wake", json={"mode": "palmas"}).status_code == 403
