"""Iniciar a Sarah com o Windows, sem janela: um atalho na pasta Inicializar do usuário.

Não precisa de administrador, não cria serviço e se desfaz apagando o atalho (ou pela chave na página Voz).
O atalho roda o pythonw (Python sem console); a saída vai para data/logs/servidor.log.
"""
import os
import subprocess
import sys
from pathlib import Path

from . import config

STARTUP = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup"
LINK_NAME = "Sarah (segundo plano).lnk"


def link() -> Path:
    return STARTUP / LINK_NAME


def enabled() -> bool:
    return link().exists()


def set_enabled(on: bool) -> None:
    if not on:
        link().unlink(missing_ok=True)
        return
    pythonw = Path(sys.executable).with_name("pythonw.exe")  # o da .venv do projeto
    q = lambda p: str(p).replace("'", "''")  # aspas simples do PowerShell
    script = (f"$s=(New-Object -ComObject WScript.Shell).CreateShortcut('{q(link())}'); $s.TargetPath='{q(pythonw)}'; "
              f"$s.Arguments='-m jarvis'; $s.WorkingDirectory='{q(config.ROOT)}'; "
              f"$s.IconLocation='{q(config.ROOT / 'web' / 'sarah.ico')},0'; "
              "$s.Description='Sarah: assistente pessoal em segundo plano'; $s.Save()")
    STARTUP.mkdir(parents=True, exist_ok=True)
    subprocess.run(["powershell", "-NoProfile", "-Command", script], check=True, capture_output=True, timeout=30)
