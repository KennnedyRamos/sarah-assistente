"""Inicia o servidor: python -m jarvis"""
import os
import socket
import sys

import uvicorn

from . import config

with socket.socket() as probe:  # antes de gravar o PID: uma 2ª cópia não pode apagar o PID da que já está rodando
    try:
        probe.bind((config.HOST, config.PORT))
    except OSError:
        sys.exit(f"[Sarah] A porta {config.PORT} já está em uso: a Sarah já está rodando? Use parar.bat antes.")
pid_file = config.DATA_DIR / "jarvis.pid"
config.DATA_DIR.mkdir(parents=True, exist_ok=True)
windowless = sys.stdout is None  # iniciado pelo pythonw (com o Windows, sem janela)
if windowless:
    (config.DATA_DIR / "logs").mkdir(exist_ok=True)
    sys.stdout = sys.stderr = open(config.DATA_DIR / "logs" / "servidor.log", "a", encoding="utf-8", buffering=1)
pid_file.write_text(str(os.getpid()))
try:
    # sem janela, o registro de cada requisição só encheria o arquivo (a página consulta o estado a cada poucos segundos)
    uvicorn.run("jarvis.main:app", host=config.HOST, port=config.PORT, log_level="info", access_log=not windowless)
finally:
    pid_file.unlink(missing_ok=True)
