"""Uso de disco da Sarah, limpeza do que envelhece e manutenção automática do banco.

Medido em 2026-10-16: conversas e memórias ocupam KB; o grosso são os modelos (necessários) e, com o tempo,
as áreas do agente de programação (cópias de projetos) e os backups de arquivos sobrescritos ou integrados.
A limpeza nunca apaga conversas, memórias, arquivos enviados, anexos ou fotos: isso é do usuário.
"""
import os
import shutil
import sqlite3
import stat
import time
from contextlib import closing
from pathlib import Path

from . import config, db
from .coding import SKIP_DIRS, areas_root
from .tools import workspace

AREA_DAYS, BACKUP_DAYS, AUDIT_DAYS = 7, 30, 180
DB_FILES = ("jarvis.db", "jarvis.db-wal", "jarvis.db-shm")


def size(path: Path) -> int:
    """Bytes ocupados. Cada arquivo conta uma vez: o cache do Whisper usa hardlinks (o mesmo arquivo com dois nomes)."""
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    seen, total = set(), 0
    for f in path.rglob("*"):
        st = f.stat()
        if f.is_file() and (st.st_dev, st.st_ino) not in seen:
            seen.add((st.st_dev, st.st_ino))
            total += st.st_size
    return total


def _last_use(area: Path) -> float:
    """Última alteração de arquivo na área (sem descer em node_modules, .venv e outras pastas geradas)."""
    newest = area.stat().st_mtime
    for dirpath, dirnames, filenames in os.walk(area):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            newest = max(newest, os.stat(os.path.join(dirpath, f)).st_mtime)
    return newest


def old_areas() -> list[Path]:
    limit = time.time() - AREA_DAYS * 86400
    return [a for a in areas_root().iterdir() if a.is_dir() and _last_use(a) < limit]


def old_backups() -> list[Path]:
    root = config.DATA_DIR / "backups"
    limit = time.time() - BACKUP_DAYS * 86400
    return [p for p in root.iterdir() if p.stat().st_mtime < limit] if root.is_dir() else []


def _remove(path: Path) -> None:
    def writable_and_retry(func, target, _exc):  # arquivos somente leitura (ex.: dentro de .git) também saem
        os.chmod(target, stat.S_IWRITE)
        func(target)
    if path.is_dir():
        shutil.rmtree(path, onerror=writable_and_retry)
    else:
        path.unlink(missing_ok=True)


def report() -> dict:
    data, ws = config.DATA_DIR, workspace()
    counts = db.query("select (select count(*) from conversations) as conversas, (select count(*) from messages) as mensagens,"
                      " (select count(*) from audit) as auditoria")[0]
    return {
        "itens": [
            {"nome": "Conversas, memórias e ajustes (banco)", "bytes": sum(size(data / f) for f in DB_FILES)},
            {"nome": "Arquivos enviados", "bytes": size(ws / "arquivos")},
            {"nome": "Anexos de e-mail", "bytes": size(ws / "anexos")},
            {"nome": "Fotos", "bytes": size(ws / "fotos")},
            {"nome": "Áreas do agente de programação", "bytes": size(areas_root())},
            {"nome": "Backups de arquivos alterados", "bytes": size(data / "backups")},
            {"nome": "Registros técnicos (logs)", "bytes": size(data / "logs")},
            {"nome": "Modelos de voz e de rosto", "bytes": size(config.MODELS_DIR)},
        ],
        **counts,
        "areas_antigas": len(old_areas()), "backups_antigos": len(old_backups()),
        "dias": {"areas": AREA_DAYS, "backups": BACKUP_DAYS, "auditoria": AUDIT_DAYS},
    }


def compact() -> None:
    """Devolve ao disco o espaço de registros apagados (o SQLite só reaproveita, não encolhe sozinho)."""
    with closing(sqlite3.connect(config.DATA_DIR / "jarvis.db", isolation_level=None, timeout=10)) as c:
        c.execute("pragma wal_checkpoint(truncate)")
        c.execute("vacuum")


def cleanup(areas: bool, backups: bool, compact_db: bool) -> int:
    """Apaga o que foi pedido e devolve quantos bytes foram liberados."""
    freed = 0
    for path in (old_areas() if areas else []) + (old_backups() if backups else []):
        freed += size(path)
        _remove(path)
    if compact_db:
        before = sum(size(config.DATA_DIR / f) for f in DB_FILES)
        compact()
        freed += max(0, before - sum(size(config.DATA_DIR / f) for f in DB_FILES))
    return freed


def maintain() -> None:
    """Na inicialização: a auditoria com mais de 180 dias sai e o SQLite atualiza as estatísticas dos índices."""
    db.execute("delete from audit where ts < datetime('now', ?)", (f"-{AUDIT_DAYS} days",))
    db.execute("pragma optimize")
