"""Persistência em SQLite: conversas, mensagens, memórias, sessões, auditoria e ajustes."""
import json
import sqlite3
from contextlib import closing

from . import config

SCHEMA = """
create table if not exists conversations(
  id integer primary key, title text not null, created_at text default current_timestamp);
create table if not exists messages(
  id integer primary key,
  conversation_id integer not null references conversations(id) on delete cascade,
  role text not null, content text not null, created_at text default current_timestamp);
create index if not exists messages_conv on messages(conversation_id, id);
create virtual table if not exists memories using fts5(content, created_at unindexed);
create table if not exists sessions(
  token_hash text primary key, created_at real not null, expires_at real not null,
  user_agent text, remote integer not null default 0);
create table if not exists audit(
  id integer primary key, ts text default current_timestamp, actor text, action text, detail text);
create table if not exists settings(key text primary key, value text not null);
"""


def connect() -> sqlite3.Connection:
    config.DATA_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(config.DATA_DIR / "jarvis.db", timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("pragma foreign_keys = on")
    return conn


def init() -> None:
    with closing(connect()) as conn, conn as c:
        c.execute("pragma journal_mode = wal")
        c.executescript(SCHEMA)


def query(sql: str, params=()) -> list[dict]:
    with closing(connect()) as conn, conn as c:
        return [dict(r) for r in c.execute(sql, params)]


def execute(sql: str, params=()) -> int:
    """Executa e retorna lastrowid (inserções) ou rowcount (demais)."""
    with closing(connect()) as conn, conn as c:  # "with conn" confirma a transação; closing() fecha a conexão
        cur = c.execute(sql, params)
        return cur.lastrowid if sql.lstrip().lower().startswith("insert") else cur.rowcount


def audit(actor: str, action: str, detail: dict | None = None) -> None:
    execute("insert into audit(actor, action, detail) values (?, ?, ?)",
            (actor, action, json.dumps(detail or {}, ensure_ascii=False)))


def get_setting(key: str) -> str | None:
    rows = query("select value from settings where key = ?", (key,))
    return rows[0]["value"] if rows else None


def set_setting(key: str, value: str) -> None:
    execute("insert into settings(key, value) values (?, ?) "
            "on conflict(key) do update set value = excluded.value", (key, value))
