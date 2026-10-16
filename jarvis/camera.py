"""Câmeras ao vivo: a webcam do PC (lida aqui) e a câmera do celular (enviada pela página do Jarvis no celular).

- A webcam do PC tem um único "dono" (uma thread): vídeo ao vivo e fotos compartilham a mesma captura, porque a
  webcam não pode ser aberta duas vezes. Ela abre quando alguém precisa e fecha 3 s depois que ninguém precisa mais;
  se alguém pedir de novo enquanto ela fecha, uma thread nova espera a anterior soltar a webcam e abre outra vez.
- A câmera do celular chega como quadros JPEG por WebSocket e fica só em memória (o último quadro).
- Nada é gravado em disco. Cada visualização dura no máximo MAX_VIEW segundos.
"""
import threading
import time
from contextlib import contextmanager

import numpy as np

from . import config

MAX_VIEW = 600       # 10 minutos por visualização
FPS = 8
WARMUP = 1.5         # segundos para a exposição automática estabilizar


class CameraError(Exception):
    pass


class _Feed:
    """Último quadro de uma fonte, com espera por quadro novo."""
    def __init__(self):
        self.cond = threading.Condition()
        self.frame, self.seq, self.at = None, 0, 0.0

    def put(self, frame) -> None:
        with self.cond:
            self.frame, self.seq, self.at = frame, self.seq + 1, time.time()
            self.cond.notify_all()

    def wait(self, after: int, timeout: float):
        with self.cond:
            self.cond.wait_for(lambda: self.seq > after, timeout)
            return self.seq, self.frame

    def clear(self) -> None:
        with self.cond:
            self.frame = None
            self.cond.notify_all()


pc = _Feed()          # quadros BGR (numpy) da webcam do PC
phone = _Feed()       # quadros JPEG (bytes) vindos do celular
_needs = 0
_lock = threading.Lock()
_thread: threading.Thread | None = None  # dona atual da webcam
_last: threading.Thread | None = None    # a dona anterior, que pode ainda estar soltando a webcam
_opened_at = 0.0
_error = ""


def _loop(previous: threading.Thread | None) -> None:
    global _thread, _opened_at, _error
    import cv2
    if previous:
        previous.join(timeout=5)  # o Windows só deixa abrir a webcam depois que a dona anterior soltou
    cap = cv2.VideoCapture(config.CAMERA_INDEX, cv2.CAP_DSHOW)
    if not cap.isOpened():
        _error = "Não consegui abrir a câmera do PC (em uso por outro app ou sem permissão no Windows?)."
        with _lock:
            _thread = None
        pc.clear()
        return
    _error, _opened_at = "", time.time()
    idle = None
    try:
        while True:
            ok, img = cap.read()
            if ok:
                pc.put(img)
            with _lock:  # decidir sair e liberar o posto juntos: quem pedir depois disso abre uma thread nova
                idle = None if _needs > 0 else (idle or time.time())
                if idle and time.time() - idle > 3:
                    _thread = None
                    break
            time.sleep(1 / FPS)
    finally:
        cap.release()
        pc.clear()


@contextmanager
def use_pc():
    """Mantém a webcam do PC aberta enquanto o bloco roda."""
    global _needs, _thread, _last
    with _lock:
        _needs += 1
        if _thread is None:
            _thread = _last = threading.Thread(target=_loop, args=(_last,), daemon=True)
            _thread.start()
    try:
        yield
    finally:
        with _lock:
            _needs -= 1


def pc_frames(n: int, spacing: float = 0.15) -> list[np.ndarray]:
    """n quadros da webcam do PC, já com a exposição ajustada (usado pelas fotos e pelo reconhecimento)."""
    with use_pc():
        seq, frames, start = 0, [], time.time()
        while len(frames) < n:
            if time.time() - start > WARMUP + 10:
                raise CameraError(_error or "A câmera do PC não mandou imagens.")
            seq, img = pc.wait(seq, 2)
            if img is None:
                if _error:
                    raise CameraError(_error)
                continue
            if time.time() - _opened_at >= WARMUP:
                frames.append(img)
                time.sleep(spacing)
        return frames


def jpeg(img: np.ndarray, quality: int = 70) -> bytes:
    import cv2
    from .face import DARK, brighten  # mesma correção das fotos para ambientes escuros
    if img.mean() < DARK:
        img = brighten(img)
    ok, buf = cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, quality])
    return buf.tobytes() if ok else b""


def opencv_available() -> bool:
    try:
        import cv2  # noqa: F401
        return True
    except ImportError:
        return False
