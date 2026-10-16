import asyncio

import pytest
from starlette.websockets import WebSocketDisconnect

from .conftest import WS
from jarvis import db, llm, memory


def collect(ws):
    events = []
    while True:
        ev = ws.receive_json()
        events.append(ev)
        if ev["type"] in ("done", "error"):
            return events


def test_ws_requires_session(client):
    with pytest.raises(WebSocketDisconnect) as e:
        with client.websocket_connect(WS) as ws:
            ws.receive_json()
    assert e.value.code == 4401


def test_ws_rejects_foreign_origin(logged):
    with pytest.raises(WebSocketDisconnect) as e:
        with logged.websocket_connect(WS, headers={"origin": "http://evil.example"}) as ws:
            ws.receive_json()
    assert e.value.code == 1008


def test_chat_streams_and_persists(logged, fake_llm):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Oi"})
        events = collect(ws)
    assert events[0]["type"] == "start"
    assert "".join(e["text"] for e in events if e["type"] == "token") == "Olá, tudo bem?"
    assert events[-1] == {"type": "done", "conversation_id": events[0]["conversation_id"], "interrupted": False}
    rows = db.query("select role, content from messages order by id")
    assert rows == [{"role": "user", "content": "Oi"}, {"role": "assistant", "content": "Olá, tudo bem?"}]


def test_context_includes_history_and_memory(logged, fake_llm):
    memory.add("O usuário se chama Kennedy.")
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Primeira"})
        cid = collect(ws)[0]["conversation_id"]
        ws.send_json({"type": "chat", "conversation_id": cid, "text": "Segunda"})
        collect(ws)
    sent = fake_llm[-1]
    assert sent[0]["role"] == "system" and "O usuário se chama Kennedy." in sent[0]["content"]
    assert [m["content"] for m in sent[1:]] == ["Primeira", "Olá, tudo bem?", "Segunda"]


def test_stop_interrupts_and_saves_partial(logged, monkeypatch):
    async def slow_chat(messages, tools=None):
        yield {"type": "token", "text": "Começando"}
        await asyncio.sleep(30)
        yield {"type": "token", "text": " nunca chega"}

    monkeypatch.setattr(llm, "chat", slow_chat)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Fale muito"})
        assert ws.receive_json()["type"] == "start"
        assert ws.receive_json() == {"type": "token", "text": "Começando"}
        ws.send_json({"type": "stop"})
        assert ws.receive_json()["interrupted"] is True
    assert db.query("select content from messages where role='assistant'")[0]["content"] == "Começando [interrompido]"


def test_llm_failure_reported(logged, monkeypatch):
    async def broken(messages, tools=None):
        raise llm.LLMError("Não consegui falar com o Ollama")
        yield  # pragma: no cover

    monkeypatch.setattr(llm, "chat", broken)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Oi"})
        events = collect(ws)
    assert events[-1] == {"type": "error", "message": "Não consegui falar com o Ollama"}


def test_message_limits(logged, fake_llm):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "   "})
        assert ws.receive_json()["type"] == "error"
        ws.send_json({"type": "chat", "text": "x" * 8001})
        assert ws.receive_json()["type"] == "error"


def test_revoked_session_closes_ws(logged, fake_llm):
    with logged.websocket_connect(WS) as ws:
        db.execute("delete from sessions")
        ws.send_json({"type": "chat", "text": "Oi"})
        with pytest.raises(WebSocketDisconnect) as e:
            ws.receive_json()
    assert e.value.code == 4401


def test_ollama_offline_status(logged, monkeypatch):
    monkeypatch.setattr("jarvis.config.LLM_URL", "http://127.0.0.1:1")  # porta sem servidor
    assert logged.get("/api/status").json()["llm"]["online"] is False


def test_unreachable_ollama_gives_clear_error(logged, monkeypatch):
    monkeypatch.setattr("jarvis.config.LLM_URL", "http://127.0.0.1:1")
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "Oi"})
        events = collect(ws)
    assert events[-1]["type"] == "error" and "Ollama" in events[-1]["message"]


def test_malformed_messages_keep_connection(logged, fake_llm):
    """JSON inválido ou que não é objeto: avisa e a conversa continua na mesma conexão."""
    with logged.websocket_connect(WS) as ws:
        ws.send_text("{isto não é json")
        assert ws.receive_json() == {"type": "error", "message": "Mensagem inválida."}
        ws.send_json(["lista", "em vez de objeto"])
        assert ws.receive_json()["message"] == "Mensagem inválida."
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Oi"})
        assert collect(ws)[-1]["type"] == "done"


def test_tool_only_round_leaves_no_empty_bubble(logged, monkeypatch):
    """Rodada só de ferramenta (sem texto) não grava mensagem vazia da Sarah no histórico."""
    rounds = iter([[{"type": "tool_calls", "calls": [{"function": {"name": "data_hora", "arguments": {}}}]}],
                   [{"type": "token", "text": "São 10h."}]])

    async def chat(messages, tools=None):
        for ev in next(rounds):
            yield ev
    monkeypatch.setattr(llm, "chat", chat)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Que horas são?"})
        collect(ws)
    roles = [r["role"] for r in db.query("select role, content from messages order by id") if r["content"]]
    assert roles == ["user", "tool", "assistant"]
    assert not db.query("select 1 from messages where role = 'assistant' and content = ''")


def test_ollama_dropping_mid_answer_gives_clear_error(logged, monkeypatch):
    import httpx

    class Dropping:
        def __init__(self, *a, **kw):
            pass

        async def __aenter__(self):
            raise httpx.RemoteProtocolError("peer closed connection")

        async def __aexit__(self, *a):
            return False
    monkeypatch.setattr(llm.httpx, "AsyncClient", Dropping)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Oi"})
        events = collect(ws)
    assert events[-1]["type"] == "error" and "caiu" in events[-1]["message"]
