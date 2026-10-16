from .conftest import WS
from jarvis import memory


def test_memory_crud(logged):
    mid = logged.post("/api/memories", json={"content": "Prefiro respostas curtas."}).json()["id"]
    assert [m["content"] for m in logged.get("/api/memories").json()] == ["Prefiro respostas curtas."]
    assert logged.put(f"/api/memories/{mid}", json={"content": "Prefiro respostas longas."}).status_code == 200
    assert logged.get("/api/memories").json()[0]["content"] == "Prefiro respostas longas."
    assert logged.delete(f"/api/memories/{mid}").status_code == 200
    assert logged.get("/api/memories").json() == []
    assert logged.delete(f"/api/memories/{mid}").status_code == 404


def test_memory_validation(logged):
    assert logged.post("/api/memories", json={"content": ""}).status_code == 422
    assert logged.post("/api/memories", json={"content": "x" * 2001}).status_code == 422


def test_memory_persists_across_connections(logged):
    memory.add("Meu time é o Bahia.")
    # nova conexão SQLite em cada chamada: se aparece aqui, está no disco
    assert memory.list_all()[0]["content"] == "Meu time é o Bahia."


def test_relevant_returns_all_when_few():
    memory.add("Gosto de café sem açúcar.")
    assert len(memory.relevant("qualquer coisa")) == 1


def test_relevant_searches_when_many():
    for i in range(memory.INJECT_ALL_UP_TO):
        memory.add(f"Anotação genérica número {i}.")
    memory.add("Meu aniversário é em 12 de março.")
    found = memory.relevant("Quando é meu aniversário?")
    assert found[0]["content"] == "Meu aniversário é em 12 de março."
    assert len(found) <= 5


def test_relevant_ignores_fts_syntax():
    for i in range(memory.INJECT_ALL_UP_TO + 1):
        memory.add(f"nota {i}")
    # aspas, parênteses e operadores do FTS5 não podem quebrar a busca
    assert memory.relevant('"OR" (AND) NEAR* ^ -') == []
    assert len(memory.relevant('nota " OR 1=1 --')) == 5


def test_history_list_and_delete(logged, fake_llm):
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": "Primeira conversa"})
        while ws.receive_json()["type"] != "done":
            pass
    convs = logged.get("/api/conversations").json()
    assert [c["title"] for c in convs] == ["Primeira conversa"]
    cid = convs[0]["id"]
    assert len(logged.get(f"/api/conversations/{cid}/messages").json()) == 2
    assert logged.delete(f"/api/conversations/{cid}").status_code == 200
    assert logged.get(f"/api/conversations/{cid}/messages").json() == []  # cascata
    assert logged.get("/api/conversations").json() == []


def test_wipe_all_history(logged, fake_llm):
    for text in ["um", "dois"]:
        with logged.websocket_connect(WS) as ws:
            ws.send_json({"type": "chat", "conversation_id": None, "text": text})
            while ws.receive_json()["type"] != "done":
                pass
    assert logged.delete("/api/conversations").json() == {"deleted": 2}
    actions = [a["action"] for a in logged.get("/api/audit").json()]
    assert "historico_apagado" in actions
