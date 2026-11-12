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
    peerstate: () => netDot(), error: () => toast("Bağlantı koptu, yeniden deneniyor…"),
  } });
  if (S.mic) S.micSid = S.core.addLocal("mic", new MediaStream([S.mic]));
  await S.core.join();
  S.core.setMe({ muted: S.muted });
  $("join").hidden = true; $("room").hidden = false;
  if (PREF.chatOpen === false) $("room").classList.add("nochat");
  applyMicState(); setupSettings(); layout(); setInterval(statsLoop, 3000);
  if (!navigator.mediaDevices?.getDisplayMedia || /iPhone|iPad|Android/i.test(navigator.userAgent)) $("bShare").hidden = true;
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
  for (const a of S.audios.values()) a.muted = S.deaf;
  for (const t of S.tiles.values()) t.video.muted = S.deaf || t.userMuted;
}
function setMuted(v) { S.muted = v; PREF.muted = v; save(); applyMicState(); S.core?.setMe({ muted: v }); }
function setDeaf(v) { S.deaf = v; applyMicState(); S.core?.setMe({ deaf: v }); }
$("bMic").onclick = () => setMuted(!S.muted);
$("bDeaf").onclick = () => setDeaf(!S.deaf);
$("bLeave").onclick = async () => { await S.core?.leave(); stopShare(); document.body.innerHTML = `<div class="jn"><div class="jn-box"><div class="jn-sigil"><i></i><i></i><i></i><b>KAMI</b></div><p>Odadan ayrıldın.</p><button onclick="location.reload()">Tekrar gir</button></div></div>`; };

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
      audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false }, systemAudio: "include", selfBrowserSurface: "exclude", surfaceSwitching: "include" });
    S.share = st;
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

// ---------------------------------------------------------------- uzak izler
function onTrack(pid, stream, kind, track) {
  if (kind === "mic" || (track.kind === "audio" && !stream.getVideoTracks().length && kind !== "player" && kind !== "screen")) {
    let a = S.audios.get(pid + ":" + stream.id);
    if (!a) {
      a = new Audio(); a.autoplay = true; a.playsInline = true; a.srcObject = stream; a.muted = S.deaf;
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
}
document.addEventListener("click", () => { for (const a of S.audios.values()) if (a.paused) a.play().catch(() => {}); S.ctx?.resume?.(); }, { capture: true });

function nameOf(pid) { return pid === "me" ? (PREF.name || "Ben") : (S.roster.find((p) => p.id === pid)?.name || "?"); }
function addTile(pid, stream, kind, mine) {
  const key = pid + ":" + stream.id;
  if (S.tiles.has(key)) return;
  const el = document.createElement("div");
  el.className = "vt"; el.dataset.key = key;
  const who = nameOf(pid), lbl = kind === "player" ? "Oynatıcı" : "Ekran";
  el.innerHTML = `<video autoplay playsinline ${mine ? "muted" : ""}></video>
    <div class="vt-bar"><span class="live">CANLI</span><b>${esc(who.includes(lbl) ? who : who + " · " + lbl)}</b><span class="info"></span><span class="sp"></span>
      ${mine ? "" : `<select class="q" title="Kalite"><option value="auto">Otomatik</option><option value="src">Kaynak</option><option value="1080">1080p60</option><option value="720">720p30</option><option value="480">480p30</option></select>
      <input type="range" class="vol" min="0" max="1" step="0.05" value="1" title="Ses">`}
      <button class="fs" title="Tam ekran"><svg viewBox="0 0 24 24"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg></button></div>`;
  const v = el.querySelector("video");
  v.srcObject = stream;
  const T = { el, video: v, pid, kind, userMuted: false, q: PREF.q || "auto" };
  v.muted = mine || S.deaf;
  v.play().catch(() => { const b = document.createElement("div"); b.className = "tapplay"; b.textContent = "▶ Yayını aç"; b.onclick = () => { v.play(); b.remove(); }; el.appendChild(b); });
  if (!mine) {
    const q = el.querySelector(".q"); q.value = T.q;
    q.onchange = () => { T.q = q.value; PREF.q = q.value; save(); if (q.value !== "auto") S.core.requestQuality(q.value, pid); else { T.autoQ = "src"; S.core.requestQuality("src", pid); } };
    if (T.q !== "auto") S.core.requestQuality(T.q, pid);
    el.querySelector(".vol").oninput = (e) => { v.volume = +e.target.value; };
  }
  el.querySelector(".fs").onclick = (e) => { e.stopPropagation(); document.fullscreenElement ? document.exitFullscreen() : (el.requestFullscreen?.() || v.webkitEnterFullscreen?.()); };
  el.addEventListener("click", () => { el.classList.add("tap"); setTimeout(() => el.classList.remove("tap"), 2500); if (S.tiles.size > 1) { const f = el.classList.toggle("focus"); $("videos").classList.toggle("focused", f); document.querySelectorAll(".vt").forEach((x) => x !== el && x.classList.remove("focus")); } });
  $("videos").appendChild(el);
  S.tiles.set(key, T);
  if (kind === "player" && !mine) toast(`${who} oynatıcıdan yayın başlattı`);
  layout();
}
function removeTile(key) {
  const T = S.tiles.get(key); if (!T) return;
  T.video.srcObject = null; T.el.remove(); S.tiles.delete(key);
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
      (p.deaf ? `<svg viewBox="0 0 24 24"><path d="M4 14v-2a8 8 0 0 1 16 0v2M3 3l18 18"/></svg>` : "") + (p.sharing ? "ekran paylaşıyor" : "");
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
      const order = ["src", "1080", "720", "480"], i = order.indexOf(T.autoQ || "src");
      if ((lost > 40 || (s.fps && s.fps < 18)) && i < 3) { T.autoQ = order[i + 1]; T.clean = 0; S.core.requestQuality(T.autoQ, T.pid); toast(`Bağlantı zayıf: yayın ${T.autoQ === "src" ? "kaynak" : T.autoQ + "p"} kaliteye indi`); }
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

if (window.pywebview?.api) init(); else { let done = false; window.addEventListener("pywebviewready", () => { if (!done) { done = true; init(); } }); setTimeout(() => { if (!done) { done = true; init(); } }, 400); }
