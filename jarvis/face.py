"""Reconhecimento facial OPCIONAL e DESLIGADO por padrão (JARVIS_FACE=on no .env para ativar).

Três coisas diferentes:
- detecção: há um rosto na imagem? (YuNet)
- reconhecimento: de quem é esse rosto, entre as pessoas cadastradas? (SFace)
- autenticação: é MESMO essa pessoa, e não uma foto? → NÃO é feita aqui (não há prova de vida).
Por isso o resultado é só informativo e nunca libera nenhuma ação.

Privacidade: a câmera só abre sob demanda (cadastro, "quem está na câmera?" ou "tirar foto"), nunca continuamente.
Pelo celular, só com JARVIS_REMOTE_CAMERA=true. O cadastro guarda só os vetores do rosto (128 números por amostra),
cifrados com DPAPI em data/face/pessoas.bin. Fotos só são salvas quando o usuário pede, em data/workspace/fotos.

Modelos (OpenCV Zoo): YuNet (MIT) e SFace (Apache 2.0). Baixar: .venv\\Scripts\\python.exe -m jarvis.face
"""
import asyncio
import hashlib
import json
import re
import time
import urllib.request
from functools import lru_cache
from pathlib import Path

import numpy as np

from . import config, db, secure
from .tools import ToolError, tool, workspace

THRESHOLD = 0.363  # similaridade de cosseno a partir da qual o OpenCV considera a mesma pessoa (SFace)
MAX_SAMPLES = 10
ZOO = "https://github.com/opencv/opencv_zoo/raw/main/models/"
MODELS = {  # arquivo: (caminho no OpenCV Zoo, sha256 verificado em 2026-10-16)
    "face_detection_yunet_2023mar.onnx": ("face_detection_yunet/",
                                          "8f2383e4dd3cfbb4553ea8718107fc0423210dc964f9f4280604804ed2552fa4"),
    "face_recognition_sface_2021dec.onnx": ("face_recognition_sface/",
                                            "0ba9fbfa01b5270c96627c4ef784da859931e02f04419c829e83484087c34e79"),
}


class FaceError(ToolError):
    pass


def _dir(name: str):
    p = (config.MODELS_DIR if name == "models" else config.DATA_DIR) / "face"
    p.mkdir(parents=True, exist_ok=True)
    return p


def models_ready() -> bool:
    return all((_dir("models") / f).exists() for f in MODELS)


def enabled() -> bool:
    return config.FACE_ENABLED and models_ready()


@lru_cache(1)
def _models():
    import cv2
    cv2.utils.logging.setLogLevel(cv2.utils.logging.LOG_LEVEL_ERROR)  # o OpenCV 5 avisa sobre "targets" a cada carga
    d = _dir("models")
    det = cv2.FaceDetectorYN.create(str(d / "face_detection_yunet_2023mar.onnx"), "", (320, 320), 0.8)
    rec = cv2.FaceRecognizerSF.create(str(d / "face_recognition_sface_2021dec.onnx"), "")
    return det, rec


def _features(img: np.ndarray) -> list[np.ndarray]:
    """Um vetor normalizado por rosto encontrado na imagem."""
    det, rec = _models()
    det.setInputSize((img.shape[1], img.shape[0]))
    faces = det.detect(img)[1]
    out = []
    for f in faces if faces is not None else []:
        v = rec.feature(rec.alignCrop(img, f)).flatten()
        out.append(v / np.linalg.norm(v))
    return out


def _capture(frames: int) -> list[np.ndarray]:
    """Quadros da webcam do PC (compartilhada com o vídeo ao vivo). Nada é salvo."""
    from . import camera
    try:
        return camera.pc_frames(frames)
    except camera.CameraError as e:
        raise FaceError(str(e)) from None


def _load() -> dict[str, list[list[float]]]:
    p = _dir("data") / "pessoas.bin"
    if not p.exists():
        return {}
    try:
        return json.loads(secure.dpapi(p.read_bytes(), protect=False))
    except ValueError:
        raise FaceError("Não consegui abrir os dados faciais (outro usuário ou PC?). Use 'Apagar tudo' e cadastre de novo.") from None


def _save(people: dict) -> None:
    p = _dir("data") / "pessoas.bin"
    if people:
        p.write_bytes(secure.dpapi(json.dumps(people).encode(), protect=True))
    else:
        p.unlink(missing_ok=True)


def people() -> list[dict]:
    return [{"nome": n, "amostras": len(v)} for n, v in sorted(_load().items())]


def enroll(name: str) -> int:
    name = " ".join(name.split())[:60]
    if not name:
        raise FaceError("Informe um nome.")
    samples = []
    for img in _capture(8):
        feats = _features(img)
        if len(feats) == 1:  # quadros com nenhum ou vários rostos são ignorados
            samples.append(feats[0].tolist())
    if len(samples) < 3:
        raise FaceError("Não vi exatamente um rosto na maioria das imagens. Fique sozinho, de frente e com boa luz.")
    data = _load()
    data[name] = (data.get(name, []) + samples)[-MAX_SAMPLES:]
    _save(data)
    return len(data[name])


def identify_images(imgs: list[np.ndarray]) -> list[dict]:
    known = {n: np.array(v) for n, v in _load().items()}
    best_faces: list[np.ndarray] = max((_features(i) for i in imgs), key=len, default=[])
    result = []
    for v in best_faces:
        scores = {n: float(np.max(s @ v)) for n, s in known.items()}
        name, score = max(scores.items(), key=lambda x: x[1], default=("", 0.0))
        result.append({"nome": name if score >= THRESHOLD else "desconhecido", "similaridade": round(score, 3)})
    return result


def identify() -> list[dict]:
    return identify_images(_capture(3))


def photo_text(found: list[dict], dark: bool) -> str:
    note = " A foto estava muito escura (pouca luz ou câmera tampada) e foi clareada automaticamente." if dark else ""
    return describe(found) + note


def describe(found: list[dict]) -> str:
    if not found:
        return "Nenhum rosto na câmera."
    names = [f"{f['nome']} (similaridade {f['similaridade']:.2f})" for f in found]
    return (f"{len(found)} rosto(s): {', '.join(names)}. Reconhecimento sem prova de vida: é só informativo, "
            "não comprova identidade.")


def remove(name: str) -> bool:
    data = _load()
    found = data.pop(name, None) is not None
    _save(data)
    return found


def remove_all() -> None:
    _save({})


# ---------- Fotos (só quando o usuário pede) ----------

PHOTO_RE = re.compile(r"foto-\d{8}-\d{6}(-\d+)?\.jpg")


def photos_dir() -> Path:
    p = workspace() / "fotos"
    p.mkdir(parents=True, exist_ok=True)
    return p


DARK = 60  # brilho médio (0–255) abaixo do qual a foto é clareada


def brighten(img: np.ndarray) -> np.ndarray:
    """Correção de gama que leva o brilho médio para ~110. Medido nesta webcam à noite: média 2–5 de 255."""
    import cv2
    mean = max(float(img.mean()), 1.0)
    gamma = max(0.2, np.log(110 / 255) / np.log(mean / 255))
    lut = (255 * (np.arange(256) / 255) ** gamma).clip(0, 255).astype(np.uint8)
    return cv2.LUT(img, lut)


def take_photo() -> tuple[str, list[dict], bool]:
    """Tira uma foto com a webcam, salva em JPEG e diz quem foi reconhecido nela e se estava escura."""
    import cv2
    img = _capture(3)[-1]  # o último quadro já está com a exposição ajustada
    found = identify_images([img])
    dark = bool(img.mean() < DARK)
    if dark:
        img = brighten(img)
    ok, jpg = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 90])
    if not ok:
        raise FaceError("Não consegui gerar a imagem.")
    stamp, n = time.strftime("%Y%m%d-%H%M%S"), 1
    name = f"foto-{stamp}.jpg"
    while (photos_dir() / name).exists():
        n += 1
        name = f"foto-{stamp}-{n}.jpg"
    (photos_dir() / name).write_bytes(jpg.tobytes())  # imencode + bytes: imwrite falha com caminhos acentuados
    return name, found, dark


def photo_path(name: str) -> Path:
    if not PHOTO_RE.fullmatch(name or ""):
        raise FaceError("Nome de foto inválido.")
    return photos_dir() / name


def list_photos() -> list[str]:
    return sorted((p.name for p in photos_dir().glob("foto-*.jpg") if PHOTO_RE.fullmatch(p.name)), reverse=True)


def camera_allowed(remote: bool) -> None:
    if remote and not config.REMOTE_CAMERA:
        raise FaceError("A câmera do PC pelo celular está desligada (JARVIS_REMOTE_CAMERA no .env).")


@tool("quem_esta_na_camera", "Quem está na câmera", "Olha a webcam do PC agora e diz quantos rostos há e se são "
      "pessoas cadastradas. Só informativo; não salva nada.", "leitura", available_if=enabled)
async def quem_esta_na_camera(args, ctx):
    camera_allowed(ctx.remote)
    found = await asyncio.to_thread(identify)
    db.audit(ctx.actor, "camera_consultada", {"rostos": len(found)})
    return describe(found)


@tool("tirar_foto", "Tirar foto", "Tira e SALVA uma foto agora com a webcam do PC (use só quando o usuário pedir) e diz "
      "quem foi reconhecido nela.", "acao", available_if=enabled)
async def tirar_foto(args, ctx):
    camera_allowed(ctx.remote)
    name, found, dark = await asyncio.to_thread(take_photo)
    db.audit(ctx.actor, "foto_tirada", {"arquivo": name, "rostos": len(found)})
    return f"Foto salva em {photos_dir() / name} [foto:{name}]. {photo_text(found, dark)}"


def download() -> None:
    d = _dir("models")
    for name, (path, sha) in MODELS.items():
        target = d / name
        if not (target.exists() and hashlib.sha256(target.read_bytes()).hexdigest() == sha):
            print(f"baixando {name}...")
            urllib.request.urlretrieve(ZOO + path + name, target)
        if hashlib.sha256(target.read_bytes()).hexdigest() != sha:
            target.unlink()
            raise SystemExit(f"{name}: arquivo diferente do esperado (sha256). Download cancelado.")
        print(f"ok  {name}")


if __name__ == "__main__":
    download()
