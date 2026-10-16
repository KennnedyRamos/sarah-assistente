from jarvis import config


def test_defaults_valid():
    assert config.validate() == []


def test_cloud_model_rejected(monkeypatch):
    monkeypatch.setattr(config, "MODEL", "gpt-oss:120b-cloud")
    assert any("nuvem" in e for e in config.validate())


def test_remote_llm_rejected(monkeypatch):
    monkeypatch.setattr(config, "LLM_URL", "https://api.example.com")
    assert any("não é local" in e for e in config.validate())


def test_bad_port_and_ctx(monkeypatch):
    monkeypatch.setattr(config, "PORT", 80)
    monkeypatch.setattr(config, "NUM_CTX", 512)
    assert len(config.validate()) == 2


def test_server_binds_loopback_only():
    assert config.HOST == "127.0.0.1"


def test_second_instance_refused_and_keeps_pid(tmp_path):
    """Com a porta ocupada, python -m jarvis sai antes de mexer no PID da cópia que já está rodando."""
    import os
    import socket
    import subprocess
    import sys
    with socket.socket() as busy:
        busy.bind(("127.0.0.1", 0))
        busy.listen()
        (tmp_path / "jarvis.pid").write_text("123")
        env = {**os.environ, "JARVIS_NO_DOTENV": "1", "JARVIS_DATA_DIR": str(tmp_path),
               "JARVIS_PORT": str(busy.getsockname()[1]), "PYTHONIOENCODING": "utf-8"}
        r = subprocess.run([sys.executable, "-m", "jarvis"], env=env, capture_output=True, encoding="utf-8", timeout=60)
    assert r.returncode == 1 and "já está em uso" in r.stderr
    assert (tmp_path / "jarvis.pid").read_text() == "123"


def test_dotenv_accepts_quotes_and_comments(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text('# comentário\nJARVIS_T1="com aspas"\nJARVIS_T2=\'simples\'\nJARVIS_T3=sem aspas\nJARVIS_T4="\n', encoding="utf-8")
    for k in ("JARVIS_T1", "JARVIS_T2", "JARVIS_T3", "JARVIS_T4"):
        monkeypatch.delenv(k, raising=False)
    config._load_dotenv(env)
    import os
    assert (os.environ["JARVIS_T1"], os.environ["JARVIS_T2"], os.environ["JARVIS_T3"], os.environ["JARVIS_T4"]) == \
        ("com aspas", "simples", "sem aspas", '"')
