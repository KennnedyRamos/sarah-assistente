"""Visão: imagens enviadas pelo 📎 vão ao modelo (reduzidas) e a ferramenta olhar_camera analisa uma foto da câmera."""
import asyncio
import base64

import cv2
import numpy as np
import pytest

from jarvis import config, llm, tools, vision

from .conftest import WS


def png(w=3000, h=2000) -> bytes:
    img = np.zeros((h, w, 3), np.uint8)
    cv2.putText(img, "SARAH", (50, h // 2), cv2.FONT_HERSHEY_SIMPLEX, 8, (255, 255, 255), 12)
    return cv2.imencode(".png", img)[1].tobytes()


def size_of(b64: str) -> tuple[int, int]:
    img = cv2.imdecode(np.frombuffer(base64.b64decode(b64), np.uint8), cv2.IMREAD_COLOR)
    return img.shape[1], img.shape[0]


def test_images_are_reduced_for_speed():
    assert size_of(vision.encode(cv2.imdecode(np.frombuffer(png(), np.uint8), cv2.IMREAD_COLOR))) == (1024, 683)
    small = cv2.imdecode(np.frombuffer(png(400, 300), np.uint8), cv2.IMREAD_COLOR)
    assert size_of(vision.encode(small)) == (400, 300)  # imagem pequena não é ampliada


def test_only_recent_images_go_to_the_model():
    folder = tools.workspace() / "arquivos"
    folder.mkdir()
    for i in range(3):
        (folder / f"foto{i}.png").write_bytes(png(800, 600))
    (folder / "nota.txt").write_text("x")
    msgs = [{"role": "user", "content": f"📎 Imagem enviada: arquivos\\foto{i}.png\nO que é?"} for i in range(3)]
    msgs += [{"role": "user", "content": "📎 Arquivo enviado: arquivos\\nota.txt\nleia"},
             {"role": "user", "content": "📎 Imagem enviada: arquivos\\sumiu.png\noi"},
             {"role": "user", "content": "📎 Imagem enviada: C:\\Windows\\fora.png\noi"}]
    vision.attach(msgs)
    assert [bool(m.get("images")) for m in msgs] == [False, True, True, False, False, False]


def test_chat_sends_uploaded_image_to_the_model(logged, monkeypatch):
    seen = []

    async def chat(messages, tools=None):
        seen.append(messages)
        yield {"type": "token", "text": "Vejo a palavra SARAH."}
    monkeypatch.setattr(llm, "chat", chat)
    path = logged.post("/api/files?nome=print.png", content=png(1200, 800)).json()["caminho"]
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "conversation_id": None, "text": f"📎 Imagem enviada: {path}\nO que está escrito?"})
        while ws.receive_json()["type"] != "done":
            pass
    last_user = [m for m in seen[0] if m["role"] == "user"][-1]
    assert len(last_user["images"]) == 1 and size_of(last_user["images"][0]) == (1024, 683)
    assert "vê diretamente" in seen[0][0]["content"]  # instrução no prompt de sistema
    assert logged.get("/api/files/print.png").status_code == 200  # miniatura na conversa
    assert logged.get("/api/files/..%5Cjarvis.db").status_code in (400, 404)
    assert logged.get("/api/files/nota.txt").status_code == 400  # só imagens


def ctx(remote=False, device=None):
    async def emit(ev):
        pass

    async def no(*a):
        return False
    return tools.Context(remote=remote, emit=emit, approve=no, device=device)


@pytest.fixture
def fake_describe(monkeypatch):
    asked = []

    async def describe(b64, question):
        asked.append((size_of(b64), question))
        return "Uma mesa com um caderno aberto."
    monkeypatch.setattr(vision, "describe", describe)
    return asked


def test_look_through_pc_camera(monkeypatch, fake_describe):
    from jarvis import camera
    monkeypatch.setattr(camera, "pc_frames", lambda n: [np.full((480, 640, 3), 3, np.uint8)])  # webcam no escuro
    ok, out = asyncio.run(tools.execute("olhar_camera", {"origem": "pc", "pergunta": "O que tem na mesa?"}, ctx()))
    assert ok and "caderno" in out and "não foi salva" in out
    assert fake_describe == [((640, 480), "O que tem na mesa?")]
    ok, out = asyncio.run(tools.execute("olhar_camera", {"origem": "pc"}, ctx(remote=True)))
    assert not ok and "JARVIS_REMOTE_CAMERA" in out  # câmera do PC pelo celular continua exigindo a opção


def test_look_through_phone_camera(fake_describe):
    photo = base64.b64encode(cv2.imencode(".jpg", np.zeros((768, 1024, 3), np.uint8))[1].tobytes()).decode()
    asked = []

    async def device(target, kind):
        asked.append((target, kind))
        return {"jpeg": photo}
    ok, out = asyncio.run(tools.execute("olhar_camera", {"origem": "celular"}, ctx(device=device)))
    assert ok and asked == [("celular", "camera_snapshot")] and "do celular" in out

    async def broken(target, kind):
        return {"jpeg": "isto não é base64!"}
    ok, out = asyncio.run(tools.execute("olhar_camera", {"origem": "celular"}, ctx(device=broken)))
    assert not ok and "inválida" in out


def test_look_is_offered_by_topic():
    assert "olhar_camera" in tools.topic_tools(["O que você está vendo na câmera?"])
    assert config.FACE_ENABLED is False  # olhar a cena não depende do reconhecimento facial
