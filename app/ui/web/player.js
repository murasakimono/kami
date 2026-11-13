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
      <div class="pl-bigeq l" id="plBigEqL">${"<i></i>".repeat(16)}</div>
      <canvas id="plBig" width="403" height="614"></canvas>
      <div class="pl-bigeq r" id="plBigEqR">${"<i></i>".repeat(16)}</div>
    </div>
    <div class="pl-empty" id="plEmpty" hidden><div><b>Kami Player</b><span>${plL("Bir video ya da şarkı sürükleyip bırak, ya da kütüphaneden seç.", "Drop a video or song here, or pick one from the library.")}</span><button class="pl-b" data-pl="queue">${plL("Kütüphaneyi aç", "Open library")}</button></div></div>
    <div class="pl-subs2" id="plSubs2"></div>
    <div class="pl-subs" id="plSubs"></div>
    <div class="pl-spin" id="plSpin"></div>
    <div class="pl-top">
      <div class="pl-title"><b id="plTitle"></b><span id="plMode"></span></div>
      ${window.KAMI_PLAYER_WINDOW ? "" : `<button class="pl-x" id="plClose" title="${plL("Kapat (Esc)", "Close (Esc)")}">‹</button>`}
    </div>
    <div class="pl-deck">
      <div class="pl-seek" id="plSeek"><i class="pl-buf" id="plBuf"></i><i class="pl-fill" id="plFill"></i><i class="pl-knob" id="plKnob"></i><span class="pl-tip" id="plTip"><img id="plThumb" alt=""><b id="plTipT"></b></span></div>
      <div class="pl-row">
        <div class="pl-left"><span class="pl-time"><b id="plCur">0:00</b> / <span id="plDur">0:00</span></span>
          <button class="pl-b" data-pl="prev" id="plPrev" title="${plL("Önceki (P)", "Previous (P)")}">⏮</button><button class="pl-b" data-pl="back" title="-10 sn">−10</button><button class="pl-b" data-pl="fwd" title="+10 sn">+10</button><button class="pl-b" data-pl="next" id="plNext" title="${plL("Sonraki (N)", "Next (N)")}">⏭</button></div>
        <div class="pl-eqw"><div class="pl-eq l" id="plEqL">${"<i></i>".repeat(7)}</div><button class="pl-eye" id="plEye" title="${plL("Oynat / duraklat (Boşluk)", "Play / pause (Space)")}"><svg class="pl-ring" viewBox="0 0 48 48" aria-hidden="true"><circle class="bg" cx="24" cy="24" r="21.5"/><circle class="fg" id="plRing" cx="24" cy="24" r="21.5" pathLength="100" transform="rotate(-90 24 24)"/></svg><svg class="pl-pp" viewBox="0 0 24 24" aria-hidden="true"><path class="l"/><path class="r"/></svg></button><div class="pl-eq r" id="plEqR">${"<i></i>".repeat(7)}</div></div>
        <div class="pl-right">
          <select class="pl-sel" id="plSub" title="${plL("Altyazı (C)", "Subtitles (C)")}"></select>
          <select class="pl-sel" id="plAud" title="${plL("Ses izi", "Audio track")}"></select>
          <select class="pl-sel" id="plRate" title="${plL("Hız", "Speed")}">${[0.5, 0.75, 1, 1.25, 1.5, 2].map((r) => `<option value="${r}" ${r === 1 ? "selected" : ""}>${r}×</option>`).join("")}</select>
          <label class="pl-vol" title="${plL("Ses (↑ ↓, M)", "Volume (↑ ↓, M)")}"><button class="pl-b" data-pl="mute" id="plMute">◢</button><input type="range" id="plVol" min="0" max="2" step="0.02" value="1"></label>
          <button class="pl-b" data-pl="mini" title="${plL("Mini oynatıcı (B)", "Mini player (B)")}">▭</button>
          <button class="pl-b" data-pl="ocr" title="${plL("Ekrandaki yazıyı oku (O)", "Read on-screen text (O)")}">⌗</button>
          <button class="pl-b" data-pl="queue" title="${plL("Sıradakiler / kütüphane (Q)", "Queue / library (Q)")}">☰</button>
          <button class="pl-b" data-pl="settings" title="${plL("Altyazı, görüntü, ses ayarları", "Subtitle, picture, audio settings")}">⚙</button>
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
  v.addEventListener("ended", () => { plEyeState(); window.plOnEnded?.(); });
  v.addEventListener("loadedmetadata", () => {
    if (PL.mode === "direct" && isFinite(v.duration)) PL.dur = v.duration;
    $("#plDur").textContent = fmtT(PL.dur);
    if (PL.info.kind === "video" && PL.mode === "direct") setTimeout(() => { if (PL.open && !v.videoWidth) plFallback("novideo"); }, 1500);
  });
  v.addEventListener("error", () => plFallback("error"));
  v.addEventListener("click", () => { clearTimeout(PL.clickT); PL.clickT = setTimeout(plToggle, 240); });
  v.addEventListener("dblclick", (e) => {
    clearTimeout(PL.clickT);   // cift tik videoyu durdurmasin
    const x = e.clientX / innerWidth;
    if (x < 0.3) plSeek(plNow() - 10); else if (x > 0.7) plSeek(plNow() + 10); else plFull();
  });
  el.addEventListener("wheel", (e) => {
    if (e.target.closest(".pl-panel, .pl-deck select, #plDrawer")) return;
    e.preventDefault(); plSetVol((PL.vol ?? 1) + (e.deltaY < 0 ? 0.05 : -0.05)); plWake();
    toast(plL("Ses ", "Volume ") + Math.round(PL.vol * 100) + "%");
  }, { passive: false });
  el.addEventListener("auxclick", (e) => { if (e.button === 1 && !e.target.closest("button, select, input")) { e.preventDefault(); plFull(); } });
  v.addEventListener("loadeddata", () => {   // kare suresi (kare kare ilerleme icin)
    if (v.requestVideoFrameCallback) {
      let last = null;
      const cb = (now, md) => { if (last !== null && md.mediaTime > last) PL.frameDur = Math.min(0.1, md.mediaTime - last); last = md.mediaTime; if (!PL.frameDur) v.requestVideoFrameCallback(cb); };
      v.requestVideoFrameCallback(cb);
    }
  });
  $("#plEye").addEventListener("click", plToggle);
  $("#plClose")?.addEventListener("click", plClose);
  el.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pl]"); if (!b) return;
    ({ back: () => plSeek(plNow() - 10), fwd: () => plSeek(plNow() + 10), mute: () => { v.muted = !v.muted; plVolUi(); }, full: plFull,
       prev: () => window.plQueueStep?.(-1), next: () => window.plQueueStep?.(1), queue: () => window.plDrawer?.(), settings: () => window.plSettings?.(), ocr: () => plOcrStart(), mini: () => window.plMini?.() })[b.dataset.pl]?.();
  });
  $("#plVol").addEventListener("input", (e) => { v.muted = false; plSetVol(+e.target.value); });
  $("#plRate").addEventListener("change", (e) => { v.playbackRate = +e.target.value; });
  $("#plSub").addEventListener("change", (e) => plLoadSub(+e.target.value));
  $("#plAud").addEventListener("change", (e) => plAudio(+e.target.value));
  // seek cubugu: tikla / surukle, uzerinde zaman ipucu
  const seek = $("#plSeek");
  const at = (e) => { const r = seek.getBoundingClientRect(); return Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * (PL.dur || 0); };
  seek.addEventListener("pointerdown", (e) => { PL.seeking = true; seek.setPointerCapture(e.pointerId); plDrawPos(at(e)); });
  seek.addEventListener("pointermove", (e) => {
    const t = at(e), tip = $("#plTip"); $("#plTipT").textContent = fmtT(t);
    plThumb(t);
    tip.style.left = (e.clientX - seek.getBoundingClientRect().left) + "px";
    if (PL.seeking) plDrawPos(t);
  });
  seek.addEventListener("pointerup", (e) => { if (PL.seeking) { PL.seeking = false; plSeek(at(e)); } });
  el.addEventListener("mousemove", plWake);
  document.addEventListener("keydown", plKey, true);
  window.plOnBuild?.();
  try { PL.vol = +(localStorage.getItem("kami.vol") || 1); } catch { PL.vol = 1; }
  plSetVol(PL.vol);
  if (window.KamiEye) {
    PL.big = new KamiEye($("#plBig"), { assets: "eye/char/", eyeY: 0.38, mirrorFrame: true });
  }
}

// cubuk onizlemesi: 5 sn dilimleri, istekler 120 ms'de bir (sunucu onbellekli)
function plThumb(t) {
  const img = $("#plThumb"), u = PL.info?.thumb_url;
  img.hidden = !u; if (!u) return;
  const slot = Math.floor(t / 5);
  if (slot === PL.thumbSlot) return;
  PL.thumbSlot = slot;
  clearTimeout(PL.thumbT);
  PL.thumbT = setTimeout(() => { img.src = `${u}?t=${slot * 5}`; }, 120);
}

// ---------- acma / kapama ----------
async function playerOpen(id) {
  if (!$("#player")) plBuild();
  let r;
  try { r = await api.player_open(id); } catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) { toast(plL("Oynatılamadı: ", "Can't play: ") + (r?.error || "?"), true); return; }
  plStart(r);
}
async function playerOpenPath(path, queue) {
  if (!$("#player")) plBuild();
  if (queue && queue.length && typeof PX !== "undefined") PX.pending = queue;
  let r;
  try { r = await api.player_open_path(path); } catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) { toast(plL("Oynatılamadı: ", "Can't play: ") + (r?.error || "?"), true); return; }
  plStart(r);
}
if (typeof STATE_HOOKS !== "undefined") STATE_HOOKS.push((s) => { const q = s.play_requests || []; if (q.length) playerOpenPath(q[q.length - 1]); });

// indirmeden izle: yt-dlp akisi / Real-Debrid / dogrudan URL (arka plan isi; ag yavas olabilir)
async function playerOpenUrl(url) {
  if (!$("#player")) plBuild();
  toast(plL("Bağlantı açılıyor…", "Opening link…"));
  let r;
  try { r = await slow("player_open_url", url); } catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) { toast(plL("İzlenemedi: ", "Can't stream: ") + (r?.error || "?"), true); return; }
  plStart(r);
  toast({ rd: "Real-Debrid", ytdlp: "yt-dlp", direct: plL("doğrudan", "direct") }[r.source] + plL(" ile oynatılıyor", " stream"));
}

function plStart(r) {
  const el = $("#player"), v = $("#plVideo");
  window.plIdle?.(false);
  Object.assign(PL, { open: true, info: r, mode: r.mode, offset: 0, audio: 0, failed: 0, dur: r.duration || 0, cues: [], subIdx: -1, subShift: 0 });
  el.hidden = false; el.classList.toggle("is-audio", r.kind === "audio");
  document.body.classList.add("pl-open");
  $("#plTitle").textContent = r.title;

  plModeUi();
  $("#plCover").style.backgroundImage = r.cover ? `url("${r.cover}")` : "";
  $("#plCover").hidden = !r.cover;
  // altyazi listesi: yan dosyalar (+ Whisper) + dosya ici izler (resim altyazilar metne cevrilemez, listede yok)
  PL.subList = [
    ...r.subs.map((x) => ({ label: x.label, url: x.url, raw: x.ass ? x.raw_url : "", lang: plLang(x.label) })),
    ...(r.embedded || []).filter((x) => !x.image).map((x) => ({
      label: [plLangName(x.lang), x.title, x.ass ? "ASS" : ""].filter(Boolean).join(" · ") || plL("İz ", "Track ") + (x.index + 1),
      url: x.url, raw: x.ass ? x.raw_url : "", lang: plLang(x.lang), def: x.default, forced: x.forced, embedded: true })),
  ];
  PL.cues2 = []; PL.sub2Idx = -1; plAssDestroy();
  $("#plSub").innerHTML = `<option value="-1">${plL("Altyazı yok", "No subtitles")}</option>` + PL.subList.map((x, i) => `<option value="${i}">${escapeHtml(x.label)}</option>`).join("");
  $("#plSub").hidden = !PL.subList.length;
  $("#plAud").innerHTML = r.audio.map((a, i) => `<option value="${i}">${escapeHtml([a.lang, a.title, a.codec].filter(Boolean).join(" · ") || plL("Ses ", "Audio ") + (i + 1))}</option>`).join("");
  $("#plAud").hidden = r.audio.length < 2;
  if (window.plPickTracks) window.plPickTracks(r);   // dizi/klasor tercihi + dil sirasi (player-lib)
  else if (PL.subList.length) { $("#plSub").value = "0"; plLoadSub(0); }
  plBlinkLoop();
  if (r.kind === "audio") PL.big?.ready.then(() => PL.big.start());
  const saved = plPos(r.path);
  const resume = saved && saved > 15 && (!PL.dur || saved < PL.dur - 30) ? saved : 0;
  if (PL.mode === "direct" && window.plDialogMix?.()) PL.mode = "remux";   // 5.1 diyalog karisimi ffmpeg ister
  if (resume) plSetSrcResume(resume); else plSetSrc(0);
  window.plOnStart?.(r);
  window.plMusicStart?.(r);
  window.plExtraStart?.(r);
  plMediaSession();
  plWake();
}
// kaldigin yerden devam: dosya yolu -> saniye (bu bilgisayarda, WebView2 depolamasinda)
function plPos(path, t) {
  try {
    const all = JSON.parse(localStorage.getItem("kami.pos") || "{}");
    if (t === undefined) return all[path] || 0;
    if (t === null) delete all[path]; else all[path] = Math.round(t);
    const keys = Object.keys(all); if (keys.length > 500) delete all[keys[0]];
    localStorage.setItem("kami.pos", JSON.stringify(all));
  } catch { /* depolama yoksa devam ozelligi sessizce kapali */ }
  return 0;
}
async function plSetSrcResume(t) {
  if (PL.mode === "direct") plSetSrc(t); else await plSeek(t, true);
  const chip = document.createElement("button");
  chip.className = "pl-chip"; chip.textContent = plL(`${fmtT(t)}'den devam · baştan başla`, `Resumed at ${fmtT(t)} · start over`);
  chip.onclick = () => { plSeek(0, true); chip.remove(); };
  $("#player").appendChild(chip);
  setTimeout(() => chip.remove(), 6000);
}
// Windows medya paneli + klavyedeki medya tuslari (WebView2 navigator.mediaSession -> SMTC)
function plMediaSession() {
  const ms = navigator.mediaSession; if (!ms) return;
  try {
    ms.metadata = new MediaMetadata({ title: PL.info.title, artist: "Kami", artwork: PL.info.cover ? [{ src: PL.info.cover, sizes: "300x300", type: "image/jpeg" }] : [] });
    ms.setActionHandler("play", () => $("#plVideo").play());
    ms.setActionHandler("pause", () => $("#plVideo").pause());
    ms.setActionHandler("seekbackward", () => plSeek(plNow() - 10));
    ms.setActionHandler("seekforward", () => plSeek(plNow() + 10));
    ms.setActionHandler("stop", plClose);
  } catch { /* eski WebView2 */ }
}
function plClose() {
  const v = $("#plVideo");
  clearInterval(PL.infoT); $("#plInfo")?.remove();
  plAssDestroy();   // gizli videoda JASSUB yeniden boyutlanmaya calisip hata atmasin
  if (PL.info?.path) { const t = plNow(); plPos(PL.info.path, PL.dur && t > PL.dur - 30 ? null : t); }

  v.pause(); v.removeAttribute("src"); v.load();   // akis baglantisi kapanir -> sunucu ffmpeg'i oldurur
  PL.open = false;
  $("#plSpin").classList.remove("on");
  if (window.KAMI_PLAYER_WINDOW) { window.plIdle?.(true); PL.big?.stop(); clearTimeout(PL.blinkT); return; }
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
  if (window.plDialogMix?.()) q.set("dm", "1");
  return `${r.stream_url}?${q}`;
}
function plSetSrc(t, autoplay = true) {
  const v = $("#plVideo");
  PL.offset = PL.mode === "direct" ? 0 : t;
  plAssSync();
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
  if (PL.info.path && Math.abs(t - (PL.lastSave || 0)) > 5) {   // 5 sn'de bir konumu yaz; sona yakinsa sil
    PL.lastSave = t;
    plPos(PL.info.path, PL.dur && t > PL.dur - 30 ? null : t);
  }
  $("#plCur").textContent = fmtT(t);
  const ring = $("#plRing"); if (ring) ring.style.strokeDashoffset = String(100 - (PL.dur ? Math.min(1, t / PL.dur) : 0) * 100);
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
  PL.big?.set({ playbackState: "idle", isDownloading: false });   // muzikte figur ziplamaz
  $("#player").classList.toggle("paused", v.paused);
  plWake();
}
function plToggle() {
  const v = $("#plVideo");
  if (v.paused) v.play().then(plAudioGraph).catch(() => {}); else v.pause();
}
function plFull() {
  if (window.KAMI_PLAYER_WINDOW && api?.player_fullscreen) {   // WebView2'de oge tam ekrani pencereyi buyutmuyor
    PL.full = !PL.full; $("#player").classList.toggle("full", PL.full);
    api.player_fullscreen(PL.full); return;
  }
  if (document.fullscreenElement) document.exitFullscreen(); else $("#player").requestFullscreen?.();
}
// ses 0-%200: %100'e kadar video.volume, ustu Web Audio kazanci (PL.boost)
function plSetVol(x) {
  const v = $("#plVideo");
  PL.vol = Math.max(0, Math.min(2, Math.round(x * 100) / 100));
  v.volume = Math.min(1, PL.vol);
  if (PL.boost) PL.boost.gain.setTargetAtTime(Math.max(1, PL.vol), PL.ctx.currentTime, 0.03);
  plVolUi();
  try { localStorage.setItem("kami.vol", String(PL.vol)); } catch { /* yok */ }
}
function plVolUi() {
  const v = $("#plVideo");
  $("#plVol").value = v.muted ? 0 : (PL.vol ?? v.volume);
  $("#plVol").title = Math.round((v.muted ? 0 : (PL.vol ?? v.volume)) * 100) + "%";
  $("#plVol").classList.toggle("boost", (PL.vol || 0) > 1);
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
    PL.comp = PL.ctx.createDynamicsCompressor(); PL.gain = PL.ctx.createGain();
    PL.boost = PL.ctx.createGain(); PL.delay = PL.ctx.createDelay(3);
    PL.src.connect(PL.comp); PL.comp.connect(PL.gain); PL.gain.connect(PL.boost); PL.boost.connect(PL.delay);
    PL.delay.connect(PL.an); PL.an.connect(PL.ctx.destination);
    PL.boost.gain.value = Math.max(1, PL.vol || 1);
    window._plGetAna = () => (plAudioGraph(), PL.an);
    window.plApplyAudio?.();
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
        plEqDraw(lv); plBigEq();   // ekolayzir figurden bagimsiz (DOM cubuklari), figur sadece nefes alir
        const bass = lv[0] * 0.6 + lv[1] * 0.4;
        $("#player").style.setProperty("--pl-beat", bass.toFixed(3));
      } else if (PL.eqOn) { PL.eqOn = false; plEqDraw(null); plBigEq(true); }
      requestAnimationFrame(loop);
    };
    loop();
  } catch (e) { console.warn("Web Audio kurulamadi", e); }
}

// muzik modunda figurun iki yaninda bagimsiz, ayna simetrik 16 bantlik ekolayzir
function plBigEq(reset) {
  const L = $("#plBigEqL"), R = $("#plBigEqR"); if (!L || !PL.bins) return;
  PL.eqOn = !reset;
  const n = 16, bars = [...L.children], bars2 = [...R.children];
  for (let i = 0; i < n; i++) {
    let v = 0;
    if (!reset) { const k0 = Math.floor(Math.pow(PL.bins.length * 0.8, i / n)), k1 = Math.max(k0 + 1, Math.floor(Math.pow(PL.bins.length * 0.8, (i + 1) / n))); for (let k = k0; k < k1; k++) v = Math.max(v, PL.bins[k]); v /= 255; }
    const h = (4 + Math.pow(v, 1.3) * 100).toFixed(1) + "%";
    bars[n - 1 - i].style.height = h; bars2[i].style.height = h;
  }
}
function plEqDraw(lv) {
  const L = $$("#plEqL i"), R = $$("#plEqR i");
  for (let i = 0; i < 7; i++) {   // ic bantlar goze yakin: bas ortada, tiz disarida
    const h = lv ? 3 + lv[i] * 22 : 3;
    L[6 - i].style.height = R[i].style.height = h.toFixed(1) + "px";
  }
}

// ---------- altyazi: WebVTT ayristir, kendi katmanimizda ciz ----------
async function plLoadSub(i, slot = 1) {
  if (slot === 2) {   // DUAL: ikinci altyazi her zaman duz metin, ustte
    PL.sub2Idx = i; PL.cues2 = []; $("#plSubs2").innerHTML = ""; $("#plSubs2").dataset.h = "";
    if (i < 0 || !PL.subList[i]) return;
    try { PL.cues2 = plParseVtt(await (await fetch(PL.subList[i].url)).text()); } catch { toast(plL("Altyazı yüklenemedi", "Subtitle failed to load"), true); }
    return;
  }
  PL.subIdx = i; PL.cues = [];
  $("#plSubs").innerHTML = ""; $("#plSubs").dataset.h = "";
  plAssDestroy();
  if (i >= 0) PL.lastSub = i;
  window.plOnSubChange?.();
  if (i < 0 || !PL.subList[i]) return;
  const it = PL.subList[i];
  const kamiStyle = typeof PX !== "undefined" && PX.cfg.assStyle === "kami";   // ASS'i Kami altyazi stiliyle duz goster
  if (it.raw && !kamiStyle && window.JASSUB && PL.info.jassub && await plAss(it)) return;   // ASS: stiller, tabelalar, konumlar korunur
  try {
    if (it.embedded) $("#plSpin").classList.add("on");   // buyuk mkv'de iz cikarma birkac saniye surebilir
    PL.cues = plParseVtt(await (await fetch(it.url)).text());
  } catch (e) { toast(plL("Altyazı yüklenemedi", "Subtitle failed to load"), true); }
  finally { if (!$("#plVideo").paused || $("#plVideo").readyState > 2) $("#plSpin").classList.remove("on"); }
}
// ASS/SSA: JASSUB (libass WASM). Worker file:// sayfasindan acilamaz -> medya sunucusundan alinip blob ile
async function plAss(it) {
  try {
    const base = PL.info.jassub;
    if (!PL.workerBlob) PL.workerBlob = URL.createObjectURL(new Blob([await (await fetch(base + "jassub-worker.js")).text()], { type: "text/javascript" }));
    const sub = await (await fetch(it.raw)).text();
    if (!sub.trim().startsWith("[Script")) return false;
    PL.ass = new JASSUB({
      video: $("#plVideo"), subContent: sub, workerUrl: PL.workerBlob,
      wasmUrl: base + "jassub-worker.wasm", modernWasmUrl: base + "jassub-worker-modern.wasm",
      fonts: PL.info.fonts || [], availableFonts: { "liberation sans": base + "default.woff2" }, fallbackFont: "liberation sans",
      timeOffset: PL.offset - PL.subShift,
    });
    return true;
  } catch (e) { console.warn("ASS cizici acilamadi, duz metne dusuluyor", e); plAssDestroy(); return false; }
}
function plAssDestroy() { try { PL.ass?.destroy(); } catch { /* zaten kapali */ } PL.ass = null; }
function plAssSync() { if (PL.ass) PL.ass.timeOffset = PL.offset - PL.subShift; }
// altyazi kaydirma: G / H (VLC gibi), ayarlar panelinde de dugme
function plShift(d) {
  PL.subShift = d === 0 ? 0 : Math.round((PL.subShift + d) * 10) / 10;
  plAssSync(); plSubDraw(plNow());
  toast(plL("Altyazı ", "Subtitles ") + (PL.subShift > 0 ? "+" : "") + PL.subShift.toFixed(1) + " sn");
  window.plOnShift?.();
}
// dil kodlari: tur/tr/Turkish -> tr
const PL_LANG = { tur: "tr", tr: "tr", turkish: "tr", eng: "en", en: "en", english: "en", jpn: "ja", ja: "ja", japanese: "ja", ger: "de", deu: "de", de: "de",
  fre: "fr", fra: "fr", fr: "fr", spa: "es", es: "es", ita: "it", it: "it", rus: "ru", ru: "ru", ara: "ar", ar: "ar", kor: "ko", ko: "ko", chi: "zh", zho: "zh", zh: "zh", por: "pt", pt: "pt" };
function plLang(x) {
  const t = String(x || "").toLowerCase().split(/[^a-z]+/).filter(Boolean);
  for (const w of t) if (PL_LANG[w]) return PL_LANG[w];
  return t[0] && t[0].length <= 3 ? t[0] : "";
}
function plLangName(code) {
  const c = plLang(code);
  return ({ tr: "Türkçe", en: "English", ja: "日本語", de: "Deutsch", fr: "Français", es: "Español", it: "Italiano", ru: "Русский", ar: "العربية", ko: "한국어", zh: "中文", pt: "Português" })[c] || (code || "");
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
  if (PL.cues2 && PL.cues2.length) {
    const b2 = $("#plSubs2");
    const h2 = PL.cues2.filter((c) => t >= c.s && t <= c.e).map((c) => `<span>${escapeHtml(c.text.replace(/<[^>]+>/g, "")).replace(/\n/g, "<br>")}</span>`).join("<br>");
    if (b2.dataset.h !== h2) { b2.innerHTML = h2; b2.dataset.h = h2; }
  }
  const box = $("#plSubs");
  const html = PL.cues.filter((c) => t >= c.s && t <= c.e)
    .map((c) => `<span>${plSubWords(c.text.replace(/<[^>]+>/g, ""))}</span>`).join("<br>");
  if (box.dataset.h !== html) { box.innerHTML = html; box.dataset.h = html; }
}

// ---------- sozluk: altyazida kelimeye tikla (B6) ----------
// Kelimeler ayri span (.w); bosluksuz yazilarda (Japonca/Cince) her karakter span, sunucu en uzun eslesmeyi bulur.
const PL_CJK = /[぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ]/;
function plSubWords(text) {
  if (plCfg().dictClick === false) return escapeHtml(text).replace(/\n/g, "<br>");   // sozluk modu kapali: duz yazi
  return text.split("\n").map((ln) => {
    let out = "", i = 0;
    for (const m of ln.matchAll(/[\p{L}\p{M}\p{N}'’\-]+/gu)) {
      out += escapeHtml(ln.slice(i, m.index));
      const w = m[0];
      if (PL_CJK.test(w)) {
        out += [...w].map((ch, k) => `<span class="w" data-l="${escapeHtml(ln)}" data-p="${m.index + k}">${escapeHtml(ch)}</span>`).join("");
      } else out += `<span class="w">${escapeHtml(w)}</span>`;
      i = m.index + w.length;
    }
    return out + escapeHtml(ln.slice(i));
  }).join("<br>");
}
function plSubLang() {
  const it = PL.subList?.[PL.subIdx];
  return (it && (it.lang || plLang(it.label || ""))) || "";
}
async function plDictOpen(el, forceLang) {
  const v = $("#plVideo");
  if (!v.paused) { v.pause(); PL.dictResume = true; }
  document.querySelectorAll("#plSubs .w.on, #plOcr .w.on").forEach((x) => x.classList.remove("on"));
  el.classList.add("on");
  let p = $("#plDict");
  if (!p) {
    p = document.createElement("aside");
    p.id = "plDict"; p.className = "pl-dict";
    $("#player").appendChild(p);
    p.addEventListener("click", (e) => e.stopPropagation());
    p.addEventListener("dblclick", (e) => e.stopPropagation());
  }
  p.hidden = false;
  const lang = forceLang != null ? forceLang : plSubLang();
  const isCjk = el.dataset.p != null;
  p.innerHTML = `<div class="pd-head"><b>${escapeHtml(el.textContent)}</b><button class="pd-x" title="${plL("Kapat", "Close")}">✕</button></div><div class="pd-body">${plL("Aranıyor…", "Looking up…")}</div>`;
  p.querySelector(".pd-x").onclick = plDictClose;
  let r;
  try {
    r = await api.dict_lookup(el.textContent, lang, isCjk ? el.dataset.l : "", isCjk ? +el.dataset.p : -1);
  } catch (e) { r = { ok: false, error: String(e) }; }
  if (isCjk && r?.word) {   // eslesen uzunlugu altyazida da isaretle
    const start = +el.dataset.p, n = [...r.word].length;
    el.parentElement.querySelectorAll(".w[data-p]").forEach((x) => { const k = +x.dataset.p; if (x.dataset.l === el.dataset.l && k >= start && k < start + n) x.classList.add("on"); });
  }
  plDictRender(p, r, lang);
}
function plDictRender(p, r, lang) {
  const body = p.querySelector(".pd-body");
  if (r?.word) p.querySelector(".pd-head b").textContent = r.word;
  const q = encodeURIComponent(r?.word || "");
  const links = `<div class="pd-links"><a href="#" data-u="https://translate.google.com/?sl=${lang || "auto"}&tl=tr&text=${q}">Google Çeviri</a> · <a href="#" data-u="https://en.wiktionary.org/wiki/${q}">Wiktionary</a>${lang === "ja" ? ` · <a href="#" data-u="https://jisho.org/search/${q}">Jisho</a>` : ""}</div>`;
  if (!r?.installed) {
    body.innerHTML = `<p class="pd-note">${plL("Sözlük henüz kurulu değil. Bir kez indirilir, sonra çevrimdışı çalışır.", "Dictionary not installed yet. Downloaded once, then works offline.")}</p><div class="pd-packs"></div>` + links;
    plDictPacks(body.querySelector(".pd-packs"));
  } else if (!r.ok || !r.entries?.length) {
    body.innerHTML = `<p class="pd-note">${r?.error ? escapeHtml(r.error) : plL("Sözlükte bulunamadı.", "Not found in the dictionary.")}</p><div class="pd-packs"></div>` + links;
    plDictPacks(body.querySelector(".pd-packs"), true);
  } else {
    body.innerHTML = r.entries.map((e) => `<div class="pd-e"><div class="pd-meta">${e.word !== r.word ? `<b>${escapeHtml(e.word)}</b> ` : ""}<i>${escapeHtml(e.pos || "")}</i> <span class="pd-lg">${escapeHtml(plLangName(e.lang) || e.lang)}</span>${e.ipa ? ` <span class="pd-ipa">${escapeHtml(e.ipa)}</span>` : ""}<span class="pd-src">${e.src === "tr" ? "TR" : "EN"}</span></div><ol>${e.glosses.map((g) => `<li>${escapeHtml(g)}</li>`).join("")}</ol></div>`).join("") + links;
  }
  body.querySelectorAll("a[data-u]").forEach((a) => a.onclick = (ev) => { ev.preventDefault(); api.open_link(a.dataset.u); });
}
async function plDictPacks(box, onlyMissing = false) {
  let st;
  try { st = await api.dict_status(); } catch { return; }
  const html = Object.entries(st.packs).filter(([, v]) => !(onlyMissing && v.done)).map(([k, v]) => {
    const pr = st.progress[k];
    const run = pr?.state === "running";
    const lab = v.done ? plL("kurulu", "installed") : run ? `${Math.round((pr.p || 0) * 100)}% · ${escapeHtml(pr.msg || "")}` : pr?.state === "error" ? plL("hata: ", "error: ") + escapeHtml(pr.msg || "") : `${v.size_mb >= 1000 ? (v.size_mb / 1000).toFixed(1) + " GB" : v.size_mb + " MB"}`;
    return `<div class="pd-pack"><span>${escapeHtml(v.name)}<small>${lab}</small></span>${v.done || run ? "" : `<button data-k="${k}">${plL("İndir", "Download")}</button>`}</div>`;
  }).join("");
  box.innerHTML = html;
  box.querySelectorAll("button[data-k]").forEach((b) => b.onclick = async () => { b.disabled = true; await api.dict_install(b.dataset.k); plDictPacks(box, onlyMissing); });
  if (Object.values(st.progress).some((x) => x.state === "running")) {
    clearTimeout(PL.dictT);
    PL.dictT = setTimeout(() => { if (box.isConnected && !$("#plDict")?.hidden) plDictPacks(box, onlyMissing); }, 1500);
  }
}
function plDictClose() {
  const p = $("#plDict");
  if (!p || p.hidden) return false;
  p.hidden = true;
  document.querySelectorAll("#plSubs .w.on").forEach((x) => x.classList.remove("on"));
  if (PL.dictResume) { PL.dictResume = false; const v = $("#plVideo"); v.play().catch(() => {}); }
  return true;
}
document.addEventListener("click", (e) => {
  const w = e.target.closest?.("#plSubs .w");
  if (!w) return;
  e.stopPropagation(); e.preventDefault();
  plDictOpen(w);
}, true);
document.addEventListener("dblclick", (e) => { if (e.target.closest?.("#plSubs .w")) { e.stopPropagation(); e.preventDefault(); } }, true);

// ---------- ekran ustu OCR (B6): kareyi dondur, bolge sec, yaziyi oku + cevir ----------
function plOcrStart() {
  const v = $("#plVideo");
  if (!PL.open || !v.videoWidth) { toast(plL("Önce bir video aç", "Open a video first"), true); return; }
  plOcrClose();
  if (!v.paused) { v.pause(); PL.ocrResume = true; }
  const ov = document.createElement("div");
  ov.id = "plOcr"; ov.className = "pl-ocr";
  ov.innerHTML = `<div class="po-hint">${plL("Okunacak yazının çevresini sürükleyerek seç · Esc: vazgeç", "Drag around the text to read · Esc: cancel")}</div><div class="po-box" hidden></div>`;
  $("#player").appendChild(ov);
  const box = ov.querySelector(".po-box");
  let x0 = 0, y0 = 0, drag = false;
  const stop = (e) => { e.stopPropagation(); e.preventDefault(); };
  ov.addEventListener("click", stop); ov.addEventListener("dblclick", stop);
  ov.addEventListener("pointerdown", (e) => {
    if (e.target.closest(".po-res")) return;
    stop(e); ov.setPointerCapture(e.pointerId); drag = true;
    const r = ov.getBoundingClientRect(); x0 = e.clientX - r.left; y0 = e.clientY - r.top;
    Object.assign(box.style, { left: x0 + "px", top: y0 + "px", width: "0px", height: "0px" }); box.hidden = false;
    ov.querySelector(".po-res")?.remove();
  });
  ov.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const r = ov.getBoundingClientRect(), x = e.clientX - r.left, y = e.clientY - r.top;
    Object.assign(box.style, { left: Math.min(x, x0) + "px", top: Math.min(y, y0) + "px", width: Math.abs(x - x0) + "px", height: Math.abs(y - y0) + "px" });
  });
  ov.addEventListener("pointerup", (e) => {
    if (!drag) return;
    drag = false; stop(e);
    const b = box.getBoundingClientRect();
    if (b.width < 12 || b.height < 8) { box.hidden = true; return; }
    plOcrRun(b);
  });
}
function plOcrCrop(b) {
  // ekrandaki secimi videonun gercek piksellerine cevir (object-fit: contain kenar bosluklari dahil)
  const v = $("#plVideo"), vr = v.getBoundingClientRect();
  const sc = Math.min(vr.width / v.videoWidth, vr.height / v.videoHeight);
  const ox = vr.left + (vr.width - v.videoWidth * sc) / 2, oy = vr.top + (vr.height - v.videoHeight * sc) / 2;
  const sx = Math.max(0, (b.left - ox) / sc), sy = Math.max(0, (b.top - oy) / sc);
  const sw = Math.min(v.videoWidth - sx, b.width / sc), sh = Math.min(v.videoHeight - sy, b.height / sc);
  if (sw < 4 || sh < 4) return "";
  const up = Math.max(1, Math.min(3, 64 / sh * 1.2));   // kucuk yazi: buyut (Windows OCR kucuk harfte zayif)
  const c = document.createElement("canvas");
  c.width = Math.round(sw * up); c.height = Math.round(sh * up);
  const g = c.getContext("2d");
  g.imageSmoothingQuality = "high";
  g.drawImage(v, sx, sy, sw, sh, 0, 0, c.width, c.height);
  try { return c.toDataURL("image/png"); } catch { return ""; }
}
async function plOcrRun(b) {
  const ov = $("#plOcr");
  if (!ov) return;
  const img = plOcrCrop(b);
  const res = document.createElement("div");
  res.className = "po-res";
  const r0 = ov.getBoundingClientRect();
  const below = b.bottom + 180 < r0.bottom;
  Object.assign(res.style, { left: Math.max(12, Math.min(b.left - r0.left, r0.width - 432)) + "px", [below ? "top" : "bottom"]: (below ? b.bottom - r0.top + 10 : r0.bottom - b.top + 10) + "px" });
  res.innerHTML = `<div class="po-txt">${plL("Okunuyor…", "Reading…")}</div>`;
  ov.appendChild(res);
  ["pointerdown", "click", "dblclick"].forEach((ev) => res.addEventListener(ev, (e) => e.stopPropagation()));
  if (!img) { res.querySelector(".po-txt").textContent = plL("Kare alınamadı.", "Could not grab the frame."); return; }
  const lang = plCfg().ocrLang && plCfg().ocrLang !== "auto" ? plCfg().ocrLang : "";
  let r;
  try { r = await slow("ocr_image", img, lang); } catch (e) { r = { ok: false, error: String(e) }; }
  if (!res.isConnected) return;
  if (!r?.ok) { res.querySelector(".po-txt").textContent = plL("Okunamadı: ", "OCR failed: ") + (r?.error || "?"); return; }
  if (!r.text) {
    res.querySelector(".po-txt").textContent = plL("Yazı bulunamadı.", "No text found.") + (lang && !r.avail.some((a) => a.startsWith(lang)) ? " " + plL(`Bu dil (${plLangName(lang) || lang}) için Windows OCR paketi yok: Ayarlar › Saat ve dil › Dil › dili ekle.`, `No Windows OCR pack for ${lang}: Settings › Time & language › Language.`) : "");
    return;
  }
  const ocrLang = plTextLang(r.text, (r.lang || "").split("-")[0]);
  res.innerHTML = `<div class="po-txt pl-subs-like">${plSubWords(r.text)}</div><div class="po-tr">${plL("Çevriliyor…", "Translating…")}</div><div class="po-act"><button data-a="copy">${plL("Kopyala", "Copy")}</button><button data-a="again">${plL("Yeni seçim", "New selection")}</button><button data-a="close">${plL("Kapat", "Close")}</button></div>`;
  res.querySelectorAll(".po-txt .w").forEach((w) => w.addEventListener("click", (e) => { e.stopPropagation(); plDictOpen(w, ["ja", "zh", "ko"].includes(ocrLang) ? ocrLang : ""); }));
  res.querySelector("[data-a=copy]").onclick = () => { navigator.clipboard?.writeText(r.text).then(() => toast(plL("Kopyalandı", "Copied"))).catch(() => {}); };
  res.querySelector("[data-a=again]").onclick = () => { res.remove(); ov.querySelector(".po-box").hidden = true; };
  res.querySelector("[data-a=close]").onclick = () => plOcrClose();
  if (ocrLang === "tr") { res.querySelector(".po-tr").remove(); return; }
  const eng = plCfg().trEngine === "nllb" ? "nllb" : "google";
  let t;
  try { t = await slow("ocr_translate", r.text, eng === "google" ? "auto" : ocrLang, eng); } catch (e) { t = { ok: false }; }
  if (!t?.ok && eng === "nllb") { try { t = await slow("ocr_translate", r.text, "auto", "google"); } catch { t = { ok: false }; } }
  const tr = res.querySelector(".po-tr");
  if (!tr) return;
  if (t?.ok && t.text) tr.textContent = t.text; else tr.remove();   // ceviri yoksa metin cevirisiz kalir
}
// yazinin dilini yazidan tahmin et (OCR motoru Turkce profille Ingilizceyi de okur, motor dili yaniltir)
function plTextLang(text, hint = "") {
  const s = String(text || "");
  if (/[\u3040-\u30ff]/.test(s)) return "ja";
  if (/[\u3400-\u9fff]/.test(s)) return hint === "zh" ? "zh" : "ja";
  if (/[\uac00-\ud7af]/.test(s)) return "ko";
  if (/[\u0400-\u04ff]/.test(s)) return "ru";
  if (/[ğışİĞŞ]/.test(s)) return "tr";
  const w = s.toLowerCase().match(/[a-zçöüâîû]+/g) || [];
  const tr = w.filter((x) => /^(ve|bir|bu|da|de|ne|için|ile|çok|ben|sen|o|mi|mı|var|yok|gibi|ama)$/.test(x)).length;
  const en = w.filter((x) => /^(the|and|a|an|is|are|of|to|you|i|it|in|that|this|what|for|on|with|be|was|my|me)$/.test(x)).length;
  if (tr !== en) return tr > en ? "tr" : "en";
  if (/[çöü]/.test(s)) return "tr";
  return hint && hint !== "tr" ? hint : "en";   // isaret yok: Latin yazi icin Ingilizce varsay (Google zaten "auto")
}
function plCfg() { return (typeof PX !== "undefined" && PX.cfg) || {}; }
function plOcrClose() {
  const ov = $("#plOcr");
  if (!ov) return false;
  ov.remove();
  if (PL.ocrResume && $("#plDict")?.hidden !== false) { PL.ocrResume = false; $("#plVideo").play().catch(() => {}); }
  PL.ocrResume = false;
  return true;
}

// ---------- klavye ----------
// eylemler (kisayollar ayarlardan degistirilebilir: localStorage kami.keys)
const PL_ACTIONS = {
  toggle: ["Oynat / duraklat", "Play / pause", () => plToggle()],
  full: ["Tam ekran", "Fullscreen", () => plFull()],
  mute: ["Sessiz", "Mute", () => { const v = $("#plVideo"); v.muted = !v.muted; plVolUi(); }],
  back5: ["5 sn geri", "Back 5 s", () => plSeek(plNow() - 5)], fwd5: ["5 sn ileri", "Forward 5 s", () => plSeek(plNow() + 5)],
  back10: ["10 sn geri", "Back 10 s", () => plSeek(plNow() - 10)], fwd10: ["10 sn ileri", "Forward 10 s", () => plSeek(plNow() + 10)],
  volup: ["Ses +", "Volume +", () => plSetVol((PL.vol ?? 1) + 0.05)], voldown: ["Ses −", "Volume −", () => plSetVol((PL.vol ?? 1) - 0.05)],
  frameback: ["Bir kare geri", "Frame back", () => plFrame(-1)], framefwd: ["Bir kare ileri", "Frame forward", () => plFrame(1)],
  slower: ["Hız −0.05", "Speed −0.05", () => plRate(-0.05)], faster: ["Hız +0.05", "Speed +0.05", () => plRate(0.05)], rate1: ["Hız 1×", "Speed 1×", () => plRate(0)],
  subs: ["Altyazı aç / kapat", "Subtitles on / off", () => { const s = $("#plSub"); if (PL.subList.length) { s.value = PL.subIdx < 0 ? String(PL.lastSub ?? 0) : "-1"; if (PL.subIdx >= 0) PL.lastSub = PL.subIdx; plLoadSub(+s.value); } }],
  subminus: ["Altyazı −0.5 sn", "Subtitles −0.5 s", () => plShift(-0.5)], subplus: ["Altyazı +0.5 sn", "Subtitles +0.5 s", () => plShift(0.5)],
  next: ["Sonraki", "Next", () => window.plQueueStep?.(1)], prev: ["Önceki", "Previous", () => window.plQueueStep?.(-1)],
  queue: ["Sıradakiler / kütüphane", "Queue / library", () => window.plDrawer?.()], settings: ["Ayarlar paneli", "Settings panel", () => window.plSettings?.()],
  info: ["Video bilgisi", "Video info", () => plInfo()],
  ocr: ["Ekrandaki yazıyı oku (OCR)", "Read on-screen text (OCR)", () => plOcrStart()],
  mini: ["Mini oynatıcı", "Mini player", () => window.plMini?.()],
  close: ["Kapat / tam ekrandan çık", "Close / exit fullscreen", () => {
    if (plOcrClose()) return;
    if (window.plMini && PL.mini) { window.plMini(false); return; }
    if (plDictClose()) return;
    if (window.plPanelClose?.()) return;
    if (PL.full) return plFull();
    if (document.fullscreenElement) return document.exitFullscreen();
    if (!window.KAMI_PLAYER_WINDOW) plClose();
  }],
};
const PL_KEYS_DEFAULT = { " ": "toggle", k: "toggle", f: "full", m: "mute", arrowleft: "back5", arrowright: "fwd5", j: "back10", l: "fwd10",
  arrowup: "volup", arrowdown: "voldown", ",": "frameback", ".": "framefwd", "[": "slower", "]": "faster", "\\": "rate1", z: "slower", x: "faster", r: "rate1", c: "subs",
  g: "subminus", h: "subplus", n: "next", p: "prev", q: "queue", s: "settings", i: "info", o: "ocr", b: "mini", escape: "close" };
function plKeymap() { try { return { ...PL_KEYS_DEFAULT, ...JSON.parse(localStorage.getItem("kami.keys") || "{}") }; } catch { return { ...PL_KEYS_DEFAULT }; } }
function plKey(e) {
  const altGr = e.getModifierState && e.getModifierState("AltGraph");
  if ((!PL.open && e.key !== "Escape") || PL.capture || e.target.matches("input:not([type=range]), textarea") || ((e.ctrlKey || e.altKey) && !altGr) || e.metaKey) return;
  const act = plKeymap()[e.key.toLowerCase()];
  if (act && PL_ACTIONS[act]) { e.preventDefault(); e.stopPropagation(); PL_ACTIONS[act][2](); plWake(); }
}
// kare kare: duraklatir, kare suresi requestVideoFrameCallback ile olculur (yoksa 1/24)
function plFrame(d) {
  const v = $("#plVideo"); v.pause();
  const t = Math.max(0, v.currentTime + d * (PL.frameDur || 1 / 24));
  v.currentTime = t;
}
function plRate(d) {
  const v = $("#plVideo");
  const r = d === 0 ? 1 : Math.max(0.25, Math.min(4, Math.round((v.playbackRate + d) * 100) / 100));
  v.playbackRate = r;
  const sel = $("#plRate");
  if (![...sel.options].some((o) => +o.value === r)) sel.insertAdjacentHTML("beforeend", `<option value="${r}">${r}×</option>`);
  sel.value = String(r);
  sel.dispatchEvent(new Event("change"));
  toast(plL("Hız ", "Speed ") + r + "×");
}
// video bilgisi: I tusu, sol ustte kucuk katman (arayuz sade kalsin diye kendiliginden acilmaz)
function plInfo() {
  let box = $("#plInfo");
  if (box) { box.remove(); clearInterval(PL.infoT); return; }
  box = document.createElement("div"); box.id = "plInfo"; box.className = "pl-info";
  $("#player").appendChild(box);
  const draw = () => {
    const v = $("#plVideo"), r = PL.info, q = v.getVideoPlaybackQuality ? v.getVideoPlaybackQuality() : null;
    const a = r.audio[PL.audio] || {};
    const br = r.size && r.duration ? Math.round((r.size * 8) / r.duration / 1000) : 0;
    const rows = [
      [plL("Mod", "Mode"), { direct: plL("doğrudan", "direct"), remux: "ffmpeg remux", transcode: plL("canlı dönüşüm", "live transcode") }[PL.mode]],
      [plL("Görüntü", "Video"), r.kind === "video" ? `${(r.vcodec || "?").toUpperCase()} · ${v.videoWidth || r.width}×${v.videoHeight || r.height}${PL.frameDur ? " · " + Math.round(1 / PL.frameDur) + " fps" : ""}` : "—"],
      [plL("Ses", "Audio"), a.codec ? `${a.codec.toUpperCase()} · ${a.channels || "?"} ${plL("kanal", "ch")}${a.lang ? " · " + a.lang : ""}` : "—"],
      [plL("Bit hızı", "Bitrate"), br ? (br > 1000 ? (br / 1000).toFixed(1) + " Mbit/s" : br + " kbit/s") : "—"],
      [plL("Hız", "Speed"), v.playbackRate + "×"],
      [plL("Düşen kare", "Dropped"), q ? `${q.droppedVideoFrames} / ${q.totalVideoFrames}` : "—"],
      [plL("Tampon", "Buffer"), v.buffered.length ? Math.max(0, v.buffered.end(v.buffered.length - 1) - v.currentTime).toFixed(1) + " sn" : "—"],
    ];
    box.innerHTML = rows.map(([k, x]) => `<div><span>${k}</span><b>${escapeHtml(String(x))}</b></div>`).join("");
  };
  draw(); PL.infoT = setInterval(draw, 1000);
}
