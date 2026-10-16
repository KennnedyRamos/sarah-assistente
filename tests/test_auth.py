import time

from fastapi.testclient import TestClient

from jarvis import auth, db
from jarvis.main import app

from .conftest import ORIGIN, PASSWORD


def test_login_without_password_configured(client):
    r = client.post("/api/login", json={"password": "qualquer-coisa"})
    assert r.status_code == 503


def test_short_password_rejected():
    import pytest
    with pytest.raises(ValueError):
        auth.set_password("curta")


def test_wrong_password_then_rate_limit(client):
    auth.set_password(PASSWORD)
    for _ in range(auth.MAX_FAILURES):
        assert client.post("/api/login", json={"password": "errada-errada"}).status_code == 401
    # bloqueado mesmo com a senha certa
    assert client.post("/api/login", json={"password": PASSWORD}).status_code == 429


def test_login_sets_protected_cookie(client):
    auth.set_password(PASSWORD)
    r = client.post("/api/login", json={"password": PASSWORD})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"].lower()
    assert "httponly" in cookie and "samesite=strict" in cookie
    assert client.get("/api/me").status_code == 200


def test_api_requires_session(client):
    for path in ["/api/status", "/api/conversations", "/api/memories", "/api/audit", "/api/sessions"]:
        assert client.get(path).status_code == 401, path


def test_foreign_host_blocked(logged):
    # simula DNS rebinding: navegador chega com Host de outro domínio
    assert logged.get("/api/me", headers={"host": "evil.example"}).status_code == 400


def test_cross_origin_post_blocked(logged):
    assert logged.post("/api/logout", headers={"origin": "http://evil.example"}).status_code == 403
    assert logged.post("/api/logout", headers={"origin": "http://localhost:3000"}).status_code == 403
    with TestClient(app, base_url="http://localhost:8765") as no_origin:
        assert no_origin.post("/api/login", json={"password": PASSWORD}).status_code == 403


def test_expired_session_rejected(logged):
    db.execute("update sessions set expires_at = ?", (time.time() - 1,))
    assert logged.get("/api/me").status_code == 401


def test_logout_invalidates_session(logged):
    assert logged.post("/api/logout").status_code == 200
    assert db.query("select count(*) as n from sessions")[0]["n"] == 0


def test_revoke_other_sessions(logged):
    with TestClient(app, base_url="http://localhost:8765", headers={"origin": ORIGIN}) as other:
        other.post("/api/login", json={"password": PASSWORD})
        assert logged.post("/api/sessions/revoke-others").json() == {"revoked": 1}
        assert other.get("/api/me").status_code == 401
        assert logged.get("/api/me").status_code == 200


def test_password_change_kills_sessions(logged):
    auth.set_password("outra-senha-longa")
    assert logged.get("/api/me").status_code == 401


def test_password_not_stored_in_plain_text(logged):
    stored = db.get_setting("password")
    assert PASSWORD not in stored and stored.startswith("scrypt$")
    assert PASSWORD not in str(db.query("select * from audit"))


def test_remote_session_flagged(client):
    auth.set_password(PASSWORD)
    client.post("/api/login", json={"password": PASSWORD}, headers={"x-forwarded-for": "100.64.0.2"})
    assert client.get("/api/me").json()["remote"] is True


def test_security_headers(client):
    h = client.get("/").headers
    assert h["x-frame-options"] == "DENY" and "default-src 'self'" in h["content-security-policy"]


def test_every_api_route_requires_session(client):
    """Varre todas as rotas da API: sem sessão, nenhuma pode funcionar (exceto login e logout)."""
    from fastapi.routing import APIRoute
    public = {"/api/login", "/api/logout"}
    checked = 0
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/api/") or route.path in public:
            continue
        path = route.path.replace("{", "").replace("}", "")  # parâmetros viram texto qualquer
        for method in route.methods - {"HEAD", "OPTIONS"}:
            r = client.request(method, path, json={})
            assert r.status_code == 401, f"{method} {route.path} respondeu {r.status_code} sem sessão"
            checked += 1
    assert checked >= 35  # garante que a varredura encontrou as rotas (38 em 2026-10-16)


def test_backup_and_restore(logged, tmp_path):
    """Backup com o Jarvis aberto, restauração numa pasta nova: conversas, memórias e senha voltam."""
    import zipfile
    from jarvis import backup, config, memory
    memory.add("Memória que precisa sobreviver ao backup.")
    (config.DATA_DIR / "models").mkdir(exist_ok=True)
    (config.DATA_DIR / "models" / "grande.onnx").write_bytes(b"0" * 1000)
    zip_path = backup.make_backup(tmp_path / "backups")
    names = zipfile.ZipFile(zip_path).namelist()
    assert "jarvis.db" in names and not any(n.startswith("models/") for n in names)
    restored = tmp_path / "restaurado"
    zipfile.ZipFile(zip_path).extractall(restored)
    config.DATA_DIR = restored  # o fixture isolated restaura depois
    assert memory.list_all()[0]["content"] == "Memória que precisa sobreviver ao backup."
    assert auth._password_ok(PASSWORD)
