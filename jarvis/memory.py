"""Memória persistente por recuperação (FTS5). Nada aqui treina o modelo."""
import re

from . import db

MAX_LEN = 2000
INJECT_ALL_UP_TO = 20  # com poucas memórias, mandar todas é mais confiável que buscar


def add(content: str) -> int:
    content = _clean(content)
    return db.execute("insert into memories(content, created_at) values (?, datetime('now'))", (content,))


def list_all() -> list[dict]:
    return db.query("select rowid as id, content, created_at from memories order by rowid desc")


def update(memory_id: int, content: str) -> bool:
    return db.execute("update memories set content = ? where rowid = ?", (_clean(content), memory_id)) > 0


def delete(memory_id: int) -> bool:
    return db.execute("delete from memories where rowid = ?", (memory_id,)) > 0


def relevant(text: str, limit: int = 5) -> list[dict]:
    if db.query("select count(*) as n from memories")[0]["n"] <= INJECT_ALL_UP_TO:
        return list_all()
    # shortcut: prefixo de 6 letras faz as vezes de radicalização; trocar por embeddings se a recuperação falhar
    words = {w[:6] for w in re.findall(r"\w{3,}", text.lower())}
    if not words:
        return []
    match = " OR ".join(f'"{w}"*' for w in words)
    return db.query("select rowid as id, content, created_at from memories where memories match ? "
                    "order by rank limit ?", (match, limit))


def _clean(content: str) -> str:
    content = content.strip()
    if not content or len(content) > MAX_LEN:
        raise ValueError(f"A memória precisa ter entre 1 e {MAX_LEN} caracteres.")
    return content
