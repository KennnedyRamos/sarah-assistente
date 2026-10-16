"""Agente de programação: trabalha numa cópia isolada do projeto ("área"), verifica e só integra com confirmação.

Isolamento possível sem administrador nem Docker:
- o projeto é copiado para data/workspace/.areas/<id>; o original só muda por integrar_alteracoes
  (confirmação com diff + backup, reversível por reverter_integracao);
- só os comandos de VERIFICACOES rodam, sem shell e com tempo limite;
- ambiente limpo: sem variáveis com tokens/senhas, e perfil, APPDATA e TEMP apontando para a área
  (o processo não enxerga ~/.npmrc, pip.ini, credenciais do git etc. pelo caminho padrão);
- Job Object do Windows: limite de memória e de processos; ao terminar, cancelar ou estourar o tempo,
  a árvore inteira de processos é morta.
Limite: não há bloqueio de rede nem de leitura de arquivos do usuário (o processo roda com o seu usuário).
"""
import asyncio
import difflib
import hashlib
import json
import os
import re
import shutil
import sys
import time
import uuid
from pathlib import Path

from . import config
from .tools import MAX_WRITE_CHARS, ToolError, _str, allowed_path, run_process, tool, workspace

META = ".jarvis-area.json"
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache", ".dart_tool",
             "build", "dist", ".jarvis-home", ".idea", ".gradle", ".mypy_cache"}
NEVER_WRITE = {".exe", ".dll", ".scr", ".com", ".msi", ".lnk", ".sys"}
MAX_FILES, MAX_BYTES = 3000, 100_000_000
LIMITS = (2048, 64)  # 2 GB de memória e 64 processos por verificação
SECRET_ENV = re.compile(r"TOKEN|SECRET|PASSWORD|PASSWD|KEY|CREDENTIAL|AUTH|COOKIE|SESSION", re.I)


def areas_root() -> Path:
    p = workspace() / ".areas"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _area(area_id: str) -> Path:
    if not re.fullmatch(r"[\w.-]{1,80}", area_id or ""):
        raise ToolError("Id de área inválido.")
    p = areas_root() / area_id
    if not (p / META).is_file():
        raise ToolError(f"A área '{area_id}' não existe. Use preparar_area primeiro.")
    return p


def _meta(area: Path) -> dict:
    return json.loads((area / META).read_text(encoding="utf-8"))


def _save_meta(area: Path, meta: dict) -> None:
    (area / META).write_text(json.dumps(meta, ensure_ascii=False, indent=1), encoding="utf-8")


def _inside(area: Path, rel: str) -> Path:
    p = (area / rel).resolve()
    root = area.resolve()
    if not p.is_relative_to(root) or p == root or p.name == META:
        raise ToolError(f"Caminho fora da área de trabalho: {rel}")
    return p


def _files(root: Path) -> dict[str, Path]:
    """Arquivos do projeto (caminho relativo com /), sem pastas geradas ou pesadas."""
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f != META:
                full = Path(dirpath) / f
                out[full.relative_to(root).as_posix()] = full
                if len(out) > MAX_FILES:
                    raise ToolError(f"Projeto com mais de {MAX_FILES} arquivos; escolha uma subpasta.")
    return out


def _tree(root: Path, limit: int = 200) -> str:
    files = sorted(_files(root))
    lines = [f"  {f} ({(root / f).stat().st_size} bytes)" for f in files[:limit]]
    more = f"\n  … e mais {len(files) - limit} arquivos" if len(files) > limit else ""
    return f"{len(files)} arquivos:\n" + "\n".join(lines) + more if files else "(vazia)"


def _sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def _text(p: Path | None) -> str | None:
    if p is None:
        return ""
    data = p.read_bytes()
    return None if b"\0" in data[:4096] else data.decode("utf-8", errors="replace")


def _changes(area: Path):
    origin = Path(_meta(area)["origem"])
    new = _files(area)
    old = _files(origin) if origin.is_dir() else {}
    added = sorted(set(new) - set(old))
    removed = sorted(set(old) - set(new))
    changed = sorted(r for r in set(new) & set(old) if new[r].read_bytes() != old[r].read_bytes())
    return origin, old, new, added, changed, removed


def _diff(old: dict, new: dict, rels: list[str], limit: int = 8000) -> str:
    out = []
    for r in rels:
        a, b = _text(old.get(r)), _text(new[r])
        if a is None or b is None:
            out.append(f"(arquivo binário) {r}")
            continue
        out += difflib.unified_diff(a.splitlines(), b.splitlines(), f"original/{r}", f"area/{r}", lineterm="", n=2)
    text = "\n".join(out)
    return text[:limit] + ("\n[diff cortado]" if len(text) > limit else "")


def _status(area_id: str) -> str:
    origin, _old, _new, added, changed, removed = _changes(_area(area_id))
    parts = [f"{len(added)} novo(s)", f"{len(changed)} alterado(s)"] + ([f"{len(removed)} removido(s)"] if removed else [])
    names = ", ".join((added + changed)[:12]) + (" …" if len(added + changed) > 12 else "")
    return f"{', '.join(parts)} em relação a {origin}" + (f": {names}" if names else "")


def list_areas() -> list[dict]:
    out = []
    for p in sorted(areas_root().iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
        if (p / META).is_file():
            out.append({"id": p.name, "origem": _meta(p)["origem"]})
    return out


# ---------- Ferramentas do modo programação ----------

@tool("estrutura_projeto", "Estrutura do projeto", "Lista todos os arquivos de um projeto (recursivo, sem pastas geradas).",
      "leitura", {"pasta": _str("Pasta do projeto ou id de área")}, ("pasta",), group="codigo")
async def estrutura_projeto(args, ctx):
    p = areas_root() / args["pasta"] if (areas_root() / args["pasta"] / META).is_file() else allowed_path(args["pasta"])
    if not p.is_dir():
        raise ToolError(f"Não é uma pasta: {p}")
    return f"{p}\n{_tree(p, 300)}"


@tool("preparar_area", "Preparar área isolada", "Cria uma cópia isolada de um projeto existente, ou uma área vazia para um "
      "projeto novo. Todo código é escrito e testado nela; o original não muda.", "acao",
      {"projeto": _str("Pasta do projeto existente, ou pasta nova onde o projeto ficará")}, ("projeto",), group="codigo")
async def preparar_area(args, ctx):
    origin = allowed_path(args["projeto"])
    if origin.is_relative_to(areas_root().resolve()):
        raise ToolError("Essa pasta já é uma área de trabalho; use o id dela.")
    if origin.exists() and not origin.is_dir():
        raise ToolError(f"Não é uma pasta: {origin}")
    files = _files(origin) if origin.exists() else {}
    if sum(f.stat().st_size for f in files.values()) > MAX_BYTES:
        raise ToolError("Projeto grande demais (mais de 100 MB sem contar pastas geradas).")
    slug = re.sub(r"[^\w-]", "", origin.name)[:40] or "projeto"
    area_id = f"{slug}-{uuid.uuid4().hex[:6]}"
    area = areas_root() / area_id
    area.mkdir()
    for rel, src in files.items():
        (area / rel).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, area / rel)
    _save_meta(area, {"origem": str(origin), "novo": not origin.exists(), "criada": time.time(), "integracoes": []})
    kind = "projeto NOVO (será criado na integração)" if not origin.exists() else f"cópia de {origin}"
    return f"Área '{area_id}' pronta: {kind}. Use area=\"{area_id}\" nas próximas ferramentas.\n{_tree(area)}"


@tool("escrever_arquivo", "Escrever arquivo na área", "Cria ou substitui um arquivo DENTRO de uma área de trabalho. "
      "Envie o conteúdo completo do arquivo.", "acao",
      {"area": _str("Id da área"), "caminho": _str("Caminho relativo dentro da área, ex.: src/app.py"),
       "conteudo": _str("Conteúdo completo do arquivo")}, ("area", "caminho"), group="codigo")
async def escrever_arquivo(args, ctx):
    area = _area(args["area"])
    p = _inside(area, args["caminho"])
    if p.suffix.lower() in NEVER_WRITE:
        raise ToolError(f"Não escrevo arquivos binários executáveis ({p.suffix}).")
    content = args.get("conteudo", "")
    if len(content) > MAX_WRITE_CHARS:
        raise ToolError("Conteúdo grande demais.")
    existed = p.exists()
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(content, encoding="utf-8", newline="")
    return f"{'Atualizado' if existed else 'Criado'}: {p.relative_to(area).as_posix()} ({content.count(chr(10)) + 1} linhas)"


@tool("ver_alteracoes", "Ver alterações", "Mostra o diff entre a área de trabalho e o projeto original.", "leitura",
      {"area": _str("Id da área")}, ("area",), group="codigo")
async def ver_alteracoes(args, ctx):
    _origin, old, new, added, changed, removed = _changes(_area(args["area"]))
    head = _status(args["area"])
    if removed:
        head += f"\nRemovidos na área (não serão apagados no original): {', '.join(removed)}"
    return f"{head}\n\n{_diff(old, new, added + changed, 5000)}" if added or changed else head


def _python(area: Path) -> str:
    venv = area / ".venv" / "Scripts" / "python.exe"
    return str(venv) if venv.exists() else getattr(sys, "_base_executable", sys.executable)


VERIFICACOES = {  # nome: (risco, função que monta o comando). Só isto pode ser executado.
    "compilar_python": ("acao", lambda a, f: [_python(a), "-m", "compileall", "-q", "."]),
    "lint_python": ("acao", lambda a, f: [_python(a), "-m", "ruff", "check", "."]),
    "testes_python": ("perigosa", lambda a, f: [_python(a), "-m", "pytest", "-q", "-p", "no:cacheprovider"]),
    "executar_python": ("perigosa", lambda a, f: [_python(a), f]),
    "instalar_dependencias_python": ("perigosa", None),
    "verificar_js": ("acao", lambda a, f: ["node", "--check", f]),
    "instalar_dependencias_node": ("perigosa", lambda a, f: ["cmd", "/c", "npm", "install", "--no-audit", "--no-fund"]),
    "testes_node": ("perigosa", lambda a, f: ["cmd", "/c", "npm", "test"]),
    "build_node": ("perigosa", lambda a, f: ["cmd", "/c", "npm", "run", "build"]),
    "analise_flutter": ("perigosa", lambda a, f: ["cmd", "/c", "flutter", "analyze"]),
    "testes_flutter": ("perigosa", lambda a, f: ["cmd", "/c", "flutter", "test"]),
}
NEEDS_FILE = {"executar_python": ".py", "verificar_js": (".js", ".mjs", ".cjs")}


def sandbox_env(area: Path) -> dict:
    keep = {"SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT", "PATH", "NUMBER_OF_PROCESSORS", "PROCESSOR_ARCHITECTURE",
            "OS", "SYSTEMDRIVE", "PROGRAMFILES", "PROGRAMFILES(X86)", "PROGRAMDATA", "FLUTTER_ROOT", "JAVA_HOME"}
    env = {k: v for k, v in os.environ.items() if k.upper() in keep and not SECRET_ENV.search(k)}
    home = area / ".jarvis-home"
    for sub in ("tmp", "roaming", "local"):
        (home / sub).mkdir(parents=True, exist_ok=True)
    real_local = os.environ.get("LOCALAPPDATA", "")
    env.update(USERPROFILE=str(home), HOME=str(home), TEMP=str(home / "tmp"), TMP=str(home / "tmp"),
               APPDATA=str(home / "roaming"), LOCALAPPDATA=str(home / "local"), PYTHONUTF8="1", PYTHONIOENCODING="utf-8",
               PYTHONDONTWRITEBYTECODE="1", NO_COLOR="1",
               # caches de pacotes reaproveitados (não têm credenciais): evita baixar tudo de novo em cada área
               PIP_CACHE_DIR=str(Path(real_local) / "pip" / "Cache"),
               npm_config_cache=str(Path(real_local) / "npm-cache"),
               PUB_CACHE=str(Path(real_local) / "Pub" / "Cache"))
    return env


def _check_risk(args):
    return VERIFICACOES.get(args.get("acao"), ("perigosa",))[0]


def _check_detail(args):
    if args.get("acao") != "instalar_dependencias_python":
        return ""
    req = _area(args["area"]) / "requirements.txt"
    return f"requirements.txt:\n{req.read_text(encoding='utf-8', errors='replace')[:3000]}" if req.exists() else ""


@tool("executar_verificacao", "Verificar código", "Roda uma verificação na área: compilar, lint, testes, executar um script "
      "ou instalar dependências do projeto (só dentro da área).", "perigosa",
      {"area": _str("Id da área"), "acao": _str("Qual verificação", enum=list(VERIFICACOES)),
       "arquivo": _str("Arquivo, só para executar_python e verificar_js")}, ("area", "acao"), timeout=900,
      risk_for=_check_risk, detail=_check_detail, group="codigo",
      describe=lambda a: f"Rodar '{a.get('acao')}' na área {a.get('area')}. O código do projeto roda com o seu usuário, "
                         "sem bloqueio de rede, com limite de 2 GB de memória e tempo limite")
async def executar_verificacao(args, ctx):
    area = _area(args["area"])
    acao, arquivo = args["acao"], args.get("arquivo", "")
    if acao in NEEDS_FILE:
        if not arquivo.lower().endswith(NEEDS_FILE[acao]):
            raise ToolError(f"'{acao}' precisa de um arquivo {NEEDS_FILE[acao]} da área.")
        arquivo = str(_inside(area, arquivo).relative_to(area.resolve()))
    env = sandbox_env(area)

    async def run(argv, timeout):
        try:
            return await asyncio.wait_for(run_process(argv, ctx, cwd=str(area), stream=True, check=True, env=env,
                                                      limits=LIMITS, encoding="utf-8"), timeout)
        except TimeoutError:
            raise ToolError(f"Passou do tempo limite de {timeout} s; todos os processos foram encerrados.") from None
    if acao == "instalar_dependencias_python":
        if not (area / "requirements.txt").exists():
            raise ToolError("Crie um requirements.txt na área antes de instalar dependências.")
        out = ""
        if not (area / ".venv").exists():
            out = await run([getattr(sys, "_base_executable", sys.executable), "-m", "venv", ".venv"], 180)
        out += await run([_python(area), "-m", "pip", "install", "--disable-pip-version-check", "-r", "requirements.txt"], 600)
        return out or "Dependências instaladas na .venv da área."
    out = await run(VERIFICACOES[acao][1](area, arquivo), 300)
    return out or f"'{acao}' terminou sem erros e sem saída."


def _integration_detail(args):
    _origin, old, new, added, changed, _removed = _changes(_area(args["area"]))
    return _diff(old, new, added + changed, 12000)


@tool("integrar_alteracoes", "Integrar alterações no projeto", "Copia os arquivos novos e alterados da área para o projeto "
      "original (com backup). Só use quando o usuário pedir para aplicar.", "perigosa",
      {"area": _str("Id da área")}, ("area",), group="codigo", timeout=120,
      describe=lambda a: f"Aplicar no projeto original: {_status(a.get('area', ''))}", detail=_integration_detail)
async def integrar_alteracoes(args, ctx):
    area = _area(args["area"])
    meta = _meta(area)
    origin, old, new, added, changed, removed = _changes(area)
    if not added and not changed:
        return "Nada para integrar: a área é igual ao original."
    allowed_path(str(origin))  # a pasta pode ter deixado de ser autorizada
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = config.DATA_DIR / "backups" / f"integracao-{area.name}-{stamp}"
    for r in changed:
        (backup / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(old[r], backup / r)
    for r in added + changed:
        (origin / r).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(new[r], origin / r)
    meta["integracoes"].append({"backup": str(backup), "adicionados": added, "alterados": changed,
                                "hashes": {r: _sha(new[r]) for r in added + changed}, "quando": stamp})
    _save_meta(area, meta)
    msg = f"Integrado em {origin}: {len(added)} novo(s), {len(changed)} alterado(s). Backup dos alterados: {backup}."
    if removed:
        msg += f" Não apaguei {len(removed)} arquivo(s) que não existem na área: {', '.join(removed[:10])}."
    if (origin / ".git").exists():
        msg += " Nada foi commitado: revise com 'git status' e 'git diff'."
    return msg


@tool("reverter_integracao", "Reverter integração", "Desfaz a última integração de uma área: restaura os arquivos "
      "alterados e remove os criados (se você não os editou depois).", "perigosa",
      {"area": _str("Id da área")}, ("area",), group="codigo",
      describe=lambda a: f"Desfazer a última integração da área {a.get('area')}")
async def reverter_integracao(args, ctx):
    area = _area(args["area"])
    meta = _meta(area)
    if not meta["integracoes"]:
        raise ToolError("Essa área não tem integração para desfazer.")
    last = meta["integracoes"][-1]
    origin, backup = Path(meta["origem"]), Path(last["backup"])
    allowed_path(str(origin))
    restored, removed, kept = [], [], []
    for r in last["alterados"] + last["adicionados"]:
        dst = origin / r
        if dst.exists() and _sha(dst) != last["hashes"][r]:
            kept.append(r)  # editado depois da integração: não mexo
        elif r in last["alterados"]:
            shutil.copy2(backup / r, dst)
            restored.append(r)
        elif dst.exists():
            dst.unlink()
            removed.append(r)
    meta["integracoes"].pop()
    _save_meta(area, meta)
    msg = f"Revertido: {len(restored)} restaurado(s), {len(removed)} removido(s)."
    return msg + (f" Mantidos por terem sido editados depois: {', '.join(kept)}." if kept else "")


@tool("descartar_area", "Descartar área", "Apaga uma área de trabalho (o projeto original não é afetado).", "acao",
      {"area": _str("Id da área")}, ("area",), group="codigo")
async def descartar_area(args, ctx):
    area = _area(args["area"])
    shutil.rmtree(area)
    return f"Área {area.name} descartada."
