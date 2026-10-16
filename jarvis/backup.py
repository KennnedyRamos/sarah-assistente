"""Backup dos dados do Jarvis num .zip (pode rodar com o Jarvis aberto): python -m jarvis.backup [pasta de destino]

Inclui: banco (cópia consistente pela API de backup do SQLite), permissões, token do Google e dados faciais
(ambos cifrados com DPAPI: só restauram neste PC e nesta conta do Windows), área de trabalho e fotos.
Fica de fora o que se baixa de novo ou é temporário: modelos (data/models), áreas de programação e logs.
Restaurar: feche o Jarvis, extraia o .zip dentro da pasta data e inicie de novo.
"""
import sqlite3
import sys
import tempfile
import time
import zipfile
from pathlib import Path

from . import config

SKIP_DIRS = {"models", "logs", ".areas"}
SKIP_FILES = {"jarvis.db", "jarvis.db-wal", "jarvis.db-shm", "jarvis.pid"}


def make_backup(dest_dir: Path) -> Path:
    data = config.DATA_DIR
    dest_dir.mkdir(parents=True, exist_ok=True)
    target = dest_dir / f"jarvis-backup-{time.strftime('%Y%m%d-%H%M%S')}.zip"
    with tempfile.TemporaryDirectory() as tmp:
        snapshot = Path(tmp) / "jarvis.db"
        src = sqlite3.connect(data / "jarvis.db")
        dst = sqlite3.connect(snapshot)
        with dst:
            src.backup(dst)  # cópia consistente mesmo com o Jarvis gravando
        src.close()
        dst.close()
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(snapshot, "jarvis.db")
            for f in data.rglob("*"):
                rel = f.relative_to(data)
                if f.is_file() and rel.name not in SKIP_FILES and not set(rel.parts) & SKIP_DIRS:
                    z.write(f, rel.as_posix())
    return target


if __name__ == "__main__":
    out = make_backup(Path(sys.argv[1]) if len(sys.argv) > 1 else config.ROOT / "backups")
    print(f"Backup criado: {out} ({out.stat().st_size / 1e6:.1f} MB)")
