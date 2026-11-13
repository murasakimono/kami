// Kami Oda arayuzu: giris, sesli konusma (RNNoise, bas-konus), ekran paylasimi, yayin izleme, sohbet.
"use strict";
const $ = (id) => document.getElementById(id);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const BASE = location.href.replace(/[?#].*$/, "").replace(/[^/]*$/, "");
const PREF = (() => { try { return JSON.parse(localStorage.kami_room || "{}"); } catch { return {}; } })();
const save = () => { try { localStorage.kami_room = JSON.stringify(PREF); } catch { /* gizli mod */ } };
const S = { core: null, ctx: null, mic: null, micRaw: null, micSid: "", muted: !!PREF.muted, deaf: false, ptt: PREF.mode === "ptt",
  pttDown: false, share: null, shareSid: "", tiles: new Map(), audios: new Map(), meters: new Map(), unread: 0, roster: [], host: "" };
const PAL = [["#6D28D9", "#C026D3"], ["#0FA37A", "#2EE6A6"], ["#B91C3C", "#F0506E"], ["#1D6FD9", "#4FA3F7"], ["#B7791F", "#E8B04A"], ["#4338CA", "#818CF8"]];
const color = (id) => PAL[[...id].reduce((a, c) => a + c.charCodeAt(0), 0) % PAL.length];
const PIP = { on: false, mixed: false, v: null, st: null, cv: null, ct: null, dest: null, nodes: new Map(), t1: 0, t2: 0 };
const outMuted = () => PIP.on && PIP.mixed;   // PiP acikken ses tek yerden (PiP videosu) calar
function toast(t) { const e = $("toast"); e.textContent = t; e.hidden = false; clearTimeout(e._t); e._t = setTimeout(() => (e.hidden = true), 3200); }

// ---------------------------------------------------------------- giris
async function listMics(sel) {
  try {
    const devs = (await navigator.mediaDevices.enumerateDevices()).filter((d) => d.kind === "audioinput");
    sel.innerHTML = `<option value="">Varsayılan mikrofon</option>` + devs.map((d) => `<option value="${esc(d.deviceId)}" ${d.deviceId === PREF.mic ? "selected" : ""}>${esc(d.label || "Mikrofon")}</option>`).join("");
  } catch { /* izin yok */ }
}
async function init() {
  try { const i = await (await fetch(BASE + "info", { cache: "no-store" })).json(); S.host = i.host; $("jnTxt").textContent = `${i.host} seni sesli odaya çağırıyor.`; }
  catch { $("jnTxt").textContent = "Oda kapanmış ya da bağlantı geçersiz."; $("jnGo").disabled = true; return; }
  $("jnName").value = PREF.name || "";
  listMics($("jnMic"));
  const kami = await kamiStatus();
  if (kami?.host) { $("jnName").value = kami.name || PREF.name || S.host; if (PREF.autojoin !== false) join(); }
}
$("jnGo").onclick = () => join();
$("jnName").addEventListener("keydown", (e) => e.key === "Enter" && join());

async function join() {
  const name = $("jnName").value.trim() || "Misafir";
  PREF.name = name; PREF.mic = $("jnMic").value || PREF.mic || ""; save();
  $("jnGo").disabled = true; $("jnErr").textContent = "";
  S.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive", sampleRate: 48000 });
  try { await S.ctx.resume(); } catch { /* sonra */ }
  try { await buildMic(); } catch (e) {
    $("jnErr").textContent = "Mikrofona izin verilmedi; yalnızca dinleyici olarak giriyorsun.";
  }
  S.core = new KamiRoom({ base: BASE, name, kind: "user", quality: PREF.q || "auto", on: {
    roster: onRoster, events: onEvents, track: onTrack, trackgone: onTrackGone, peergone: onPeerGone,
    peerstate: () => netDot(), msg: onAppMsg, bin: onBin, error: () => toast("Bağlantı koptu, yeniden deneniyor…"),
  } });
  if (S.mic) S.micSid = S.core.addLocal("mic", new MediaStream([S.mic]));
  await S.core.join();
  S.core.setMe({ muted: S.muted });
  $("join").hidden = true; $("room").hidden = false;
  if (PREF.chatOpen === false) $("room").classList.add("nochat");
  applyMicState(); setupSettings(); layout(); setInterval(statsLoop, 3000);
  if (!navigator.mediaDevices?.getDisplayMedia || /iPhone|iPad|Android/i.test(navigator.userAgent)) $("bShare").hidden = true;
  const pv = $("pipV");
  if (!(document.pictureInPictureEnabled || pv.webkitSupportsPresentationMode)) $("bPip").hidden = true;
  kamiInvite();
}

// ---------------------------------------------------------------- mikrofon hatti
async function buildMic() {
  const ns = PREF.ns || "rnnoise";
  const raw = await navigator.mediaDevices.getUserMedia({ audio: {
    deviceId: PREF.mic ? { exact: PREF.mic } : undefined, echoCancellation: true, noiseSuppression: ns === "browser",
    autoGainControl: true, channelCount: 1, sampleRate: 48000 } });
  S.micRaw?.getTracks().forEach((t) => t.stop());
  S.micRaw = raw;
  try { await S.ctx.resume(); } catch { /* tiklama bekliyor */ }
  if (S.ctx.state !== "running") {   // ses islemcisi askida: ham izle konus, ilk tiklamada guclu hatta gec
    const t = raw.getAudioTracks()[0];
    if (S.mic && S.core && S.micSid) S.core.replaceTrack(S.micSid, S.mic, t);
    S.mic = t; S.micAn = null; S.needCtx = true;
    applyMicState();
    return;
  }
  S.needCtx = false;
  const src = S.ctx.createMediaStreamSource(raw);
  let node = src;
  if (ns === "rnnoise" && S.ctx.audioWorklet) {
    try {
      const m = await import(BASE + "s/ns.js");
      S.rnWasm ||= await m.loadRnnoise({ url: BASE + "s/rnnoise.wasm", simdUrl: BASE + "s/rnnoise_simd.wasm" });
      if (!S.rnLoaded) { await S.ctx.audioWorklet.addModule(BASE + "s/rnnoise-worklet.js"); S.rnLoaded = true; }
      const rn = new m.RnnoiseWorkletNode(S.ctx, { wasmBinary: S.rnWasm, maxChannels: 1 });
      node.connect(rn); node = rn;
    } catch (e) { console.warn("RNNoise", e); toast("Güçlü gürültü engelleme açılamadı; tarayıcınınki kullanılıyor."); }
  }
  const an = S.ctx.createAnalyser(); an.fftSize = 512; node.connect(an);
  const dest = S.ctx.createMediaStreamDestination(); node.connect(dest);
  const track = dest.stream.getAudioTracks()[0];
  if (S.mic && S.core && S.micSid) S.core.replaceTrack(S.micSid, S.mic, track);
  S.mic = track; S.micAn = an;
  applyMicState();
}
function micOpen() { return !S.muted && !S.deaf && (!S.ptt || S.pttDown); }
function applyMicState() {
  if (S.mic) S.mic.enabled = micOpen();
  $("bMic")?.classList.toggle("x", S.muted || S.deaf);
  $("bMic")?.classList.toggle("ptt-on", S.ptt && S.pttDown && !S.muted);
  $("bDeaf")?.classList.toggle("x", S.deaf);
  for (const a of S.audios.values()) a.muted = S.deaf || outMuted();
  for (const t of S.tiles.values()) if (t.pid !== "me") t.video.muted = S.deaf || t.userMuted || outMuted();
  if (PIP.v) PIP.v.muted = S.deaf || !PIP.mixed;
  syncFsCtl();
}
function setMuted(v) { S.muted = v; PREF.muted = v; save(); applyMicState(); S.core?.setMe({ muted: v }); }
function setDeaf(v) { S.deaf = v; applyMicState(); S.core?.setMe({ deaf: v }); }
$("bMic").onclick = () => setMuted(!S.muted);
$("bDeaf").onclick = () => setDeaf(!S.deaf);
$("bLeave").onclick = async () => { await S.core?.leave(); stopShare(); stopCam(); document.body.innerHTML = `<div class="jn"><div class="jn-box"><div class="jn-sigil"><i></i><i></i><i></i><b>KAMI</b></div><p>Odadan ayrıldın.</p><button onclick="location.reload()">Tekrar gir</button></div></div>`; };

// bas-konus / kisayollar (sayfa odaktayken; Kami penceresinde genel kisayol Python'dan gelir)
function pttKey(down) { if (!S.ptt) return; S.pttDown = down; applyMicState(); }
window.kamiKey = (act, down) => {
  if (act === "ptt") pttKey(!!down);
  else if (act === "mute") setMuted(!S.muted);
  else if (act === "deaf") setDeaf(!S.deaf);
};
document.addEventListener("keydown", (e) => {
  if (S.capture) { e.preventDefault(); PREF.pttKey = e.code; save(); S.capture = false; $("sPtt").textContent = e.code; return; }
  if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
  if (e.ctrlKey && e.shiftKey && e.code === "KeyM") { e.preventDefault(); setMuted(!S.muted); }
  else if (e.ctrlKey && e.shiftKey && e.code === "KeyD") { e.preventDefault(); setDeaf(!S.deaf); }
  else if (S.ptt && e.code === (PREF.pttKey || "KeyV") && !e.repeat) pttKey(true);
});
document.addEventListener("keyup", (e) => { if (S.ptt && e.code === (PREF.pttKey || "KeyV")) pttKey(false); });
window.addEventListener("blur", () => { if (S.ptt && S.pttDown && !window.pywebview) pttKey(false); });

// ---------------------------------------------------------------- ekran paylasimi
$("bShare").onclick = async () => {
  if (S.share) { stopShare(); return; }
  try {
    const st = await navigator.mediaDevices.getDisplayMedia({ video: { frameRate: { ideal: 60, max: 60 }, width: { ideal: 1920 }, height: { ideal: 1080 } },
      // restrictOwnAudio: sistem sesinden Kami Oda'nin kendi caldigi sesi (karsi tarafin konusmasi) cikarir; yoksa
      // tam ekran + "sistem sesini paylas" secilince konusan kendi sesini geri duyar (Discord bunu kendi yapiyor)
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false, restrictOwnAudio: true },
      systemAudio: "include", selfBrowserSurface: "exclude", surfaceSwitching: "include" });
    S.share = st;
    const sa = st.getAudioTracks()[0];
    if (sa && !sa.getSettings().restrictOwnAudio) {
      try { await sa.applyConstraints({ restrictOwnAudio: true }); } catch { }
      if (!sa.getSettings().restrictOwnAudio)
        toast("Sistem sesi paylaşılıyor, ama bu sürüm odadaki sesleri ayıklayamıyor: yankı olursa kulaklık tak veya “Sistem sesini paylaş”ı kapat.");
    }
    st.getVideoTracks()[0].addEventListener("ended", stopShare);
    S.shareSid = S.core.addLocal("screen", st);
    S.core.setMe({ sharing: "screen" });
    $("bShare").classList.add("act");
    addTile("me", st, "screen", true);
  } catch (e) { if (e.name !== "NotAllowedError") toast("Ekran paylaşılamadı: " + e.message); }
};
function stopShare() {
  if (!S.share) return;
  S.share.getTracks().forEach((t) => t.stop());
  S.core?.removeLocal(S.shareSid); S.core?.setMe({ sharing: "" });
  removeTile("me:" + S.share.id); S.share = null; $("bShare").classList.remove("act");
}

// ---------------------------------------------------------------- kamera
$("bCam").onclick = async () => {
  if (S.cam) { stopCam(); return; }
  try {
    const st = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 }, facingMode: "user" } });
    S.cam = st; S.camSid = S.core.addLocal("cam", st);
    $("bCam").classList.add("act");
    addTile("me", st, "cam", true);
  } catch (e) { toast("Kamera açılamadı: " + (e.message || e.name)); }
};
function stopCam() {
  if (!S.cam) return;
  S.cam.getTracks().forEach((t) => t.stop());
  S.core?.removeLocal(S.camSid); removeTile("me:" + S.cam.id); S.cam = null; $("bCam").classList.remove("act");
}

// ---------------------------------------------------------------- uzak izler
function onTrack(pid, stream, kind, track) {
  if (kind === "mic" || (track.kind === "audio" && !stream.getVideoTracks().length && kind !== "player" && kind !== "screen")) {
    let a = S.audios.get(pid + ":" + stream.id);
    if (!a) {
      a = new Audio(); a.autoplay = true; a.playsInline = true; a.srcObject = stream; a.muted = S.deaf || outMuted();
      a.volume = (PREF.vol?.[nameOf(pid)] ?? 1);
      S.audios.set(pid + ":" + stream.id, a);
      a.play().catch(() => toast("Sesi duymak için ekrana bir kez dokun."));
      meterFor(pid, stream);
    }
    return;
  }
  if (track.kind === "video" || stream.getVideoTracks().length) addTile(pid, stream, kind, false);
}
function onTrackGone(pid, stream) { removeTile(pid + ":" + stream.id); }
function onPeerGone(pid) {
  for (const k of [...S.tiles.keys()]) if (k.startsWith(pid + ":")) removeTile(k);
  for (const [k, a] of [...S.audios]) if (k.startsWith(pid + ":")) { a.srcObject = null; S.audios.delete(k); }
  S.meters.delete(pid);
  dropRx(pid);
}
// iPhone: Safari arka plana gecince iOS mikrofonu keser (PiP'de dinleme surer). Odadakiler bunu gorsun;
// geri gelince mikrofon kendiliginden toparlansin.
const IOS = /iPhone|iPad/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
document.addEventListener("visibilitychange", () => {
  if (!S.core) return;
  if (IOS) S.core.setMe({ bg: document.hidden });
  if (!document.hidden) setTimeout(micRecover, 400);
});
async function micRecover() {
  const t = S.micRaw?.getAudioTracks()[0];
  if (!S.micRaw || !t || t.readyState === "live" && !t.muted) return;
  try { await S.ctx?.resume(); } catch { /* dokunus bekliyor */ }
  try { await buildMic(); toast("Mikrofon yeniden açıldı."); } catch { toast("Mikrofon açılamadı; ekrana bir kez dokun."); }
}
document.addEventListener("click", async () => {
  for (const a of S.audios.values()) if (a.paused) a.play().catch(() => {});
  try { await S.ctx?.resume?.(); } catch { /* yok */ }
  if (S.needCtx && S.ctx?.state === "running") { S.needCtx = false; buildMic().catch(() => {}); }
}, { capture: true });

function nameOf(pid) { return pid === "me" ? (PREF.name || "Ben") : (S.roster.find((p) => p.id === pid)?.name || "?"); }
function addTile(pid, stream, kind, mine) {
  const key = pid + ":" + stream.id;
  if (S.tiles.has(key)) return;
  const el = document.createElement("div");
  el.className = "vt"; el.dataset.key = key;
  const who = nameOf(pid), lbl = kind === "player" ? "Oynatıcı" : kind === "cam" ? "Kamera" : "Ekran";
  el.innerHTML = `<video autoplay playsinline ${mine ? "muted" : ""}></video>
    <div class="vt-bar">${kind === "cam" ? "" : `<span class="live">CANLI</span>`}<b>${esc(who.includes(lbl) ? who : who + " · " + lbl)}</b><span class="info"></span><span class="sp"></span>
      ${mine ? "" : `<select class="q" title="Kalite"><option value="auto">Otomatik</option><option value="src">Kaynak</option><option value="1080">1080p60</option><option value="1080_30">1080p30</option><option value="720">720p30</option><option value="480">480p30</option></select>
      <input type="range" class="vol" min="0" max="1" step="0.05" value="1" title="Ses">`}
      ${kind === "screen" ? `<button class="pen" title="Ekranın üstüne çiz / göster"><svg viewBox="0 0 24 24"><path d="M4 20l4-1 11-11-3-3L5 16zM14 6l3 3"/></svg></button>` : ""}
      <button class="fs" title="Tam ekran"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button></div>`;
  const v = el.querySelector("video");
  v.srcObject = stream;
  const T = { el, video: v, pid, kind, userMuted: false, q: PREF.q || "auto", pst: null,
    owner: mine ? S.core.id : pid, sid: stream.id, strokes: new Map(), lasers: new Map(), tool: "" };
  if (kind === "screen") setupDraw(T);
  v.muted = mine || S.deaf;
  v.play().catch(() => { const b = document.createElement("div"); b.className = "tapplay"; b.textContent = "▶ Yayını aç"; b.onclick = () => { v.play(); b.remove(); }; el.appendChild(b); });
  if (!mine) {
    const q = el.querySelector(".q"); q.value = T.q;
    q.onchange = () => { T.q = q.value; PREF.q = q.value; save(); if (q.value !== "auto") S.core.requestQuality(q.value, pid); else { T.autoQ = "src"; S.core.requestQuality("src", pid); } };
    if (T.q !== "auto") S.core.requestQuality(T.q, pid);
    el.querySelector(".vol").oninput = (e) => { v.volume = +e.target.value; T.userMuted = +e.target.value === 0; v.muted = S.deaf || T.userMuted || outMuted(); };
  }
  el.insertAdjacentHTML("beforeend", `<div class="vt-ctl"><button data-c="mic" title="Mikrofon">${$("bMic").innerHTML}</button><button data-c="deaf" title="Kulaklık">${$("bDeaf").innerHTML}</button><button data-c="exit" title="Tam ekrandan çık"><svg viewBox="0 0 24 24"><path d="M9 4v5H4M15 4v5h5M9 20v-5H4M15 20v-5h5"/></svg></button></div>`);
  el.querySelector(".vt-ctl").onclick = (e) => {
    e.stopPropagation(); const c = e.target.closest("[data-c]")?.dataset.c;
    if (c === "mic") setMuted(!S.muted); else if (c === "deaf") setDeaf(!S.deaf); else if (c === "exit") exitFs(el);
    syncFsCtl();
  };
  el.querySelector(".fs").onclick = (e) => { e.stopPropagation(); isFs(el) ? exitFs(el) : enterFs(el); };
  if (kind === "player" && !mine) {   // izleyen de oynat/durdur, sar, altyazi secebilsin
    el.insertAdjacentHTML("beforeend", `<div class="vt-sub"></div><div class="vt-pl">
      <button data-p="back" title="10 sn geri">−10</button><button data-p="toggle" class="pp" title="Oynat / durdur">❚❚</button><button data-p="fwd" title="10 sn ileri">+10</button>
      <span class="t">0:00</span><div class="bar"><i></i><b></b></div><span class="d">0:00</span>
      <select class="sub" title="Altyazı"><option value="-1">Altyazı yok</option></select></div>`);
    const pl = el.querySelector(".vt-pl");
    pl.onclick = (e) => {
      e.stopPropagation();
      const b = e.target.closest("[data-p]"), bar = e.target.closest(".bar");
      if (b) S.core.send(pid, { k: "plc", act: b.dataset.p === "toggle" ? "toggle" : "skip", v: b.dataset.p === "back" ? -10 : 10 });
      else if (bar && T.pst?.dur) { const r = bar.getBoundingClientRect(); S.core.send(pid, { k: "plc", act: "seek", v: (e.clientX - r.left) / r.width * T.pst.dur }); }
    };
    pl.querySelector(".sub").onchange = (e) => S.core.send(pid, { k: "plc", act: "sub", v: +e.target.value });
  }
  const pubName = nameOf(pid);
  if (!mine && kind === "player" && PREF.name && pubName.startsWith(PREF.name + " ·") && window.pywebview) {
    T.userMuted = true; v.muted = true;   // kendi oynatici yayinin: Player'dan zaten duyuyorsun (cift ses olmasin)
    const vol = el.querySelector(".vol"); if (vol) vol.value = 0;
  }
  if (mine && kind === "cam") v.style.transform = "scaleX(-1)";
  let idleT; const wake = () => { el.classList.remove("idle"); clearTimeout(idleT); idleT = setTimeout(() => isFs(el) && el.classList.add("idle"), 3000); };
  el.addEventListener("pointermove", wake); el.addEventListener("pointerdown", wake);
  el.addEventListener("click", () => { el.classList.add("tap"); setTimeout(() => el.classList.remove("tap"), 2500); if (S.tiles.size > 1) { const f = el.classList.toggle("focus"); $("videos").classList.toggle("focused", f); document.querySelectorAll(".vt").forEach((x) => x !== el && x.classList.remove("focus")); } });
  $("videos").appendChild(el);
  S.tiles.set(key, T);
  if (kind === "player" && !mine) toast(`${who} oynatıcıdan yayın başlattı`);
  layout();
}
function isFs(el) { return document.fullscreenElement === el || document.webkitFullscreenElement === el || el.classList.contains("pfs"); }
function enterFs(el) {
  const req = el.requestFullscreen || el.webkitRequestFullscreen;
  if (req) { Promise.resolve(req.call(el)).catch(() => el.classList.add("pfs")); }
  else el.classList.add("pfs");   // iPhone: ogeyi tam ekran yap (PWA'da tarayici cubugu yok)
  try { screen.orientation?.lock?.("landscape").catch(() => {}); } catch { /* yok */ }
  syncFsCtl();
}
function exitFs(el) {
  if (el.classList.contains("pfs")) el.classList.remove("pfs");
  else (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
  try { screen.orientation?.unlock?.(); } catch { /* yok */ }
}
function syncFsCtl() {
  document.querySelectorAll(".vt-ctl").forEach((c) => {
    c.querySelector('[data-c="mic"]').classList.toggle("x", S.muted || S.deaf);
    c.querySelector('[data-c="deaf"]').classList.toggle("x", S.deaf);
  });
}
const fmtT = (t) => { t = Math.max(0, Math.floor(t || 0)); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), x = t % 60; return (h ? h + ":" + String(m).padStart(2, "0") : m) + ":" + String(x).padStart(2, "0"); };
function onAppMsg(from, m) {
  if (m?.k === "draw") return drawIn(from, m);
  if (m?.k === "file") return fileIn(from, m);
  if (m?.k !== "pl") return;
  for (const T of S.tiles.values()) {
    if (T.pid !== from || T.kind !== "player") continue;
    const st = m.st; T.pst = { ...st, at: Date.now() };
    const el = T.el;
    el.querySelector(".vt-pl .pp").textContent = st.paused ? "▶" : "❚❚";
    el.querySelector(".vt-pl .d").textContent = fmtT(st.dur);
    el.querySelector(".vt-sub").innerHTML = st.line ? `<span>${esc(st.line).replace(/\n/g, "<br>")}</span>` : "";
    const sel = el.querySelector(".vt-pl .sub");
    const opts = `<option value="-1">Altyazı yok</option>` + st.subs.map((l, i) => `<option value="${i}">${esc(l)}</option>`).join("");
    if (sel.dataset.o !== opts) { sel.innerHTML = opts; sel.dataset.o = opts; }
    sel.value = String(st.sub);
  }
}
setInterval(() => {   // oynatici zamanini aradaki surede tahmin et
  for (const T of S.tiles.values()) {
    if (!T.pst) continue;
    const t = T.pst.t + (T.pst.paused ? 0 : (Date.now() - T.pst.at) / 1000);
    T.el.querySelector(".vt-pl .t").textContent = fmtT(t);
    T.el.querySelector(".vt-pl .bar b").style.width = (T.pst.dur ? Math.min(100, t / T.pst.dur * 100) : 0) + "%";
  }
}, 500);
function removeTile(key) {
  const T = S.tiles.get(key); if (!T) return;
  T.video.srcObject = null; T.el.remove(); S.tiles.delete(key); T.dead = true;
  if (!document.querySelector(".vt.focus")) $("videos").classList.remove("focused");
  layout();
}

// ---------------------------------------------------------------- katilimcilar
function onRoster(list) {
  S.roster = list;
  const users = list.filter((p) => p.kind === "user");
  $("rmCount").textContent = `${users.length} kişi` + (list.some((p) => p.kind === "stream") ? " · yayın açık" : "");
  const box = $("circle");
  const seen = new Set();
  for (const p of users) {
    seen.add(p.id);
    let el = box.querySelector(`[data-id="${p.id}"]`);
    const me = p.id === S.core.id;
    if (!el) {
      const [c1, c2] = color(p.id);
      el = document.createElement("div"); el.className = "tk"; el.dataset.id = p.id;
      el.style.setProperty("--c1", c1); el.style.setProperty("--c2", c2);
      el.innerHTML = `<div class="tk-face"></div><b></b><small></small>` + (me ? "" : `<input type="range" min="0" max="1.5" step="0.05" title="Ses seviyesi">`);
      box.appendChild(el);
      const r = el.querySelector("input");
      if (r) { r.value = PREF.vol?.[p.name] ?? 1; r.oninput = () => { PREF.vol ||= {}; PREF.vol[p.name] = +r.value; save(); for (const [k, a] of S.audios) if (k.startsWith(p.id + ":")) a.volume = Math.min(1, +r.value); }; }
    }
    el.querySelector(".tk-face").textContent = (p.name || "?").trim().charAt(0).toUpperCase();
    el.querySelector("b").textContent = p.name + (me ? " (sen)" : "");
    el.querySelector("small").innerHTML = (p.muted ? `<svg viewBox="0 0 24 24"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6M3 3l18 18"/></svg>` : "") +
      (p.deaf ? `<svg viewBox="0 0 24 24"><path d="M4 14v-2a8 8 0 0 1 16 0v2M3 3l18 18"/></svg>` : "") + (p.sharing ? "ekran paylaşıyor" : "") +
      (p.bg ? `<span class="bg">arka planda · mikrofonu kapalı</span>` : "");
  }
  box.querySelectorAll(".tk").forEach((el) => { if (!seen.has(el.dataset.id)) el.remove(); });
  layout();
}
function layout() {
  const st = $("stage"), vids = S.tiles.size;
  st.classList.toggle("hasvid", vids > 0);
  $("videos").style.setProperty("--cols", vids <= 1 ? 1 : vids <= 4 ? 2 : 3);
  if (vids) return;
  const tks = [...$("circle").querySelectorAll(".tk")], n = tks.length;
  const W = st.clientWidth, H = st.clientHeight, R = Math.min(W, H) * (n <= 1 ? 0 : 0.3);
  tks.forEach((el, i) => {
    const a = -Math.PI / 2 + (i / Math.max(1, n)) * Math.PI * 2;
    el.style.left = W / 2 + Math.cos(a) * R + "px"; el.style.top = H / 2 + Math.sin(a) * R + "px";
  });
}
window.addEventListener("resize", layout);

// konusma halkasi: ses seviyesi olcer
function meterFor(pid, stream) {
  try { const src = S.ctx.createMediaStreamSource(stream), an = S.ctx.createAnalyser(); an.fftSize = 512; src.connect(an); S.meters.set(pid, an); } catch { /* yok */ }
}
const buf = new Uint8Array(512);
function level(an) { an.getByteTimeDomainData(buf); let m = 0; for (const v of buf) m = Math.max(m, Math.abs(v - 128)); return m / 128; }
function talkLoop() {
  if (S.core) {
    const lv = S.micAn ? level(S.micAn) : 0;
    if (!$("set").hidden) $("sMeter").style.width = Math.min(100, lv * 220) + "%";
    const meEl = document.querySelector(`.tk[data-id="${S.core.id}"]`);
    meEl?.classList.toggle("talk", micOpen() && lv > 0.06);
    for (const [pid, an] of S.meters) document.querySelector(`.tk[data-id="${pid}"]`)?.classList.toggle("talk", level(an) > 0.05);
  }
  requestAnimationFrame(talkLoop);
}
requestAnimationFrame(talkLoop);

// baglanti kalitesi + otomatik yayin kalitesi
async function statsLoop() {
  let worst = "ok";
  for (const [key, T] of S.tiles) {
    if (T.pid === "me") continue;
    const s = await S.core.stats(T.pid); if (!s) continue;
    const info = T.el.querySelector(".info");
    if (info) info.textContent = `${s.h ? s.h + "p" : ""}${s.fps ? " " + s.fps + "fps" : ""} · ${s.rtt}ms${s.relay ? " · röle" : ""}`;
    if (T.q === "auto") {   // kayip artarsa bir kademe dus, uzun sure temizse cik
      const lost = s.loss - (T.lastLoss ?? s.loss); T.lastLoss = s.loss;
      const order = ["src", "1080", "1080_30", "720", "480"], i = order.indexOf(T.autoQ || "src");
      if ((lost > 40 || (s.fps && s.fps < 18)) && i < order.length - 1) { T.autoQ = order[i + 1]; T.clean = 0; S.core.requestQuality(T.autoQ, T.pid); toast(`Bağlantı zayıf: yayın ${T.autoQ.replace("_", "p ").replace(/^(\d+)$/, "$1p")} kaliteye indi`); }
      else if (lost < 3) { T.clean = (T.clean || 0) + 1; if (T.clean > 10 && i > 0) { T.autoQ = order[i - 1]; T.clean = 0; S.core.requestQuality(T.autoQ, T.pid); } }
    }
    if (s.rtt > 250) worst = "bad"; else if (s.rtt > 120 && worst === "ok") worst = "mid";
  }
  netDot(worst);
}
function netDot(w) {
  const pcs = [...(S.core?.peers.values() || [])], bad = pcs.some((P) => ["failed", "disconnected"].includes(P.pc.connectionState));
  $("rmNet").className = "rm-net " + (bad ? "bad" : w || "ok");
}

// ---------------------------------------------------------------- sohbet
function onEvents(evs) {
  const box = $("msgs");
  for (const e of evs) {
    const el = document.createElement("div");
    const me = e.who === PREF.name && e.kind !== "sys";
    el.className = "msg" + (e.kind === "sys" ? " sys" : "") + (me ? " me" : "");
    const t = new Date(e.t * 1000);
    el.innerHTML = `<b>${esc(e.who)}</b>${esc(e.text)}<time>${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}</time>`;
    box.appendChild(el);
    if ($("room").classList.contains("nochat") && e.kind !== "sys" && !me) { $("rmUnread").hidden = false; toast(`${e.who}: ${e.text}`); }
  }
  box.scrollTop = box.scrollHeight;
}
$("fileIn").onchange = (e) => { [...e.target.files].forEach(sendFile); e.target.value = ""; };
$("msg").addEventListener("paste", (e) => { const fs = [...(e.clipboardData?.files || [])]; if (fs.length) { e.preventDefault(); fs.forEach(sendFile); } });
document.addEventListener("paste", (e) => { if (e.target.closest?.("input,textarea") || !S.core) return; const fs = [...(e.clipboardData?.files || [])]; if (fs.length) { e.preventDefault(); fs.forEach(sendFile); } });
$("chat").addEventListener("dragover", (e) => { if (e.dataTransfer?.types?.includes("Files")) { e.preventDefault(); $("chat").classList.add("drop"); } });
$("chat").addEventListener("dragleave", () => $("chat").classList.remove("drop"));
$("chat").addEventListener("drop", (e) => { e.preventDefault(); $("chat").classList.remove("drop"); [...(e.dataTransfer?.files || [])].forEach(sendFile); });
$("send").onsubmit = (e) => { e.preventDefault(); const t = $("msg").value.trim(); if (t) { S.core.chat(t); $("msg").value = ""; } };
$("rmChatBtn").onclick = () => { const c = $("room").classList.toggle("nochat"); PREF.chatOpen = !c; save(); $("rmUnread").hidden = true; setTimeout(layout, 50); };

// ---------------------------------------------------------------- ayarlar
function setupSettings() {
  $("bSet").onclick = (e) => { e.stopPropagation(); $("set").hidden = !$("set").hidden; if (!$("set").hidden) listMics($("sMic")); };
  document.addEventListener("click", (e) => { if (!e.target.closest("#set") && !e.target.closest("#bSet")) $("set").hidden = true; });
  $("sNs").value = PREF.ns || "rnnoise";
  $("sMode").value = S.ptt ? "ptt" : "vad";
  $("sPtt").textContent = PREF.pttKey || "KeyV";
  $("sPttRow").hidden = !S.ptt;
  $("sQ").value = PREF.q || "auto";
  $("sMic").onchange = async (e) => { PREF.mic = e.target.value; save(); try { await buildMic(); } catch { toast("Mikrofon açılamadı"); } };
  $("sNs").onchange = async (e) => { PREF.ns = e.target.value; save(); try { await buildMic(); } catch { toast("Mikrofon açılamadı"); } };
  $("sMode").onchange = (e) => { S.ptt = e.target.value === "ptt"; PREF.mode = e.target.value; save(); $("sPttRow").hidden = !S.ptt; applyMicState(); };
  $("sPtt").onclick = () => { S.capture = true; $("sPtt").textContent = "Bir tuşa bas…"; };
  $("sQ").onchange = (e) => { PREF.q = e.target.value; save(); for (const T of S.tiles.values()) if (T.pid !== "me") { const q = T.el.querySelector(".q"); if (q) { q.value = e.target.value; q.onchange(); } } };
}

// ---------------------------------------------------------------- Kami penceresi (ev sahibi)
async function kamiStatus() {
  const api = window.pywebview?.api;
  if (!api?.room_status) return null;
  try { const s = await api.room_status(); return { ...s, host: s.on && s.local && BASE.startsWith(s.local) }; } catch { return null; }
}
async function kamiInvite() {
  const s = await kamiStatus(); if (!s?.host) return;
  $("rmInvite").hidden = false;
  const tick = async () => {
    const st = await kamiStatus(); if (!st) return;
    $("rmUrl").value = st.url || (st.tunnel === "installing" ? "Cloudflare aracı indiriliyor…" : st.tunnel === "error" ? "Tünel açılamadı: " + st.error : "Davet bağlantısı hazırlanıyor…");
    $("sTurn").textContent = st.turn ? "Cloudflare TURN açık: her ağda bağlanır." : "TURN anahtarı yok: bazı mobil hatlarda bağlantı kurulamayabilir (Kami Ayarlar > Kami Oda).";
    if (!st.url) setTimeout(tick, 1500);
  };
  tick();
  $("rmCopy").onclick = () => { const u = $("rmUrl").value; if (!u.startsWith("http")) return; navigator.clipboard?.writeText(u).catch(() => window.pywebview.api.copy_text(u)); $("rmCopy").textContent = "Kopyalandı"; setTimeout(() => ($("rmCopy").textContent = "Kopyala"), 1500); };
}

// ---------------------------------------------------------------- yardimcilar (dogrudan kanal)
const userPeers = () => [...(S.core?.peers.keys() || [])].filter((id) => S.roster.find((p) => p.id === id)?.kind === "user");
const myColor = () => color(S.core?.id || "x")[1];

// ---------------------------------------------------------------- ekran ustune cizim / lazer
// Koordinatlar videonun goruntu alanina gore 0..1; herkes (paylasan dahil) ayni ekran karosunda gorur.
const DRAW_HOLD = 3500, DRAW_FADE = 900, LASER_HOLD = 1400;
function vRect(T) {
  const W = T.el.clientWidth, H = T.el.clientHeight, vw = T.video.videoWidth || 16, vh = T.video.videoHeight || 9;
  const k = Math.min(W / vw, H / vh), w = vw * k, h = vh * k;
  return { x: (W - w) / 2, y: (H - h) / 2, w, h };
}
function setupDraw(T) {
  const el = T.el;
  el.insertAdjacentHTML("beforeend", `<canvas class="draw"></canvas><div class="vt-draw" hidden>
    <button data-t="p" title="Kalem">✎</button><button data-t="a" title="Ok">➚</button><button data-t="l" title="Lazer">●</button>
    <button data-t="x" title="Çizimlerimi sil">⌫</button><button data-t="" title="Kapat">✕</button></div>`);
  T.cv = el.querySelector("canvas.draw");
  const bar = el.querySelector(".vt-draw");
  const setTool = (t) => {
    T.tool = t; el.classList.toggle("drawing", !!t); bar.hidden = !t;
    bar.querySelectorAll("[data-t]").forEach((b) => b.classList.toggle("act", b.dataset.t === t && !!t));
    el.querySelector(".pen").classList.toggle("act", !!t);
  };
  el.querySelector(".pen").onclick = (e) => { e.stopPropagation(); setTool(T.tool ? "" : "p"); };
  bar.onclick = (e) => {
    e.stopPropagation(); const t = e.target.closest("[data-t]")?.dataset.t; if (t === undefined) return;
    if (t === "x") { drawSend(T, { t: "x" }); return; }
    setTool(t);
  };
  const cv = T.cv; let cur = null, lastSend = 0, buf = [];
  const pt = (e) => { const r = cv.getBoundingClientRect(), R = vRect(T); return [Math.round(((e.clientX - r.left - R.x) / R.w) * 1e4) / 1e4, Math.round(((e.clientY - r.top - R.y) / R.h) * 1e4) / 1e4]; };
  const flush = (end) => {
    if (!cur) return;
    if (cur.t === "p" && (buf.length || end)) { drawSend(T, { t: "p", id: cur.id, p: buf, e: end ? 1 : 0 }); buf = []; }
    if (cur.t === "a") drawSend(T, { t: "a", id: cur.id, p: cur.p, e: end ? 1 : 0 });
    lastSend = Date.now();
  };
  cv.addEventListener("click", (e) => e.stopPropagation());
  cv.addEventListener("pointerdown", (e) => {
    if (!T.tool) return;
    e.preventDefault(); e.stopPropagation(); cv.setPointerCapture?.(e.pointerId);
    const [x, y] = pt(e);
    if (T.tool === "l") { drawSend(T, { t: "l", x, y }); cur = { t: "l" }; return; }
    cur = { t: T.tool, id: Math.random().toString(36).slice(2, 8), p: T.tool === "a" ? [x, y, x, y] : [] };
    if (cur.t === "p") buf.push(x, y);
    flush(false);
  });
  cv.addEventListener("pointermove", (e) => {
    if (!T.tool) return;
    const [x, y] = pt(e);
    if (T.tool === "l") { if ((cur || e.pointerType === "mouse") && Date.now() - lastSend > 33) { drawSend(T, { t: "l", x, y }); lastSend = Date.now(); } return; }
    if (!cur) return;
    if (cur.t === "p") buf.push(x, y); else { cur.p[2] = x; cur.p[3] = y; }
    if (Date.now() - lastSend > 40) flush(false);
  });
  const up = () => { if (cur && cur.t !== "l") flush(true); cur = null; };
  cv.addEventListener("pointerup", up); cv.addEventListener("pointercancel", up);
}
function drawSend(T, m) {
  const msg = { k: "draw", o: T.owner, v: T.sid, c: myColor(), ...m };
  drawApply(T, S.core.id, msg);
  for (const id of userPeers()) S.core.sendDirect(id, msg);
}
function drawIn(from, m) {
  const T = S.tiles.get((m.o === S.core?.id ? "me" : m.o) + ":" + m.v);
  if (T?.cv) drawApply(T, from, m);
}
function drawApply(T, from, m) {
  const now = Date.now();
  if (m.t === "x") { for (const k of [...T.strokes.keys()]) if (k.startsWith(from + ":")) T.strokes.delete(k); }
  else if (m.t === "l") T.lasers.set(from, { x: m.x, y: m.y, c: m.c, at: now });
  else {
    const k = from + ":" + m.id; let s = T.strokes.get(k);
    if (!s) { s = { t: m.t, c: m.c, p: [] }; T.strokes.set(k, s); }
    if (m.t === "p") s.p.push(...(m.p || [])); else s.p = m.p || s.p;
    s.at = now; s.done = !!m.e;
  }
  if (!T.raf) T.raf = requestAnimationFrame(() => drawFrame(T));
}
function drawFrame(T) {
  T.raf = 0;
  if (T.dead) return;
  const cv = T.cv, dpr = window.devicePixelRatio || 1, W = T.el.clientWidth, H = T.el.clientHeight;
  if (cv.width !== Math.round(W * dpr) || cv.height !== Math.round(H * dpr)) { cv.width = Math.round(W * dpr); cv.height = Math.round(H * dpr); }
  const g = cv.getContext("2d"); g.setTransform(dpr, 0, 0, dpr, 0, 0); g.clearRect(0, 0, W, H);
  const R = vRect(T), X = (x) => R.x + x * R.w, Y = (y) => R.y + y * R.h, now = Date.now();
  g.lineCap = "round"; g.lineJoin = "round";
  for (const [k, s] of T.strokes) {
    const age = s.done ? now - s.at : 0;
    if (age > DRAW_HOLD + DRAW_FADE) { T.strokes.delete(k); continue; }
    g.globalAlpha = age > DRAW_HOLD ? 1 - (age - DRAW_HOLD) / DRAW_FADE : 1;
    g.strokeStyle = s.c; g.fillStyle = s.c; g.lineWidth = Math.max(3, R.w / 320);
    g.shadowColor = "rgba(0,0,0,.6)"; g.shadowBlur = 4;
    if (s.t === "p" && s.p.length >= 2) {
      g.beginPath(); g.moveTo(X(s.p[0]), Y(s.p[1]));
      for (let i = 2; i < s.p.length; i += 2) g.lineTo(X(s.p[i]), Y(s.p[i + 1]));
      if (s.p.length === 2) g.lineTo(X(s.p[0]) + 0.1, Y(s.p[1]));
      g.stroke();
    } else if (s.t === "a" && s.p.length === 4) {
      const x0 = X(s.p[0]), y0 = Y(s.p[1]), x1 = X(s.p[2]), y1 = Y(s.p[3]), a = Math.atan2(y1 - y0, x1 - x0), L = g.lineWidth * 5;
      g.beginPath(); g.moveTo(x0, y0); g.lineTo(x1, y1); g.stroke();
      g.beginPath(); g.moveTo(x1, y1); g.lineTo(x1 - L * Math.cos(a - 0.45), y1 - L * Math.sin(a - 0.45));
      g.lineTo(x1 - L * Math.cos(a + 0.45), y1 - L * Math.sin(a + 0.45)); g.closePath(); g.fill();
    }
  }
  g.shadowBlur = 0;
  for (const [who, l] of T.lasers) {
    const age = now - l.at; if (age > LASER_HOLD) { T.lasers.delete(who); continue; }
    g.globalAlpha = age > LASER_HOLD - 400 ? (LASER_HOLD - age) / 400 : 1;
    const x = X(l.x), y = Y(l.y);
    const rg = g.createRadialGradient(x, y, 0, x, y, 18); rg.addColorStop(0, l.c); rg.addColorStop(1, "transparent");
    g.fillStyle = rg; g.beginPath(); g.arc(x, y, 18, 0, 7); g.fill();
    g.fillStyle = "#fff"; g.beginPath(); g.arc(x, y, 4, 0, 7); g.fill();
    g.font = "600 12px system-ui"; g.fillStyle = l.c; g.fillText(nameOf(who === S.core.id ? "me" : who), x + 12, y - 10);
  }
  g.globalAlpha = 1;
  if (T.strokes.size || T.lasers.size) T.raf = requestAnimationFrame(() => drawFrame(T));
}

// ---------------------------------------------------------------- sohbette dosya / gorsel (dogrudan, sunucusuz)
const FILE_CHUNK = 16 * 1024, FILE_MAX = 300 * 1024 * 1024;
const RX = new Map();   // from:fid -> {name,size,mime,got,parts,el}
const fmtB = (n) => n < 1024 ? n + " B" : n < 1048576 ? (n / 1024).toFixed(0) + " KB" : (n / 1048576).toFixed(1) + " MB";
function chatEl(who, me) {
  const el = document.createElement("div"); el.className = "msg file" + (me ? " me" : "");
  const t = new Date();
  el.innerHTML = `<b>${esc(who)}</b><span class="fbody"></span><time>${String(t.getHours()).padStart(2, "0")}:${String(t.getMinutes()).padStart(2, "0")}</time>`;
  $("msgs").appendChild(el); $("msgs").scrollTop = $("msgs").scrollHeight;
  return el;
}
function fileShow(el, name, mime, blob, size) {
  const url = URL.createObjectURL(blob), body = el.querySelector(".fbody");
  if (/^image\//.test(mime)) {
    body.innerHTML = `<a href="${url}" download="${esc(name)}" target="_blank"><img src="${url}" alt="${esc(name)}"></a>`;
    body.querySelector("img").onload = () => ($("msgs").scrollTop = $("msgs").scrollHeight);
  } else if (/^video\//.test(mime)) body.innerHTML = `<video src="${url}" controls playsinline></video><a href="${url}" download="${esc(name)}">${esc(name)}</a>`;
  else if (/^audio\//.test(mime)) body.innerHTML = `<audio src="${url}" controls></audio><a href="${url}" download="${esc(name)}">${esc(name)}</a>`;
  else body.innerHTML = `<a class="fdl" href="${url}" download="${esc(name)}">⬇ ${esc(name)} <small>${fmtB(size)}</small></a>`;
}
function fileProg(el, name, got, size) {
  el.querySelector(".fbody").innerHTML = `<span class="fprog">${esc(name)} <small>${fmtB(got)} / ${fmtB(size)}</small><i style="width:${size ? Math.round(got / size * 100) : 0}%"></i></span>`;
}
async function sendFile(f) {
  if (!S.core || !f) return;
  if (f.size > FILE_MAX) { toast(`Dosya çok büyük (en fazla ${fmtB(FILE_MAX)}).`); return; }
  const name = f.name && f.name !== "image.png" ? f.name : `gorsel-${Date.now().toString(36)}.${(f.type.split("/")[1] || "bin").replace("jpeg", "jpg")}`;
  const to = userPeers().filter((id) => S.core.direct(id));
  const miss = userPeers().filter((id) => !S.core.direct(id));
  if (miss.length) toast(`${miss.map(nameOf).join(", ")} ile doğrudan bağlantı yok; dosya ona gitmiyor.`);
  const el = chatEl(PREF.name || "Ben", true);
  if (!to.length) { fileShow(el, name, f.type, f, f.size); if (!miss.length) toast("Odada dosya gönderilecek kimse yok."); return; }
  const fid = (Math.random() * 0xffffffff) >>> 0;
  const head = { k: "file", f: fid, n: name, s: f.size, m: f.type || "application/octet-stream" };
  for (const id of to) S.core.sendDirect(id, head);
  try {
    let lastUi = 0;
    for (let o = 0; o < f.size; o += FILE_CHUNK) {
      const data = new Uint8Array(await f.slice(o, o + FILE_CHUNK).arrayBuffer());
      const pkt = new Uint8Array(4 + data.length); new DataView(pkt.buffer).setUint32(0, fid); pkt.set(data, 4);
      for (const id of to) { try { await S.core.sendBin(id, pkt.buffer); } catch { /* o kisi ayrildi */ } }
      if (Date.now() - lastUi > 200) { fileProg(el, name, o + data.length, f.size); lastUi = Date.now(); }
    }
    fileShow(el, name, head.m, f, f.size);
  } catch (e) { el.querySelector(".fbody").textContent = "Gönderilemedi: " + e.message; }
}
function fileIn(from, m) {
  if (!(m.s >= 0) || m.s > FILE_MAX) return;
  const el = chatEl(nameOf(from), false);
  const R = { name: String(m.n || "dosya").slice(0, 200), size: m.s, mime: String(m.m || ""), got: 0, parts: [], el, ui: 0 };
  RX.set(from + ":" + m.f, R);
  if (!m.s) fileDone(from + ":" + m.f, R); else fileProg(el, R.name, 0, R.size);
  if ($("room").classList.contains("nochat")) { $("rmUnread").hidden = false; toast(`${nameOf(from)} bir dosya gönderiyor: ${R.name}`); }
}
function onBin(from, buf) {
  if (buf.byteLength < 4) return;
  const fid = new DataView(buf).getUint32(0), key = from + ":" + fid, R = RX.get(key); if (!R) return;
  R.parts.push(buf.slice(4)); R.got += buf.byteLength - 4;
  if (R.got >= R.size) fileDone(key, R);
  else if (Date.now() - R.ui > 200) { fileProg(R.el, R.name, R.got, R.size); R.ui = Date.now(); }
}
function fileDone(key, R) {
  RX.delete(key);
  fileShow(R.el, R.name, R.mime, new Blob(R.parts, { type: R.mime }), R.size);
  $("msgs").scrollTop = $("msgs").scrollHeight;
}
function dropRx(pid) {
  for (const [k, R] of [...RX]) if (k.startsWith(pid + ":")) { RX.delete(k); R.el.querySelector(".fbody").textContent = `${R.name}: aktarım yarıda kaldı`; }
}

// ---------------------------------------------------------------- PiP / arka plan modu (iPhone Safari icin)
// Oda tek bir videoya toplanir: varsa ekran/kamera goruntusu, yoksa konusanlari gosteren bir kart; tum uzak sesler
// bu videoya karisir. Safari'den cikinca PiP oynamaya devam ettigi icin ses kesilmez.
function pipCanvasTrack() {
  if (PIP.ct && PIP.ct.readyState === "live") return PIP.ct;
  PIP.cv = document.createElement("canvas"); PIP.cv.width = 640; PIP.cv.height = 360;
  pipDraw();
  PIP.ct = PIP.cv.captureStream(4).getVideoTracks()[0];
  return PIP.ct;
}
function pipDraw() {
  const c = PIP.cv; if (!c) return;
  const g = c.getContext("2d");
  g.fillStyle = "#07060B"; g.fillRect(0, 0, 640, 360);
  g.textAlign = "center"; g.fillStyle = "#C4B5FD"; g.font = "700 28px system-ui, sans-serif"; g.fillText("KAMI ODA", 320, 62);
  const users = S.roster.filter((p) => p.kind === "user").slice(0, 6), n = users.length;
  users.forEach((p, i) => {
    const x = 640 * (i + 1) / (n + 1), y = 185, talk = document.querySelector(`.tk[data-id="${p.id}"]`)?.classList.contains("talk"), [c1, c2] = color(p.id);
    if (talk) { g.beginPath(); g.arc(x, y, 54, 0, 7); g.fillStyle = "#2EE6A6"; g.fill(); }
    g.beginPath(); g.arc(x, y, 46, 0, 7); g.fillStyle = talk ? c2 : c1; g.fill();
    g.fillStyle = "#fff"; g.font = "700 36px system-ui, sans-serif"; g.fillText((p.name || "?").trim().charAt(0).toUpperCase(), x, y + 13);
    g.fillStyle = "#E9E4F5"; g.font = "500 17px system-ui, sans-serif"; g.fillText((p.name || "").slice(0, 12), x, y + 84);
  });
  if (S.muted || S.deaf) { g.fillStyle = "#FF8095"; g.font = "600 16px system-ui, sans-serif"; g.fillText(S.deaf ? "Sağırlaştırıldın" : "Mikrofonun kapalı", 320, 340); }
}
function pipVideoTrack() {
  const tiles = [...S.tiles.values()];
  const pick = tiles.find((t) => t.el.classList.contains("focus")) || tiles.find((t) => t.pid !== "me" && t.kind !== "cam") || tiles.find((t) => t.pid !== "me") || tiles[0];
  const tr = pick?.video.srcObject?.getVideoTracks()[0];
  return tr && tr.readyState === "live" ? tr : pipCanvasTrack();
}
function pipMix() {
  if (!S.ctx || S.ctx.state !== "running") return null;
  PIP.dest ||= S.ctx.createMediaStreamDestination();
  const want = new Map();
  for (const [k, a] of S.audios) if (a.srcObject) want.set("a" + k, { st: a.srcObject, vol: a.volume });
  for (const [k, T] of S.tiles) { const st = T.video.srcObject; if (T.pid !== "me" && st?.getAudioTracks().length) want.set("t" + k, { st, vol: T.userMuted ? 0 : T.video.volume }); }
  for (const [k, n] of PIP.nodes) if (!want.has(k)) { try { n.src.disconnect(); n.g.disconnect(); } catch { /* yok */ } PIP.nodes.delete(k); }
  for (const [k, w] of want) {
    let n = PIP.nodes.get(k);
    if (!n) { try { const src = S.ctx.createMediaStreamSource(w.st), g = S.ctx.createGain(); src.connect(g); g.connect(PIP.dest); n = { src, g }; PIP.nodes.set(k, n); } catch { continue; } }
    n.g.gain.value = w.vol;
  }
  return PIP.dest.stream.getAudioTracks()[0];
}
function pipTick() {
  if (!PIP.on) return;
  if (PIP.mixed) pipMix();
  const want = pipVideoTrack(), cur = PIP.st.getVideoTracks()[0];
  if (cur !== want) { if (cur) PIP.st.removeTrack(cur); PIP.st.addTrack(want); }
}
const pipActive = () => document.pictureInPictureElement === PIP.v || PIP.v?.webkitPresentationMode === "picture-in-picture";
async function pipEnter() {
  const v = PIP.v;
  try {
    if (v.requestPictureInPicture && document.pictureInPictureEnabled) await v.requestPictureInPicture();
    else if (v.webkitSupportsPresentationMode?.("picture-in-picture")) v.webkitSetPresentationMode("picture-in-picture");
    return true;
  } catch { return false; }
}
async function pipStart() {
  if (PIP.on) { if (!pipActive()) pipEnter(); return; }
  PIP.v = $("pipV");
  try { await S.ctx?.resume(); } catch { /* yok */ }
  const at = pipMix();
  PIP.mixed = !!at;
  PIP.st = new MediaStream([pipVideoTrack(), ...(at ? [at] : [])]);
  PIP.v.srcObject = PIP.st;
  PIP.on = true; applyMicState();
  $("pipBox").hidden = false; $("bPip").classList.add("act");
  try { await PIP.v.play(); } catch { /* dokunus bekliyor */ }
  PIP.t1 = setInterval(pipTick, 1000); PIP.t2 = setInterval(pipDraw, 300);
  if (!(await pipEnter())) toast("Küçük pencereye almak için kutudaki ⧉ düğmesine dokun; sonra Safari'den çıkabilirsin.");
  if (!PIP.mixed) toast("Ses karıştırıcı açılamadı; arka planda ses kesilebilir. Ekrana bir kez dokunup tekrar dene.");
}
function pipStop() {
  if (!PIP.on) return;
  if (document.pictureInPictureElement === PIP.v) document.exitPictureInPicture?.().catch(() => {});
  else if (PIP.v?.webkitPresentationMode === "picture-in-picture") PIP.v.webkitSetPresentationMode("inline");
  clearInterval(PIP.t1); clearInterval(PIP.t2);
  for (const n of PIP.nodes.values()) { try { n.src.disconnect(); n.g.disconnect(); } catch { /* yok */ } }
  PIP.nodes.clear();
  PIP.v.srcObject = null; PIP.on = false; PIP.mixed = false;
  $("pipBox").hidden = true; $("bPip").classList.remove("act");
  applyMicState();
}
$("bPip").onclick = () => (PIP.on && pipActive() ? pipStop() : pipStart());
$("pipGo").onclick = (e) => { e.stopPropagation(); pipEnter(); };
$("pipX").onclick = (e) => { e.stopPropagation(); pipStop(); };

if (window.pywebview?.api) init(); else { let done = false; window.addEventListener("pywebviewready", () => { if (!done) { done = true; init(); } }); setTimeout(() => { if (!done) { done = true; init(); } }, 400); }
