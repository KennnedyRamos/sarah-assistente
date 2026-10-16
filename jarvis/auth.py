"""Senha local, sessões e verificação de Host/Origin (DNS rebinding e CSRF)."""
import hashlib
import hmac
import secrets
import time
from urllib.parse import urlparse

from fastapi import HTTPException, Request

from . import config, db

COOKIE = "jarvis_session"
MAX_FAILURES, FAILURE_WINDOW = 5, 300  # 5 erros em 5 min bloqueiam o login por 5 min
_failures: list[float] = []


def _scrypt(password: str, salt: bytes) -> bytes:
    return hashlib.scrypt(password.encode(), salt=salt, n=2**14, r=8, p=1)


def set_password(password: str) -> None:
    if len(password) < 10:
        raise ValueError("A senha precisa ter pelo menos 10 caracteres.")
    salt = secrets.token_bytes(16)
    db.set_setting("password", f"scrypt${salt.hex()}${_scrypt(password, salt).hex()}")
    db.execute("delete from sessions")  # trocar a senha derruba todas as sessões
    db.audit("local", "senha_definida")


def password_configured() -> bool:
    return db.get_setting("password") is not None


def _password_ok(password: str) -> bool:
    _, salt, expected = db.get_setting("password").split("$")
    return hmac.compare_digest(_scrypt(password, bytes.fromhex(salt)).hex(), expected)


def login(password: str, user_agent: str, remote: bool) -> str:
    """Retorna o token da nova sessão ou levanta HTTPException."""
    if not password_configured():
        raise HTTPException(503, "Senha ainda não definida. Execute iniciar.bat ou 'python -m jarvis.setpass'.")
    now = time.time()
    _failures[:] = [t for t in _failures if now - t < FAILURE_WINDOW]
    if len(_failures) >= MAX_FAILURES:
        raise HTTPException(429, "Muitas tentativas. Aguarde alguns minutos.")
    if not _password_ok(password):
        _failures.append(now)
        db.audit("remoto" if remote else "local", "login_falhou")
        raise HTTPException(401, "Senha incorreta.")
    _failures.clear()
    db.execute("delete from sessions where expires_at <= ?", (now,))  # limpeza: sessões vencidas não servem mais
    token = secrets.token_urlsafe(32)
    db.execute("insert into sessions(token_hash, created_at, expires_at, user_agent, remote) values (?,?,?,?,?)",
               (_hash(token), now, now + config.SESSION_HOURS * 3600, user_agent[:200], int(remote)))
    db.audit("remoto" if remote else "local", "login")
    return token


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def session_from_token(token: str | None) -> dict | None:
    if not token:
        return None
    rows = db.query("select rowid as id, * from sessions where token_hash = ? and expires_at > ?",
                    (_hash(token), time.time()))
    return rows[0] if rows else None


def logout(token: str | None) -> None:
    if token:
        db.execute("delete from sessions where token_hash = ?", (_hash(token),))


def is_remote(headers) -> bool:
    # tailscale serve encaminha para 127.0.0.1 e acrescenta estes cabeçalhos
    return "x-forwarded-for" in headers or "tailscale-user-login" in headers


def host_allowed(host: str | None) -> bool:
    return bool(host) and urlparse("//" + host).hostname in config.ALLOWED_HOSTS


def origin_allowed(headers) -> bool:
    """Origin precisa ser exatamente o mesmo host:porta da requisição (same-origin)."""
    origin, host = headers.get("origin"), headers.get("host")
    return bool(origin and host) and urlparse(origin).netloc == host and host_allowed(host)


def require_session(request: Request) -> dict:
    session = session_from_token(request.cookies.get(COOKIE))
    if not session:
        raise HTTPException(401, "Sessão inválida ou expirada. Faça login.")
    return session
