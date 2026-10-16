"""Reconhecimento facial com câmera e modelo simulados (nenhuma imagem real)."""
import asyncio

import numpy as np
import pytest
from fastapi.testclient import TestClient

from jarvis import config, face, tools
from jarvis.main import app

from .conftest import ORIGIN, PASSWORD

rng = np.random.default_rng(1)
ANA = rng.standard_normal(128)
OUTRA = rng.standard_normal(128)


def unit(v):
    return v / np.linalg.norm(v)


class Frame(np.ndarray):
    faces: list = []


def frame(*faces):
    """Imagem real (para virar JPEG) que carrega os vetores dos rostos que 'aparecem' nela."""
    img = np.full((48, 64, 3), 128, dtype=np.uint8).view(Frame)
    img.faces = [unit(f) for f in faces]
    return img


@pytest.fixture
def camera(monkeypatch):
    monkeypatch.setattr(config, "FACE_ENABLED", True)
    monkeypatch.setattr(face, "models_ready", lambda: True)
    monkeypatch.setattr(face, "_features", lambda img: list(getattr(img, "faces", [])))
    shots = {"frames": []}
    monkeypatch.setattr(face, "_capture", lambda n: shots["frames"])
    return shots


def test_disabled_by_default(logged):
    assert config.FACE_ENABLED is False
    assert "quem_esta_na_camera" not in {t.name for t in tools.available(False)}
    assert logged.get("/api/face").json()["enabled"] is False
    assert logged.post("/api/face/enroll", json={"nome": "Ana"}).status_code == 409
    assert logged.post("/api/face/identify").status_code == 409


def test_enroll_and_identify(camera):
    camera["frames"] = [frame(ANA + rng.normal(0, 0.3, 128)) for _ in range(8)]
    assert face.enroll("  Ana   Silva ") == 8
    assert face.people() == [{"nome": "Ana Silva", "amostras": 8}]
    found = face.identify_images([frame(ANA + rng.normal(0, 0.3, 128))])
    assert found[0]["nome"] == "Ana Silva" and found[0]["similaridade"] > face.THRESHOLD
    assert face.identify_images([frame(OUTRA)])[0]["nome"] == "desconhecido"
    assert face.identify_images([frame()]) == []
    assert "Nenhum rosto" in face.describe([]) and "não comprova identidade" in face.describe(found)


def test_enroll_needs_exactly_one_face(camera):
    camera["frames"] = [frame(ANA, OUTRA)] * 8  # duas pessoas no quadro
    with pytest.raises(face.FaceError, match="exatamente um rosto"):
        face.enroll("Ana")
    camera["frames"] = [frame()] * 8  # ninguém
    with pytest.raises(face.FaceError):
        face.enroll("Ana")


def test_samples_capped(camera):
    camera["frames"] = [frame(ANA)] * 8
    face.enroll("Ana")
    assert face.enroll("Ana") == face.MAX_SAMPLES


def test_stored_encrypted_without_images(camera):
    camera["frames"] = [frame(ANA)] * 8
    face.enroll("Ana")
    raw = (config.DATA_DIR / "face" / "pessoas.bin").read_bytes()
    assert b"Ana" not in raw  # nome e vetores cifrados com DPAPI
    assert [p.name for p in (config.DATA_DIR / "face").iterdir()] == ["pessoas.bin"]  # nenhuma imagem


def test_remove_and_remove_all(camera):
    camera["frames"] = [frame(ANA)] * 8
    face.enroll("Ana")
    face.enroll("Bia")
    assert face.remove("Ana") and not face.remove("Ana")
    face.remove_all()
    assert face.people() == [] and not (config.DATA_DIR / "face" / "pessoas.bin").exists()


def test_tool_local_only(camera):
    camera["frames"] = [frame(ANA)] * 3

    async def emit(ev):
        pass

    async def no(*a):
        return False

    def run(remote):
        return asyncio.run(tools.execute("quem_esta_na_camera", {}, tools.Context(remote=remote, emit=emit, approve=no)))
    ok, out = run(remote=False)
    assert ok and "desconhecido" in out
    ok, out = run(remote=True)
    assert not ok and "JARVIS_REMOTE_CAMERA" in out


def test_api_flow(logged, camera):
    camera["frames"] = [frame(ANA)] * 8
    r = logged.post("/api/face/enroll", json={"nome": "Ana"})
    assert r.status_code == 200 and r.json()["people"] == [{"nome": "Ana", "amostras": 8}]
    camera["frames"] = [frame(ANA)]
    assert "Ana" in logged.post("/api/face/identify").json()["texto"]
    assert logged.delete("/api/face/people/Ana").status_code == 200
    assert logged.delete("/api/face/people/Ana").status_code == 404
    actions = [a["action"] for a in logged.get("/api/audit").json()]
    assert {"rosto_cadastrado", "camera_consultada", "rosto_removido"} <= set(actions)


def test_phone_cannot_use_pc_camera_but_can_delete(logged, camera):
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as phone:
        phone.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.5"})
        assert phone.post("/api/face/enroll", json={"nome": "Ana"}).status_code == 403
        assert phone.post("/api/face/identify").status_code == 403
        assert phone.delete("/api/face/people").status_code == 200  # apagar sempre é permitido


@pytest.mark.skipif(not face.models_ready(), reason="modelos faciais não baixados")
def test_real_models_load_and_find_no_face_in_blank_image():
    assert face.identify_images([np.zeros((240, 320, 3), dtype=np.uint8)]) == []


# ---------- Fotos e câmera pelo celular ----------

def test_take_photo_saves_jpeg_and_identifies(camera):
    import cv2
    camera["frames"] = [frame(ANA)] * 8
    face.enroll("Ana")
    camera["frames"] = [frame(), frame(), frame(ANA + rng.normal(0, 0.3, 128))]
    name, found, dark = face.take_photo()
    data = (face.photos_dir() / name).read_bytes()
    assert cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR).shape == (48, 64, 3)
    assert found[0]["nome"] == "Ana" and face.list_photos() == [name]
    name2, _, _ = face.take_photo()  # duas no mesmo segundo não se sobrescrevem
    assert name2 != name and len(face.list_photos()) == 2


def test_photo_tool_result_has_marker(camera):
    camera["frames"] = [frame()] * 3

    async def emit(ev):
        pass

    async def no(*a):
        return False
    ok, out = asyncio.run(tools.execute("tirar_foto", {}, tools.Context(remote=False, emit=emit, approve=no)))
    assert ok and "[foto:foto-" in out and "Nenhum rosto" in out


def test_photo_api(logged, camera):
    camera["frames"] = [frame()] * 3
    r = logged.post("/api/face/photo")
    name = r.json()["foto"]
    img = logged.get(f"/api/photos/{name}")
    assert img.status_code == 200 and img.headers["content-type"] == "image/jpeg"
    assert "no-store" in img.headers["cache-control"]
    assert logged.get("/api/photos/foto-1.jpg").status_code == 400  # nome fora do padrão
    assert logged.get("/api/photos/foto-20990101-000000.jpg").status_code == 404
    assert logged.get("/api/face").json()["photos"] == [name]
    assert logged.delete(f"/api/photos/{name}").json() == {"photos": []}
    logged.post("/api/face/photo")
    assert logged.delete("/api/photos").json() == {"photos": []}
    actions = [a["action"] for a in logged.get("/api/audit").json()]
    assert {"foto_tirada", "foto_apagada", "fotos_apagadas"} <= set(actions)


def test_photos_need_session(client):
    assert client.get("/api/photos/foto-20990101-000000.jpg").status_code == 401
    assert client.post("/api/face/photo").status_code == 401


def test_phone_camera_when_enabled(logged, camera, monkeypatch):
    monkeypatch.setattr(config, "REMOTE_CAMERA", True)
    camera["frames"] = [frame(ANA)] * 8
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as phone:
        phone.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.5"})
        assert phone.get("/api/face").json()["can_use_camera"] is True
        assert phone.post("/api/face/enroll", json={"nome": "Ana"}).status_code == 200
        assert "Ana" in phone.post("/api/face/identify").json()["texto"]
        name = phone.post("/api/face/photo").json()["foto"]
        assert phone.get(f"/api/photos/{name}").status_code == 200
    audit = logged.get("/api/audit").json()
    assert any(a["actor"] == "remoto" and a["action"] == "foto_tirada" for a in audit)


def test_dark_photo_is_brightened(camera):
    import cv2
    dark = np.full((48, 64, 3), 3, dtype=np.uint8).view(Frame)  # medido nesta webcam à noite: brilho 2–5
    dark.faces = []
    camera["frames"] = [dark] * 3
    name, found, was_dark = face.take_photo()
    saved = cv2.imdecode(np.frombuffer((face.photos_dir() / name).read_bytes(), np.uint8), cv2.IMREAD_COLOR)
    assert was_dark and saved.mean() > face.DARK
    assert "clareada" in face.photo_text(found, was_dark)
    camera["frames"] = [frame()] * 3  # imagem normal (brilho 128) fica como está
    name, _, was_dark = face.take_photo()
    assert not was_dark
