"""Acesso remoto via Tailscale. O Jarvis não abre portas: só lê o estado do Tailscale e do `tailscale serve`,
que publica https://<pc>.<tailnet>.ts.net apenas para aparelhos da sua conta e encaminha para 127.0.0.1."""
import json
import shutil
import subprocess
from pathlib import Path

from . import config

TAILSCALE = shutil.which("tailscale") or str(Path("C:/Program Files/Tailscale/tailscale.exe"))


def _run(*args: str) -> subprocess.CompletedProcess | None:
    try:
        return subprocess.run([TAILSCALE, *args], capture_output=True, text=True, encoding="utf-8", timeout=5)
    except (OSError, subprocess.TimeoutExpired):
        return None


def status() -> dict:
    r = _run("status", "--json")
    if r is None:
        return {"installed": False, "online": False}
    try:
        s = json.loads(r.stdout or "{}")
    except ValueError:
        return {"installed": True, "online": False}
    name = (s.get("Self") or {}).get("DNSName", "").rstrip(".").lower()
    serve = _run("serve", "status", "--json")
    # o serve encaminha para http://127.0.0.1:<porta>; confere se é para a porta do Jarvis
    serving = bool(serve and serve.returncode == 0 and f"127.0.0.1:{config.PORT}" in (serve.stdout or ""))
    return {"installed": True, "online": s.get("BackendState") == "Running", "name": name,
            "url": f"https://{name}" if name and serving else "", "serving": serving}
