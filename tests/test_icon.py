"""Gerador do logotipo: qualquer imagem vira ícones da página e um .ico válido para o atalho."""
import struct

import cv2
import numpy as np
import pytest

from jarvis import icon


def test_icons_from_any_image(tmp_path):
    img = np.zeros((300, 500, 4), np.uint8)  # retangular e com transparência
    img[:, :, 2] = img[:, :, 3] = 255
    src = tmp_path / "logotipo é meu.png"  # caminho com acento
    cv2.imencode(".png", img)[1].tofile(src)
    ico = icon.make_icons(src, tmp_path)
    for size in (192, 512):
        out = cv2.imdecode(np.fromfile(tmp_path / f"icon-{size}.png", np.uint8), cv2.IMREAD_UNCHANGED)
        assert out.shape == (size, size, 4)  # recorte quadrado, transparência mantida
    data = ico.read_bytes()
    reserved, kind, count = struct.unpack_from("<HHH", data)
    assert (reserved, kind, count) == (0, 1, len(icon.ICO_SIZES))
    for i, size in enumerate(icon.ICO_SIZES):
        w, h, _, _, planes, bpp, length, offset = struct.unpack_from("<BBBBHHII", data, 6 + 16 * i)
        assert w == size % 256 and planes == 1 and bpp == 32
        assert data[offset:offset + 8] == b"\x89PNG\r\n\x1a\n" and offset + length <= len(data)


def test_unreadable_image(tmp_path):
    (tmp_path / "x.png").write_bytes(b"nao e imagem")
    with pytest.raises(ValueError, match="Não consegui ler"):
        icon.make_icons(tmp_path / "x.png", tmp_path)
