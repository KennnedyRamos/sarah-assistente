import asyncio
import subprocess
import sys

import pytest

from jarvis import coding, db, llm, tools

from .conftest import WS

HAS_PYTEST = subprocess.run([getattr(sys, "_base_executable", sys.executable), "-c", "import pytest"],
                            capture_output=True).returncode == 0


def run(coro):
    return asyncio.run(coro)


def execute(name, args, approve=False, mode="codigo", seen=None, remote=False):
    async def emit(ev):
        pass

    async def decide(label, summary, detail=""):
        if seen is not None:
            seen.append((summary, detail))
        return approve
    return run(tools.execute(name, args, tools.Context(remote=remote, emit=emit, approve=decide, mode=mode)))


@pytest.fixture
def project():
    p = tools.workspace() / "meuapp"
    (p / "src").mkdir(parents=True)
    (p / "src" / "calc.py").write_text("def soma(a, b):\n    return a - b\n", encoding="utf-8")
    (p / "README.md").write_text("# Meu app\n", encoding="utf-8")
    (p / "node_modules" / "lib").mkdir(parents=True)
    (p / "node_modules" / "lib" / "x.js").write_text("pesado")
    (p / "__pycache__").mkdir()
    (p / "__pycache__" / "a.pyc").write_bytes(b"\0")
    return p


def area_id(out: str) -> str:
    return out.split("'")[1]


def prepare(path) -> str:
    ok, out = execute("preparar_area", {"projeto": str(path)})
    assert ok, out
    return area_id(out)


# ---------- Área isolada ----------

def test_prepare_copies_without_heavy_dirs(project):
    a = prepare(project)
    area = coding.areas_root() / a
    assert (area / "src" / "calc.py").exists() and (area / "README.md").exists()
    assert not (area / "node_modules").exists() and not (area / "__pycache__").exists()


def test_new_project_starts_empty():
    ok, out = execute("preparar_area", {"projeto": "projetos/novo"})
    assert ok and "projeto NOVO" in out
    assert not (tools.workspace() / "projetos" / "novo").exists()  # só nasce na integração


def test_prepare_outside_authorized_dirs_blocked():
    ok, out = execute("preparar_area", {"projeto": "C:\\Windows\\System32"})
    assert not ok and "fora das pastas autorizadas" in out


def test_write_cannot_escape_area(project):
    a = prepare(project)
    for bad in ("..\\..\\fora.txt", "C:\\Windows\\fora.txt", coding.META, "..\\" + a + "x\\y.txt"):
        ok, out = execute("escrever_arquivo", {"area": a, "caminho": bad, "conteudo": "x"})
        assert not ok and "fora da área" in out, bad
    ok, out = execute("escrever_arquivo", {"area": a, "caminho": "malware.exe", "conteudo": "x"})
    assert not ok and "executáveis" in out


def test_invalid_area_ids_rejected():
    for bad in ("..", "../workspace", "x/y", ""):
        ok, out = execute("ver_alteracoes", {"area": bad})
        assert not ok


def test_original_untouched_until_integration(project):
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "src/calc.py", "conteudo": "def soma(a, b):\n    return a + b\n"})
    assert "a - b" in (project / "src" / "calc.py").read_text()


def test_diff_shows_changes(project):
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "src/calc.py", "conteudo": "def soma(a, b):\n    return a + b\n"})
    execute("escrever_arquivo", {"area": a, "caminho": "tests/test_calc.py", "conteudo": "x = 1\n"})
    (coding.areas_root() / a / "README.md").unlink()
    ok, out = execute("ver_alteracoes", {"area": a})
    assert ok and "1 novo(s), 1 alterado(s), 1 removido(s)" in out
    assert "-    return a - b" in out and "+    return a + b" in out and "tests/test_calc.py" in out


def test_tree_tool(project):
    ok, out = execute("estrutura_projeto", {"pasta": str(project)})
    assert ok and "src/calc.py" in out and "node_modules" not in out


# ---------- Verificações ----------

def test_compile_is_action_and_reports_syntax_errors(project):
    a = prepare(project)
    assert execute("executar_verificacao", {"area": a, "acao": "compilar_python"})[0]  # sem confirmação
    execute("escrever_arquivo", {"area": a, "caminho": "src/ruim.py", "conteudo": "def x(:\n"})
    ok, out = execute("executar_verificacao", {"area": a, "acao": "compilar_python"})
    assert not ok and "SyntaxError" in out


def test_running_code_needs_confirmation(project):
    a = prepare(project)
    ok, out = execute("executar_verificacao", {"area": a, "acao": "testes_python"}, approve=True)
    assert out.startswith("[SIMULAÇÃO]")  # modo padrão
    tools.save_settings("normal", [])
    ok, out = execute("executar_verificacao", {"area": a, "acao": "testes_python"}, approve=False)
    assert not ok and "recusou" in out


@pytest.mark.skipif(not HAS_PYTEST, reason="pytest não instalado no Python base")
def test_pytest_pass_and_fail(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "test_calc.py",
                                 "conteudo": "from src.calc import soma\n\ndef test_soma():\n    assert soma(2, 3) == 5\n"})
    ok, out = execute("executar_verificacao", {"area": a, "acao": "testes_python"}, approve=True)
    assert not ok and "1 failed" in out and "assert -1 == 5" in out
    execute("escrever_arquivo", {"area": a, "caminho": "src/calc.py", "conteudo": "def soma(a, b):\n    return a + b\n"})
    ok, out = execute("executar_verificacao", {"area": a, "acao": "testes_python"}, approve=True)
    assert ok and "1 passed" in out


def test_clean_environment(project, monkeypatch):
    tools.save_settings("normal", [])
    monkeypatch.setenv("GITHUB_TOKEN", "segredo-123")
    monkeypatch.setenv("MINHA_API_KEY", "segredo-456")
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "env.py",
                                 "conteudo": "import os\nprint(sorted(os.environ.items()))\nprint('HOME=' + os.environ['USERPROFILE'])\n"})
    ok, out = execute("executar_verificacao", {"area": a, "acao": "executar_python", "arquivo": "env.py"}, approve=True)
    assert ok and "segredo" not in out
    assert f"HOME={coding.areas_root() / a / '.jarvis-home'}" in out


def test_memory_limit(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "guloso.py", "conteudo": "x = bytearray(3 * 1024**3)\nprint('alocou')\n"})
    ok, out = execute("executar_verificacao", {"area": a, "acao": "executar_python", "arquivo": "guloso.py"}, approve=True)
    assert not ok and "MemoryError" in out and "alocou" not in out


def test_cancel_kills_whole_process_tree(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    marker = (tools.workspace() / "neto.txt").as_posix()
    neto = f"import time; time.sleep(2); open('{marker}', 'w').write('x')"
    execute("escrever_arquivo", {"area": a, "caminho": "pai.py", "conteudo":
            f"import subprocess, sys, time\nsubprocess.Popen([sys.executable, '-c', {neto!r}])\ntime.sleep(30)\n"})

    async def emit(ev):
        pass

    async def yes(*_):
        return True

    async def scenario():
        ctx = tools.Context(remote=False, emit=emit, approve=yes, mode="codigo")
        task = asyncio.create_task(tools.execute("executar_verificacao",
                                                 {"area": a, "acao": "executar_python", "arquivo": "pai.py"}, ctx))
        await asyncio.sleep(1)
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        await asyncio.sleep(2.5)
    run(scenario())
    assert not (tools.workspace() / "neto.txt").exists()


def test_install_requires_requirements_and_shows_it(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    ok, out = execute("executar_verificacao", {"area": a, "acao": "instalar_dependencias_python"}, approve=True)
    assert not ok and "requirements.txt" in out
    execute("escrever_arquivo", {"area": a, "caminho": "requirements.txt", "conteudo": "requests==2.32.0\n"})
    seen = []
    execute("executar_verificacao", {"area": a, "acao": "instalar_dependencias_python"}, approve=False, seen=seen)
    assert "requests==2.32.0" in seen[0][1]  # o usuário vê exatamente o que será instalado


def test_file_argument_validated(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    ok, out = execute("executar_verificacao", {"area": a, "acao": "executar_python", "arquivo": "README.md"}, approve=True)
    assert not ok and ".py" in out
    ok, out = execute("executar_verificacao", {"area": a, "acao": "executar_python", "arquivo": "..\\..\\x.py"}, approve=True)
    assert not ok and "fora da área" in out


# ---------- Integração e reversão ----------

def test_integrate_shows_diff_backs_up_and_reverts(project):
    tools.save_settings("normal", [])
    (project / ".git").mkdir()
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "src/calc.py", "conteudo": "def soma(a, b):\n    return a + b\n"})
    execute("escrever_arquivo", {"area": a, "caminho": "tests/test_calc.py", "conteudo": "ok = True\n"})
    seen = []
    ok, out = execute("integrar_alteracoes", {"area": a}, approve=False, seen=seen)
    assert not ok and "a - b" in (project / "src" / "calc.py").read_text()
    summary, detail = seen[0]
    assert "1 novo(s), 1 alterado(s)" in summary and "+    return a + b" in detail
    ok, out = execute("integrar_alteracoes", {"area": a}, approve=True)
    assert ok and "Nada foi commitado" in out
    assert "a + b" in (project / "src" / "calc.py").read_text() and (project / "tests" / "test_calc.py").exists()
    ok, out = execute("reverter_integracao", {"area": a}, approve=True)
    assert ok and "1 restaurado(s), 1 removido(s)" in out
    assert "a - b" in (project / "src" / "calc.py").read_text() and not (project / "tests" / "test_calc.py").exists()


def test_revert_keeps_files_edited_after_integration(project):
    tools.save_settings("normal", [])
    a = prepare(project)
    execute("escrever_arquivo", {"area": a, "caminho": "src/calc.py", "conteudo": "def soma(a, b):\n    return a + b\n"})
    execute("integrar_alteracoes", {"area": a}, approve=True)
    (project / "src" / "calc.py").write_text("# editado por você depois\n")
    ok, out = execute("reverter_integracao", {"area": a}, approve=True)
    assert ok and "Mantidos" in out and (project / "src" / "calc.py").read_text() == "# editado por você depois\n"


def test_new_project_created_on_integration():
    tools.save_settings("normal", [])
    a = area_id(execute("preparar_area", {"projeto": "projetos/ola"})[1])
    execute("escrever_arquivo", {"area": a, "caminho": "main.py", "conteudo": "print('olá')\n"})
    assert execute("integrar_alteracoes", {"area": a}, approve=True)[0]
    assert (tools.workspace() / "projetos" / "ola" / "main.py").read_text(encoding="utf-8") == "print('olá')\n"


def test_discard_area(project):
    a = prepare(project)
    assert execute("descartar_area", {"area": a})[0]
    assert not (coding.areas_root() / a).exists() and project.exists()


# ---------- Modos ----------

def test_tool_sets_per_mode():
    geral = {t.name for t in tools.available(False, "geral")}
    codigo = {t.name for t in tools.available(False, "codigo")}
    assert "preparar_area" not in geral and "abrir_aplicativo" not in codigo
    assert {"ler_arquivo", "listar_arquivos", "preparar_area", "executar_verificacao"} <= codigo
    ok, out = execute("preparar_area", {"projeto": "x"}, mode="geral")
    assert not ok and "não está disponível" in out


def test_remote_coding_is_read_only(project):
    tools.save_settings("normal", [])
    assert {t.risk for t in tools.available(True, "codigo")} == {"leitura"}
    ok, _ = execute("preparar_area", {"projeto": str(project)}, remote=True)
    assert not ok


def test_chat_coding_mode_uses_coding_prompt_and_tools(logged, monkeypatch):
    seen = []

    async def chat(messages, tools_=None):
        seen.append((messages, tools_))
        yield {"type": "token", "text": "ok"}
    monkeypatch.setattr(llm, "chat", chat)
    with logged.websocket_connect(WS) as ws:
        ws.send_json({"type": "chat", "text": "Crie um projeto", "mode": "codigo"})
        while ws.receive_json()["type"] != "done":
            pass
        ws.send_json({"type": "chat", "text": "Oi"})
        while ws.receive_json()["type"] != "done":
            pass
    (code_msgs, code_tools), (gen_msgs, gen_tools) = seen
    assert code_msgs[0]["content"].startswith("Você é a Sarah no modo programação")
    assert "preparar_area" in {t["function"]["name"] for t in code_tools}
    assert "preparar_area" not in {t["function"]["name"] for t in gen_tools}
    assert db.query("select count(*) as n from conversations")[0]["n"] == 2
