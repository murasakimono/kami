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
  a4kStop();
  PE.segs = []; PE.skipped = new Set(); PE.clipA = PE.clipB = null;
  peDrawMarks();
  $("#plSkip")?.remove();
  peAmbient(r.kind === "video" && peCfg().ambient !== false);
  if (!r.path) { if (r.kind === "video" && a4kWanted(r)) a4kStart(true); return; }
  let res;
  try { res = await slow("player_skips", r.path, r.duration || 0, r.tags || {}); } catch { res = null; }
  if (!res?.ok || PL.info !== r) return;
  PE.segs = res.segments || [];
  peDrawMarks();
  peAfterInfo(r);
};
function peAfterInfo(r) {
  if (PL.info !== r || r.kind !== "video") return;
  if (a4kWanted(r)) a4kStart(true);
  peAutoSub(r);
}

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
        if (!await kAsk(plL(`"${s.name}" dizisinin ${s.paths.length} bölümü Geri Dönüşüm Kutusu'na taşınsın mı?`, `Move ${s.paths.length} episodes to the Recycle Bin?`))) return;
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
    if (!await kAsk(plL("Dosya hatalar yok sayılarak yeniden paketlenecek; orijinale dokunulmaz, yanına \"(onarildi)\" adıyla yazılır. Devam?", "Repack ignoring errors into a new file next to it?"))) return;
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
// ---------- B9 kinetik altyazi: sese gore dinamik tipografi ----------
// fisilti: ince + kucuk; normal: standart; bagirma/patlama: titreme + agresif font (extreme-loud) + neon golge patlamasi.
// rAF icinde yalnizca CSS degiskenleri ve tek bir sinif degisir (yeniden cizim yok).
(function peKinetic() {
  const buf = new Uint8Array(1024), fb = new Uint8Array(256);
  let avg = 0.05, sm = 0, on = false, bassAvg = 0.2, vocAvg = 0.2, glitchUntil = 0;
  const loop = () => {
    requestAnimationFrame(loop);
    const b = $("#plSubs");
    if (!b) return;
    const act = peCfg().kinetic && PL.an && PL.open && !$("#plVideo").paused;
    if (!act) { if (on) { on = false; b.classList.remove("kinetic", "shake", "extreme-loud", "glitch"); $("#player")?.style.setProperty("--sub-bass", "0"); } return; }
    if (!on) { on = true; b.classList.add("kinetic"); }
    PL.an.getByteTimeDomainData(buf);
    let sum = 0; for (let i = 0; i < buf.length; i++) { const x = (buf[i] - 128) / 128; sum += x * x; }
    const rms = Math.sqrt(sum / buf.length);
    avg = avg * 0.995 + rms * 0.005;
    sm = sm * 0.7 + rms * 0.3;                       // titremeyi onlemek icin yumusatilmis genlik
    const rel = avg > 0.002 ? sm / avg : 1;          // filmin ortalama sesine gore (0.3 fisilti .. 1 normal .. 2.6+ bagirma)
    const loud = rms > Math.max(0.22, avg * 2.6);
    const k = Math.max(0, Math.min(1, (rel - 0.35) / 0.65));   // 0 fisilti -> 1 normal
    b.style.setProperty("--sub-weight", String(Math.round(300 + 200 * k + (loud ? 300 : 0))));
    b.style.setProperty("--sub-scale", (0.95 + 0.05 * k + (loud ? 0.06 : 0)).toFixed(3));
    b.style.setProperty("--sub-glow", Math.min(48, Math.max(0, (rel - 1) * 14)).toFixed(1));
    b.style.setProperty("--shk", Math.min(1, (rms - avg) * 3).toFixed(2));
    // muzik: bas vurusu -> mor ambilight, vokal yukselisi -> kisa glitch (altyazi/soz ekolayzir gibi)
    PL.an.getByteFrequencyData(fb);
    const hz = (PL.ctx?.sampleRate || 48000) / 2 / fb.length;
    let bs = 0, bn = 0, vs = 0, vn = 0;
    for (let i = 0; i < fb.length; i++) { const f = i * hz; if (f < 160) { bs += fb[i]; bn++; } else if (f > 300 && f < 3400) { vs += fb[i]; vn++; } }
    const bass = bn ? bs / bn / 255 : 0, voc = vn ? vs / vn / 255 : 0;
    bassAvg = bassAvg * 0.98 + bass * 0.02; vocAvg = vocAvg * 0.985 + voc * 0.015;
    const kick = Math.max(0, Math.min(1, (bass - bassAvg * 1.05) * 4));
    $("#player").style.setProperty("--sub-bass", kick.toFixed(2));
    const now = performance.now();
    if (voc > 0.3 && voc > vocAvg * 1.32 && now > glitchUntil + 250) glitchUntil = now + 140;
    b.classList.toggle("glitch", now < glitchUntil && !loud);
    b.classList.toggle("shake", loud);
    b.classList.toggle("extreme-loud", loud);
    if (loud) b.classList.toggle("trch", /[ıİşŞğĞçÇöÖüÜ]/.test(b.textContent));   // Damnation'da Turkce harf yok: Rubik Glitch'e dus
  };
  requestAnimationFrame(loop);
})();
const _peVid = window.pxExtraVideoHtml;
window.pxExtraVideoHtml = () => _peVid() + `<div class="px-shift"><span>${plL("Kinetik altyazı (sese göre kalınlık, bağırmada titreme, basla parlama, vokalde glitch)", "Kinetic subtitles")}</span></div>${peSeg("kinetic", [[0, plL("Kapalı", "Off")], [1, plL("Açık", "On")]], peCfg().kinetic ? 1 : 0)}`;
document.addEventListener("click", (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="kinetic"]'); const b = e.target.closest?.("button");
  if (seg && b) { PX.cfg.kinetic = b.dataset.v === "1"; pxSave(); }
}, true);

// ---------- Anime4K (WebGPU): 720p ve alti animede otomatik, U tusu, Hafif / Dengeli / Guclu ----------
const A4 = { on: false, dev: null, canvas: null, loading: null };
const a4kLib = () => window["anime4k-webgpu"];
function a4kLooksAnime(r) {
  const n = String(r.path || r.title || "");
  return /\[[^\]]{2,}\]/.test(n.split(/[\\/]/).pop()) || (PL.subList || []).some((x) => x.raw) || PE.segs.some((s) => s.src === "aniskip");
}
function a4kWanted(r) {
  const m = peCfg().a4k || "auto";
  if (m === "on") return true;
  if (m === "off") return false;
  return (r.height || 0) > 0 && r.height <= 720 && a4kLooksAnime(r);
}
function a4kLoad() {
  if (a4kLib()) return Promise.resolve();
  if (!A4.loading) A4.loading = new Promise((ok, bad) => { const sc = document.createElement("script"); sc.src = "vendor/anime4k/anime4k.js"; sc.onload = ok; sc.onerror = bad; document.head.appendChild(sc); });
  return A4.loading;
}
function a4kRect() {
  const v = $("#plVideo"), r = v.getBoundingClientRect(), p = $("#player").getBoundingClientRect();
  const sc = Math.min(r.width / v.videoWidth, r.height / v.videoHeight);
  const w = v.videoWidth * sc, h = v.videoHeight * sc;
  return { x: r.left - p.left + (r.width - w) / 2, y: r.top - p.top + (r.height - h) / 2, w, h };
}
function a4kPlace() {
  if (!A4.canvas) return;
  const b = a4kRect();
  Object.assign(A4.canvas.style, { left: b.x + "px", top: b.y + "px", width: b.w + "px", height: b.h + "px" });
}
async function a4kStart(auto = false) {
  const v = $("#plVideo");
  if (A4.on || !PL.open || PL.info?.kind !== "video") return;
  if (!navigator.gpu) { if (!auto) toast(plL("Anime4K için WebGPU desteklenmiyor", "WebGPU not supported"), true); return; }
  if (!v.videoWidth) { v.addEventListener("loadeddata", () => a4kStart(auto), { once: true }); return; }
  try { await a4kLoad(); } catch { toast(plL("Anime4K yüklenemedi", "Anime4K failed to load"), true); return; }
  const lib = a4kLib(); if (!lib) return;
  a4kStop();
  const c = document.createElement("canvas"); c.id = "plA4k"; c.className = "pl-a4k";
  v.after(c); A4.canvas = c;
  const b = a4kRect(), dpr = window.devicePixelRatio || 1;
  const q = peCfg().a4kQ || "light";
  c.width = Math.round(Math.min(b.w * dpr, v.videoWidth * (q === "light" ? 2 : 4)));
  c.height = Math.round(c.width * v.videoHeight / v.videoWidth);
  a4kPlace();
  try {
    await lib.render({
      video: v, canvas: c,
      pipelineBuilder: (device, inputTexture) => {
        A4.dev = device;
        const dims = { nativeDimensions: { width: v.videoWidth, height: v.videoHeight }, targetDimensions: { width: c.width, height: c.height } };
        if (q === "strong") return [new lib.ModeAA({ device, inputTexture, ...dims })];
        if (q === "balanced") return [new lib.ModeA({ device, inputTexture, ...dims })];
        return [new lib.CNNx2M({ device, inputTexture })];
      },
    });
    A4.on = true;
    toast(`Anime4K ${plL("açık", "on")} · ${{ light: plL("Hafif", "Light"), balanced: plL("Dengeli", "Balanced"), strong: plL("Güçlü", "Strong") }[q]}${auto ? plL(" (otomatik, U ile kapat)", " (auto, U to turn off)") : ""}`);
  } catch (e) { a4kStop(); toast("Anime4K: " + String(e?.message || e).slice(0, 80), true); }
}
function a4kStop() {
  try { A4.dev?.destroy(); } catch { /* yok */ }
  A4.dev = null; A4.on = false;
  A4.canvas?.remove(); A4.canvas = null;
}
function a4kToggle() { if (A4.on) { a4kStop(); toast(plL("Anime4K kapalı", "Anime4K off")); } else a4kStart(false); }
window.addEventListener("resize", a4kPlace);
document.addEventListener("fullscreenchange", () => setTimeout(a4kPlace, 120));
setInterval(() => { if (A4.on) a4kPlace(); }, 1000);   // pencere boyutu / tam ekran / mini gecisleri
PL_ACTIONS.a4k = ["Anime4K aç / kapat", "Anime4K on / off", () => a4kToggle()];
if (!PL_KEYS_DEFAULT.u) PL_KEYS_DEFAULT.u = "a4k";

// ---------- Kami Cinema Shader (WebGL2 Live-Action: CAS + Deband + Denoise) ----------
const CIN = { on: false, canvas: null, gl: null, prog: null, tex: null, raf: 0, uSize: null, uStr: null };
const CIN_VS = `attribute vec2 p; varying vec2 v; void main(){ v = vec2(p.x*0.5+0.5, 0.5-p.y*0.5); gl_Position = vec4(p,0.0,1.0); }`;
const CIN_FS = `precision mediump float;
uniform sampler2D uTex; uniform vec2 uSize; uniform float uStr; varying vec2 v;
vec3 samplePx(vec2 off){ return texture2D(uTex, clamp(v + off / uSize, 0.0, 1.0)).rgb; }
void main(){
  vec3 c = samplePx(vec2(0.0));
  vec3 n = samplePx(vec2(0.0,-1.0)), s = samplePx(vec2(0.0,1.0)), w = samplePx(vec2(-1.0,0.0)), e = samplePx(vec2(1.0,0.0));
  vec3 blur = (n + s + w + e + c) * 0.2;
  float diff = length(c - blur);
  // Hafif deband + denoise: cok kucuk farklari yumusat, detaylari CAS ile keskinlestir
  vec3 clean = mix(blur, c, smoothstep(0.015, 0.08, diff));
  vec3 mn = min(min(n, s), min(w, e)), mx = max(max(n, s), max(w, e));
  float amp = clamp(min(mn.g, 1.0 - mx.g) / max(mx.g, 1e-4), 0.0, 1.0);
  float k = -uStr * mix(0.10, 0.22, sqrt(amp));
  vec3 sharp = clamp((clean + (n + s + w + e) * k) / (1.0 + 4.0 * k), 0.0, 1.0);
  gl_FragColor = vec4(sharp, 1.0);
}`;
function cinPlace() {
  if (!CIN.canvas) return;
  const b = a4kRect();
  Object.assign(CIN.canvas.style, { left: b.x + "px", top: b.y + "px", width: b.w + "px", height: b.h + "px" });
}
function cinStop() {
  if (CIN.raf) cancelAnimationFrame(CIN.raf);
  CIN.raf = 0; CIN.on = false;
  CIN.canvas?.remove(); CIN.canvas = null; CIN.gl = null;
}
function cinStart() {
  const v = $("#plVideo");
  if (!PL.open || PL.info?.kind !== "video") return;
  if (!v.videoWidth) { v.addEventListener("loadeddata", cinStart, { once: true }); return; }
  if (A4.on) a4kStop();
  cinStop();
  const c = document.createElement("canvas");
  c.id = "plCinema"; c.className = "pl-a4k";
  v.after(c); CIN.canvas = c;
  c.width = v.videoWidth; c.height = v.videoHeight;
  cinPlace();
  const gl = c.getContext("webgl2") || c.getContext("webgl");
  if (!gl) { cinStop(); toast(plL("WebGL desteklenmiyor", "WebGL not supported"), true); return; }
  const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return s; };
  const pr = gl.createProgram();
  gl.attachShader(pr, sh(gl.VERTEX_SHADER, CIN_VS));
  gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, CIN_FS));
  gl.linkProgram(pr); gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf);
  gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const tex = gl.createTexture(); gl.bindTexture(gl.TEXTURE_2D, tex);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
  gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
  CIN.gl = gl; CIN.prog = pr; CIN.tex = tex;
  CIN.uSize = gl.getUniformLocation(pr, "uSize");
  CIN.uStr = gl.getUniformLocation(pr, "uStr");
  CIN.on = true;
  const draw = () => {
    if (!CIN.on || !CIN.gl) return;
    const mode = peCfg().cinema || "balanced";
    const str = mode === "strong" ? 1.35 : (mode === "light" ? 0.55 : 0.95);
    gl.viewport(0, 0, c.width, c.height);
    gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, v);
    gl.uniform2f(CIN.uSize, c.width, c.height);
    gl.uniform1f(CIN.uStr, str);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    CIN.raf = requestAnimationFrame(draw);
  };
  draw();
  toast(plL("Sinema HD (Live-Action) açık", "Cinema HD (Live-Action) on"));
}
function cinToggle() { if (CIN.on) { cinStop(); toast(plL("Sinema HD kapalı", "Cinema HD off")); } else cinStart(); }
PL_ACTIONS.cinema = ["Sinema HD aç / kapat", "Cinema HD on / off", () => cinToggle()];
window.addEventListener("resize", cinPlace);
document.addEventListener("fullscreenchange", () => setTimeout(cinPlace, 120));

const _peVid2 = window.pxExtraVideoHtml;
window.pxExtraVideoHtml = () => _peVid2() + `<div class="px-shift"><span>Anime4K (${plL("netleştirme, U tuşu", "sharpen, U key")})</span></div>
  ${peSeg("a4k", [["auto", plL("Otomatik (≤720p anime)", "Auto (≤720p anime)")], ["on", plL("Hep açık", "Always")], ["off", plL("Kapalı", "Off")]], peCfg().a4k || "auto")}
  ${peSeg("a4kQ", [["light", plL("Hafif", "Light")], ["balanced", plL("Dengeli", "Balanced")], ["strong", plL("Güçlü", "Strong")]], peCfg().a4kQ || "light")}
  <div class="px-shift"><span>${plL("Sinema HD (Live-Action CAS + Deband)", "Cinema HD (Live-Action CAS + Deband)")}</span></div>
  ${peSeg("cinema", [["off", plL("Kapalı", "Off")], ["light", plL("Hafif", "Light")], ["balanced", plL("Dengeli", "Balanced")], ["strong", plL("Güçlü", "Strong")]], peCfg().cinema || "off")}
  <p class="px-hint">${plL("Ekran kartında çalışır. Güçlü mod laptopu ısıtabilir.", "Runs on the GPU. Strong mode can heat up laptops.")}</p>`;
document.addEventListener("click", (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="a4k"], #plPanel .px-xseg[data-x="a4kQ"], #plPanel .px-xseg[data-x="cinema"]'); const b = e.target.closest?.("button");
  if (!seg || !b) return;
  PX.cfg[seg.dataset.x] = b.dataset.v; pxSave();
  if (seg.dataset.x === "a4kQ" && A4.on) { a4kStop(); a4kStart(false); }
  if (seg.dataset.x === "a4k" && PL.info) { if (a4kWanted(PL.info)) a4kStart(false); else a4kStop(); }
  if (seg.dataset.x === "cinema") { if (b.dataset.v === "off") cinStop(); else cinStart(); }
}, true);

// ---------- OpenSubtitles: Turkce altyazi yoksa bul ----------
PE.osKey = null;
async function peOsKey() { if (PE.osKey == null) { try { PE.osKey = !!(await api.opensub_status()).has_key; } catch { PE.osKey = false; } } return PE.osKey; }
function peAddSub(res) {
  const url = "data:text/vtt;charset=utf-8," + encodeURIComponent(res.vtt);
  PL.subList.push({ label: "Türkçe · OpenSubtitles", url, raw: "", lang: "tr" });
  const sel = $("#plSub");
  sel.innerHTML = `<option value="-1">${plL("Altyazı yok", "No subtitles")}</option>` + PL.subList.map((x, i) => `<option value="${i}">${escapeHtml(x.label)}</option>`).join("");
  sel.hidden = false; sel.value = String(PL.subList.length - 1); plLoadSub(PL.subList.length - 1);
  window.plCcSync?.();
  toast(plL("Türkçe altyazı indirildi", "Turkish subtitle downloaded") + (res.release ? " · " + res.release : ""));
}
const peOsErr = (e) => ({ not_found: plL("bu bölüme uyan altyazı yok", "no matching subtitle"), bad_key: plL("API anahtarı geçersiz", "invalid API key"), quota: plL("günlük indirme hakkı doldu", "daily quota reached") }[e] || e || "?");
async function peFetchSub(manual) {
  const r = PL.info; if (!r?.path) return;
  if (!(await peOsKey())) { if (manual) toast(plL("Önce Altyazı ayarlarına OpenSubtitles API anahtarını gir", "Enter your OpenSubtitles API key first"), true); return; }
  if (manual) return peSubPicker(r);
  let res; try { res = await slow("subtitle_fetch", r.path, "tr", r.title || ""); } catch { res = { ok: false }; }
  if (PL.info !== r) return;
  if (!res?.ok) { if (res?.error === "bad_key") toast(plL("Altyazı: ", "Subtitle: ") + peOsErr(res.error), true); return; }
  peAddSub(res);
}
async function peSubPicker(r) {
  const box = $("#peOsList"); if (!box) return;
  box.innerHTML = `<p class="px-hint">${plL("Aranıyor…", "Searching…")}</p>`;
  let res; try { res = await slow("subtitle_search", r.path, "tr", r.title || ""); } catch { res = { ok: false }; }
  if (PL.info !== r) return;
  if (!res?.ok) { box.innerHTML = `<p class="px-hint">${escapeHtml(peOsErr(res?.error))}</p>`; return; }
  const c = res.candidates || [], inf = res.info || {};
  const want = escapeHtml(inf.show || "") + (inf.season != null ? ` · S${String(inf.season).padStart(2, "0")}E${String(inf.episode).padStart(2, "0")}` : "");
  box.innerHTML = `<p class="px-hint">${plL("Aranan", "Looking for")}: <b>${want}</b></p>` + (c.length ? `<div class="pe-os">${c.slice(0, 5).map((x) => `<button class="pe-os-i ${x.ok ? "" : "bad"}" data-fid="${x.file_id}" title="${escapeHtml(x.release)}">
      <b>${escapeHtml(x.title || x.release)}</b><span>${escapeHtml(x.release)}</span><small>${x.ok ? "✓ " + plL("uyuyor", "matches") : "✕ " + plL("başka yapım olabilir", "may be another title")} · ${x.downloads} ${plL("indirme", "downloads")}${x.hash ? " · " + plL("dosyayla birebir", "exact file") : ""}</small></button>`).join("")}</div>` : `<p class="px-hint">${plL("Sonuç yok", "No results")}</p>`);
  box.querySelectorAll("[data-fid]").forEach((b) => b.onclick = async (e) => {
    e.stopPropagation(); box.innerHTML = `<p class="px-hint">${plL("İndiriliyor…", "Downloading…")}</p>`;
    let d; try { d = await slow("subtitle_fetch", r.path, "tr", r.title || "", +b.dataset.fid); } catch { d = { ok: false }; }
    box.innerHTML = "";
    if (d?.ok) peAddSub(d); else toast(plL("İndirilemedi: ", "Failed: ") + peOsErr(d?.error), true);
  });
}
function peAutoSub(r) {
  if (peCfg().osAuto === false || !r.path) return;
  if ((PL.subList || []).some((x) => x.lang === "tr")) return;
  peFetchSub(false);
}
window.pxExtraSubHtml = () => `<div class="px-shift"><span>${plL("Türkçe altyazı (OpenSubtitles)", "Turkish subtitles (OpenSubtitles)")}</span><button class="pl-b" data-xa="osfind">${plL("Bul", "Find")}</button></div>
  ${peSeg("osAuto", [[1, plL("Yoksa otomatik bul", "Auto when missing")], [0, plL("Sadece elle", "Manual only")]], peCfg().osAuto === false ? 0 : 1)}
  <div class="px-shift"><input class="px-in" id="peOsKey" type="password" placeholder="${plL("OpenSubtitles API anahtarı", "OpenSubtitles API key")}" style="flex:1"><button class="pl-b" data-xa="oskey">${plL("Kaydet", "Save")}</button></div>
  <p class="px-hint">${plL("Ücretsiz anahtar: opensubtitles.com/consumers. Anahtar bu bilgisayarda şifreli saklanır.", "Free key at opensubtitles.com/consumers. Stored encrypted on this PC.")}</p><div id="peOsList"></div>`;
document.addEventListener("click", async (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="osAuto"]'); const b = e.target.closest?.("button");
  if (seg && b) { PX.cfg.osAuto = b.dataset.v === "1"; pxSave(); return; }
  if (!b || !b.closest("#plPanel")) return;
  if (b.dataset.xa === "osfind") { e.stopPropagation(); peFetchSub(true); }
  if (b.dataset.xa === "oskey") { e.stopPropagation(); const k = $("#peOsKey").value.trim(); const r = await api.opensub_set_key(k); PE.osKey = !!r?.has_key; $("#peOsKey").value = ""; toast(PE.osKey ? plL("Anahtar kaydedildi", "Key saved") : plL("Anahtar silindi", "Key removed")); }
}, true);

// ---------- Bu sarki ne? (oynaticidaki sesten) ----------
const _peTools2 = window.pxExtraToolsHtml;
window.pxExtraToolsHtml = () => _peTools2() + `<div class="px-shift"><span>${plL("Bu şarkı ne? (Ctrl+Shift+S her yerde)", "What's this song? (Ctrl+Shift+S anywhere)")}</span><button class="pl-b" data-xa="song">🎵 ${plL("Dinle", "Listen")}</button></div><div id="peSongRes"></div>`;
document.addEventListener("click", async (e) => {
  const b = e.target.closest?.('#plPanel button[data-xa="song"]'); if (!b) return;
  e.stopPropagation();
  const box = $("#peSongRes"); box.innerHTML = `<p class="px-hint">${plL("Dinleniyor… (ilk seferde araç kurulur)", "Listening… (first time installs a helper)")}</p>`;
  let r; try { r = await slow("song_identify", PL.info?.path || "", plNow()); } catch { r = { ok: false }; }
  if (!r?.ok) { box.innerHTML = `<p class="px-hint">${plL("Tanınamadı", "Not recognized")}${r?.error && r.error !== "not_found" ? ": " + escapeHtml(r.error) : ""}</p>`; return; }
  const s = r.song, q = encodeURIComponent(`${s.artist} ${s.title}`);
  box.innerHTML = `<div class="pe-song">${s.cover ? `<img src="${escapeHtml(s.cover)}" alt="">` : ""}<div><b>${escapeHtml(s.title)}</b><span>${escapeHtml(s.artist)}${s.album ? " · " + escapeHtml(s.album) : ""}</span>
    <div><button class="pl-b" data-u="https://www.youtube.com/results?search_query=${q}">YouTube</button><button class="pl-b" data-u="https://open.spotify.com/search/${q}">Spotify</button></div></div></div>`;
  box.querySelectorAll("[data-u]").forEach((x) => x.onclick = (ev) => { ev.stopPropagation(); api.open_link(x.dataset.u); });
}, true);

// ---------- kutuphane: dizi bolumlerini sezon klasorlerine ayir ----------
const _peRender2 = window.pxDrawerRender;
window.pxDrawerRender = async (...a) => {
  await _peRender2(...a);
  const body = $("#pxBody"); if (!body || PX.libTab !== "lib" || !PX.libSeries) return;
  const s = PX.lib?.series?.find((x) => x.name === PX.libSeries); if (!s?.paths?.length) return;
  const back = body.querySelector(".px-back"); if (!back || body.querySelector("#peOrg")) return;
  back.insertAdjacentHTML("afterend", `<button class="pl-b" id="peOrg" style="margin:6px 0 10px">📂 ${plL("Sezon klasörlerine ayır", "Organize into season folders")}</button>`);
  $("#peOrg").onclick = async (ev) => {
    ev.stopPropagation();
    const pv = await slow("library_organize", s.paths, false);
    if (!pv?.count) { toast(plL("Zaten düzenli görünüyor", "Already organized")); return; }
    const sample = pv.moves.slice(0, 3).map((m) => "• " + m[1].split(/[\\/]/).slice(-3).join("\\")).join("\n");
    if (!await kAsk(plL(`${pv.count} dosya "Dizi / Sezon XX" düzenine taşınacak (yan altyazılar dahil):\n${sample}${pv.count > 3 ? "\n…" : ""}\n\nDevam?`, `Move ${pv.count} files into season folders?`))) return;
    const r = await slow("library_organize", s.paths, true);
    toast(plL(`${r?.count || 0} dosya taşındı`, `${r?.count || 0} files moved`));
    PX.lib = null; PX.libSeries = null; window.pxDrawerRender();
  };
};


// ---------- altyazi secici: uzun liste yerine CC dugmesi + dil rozeti ----------
function plCcSync() {
  const sel = $("#plSub"), b = $("#plCC"); if (!sel || !b) return;
  b.hidden = sel.hidden;
  const opt = sel.options[sel.selectedIndex];
  const on = sel.value !== "-1" && opt;
  const lab = on ? opt.textContent : "";
  const code = !on ? "" : /türk|turk|\btr\b/i.test(lab) ? "TR" : /ingiliz|english|\ben\b/i.test(lab) ? "EN" : /japon|japan|\bja\b/i.test(lab) ? "JA" : lab.slice(0, 2).toUpperCase();
  b.classList.toggle("on", !!on);
  b.querySelector("i").textContent = code;
  b.title = plL("Altyazı (C)", "Subtitles (C)") + (lab ? " · " + lab : "");
}
window.plCcSync = plCcSync;
function plCcInit() {
  const sel = $("#plSub"); if (!sel || $("#plCC")) return;
  sel.classList.add("pl-sub-hidden");
  const b = document.createElement("button");
  b.className = "pl-b pl-cc"; b.id = "plCC"; b.innerHTML = `CC<i></i>`;
  sel.after(b);
  const menu = document.createElement("div"); menu.className = "pl-ccmenu"; menu.hidden = true; b.after(menu);
  b.addEventListener("click", (e) => {
    e.stopPropagation();
    if (!menu.hidden) { menu.hidden = true; return; }
    menu.innerHTML = [...sel.options].map((o) => `<button data-v="${o.value}" class="${o.value === sel.value ? "on" : ""}">${escapeHtml(o.textContent)}</button>`).join("");
    menu.hidden = false;
    const r = b.getBoundingClientRect();
    Object.assign(menu.style, { position: "fixed", left: Math.max(8, r.right - 240) + "px", bottom: (innerHeight - r.top + 8) + "px", right: "auto" });
  });
  menu.addEventListener("click", (e) => {
    const o = e.target.closest("button[data-v]"); if (!o) return;
    e.stopPropagation(); sel.value = o.dataset.v; sel.dispatchEvent(new Event("change")); menu.hidden = true; plCcSync();
  });
  document.addEventListener("click", () => { menu.hidden = true; });
  sel.addEventListener("change", plCcSync);
  new MutationObserver(plCcSync).observe(sel, { attributes: true, attributeFilter: ["hidden"], childList: true });
  plCcSync();
}
plCcInit(); setInterval(plCcInit, 800);   // oynatici arayuzu sonradan kurulur

// ---------- ayar sekmeleri: acilir alt basliklar (son acik hatirlanir) ----------
function pxGroupSec(sec) {
  const tab = sec.dataset.t;
  const kids = [...sec.children];
  if (kids.length < 4) return;
  const groups = [];
  let cur = null;
  for (const el of kids) {
    const isHead = el.classList.contains("px-shift") && el.querySelector(":scope > span");
    if (isHead || !cur) { cur = { head: isHead ? el : null, body: isHead ? [] : [el] }; groups.push(cur); }
    else cur.body.push(el);
  }
  let open; try { open = JSON.parse(localStorage.getItem("kami.pgrp") || "{}"); } catch { open = {}; }
  groups.forEach((g, gi) => {
    if (!g.body.length) return;   // tek satir: oldugu gibi kalir
    const key = (g.head?.querySelector("span")?.textContent || "temel").slice(0, 40);
    const wrap = document.createElement("div"); wrap.className = "px-grp";
    let head = g.head;
    if (!head) { head = document.createElement("div"); head.className = "px-shift"; head.innerHTML = `<span>${plL("Temel ayarlar", "Basics")}</span>`; }
    head.classList.add("px-gh");
    const body = document.createElement("div"); body.className = "px-gb";
    (g.head || g.body[0]).before(wrap);
    wrap.append(head, body); g.body.forEach((x) => body.appendChild(x));
    const isOpen = open[tab] ? open[tab] === key : gi === 0;
    wrap.classList.toggle("open", isOpen);
    head.addEventListener("click", (e) => {
      if (e.target.closest("button, input, select, label")) return;
      e.stopPropagation();
      const now = !wrap.classList.contains("open");
      sec.querySelectorAll(".px-grp.open").forEach((x) => x.classList.remove("open"));
      wrap.classList.toggle("open", now);
      open[tab] = now ? key : ""; try { localStorage.setItem("kami.pgrp", JSON.stringify(open)); } catch { /* yok */ }
    });
  });
}
const _pxTabify = window.pxTabify || (typeof pxTabify === "function" ? pxTabify : null);
if (_pxTabify) {
  window.pxTabify = pxTabify = function (p) {   // eslint-disable-line no-func-assign
    _pxTabify(p);
    p.querySelectorAll(".px-sec").forEach(pxGroupSec);
  };
}

// Ctrl+K paleti (oynatici): eylemler + son izlenenler + ayar sekmeleri
window.KPAL = window.KPAL || [];
window.KPAL.push(() => {
  const out = Object.entries(PL_ACTIONS).map(([k, [tr, en, fn]]) => ({ ic: "›", t: plL(tr, en), sub: plL("eylem", "action"), run: fn }));
  for (const r of peLS("kami.recent", []).slice(0, 30)) {
    const name = String(r.p).split(/[\\/]/).pop();
    out.push({ ic: "▶", t: name, sub: plL("son izlenen", "recent"), run: () => playerOpenPath(r.p) });
  }
  ["Altyazı", "Görüntü", "Ses", "Müzik", "Kısayollar", "Genel", "Araçlar"].forEach((n, i) => out.push({ ic: "⚙", t: plL("Ayarlar: ", "Settings: ") + n, sub: plL("ayar", "setting"), run: () => { if ($("#plPanel")?.hidden !== false) window.plSettings?.(); setTimeout(() => document.querySelector(`.px-ptabs button[data-tab="${i}"]`)?.click(), 80); } }));
  return out;
});

// ---------- Lyric video (HyperFrames): Araclar sekmesi ----------
const LV = { timer: null };
const _peTools4 = window.pxExtraToolsHtml;
window.pxExtraToolsHtml = () => _peTools4() + `<div class="px-shift"><span>${plL("Lyric video (senkron sözlerden)", "Lyric video (from synced lyrics)")}</span><button class="pl-b" data-xa="lv">🎬 ${plL("Yap", "Make")}</button></div>
  ${peSeg("lvStyle", [["kinetic", plL("Kinetik", "Kinetic")], ["simple", plL("Sade", "Simple")], ["karaoke", "Karaoke"]], peCfg().lvStyle || "kinetic")}
  ${peSeg("lvAspect", [["h", "16:9 YouTube"], ["v", "9:16 Reels / TikTok"]], peCfg().lvAspect || "h")}
  ${(peCfg().lvAspect || "h") === "v" ? peSeg("lvLen", [[15, "15 sn"], [30, "30 sn"], [60, "60 sn"]], peCfg().lvLen || 30) + `<p class="px-hint">${plL("Reels şu anki saniyeden başlar.", "The clip starts at the current position.")}</p>` : ""}
  <div id="peLvRes"></div>`;
function lvDraw(j) {
  const box = $("#peLvRes"); if (!box || !j) return;
  if (j.state === "running") box.innerHTML = `<p class="px-hint">${j.stage === "render" ? plL("İşleniyor", "Rendering") + (j.p ? ` · %${Math.round(j.p * 100)}` : plL(" (ilk seferde HyperFrames iner)", " (first run downloads HyperFrames)")) : plL("Hazırlanıyor…", "Preparing…")}</p><button class="pl-b" data-xa="lvstop">${plL("İptal", "Cancel")}</button>`;
  else if (j.state === "done") box.innerHTML = `<p class="px-hint">✓ ${escapeHtml(String(j.out || "").split(/[\\/]/).pop())}</p><button class="pl-b" data-xa="lvplay">${plL("Oynat", "Play")}</button><button class="pl-b" data-xa="lvfolder">${plL("Klasörü aç", "Open folder")}</button>`;
  else if (j.state === "error") box.innerHTML = `<p class="px-hint">${({ cancelled: plL("İptal edildi", "Cancelled"), no_synced: plL("Bu şarkının senkron sözü yok (LRC/SRT ya da LRCLIB)", "No synced lyrics"), node_yok: plL("Node.js gerekli (nodejs.org)", "Node.js required") })[j.error] || plL("Olmadı: ", "Failed: ") + escapeHtml(j.error || "?")}</p>`;
  else box.innerHTML = "";
}
async function lvPoll() {
  clearTimeout(LV.timer);
  let j; try { j = await api.lyricvideo_status(); } catch { return; }
  lvDraw(j);
  if (j?.state === "running") LV.timer = setTimeout(lvPoll, 1500);
}
document.addEventListener("click", async (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="lvStyle"], #plPanel .px-xseg[data-x="lvAspect"], #plPanel .px-xseg[data-x="lvLen"]');
  const b = e.target.closest?.("button");
  if (seg && b) { PX.cfg[seg.dataset.x] = seg.dataset.x === "lvLen" ? +b.dataset.v : b.dataset.v; pxSave(); if (seg.dataset.x === "lvAspect") window.plSettings?.(), window.plSettings?.(); return; }
  if (!b || !b.closest("#plPanel") || !String(b.dataset.xa || "").startsWith("lv")) return;
  e.stopPropagation();
  const a = b.dataset.xa, c = peCfg();
  if (a === "lv") {
    if (!PL.info?.path) { toast(plL("Önce bir şarkı aç", "Open a song first"), true); return; }
    const v = (c.lvAspect || "h") === "v";
    const r = await api.lyricvideo_start(PL.info.path, c.lvStyle || "kinetic", v, v ? plNow() : 0, v ? (c.lvLen || 30) : 0, window.pmSyncedLrc?.() || "");
    if (!r?.ok) { lvDraw({ state: "error", error: r?.error }); return; }
    toast(plL("Lyric video başladı; bitince bildirim gelir", "Lyric video started; you'll be notified")); lvPoll();
  }
  if (a === "lvstop") { await api.lyricvideo_cancel(); setTimeout(lvPoll, 600); }
  if (a === "lvplay") api.lyricvideo_open("play");
  if (a === "lvfolder") api.lyricvideo_open("folder");
}, true);
document.addEventListener("click", (e) => { if (e.target.closest?.("#plPanel .px-ptabs button")) setTimeout(lvPoll, 60); }, true);

// ---------- altyazi fontu: aile, kalinlik, kenar cizgisi ----------
const SUBF = { list: null };
const SUBF_PRESET = ["Chakra Petch", "Segoe UI", "Arial", "Verdana", "Tahoma", "Trebuchet MS", "Georgia", "Calibri", "Bahnschrift", "Impact", "Comic Sans MS", "Consolas"];
function subFontApply() {
  const c = peCfg(), el = $("#player"); if (!el) return;
  el.style.setProperty("--sub-font", `"${(c.subFont || "Chakra Petch").replace(/"/g, "")}"`);
  el.style.setProperty("--sub-fw", c.subFw === "bold" ? "800" : c.subFw === "light" ? "400" : "600");
  el.style.setProperty("--sub-stroke", { none: "0px", thin: "1.5px", thick: "3px" }[c.subStroke || "none"]);
}
const _peSub2 = window.pxExtraSubHtml;
window.pxExtraSubHtml = () => {
  const c = peCfg(), fonts = [...new Set(SUBF_PRESET.concat(SUBF.list || []))];
  if (!SUBF.list) api.system_fonts?.().then((l) => { SUBF.list = l || []; }).catch(() => { SUBF.list = []; });
  return (_peSub2?.() || "") + `<div class="px-shift"><span>${plL("Altyazı fontu", "Subtitle font")}</span>
    <select class="pl-sel pe-subfont" style="max-width:190px">${fonts.map((f) => `<option ${f === (c.subFont || "Chakra Petch") ? "selected" : ""} style="font-family:'${esc2(f)}'">${esc2(f)}</option>`).join("")}</select></div>
    ${peSeg("subFw", [["light", plL("İnce", "Light")], ["normal", "Normal"], ["bold", plL("Kalın", "Bold")]], c.subFw || "normal")}
    ${peSeg("subStroke", [["none", plL("Kenar yok", "No outline")], ["thin", plL("İnce kenar", "Thin outline")], ["thick", plL("Kalın kenar", "Thick outline")]], c.subStroke || "none")}
    <p class="pe-subprev" style="font-family:'${esc2(c.subFont || "Chakra Petch")}'">${plL("Örnek: Kami ile izliyorsun", "Sample: watching with Kami")}</p>`;
};
function esc2(t) { return String(t).replace(/[&<>"']/g, (ch) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[ch])); }
document.addEventListener("change", (e) => {
  if (!e.target.matches?.(".pe-subfont")) return;
  PX.cfg.subFont = e.target.value; pxSave(); subFontApply();
  const pv = $(".pe-subprev"); if (pv) pv.style.fontFamily = `'${e.target.value}'`;
});
document.addEventListener("click", (e) => {
  const seg = e.target.closest?.('#plPanel .px-xseg[data-x="subFw"], #plPanel .px-xseg[data-x="subStroke"]'), b = e.target.closest?.("button");
  if (seg && b) { PX.cfg[seg.dataset.x] = b.dataset.v; pxSave(); setTimeout(subFontApply, 0); }
}, true);
setTimeout(subFontApply, 300);
