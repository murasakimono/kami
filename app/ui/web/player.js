// Kami oynatici (P1): HTML5 video/ses + yerel medya sunucusu (app/core/media_server.py).
// Goz = oynat/duraklat; Web Audio AnalyserNode ile gozun iki yaninda ekolayzir. Altyazi kendi katmanimizda cizilir
// (akis modunda ileri sarinca video zamani sifirdan baslar; <track> kayardi). P2'de kelime tiklama / DUAL bunun ustune.
"use strict";

const PL = {
  open: false, info: null, mode: "direct", offset: 0, audio: 0, failed: 0, dur: 0,
  ctx: null, src: null, an: null, bins: null, eye: null, big: null,
  cues: [], subIdx: -1, subShift: 0, hideT: 0, seeking: false, volume: 1,
};
const plL = (tr, en) => (state.lang !== "en" ? tr : en);
const fmtT = (s) => {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
};

function plBuild() {
  const el = document.createElement("div");
  el.id = "player"; el.hidden = true;
  el.innerHTML = `
    <video id="plVideo" playsinline preload="auto"></video>
    <div class="pl-audio" id="plAudio">
      <div class="pl-cover" id="plCover"></div>
      <canvas id="plBig" width="760" height="614"></canvas>
    </div>
    <div class="pl-subs" id="plSubs"></div>
    <div class="pl-spin" id="plSpin"></div>
    <div class="pl-top">
      <div class="pl-title"><b id="plTitle"></b><span id="plMode"></span></div>
      <button class="pl-x" id="plClose" title="${plL("Kapat (Esc)", "Close (Esc)")}">✕</button>
    </div>
    <div class="pl-deck">
      <div class="pl-seek" id="plSeek"><i class="pl-buf" id="plBuf"></i><i class="pl-fill" id="plFill"></i><i class="pl-knob" id="plKnob"></i><span class="pl-tip" id="plTip"></span></div>
      <div class="pl-row">
        <div class="pl-left"><span class="pl-time"><b id="plCur">0:00</b> / <span id="plDur">0:00</span></span>
          <button class="pl-b" data-pl="back" title="-10 sn">−10</button><button class="pl-b" data-pl="fwd" title="+10 sn">+10</button></div>
        <div class="pl-eqw"><div class="pl-eq l" id="plEqL">${"<i></i>".repeat(7)}</div><button class="pl-eye" id="plEye" title="${plL("Oynat / duraklat (Boşluk)", "Play / pause (Space)")}"><span class="pl-iris"><img src="eye/iris.webp" alt=""></span><svg class="pl-ico pl-ico-play" viewBox="0 0 24 24"><path d="M8 5l11 7-11 7z"/></svg><svg class="pl-ico pl-ico-pause" viewBox="0 0 24 24"><path d="M7 5h3.5v14H7zM13.5 5H17v14h-3.5z"/></svg></button><div class="pl-eq r" id="plEqR">${"<i></i>".repeat(7)}</div></div>
        <div class="pl-right">
          <select class="pl-sel" id="plSub" title="${plL("Altyazı (C)", "Subtitles (C)")}"></select>
          <select class="pl-sel" id="plAud" title="${plL("Ses izi", "Audio track")}"></select>
          <select class="pl-sel" id="plRate" title="${plL("Hız", "Speed")}">${[0.5, 0.75, 1, 1.25, 1.5, 2].map((r) => `<option value="${r}" ${r === 1 ? "selected" : ""}>${r}×</option>`).join("")}</select>
          <label class="pl-vol" title="${plL("Ses (↑ ↓, M)", "Volume (↑ ↓, M)")}"><button class="pl-b" data-pl="mute" id="plMute">◢</button><input type="range" id="plVol" min="0" max="1" step="0.02" value="1"></label>
          <button class="pl-b" data-pl="full" title="${plL("Tam ekran (F)", "Fullscreen (F)")}">⛶</button>
        </div>
      </div>
    </div>`;
  document.body.appendChild(el);
  const v = $("#plVideo");
  v.crossOrigin = "anonymous";   // Web Audio sesi okuyabilsin (sunucu CORS * verir)
  v.addEventListener("timeupdate", plTick);
  v.addEventListener("progress", plBufDraw);
  v.addEventListener("waiting", () => $("#plSpin").classList.add("on"));
  v.addEventListener("playing", () => { $("#plSpin").classList.remove("on"); plEyeState(); });
  v.addEventListener("pause", plEyeState);
  v.addEventListener("ended", plEyeState);
  v.addEventListener("loadedmetadata", () => {
    if (PL.mode === "direct" && isFinite(v.duration)) PL.dur = v.duration;
    $("#plDur").textContent = fmtT(PL.dur);
    if (PL.info.kind === "video" && PL.mode === "direct") setTimeout(() => { if (PL.open && !v.videoWidth) plFallback("novideo"); }, 1500);
  });
  v.addEventListener("error", () => plFallback("error"));
  v.addEventListener("click", plToggle);
  v.addEventListener("dblclick", plFull);
  $("#plEye").addEventListener("click", plToggle);
  $("#plClose").addEventListener("click", plClose);
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pl]"); if (!b) return;
    ({ back: () => plSeek(plNow() - 10), fwd: () => plSeek(plNow() + 10), mute: () => { v.muted = !v.muted; plVolUi(); }, full: plFull })[b.dataset.pl]?.();
  });
  $("#plVol").addEventListener("input", (e) => { v.volume = +e.target.value; v.muted = false; plVolUi(); });
  $("#plRate").addEventListener("change", (e) => { v.playbackRate = +e.target.value; });
  $("#plSub").addEventListener("change", (e) => plLoadSub(+e.target.value));
  $("#plAud").addEventListener("change", (e) => plAudio(+e.target.value));
  // seek cubugu: tikla / surukle, uzerinde zaman ipucu
  const seek = $("#plSeek");
  const at = (e) => { const r = seek.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (PL.dur || 0); };
  seek.addEventListener("pointerdown", (e) => { PL.seeking = true; seek.setPointerCapture(e.pointerId); plDrawPos(at(e)); });
  seek.addEventListener("pointermove", (e) => {
    const t = at(e), tip = $("#plTip"); tip.textContent = fmtT(t);
    tip.style.left = (e.clientX - seek.getBoundingClientRect().left) + "px";
    if (PL.seeking) plDrawPos(t);
  });
  seek.addEventListener("pointerup", (e) => { if (PL.seeking) { PL.seeking = false; plSeek(at(e)); } });
  el.addEventListener("mousemove", plWake);
  document.addEventListener("keydown", plKey, true);
  if (window.KamiEye) {
    PL.big = new KamiEye($("#plBig"), { assets: "eye/char/", eyeY: 0.38, mirrorFrame: true });
  }
}

// ---------- acma / kapama ----------
async function playerOpen(id) {
  if (!$("#player")) plBuild();
  let r;
  try { r = await api.player_open(id); } catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) { toast(plL("Oynatılamadı: ", "Can't play: ") + (r?.error || "?"), true); return; }
  plStart(r);
}
function plStart(r) {
  const el = $("#player"), v = $("#plVideo");
  Object.assign(PL, { open: true, info: r, mode: r.mode, offset: 0, audio: 0, failed: 0, dur: r.duration || 0, cues: [], subIdx: -1, subShift: 0 });
  el.hidden = false; el.classList.toggle("is-audio", r.kind === "audio");
  document.body.classList.add("pl-open");
  $("#plTitle").textContent = r.title;
  plModeUi();
  $("#plCover").style.backgroundImage = r.cover ? `url("${r.cover}")` : "";
  $("#plCover").hidden = !r.cover;
  $("#plSub").innerHTML = `<option value="-1">${plL("Altyazı yok", "No subtitles")}</option>` + r.subs.map((s, i) => `<option value="${i}">${escapeHtml(s.label)}</option>`).join("");
  $("#plSub").hidden = !r.subs.length;
  $("#plAud").innerHTML = r.audio.map((a, i) => `<option value="${i}">${escapeHtml([a.lang, a.title, a.codec].filter(Boolean).join(" · ") || plL("Ses ", "Audio ") + (i + 1))}</option>`).join("");
  $("#plAud").hidden = r.audio.length < 2;
  if (r.subs.length) { $("#plSub").value = "0"; plLoadSub(0); }
  plBlinkLoop();
  if (r.kind === "audio") PL.big?.ready.then(() => PL.big.start());
  plSetSrc(0);
  plWake();
}
function plClose() {
  const v = $("#plVideo");
  v.pause(); v.removeAttribute("src"); v.load();   // akis baglantisi kapanir -> sunucu ffmpeg'i oldurur
  PL.open = false;
  $("#player").hidden = true;
  document.body.classList.remove("pl-open");
  if (document.fullscreenElement) document.exitFullscreen();
  PL.big?.stop(); clearTimeout(PL.blinkT);
}

// ---------- kaynak / zaman ----------
function plUrl(t) {
  const r = PL.info;
  if (PL.mode === "direct") return r.direct_url;
  const q = new URLSearchParams({ t: t.toFixed(3), a: PL.audio, m: PL.mode });
  return `${r.stream_url}?${q}`;
}
function plSetSrc(t, autoplay = true) {
  const v = $("#plVideo");
  PL.offset = PL.mode === "direct" ? 0 : t;
  v.src = plUrl(t);
  if (PL.mode === "direct" && t) v.currentTime = t;
  $("#plSpin").classList.add("on");
  if (autoplay) v.play().then(plAudioGraph).catch(() => {});
}
const plNow = () => PL.offset + ($("#plVideo").currentTime || 0);
async function plSeek(t, play) {
  t = Math.max(0, Math.min(PL.dur ? PL.dur - 0.5 : t, t));
  const v = $("#plVideo");
  if (PL.mode === "direct") { v.currentTime = t; plTick(); return; }
  const paused = v.paused;
  if (PL.mode === "remux" && PL.info.kind === "video") {   // kopya akis anahtar kareden baslar: gercek baslangici sor
    try { t = (await (await fetch(`${PL.info.stream_url.replace("/x/", "/k/")}?t=${t}`)).json()).t; } catch { /* yaklasik */ }
  }
  plSetSrc(t, play ?? !paused);
  plDrawPos(t);
}
function plFallback(why) {
  if (!PL.open) return;
  if (PL.mode === "transcode" || PL.failed >= 2) {
    if (why === "error") toast(plL("Bu dosya oynatılamadı", "This file can't be played"), true);
    return;
  }
  PL.failed++;
  const t = plNow();
  PL.mode = PL.mode === "direct" ? "remux" : "transcode";
  console.info("oynatici geri dusus:", why, "->", PL.mode);
  plModeUi();
  plSeek(t, true);
}
function plAudio(i) {
  PL.audio = i;
  const t = plNow();
  if (PL.mode === "direct") PL.mode = "remux";   // dogrudan oynatmada iz secilemez -> ffmpeg secer
  plModeUi();
  plSeek(t);
}
function plModeUi() {
  const m = { direct: "", remux: plL("· ffmpeg ile açılıyor", "· via ffmpeg"), transcode: plL("· canlı dönüştürülüyor", "· live transcode") }[PL.mode];
  $("#plMode").textContent = m || "";
}

// ---------- cizim ----------
function plTick() {
  if (!PL.open) return;
  const t = plNow();
  $("#plCur").textContent = fmtT(t);
  if (!PL.seeking) plDrawPos(t);
  plSubDraw(t);
}
function plDrawPos(t) {
  const p = PL.dur ? Math.min(1, t / PL.dur) * 100 : 0;
  $("#plFill").style.width = p + "%"; $("#plKnob").style.left = p + "%";
  if (PL.seeking) $("#plCur").textContent = fmtT(t);
}
function plBufDraw() {
  const v = $("#plVideo"); if (!v.buffered.length || !PL.dur) return;
  const end = PL.offset + v.buffered.end(v.buffered.length - 1);
  $("#plBuf").style.width = Math.min(100, (end / PL.dur) * 100) + "%";
}
function plEyeState() {
  const v = $("#plVideo"), st = v.paused ? "paused" : "playing";
  PL.big?.set({ playbackState: st, isDownloading: false });
  $("#player").classList.toggle("paused", v.paused);
  plWake();
}
function plToggle() {
  const v = $("#plVideo");
  if (v.paused) v.play().then(plAudioGraph).catch(() => {}); else v.pause();
}
function plFull() {
  if (document.fullscreenElement) document.exitFullscreen(); else $("#player").requestFullscreen?.();
}
function plVolUi() {
  const v = $("#plVideo");
  $("#plVol").value = v.muted ? 0 : v.volume;
  $("#plMute").textContent = v.muted || v.volume === 0 ? "◁" : "◢";
}
function plWake() {
  const el = $("#player"); if (!el) return;
  el.classList.remove("idle");
  clearTimeout(PL.hideT);
  PL.hideT = setTimeout(() => { if (!$("#plVideo").paused && PL.info?.kind === "video") el.classList.add("idle"); }, 2600);
}

// ---------- yuvarlak goz: ara ara kirpar (duraklatinca yari kapali durur, CSS) ----------
function plBlinkLoop() {
  clearTimeout(PL.blinkT);
  PL.blinkT = setTimeout(() => {
    const e = $("#plEye");
    if (PL.open && e) { e.classList.add("blink"); setTimeout(() => e.classList.remove("blink"), 140); }
    if (PL.open) plBlinkLoop();
  }, 2600 + Math.random() * 3600);
}

// ---------- ekolayzir: AnalyserNode -> gozun iki yani ----------
function plAudioGraph() {
  if (PL.ctx) { if (PL.ctx.state === "suspended") PL.ctx.resume(); return; }
  try {
    PL.ctx = new (window.AudioContext || window.webkitAudioContext)();
    PL.src = PL.ctx.createMediaElementSource($("#plVideo"));
    PL.an = PL.ctx.createAnalyser(); PL.an.fftSize = 512; PL.an.smoothingTimeConstant = 0.78;
    PL.src.connect(PL.an); PL.an.connect(PL.ctx.destination);
    PL.bins = new Uint8Array(PL.an.frequencyBinCount);
    const N = 7, edges = [];   // logaritmik bantlar ~40 Hz .. 16 kHz
    for (let i = 0; i <= N; i++) edges.push(Math.round(Math.pow(PL.bins.length * 0.75, i / N)));
    const loop = () => {
      if (PL.open && !$("#plVideo").paused) {
        PL.an.getByteFrequencyData(PL.bins);
        const lv = [];
        for (let i = 0; i < N; i++) {
          let s = 0, n = 0;
          for (let k = Math.max(1, edges[i]); k <= Math.max(edges[i], edges[i + 1]); k++) { s += PL.bins[k]; n++; }
          lv.push(Math.pow((s / Math.max(1, n)) / 255, 1.4));
        }
        PL.big?.set({ levels: lv });   // kucuk gozde cubuklar DOM'da (altigenin iki yani)
        plEqDraw(lv);
        const bass = lv[0] * 0.6 + lv[1] * 0.4;
        $("#player").style.setProperty("--pl-beat", bass.toFixed(3));
      } else if (PL.big?.target.levels) { PL.big.set({ levels: null }); plEqDraw(null); }
      requestAnimationFrame(loop);
    };
    loop();
  } catch (e) { console.warn("Web Audio kurulamadi", e); }
}

function plEqDraw(lv) {
  const L = $$("#plEqL i"), R = $$("#plEqR i");
  for (let i = 0; i < 7; i++) {   // ic bantlar goze yakin: bas ortada, tiz disarida
    const h = lv ? 3 + lv[i] * 22 : 3;
    L[6 - i].style.height = R[i].style.height = h.toFixed(1) + "px";
  }
}

// ---------- altyazi: WebVTT ayristir, kendi katmanimizda ciz ----------
async function plLoadSub(i) {
  PL.subIdx = i; PL.cues = [];
  $("#plSubs").innerHTML = "";
  if (i < 0) return;
  try {
    const txt = await (await fetch(PL.info.subs[i].url)).text();
    PL.cues = plParseVtt(txt);
  } catch (e) { toast(plL("Altyazı yüklenemedi", "Subtitle failed to load"), true); }
}
function plParseVtt(txt) {
  const ts = (s) => { const p = s.trim().split(":").map(parseFloat); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; };
  const out = [];
  for (const block of txt.replace(/\r/g, "").split(/\n{2,}/)) {
    const lines = block.split("\n"); const k = lines.findIndex((l) => l.includes("-->"));
    if (k < 0) continue;
    const [a, b] = lines[k].split("-->");
    const text = lines.slice(k + 1).join("\n").trim();
    if (text) out.push({ s: ts(a), e: ts(b.trim().split(/\s+/)[0]), text });
  }
  return out;
}
function plSubDraw(t) {
  t -= PL.subShift;
  const box = $("#plSubs");
  const html = PL.cues.filter((c) => t >= c.s && t <= c.e)
    .map((c) => `<span>${escapeHtml(c.text.replace(/<[^>]+>/g, "")).replace(/\n/g, "<br>")}</span>`).join("<br>");
  if (box.dataset.h !== html) { box.innerHTML = html; box.dataset.h = html; }
}

// ---------- klavye ----------
function plKey(e) {
  if (!PL.open || e.target.matches("input[type=text], textarea")) return;
  const v = $("#plVideo"), k = e.key.toLowerCase();
  const map = {
    " ": plToggle, k: plToggle, f: plFull, m: () => { v.muted = !v.muted; plVolUi(); },
    arrowleft: () => plSeek(plNow() - 5), arrowright: () => plSeek(plNow() + 5),
    j: () => plSeek(plNow() - 10), l: () => plSeek(plNow() + 10),
    arrowup: () => { v.volume = Math.min(1, v.volume + 0.05); plVolUi(); }, arrowdown: () => { v.volume = Math.max(0, v.volume - 0.05); plVolUi(); },
    c: () => { const s = $("#plSub"); if (PL.info.subs.length) { s.value = PL.subIdx < 0 ? "0" : "-1"; plLoadSub(+s.value); } },
    escape: () => { if (!document.fullscreenElement) plClose(); },
  };
  if (map[k]) { e.preventDefault(); e.stopPropagation(); map[k](); plWake(); }
}
