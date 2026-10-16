"use strict";
// ---------- Rosto da Sarah ----------
// A imagem web/sarah.webp é deformada por uma malha (WebGL), como nos avatares 2D animados: a boca abre por uma fenda
// entre os lábios, as pálpebras fecham, os olhos olham em volta, as sobrancelhas sobem, a boca sorri e a cabeça gira
// em falso 3D (o nariz anda mais que as bordas). Sem WebGL 2, fica a imagem parada.
const avatar = (() => {
  const CAPTIONS = { idle: "Pronta para ajudar", listening: "Sarah está ouvindo…", thinking: "Sarah está pensando…",
    writing: "Sarah está respondendo…", speaking: "Sarah está falando…" };
  // Pontos do rosto medidos na imagem (550x768): centro da boca, linha entre os lábios, olhos.
  const W = 550, H = 768, MX = 275, LIP_Y = 533, EYES = [190, 360], EYE_Y = 344;
  const GLOW = { idle: [.12, .66, 1], speaking: [.12, .66, 1], listening: [.88, .27, .5], thinking: [.49, .36, 1], writing: [.23, .48, 1] };
  const MOOD = { idle: [.25, 0], listening: [.15, .35], thinking: [0, -.25], writing: [.1, 0], speaking: [.12, 0] }; // [sorriso, sobrancelha]
  const clamp = (v, a = 0, b = 1) => Math.min(b, Math.max(a, v));
  const smooth = (a, b, v) => { const t = clamp((v - a) / (b - a)); return t * t * (3 - 2 * t); };
  const lens = (x, half) => Math.max(0, 1 - ((x - MX) / half) ** 2);
  const lip = (x) => 530 + 7 * lens(x, 69);
  const gauss = (dx, dy, sx, sy) => Math.exp(-((dx / sx) ** 2 + (dy / sy) ** 2));

  // Pesos de cada ponto da malha para cada movimento (calculados uma vez).
  function build(points, lowerOf, isInner) {
    const n = points.length / 2, f = () => new Float32Array(n);
    const m = { n, B: Float32Array.from(points), pos: new Float32Array(n * 2),
      jaw: f(), lip: f(), mouth: f(), rel: f(), gL: f(), gR: f(), cheek: f(), eye: f(), closed: f(), gaze: f(), brow: f(), z: f() };
    m.uv = new Float32Array(n * 2);
    for (let i = 0; i < n; i++) {
      const x = m.B[2 * i], y = m.B[2 * i + 1], below = y - lip(x);
      m.uv[2 * i] = x / W; m.uv[2 * i + 1] = y / H;
      m.mouth[i] = gauss(x - MX, y - 535, 85, 32); m.rel[i] = (x - MX) / 69;
      const h = ((x - MX) / 205) ** 2 + ((y - 370) / 320) ** 2;
      m.z[i] = ((h < 1 ? Math.sqrt(1 - h) : 0) + .35 * gauss(x - MX, y - 440, 28, 60)) * (1 - smooth(600, 700, y));
      if (isInner) continue;
      if (lowerOf(i)) { // queixo e lábio de baixo: descem; a fenda fecha nos cantos e as bochechas esticam devagar
        const near = 1 - smooth(0, 28, below), inside = 1 - smooth(0, 12, Math.abs(x - MX) - 69);
        const chin = (1 - smooth(50, 140, Math.abs(x - MX))) * (1 - smooth(625, 700, y));
        m.jaw[i] = near * Math.pow(lens(x, 69), .85) * inside + (1 - near) * chin; // abertura oval, cantos finos
      } else m.lip[i] = lens(x, 72) * (1 - smooth(0, 22, -below));
      m.gL[i] = gauss(x - 206, y - 530, 18, 18); m.gR[i] = gauss(x - 344, y - 530, 18, 18);
      m.cheek[i] = gauss(x - 200, y - 470, 45, 40) + gauss(x - 350, y - 470, 45, 40);
      const ex = Math.abs(x - EYES[0]) < Math.abs(x - EYES[1]) ? EYES[0] : EYES[1];
      m.eye[i] = 1 - smooth(30, 52, Math.abs(x - ex));
      // olho fechado: a pele acima (312–330) desce e cobre o olho, que se comprime numa faixa de 2 px na pálpebra de baixo
      m.closed[i] = y < 312 ? y : y < 330 ? 312 + (y - 312) * 48 / 18 : y < 362 ? 360 + (y - 330) * 2 / 32 : y;
      const inEye = ((x - ex) / 40) ** 2 + ((y - EYE_Y) / 15) ** 2;
      m.gaze[i] = gauss(x - ex, y - EYE_Y, 16, 16) * (1 - smooth(.55, 1, inEye)); // a íris anda, a borda do olho fica
      m.brow[i] = gauss(0, y - 312, 1, 13) * (1 - smooth(40, 70, Math.abs(x - ex)));
    }
    return m;
  }
  function deform(m, k) {
    const cy = Math.cos(k.yaw), sy = Math.sin(k.yaw), cp = Math.cos(k.pitch), sp = Math.sin(k.pitch), blink = Math.max(k.blink, k.squint);
    for (let i = 0; i < m.n; i++) {
      const by = m.B[2 * i + 1];
      let x = m.B[2 * i], y = by;
      y += k.jaw * 16 * m.jaw[i] - k.jaw * 5 * m.lip[i];
      x += k.wide * 7 * m.mouth[i] * m.rel[i] + k.smile * 3 * (m.gR[i] - m.gL[i]);
      y -= k.smile * (5 * (m.gL[i] + m.gR[i]) + 2.5 * m.cheek[i]) + k.brow * 4 * m.brow[i];
      y += (m.closed[i] - by) * blink * m.eye[i];
      x += k.gx * 7 * m.gaze[i]; y += k.gy * 3.5 * m.gaze[i];
      m.pos[2 * i] = MX + (x - MX) * cy + m.z[i] * 110 * sy;
      m.pos[2 * i + 1] = 370 + (y - 370) * cp + m.z[i] * 80 * sp;
    }
  }

  // Malha do rosto: colunas alinhadas aos cantos da boca (206 e 344); linhas mais densas nos olhos e na boca.
  const cols = [0];
  for (let x = 2; x < W; x += 6) cols.push(x);
  cols.push(W);
  const rows = [];
  for (const [a, b, s] of [[0, 300, 6], [300, 372, 3], [372, 501, 6], [501, 571, 2], [571, H, 6]]) for (let y = a; y < b; y += s) rows.push(y);
  rows.push(H);
  const nC = cols.length, lipRow = rows.indexOf(LIP_Y), pts = [], lowerFlag = [];
  for (const y0 of rows) for (const x of cols) {
    pts.push(x, y0 + (lip(x) - LIP_Y) * Math.max(0, 1 - Math.abs(y0 - LIP_Y) / 30)); // a linha da boca segue a curva dos lábios
    lowerFlag.push(y0 > LIP_Y);
  }
  const dup = new Map(); // a fenda: pontos da linha da boca duplicados entre os cantos (um vai com o lábio de cima, outro com o de baixo)
  cols.forEach((x, c) => {
    if (x <= 206 || x >= 344) return;
    dup.set(c, pts.length / 2);
    pts.push(pts[2 * (lipRow * nC + c)], pts[2 * (lipRow * nC + c) + 1]);
    lowerFlag.push(true);
  });
  const faceIdx = [];
  for (let r = 0; r < rows.length - 1; r++) for (let c = 0; c < nC - 1; c++) {
    const top = (cc) => (r === lipRow && dup.has(cc) ? dup.get(cc) : r * nC + cc);
    const a = top(c), b = top(c + 1), d = (r + 1) * nC + c, e = d + 1;
    faceIdx.push(a, d, b, b, d, e);
  }
  const face = build(pts, (i) => lowerFlag[i], false);
  face.index = Uint32Array.from(faceIdx);
  // Interior da boca (desenhado atrás do rosto; só aparece pela fenda) e dois brilhos nos olhos.
  const innerPts = [], innerIdx = [];
  for (let r = 0; r < 5; r++) for (let c = 0; c < 9; c++) innerPts.push(196 + c * 20, 516 + r * 17);
  for (let r = 0; r < 4; r++) for (let c = 0; c < 8; c++) { const a = r * 9 + c; innerIdx.push(a, a + 9, a + 1, a + 1, a + 9, a + 10); }
  const inner = build(innerPts, () => false, true);
  inner.index = Uint16Array.from(innerIdx);
  const glow = { pos: new Float32Array(16), uv: Float32Array.from([0, 0, 1, 0, 0, 1, 1, 1, 0, 0, 1, 0, 0, 1, 1, 1]),
    index: Uint16Array.from([0, 2, 1, 1, 2, 3, 4, 6, 5, 5, 6, 7]) };
  function placeGlow(k) {
    EYES.forEach((ex, e) => {
      const x = ex + k.gx * 7, y = EYE_Y + k.gy * 3.5, z = .85;
      const cx = MX + (x - MX) * Math.cos(k.yaw) + z * 110 * Math.sin(k.yaw), cy = 370 + (y - 370) * Math.cos(k.pitch) + z * 80 * Math.sin(k.pitch);
      glow.pos.set([cx - 26, cy - 26, cx + 26, cy - 26, cx - 26, cy + 26, cx + 26, cy + 26], e * 8);
    });
  }

  const VS = `#version 300 es
in vec2 aPos; in vec2 aUv; out vec2 vUv; uniform vec2 uSize;
void main() { vUv = aUv; gl_Position = vec4(aPos.x / uSize.x * 2. - 1., 1. - aPos.y / uSize.y * 2., 0., 1.); }`;
  const FS = `#version 300 es
precision mediump float;
in vec2 vUv; out vec4 o;
uniform sampler2D uTex; uniform int uMode; uniform float uJaw, uGlowA; uniform vec3 uGlow;
void main() {
  if (uMode == 0) { o = texture(uTex, vUv); return; }
  if (uMode == 2) { vec2 q = vUv * 2. - 1.; float a = uGlowA * exp(-dot(q, q) * 3.); o = vec4(uGlow * a, 0.); return; }
  vec2 p = vUv * vec2(${W}., ${H}.);
  float u = (p.x - ${MX}.) / 72., v = (p.x - ${MX}.) / 69.;
  float top = 530. + 7. * max(0., 1. - v * v) - 5. * uJaw * max(0., 1. - u * u);
  float d = p.y - top;
  // interior azul-escuro (o rosto é de cristal, não preto), sombra logo abaixo do lábio e dentes suaves
  vec3 c = mix(vec3(.16, .32, .55), vec3(.05, .13, .27), clamp(d / 16., 0., 1.));
  float teeth = smoothstep(.3, 1.2, d) * (1. - smoothstep(3. * uJaw, 4.5 * uJaw + .8, d));
  c = mix(c, vec3(.72, .86, .97), teeth * .75);
  c *= .75 + .25 * smoothstep(0., 2.5, d);
  o = vec4(c, 1.);
}`;

  function renderer(canvas) {
    const gl = canvas.getContext("webgl2", { premultipliedAlpha: true, antialias: true });
    if (!gl) return null;
    const shader = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
    const prog = gl.createProgram();
    gl.attachShader(prog, shader(gl.VERTEX_SHADER, VS));
    gl.attachShader(prog, shader(gl.FRAGMENT_SHADER, FS));
    gl.bindAttribLocation(prog, 0, "aPos");
    gl.bindAttribLocation(prog, 1, "aUv");
    gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    const U = Object.fromEntries(["uSize", "uMode", "uJaw", "uGlow", "uGlowA", "uTex"].map((n) => [n, gl.getUniformLocation(prog, n)]));
    const upload = (m) => {
      const vao = gl.createVertexArray();
      gl.bindVertexArray(vao);
      const pb = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, pb);
      gl.bufferData(gl.ARRAY_BUFFER, m.uv.byteLength, gl.DYNAMIC_DRAW);
      gl.enableVertexAttribArray(0);
      gl.vertexAttribPointer(0, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ARRAY_BUFFER, m.uv, gl.STATIC_DRAW);
      gl.enableVertexAttribArray(1);
      gl.vertexAttribPointer(1, 2, gl.FLOAT, false, 0, 0);
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, gl.createBuffer());
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, m.index, gl.STATIC_DRAW);
      gl.bindVertexArray(null);
      return { vao, pb, m, count: m.index.length, type: m.index instanceof Uint32Array ? gl.UNSIGNED_INT : gl.UNSIGNED_SHORT };
    };
    const parts = [upload(inner), upload(face), upload(glow)];
    const tex = gl.createTexture();
    let ready = false;
    const img = new Image();
    img.onload = () => {
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
      gl.generateMipmap(gl.TEXTURE_2D);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR_MIPMAP_LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      ready = true;
    };
    img.src = "sarah.webp";
    return (k) => {
      if (!ready || !canvas.offsetParent) return; // não desenha o rosto escondido (ex.: o do login depois de entrar)
      const dpr = Math.min(devicePixelRatio || 1, 2), w = Math.round(canvas.clientWidth * dpr), h = Math.round(canvas.clientHeight * dpr);
      if (canvas.width !== w || canvas.height !== h) { canvas.width = w; canvas.height = h; }
      gl.viewport(0, 0, w, h);
      gl.clearColor(0, 0, 0, 0);
      gl.clear(gl.COLOR_BUFFER_BIT);
      gl.useProgram(prog);
      gl.uniform2f(U.uSize, W, H);
      gl.uniform1f(U.uJaw, k.jaw);
      gl.uniform3fv(U.uGlow, k.glowColor);
      gl.uniform1f(U.uGlowA, k.glowA);
      gl.activeTexture(gl.TEXTURE0);
      gl.bindTexture(gl.TEXTURE_2D, tex);
      gl.uniform1i(U.uTex, 0);
      gl.enable(gl.BLEND);
      parts.forEach((p, mode) => {
        gl.blendFunc(gl.ONE, mode === 2 ? gl.ONE : gl.ONE_MINUS_SRC_ALPHA); // brilho dos olhos soma luz
        gl.bindVertexArray(p.vao);
        gl.bindBuffer(gl.ARRAY_BUFFER, p.pb);
        gl.bufferSubData(gl.ARRAY_BUFFER, 0, p.m.pos);
        gl.uniform1i(U.uMode, [1, 0, 2][mode]);
        gl.drawElements(gl.TRIANGLES, p.count, p.type, 0);
      });
    };
  }

  const faces = [];
  document.querySelectorAll("[data-avatar]").forEach((host) => {
    const canvas = el("canvas", { className: "avatar" });
    canvas.setAttribute("role", "img");
    canvas.setAttribute("aria-label", "Rosto da Sarah");
    host.append(canvas);
    const draw = renderer(canvas);
    if (draw) faces.push({ canvas, draw });
    else canvas.replaceWith(el("img", { className: "avatar", src: "sarah.webp", alt: "Rosto da Sarah" }));
  });

  // ----- comportamento: o que faz o rosto parecer vivo -----
  const still = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const ph = [0, 1, 2, 3, 4].map(() => Math.random() * 6.28);
  const k = { jaw: 0, wide: 0, smile: .2, blink: 0, squint: 0, gx: 0, gy: 0, brow: 0, yaw: 0, pitch: 0, glowA: .25, glowColor: GLOW.idle };
  const goal = { gx: 0, gy: 0 }, pose = { rot: 0, x: 0, y: 0, s: 1 };
  let current = "idle", mic = 0, last = 0, nod = 0, emph = 0, tilt = 1, held = null;
  let blinkAt = performance.now() + 1500, blinkStart = -1, saccadeAt = 0;

  function update(now) {
    const t = now / 1000;
    let target = 0, bright = .5;
    if (current === "speaking" && tts.audio) {
      const env = tts.env, i = Math.floor(tts.audio.currentTime * 50);
      if (env) { target = Math.pow(env.level[i] ?? 0, .8); bright = env.bright[i] ?? .5; }
      else target = .35 + .35 * Math.sin(now / 70);
    }
    k.jaw += (target - k.jaw) * (target > k.jaw ? .55 : .3);            // a mandíbula abre rápido e fecha mais devagar
    k.wide += (clamp((bright - .35) * 2.2, -1, 1) * Math.min(1, k.jaw * 2) - k.wide) * .25; // "e/i/s" alargam, "o/u" arredondam
    if (target - last > .22 && target > .45 && nod < .3) { nod = 1; emph = 1; }          // sílaba forte: aceno e sobrancelha
    last = target;
    nod *= .9;
    emph *= .93;
    if (!still && now > saccadeAt) { // olhar: saltos rápidos; quase sempre volta para quem está na frente
      const away = current !== "listening" && Math.random() < (current === "speaking" ? .25 : .45);
      [goal.gx, goal.gy] = current === "thinking" ? [-.4 + Math.random() * .3, -.8]
        : away ? [(Math.random() - .5) * 1.4, (Math.random() - .5) * .9] : [(Math.random() - .5) * .15, (Math.random() - .5) * .1];
      saccadeAt = now + (current === "listening" ? 1800 : 600) + Math.random() * 2400;
    }
    k.gx += (goal.gx - k.gx) * .45;
    k.gy += (goal.gy - k.gy) * .45;
    const [smile, brow] = MOOD[current];
    k.smile += (smile - k.smile) * .05;
    k.brow += (brow + .7 * emph - k.brow) * .15;
    k.squint += ((current === "thinking" ? .3 : 0) - k.squint) * .08;
    if (!still && now > blinkAt && blinkStart < 0) blinkStart = now;
    if (blinkStart >= 0) { // fecha em 70 ms, abre em 100 ms; às vezes pisca duas vezes
      const d = now - blinkStart;
      k.blink = d < 70 ? d / 70 : d < 170 ? 1 - (d - 70) / 100 : 0;
      if (d >= 170) { blinkStart = -1; blinkAt = now + (Math.random() < .15 ? 120 : 1600 + Math.random() * 4800); }
    }
    if (!still) {
      const sway = current === "speaking" ? 1 : .6;
      k.yaw = sway * .06 * (Math.sin(t * .37 + ph[0]) + .5 * Math.sin(t * .9 + ph[1])) + k.gx * .04; // a cabeça segue um pouco o olhar
      k.pitch = sway * .04 * Math.sin(t * .5 + ph[2]) + .06 * nod + (current === "thinking" ? -.05 : current === "listening" ? .03 : 0);
      let rot = sway * (.5 * Math.sin(t * .55 + ph[3]) + .3 * Math.sin(t * 1.3 + ph[4])) + 1.2 * nod * (ph[0] > 3 ? 1 : -1), s = 1;
      if (current === "listening") { rot += 3 * tilt; s = 1.025; } // cabeça inclinada, atenta
      pose.rot += (rot - pose.rot) * .08;
      pose.x += (.4 * Math.sin(t * .4 + ph[2]) - pose.x) * .08;
      pose.y += (.3 * Math.sin(t * 1.6 + ph[3]) + .6 * nod - pose.y) * .12;
      pose.s += (s - pose.s) * .08;
    }
    k.glowA = (.22 + .5 * (current === "speaking" ? k.jaw : current === "listening" ? mic : 0)) * (1 - Math.max(k.blink, k.squint)); // olho fechado não brilha
    k.glowColor = GLOW[current];
    if (current === "speaking") document.body.style.setProperty("--lvl", k.jaw.toFixed(2));
    if (held) Object.assign(k, held);
  }
  function frame(now) {
    update(now);
    if (faces.length) {
      deform(face, k);
      deform(inner, k);
      placeGlow(k);
      const tf = `translate(${pose.x.toFixed(2)}%, ${pose.y.toFixed(2)}%) rotate(${pose.rot.toFixed(2)}deg) scale(${pose.s.toFixed(3)})`;
      for (const f of faces) { f.draw(k); f.canvas.style.transform = tf; }
    }
    requestAnimationFrame(frame);
  }
  requestAnimationFrame(frame);
  document.body.dataset.state = current;

  return {
    setState(s) {
      if (s === current) return;
      current = s;
      document.body.dataset.state = s;
      $("#avatar-caption").textContent = CAPTIONS[s];
      if (s !== "listening") { mic = 0; document.body.style.setProperty("--lvl", "0"); }
      if (s === "listening") tilt = Math.random() < .5 ? -1 : 1;
      if (s === "speaking" && Math.random() < .5) blinkAt = 0; // é comum piscar ao começar a falar
      saccadeAt = 0;
    },
    level(v) { mic = Math.min(v * 8, 1); document.body.style.setProperty("--lvl", mic.toFixed(2)); },
    hold(values) { held = values; }, // fixa movimentos (usado nos testes visuais)
  };
})();

// Som da fala a cada 20 ms, calculado do próprio áudio antes de tocar:
// level = volume (0 a 1) e bright = quanto o som é agudo (cruzamentos por zero), que separa "s/e/i" de "o/u".
let envCtx = null;
async function envelope(blob) {
  try {
    envCtx ||= new AudioContext();
    const buf = await envCtx.decodeAudioData(await blob.arrayBuffer());
    const data = buf.getChannelData(0), step = Math.max(1, Math.floor(buf.sampleRate / 50)), level = [], bright = [];
    for (let i = 0; i < data.length; i += step) {
      let sum = 0, cross = 0;
      const end = Math.min(i + step, data.length);
      for (let j = i; j < end; j++) {
        sum += data[j] * data[j];
        if (j > i && (data[j] >= 0) !== (data[j - 1] >= 0)) cross++;
      }
      level.push(Math.sqrt(sum / step));
      bright.push(Math.min(1, Math.max(0, (cross / (end - i) - 0.03) / 0.15)));
    }
    const peak = level.reduce((a, b) => Math.max(a, b), 1e-4);
    return { level: level.map((v) => Math.min(1, (v / peak) * 1.25)), bright };
  } catch { return null; }
}
