"use strict";
const $ = (s) => document.querySelector(s);
const state = { conversationId: null, ws: null, busy: false, bubble: null, retry: 1000, cards: {}, lastActivity: Date.now(), wakeError: "" };

// ---------- API ----------
async function api(path, opts = {}) {
  const r = await fetch(path, {
    ...opts,
    headers: { "Content-Type": "application/json" },
    body: opts.body ? JSON.stringify(opts.body) : undefined,
  });
  const data = await r.json().catch(() => ({}));
  if (r.status === 401 && path !== "/api/login") { showLogin(); throw new Error("Sessão expirada."); }
  if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
  return data;
}

function el(tag, props = {}, ...children) {
  const node = Object.assign(document.createElement(tag), props);
  node.append(...children);
  return node;
}
// Avisos curtos no rodapé (erros e resultados), sem travar a tela como o notify().
function notify(text) {
  const t = $("#toast");
  t.textContent = text;
  t.hidden = false;
  clearTimeout(notify.timer);
  notify.timer = setTimeout(() => (t.hidden = true), 4500);
}
// Qualquer chamada à API que falhe sem tratamento local vira um aviso (antes falhava em silêncio).
window.addEventListener("unhandledrejection", (e) => {
  console.error(e.reason);
  notify(e.reason instanceof TypeError ? "Sem conexão com a Sarah agora." : e.reason?.message || "Algo deu errado.");
});
// Datas do SQLite vêm em UTC ("AAAA-MM-DD HH:MM:SS"); as das sessões, em segundos.
const parseDate = (s) => new Date(typeof s === "number" ? s * 1000 : s.replace(" ", "T") + "Z");
const fmtDate = (s) => parseDate(s).toLocaleString("pt-BR");

// ---------- Login ----------
function showLogin() {
  state.ws?.close();
  $("#app-view").hidden = true;
  $("#login-view").hidden = false;
  $("#password").focus();
}

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  $("#login-error").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: { password: $("#password").value } });
    $("#password").value = "";
    start();
  } catch (err) { $("#login-error").textContent = err.message; }
});

async function start() {
  try { await api("/api/me"); } catch { return; }
  $("#login-view").hidden = true;
  $("#app-view").hidden = false;
  connect();
  openConversation(null);
  refreshStatus();
}

// ---------- Abas ----------
// ---------- Menu ☰ e páginas ----------
const TITLES = { memory: "Memória", voice: "Voz", tools: "Ferramentas", security: "Segurança" };
function showView(name) {
  document.querySelectorAll(".view").forEach((v) => (v.hidden = v.id !== `view-${name}`));
  $("#back-btn").hidden = name === "chat";
  $("#page-title").textContent = TITLES[name] || "";
  toggleMenu(false);
  if (name === "memory") loadMemories();
  if (name === "security") loadSecurity();
  if (name === "voice") loadVoice();
  if (name === "tools") loadTools();
}
function toggleMenu(open) {
  $("#menu").hidden = !open;
  $("#menu-btn").setAttribute("aria-expanded", open);
}
$("#menu-btn").addEventListener("click", (e) => { e.stopPropagation(); toggleMenu($("#menu").hidden); });
document.addEventListener("click", (e) => { if (!$("#menu").hidden && !$("#menu").contains(e.target)) toggleMenu(false); });
document.querySelectorAll("#menu [data-view]").forEach((b) => b.addEventListener("click", () => showView(b.dataset.view)));
$('#menu [data-action="new"]').addEventListener("click", () => { showView("chat"); openConversation(null); });
$('#menu [data-action="history"]').addEventListener("click", () => showSidebar(true));
$("#back-btn").addEventListener("click", () => showView("chat"));

// ---------- Histórico (lateral esquerda) ----------
const wide = matchMedia("(min-width: 1000px)");
try { document.body.classList.toggle("side-collapsed", localStorage.getItem("sarah-side") === "0"); } catch { /* modo privado */ }
function sidebarShown() { return wide.matches ? !document.body.classList.contains("side-collapsed") : $("#sidebar").classList.contains("open"); }
function showSidebar(open) {
  showView("chat");
  if (!wide.matches) return $("#sidebar").classList.toggle("open", open);
  document.body.classList.toggle("side-collapsed", !open);
  try { localStorage.setItem("sarah-side", open ? "1" : "0"); } catch { /* modo privado */ }
}
function closeDrawer() { $("#sidebar").classList.remove("open"); } // no PC a lateral fica; no celular a gaveta fecha
$("#history-btn").addEventListener("click", () => showSidebar(!sidebarShown()));
$("#close-sidebar").addEventListener("click", closeDrawer);
$("#view-chat").addEventListener("click", (e) => { // toque fora da gaveta fecha
  if ($("#sidebar").classList.contains("open") && !$("#sidebar").contains(e.target)) closeDrawer();
});
document.addEventListener("keydown", (e) => { if (e.key === "Escape") { closeDrawer(); toggleMenu(false); ttsStop(); } });

// ---------- Estado ----------
function setPill(id, text, cls) {
  const p = $(id);
  p.textContent = text;
  p.className = `pill ${cls}`;
  if (id === "#conn-status") $("#conn-dot").className = `dot ${cls}`; // bolinha no botão do menu
}

async function refreshStatus() {
  try {
    const { llm, wake, wake_wanted: wanted, wake_error: wakeError } = await api("/api/status");
    setWakePill(wake, wanted);
    if (wakeError !== state.wakeError) { // avisa uma vez quando aparece um problema (ex.: microfone desconectado)
      state.wakeError = wakeError;
      if (wakeError) notify(wakeError);
    }
    if (!llm.online) setPill("#model-status", "Ollama offline", "bad");
    else if (!llm.installed) setPill("#model-status", `${llm.model} não instalado`, "bad");
    else if (llm.loaded) setPill("#model-status", `${llm.model} · ${llm.gpu ? "GPU" : "CPU"}`, "ok");
    else setPill("#model-status", `${llm.model} · em espera`, "warn");
  } catch { /* 401 já tratado */ }
}
setInterval(() => { if (!$("#app-view").hidden) refreshStatus(); }, 15000);

function setWakePill(mode, wanted) {
  const pill = $("#wake-status");
  pill.hidden = wanted === "off";
  pill.textContent = mode !== "off" ? `Escuta local: ${mode}` : "Escuta local: sem microfone";
  pill.className = `pill ${mode !== "off" ? "warn" : "bad"}`;
}

// ---------- WebSocket ----------
function connect() {
  const ws = new WebSocket(`${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/chat`);
  state.ws = ws;
  ws.onopen = () => { state.retry = 1000; setPill("#conn-status", "Conectado", "ok"); };
  ws.onclose = (e) => {
    setPill("#conn-status", "Desconectado", "bad");
    setBusy(false);
    if (e.code === 4401) return showLogin();
    if (!$("#app-view").hidden && state.ws === ws) setTimeout(connect, (state.retry = Math.min(state.retry * 2, 15000)));
  };
  ws.onmessage = (e) => handleEvent(JSON.parse(e.data));
}

function handleEvent(ev) {
  if (ev.type === "start") {
    const isNew = state.conversationId !== ev.conversation_id;
    state.conversationId = ev.conversation_id;
    state.bubble = null;
    state.taskId = ev.task_id;
    if (isNew) loadConversations();
  } else if (ev.type === "token") {
    if (!state.streaming) { state.streaming = true; updateControls(); }
    if (!state.bubble) { state.raw = ""; state.bubble = addMessage("assistant", ""); }
    state.raw += ev.text;
    state.bubble.innerHTML = renderMarkdown(state.raw);
    scrollDown();
    ttsFeed(ev.text);
  } else if (ev.type === "done") {
    state.lastActivity = Date.now();
    loadConversations(); // a conversa sobe para o topo da lateral
    if (ev.interrupted) (state.bubble || addMessage("assistant", "")).textContent += " [interrompido]";
    document.querySelectorAll(".msg.approval button").forEach((b) => (b.disabled = true));
    if (!ev.interrupted) ttsFeed("", true);
    setBusy(false);
    refreshStatus();
  } else if (ev.type === "error") {
    addMessage("error", ev.message);
    setBusy(false);
  } else if (ev.type === "tool_start") {
    state.bubble = null;
    state.cards[ev.id] = addToolCard(ev.label, ev.args);
  } else if (ev.type === "tool_output") {
    const pre = state.cards[ev.id]?.querySelector("pre");
    if (pre) { pre.textContent += `${ev.line}\n`; pre.scrollTop = pre.scrollHeight; }
  } else if (ev.type === "tool_end") {
    finishToolCard(state.cards[ev.id], ev.ok, ev.result);
  } else if (ev.type === "approval") {
    addApproval(ev);
  } else if (ev.type === "approval_expired") {
    closeApproval(ev.id, "Expirou sem resposta: nada foi feito.");
  } else if (ev.type === "approval_closed") {
    closeApproval(ev.id, ev.ok ? "Aprovado." : "Recusado: nada foi feito.");
  } else if (ev.type === "device_request") {
    handleDeviceRequest(ev);
  } else if (ev.type === "wake" && !rec.active && !state.busy && !tts.speaking) {
    onWake(ev);
  }
}

// "Sarah" (ou palmas) com a Sarah parada. Depois de 30 min sem conversar, começa uma conversa nova:
// o assunto antigo não se mistura com o novo (e o modelo responde mais rápido com menos histórico).
const NEW_CHAT_AFTER = 30 * 60000;
async function onWake(ev) {
  if (!navigator.userActivation?.hasBeenActive) notify("Clique uma vez na página da Sarah para ela poder responder falando.");
  showView("chat");
  if (state.conversationId && Date.now() - state.lastActivity > NEW_CHAT_AFTER) await openConversation(null);
  beep();
  if (ev.text) { $("#input").value = ev.text; send(); } // "Sarah, que horas são?": a pergunta veio junto
  else startRecording();
}

function setBusy(busy) {
  state.busy = busy;
  if (!busy) state.streaming = false;
  updateControls();
}

function updateControls() {
  const active = state.busy || tts.speaking;
  $("#send-btn").hidden = active;
  $("#stop-btn").hidden = !active;
  avatar.setState(rec.active ? "listening" : tts.speaking ? "speaking"
    : state.busy ? (state.streaming ? "writing" : "thinking") : "idle");
}

$("#avatar-btn").addEventListener("click", () => (rec.active ? stopRecording() : startRecording()));

// Sem mensagens, o rosto ocupa a tela; quando a conversa começa, ele vai para o topo e o chat aparece embaixo.
function setHome(home) { $("#view-chat").classList.toggle("compact", !home); }

// Arquivo enviado pela caixa de mensagem: fica em arquivos\ na área de trabalho e vai junto com a próxima mensagem.
let attached = null;
function clearAttach() { attached = null; $("#attach-chip").hidden = true; }
$("#attach-btn").addEventListener("click", () => $("#file-input").click());
$("#attach-clear").addEventListener("click", clearAttach);
$("#file-input").addEventListener("change", async () => {
  const f = $("#file-input").files[0];
  $("#file-input").value = "";
  if (!f) return;
  if (f.size > 25e6) return notify("Arquivo grande demais (máximo 25 MB).");
  $("#attach-name").textContent = `Enviando ${f.name}…`;
  $("#attach-chip").hidden = false;
  try {
    const r = await fetch(`/api/files?nome=${encodeURIComponent(f.name)}`,
      { method: "POST", headers: { "Content-Type": "application/octet-stream" }, body: f });
    if (r.status === 401) return showLogin();
    const data = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
    attached = data.caminho;
    $("#attach-name").textContent = `📎 ${data.caminho}`;
    $("#input").focus();
  } catch (e) { clearAttach(); notify(`Não consegui enviar o arquivo: ${e.message}`); }
});

// ---------- Chat ----------
// Markdown mínimo e seguro: escapa todo o HTML antes de formatar.
function renderMarkdown(text) {
  return text.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/```\w*\n?([\s\S]*?)(```|$)/g, "<pre><code>$1</code></pre>")
    .replace(/`([^`\n]+)`/g, "<code>$1</code>")
    .replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>")
    .replace(/^#{1,6} (.+)$/gm, "<strong>$1</strong>")
    // só https e sem aspas no endereço: o texto já foi escapado, então não há como sair do atributo href
    .replace(/\[([^\]\n]+)\]\((https:\/\/[^\s()"'<>]+)\)/g, '<a href="$2" target="_blank" rel="noopener noreferrer">$1</a>');
}

function msgNode(role, text) {
  if (role === "tool") {
    const t = JSON.parse(text);
    const card = toolCardNode(t.label, "");
    finishToolCard(card, t.ok, t.result);
    return card;
  }
  const node = el("div", { className: `msg ${role}` });
  if (role === "assistant") node.innerHTML = renderMarkdown(text); else node.textContent = text;
  const image = role === "user" && /^📎 Imagem enviada: arquivos[\\/]([^\n\\/]+)$/m.exec(text);
  if (image) node.append(el("img", { className: "sent-image", src: `/api/files/${encodeURIComponent(image[1])}`, alt: image[1], loading: "lazy" }));
  return node;
}

function addMessage(role, text) {
  $("#messages").querySelector(".empty")?.remove();
  setHome(false);
  const node = msgNode(role, text);
  $("#messages").append(node);
  scrollDown();
  return node;
}
const scrollDown = () => { const m = $("#messages"); m.scrollTop = m.scrollHeight; };

function send() {
  let text = $("#input").value.trim();
  if ((!text && !attached) || state.busy) return;
  if (state.ws?.readyState !== WebSocket.OPEN) return notify("Sem conexão com a Sarah. Tentando reconectar…");
  if (attached) {
    const image = /\.(jpe?g|png|webp|bmp)$/i.test(attached); // imagem: a Sarah vê o conteúdo; outros arquivos ela lê pelas ferramentas
    text = `📎 ${image ? "Imagem enviada" : "Arquivo enviado"}: ${attached}\n${text || (image ? "O que tem nesta imagem?" : "Veja este arquivo.")}`;
    clearAttach();
  }
  ttsStop();
  state.lastActivity = Date.now();
  addMessage("user", text);
  state.ws.send(JSON.stringify({ type: "chat", conversation_id: state.conversationId, text, mode: codeMode ? "codigo" : "geral" }));
  $("#input").value = "";
  autoGrow();
  setBusy(true);
}

$("#composer").addEventListener("submit", (e) => { e.preventDefault(); send(); });
$("#input").addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) { e.preventDefault(); send(); }
});
function autoGrow() {
  const t = $("#input");
  t.style.height = "auto";
  t.style.height = `${t.scrollHeight + t.offsetHeight - t.clientHeight}px`; // inclui a borda
  t.style.overflowY = t.scrollHeight > t.clientHeight ? "auto" : "hidden"; // passou do max-height
}
$("#input").addEventListener("input", autoGrow);
$("#stop-btn").addEventListener("click", () => {
  if (state.busy) state.ws?.send(JSON.stringify({ type: "stop" }));
  ttsStop();
});
$("#new-chat").addEventListener("click", () => openConversation(null));

let conversations = [];
async function loadConversations() {
  conversations = await api("/api/conversations");
  renderConversations();
}

// Agrupadas pela última atividade (Hoje, Ontem…) e filtradas pela busca.
function renderConversations() {
  const q = $("#conv-search").value.trim().toLowerCase();
  const day = 86400000, today = new Date().setHours(0, 0, 0, 0);
  const group = (t) => (t >= today ? "Hoje" : t >= today - day ? "Ontem" : t >= today - 7 * day ? "Últimos 7 dias"
    : t >= today - 30 * day ? "Últimos 30 dias" : "Mais antigas");
  const items = [];
  let last = "";
  for (const c of conversations.filter((x) => !q || x.title.toLowerCase().includes(q))) {
    const g = group(parseDate(c.updated_at).getTime());
    if (g !== last) items.push(el("li", { className: "conv-group", textContent: (last = g) }));
    items.push(el("li", { className: c.id === state.conversationId ? "active" : "" },
      el("button", { className: "open", textContent: c.title, title: `${c.title}\n${fmtDate(c.updated_at)}`, onclick: () => openConversation(c.id) }),
      el("button", { className: "del", textContent: "✕", ariaLabel: `Excluir conversa ${c.title}`, onclick: () => deleteConversation(c) })));
  }
  $("#conv-list").replaceChildren(...(items.length ? items
    : [el("li", { className: "hint", textContent: q ? "Nenhuma conversa com esse título." : "Nenhuma conversa ainda." })]));
}
$("#conv-search").addEventListener("input", renderConversations);

async function openConversation(id) {
  if (state.busy) return notify("Aguarde a resposta atual ou toque em Parar.");
  state.conversationId = id;
  state.cards = {};
  state.lastActivity = Date.now();
  closeDrawer();
  const msgs = id ? await api(`/api/conversations/${id}/messages`) : [];
  $("#messages").replaceChildren(...(msgs.length ? msgs.map((m) => msgNode(m.role, m.content))
    : [el("p", { className: "empty", textContent: "Nova conversa. Como posso ajudar?" })]));
  setHome(!msgs.length);
  scrollDown();
  loadConversations();
  $("#input").focus();
}

async function deleteConversation(c) {
  if (!confirm(`Excluir a conversa "${c.title}"? Isso não pode ser desfeito.`)) return;
  await api(`/api/conversations/${c.id}`, { method: "DELETE" });
  if (c.id === state.conversationId) openConversation(null); else loadConversations();
}

// ---------- Ferramentas no chat ----------
function toolCardNode(label, args) {
  return el("div", { className: "msg tool" },
    el("details", {}, el("summary", { textContent: `🔧 ${label} … executando` }),
      el("small", { className: "hint", textContent: args || "" }), el("pre")));
}

function addToolCard(label, args) {
  $("#messages").querySelector(".empty")?.remove();
  setHome(false);
  const card = toolCardNode(label, args);
  $("#messages").append(card);
  scrollDown();
  return card;
}

function finishToolCard(card, ok, result) {
  if (!card) return;
  card.classList.toggle("fail", !ok);
  const summary = card.querySelector("summary");
  summary.textContent = summary.textContent.replace("… executando", ok ? "✓" : "✗");
  card.querySelector("pre").replaceChildren(...linkify(result));
  const photo = /\[foto:(foto-[\d-]+\.jpg)\]/.exec(result); // tirar_foto: mostra a imagem no próprio cartão
  if (photo && ok) card.append(photoNode(photo[1]));
  const live = /\[camera:(pc|celular)\]/.exec(result); // mostrar_camera: vídeo ao vivo no próprio cartão
  if (live && ok) card.append(liveNode(live[1]));
}

// ---------- Aparelhos: localização e câmeras ----------
const wsBase = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}`;

// Vídeo ao vivo (MJPEG): fechar a imagem encerra a conexão e o servidor desliga a câmera.
function liveNode(origem) {
  const img = el("img", { src: `/api/camera/${origem}/stream?t=${Date.now()}`, alt: `Câmera ${origem} ao vivo` });
  const box = el("div", { className: "live" }, img);
  const stop = () => { img.removeAttribute("src"); box.remove(); };
  img.onerror = () => { box.replaceChildren(el("p", { className: "hint", textContent: "A câmera parou ou não está disponível." })); };
  box.append(el("button", { className: "danger", textContent: `Parar câmera ${origem === "pc" ? "do PC" : "do celular"}`, onclick: stop }));
  return box;
}

async function handleDeviceRequest(ev) {
  const reply = (ok, data, error) => state.ws?.send(JSON.stringify({ type: "device_response", id: ev.id, ok, data, error }));
  if (ev.kind === "geo") {
    if (!navigator.geolocation) return reply(false, null, "este navegador não informa localização");
    navigator.geolocation.getCurrentPosition(
      (p) => reply(true, { lat: p.coords.latitude, lon: p.coords.longitude, accuracy: p.coords.accuracy }),
      (e) => reply(false, null, e.code === 1 ? "permissão de localização negada no navegador" : e.message),
      { enableHighAccuracy: true, timeout: 15000, maximumAge: 60000 });
  } else if (ev.kind === "camera_start") {
    try { await startPublishing(); reply(true, {}); } catch (e) { reply(false, null, `câmera indisponível: ${e.message}`); }
  } else if (ev.kind === "camera_snapshot") {
    try { reply(true, { jpeg: await snapshot() }); } catch (e) { reply(false, null, `câmera indisponível: ${e.message}`); }
  } else {
    reply(false, null, "pedido desconhecido");
  }
}

// Uma foto só, para a Sarah analisar: a câmera liga, ajusta a exposição por ~1 s e desliga. O aparelho avisa na tela.
async function snapshot() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("a câmera só funciona em localhost ou HTTPS");
  if (!("ImageCapture" in window)) throw new Error("este navegador não tira foto direta (use Chrome ou Edge)");
  notify("📷 A Sarah está tirando uma foto com a câmera deste aparelho.");
  const stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: "environment", width: 1280, height: 960 }, audio: false });
  try {
    await new Promise((r) => setTimeout(r, 1000)); // exposição automática
    const frame = await new ImageCapture(stream.getVideoTracks()[0]).grabFrame();
    const scale = Math.min(1, 1024 / Math.max(frame.width, frame.height));
    const canvas = el("canvas", { width: Math.round(frame.width * scale), height: Math.round(frame.height * scale) });
    canvas.getContext("2d").drawImage(frame, 0, 0, canvas.width, canvas.height);
    return canvas.toDataURL("image/jpeg", 0.85).split(",")[1];
  } finally {
    stream.getTracks().forEach((t) => t.stop());
  }
}

// Transmite a câmera DESTE aparelho (ex.: celular → PC). Faixa vermelha visível o tempo todo; para em 10 min.
const pub = { stream: null, ws: null, timer: null, stopAt: null, facing: "environment" };

async function startPublishing() {
  if (pub.stream) return;
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("a câmera só funciona em localhost ou HTTPS");
  pub.stream = await navigator.mediaDevices.getUserMedia({ video: { facingMode: pub.facing, width: 640, height: 480 }, audio: false });
  // a prévia fica na faixa: um <video> fora da página não decodifica quadros (o canvas saía 2x2)
  const video = $("#pub-preview");
  video.srcObject = pub.stream;
  await video.play();
  pub.ws = new WebSocket(`${wsBase}/ws/camera`);
  pub.ws.onclose = stopPublishing;
  const canvas = document.createElement("canvas");
  pub.timer = setInterval(() => {
    if (pub.ws?.readyState !== WebSocket.OPEN || pub.ws.bufferedAmount > 200000 || !video.videoWidth) return;
    canvas.width = video.videoWidth;
    canvas.height = video.videoHeight;
    canvas.getContext("2d").drawImage(video, 0, 0);
    canvas.toBlob((b) => b && pub.ws?.readyState === WebSocket.OPEN && pub.ws.send(b), "image/jpeg", 0.6);
  }, 150);
  pub.stopAt = setTimeout(stopPublishing, 600000);
  $("#pub-banner").hidden = false;
}

function stopPublishing() {
  clearInterval(pub.timer);
  clearTimeout(pub.stopAt);
  pub.stream?.getTracks().forEach((t) => t.stop());
  $("#pub-preview").srcObject = null;
  const ws = pub.ws;
  Object.assign(pub, { stream: null, ws: null, timer: null, stopAt: null });
  if (ws && ws.readyState <= WebSocket.OPEN) ws.close();
  $("#pub-banner").hidden = true;
}

$("#pub-stop").addEventListener("click", stopPublishing);
$("#pub-flip").addEventListener("click", async () => {
  pub.facing = pub.facing === "environment" ? "user" : "environment";
  stopPublishing();
  try { await startPublishing(); } catch (e) { notify(`Câmera indisponível: ${e.message}`); }
});

$("#cam-pc").addEventListener("click", () => $("#cam-view").replaceChildren(liveNode("pc")));
$("#cam-phone").addEventListener("click", async () => {
  $("#cam-view").replaceChildren(el("p", { className: "hint", textContent: "Pedindo ao celular para ligar a câmera…" }));
  try {
    await api("/api/camera/celular/start", { method: "POST" });
    $("#cam-view").replaceChildren(liveNode("celular"));
  } catch (e) { $("#cam-view").replaceChildren(el("p", { className: "error", textContent: e.message })); }
});
$("#cam-self").addEventListener("click", async () => {
  try { await startPublishing(); } catch (e) { notify(`Câmera indisponível: ${e.message}`); }
});

function photoNode(name) {
  const url = `/api/photos/${encodeURIComponent(name)}`;
  return el("a", { href: url, target: "_blank", className: "photo" },
    el("img", { src: url, alt: `Foto ${name}`, loading: "lazy" }));
}

// Endereços https viram links (ex.: "abrir" de cada e-mail); o resto continua texto puro.
function linkify(text) {
  return text.split(/(https:\/\/[^\s<>"']+)/).map((part, i) => (i % 2
    ? el("a", { href: part, textContent: part, target: "_blank", rel: "noopener noreferrer" })
    : document.createTextNode(part)));
}

function addApproval(ev) {
  $("#messages").querySelector(".empty")?.remove();
  const answer = (ok) => {
    state.ws?.send(JSON.stringify({ type: "approve", id: ev.id, ok }));
    closeApproval(ev.id, ok ? "Aprovado." : "Recusado: nada foi feito.");
  };
  const card = el("div", { className: "msg approval", id: `approval-${ev.id}`, role: "alertdialog", ariaLabel: "Confirmação necessária" },
    el("strong", { textContent: `⚠️ Confirmação necessária: ${ev.label}` }),
    el("div", { textContent: ev.summary }),
    ...(ev.detail ? [el("details", { open: true }, el("summary", { textContent: "Detalhes (o que vai mudar)" }), diffNode(ev.detail))] : []),
    el("div", { className: "row" },
      el("button", { className: "primary", textContent: "Aprovar", onclick: () => answer(true) }),
      el("button", { className: "danger", textContent: "Recusar", onclick: () => answer(false) })));
  $("#messages").append(card);
  scrollDown();
  card.querySelector("button.danger").focus(); // foco no botão seguro
  if (prefs.speak) ttsFeed("Preciso da sua confirmação na tela.", true);
}

// Diff com cores; cada linha vira texto puro (sem HTML vindo do servidor).
function diffNode(text) {
  const kind = (l) => (l.startsWith("+") && !l.startsWith("+++") ? "add" : l.startsWith("-") && !l.startsWith("---") ? "del" : l.startsWith("@@") ? "hunk" : "");
  return el("pre", { className: "diff" }, ...text.split("\n").map((l) => el("span", { className: kind(l), textContent: `${l}\n` })));
}

// Modo programação: outro conjunto de ferramentas e o fluxo de área isolada.
let codeMode = (() => { try { return localStorage.getItem("jarvis-code") === "1"; } catch { return false; } })();
function setCodeMode(on) {
  codeMode = on;
  try { localStorage.setItem("jarvis-code", on ? "1" : "0"); } catch { /* modo privado */ }
  $("#code-btn").setAttribute("aria-pressed", on);
  $("#input").placeholder = on ? "Modo programação: descreva o projeto ou a tarefa de código…" : "Digite uma mensagem…";
}
$("#code-btn").addEventListener("click", () => setCodeMode(!codeMode));
setCodeMode(codeMode);

function closeApproval(id, text) {
  const card = document.getElementById(`approval-${id}`);
  if (!card || card.querySelector("button").disabled) return;
  card.querySelectorAll("button").forEach((b) => (b.disabled = true));
  card.append(el("div", { className: "hint", textContent: text }));
}

// ---------- Tarefas de outros aparelhos (ex.: começou no PC, acompanha no celular) ----------
async function refreshTasks() {
  if ($("#app-view").hidden || document.visibilityState !== "visible") return;
  let tasks;
  try { tasks = await api("/api/tasks"); } catch { return; }
  const others = tasks.filter((t) => t.id !== state.taskId);
  $("#tasks-panel").hidden = !others.length;
  $("#tasks-panel").replaceChildren(...others.flatMap((t) => [
    el("div", { className: "task" },
      el("span", { className: "grow", textContent: `⏳ Em andamento (${t.origin === "remoto" ? "celular" : "PC"}${t.mode === "codigo" ? ", programação" : ""}): "${t.text}"` }),
      el("button", { className: "danger", textContent: "Parar", onclick: () => api(`/api/tasks/${t.id}/stop`, { method: "POST" }).then(refreshTasks) })),
    ...t.approvals.map((a) => el("div", { className: "msg approval" },
      el("strong", { textContent: `⚠️ Confirmação: ${a.label}` }), el("div", { textContent: a.summary }),
      ...(a.detail ? [el("details", {}, el("summary", { textContent: "Detalhes" }), diffNode(a.detail))] : []),
      el("div", { className: "row" },
        el("button", { className: "primary", textContent: "Aprovar", onclick: () => answerRemote(a.id, true) }),
        el("button", { className: "danger", textContent: "Recusar", onclick: () => answerRemote(a.id, false) })))),
  ]));
}

async function answerRemote(id, ok) {
  try { await api(`/api/approvals/${id}`, { method: "POST", body: { ok } }); } catch (e) { notify(e.message); }
  refreshTasks();
}
setInterval(refreshTasks, 3000);

// ---------- Aba Ferramentas ----------
async function loadTools() {
  showTools(await api("/api/tools"));
  loadGoogle();
  loadFace();
}

async function loadFace() {
  const f = await api("/api/face");
  $("#face-status").textContent = f.enabled
    ? (f.can_use_camera ? "Ativo. A câmera só abre quando você pede; fotos só são salvas com \"Tirar foto\". O reconhecimento é só informativo: uma foto pode enganar, então não serve como senha."
      : "Ativo, mas a câmera do PC pelo celular está desligada (JARVIS_REMOTE_CAMERA no .env).")
    : f.feature_on ? "Ativado no .env, mas faltam os modelos: rode .venv\\Scripts\\python.exe -m jarvis.face e reinicie."
    : "Desativado (padrão). Para ativar: JARVIS_FACE=on no .env, baixe os modelos (python -m jarvis.face) e reinicie. Detalhes em docs/INTEGRATIONS.md.";
  $("#face-controls").hidden = !f.enabled;
  $("#face-enroll").disabled = $("#face-identify").disabled = $("#face-photo").disabled = !f.can_use_camera;
  showFacePeople(f.people);
  showPhotos(f.photos);
}

function showPhotos(names) {
  $("#photos-wipe").hidden = !names.length;
  $("#photo-list").replaceChildren(...(names.length ? names.map((n) => el("figure", {}, photoNode(n),
    el("figcaption", {}, n.replace(/foto-(\d{4})(\d\d)(\d\d)-(\d\d)(\d\d)(\d\d).*/, "$3/$2/$1 $4:$5:$6"), " ",
      el("button", { className: "danger", textContent: "Apagar", ariaLabel: `Apagar ${n}`, onclick: async () => {
        if (!confirm("Apagar esta foto?")) return;
        showPhotos((await api(`/api/photos/${encodeURIComponent(n)}`, { method: "DELETE" })).photos);
      } }))))
    : [el("p", { className: "hint", textContent: "Nenhuma foto salva." })]));
}

$("#face-photo").addEventListener("click", async () => {
  $("#face-result").textContent = "Tirando a foto…";
  try {
    const r = await api("/api/face/photo", { method: "POST" });
    $("#face-result").replaceChildren(`Foto salva. ${r.texto}`, photoNode(r.foto));
    showPhotos(r.photos);
  } catch (e) { $("#face-result").textContent = e.message; }
});
$("#photos-wipe").addEventListener("click", async () => {
  if (!confirm("Apagar TODAS as fotos salvas? Isso não pode ser desfeito.")) return;
  showPhotos((await api("/api/photos", { method: "DELETE" })).photos);
});

function showFacePeople(list) {
  $("#face-people").replaceChildren(...(list.length ? list.map((p) => el("li", {},
    el("div", { className: "grow", textContent: `${p.nome} (${p.amostras} amostras)` }),
    el("button", { className: "danger", textContent: "Remover", onclick: async () => {
      if (!confirm(`Apagar os dados faciais de ${p.nome}?`)) return;
      showFacePeople((await api(`/api/face/people/${encodeURIComponent(p.nome)}`, { method: "DELETE" })).people);
    } })))
    : [el("li", { className: "hint", textContent: "Ninguém cadastrado." })]));
}

$("#face-enroll").addEventListener("click", async () => {
  const nome = $("#face-name").value.trim();
  if (!nome) return $("#face-name").focus();
  $("#face-result").textContent = "Olhe para a câmera por uns 3 segundos…";
  try {
    const r = await api("/api/face/enroll", { method: "POST", body: { nome } });
    $("#face-result").textContent = `Cadastrado: ${nome} (${r.amostras} amostras).`;
    showFacePeople(r.people);
  } catch (e) { $("#face-result").textContent = e.message; }
});
$("#face-identify").addEventListener("click", async () => {
  $("#face-result").textContent = "Olhando a câmera…";
  try { $("#face-result").textContent = (await api("/api/face/identify", { method: "POST" })).texto; }
  catch (e) { $("#face-result").textContent = e.message; }
});
$("#face-wipe").addEventListener("click", async () => {
  if (!confirm("Apagar TODOS os dados faciais? Isso não pode ser desfeito.")) return;
  showFacePeople((await api("/api/face/people", { method: "DELETE" })).people);
  $("#face-result").textContent = "Todos os dados faciais foram apagados.";
});

async function loadGoogle() {
  const g = await api("/api/google");
  $("#google-status").textContent = g.connecting ? "Aguardando você autorizar no navegador do PC… Se o Google mostrou "
      + "\"Acesso bloqueado\", adicione seu e-mail em Audience → Test users no Google Cloud e clique em \"Abrir login de novo\"."
    : g.connected && g.needs_reconnect ? `Conectada: ${g.email || "(conta)"}. Há permissões novas (ex.: ver a lista de agendas): clique em Reconectar.`
    : g.connected ? `Conectada: ${g.email || "(conta)"}. Lê e busca e-mails, baixa anexos, cria rascunhos e vê agendas; enviar e criar, alterar ou apagar eventos pede confirmação.`
    : g.error ? g.error
    : !g.configured ? "Não configurada. Crie o projeto no Google Cloud e coloque o client_secret.json em data\\google (passo a passo em docs/INTEGRATIONS.md)."
    : "Pronta para conectar.";
  $("#google-connect").hidden = (g.connected && !g.needs_reconnect) || !g.configured || !g.can_connect;
  $("#google-connect").textContent = g.connecting ? "Abrir login de novo" : g.connected ? "Reconectar" : "Conectar conta Google";
  $("#google-disconnect").hidden = !g.connected;
  if (g.connecting) setTimeout(loadGoogle, 2000);
}

$("#google-connect").addEventListener("click", async () => {
  try { await api("/api/google/connect", { method: "POST" }); } catch (e) { return notify(e.message); }
  setTimeout(loadGoogle, 800);
});
$("#google-disconnect").addEventListener("click", async () => {
  if (!confirm("Desconectar a conta Google? O acesso é revogado no Google e o token local é apagado.")) return;
  await api("/api/google/disconnect", { method: "POST" });
  loadGoogle();
});

function showTools(d) {
  $("#tools-mode").value = d.mode;
  $("#tools-mode").disabled = !d.can_change;
  $("#tools-note").textContent = d.error || (d.can_change ? "" : "Sessão remota: só ferramentas de leitura; mudanças só no próprio PC.");
  const riskName = { leitura: "leitura", acao: "ação", perigosa: "perigosa · confirma" };
  $("#tools-list").replaceChildren(...d.tools.map((t) => {
    const box = el("input", { type: "checkbox", checked: t.enabled, disabled: !d.can_change, id: `tool-${t.name}` });
    box.addEventListener("change", saveTools);
    return el("li", {}, box,
      el("label", { className: "grow", htmlFor: `tool-${t.name}` }, `${t.label} `,
        el("span", { className: `badge ${t.risk}`, textContent: riskName[t.risk] }),
        ...(t.group === "codigo" ? [" ", el("span", { className: "badge codigo", textContent: "programação" })] : []),
        el("small", { textContent: t.description })));
  }));
  const p = d.permissions;
  const isWorkspace = (x) => x.toLowerCase() === (p.workspace || "").toLowerCase();
  $("#folder-list").replaceChildren(...p.pastas.map((x) => el("li", {},
    el("div", { className: "grow", textContent: x }, ...(isWorkspace(x) ? [el("small", { textContent: "Área de trabalho da Sarah (sempre liberada)" })] : [])),
    ...(d.can_change && !isWorkspace(x) ? [el("button", { className: "danger", textContent: "Retirar", onclick: () => setFolder(x, false) })] : []))));
  $("#folder-suggest").replaceChildren(...(d.can_change ? p.sugestoes.map((s) => el("button", {
    type: "button", textContent: `+ ${s.nome}`, title: s.caminho, onclick: () => setFolder(s.caminho, true) })) : []));
  $("#folder-form").hidden = !d.can_change;
  $("#tools-perms").replaceChildren(el("dl", {},
    el("dt", { textContent: "Aplicativos" }), el("dd", { textContent: p.aplicativos.join(", ") || "nenhum" }),
    el("dt", { textContent: "Scripts aprovados" }), el("dd", { textContent: p.scripts.join(", ") || "nenhum" })));
}

async function saveTools() {
  const disabled = [...document.querySelectorAll("#tools-list input")].filter((b) => !b.checked).map((b) => b.id.slice(5));
  try { showTools(await api("/api/tools", { method: "PUT", body: { mode: $("#tools-mode").value, disabled } })); }
  catch (e) { notify(e.message); loadTools(); }
}
$("#tools-mode").addEventListener("change", saveTools);

async function setFolder(caminho, autorizar) {
  const ask = autorizar ? `Liberar ${caminho}?\n\nA Sarah poderá listar, criar e mover arquivos ali, e apagar (sempre com sua confirmação).`
    : `Retirar o acesso da Sarah a ${caminho}?`;
  if (!caminho || !confirm(ask)) return;
  try {
    showTools(await api("/api/permissions/folders", { method: "POST", body: { caminho, autorizar } }));
    $("#folder-input").value = "";
  } catch (e) { notify(e.message); }
}
$("#folder-form").addEventListener("submit", (e) => { e.preventDefault(); setFolder($("#folder-input").value.trim(), true); });

// ---------- Voz ----------
const VOICE_DEFAULTS = { speak: true, voice: "pf_dora", speed: 1, mic: "", out: "", silence: 0.02 };
const prefs = (() => {
  try { return { ...VOICE_DEFAULTS, ...JSON.parse(localStorage.getItem("jarvis-voice") || "{}") }; } catch { return { ...VOICE_DEFAULTS }; }
})();
function savePrefs() { try { localStorage.setItem("jarvis-voice", JSON.stringify(prefs)); } catch { /* modo privado */ } }

const rec = { active: false, recorder: null, stream: null, ctx: null, timer: null };
const tts = { gen: 0, buffer: "", chain: Promise.resolve(), audio: null, speaking: false };

async function openMic() {
  if (!navigator.mediaDevices?.getUserMedia) throw new Error("o navegador só libera o microfone em localhost ou HTTPS.");
  return navigator.mediaDevices.getUserMedia({ audio: prefs.mic ? { deviceId: { exact: prefs.mic } } : true });
}

// Mede o volume e chama onTick(rms) a cada 100 ms até stopLevel().
function watchLevel(stream, onTick) {
  rec.ctx = new AudioContext();
  const analyser = rec.ctx.createAnalyser();
  analyser.fftSize = 2048;
  rec.ctx.createMediaStreamSource(stream).connect(analyser);
  const buf = new Float32Array(analyser.fftSize);
  rec.timer = setInterval(() => {
    analyser.getFloatTimeDomainData(buf);
    const rms = Math.sqrt(buf.reduce((s, v) => s + v * v, 0) / buf.length);
    $("#mic-level").value = Math.min(rms * 8, 1);
    avatar.level(rms);
    onTick(rms);
  }, 100);
}
function stopLevel() { clearInterval(rec.timer); rec.ctx?.close(); rec.ctx = null; $("#mic-level").value = 0; avatar.level(0); }

async function startRecording() {
  ttsStop();
  try { rec.stream = await openMic(); } catch (e) { return addMessage("error", `Microfone indisponível: ${e.message}`); }
  const chunks = [];
  rec.recorder = new MediaRecorder(rec.stream);
  rec.recorder.ondataavailable = (e) => e.data.size && chunks.push(e.data);
  rec.recorder.onstop = () => sendAudio(new Blob(chunks, { type: rec.recorder.mimeType }));
  rec.recorder.start();
  setMic(true);
  // Para sozinho após 1,2 s de silêncio depois de ouvir fala, após 8 s sem fala ou em 60 s.
  const started = Date.now();
  let heard = false, quietSince = Date.now();
  watchLevel(rec.stream, (rms) => {
    if (rms > prefs.silence) { heard = true; quietSince = Date.now(); }
    const now = Date.now();
    if ((heard && now - quietSince > 1200) || (!heard && now - started > 8000) || now - started > 60000) stopRecording();
  });
}

function stopRecording() {
  if (!rec.active) return;
  stopLevel();
  if (rec.recorder?.state === "recording") rec.recorder.stop();
  rec.stream?.getTracks().forEach((t) => t.stop());
  setMic(false);
}

function setMic(on) {
  rec.active = on;
  $("#mic-btn").setAttribute("aria-pressed", on);
  $("#mic-btn").setAttribute("aria-label", on ? "Parar de ouvir" : "Falar (clique de novo para parar)");
  updateControls();
}

async function sendAudio(blob) {
  const note = addMessage("note", "Transcrevendo…");
  try {
    const r = await fetch("/api/stt", { method: "POST", headers: { "Content-Type": blob.type || "application/octet-stream" }, body: blob });
    if (r.status === 401) return showLogin();
    const data = await r.json();
    if (!r.ok) throw new Error(data.detail || `Erro ${r.status}`);
    note.remove();
    if (!data.text) return addMessage("error", "Não ouvi nada. Tente de novo mais perto do microfone.");
    $("#input").value = data.text;
    send();
  } catch (e) { note.remove(); addMessage("error", `Falha na transcrição: ${e.message}`); }
}

$("#mic-btn").addEventListener("click", () => (rec.active ? stopRecording() : startRecording()));

// Fala frase a frase enquanto o texto ainda chega, para reduzir a espera.
function ttsFeed(text, final = false) {
  if (!prefs.speak) return;
  tts.buffer += text;
  let m;
  while ((m = tts.buffer.match(/^([\s\S]*?[.!?…\n])\s+/)) || tts.buffer.length > 300) {
    const cut = m ? m[0].length : Math.max(tts.buffer.lastIndexOf(" ", 300), 1);
    ttsEnqueue(tts.buffer.slice(0, cut));
    tts.buffer = tts.buffer.slice(cut);
  }
  if (final) { ttsEnqueue(tts.buffer); tts.buffer = ""; }
}

function ttsEnqueue(sentence) {
  if (!/[\p{L}\p{N}]/u.test(sentence)) return;
  const gen = tts.gen;
  const audio = fetch("/api/tts", { // começa a sintetizar enquanto a frase anterior ainda toca
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ text: sentence.slice(0, 1000), voice: prefs.voice, speed: prefs.speed }),
  }).then((r) => (r.status === 200 ? r.blob() : null)).catch(() => null);
  tts.chain = tts.chain.then(async () => {
    const blob = await audio;
    const env = blob && gen === tts.gen ? await envelope(blob) : null;
    if (blob && gen === tts.gen) await playBlob(blob, env); // Parar durante a análise também cancela
  });
}

function playBlob(blob, env = null) {
  tts.env = env;
  return new Promise((resolve) => {
    const a = new Audio(URL.createObjectURL(blob));
    if (prefs.out && a.setSinkId) a.setSinkId(prefs.out).catch(() => {});
    const end = () => { URL.revokeObjectURL(a.src); tts.audio = null; tts.env = null; setSpeaking(false); resolve(); };
    a.onended = a.onerror = a.onpause = end;
    tts.audio = a;
    setSpeaking(true);
    a.play().catch(end);
  });
}

function setSpeaking(on) { tts.speaking = on; updateControls(); }
function ttsStop() { tts.gen++; tts.buffer = ""; tts.audio?.pause(); }

function setSpeak(on) {
  prefs.speak = on;
  savePrefs();
  $("#speak-toggle").setAttribute("aria-pressed", on);
  $("#speak-label").textContent = $("#speak-toggle").title = on ? "Respostas faladas: ligadas" : "Respostas faladas: desligadas";
  $("#pref-speak").checked = on;
  if (!on) ttsStop();
}
$("#speak-toggle").addEventListener("click", () => setSpeak(!prefs.speak));

async function loadVoice() {
  showWake(await api("/api/wake"));
  api("/api/autostart").then((a) => { $("#autostart").checked = a.ligado; $("#autostart").disabled = !a.can_change; });
  const s = await api("/api/voice/status");
  $("#voice-status").textContent = s.stt && s.tts
    ? `Modelos prontos: Whisper ${s.whisper_model} (transcrição) e Kokoro (fala), rodando na CPU.`
    : "Modelos de voz não encontrados. No PC, rode: .venv\\Scripts\\python.exe -m jarvis.voice";
  $("#pref-voice").replaceChildren(...Object.entries(s.voices).map(([id, name]) => el("option", { value: id, textContent: name })));
  $("#pref-voice").value = prefs.voice;
  $("#pref-speed").value = prefs.speed;
  $("#speed-out").textContent = `${Number(prefs.speed).toFixed(2)}×`;
  $("#pref-silence").value = prefs.silence;
  $("#pref-speak").checked = prefs.speak;
  // Os nomes dos dispositivos só aparecem depois que o microfone foi autorizado uma vez.
  const devices = (await navigator.mediaDevices?.enumerateDevices?.()) ?? [];
  const fill = (sel, kind) => $(sel).replaceChildren(el("option", { value: "", textContent: "Padrão do sistema" }),
    ...devices.filter((d) => d.kind === kind && d.deviceId && d.deviceId !== "default")
      .map((d, i) => el("option", { value: d.deviceId, textContent: d.label || `Dispositivo ${i + 1}` })));
  fill("#pref-mic", "audioinput");
  fill("#pref-out", "audiooutput");
  $("#pref-mic").value = prefs.mic;
  $("#pref-out").value = prefs.out;
  $("#pref-out").disabled = !("setSinkId" in HTMLMediaElement.prototype);
}

$("#pref-speak").addEventListener("change", (e) => setSpeak(e.target.checked));

function showWake(w) {
  $("#wake-mode").value = w.wanted ?? w.mode; // a escolha do usuário, mesmo que o microfone esteja fora agora
  $("#wake-mode").disabled = !w.can_change;
  $("#wake-mode").querySelectorAll("option[value=palavra], option[value=ambos]").forEach((o) => (o.disabled = !w.available.palavra));
  $("#wake-note").textContent = !w.can_change ? "Só pode ser alterada no próprio PC."
    : w.error || (w.available.palavra ? "" : "Gatilho \"Sarah\" sem modelo: rode .venv\\Scripts\\python.exe -m jarvis.listener. As palmas funcionam sem instalar nada.");
  setWakePill(w.mode, w.wanted ?? w.mode);
  document.querySelectorAll(".wake-local").forEach((n) => (n.hidden = !w.can_change));
  if (!w.can_change) return;
  $("#wake-device").replaceChildren(el("option", { value: "", textContent: "Padrão do Windows" }),
    ...w.devices.map((name) => el("option", { value: name, textContent: name })));
  $("#wake-device").value = w.device;
  $("#clap-result").textContent ||= `Ajuste atual: pico mínimo ${w.clap.min_peak}, ${w.clap.ratio}× acima do ruído.`;
}

$("#wake-mode").addEventListener("change", async (e) => {
  try { showWake(await api("/api/wake", { method: "POST", body: { mode: e.target.value } })); } catch (err) { notify(err.message); }
});

$("#autostart").addEventListener("change", async (e) => {
  try {
    const a = await api("/api/autostart", { method: "POST", body: { ligar: e.target.checked } });
    notify(a.ligado ? "A Sarah vai iniciar sozinha com o Windows, sem janela." : "A Sarah não inicia mais com o Windows.");
  } catch (err) { e.target.checked = !e.target.checked; notify(err.message); }
});

$("#wake-device").addEventListener("change", async (e) => {
  try { showWake(await api("/api/wake/settings", { method: "POST", body: { device: e.target.value } })); } catch (err) { notify(err.message); }
});

let clapSuggestion = null;
$("#clap-calibrate").addEventListener("click", async () => {
  const btn = $("#clap-calibrate"), out = $("#clap-result");
  btn.disabled = true;
  $("#clap-apply").hidden = true;
  out.textContent = "Ouvindo por 12 s… bata duas palmas, espere 2 s e bata mais duas.";
  try {
    const r = await api("/api/wake/calibrate", { method: "POST" });
    clapSuggestion = r.sugestao;
    const loud = r.estalos.map((s) => `${s.destaque}×`).join(", ") || "nenhum";
    out.textContent = r.ruido < 0.0002
      ? `O microfone "${r.microfone}" não captou som nenhum (silêncio digital). Escolha outro microfone acima.`
      : !r.sugestao
        ? `Microfone "${r.microfone}": ruído ${r.ruido}, estalos: ${loud}. Nenhuma palma clara; tente de novo, mais perto ou mais forte.`
        : `Microfone "${r.microfone}": ruído ${r.ruido}, estalos: ${loud}. Sugestão: pico mínimo ${r.sugestao.min_peak}, ${r.sugestao.ratio}× acima do ruído.`;
    $("#clap-apply").hidden = !r.sugestao;
  } catch (err) {
    out.textContent = err.message;
  } finally {
    btn.disabled = false;
  }
});

$("#clap-apply").addEventListener("click", async () => {
  try {
    showWake(await api("/api/wake/settings", { method: "POST", body: clapSuggestion }));
    $("#clap-apply").hidden = true;
    $("#clap-result").textContent = "Ajuste aplicado. Ligue a escuta em \"Duas palmas\" e teste.";
  } catch (err) { notify(err.message); }
});

// Bipe curto avisando que a Sarah começou a ouvir.
function beep() {
  const ctx = new AudioContext();
  const osc = ctx.createOscillator();
  const gain = ctx.createGain();
  osc.frequency.value = 880;
  gain.gain.setValueAtTime(0.15, ctx.currentTime);
  gain.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 0.15);
  osc.connect(gain).connect(ctx.destination);
  osc.start();
  osc.stop(ctx.currentTime + 0.15);
  osc.onended = () => ctx.close();
}
for (const [id, key, num] of [["#pref-voice", "voice"], ["#pref-speed", "speed", true], ["#pref-mic", "mic"], ["#pref-out", "out"], ["#pref-silence", "silence", true]]) {
  $(id).addEventListener("input", (e) => {
    prefs[key] = num ? Number(e.target.value) : e.target.value;
    if (key === "speed") $("#speed-out").textContent = `${prefs.speed.toFixed(2)}×`;
    savePrefs();
  });
}

$("#test-voice").addEventListener("click", () => {
  const was = prefs.speak;
  prefs.speak = true;
  ttsStop();
  ttsFeed("Olá! Esta é a minha voz. Estou pronta para ajudar.", true);
  prefs.speak = was;
});

$("#test-mic").addEventListener("click", async () => {
  let stream;
  try { stream = await openMic(); } catch (e) { return notify(`Microfone indisponível: ${e.message}`); }
  let peak = 0;
  watchLevel(stream, (rms) => { peak = Math.max(peak, rms); });
  setTimeout(() => {
    stopLevel();
    stream.getTracks().forEach((t) => t.stop());
    notify(peak > prefs.silence ? `Microfone OK (pico ${peak.toFixed(3)}; limite ${prefs.silence}).`
      : `Sinal baixo (pico ${peak.toFixed(3)}). Fale mais perto ou mova a sensibilidade para a esquerda.`);
    loadVoice();
  }, 3000);
});

// ---------- Memória ----------
async function loadMemories() {
  const list = await api("/api/memories");
  $("#memory-list").replaceChildren(...(list.length ? list.map((m) => el("li", {},
    el("div", { className: "grow" }, m.content, el("small", { textContent: fmtDate(m.created_at) })),
    el("button", { textContent: "Editar", onclick: () => editMemory(m) }),
    el("button", { className: "danger", textContent: "Excluir", onclick: () => deleteMemory(m) })))
    : [el("li", { className: "hint", textContent: "Nenhuma memória salva." })]));
}

$("#memory-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  await api("/api/memories", { method: "POST", body: { content: $("#memory-input").value } });
  $("#memory-input").value = "";
  loadMemories();
});

async function editMemory(m) {
  const content = prompt("Editar memória:", m.content);
  if (content === null || !content.trim()) return;
  await api(`/api/memories/${m.id}`, { method: "PUT", body: { content } });
  loadMemories();
}

async function deleteMemory(m) {
  if (!confirm(`Excluir a memória "${m.content}"?`)) return;
  await api(`/api/memories/${m.id}`, { method: "DELETE" });
  loadMemories();
}

// ---------- Segurança ----------
const fmtBytes = (n) => (n >= 1e9 ? `${(n / 1e9).toFixed(1)} GB` : n >= 1e6 ? `${(n / 1e6).toFixed(1)} MB`
  : n >= 1e3 ? `${Math.round(n / 1e3)} KB` : `${n} B`);

function showStorage(r) {
  $("#storage-list").replaceChildren(...r.itens.map((i) => el("li", {},
    el("div", { className: "grow", textContent: i.nome }), el("strong", { textContent: fmtBytes(i.bytes) }))));
  $("#storage-note").textContent = `${r.conversas} conversa(s), ${r.mensagens} mensagem(ns), ${r.auditoria} evento(s) de auditoria `
    + `(os com mais de ${r.dias.auditoria} dias saem sozinhos). Áreas sem uso há ${r.dias.areas}+ dias: ${r.areas_antigas}; `
    + `backups com ${r.dias.backups}+ dias: ${r.backups_antigos}.`;
  $("#clean-areas").disabled = !r.areas_antigas;
  $("#clean-backups").disabled = !r.backups_antigos;
}

async function cleanStorage(what, ask) {
  if (!confirm(ask)) return;
  const r = await api("/api/storage/cleanup", { method: "POST", body: { [what]: true } });
  showStorage(r);
  notify(`Pronto: ${fmtBytes(r.liberado)} liberados.`);
}
$("#clean-areas").addEventListener("click", () => cleanStorage("areas",
  "Apagar as áreas de programação sem uso há 7 dias ou mais? Alterações que não foram integradas ao projeto original se perdem."));
$("#clean-backups").addEventListener("click", () => cleanStorage("backups", "Apagar os backups com 30 dias ou mais?"));
$("#clean-compact").addEventListener("click", () => cleanStorage("compactar", "Compactar o banco agora? Leva alguns segundos."));

async function loadSecurity() {
  api("/api/storage").then(showStorage);
  api("/api/remote").then((r) => {
    $("#remote-status").textContent = !r.installed ? "Tailscale não instalado: a Sarah só funciona neste PC."
      : !r.online ? "Tailscale instalado, mas desconectado (ícone do Tailscale → Connect)."
      : !r.serving ? `Tailscale conectado (${r.name}), mas a Sarah ainda não está publicada na tailnet.`
      : `Ativo em ${r.url}, só para aparelhos da sua conta Tailscale. Pelo celular: `
        + (r.remote_tools_all ? "ações e aprovações liberadas (sempre com confirmação)."
          : "só ferramentas de leitura; você pode recusar e parar tarefas, mas aprovar ações está desligado.");
  }).catch(() => {});
  const [sessions, audit] = await Promise.all([api("/api/sessions"), api("/api/audit")]);
  $("#session-list").replaceChildren(...sessions.map((s) => el("li", {}, el("div", { className: "grow" },
    `${s.remote ? "Remota" : "Local"}${s.current ? " (esta)" : ""} · ${s.user_agent || "?"}`,
    el("small", { textContent: `Início ${fmtDate(s.created_at)} · expira ${fmtDate(s.expires_at)}` })))));
  $("#audit-list").replaceChildren(...audit.map((a) => el("li", {},
    el("div", { className: "grow", textContent: `${fmtDate(a.ts)}  ${a.actor}  ${a.action}  ${a.detail === "{}" ? "" : a.detail}` }))));
}

$("#revoke-btn").addEventListener("click", async () => {
  const { revoked } = await api("/api/sessions/revoke-others", { method: "POST" });
  notify(`${revoked} sessão(ões) encerrada(s).`);
  loadSecurity();
});
$("#logout-btn").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }); showLogin(); });
$("#wipe-history").addEventListener("click", async () => {
  if (!confirm("Apagar TODAS as conversas? Isso não pode ser desfeito.")) return;
  const { deleted } = await api("/api/conversations", { method: "DELETE" });
  notify(`${deleted} conversa(s) apagada(s).`);
  openConversation(null);
});

setSpeak(prefs.speak);

// ---------- Início ----------
fetch("/api/me").then((r) => (r.ok ? start() : showLogin()));
