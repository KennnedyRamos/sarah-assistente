"""Uso de disco, limpeza segura e manutenção automática do banco."""
import json
import os
import stat
import time

from jarvis import auth, coding, config, db, storage, tools

from .conftest import PASSWORD

OLD = time.time() - 40 * 86400


def make_area(name: str, old: bool):
    area = coding.areas_root() / name
    (area / "src").mkdir(parents=True)
    (area / coding.META).write_text(json.dumps({"origem": "C:/projeto"}), encoding="utf-8")
    (area / "src" / "app.py").write_text("print(1)" * 100)
    git = area / ".git"
    git.mkdir()
    (git / "objeto").write_text("x")
    os.chmod(git / "objeto", stat.S_IREAD)  # como os objetos do git: somente leitura
    if old:
        for f in area.rglob("*"):
            os.utime(f, (OLD, OLD))
        os.utime(area, (OLD, OLD))
    return area


def test_cleanup_only_old_areas_and_backups():
    old_area, new_area = make_area("velha", True), make_area("nova", False)
    backups = config.DATA_DIR / "backups"
    backups.mkdir()
    (backups / "antigo.txt").write_text("a" * 1000)
    (backups / "recente.txt").write_text("b")
    os.utime(backups / "antigo.txt", (OLD, OLD))
    (tools.workspace() / "arquivos").mkdir()
    (tools.workspace() / "arquivos" / "meu.pdf").write_bytes(b"%PDF" * 100)
    os.utime(tools.workspace() / "arquivos" / "meu.pdf", (OLD, OLD))
    r = storage.report()
    assert r["areas_antigas"] == 1 and r["backups_antigos"] == 1
    freed = storage.cleanup(areas=True, backups=True, compact_db=False)
    assert freed > 1000 and not old_area.exists() and new_area.exists()
    assert not (backups / "antigo.txt").exists() and (backups / "recente.txt").exists()
    assert (tools.workspace() / "arquivos" / "meu.pdf").exists()  # arquivos do usuário nunca são apagados


def test_maintenance_prunes_old_audit_and_compacts():
    db.execute("insert into audit(ts, actor, action) values (datetime('now', '-200 days'), 'local', 'antigo')")
    db.audit("local", "recente")
    storage.maintain()
    actions = [a["action"] for a in db.query("select action from audit")]
    assert "antigo" not in actions and "recente" in actions
    storage.cleanup(areas=False, backups=False, compact_db=True)  # VACUUM roda sem erro com o banco em uso
    assert db.query("select count(*) as n from audit")[0]["n"] >= 1


def test_storage_api_local_only(logged, client):
    r = logged.get("/api/storage").json()
    assert {i["nome"] for i in r["itens"]} >= {"Arquivos enviados", "Modelos de voz e de rosto"} and "conversas" in r
    assert "liberado" in logged.post("/api/storage/cleanup", json={"compactar": True}).json()
    assert "armazenamento_limpo" in [a["action"] for a in logged.get("/api/audit").json()]
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.post("/api/storage/cleanup", json={"areas": True}).status_code == 403


def test_conversations_ordered_by_last_activity(logged):
    first = db.execute("insert into conversations(title) values ('primeira')")
    second = db.execute("insert into conversations(title) values ('segunda')")
    db.execute("insert into messages(conversation_id, role, content, created_at) values (?, 'user', 'oi', datetime('now', '-1 day'))",
               (second,))
    db.execute("insert into messages(conversation_id, role, content) values (?, 'user', 'agora')", (first,))
    convs = logged.get("/api/conversations").json()
    assert [c["title"] for c in convs] == ["primeira", "segunda"] and all("updated_at" in c for c in convs)


def test_size_counts_hardlinks_once(tmp_path):
    """O cache do Whisper guarda o mesmo arquivo com dois nomes (hardlink): conta uma vez só."""
    cache = tmp_path / "cache"  # a pasta do teste também guarda o banco isolado
    cache.mkdir()
    (cache / "blob").write_bytes(b"x" * 1000)
    os.link(cache / "blob", cache / "model.bin")
    assert storage.size(cache) == 1000
