"""Logotipo da Sarah: python -m jarvis.icon caminho\\da\\imagem.png

Gera, a partir de qualquer imagem PNG, JPG ou WEBP (recorte quadrado no centro):
- web/icon-192.png e web/icon-512.png: ícone da página, da aba e do app no celular ("Adicionar à tela inicial");
- web/sarah.ico: ícone do atalho "Sarah" da Área de Trabalho, que passa a usá-lo.
"""
import struct
import subprocess
import sys
from pathlib import Path

import cv2
import numpy as np

from . import config

ICO_SIZES = (16, 24, 32, 48, 64, 128, 256)


def _square(img: np.ndarray) -> np.ndarray:
    h, w = img.shape[:2]
    s = min(h, w)
    return img[(h - s) // 2:(h - s) // 2 + s, (w - s) // 2:(w - s) // 2 + s]


def _png(img: np.ndarray, size: int) -> bytes:
    ok, data = cv2.imencode(".png", cv2.resize(img, (size, size), interpolation=cv2.INTER_AREA))
    if not ok:
        raise ValueError("Não consegui gerar o PNG.")
    return data.tobytes()


def _ico(img: np.ndarray) -> bytes:
    """ICO com PNG dentro (aceito pelo Windows desde o Vista), nos tamanhos que o Explorador usa."""
    images = [_png(img, s) for s in ICO_SIZES]
    out, offset = struct.pack("<HHH", 0, 1, len(images)), 6 + 16 * len(images)
    for size, data in zip(ICO_SIZES, images, strict=True):
        out += struct.pack("<BBBBHHII", size % 256, size % 256, 0, 0, 1, 32, len(data), offset)  # 256 vira 0
        offset += len(data)
    return out + b"".join(images)


def make_icons(src: Path, web: Path) -> Path:
    img = cv2.imdecode(np.fromfile(src, np.uint8), cv2.IMREAD_UNCHANGED)  # imread não abre caminhos com acento
    if img is None:
        raise ValueError(f"Não consegui ler a imagem: {src}")
    if img.ndim == 2:
        img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
    img = _square(img)
    for size in (192, 512):
        (web / f"icon-{size}.png").write_bytes(_png(img, size))
    ico = web / "sarah.ico"
    ico.write_bytes(_ico(img))
    return ico


def set_shortcut_icon(ico: Path) -> Path | None:
    """Troca o ícone do atalho Sarah.lnk da Área de Trabalho, se ele existir."""
    from .tools import known_folder
    lnk = (known_folder("Área de Trabalho") or Path.home() / "Desktop") / "Sarah.lnk"
    if not lnk.exists():
        return None
    q = lambda p: str(p).replace("'", "''")  # aspas simples do PowerShell
    subprocess.run(["powershell", "-NoProfile", "-Command",
                    f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(lnk)}'); "
                    f"$s.IconLocation='{q(ico)},0'; $s.Save()"], check=True, capture_output=True, timeout=30)
    return lnk


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    ico = make_icons(Path(sys.argv[1]), config.ROOT / "web")
    lnk = set_shortcut_icon(ico)
    print(f"Ícones gerados em web\\ ({ico.name}, icon-192.png, icon-512.png).",
          f"Atalho atualizado: {lnk}" if lnk else "Atalho Sarah.lnk não encontrado na Área de Trabalho.",
          "Recarregue a página (Ctrl+F5) para ver o ícone novo.")
