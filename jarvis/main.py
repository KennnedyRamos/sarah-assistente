"""Aplicação FastAPI: API REST, WebSocket do chat e interface web."""
import asyncio
import contextlib
import io
import json
import logging
import re
import time
import uuid
from collections import defaultdict, deque
from contextlib import asynccontextmanager
from logging.handlers import RotatingFileHandler
from pathlib import Path

import soundfile as sf
from fastapi import Depends, FastAPI, HTTPException, Request, Response, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from . import agent, auth, autostart, camera, config, db, face, google_api, listener, llm, memory, remote, storage, tools, vision, voice

log = logging.getLogger("jarvis")
MAX_MESSAGE = 8000
RATE_LIMIT = 240  # requisições por minuto por cliente na API
_hits: dict[str, deque] = defaultdict(deque)
SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Content-Security-Policy": "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
                               "connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'",
}


def setup_logging() -> None:
    if log.handlers:
        return
    (config.DATA_DIR / "logs").mkdir(parents=True, exist_ok=True)
    handler = RotatingFileHandler(config.DATA_DIR / "logs" / "jarvis.log", maxBytes=1_000_000,
                                  backupCount=5, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    errors = config.validate()
    if errors:
        raise SystemExit("Configuração inválida:\n- " + "\n- ".join(errors))
    db.init()
    storage.maintain()
    setup_logging()
    log.info("Sarah iniciada em %s:%s com o modelo %s", config.HOST, config.PORT, config.MODEL)
    loop = asyncio.get_running_loop()
    app.state.listener = listener.Listener(
        on_wake=lambda source, text="": asyncio.run_coroutine_threadsafe(broadcast_wake(source, text), loop))
    # o modo escolhido em Voz (menu ☰) vale mais que o .env (assim não se perde ao reiniciar)
    wake = db.get_setting("wake_mode") or config.WAKE_MODE
    if wake != "off":
        await asyncio.to_thread(app.state.listener.set_mode, wake)
    st = await refresh_remote()
    if st.get("url"):
        print(f"[Sarah] Pelo celular (Tailscale): {st['url']}", flush=True)

    async def keep_remote_fresh():  # o Tailscale pode conectar depois da Sarah (ex.: logo após ligar o PC)
        while True:
            await asyncio.sleep(60)
            try:
                await refresh_remote()
            except Exception:  # um erro passageiro não pode parar a atualização para sempre
                log.exception("Falha ao ler o estado do Tailscale")
    async def keep_listening():  # microfone desconectado ou trocado: a escuta volta sozinha quando ele reaparecer
        while True:
            await asyncio.sleep(20)
            if not app.state.listener.healthy():
                await asyncio.to_thread(app.state.listener.recover)
    refresher, watcher = spawn(keep_remote_fresh()), spawn(keep_listening())
    yield
    refresher.cancel()
    watcher.cancel()
    app.state.listener.stop()
    log.info("Sarah encerrada")


app = FastAPI(lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)
local_clients: set[WebSocket] = set()  # interfaces abertas no próprio PC (recebem o aviso de acionamento)
CLIENTS: dict[WebSocket, bool] = {}     # todas as páginas abertas → é sessão remota (celular)?
DEVICE_REQUESTS: dict[str, asyncio.Future] = {}
PUBLISHERS: set[WebSocket] = set()      # páginas transmitindo a própria câmera
VIEWERS = {"pc": 0, "celular": 0}
_background: set[asyncio.Task] = set()


def spawn(coro) -> asyncio.Task:
    """Tarefa em segundo plano que não some no meio (o laço de eventos só guarda referência fraca)."""
    task = asyncio.create_task(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)
    return task


def _actor(session) -> str:
    """Quem fez a ação, como aparece na auditoria."""
    return "remoto" if session["remote"] else "local"


def local_only(session, why: str) -> None:
    """Coisas que mexem no próprio PC (microfone, permissões, login do Google) não podem ser feitas pelo celular."""
    if session["remote"]:
        raise HTTPException(403, why)


async def ask_device(target: str, kind: str, origin: WebSocket | None, origin_remote: bool) -> dict:
    """Pede algo à página aberta num aparelho ("este", "celular" ou "pc") e espera a resposta."""
    if target == "este" and origin is not None:
        ws = origin
    else:
        want_remote = target == "celular" or (target == "este" and origin_remote)
        found = [w for w, r in CLIENTS.items() if r == want_remote]
        if not found:
            raise tools.ToolError(f"Nenhum {'celular' if want_remote else 'PC'} está com a página da Sarah aberta agora. "
                                  "Abra a Sarah nele (e deixe a página na tela) e tente de novo.")
        ws = found[-1]  # a página aberta mais recentemente
    rid = uuid.uuid4().hex[:10]
    fut = asyncio.get_running_loop().create_future()
    DEVICE_REQUESTS[rid] = fut
    try:
        await ws.send_json({"type": "device_request", "id": rid, "kind": kind})
        answer = await asyncio.wait_for(fut, timeout=25)
    except TimeoutError:
        raise tools.ToolError("O aparelho não respondeu (página em segundo plano, tela bloqueada ou permissão pendente).") from None
    finally:
        DEVICE_REQUESTS.pop(rid, None)
    if not answer.get("ok"):
        raise tools.ToolError(f"O aparelho não conseguiu: {str(answer.get('error') or 'recusado')[:200]}")
    return answer.get("data") or {}


async def broadcast_wake(source: str, text: str = "") -> None:
    """text: o que foi dito junto com o nome ("Sarah, que horas são?"); a página já envia como pergunta.
    Sem nenhuma página aberta no PC, o próprio servidor ouve, responde e fala (mãos livres)."""
    if not local_clients:
        spawn(hands_free(text))
        return
    for ws in list(local_clients):
        try:
            await ws.send_json({"type": "wake", "source": source} | ({"text": text} if text else {}))
        except Exception:
            local_clients.discard(ws)


async def refresh_remote() -> dict:
    """Lê o estado do Tailscale e libera o nome do PC na tailnet como Host aceito."""
    st = await asyncio.to_thread(remote.status)
    if st.get("name") and st["name"] not in config.ALLOWED_HOSTS:
        config.ALLOWED_HOSTS.add(st["name"])
        log.info("Acesso remoto: host %s liberado (serve ativo: %s)", st["name"], st.get("serving"))
    return st


def rate_limited(request: Request) -> bool:
    key = request.headers.get("x-forwarded-for") or (request.client.host if request.client else "?")
    now, hits = time.monotonic(), _hits[key]
    while hits and now - hits[0] > 60:
        hits.popleft()
    hits.append(now)
    return len(hits) > RATE_LIMIT


@app.middleware("http")
async def guard(request: Request, call_next):
    if not auth.host_allowed(request.headers.get("host")):
        return JSONResponse({"detail": "Host não permitido."}, status_code=400)
    if request.method not in ("GET", "HEAD", "OPTIONS") and not auth.origin_allowed(request.headers):
        return JSONResponse({"detail": "Origem não permitida."}, status_code=403)
    if request.url.path.startswith("/api/") and rate_limited(request):
        return JSONResponse({"detail": "Muitas requisições. Aguarde um minuto."}, status_code=429)
    response = await call_next(request)
    response.headers.update(SECURITY_HEADERS)
    return response


# ---------- Sarah sem a página aberta (mãos livres no PC) ----------

SENTENCE = re.compile(r"^(.*?[.!?…\n])\s+", re.S)
_hands_free_busy = False


def _recent_conversation() -> int | None:
    """A conversa com atividade nos últimos 30 min continua; depois disso começa outra (igual à página)."""
    rows = db.query("select c.id from conversations c left join messages m on m.conversation_id = c.id group by c.id "
                    "having coalesce(max(m.created_at), c.created_at) >= datetime('now', '-30 minutes') "
                    "order by coalesce(max(m.created_at), c.created_at) desc limit 1")
    return rows[0]["id"] if rows else None


async def hands_free(text: str = "") -> None:
    """Depois do "Sarah" (ou palmas): ouve a pergunta pelo microfone do PC, responde e fala frase a frase.
    A conversa vai para o histórico; a tarefa e as confirmações aparecem no celular, que pode parar ou aprovar."""
    global _hands_free_busy
    if _hands_free_busy:
        return
    _hands_free_busy = True
    lst, task_id, player = app.state.listener, uuid.uuid4().hex[:10], None
    sentences: asyncio.Queue = asyncio.Queue()

    async def speak_all():
        while (sentence := await sentences.get()) is not None:
            wav = await asyncio.to_thread(voice.synthesize, sentence)
            if wav:
                lst.mute(sf.info(io.BytesIO(wav)).duration + 1.0)  # a escuta não ouve a própria Sarah
                await asyncio.to_thread(voice.play, wav)

    async def approve(call_id: str, label: str, summary: str, detail: str = "") -> bool:
        fut = asyncio.get_running_loop().create_future()
        APPROVALS[call_id] = {"id": call_id, "task_id": task_id, "label": label, "summary": summary, "detail": detail,
                              "future": fut}
        await sentences.put(f"Preciso da sua confirmação para {label}. Responda na tela do celular.")
        try:
            return await asyncio.wait_for(fut, timeout=300)
        except TimeoutError:
            return False
        finally:
            APPROVALS.pop(call_id, None)

    try:
        if not text:
            lst.mute(0.6)
            await asyncio.to_thread(voice.beep)
            audio = await asyncio.to_thread(lst.record)
            if audio is None:
                return  # ninguém falou: volta a esperar o "Sarah"
            text = (await asyncio.to_thread(voice.transcribe, audio)).strip()
        player = asyncio.create_task(speak_all())
        if not text:
            await sentences.put("Não entendi. Pode repetir?")
            return
        cid = _recent_conversation()
        TASKS[task_id] = {"id": task_id, "conversation_id": cid, "text": text[:120], "started": time.time(),
                          "origin": "local", "mode": "geral", "task": asyncio.current_task()}
        db.audit("local", "maos_livres", {"texto": text[:100]})
        buffer = ""
        async for event in agent.respond(cid, text, approve=approve):
            if event["type"] == "start":
                TASKS[task_id]["conversation_id"] = event["conversation_id"]
            elif event["type"] == "token":
                buffer += event["text"]
                while m := SENTENCE.match(buffer):  # fala cada frase assim que ela termina
                    await sentences.put(voice.clean_for_speech(m.group(1)))
                    buffer = buffer[m.end():]
        if buffer.strip():
            await sentences.put(voice.clean_for_speech(buffer))
    except asyncio.CancelledError:
        await asyncio.to_thread(voice.stop_playback)  # parada pelo celular: a fala para na hora
    except llm.LLMError:
        await sentences.put("Não consegui falar com o modelo agora.")
    except voice.VoiceUnavailable as e:
        log.warning("Mãos livres sem voz: %s", e)
    except Exception:
        log.exception("Falha no modo mãos livres")
    finally:
        TASKS.pop(task_id, None)
        if player:
            await sentences.put(None)
            with contextlib.suppress(Exception, asyncio.CancelledError):
                await player
        _hands_free_busy = False


# ---------- Autenticação ----------

class LoginBody(BaseModel):
    password: str = Field(max_length=200)


@app.post("/api/login")
def login(body: LoginBody, request: Request, response: Response):
    token = auth.login(body.password, request.headers.get("user-agent", ""), auth.is_remote(request.headers))
    secure = request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https"
    response.set_cookie(auth.COOKIE, token, max_age=int(config.SESSION_HOURS * 3600),
                        httponly=True, samesite="strict", secure=secure)
    return {"ok": True}


@app.post("/api/logout")
def logout(request: Request, response: Response):
    auth.logout(request.cookies.get(auth.COOKIE))
    response.delete_cookie(auth.COOKIE)
    return {"ok": True}


@app.get("/api/me")
def me(session=Depends(auth.require_session)):
    return {"remote": bool(session["remote"]), "expires_at": session["expires_at"]}


@app.get("/api/sessions")
def sessions(session=Depends(auth.require_session)):
    rows = db.query("select rowid as id, created_at, expires_at, user_agent, remote from sessions "
                    "where expires_at > ? order by created_at desc", (time.time(),))
    return [dict(r, current=r["id"] == session["id"]) for r in rows]


@app.post("/api/sessions/revoke-others")
def revoke_others(session=Depends(auth.require_session)):
    n = db.execute("delete from sessions where rowid != ?", (session["id"],))
    db.audit("usuario", "sessoes_revogadas", {"quantidade": n})
    return {"revoked": n}


# ---------- Estado ----------

@app.get("/api/status")
async def status(session=Depends(auth.require_session)):
    lst = app.state.listener
    return {"llm": await llm.status(), "wake": lst.mode, "wake_wanted": lst.wanted, "wake_error": lst.error}


# ---------- Histórico ----------

@app.get("/api/conversations")
def conversations(session=Depends(auth.require_session)):
    """Da conversa com atividade mais recente para a mais antiga (para a lateral agrupar por data)."""
    return db.query("select c.id, c.title, c.created_at, coalesce(max(m.created_at), c.created_at) as updated_at "
                    "from conversations c left join messages m on m.conversation_id = c.id "
                    "group by c.id order by updated_at desc, c.id desc")


@app.get("/api/conversations/{cid}/messages")
def messages(cid: int, session=Depends(auth.require_session)):
    return db.query("select id, role, content, created_at from messages where conversation_id = ? order by id",
                    (cid,))


@app.delete("/api/conversations/{cid}")
def delete_conversation(cid: int, session=Depends(auth.require_session)):
    if not db.execute("delete from conversations where id = ?", (cid,)):
        raise HTTPException(404, "Conversa não encontrada.")
    db.audit("usuario", "conversa_excluida", {"id": cid})
    return {"ok": True}


@app.delete("/api/conversations")
def delete_all_conversations(session=Depends(auth.require_session)):
    n = db.execute("delete from conversations")
    db.audit("usuario", "historico_apagado", {"quantidade": n})
    return {"deleted": n}


# ---------- Memória ----------

class MemoryBody(BaseModel):
    content: str = Field(min_length=1, max_length=memory.MAX_LEN)


@app.get("/api/memories")
def list_memories(session=Depends(auth.require_session)):
    return memory.list_all()


@app.post("/api/memories")
def add_memory(body: MemoryBody, session=Depends(auth.require_session)):
    mid = memory.add(body.content)
    db.audit("usuario", "memoria_criada", {"id": mid})
    return {"id": mid}


@app.put("/api/memories/{mid}")
def update_memory(mid: int, body: MemoryBody, session=Depends(auth.require_session)):
    if not memory.update(mid, body.content):
        raise HTTPException(404, "Memória não encontrada.")
    db.audit("usuario", "memoria_editada", {"id": mid})
    return {"ok": True}


@app.delete("/api/memories/{mid}")
def delete_memory(mid: int, session=Depends(auth.require_session)):
    if not memory.delete(mid):
        raise HTTPException(404, "Memória não encontrada.")
    db.audit("usuario", "memoria_excluida", {"id": mid})
    return {"ok": True}


# ---------- Voz (o áudio fica só em memória; nada é gravado em disco) ----------

@app.get("/api/voice/status")
def voice_status(session=Depends(auth.require_session)):
    return voice.status()


MAX_UPLOAD = 25_000_000


@app.post("/api/files")
async def upload_file(request: Request, nome: str, session=Depends(auth.require_session)):
    """Arquivo da caixa de mensagem: vai para arquivos\\ na área de trabalho da Sarah e nunca é executado."""
    data = bytearray()
    async for chunk in request.stream():
        data += chunk
        if len(data) > MAX_UPLOAD:
            raise HTTPException(413, "Arquivo grande demais (máximo 25 MB).")
    if not data:
        raise HTTPException(400, "Arquivo vazio.")
    try:
        path = await asyncio.to_thread(tools.save_new_file, "arquivos", nome, bytes(data))
    except tools.ToolError as e:
        raise HTTPException(400, str(e)) from None
    db.audit(_actor(session), "arquivo_enviado", {"arquivo": path.name, "bytes": len(data)})
    return {"caminho": str(path.relative_to(tools.workspace())), "bytes": len(data)}


@app.get("/api/files/{name}")
def get_uploaded_image(name: str, session=Depends(auth.require_session)):
    """Miniatura na conversa: só imagens enviadas pelo 📎 (pasta arquivos da área de trabalho)."""
    if tools.safe_filename(name) != name or Path(name).suffix.lower() not in vision.IMAGE_EXT:
        raise HTTPException(400, "Nome de imagem inválido.")
    path = tools.workspace() / "arquivos" / name
    if not path.is_file():
        raise HTTPException(404, "Imagem não encontrada.")
    return FileResponse(path, headers={"Cache-Control": "private, max-age=3600"})


@app.post("/api/stt")
async def speech_to_text(request: Request, session=Depends(auth.require_session)):
    audio = bytearray()
    async for chunk in request.stream():
        audio += chunk
        if len(audio) > voice.MAX_AUDIO_BYTES:
            raise HTTPException(413, "Áudio grande demais (máximo 10 MB).")
    if not audio:
        raise HTTPException(400, "Nenhum áudio recebido.")
    try:
        return {"text": await asyncio.to_thread(voice.transcribe, bytes(audio))}
    except voice.VoiceUnavailable as e:
        raise HTTPException(503, str(e)) from None
    except Exception:
        log.exception("Falha na transcrição")
        raise HTTPException(400, "Não consegui ler esse áudio.") from None


class TTSBody(BaseModel):
    text: str = Field(min_length=1, max_length=voice.MAX_TTS_CHARS)
    voice: str = "pf_dora"
    speed: float = Field(1.0, ge=0.5, le=2.0)


@app.post("/api/tts")
async def text_to_speech(body: TTSBody, session=Depends(auth.require_session)):
    if body.voice not in voice.VOICES:
        raise HTTPException(422, "Voz desconhecida.")
    try:
        wav = await asyncio.to_thread(voice.synthesize, body.text, body.voice, body.speed)
    except voice.VoiceUnavailable as e:
        raise HTTPException(503, str(e)) from None
    if wav and not session["remote"]:  # a fala sai pelas caixas do PC: a escuta não pode ouvir a Sarah dizendo "Sarah"
        app.state.listener.mute(sf.info(io.BytesIO(wav)).duration + 1.0)
    return Response(wav, media_type="audio/wav") if wav else Response(status_code=204)


class WakeBody(BaseModel):
    mode: str


@app.get("/api/wake")
def wake_status(session=Depends(auth.require_session)):
    lst = app.state.listener
    out = {"mode": lst.mode, "wanted": lst.wanted, "error": lst.error, "can_change": not session["remote"],
           "available": {"palavra": listener.spotter_available(), "palmas": True}}
    if not session["remote"]:
        min_peak, ratio = listener.clap_params()
        out |= {"device": db.get_setting("wake_device") or "", "clap": {"min_peak": min_peak, "ratio": ratio}}
        try:
            out["devices"] = listener.input_devices()
        except Exception:  # sounddevice ausente ou sem placa de som
            out["devices"] = []
    return out


MIC_ONLY_ON_PC = "Por privacidade, a escuta do microfone do PC só pode ser ligada no próprio PC."


@app.post("/api/wake")
async def set_wake(body: WakeBody, session=Depends(auth.require_session)):
    local_only(session, MIC_ONLY_ON_PC)
    if body.mode not in listener.MODES:
        raise HTTPException(422, "Modo inválido.")
    await asyncio.to_thread(app.state.listener.set_mode, body.mode)
    db.set_setting("wake_mode", body.mode)
    db.audit("local", "escuta_local", {"modo": app.state.listener.mode})
    return wake_status(session)


class AutostartBody(BaseModel):
    ligar: bool


@app.get("/api/autostart")
def autostart_status(session=Depends(auth.require_session)):
    return {"ligado": autostart.enabled(), "can_change": not session["remote"]}


@app.post("/api/autostart")
def autostart_set(body: AutostartBody, session=Depends(auth.require_session)):
    """Iniciar com o Windows, sem janela: um atalho na pasta Inicializar do usuário (desfazível)."""
    local_only(session, "Isto muda o Windows deste PC: faça no próprio PC.")
    try:
        autostart.set_enabled(body.ligar)
    except Exception as e:
        raise HTTPException(500, f"Não consegui mudar a inicialização com o Windows: {e}") from None
    db.audit("local", "inicio_automatico", {"ligado": body.ligar})
    return autostart_status(session)


class WakeSettingsBody(BaseModel):
    device: str | None = Field(None, max_length=200)  # "" = padrão do Windows
    min_peak: float | None = Field(None, ge=0.001, le=1)
    ratio: float | None = Field(None, ge=2, le=20)


async def restart_listener() -> None:
    """Reabre o microfone com o ajuste novo, se a escuta estiver ligada."""
    mode = app.state.listener.mode
    if mode != "off":
        await asyncio.to_thread(app.state.listener.set_mode, mode)


@app.post("/api/wake/settings")
async def wake_settings(body: WakeSettingsBody, session=Depends(auth.require_session)):
    local_only(session, MIC_ONLY_ON_PC)
    if (body.min_peak is None) != (body.ratio is None):
        raise HTTPException(422, "Informe min_peak e ratio juntos.")
    if body.device is not None:
        db.set_setting("wake_device", body.device)
    if body.min_peak is not None:
        db.set_setting("clap", json.dumps({"min_peak": body.min_peak, "ratio": body.ratio}))
    db.audit("local", "escuta_ajustada", body.model_dump(exclude_none=True))
    await restart_listener()
    return wake_status(session)


@app.post("/api/wake/calibrate")
async def wake_calibrate(session=Depends(auth.require_session)):
    """Ouve 12 s (só em memória) para medir o ruído e as palmas; nada é salvo até clicar em Aplicar."""
    local_only(session, MIC_ONLY_ON_PC)
    lst = app.state.listener
    mode = lst.mode
    await asyncio.to_thread(lst.stop)  # libera o microfone durante a medição
    try:
        result = await asyncio.to_thread(listener.measure, 12)
    except Exception as e:
        raise HTTPException(503, f"Não consegui ouvir o microfone: {e}") from None
    finally:
        if mode != "off":
            await asyncio.to_thread(lst.set_mode, mode)
    db.audit("local", "palmas_calibradas", {"estalos": len(result["estalos"]), "microfone": result["microfone"]})
    return result


# ---------- Ferramentas ----------

class ToolSettingsBody(BaseModel):
    mode: str
    disabled: list[str] = []


@app.get("/api/tools")
def list_tools(session=Depends(auth.require_session)):
    s = tools.settings()
    try:
        perms, error = tools.permissions(), ""
    except tools.ToolError as e:
        perms, error = {"pastas": [], "aplicativos": {}, "scripts": {}}, str(e)
    offered = {t.name for t in tools.available(bool(session["remote"]))}
    return {
        "mode": s["mode"], "can_change": not session["remote"], "remote_all": config.REMOTE_TOOLS_ALL, "error": error,
        "tools": [{"name": t.name, "label": t.label, "description": t.description, "risk": t.risk, "group": t.group,
                   "enabled": t.name not in s["disabled"], "offered": t.name in offered} for t in tools.REGISTRY.values()],
        "permissions": {"pastas": perms["pastas"], "aplicativos": list(perms["aplicativos"]),
                        "scripts": list(perms.get("scripts", {})), "workspace": str(tools.workspace()),
                        "sugestoes": [] if session["remote"] or error else tools.folder_suggestions()},
    }


class FolderBody(BaseModel):
    caminho: str = Field(min_length=1, max_length=500)
    autorizar: bool


@app.post("/api/permissions/folders")
def authorize_folder(body: FolderBody, session=Depends(auth.require_session)):
    """Liberar uma pasta é dar acesso à Sarah: só no próprio PC, nunca pelo celular."""
    local_only(session, "Pastas só podem ser liberadas no próprio PC.")
    try:
        tools.authorize_folder(body.caminho, body.autorizar)
    except tools.ToolError as e:
        raise HTTPException(400, str(e)) from None
    db.audit("local", "pasta_liberada" if body.autorizar else "pasta_retirada", {"caminho": body.caminho})
    return list_tools(session)


@app.put("/api/tools")
def update_tools(body: ToolSettingsBody, session=Depends(auth.require_session)):
    local_only(session, "Permissões de ferramentas só podem ser alteradas no próprio PC.")
    try:
        s = tools.save_settings(body.mode, body.disabled)
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    db.audit("local", "permissoes_ferramentas", s)
    return list_tools(session)


# ---------- Integração Google (Gmail e Agenda) ----------

@app.get("/api/google")
def google_status(session=Depends(auth.require_session)):
    return google_api.status() | {"can_connect": not session["remote"]}


@app.post("/api/google/connect")
async def google_connect(session=Depends(auth.require_session)):
    local_only(session, "A conexão com o Google abre o navegador do PC: faça no próprio PC.")
    if not google_api.status()["configured"]:
        raise HTTPException(409, "Falta o client_secret.json em data/google. Veja INTEGRATIONS.md.")

    def run():
        try:
            google_api.connect()
        except Exception as e:  # o usuário vê o resultado consultando o status
            log.warning("Conexão com o Google falhou: %s", e)
    asyncio.get_running_loop().run_in_executor(None, run)
    return {"started": True}


@app.post("/api/google/disconnect")
async def google_disconnect(session=Depends(auth.require_session)):
    await asyncio.to_thread(google_api.disconnect, _actor(session))
    return google_api.status()


# ---------- Reconhecimento facial (opcional, desligado por padrão) ----------

class FaceBody(BaseModel):
    nome: str = Field(min_length=1, max_length=60)


@app.get("/api/face")
def face_status(session=Depends(auth.require_session)):
    on = face.enabled()
    return {"enabled": on, "feature_on": config.FACE_ENABLED, "models": face.models_ready(),
            "people": face.people() if on else [], "photos": face.list_photos(),
            "can_use_camera": not session["remote"] or config.REMOTE_CAMERA}


def _camera_allowed(session) -> None:
    if not face.enabled():
        raise HTTPException(409, "Reconhecimento facial desativado. Veja INTEGRATIONS.md para ativar.")
    try:
        face.camera_allowed(bool(session["remote"]))
    except face.FaceError as e:
        raise HTTPException(403, str(e)) from None


@app.post("/api/face/photo")
async def face_photo(session=Depends(auth.require_session)):
    _camera_allowed(session)
    try:
        name, found, dark = await asyncio.to_thread(face.take_photo)
    except face.FaceError as e:
        raise HTTPException(422, str(e)) from None
    db.audit(_actor(session), "foto_tirada", {"arquivo": name, "rostos": len(found)})
    return {"foto": name, "texto": face.photo_text(found, dark), "photos": face.list_photos()}


@app.get("/api/photos/{name}")
def get_photo(name: str, session=Depends(auth.require_session)):
    try:
        path = face.photo_path(name)
    except face.FaceError as e:
        raise HTTPException(400, str(e)) from None
    if not path.exists():
        raise HTTPException(404, "Foto não encontrada.")
    return FileResponse(path, media_type="image/jpeg", headers={"Cache-Control": "private, no-store"})


@app.delete("/api/photos/{name}")
def delete_photo(name: str, session=Depends(auth.require_session)):
    try:
        path = face.photo_path(name)
    except face.FaceError as e:
        raise HTTPException(400, str(e)) from None
    if not path.exists():
        raise HTTPException(404, "Foto não encontrada.")
    path.unlink()
    db.audit(_actor(session), "foto_apagada", {"arquivo": name})
    return {"photos": face.list_photos()}


@app.delete("/api/photos")
def delete_all_photos(session=Depends(auth.require_session)):
    names = face.list_photos()
    for n in names:
        face.photo_path(n).unlink()
    db.audit(_actor(session), "fotos_apagadas", {"quantidade": len(names)})
    return {"photos": []}


@app.post("/api/face/enroll")
async def face_enroll(body: FaceBody, session=Depends(auth.require_session)):
    _camera_allowed(session)
    try:
        n = await asyncio.to_thread(face.enroll, body.nome)
    except face.FaceError as e:
        raise HTTPException(422, str(e)) from None
    db.audit(_actor(session), "rosto_cadastrado", {"nome": body.nome, "amostras": n})
    return {"amostras": n, "people": face.people()}


@app.post("/api/face/identify")
async def face_identify(session=Depends(auth.require_session)):
    _camera_allowed(session)
    try:
        found = await asyncio.to_thread(face.identify)
    except face.FaceError as e:
        raise HTTPException(422, str(e)) from None
    db.audit(_actor(session), "camera_consultada", {"rostos": len(found)})
    return {"texto": face.describe(found), "rostos": found}


@app.delete("/api/face/people/{nome}")
def face_remove(nome: str, session=Depends(auth.require_session)):
    if not face.remove(nome):
        raise HTTPException(404, "Pessoa não cadastrada.")
    db.audit(_actor(session), "rosto_removido", {"nome": nome})
    return {"people": face.people()}


@app.delete("/api/face/people")
def face_remove_all(session=Depends(auth.require_session)):
    face.remove_all()  # funciona mesmo com o módulo desligado: apagar dados biométricos sempre deve ser possível
    db.audit(_actor(session), "dados_faciais_apagados")
    return {"people": []}


# ---------- Armazenamento ----------

@app.get("/api/storage")
def storage_report(session=Depends(auth.require_session)):
    return storage.report()


class CleanupBody(BaseModel):
    areas: bool = False      # áreas do agente de programação sem uso há 7+ dias
    backups: bool = False    # backups com 30+ dias
    compactar: bool = False  # devolve ao disco o espaço de registros apagados


@app.post("/api/storage/cleanup")
def storage_cleanup(body: CleanupBody, session=Depends(auth.require_session)):
    local_only(session, "A limpeza só pode ser feita no próprio PC.")
    freed = storage.cleanup(body.areas, body.backups, body.compactar)
    db.audit("local", "armazenamento_limpo", body.model_dump() | {"bytes": freed})
    return storage.report() | {"liberado": freed}


# ---------- Auditoria ----------

@app.get("/api/audit")
def audit_log(session=Depends(auth.require_session)):
    return db.query("select id, ts, actor, action, detail from audit order by id desc limit 200")


# ---------- Chat em tempo real ----------

# Tarefas em execução e confirmações pendentes, visíveis para qualquer sessão (PC ou celular).
TASKS: dict[str, dict] = {}
APPROVALS: dict[str, dict] = {}


def resolve_approval(call_id: str, ok: bool, remote: bool) -> None:
    item = APPROVALS.get(call_id)
    if not item or item["future"].done():
        raise HTTPException(404, "Essa confirmação não está mais pendente.")
    if ok and remote and not config.REMOTE_TOOLS_ALL:
        raise HTTPException(403, "Aprovar pelo celular está desligado (JARVIS_REMOTE_TOOLS_ALL). Você pode recusar ou parar.")
    fut = item["future"]  # entrega segura mesmo se a resposta vier de outra thread ou laço de eventos
    fut.get_loop().call_soon_threadsafe(lambda: fut.done() or fut.set_result(ok))
    db.audit("remoto" if remote else "local", "confirmacao", {"aprovada": ok, "acao": item["summary"][:200]})


@app.get("/api/tasks")
def list_tasks(session=Depends(auth.require_session)):
    return [{k: t[k] for k in ("id", "conversation_id", "text", "started", "origin", "mode")}
            | {"approvals": [{k: a[k] for k in ("id", "label", "summary", "detail")}
                             for a in APPROVALS.values() if a["task_id"] == t["id"] and not a["future"].done()]}
            for t in TASKS.values()]


@app.post("/api/tasks/{task_id}/stop")
def stop_task(task_id: str, session=Depends(auth.require_session)):
    t = TASKS.get(task_id)
    if not t:
        raise HTTPException(404, "Tarefa não encontrada ou já terminou.")
    t["task"].cancel()
    db.audit(_actor(session), "tarefa_interrompida", {"texto": t["text"][:100]})
    return {"ok": True}


class ApprovalBody(BaseModel):
    ok: bool


@app.post("/api/approvals/{call_id}")
def answer_approval(call_id: str, body: ApprovalBody, session=Depends(auth.require_session)):
    resolve_approval(call_id, body.ok, bool(session["remote"]))
    return {"ok": True}


@app.get("/api/remote")
async def remote_status(session=Depends(auth.require_session)):
    return await refresh_remote() | {"remote_tools_all": config.REMOTE_TOOLS_ALL}


async def _ws_allowed(ws: WebSocket) -> dict | None:
    """Mesmas regras da API: Host e Origin conferidos (DNS rebinding e CSRF) e sessão válida."""
    if not (auth.host_allowed(ws.headers.get("host")) and auth.origin_allowed(ws.headers)):
        await ws.close(code=1008)
        return None
    session = auth.session_from_token(ws.cookies.get(auth.COOKIE))
    if not session:
        await ws.close(code=4401)
    return session


@app.websocket("/ws/chat")
async def ws_chat(ws: WebSocket):
    session = await _ws_allowed(ws)
    if not session:
        return
    token = ws.cookies.get(auth.COOKIE)
    await ws.accept()
    remote = bool(session["remote"])
    if not remote:
        local_clients.add(ws)
    CLIENTS[ws] = remote
    task: asyncio.Task | None = None
    task_id = ""

    def device(target: str, kind: str):
        return ask_device(target, kind, ws, remote)

    async def approve(call_id: str, label: str, summary: str, detail: str = "") -> bool:
        fut = asyncio.get_running_loop().create_future()
        APPROVALS[call_id] = {"id": call_id, "task_id": task_id, "label": label, "summary": summary,
                              "detail": detail, "future": fut}
        await ws.send_json({"type": "approval", "id": call_id, "label": label, "summary": summary, "detail": detail})
        try:
            ok = await asyncio.wait_for(fut, timeout=300)
            await ws.send_json({"type": "approval_closed", "id": call_id, "ok": ok})  # pode ter sido respondida em outro aparelho
            return ok
        except TimeoutError:
            await ws.send_json({"type": "approval_expired", "id": call_id})
            return False
        finally:
            APPROVALS.pop(call_id, None)

    async def run(cid, text, mode):
        try:
            async for event in agent.respond(cid, text, remote=remote, emit=ws.send_json, approve=approve, mode=mode,
                                             device=device):
                if event["type"] == "start":
                    TASKS[task_id]["conversation_id"] = event["conversation_id"]
                    event["task_id"] = task_id
                await ws.send_json(event)
        except llm.LLMError as e:
            await ws.send_json({"type": "error", "message": str(e)})
        except asyncio.CancelledError:
            with contextlib.suppress(Exception):  # o socket pode já ter fechado (desconexão)
                await ws.send_json({"type": "done", "conversation_id": cid, "interrupted": True})
        except Exception:
            log.exception("Falha ao gerar resposta")
            with contextlib.suppress(Exception):
                await ws.send_json({"type": "error", "message": "Erro interno. Veja data/logs/jarvis.log."})
        finally:
            TASKS.pop(task_id, None)

    try:
        while True:
            try:
                msg = await ws.receive_json()
            except (ValueError, KeyError):  # JSON inválido ou mensagem binária: ignora e mantém a conexão
                msg = None
            if not isinstance(msg, dict):
                await ws.send_json({"type": "error", "message": "Mensagem inválida."})
                continue
            if not auth.session_from_token(token):  # sessão revogada ou expirada
                await ws.close(code=4401)
                return
            if msg.get("type") == "stop":
                if task and not task.done():
                    task.cancel()
            elif msg.get("type") == "approve":
                try:
                    resolve_approval(str(msg.get("id")), msg.get("ok") is True, remote)
                except HTTPException as e:
                    await ws.send_json({"type": "error", "message": e.detail})
            elif msg.get("type") == "device_response":
                fut = DEVICE_REQUESTS.get(str(msg.get("id")))
                if fut and not fut.done():
                    fut.get_loop().call_soon_threadsafe(lambda f=fut, m=msg: f.done() or f.set_result(m))
            elif msg.get("type") == "chat":
                text = str(msg.get("text", "")).strip()
                if task and not task.done():
                    await ws.send_json({"type": "error", "message": "Aguarde a resposta atual ou interrompa."})
                elif not text or len(text) > MAX_MESSAGE:
                    await ws.send_json({"type": "error", "message": f"Mensagem vazia ou maior que {MAX_MESSAGE} caracteres."})
                else:
                    cid = msg.get("conversation_id")
                    mode = "codigo" if msg.get("mode") == "codigo" else "geral"
                    task_id = uuid.uuid4().hex[:10]
                    task = asyncio.create_task(run(cid if isinstance(cid, int) else None, text, mode))
                    TASKS[task_id] = {"id": task_id, "conversation_id": cid, "text": text[:120], "started": time.time(),
                                      "origin": _actor(session), "mode": mode, "task": task}
    except WebSocketDisconnect:
        pass
    finally:
        if task and not task.done():  # a página fechou: a resposta em andamento para (e libera o modelo)
            task.cancel()
        local_clients.discard(ws)
        CLIENTS.pop(ws, None)


# ---------- Câmeras ao vivo ----------

@app.websocket("/ws/camera")
async def ws_camera(ws: WebSocket):
    """A página de um aparelho (normalmente o celular) envia quadros JPEG da própria câmera."""
    session = await _ws_allowed(ws)
    if not session:
        return
    await ws.accept()
    PUBLISHERS.add(ws)
    db.audit(_actor(session), "camera_transmitindo", {})
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data and len(data) <= 500_000 and data[:2] == b"\xff\xd8":  # só JPEG
                camera.phone.put(data)
    except WebSocketDisconnect:
        pass
    finally:
        PUBLISHERS.discard(ws)
        if not PUBLISHERS:
            camera.phone.clear()


async def _stop_phone_if_unwatched() -> None:
    await asyncio.sleep(15)
    if VIEWERS["celular"] == 0:
        for ws in list(PUBLISHERS):  # ninguém mais assistindo: o celular para de transmitir
            await ws.close(code=1000)


@app.get("/api/camera/{origem}/stream")
async def camera_stream(origem: str, request: Request, session=Depends(auth.require_session)):
    if origem not in ("pc", "celular"):
        raise HTTPException(404, "Câmera desconhecida.")
    if origem == "pc":
        try:
            face.camera_allowed(bool(session["remote"]))
        except face.FaceError as e:
            raise HTTPException(403, str(e)) from None
        if not camera.opencv_available():
            raise HTTPException(409, "Falta o OpenCV: rode iniciar.bat para instalar as dependências.")
    db.audit(_actor(session), "camera_vista", {"origem": origem})

    async def frames():
        feed = camera.pc if origem == "pc" else camera.phone
        hold = camera.use_pc() if origem == "pc" else contextlib.nullcontext()
        start, seq = time.monotonic(), 0
        VIEWERS[origem] += 1
        try:
            with hold:
                while time.monotonic() - start < camera.MAX_VIEW and not await request.is_disconnected():
                    seq, frame = await asyncio.to_thread(feed.wait, seq, 2)
                    if frame is None:
                        continue
                    data = await asyncio.to_thread(camera.jpeg, frame) if origem == "pc" else frame
                    yield (b"--frame\r\nContent-Type: image/jpeg\r\nContent-Length: " + str(len(data)).encode()
                           + b"\r\n\r\n" + data + b"\r\n")
        finally:
            VIEWERS[origem] -= 1
            if origem == "celular" and VIEWERS["celular"] == 0:
                spawn(_stop_phone_if_unwatched())

    return StreamingResponse(frames(), media_type="multipart/x-mixed-replace; boundary=frame",
                             headers={"Cache-Control": "no-store"})


@app.post("/api/camera/celular/start")
async def camera_phone_start(session=Depends(auth.require_session)):
    """Pede à página aberta no celular para começar a transmitir a câmera (usado pelo botão no PC)."""
    try:
        await ask_device("celular", "camera_start", None, bool(session["remote"]))
    except tools.ToolError as e:
        raise HTTPException(409, str(e)) from None
    db.audit(_actor(session), "camera_ao_vivo", {"origem": "celular"})
    return {"ok": True}


app.mount("/", StaticFiles(directory=config.ROOT / "web", html=True), name="web")
