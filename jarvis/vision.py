"""Visão: o mesmo modelo de linguagem (qwen3.5:4b) entende imagens; não há modelo extra nem custo.

Medido em 2026-10-16: ícone de 192 px em 2,8 s; captura de tela de 1366x800 (~1.100 tokens) em 11,7 s, descrita certo.
Equilíbrio entre precisão e velocidade: as imagens vão com no máximo 1024 px no lado maior (lê textos de tamanho normal
e custa ~1.000 tokens) e só as 2 imagens mais recentes da conversa vão como imagem; as antigas ficam só como texto.
"""
import base64
import re
from functools import lru_cache

import cv2
import numpy as np

from . import llm
from .tools import ToolError, allowed_path

MAX_SIDE = 1024
KEEP_IMAGES = 2
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
ATTACHED = re.compile(r"^📎 (?:Arquivo|Imagem) enviad[oa]: (.+)$", re.M)  # linha que a interface põe na mensagem
DESCRIBE_PROMPT = ("Você analisa imagens com precisão. Responda em português do Brasil, de forma objetiva. Descreva só o que "
                   "dá para ver; leia textos visíveis quando forem relevantes; se algo não estiver claro, diga que não dá "
                   "para ter certeza. Não invente detalhes.")


def encode(img: np.ndarray) -> str:
    """Imagem BGR → JPEG reduzido (lado maior ≤ 1024 px) em base64, como o Ollama espera."""
    h, w = img.shape[:2]
    scale = MAX_SIDE / max(h, w)
    if scale < 1:
        img = cv2.resize(img, (round(w * scale), round(h * scale)), interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, 88])
    if not ok:
        raise ToolError("Não consegui preparar a imagem.")
    return base64.b64encode(buf.tobytes()).decode()


def decode(data: bytes) -> np.ndarray:
    img = cv2.imdecode(np.frombuffer(data, np.uint8), cv2.IMREAD_COLOR)
    if img is None:
        raise ToolError("Não consegui abrir a imagem (formato não suportado ou arquivo corrompido).")
    return img


@lru_cache(32)
def _encode_file(path: str, mtime: float) -> str:  # a mesma imagem volta em cada turno: reduz só uma vez
    return encode(decode(open(path, "rb").read()))


def images_in(text: str) -> list[str]:
    """Imagens anexadas a uma mensagem (só da área de trabalho e pastas autorizadas), prontas para o modelo."""
    out = []
    for raw in ATTACHED.findall(text):
        try:
            p = allowed_path(raw.strip())
            if p.suffix.lower() in IMAGE_EXT and p.is_file():
                out.append(_encode_file(str(p), p.stat().st_mtime))
        except ToolError:
            continue  # imagem apagada, corrompida ou fora das pastas: a mensagem segue só com o texto
    return out


def attach(messages: list[dict]) -> None:
    """Põe as imagens nas mensagens do usuário; só as KEEP_IMAGES mais recentes (cada uma custa ~1.000 tokens)."""
    left = KEEP_IMAGES
    for m in reversed(messages):
        if left and m["role"] == "user":
            images = images_in(m["content"])
            if images:
                m["images"] = images
                left -= 1


async def describe(image_b64: str, question: str) -> str:
    """Pergunta sobre uma imagem numa chamada separada ao modelo (usada pelas ferramentas de câmera)."""
    parts = []
    async for event in llm.chat([{"role": "system", "content": DESCRIBE_PROMPT},
                                 {"role": "user", "content": question, "images": [image_b64]}]):
        if event["type"] == "token":
            parts.append(event["text"])
    return "".join(parts).strip() or "Não consegui descrever a imagem."
