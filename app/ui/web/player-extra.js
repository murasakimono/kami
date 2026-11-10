// Kami Player B8/B9: intro/outro atla (AniSkip), SponsorBlock, seekbar bolumleri, izlemeye devam + izlendi,
// dizi posterleri (AniList), izlenen diziyi temizle, 10 bantli EQ, dondur/cevir, ortam isigi, ses cikar, klip, onarim.
// player.js plStart sonunda window.plExtraStart(r) cagirir.
"use strict";

const PE = { segs: [], skipped: new Set(), amb: 0, clipA: null, clipB: null };
const peCfg = () => (typeof PX !== "undefined" && PX.cfg) || {};
const peLS = (k, d) => { try { return JSON.parse(localStorage.getItem(k) || "null") ?? d; } catch { return d; } };
const peSave = (k, v) => { try { localStorage.setItem(k, JSON.stringify(v)); } catch { /* yok */ } };
const SEG_NAMES = { op: ["İntroyu atla", "Skip intro"], ed: ["Kapanışı atla", "Skip outro"], recap: ["Özeti atla", "Skip recap"],
  sponsor: ["Sponsor", "Sponsor"], selfpromo: ["Tanıtım", "Self-promo"], interaction: ["Abone ol hatırlatması", "Interaction"],
  intro: ["İntro", "Intro"], outro: ["Kapanış", "Outro"], music_offtopic: ["Müzik dışı", "Non-music"] };
const segName = (t) => plL(...(SEG_NAMES[t] || [t, t]));

window.plExtraStart = async (r) => {
  PE.segs = []; PE.skipped = new Set(); PE.clipA = PE.clipB = null;
  peDrawMarks();
  $("#plSkip")?.remove();
  peAmbient(r.kind === "video" && peCfg().ambient !== false);
  if (!r.path) return;
  let res;
  try { res = await slow("player_skips", r.path, r.duration || 0, r.tags || {}); } catch { res = null; }
  if (!res?.ok || PL.info !== r) return;
  PE.segs = res.segments || [];
  peDrawMarks();
};

// ---------- seekbar: bolumler + atlama araliklari ----------
function peDrawMarks() {
  const seek = $("#plSeek"); if (!seek) return;
  seek.querySelectorAll(".pe-mark, .pe-ch").forEach((x) => x.remove());
  const d = PL.dur || 0; if (!d) return;
  for (const s of PE.segs) {
    const m = document.createElement("i");
    m.className = "pe-mark t-" + s.type;
    m.style.left = (s.start / d * 100) + "%"; m.style.width = Math.max(0.3, (s.end - s.start) / d * 100) + "%";
    seek.appendChild(m);
  }
  for (const c of (PL.info?.chapters || []).slice(1)) {
    const m = document.createElement("i");
    m.className = "pe-ch"; m.style.left = (c.start / d * 100) + "%";
    seek.appendChild(m);
  }
}
document.addEventListener("pointermove", (e) => {   // ipucuna bolum adini ekle
  const seek = e.target.closest?.("#plSeek"); if (!seek || !PL.dur) return;
  const r = seek.getBoundingClientRect(), t = Math.max(0, Math.min(1, (e.clientX - r.left) / r.width)) * PL.dur;
  const ch = (PL.info?.chapters || []).filter((c) => c.start <= t).pop();
  const sg = PE.segs.find((s) => t >= s.start && t <= s.end);
  const extra = [ch?.title, sg ? segName(sg.type) : ""].filter(Boolean).join(" · ");
  const tt = $("#plTipT"); if (tt && extra && !tt.textContent.includes("·")) tt.textContent += " · " + extra;
});

// ---------- oynatirken: atla dugmesi, sponsor otomatik atlama, izlemeye devam / izlendi ----------
document.addEventListener("timeupdate", (e) => {
  if (e.target.id !== "plVideo" || !PL.open || !PL.info) return;
  const t = plNow(), d = PL.dur || 0, path = PL.info.path;
  // atlama
  const cur = PE.segs.find((s) => t >= s.start && t < s.end - 0.5);
  if (cur && cur.src === "sponsorblock" && peCfg().sbAuto !== false && !PE.skipped.has(cur)) {
    PE.skipped.add(cur); plSeek(cur.end, true); toast(plL("Atlandı: ", "Skipped: ") + segName(cur.type));
  }
  let b = $("#plSkip");
  if (cur && cur.src === "aniskip") {
    if (!b) {
      b = document.createElement("button"); b.id = "plSkip"; b.className = "pl-skip";
      b.addEventListener("click", (ev) => { ev.stopPropagation(); const s = b._seg; if (s) { PE.skipped.add(s); plSeek(s.end, true); } b.remove(); });
      $("#player").appendChild(b);
    }
    if (b._seg !== cur) { b._seg = cur; b.textContent = segName(cur.type) + " ›"; }
    if (peCfg().autoSkip && !PE.skipped.has(cur)) { PE.skipped.add(cur); plSeek(cur.end, true); toast(segName(cur.type)); }
  } else if (b) b.remove();
  // izlemeye devam + izlendi
  if (!path || !d || PL.info.kind !== "video") return;
  if (Math.abs(t - (PE.lastRec || 0)) < 5) return;
  PE.lastRec = t;
  const rec = peLS("kami.recent", []).filter((x) => x.p !== path);
  const done = t > d * 0.92 || t > d - 90;
  if (done) { const w = peLS("kami.watched", {}); if (!w[path]) { w[path] = Date.now(); peSave("kami.watched", w); } }
  if (!done && t > 30) rec.unshift({ p: path, t: Math.round(t), d: Math.round(d), ts: Date.now() });
  peSave("kami.recent", rec.slice(0, 30));
}, true);

// ---------- kutuphane cekmecesi: izlemeye devam rafi, izlendi isaretleri, posterler, temizle ----------
const _peRender = window.pxDrawerRender;
window.pxDrawerRender = async (...a) => {
  await _peRender(...a);
  const body = $("#pxBody"); if (!body || typeof PX === "undefined") return;
  const W = peLS("kami.watched", {});
  body.querySelectorAll(".px-row[data-play]").forEach((r) => { const p = PX.view?.[+r.dataset.play]; if (p && W[p]) r.classList.add("seen"); });
  if (PX.libTab !== "lib") return;
  if (PX.libSeries) {   // dizi sayfasi: hepsi izlendiyse temizle
    const s = PX.lib?.series?.find((x) => x.name === PX.libSeries);
    if (s && s.paths.length && s.paths.every((p) => W[p])) {
      body.insertAdjacentHTML("beforeend", `<div class="pe-clean"><span>${plL("Bu dizinin tüm bölümlerini izledin.", "You've watched every episode.")}</span><button class="pl-b" id="peTrash">🗑 ${plL("Geri Dönüşüm Kutusu'na taşı", "Move to Recycle Bin")}</button></div>`);
      $("#peTrash").onclick = async (ev) => {
        ev.stopPropagation();
        if (!confirm(plL(`"${s.name}" dizisinin ${s.paths.length} bölümü Geri Dönüşüm Kutusu'na taşınsın mı?`, `Move ${s.paths.length} episodes to the Recycle Bin?`))) return;
        const r = await api.library_trash(s.paths);
        toast(r?.ok ? plL("Taşındı (geri alınabilir)", "Moved (can be restored)") : plL("Taşınamadı", "Couldn't move"), !r?.ok);
        if (r?.ok) { PX.lib = null; PX.libSeries = null; window.pxDrawerRender(); }
      };
    }
    return;
  }
  // izlemeye devam rafi
  const rec = peLS("kami.recent", []).filter((x) => !W[x.p]).slice(0, 8);
  if (rec.length) {
    body.insertAdjacentHTML("afterbegin", `<h4>${plL("İzlemeye devam", "Continue watching")}</h4><div class="pe-shelf">${rec.map((x, i) => `<button class="pe-cont" data-cont="${i}"><b>${escapeHtml(pxBase(x.p))}</b><small>${fmtT(x.t)} / ${fmtT(x.d)}</small><i style="width:${Math.min(100, x.t / x.d * 100).toFixed(1)}%"></i></button>`).join("")}</div>`);
    body.querySelectorAll("[data-cont]").forEach((b) => b.onclick = (ev) => { ev.stopPropagation(); const x = rec[+b.dataset.cont]; playerOpenPath(x.p); $("#plDrawer").hidden = true; });
  }
  // dizi posterleri (AniList, onbellekli)
  const cards = [...body.querySelectorAll(".px-series[data-series]")];
  if (!cards.length) return;
  PX.posters = PX.posters || {};
  const need = cards.map((c) => c.dataset.series).filter((n) => !(n in PX.posters));
  const paint = () => cards.forEach((c) => { const p = PX.posters[c.dataset.series]; if (p?.cover) { c.style.backgroundImage = `linear-gradient(180deg, rgba(8,6,12,.1), rgba(8,6,12,.92)), url("${p.cover}")`; c.classList.add("has-poster"); } });
  paint();
  if (need.length && !PE.posterBusy) {
    PE.posterBusy = true;
    try { const r = await slow("library_posters", need); need.forEach((n) => { PX.posters[n] = r?.posters?.[n] || null; }); } catch { /* yok */ }
    PE.posterBusy = false;
    if (body.isConnected) paint();
  }
};

// ---------- 10 bantli ekolayzir ----------
const EQ_F = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
const EQ_PRESETS = { off: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0], bass: [6, 5, 4, 2, 0, 0, 0, 0, 0, 0], speech: [-4, -3, -1, 1, 3, 4, 4, 3, 1, -1],
  treble: [0, 0, 0, 0, 0, 1, 2, 4, 5, 6], vshape: [4, 3, 1, 0, -1, -1, 0, 2, 3, 4] };
function peEqBuild() {
  if (!PL.ctx || PL.eq) return;
  PL.eq = EQ_F.map((f, i) => { const b = PL.ctx.createBiquadFilter(); b.type = i === 0 ? "lowshelf" : i === 9 ? "highshelf" : "peaking"; b.frequency.value = f; b.Q.value = 1.1; return b; });
  PL.mono = PL.ctx.createGain(); PL.mono.channelCount = 1; PL.mono.channelCountMode = "explicit"; PL.mono.channelInterpretation = "speakers";
  try { PL.gain.disconnect(PL.boost); } catch { /* yok */ }
  PL.gain.connect(PL.eq[0]);
  for (let i = 0; i < 9; i++) PL.eq[i].connect(PL.eq[i + 1]);
  PL.eqOut = PL.eq[9];
  PL.eqOut.connect(PL.boost);
}
function peEqApply() {
  if (!PL.ctx) return;
  peEqBuild();
  const c = peCfg(), g = c.eqGains || EQ_PRESETS.off, t = PL.ctx.currentTime;
  PL.eq.forEach((b, i) => b.gain.setTargetAtTime(c.eqOn === false ? 0 : (g[i] || 0), t, 0.03));
  const wantMono = !!c.mono;
  if (wantMono !== !!PL.monoOn) {   // mono: tek kanala indir, iki kulaga ayni ses
    try { PL.eqOut.disconnect(); } catch { /* yok */ }
    if (wantMono) { PL.eqOut.connect(PL.mono); PL.mono.connect(PL.boost); } else { try { PL.mono.disconnect(); } catch { /* yok */ } PL.eqOut.connect(PL.boost); }
    PL.monoOn = wantMono;
  }
}
const _peAudio = window.plApplyAudio;
window.plApplyAudio = () => { _peAudio?.(); try { peEqApply(); } catch (e) { console.warn("eq", e); } };

// ---------- dondur / cevir + ortam isigi ----------
const _peVideo = window.pxApplyVideo;
window.pxApplyVideo = () => {
  _peVideo?.();
  const v = $("#plVideo"); if (!v || typeof PX === "undefined") return;
  const c = PX.cfg.vid, rot = +c.rot || 0, flip = !!c.flip;
  if (!rot && !flip) return;
  const fit = rot % 180 ? Math.min(innerWidth / innerHeight, innerHeight / innerWidth) : 1;
  v.style.transform = `${v.style.transform || ""} rotate(${rot}deg) scale(${(flip ? -1 : 1) * fit}, ${fit})`.trim();
};
function peAmbient(on) {
  clearInterval(PE.amb); PE.amb = 0;
  let a = $("#plAmb");
  if (!on) { if (a) a.hidden = true; return; }
  if (!a) { a = document.createElement("div"); a.id = "plAmb"; a.className = "pl-amb"; $("#player").prepend(a); }
  a.hidden = false;
  const c = document.createElement("canvas"); c.width = 16; c.height = 9;
  const g = c.getContext("2d", { willReadFrequently: true });
  const avg = (d, idx) => { let r = 0, gg = 0, b = 0; for (const i of idx) { r += d[i * 4]; gg += d[i * 4 + 1]; b += d[i * 4 + 2]; } const n = idx.length; return `${r / n | 0},${gg / n | 0},${b / n | 0}`; };
  const L = [], R = [], T = [], B = [];
  for (let y = 0; y < 9; y++) { L.push(y * 16, y * 16 + 1); R.push(y * 16 + 14, y * 16 + 15); }
  for (let x = 0; x < 16; x++) { T.push(x, 16 + x); B.push(7 * 16 + x, 8 * 16 + x); }
  PE.amb = setInterval(() => {
    const v = $("#plVideo");
    if (!PL.open || v.paused || !v.videoWidth || PL.mini) return;
    try {
      g.drawImage(v, 0, 0, 16, 9);
      const d = g.getImageData(0, 0, 16, 9).data;
      a.style.setProperty("--al", avg(d, L)); a.style.setProperty("--ar", avg(d, R));
      a.style.setProperty("--at", avg(d, T)); a.style.setProperty("--ab", avg(d, B));
    } catch { clearInterval(PE.amb); }
  }, 280);
}

// ---------- ayarlar paneline eklenen bolumler (player-lib plSettings cagirir) ----------
const peSeg = (key, opts, cur) => `<div class="px-xseg" data-x="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${String(cur) === String(v) ? "on" : ""}">${l}</button>`).join("")}</div>`;
window.pxExtraVideoHtml = () => {
  const c = PX.cfg;
  return `<div class="px-shift"><span>${plL("Döndür / çevir", "Rotate / flip")}</span></div>
    ${peSeg("rot", [[0, "0°"], [90, "90°"], [180, "180°"], [270, "270°"]], c.vid.rot || 0)}
    ${peSeg("flip", [[0, plL("Normal", "Normal")], [1, plL("Ayna", "Mirror")]], c.vid.flip ? 1 : 0)}
    <div class="px-shift"><span>${plL("Ortam ışığı (görüntünün kenar renkleri)", "Ambient light (edge colors)")}</span></div>
    ${peSeg("ambient", [[0, plL("Kapalı", "Off")], [1, plL("Açık", "On")]], c.ambient === false ? 0 : 1)}`;
};
window.pxExtraAudioHtml = () => {
  const c = PX.cfg, g = c.eqGains || EQ_PRESETS.off;
  return `<div class="px-shift"><span>${plL("Ekolayzır", "Equalizer")}</span></div>
    ${peSeg("eqp", [["off", plL("Düz", "Flat")], ["bass", plL("Bas", "Bass")], ["speech", plL("Konuşma", "Speech")], ["treble", plL("Tiz", "Treble")], ["vshape", "V"]], c.eqPreset || "off")}
    <div class="pe-eq">${EQ_F.map((f, i) => `<label><input type="range" min="-12" max="12" step="1" value="${g[i] || 0}" data-xeq="${i}" orient="vertical"><small>${f >= 1000 ? f / 1000 + "k" : f}</small></label>`).join("")}</div>
    ${peSeg("mono", [[0, "Stereo"], [1, "Mono"]], c.mono ? 1 : 0)}
    <div class="px-shift"><span>${plL("İntro / kapanış", "Intro / outro")}</span></div>
    ${peSeg("autoSkip", [[0, plL("Düğme göster", "Show button")], [1, plL("Otomatik atla", "Auto skip")]], c.autoSkip ? 1 : 0)}
    ${peSeg("sbAuto", [[1, plL("Sponsorları atla", "Skip sponsors")], [0, plL("Atlama", "Don't skip")]], c.sbAuto === false ? 0 : 1)}`;
};
window.pxExtraToolsHtml = () => `<h4>${plL("Araçlar", "Tools")}</h4>
    <div class="px-shift"><span>${plL("Klip", "Clip")} <b id="peClipLbl">${peClipLbl()}</b></span><button class="pl-b" data-xa="ca">[ ${plL("baş", "in")}</button><button class="pl-b" data-xa="cb">${plL("son", "out")} ]</button></div>
    <div class="px-shift"><button class="pl-b" data-xa="copy">${plL("Kayıpsız kaydet", "Save lossless")}</button><button class="pl-b" data-xa="gif">GIF</button><button class="pl-b" data-xa="discord">${plL("Discord'a sığdır", "Fit for Discord")}</button></div>
    <p class="px-hint">${plL("Kayıpsız: anahtar kareden keser, kaliteyi bozmaz. Discord: 10 MB altına sıkıştırır. Dosyalar videonun yanına kaydedilir.", "Lossless cuts at keyframes. Discord compresses under 10 MB. Saved next to the video.")}</p>
    <div class="px-shift"><input class="px-in" id="peLyrQ" placeholder="${plL("Sözden şarkı bul: aklındaki satırı yaz", "Find a song from a lyric line")}" style="flex:1"><button class="pl-b" data-xa="lyrq">${plL("Ara", "Search")}</button></div><div id="peLyrRes"></div>
    <div class="px-shift"><button class="pl-b" data-xa="audio">${plL("Sesi çıkar", "Extract audio")}</button><button class="pl-b" data-xa="repair">${plL("Bozuk dosyayı onar", "Repair file")}</button></div>`;
function peClipLbl() { return PE.clipA == null && PE.clipB == null ? "" : `${PE.clipA != null ? fmtT(PE.clipA) : "…"} → ${PE.clipB != null ? fmtT(PE.clipB) : "…"}`; }

document.addEventListener("click", async (e) => {
  const p = e.target.closest?.("#plPanel"); if (!p) return;
  const b = e.target.closest("button"); if (!b) return;
  const seg = b.closest(".px-xseg");
  if (seg) {
    e.stopPropagation();
    const k = seg.dataset.x, v = b.dataset.v, c = PX.cfg;
    seg.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
    if (k === "rot") c.vid.rot = +v; else if (k === "flip") c.vid.flip = v === "1";
    else if (k === "ambient") { c.ambient = v === "1"; peAmbient(c.ambient && PL.info?.kind === "video"); }
    else if (k === "eqp") { c.eqPreset = v; c.eqGains = EQ_PRESETS[v].slice(); p.querySelectorAll("[data-xeq]").forEach((r) => { r.value = c.eqGains[+r.dataset.xeq]; }); }
    else if (k === "mono") c.mono = v === "1"; else if (k === "autoSkip") c.autoSkip = v === "1"; else if (k === "sbAuto") c.sbAuto = v === "1";
    pxSave(); window.pxApplyVideo(); window.plApplyAudio();
    return;
  }
  const act = b.dataset.xa; if (!act) return;
  e.stopPropagation();
  if (act === "lyrq") {
    const q = ($("#peLyrQ")?.value || "").trim(); if (q.length < 4) return;
    const box = $("#peLyrRes"); box.innerHTML = `<p class="px-hint">${plL("Aranıyor…", "Searching…")}</p>`;
    let r; try { r = await slow("lyrics_search", q); } catch { r = null; }
    const hits = r?.hits || [];
    box.innerHTML = hits.length ? hits.map((h, i) => `<button class="px-row" data-lh="${i}"><span>${escapeHtml(h.artist)} — ${escapeHtml(h.title)}<small> ${h.local ? "· " + plL("kütüphanende", "in library") : "· YouTube"}</small></span></button>`).join("") : `<p class="px-hint">${plL("Bulunamadı.", "Not found.")}</p>`;
    box.querySelectorAll("[data-lh]").forEach((x) => x.onclick = (ev) => { ev.stopPropagation(); const h = hits[+x.dataset.lh]; if (h.local) playerOpenPath(h.local); else api.open_link("https://www.youtube.com/results?search_query=" + encodeURIComponent(h.artist + " " + h.title)); });
    return;
  }
  const path = PL.info?.path;
  if (!path) { toast(plL("Bu işlem için yerel bir dosya açık olmalı", "Needs a local file"), true); return; }
  if (act === "ca" || act === "cb") { PE[act === "ca" ? "clipA" : "clipB"] = plNow(); const l = $("#peClipLbl"); if (l) l.textContent = peClipLbl(); return; }
  let r;
  if (["copy", "gif", "discord"].includes(act)) {
    const a = PE.clipA ?? 0, z = PE.clipB ?? PL.dur;
    if (!(z > a)) { toast(plL("Önce klibin başını ve sonunu işaretle", "Mark clip in and out first"), true); return; }
    if (act === "gif" && z - a > 30) { toast(plL("GIF için en fazla 30 sn seç", "Keep GIFs under 30 s"), true); return; }
    toast(plL("Klip hazırlanıyor…", "Making clip…"));
    r = await slow("media_clip", path, a, z, act);
  } else if (act === "audio") {
    toast(plL("Ses çıkarılıyor…", "Extracting audio…"));
    r = await slow("media_extract_audio", path, PL.info.audio?.[PL.audio || 0]?.codec || "");
  } else if (act === "repair") {
    if (!confirm(plL("Dosya hatalar yok sayılarak yeniden paketlenecek; orijinale dokunulmaz, yanına \"(onarildi)\" adıyla yazılır. Devam?", "Repack ignoring errors into a new file next to it?"))) return;
    toast(plL("Onarılıyor…", "Repairing…"));
    r = await slow("media_repair", path);
  }
  if (r?.ok) { toast(plL("Kaydedildi: ", "Saved: ") + String(r.path).split(/[\\/]/).pop()); try { api.open_path?.(r.path.replace(/[\\/][^\\/]*$/, "")); } catch { /* yok */ } }
  else toast(plL("Olmadı: ", "Failed: ") + (r?.error || "?"), true);
}, true);
document.addEventListener("input", (e) => {
  const r = e.target.closest?.("[data-xeq]"); if (!r) return;
  const c = PX.cfg; c.eqGains = (c.eqGains || EQ_PRESETS.off).slice(); c.eqGains[+r.dataset.xeq] = +r.value; c.eqPreset = "custom";
  document.querySelectorAll('.px-xseg[data-x="eqp"] button').forEach((x) => x.classList.remove("on"));
  pxSave(); window.plApplyAudio();
}, true);

// ---------- B13 cokme kurtarma: oturum temiz kapanmadiysa son dosyaya devam teklifi ----------
document.addEventListener("timeupdate", (e) => {
  if (e.target.id !== "plVideo" || !PL.open || !PL.info?.path) return;
  if (Math.abs(plNow() - (PE.lastSess || 0)) < 5) return;
  PE.lastSess = plNow();
  peSave("kami.last", { p: PL.info.path, t: Math.round(plNow()), ts: Date.now() }); peSave("kami.clean", 0);
}, true);
window.addEventListener("beforeunload", () => peSave("kami.clean", 1));
setTimeout(() => {
  const last = peLS("kami.last", null);
  if (peLS("kami.clean", 1) !== 0 || !last?.p || PL.open) return;
  peSave("kami.clean", 1);
  const chip = document.createElement("button");
  chip.className = "pl-chip pe-crash";
  chip.textContent = plL(`Son oturum beklenmedik kapandı · ${pxBase(last.p)} ${fmtT(last.t)}'den devam et`, `Last session closed unexpectedly · resume ${pxBase(last.p)} at ${fmtT(last.t)}`);
  chip.onclick = () => { chip.remove(); playerOpenPath(last.p); };
  document.body.appendChild(chip);
  setTimeout(() => chip.remove(), 15000);
}, 1500);
// ---------- B9 kinetik altyazi: ses genligi esigi asinca (bagirma/patlama) altyazi titrer, dusunce durur ----------
(function peKinetic() {
  const buf = new Uint8Array(1024);
  let avg = 0.05;
  const loop = () => {
    requestAnimationFrame(loop);
    const b = $("#plSubs");
    if (!b) return;
    if (!peCfg().kinetic || !PL.an || !PL.open || $("#plVideo").paused) { b.classList.remove("shake"); return; }
    PL.an.getByteTimeDomainData(buf);
    let sum = 0; for (let i = 0; i < buf.length; i++) { const x = (buf[i] - 128) / 128; sum += x * x; }
    const rms = Math.sqrt(sum / buf.length);
    avg = avg * 0.995 + rms * 0.005;   // ortalama ses duzeyi (sessiz/gurultulu filmlere uyum)
    const loud = rms > Math.max(0.22, avg * 2.6);
    b.classList.toggle("shake", loud);
    if (loud) b.style.setProperty("--shk", Math.min(1, (rms - avg) * 3).toFixed(2));
  };
  requestAnimationFrame(loop);
})();
const _peVid = window.pxExtraVideoHtml;
window.pxExtraVideoHtml = () => _peVid() + `<div class="px-shift"><span>${plL("Kinetik altyazı (yüksek seste titrer)", "Kinetic subtitles")}</span></div>${peSeg("kinetic", [[0, plL("Kapalı", "Off")], [1, plL("Açık", "On")]], peCfg().kinetic ? 1 : 0)}`;
document.addEventListener("click", (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="kinetic"]'); const b = e.target.closest?.("button");
  if (seg && b) { PX.cfg.kinetic = b.dataset.v === "1"; pxSave(); }
}, true);
