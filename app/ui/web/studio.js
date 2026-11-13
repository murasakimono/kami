"use strict";
// Kami Studio: proje durumu, onizleme (tuval + JASSUB), zaman cizelgesi, denetci. Paneller: studio-panels.js
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let api = null;

const ST = {
  p: null, path: "", sel: new Set(), t: 0, playing: false, px: 80, snap: true, ripple: false,
  undo: [], redo: [], cat: { fx: {}, trans: {}, zoom: [], captions: {}, anims: {}, subscribe: {}, fonts: [] },
  rt: {}, media: {}, dirty: false, lastSave: 0, binSel: new Set(), pq: .75, clip: null,
};
const TRACK_H = { video: 58, audio: 46, text: 34, fx: 30 };
const KIND_COL = { video: "var(--c-video)", audio: "var(--c-audio)", text: "var(--c-text)", fx: "var(--c-fx)" };

// ---------------------------------------------------------------- yardimcilar
function fmt(t, cs = true) {
  t = Math.max(0, t || 0);
  const m = Math.floor(t / 60), s = t - m * 60;
  return `${String(m).padStart(2, "0")}:${cs ? s.toFixed(2).padStart(5, "0") : String(Math.floor(s)).padStart(2, "0")}`;
}
let toastT = 0;
function toast(msg, ms = 2400) { const el = $("#toast"); el.textContent = msg; el.classList.add("on"); clearTimeout(toastT); toastT = setTimeout(() => el.classList.remove("on"), ms); }
function modal(html, onReady) {
  const m = $("#modal"); m.innerHTML = `<div class="mbox cut">${html}</div>`; m.hidden = false;
  return new Promise(res => {
    const close = v => { m.hidden = true; m.innerHTML = ""; document.removeEventListener("keydown", kd, true); res(v); };
    const kd = e => { if (e.key === "Escape") { e.stopPropagation(); close(null); } };
    document.addEventListener("keydown", kd, true);
    m.onclick = e => { const b = e.target.closest("[data-v]"); if (b) close(b.dataset.v === "ok" ? (onReady?.collect?.() ?? true) : b.dataset.v === "no" ? null : b.dataset.v); };
    onReady?.init?.(m, close);
  });
}
function ask(title, text, ok = "Tamam", no = "Vazgeç") {
  return modal(`<h3>${esc(title)}</h3><div class="hint" style="font-size:13px">${text}</div><div class="row"><button class="tb" data-v="no">${no}</button><button class="tb pri" data-v="ok">${ok}</button></div>`);
}
function promptText(title, val = "", hint = "") {
  return modal(`<h3>${esc(title)}</h3>${hint ? `<div class="hint">${hint}</div>` : ""}<input class="in" id="mIn" value="${esc(val)}"><div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">Tamam</button></div>`,
    { init: m => { const i = $("#mIn", m); i.focus(); i.select(); i.onkeydown = e => { if (e.key === "Enter") m.querySelector('[data-v="ok"]').click(); }; }, collect: () => $("#mIn").value });
}
function busy(text, p) {
  const b = $("#busy");
  if (text === null) { b.hidden = true; return; }
  b.hidden = false; b.innerHTML = `<div>${esc(text)}</div>${p != null ? `<div class="bar"><i style="width:${Math.round(p * 100)}%"></i></div>` : ""}`;
}
async function job(name, args = []) {
  const j = await api.job_start(name, args);
  if (!j?.ok) throw new Error(j?.error || "job");
  for (;;) {
    await new Promise(r => setTimeout(r, 160));
    const r = await api.job_result(j.job);
    if (r.state === "done") return r.result;
    if (r.state === "lost") throw new Error("lost");
  }
}
async function waitStudioJob(jid, label) {
  for (;;) {
    await new Promise(r => setTimeout(r, 400));
    const j = await api.studio_job(jid);
    if (!j || !j.state) { busy(null); throw new Error("iş kayboldu"); }
    busy(label + (j.line ? " — " + j.line : ""), j.p || 0);
    if (j.state !== "running") { busy(null); if (j.state === "done") return j; throw new Error(j.error || j.state); }
  }
}
const uid = (pre = "c") => { const ids = new Set(ST.p.clips.map(c => c.id)); let i = ids.size + 1; while (ids.has(pre + i)) i++; return pre + i; };
const clone = o => JSON.parse(JSON.stringify(o));
const trackOf = c => ST.p.tracks.find(t => t.id === c.track) || {};
const assetOf = c => ST.p.assets[c.asset];
const clipKind = c => { const tk = trackOf(c).kind; if (tk !== "video") return tk; const a = assetOf(c); return a?.kind === "image" && !a.gif ? "image" : "video"; };
const projEnd = () => Math.max(0, ...ST.p.clips.map(c => c.start + c.dur));
const vidTracks = () => ST.p.tracks.filter(t => t.kind === "video");
function defaultFit(c) { return c.fit || (c.track === "v1" || vidTracks().length === 1 ? "cover" : "contain"); }
const selClips = () => ST.p.clips.filter(c => ST.sel.has(c.id));

// ---------------------------------------------------------------- gecmis / kayit
function snap() { ST.undo.push(JSON.stringify(ST.p)); if (ST.undo.length > 120) ST.undo.shift(); ST.redo = []; }
function changed(full = true) {
  ST.dirty = true; $("#saved").textContent = "● kaydedilmedi"; $("#saved").classList.add("dirty");
  if (full) renderTimeline(); renderInsp(); assDirty(); draw(); scheduleSave();
}
function undo() { if (!ST.undo.length) return; ST.redo.push(JSON.stringify(ST.p)); ST.p = JSON.parse(ST.undo.pop()); afterLoad(true); }
function redo() { if (!ST.redo.length) return; ST.undo.push(JSON.stringify(ST.p)); ST.p = JSON.parse(ST.redo.pop()); afterLoad(true); }
let saveT = 0;
function scheduleSave() { clearTimeout(saveT); saveT = setTimeout(save, 1500); }
async function save(as = false) {
  clearTimeout(saveT);
  ST.p.name = $("#pname").value.trim() || "Proje";
  let path = ST.path;
  if (as || !path) {
    if (as) { path = await api.studio_pick_save(ST.p.name, ".kstudio"); if (!path) return; }
  }
  const p = clone(ST.p);
  for (const a of Object.values(p.assets)) { delete a.url; delete a.missing; }
  const r = await job("studio_save", [p, path || ""]);
  if (r?.ok) { ST.path = r.path; ST.dirty = false; $("#saved").textContent = "✓ kaydedildi"; $("#saved").classList.remove("dirty"); }
}
function afterLoad(keepSel = false) {
  if (!keepSel) ST.sel.clear(); else for (const id of [...ST.sel]) if (!ST.p.clips.some(c => c.id === id)) ST.sel.delete(id);
  $("#pname").value = ST.p.name || "Proje";
  const r = `${ST.p.w}x${ST.p.h}`;
  if (![...$("#ratio").options].some(o => o.value === r)) $("#ratio").add(new Option(`${ST.p.w}×${ST.p.h}`, r));
  $("#ratio").value = r;
  for (const a of Object.values(ST.p.assets)) prepAsset(a);
  layoutView(); renderTimeline(); renderInsp(); assDirty(true); window.renderPanel?.(); seek(ST.t); scheduleSave();
}
async function openProject(path) {
  busy("Proje açılıyor…");
  try {
    const r = await job("studio_open", [path]);
    if (!r?.ok) throw new Error(r?.error || "açılamadı");
    stopAll(); ST.p = r.project; ST.path = r.path; ST.undo = []; ST.redo = []; ST.t = 0; ST.dirty = false;
    ST.p.markers ||= [];
    afterLoad(); $("#saved").textContent = "✓ açık"; $("#saved").classList.remove("dirty");
    const miss = Object.values(ST.p.assets).filter(a => a.missing).length;
    if (miss) toast(`${miss} medya dosyası bulunamadı (taşınmış olabilir)`, 4000);
  } catch (e) { toast("Açılamadı: " + e.message, 4000); }
  busy(null);
}
async function newProject() {
  if (ST.dirty) await save();
  stopAll(); ST.p = await api.studio_new(); ST.path = ""; ST.undo = []; ST.redo = []; ST.t = 0;
  afterLoad(); $("#saved").textContent = "";
}

// ---------------------------------------------------------------- medya
function prepAsset(a) {
  const key = a.path;
  if (ST.media[key]) return ST.media[key];
  const m = ST.media[key] = { peaks: null, thumbs: null, img: null };
  if (a.kind === "image" && !a.gif) { m.img = new Image(); m.img.src = a.url; m.img.onload = () => draw(); }
  if (a.gif) { m.img = new Image(); m.img.src = a.url; }
  if (a.kind === "video" && !a.gif) job("studio_thumbs", [a.path, 16]).then(r => { m.thumbs = r; renderTimeline(); window.onThumbs?.(); }).catch(() => {});
  if (a.audio || a.kind === "audio") job("studio_peaks", [a.path]).then(r => { m.peaks = r; renderTimeline(); }).catch(() => {});
  return m;
}
async function importPaths(paths, addToTimeline = false) {
  if (!paths?.length) return [];
  busy(`${paths.length} dosya içe aktarılıyor…`);
  let infos = [];
  try { infos = await job("studio_info", [paths]); } catch (e) { toast("İçe aktarılamadı: " + e.message); }
  busy(null);
  const added = [];
  snap();
  for (const i of infos) {
    if (!i.ok) { toast("Desteklenmiyor: " + (i.path || "").split(/[\\/]/).pop()); continue; }
    let aid = Object.keys(ST.p.assets).find(k => ST.p.assets[k].path === i.path);
    if (!aid) {
      aid = "a1"; let n = 1; while (ST.p.assets[aid]) aid = "a" + (++n);
      ST.p.assets[aid] = { path: i.path, kind: i.kind, dur: i.dur, w: i.w, h: i.h, audio: i.audio, name: i.name, gif: i.gif, url: i.url };
      prepAsset(ST.p.assets[aid]);
    }
    added.push(aid);
  }
  if (addToTimeline) for (const aid of added) appendAsset(aid);
  if (!ST.p.clips.length && added.length && !addToTimeline) for (const aid of added) appendAsset(aid);
  changed(); window.renderPanel?.();
  return added;
}
function trackFor(kind) {
  if (kind === "image" || kind === "video") return vidTracks().find(t => t.id === "v1")?.id || vidTracks().at(-1)?.id || addTrack("video");
  return ST.p.tracks.find(t => t.kind === kind)?.id || addTrack(kind);
}
function addTrack(kind, name) {
  const pre = { video: "v", audio: "a", text: "t", fx: "f" }[kind];
  let i = 1; while (ST.p.tracks.some(t => t.id === pre + i)) i++;
  const t = { id: pre + i, kind, name: name || { video: "Video", audio: "Ses", text: "Metin", fx: "Efekt" }[kind] + " " + i };
  if (kind === "video") ST.p.tracks.unshift(t); else ST.p.tracks.push(t);
  return t.id;
}
function appendAsset(aid) {
  const a = ST.p.assets[aid], tr = trackFor(a.kind === "audio" ? "audio" : "video");
  const end = Math.max(0, ...ST.p.clips.filter(c => c.track === tr).map(c => c.start + c.dur));
  return addClip({ asset: aid, track: tr, start: end, dur: a.dur, in: 0 });
}
function addClip(o) {
  const c = { id: uid(), start: 0, dur: 3, in: 0, speed: 1, ...o };
  ST.p.clips.push(c); return c;
}
// oynatma kafasina: ust katmanda bos izi bul
function placeAt(o, kind, t = ST.t) {
  const cands = ST.p.tracks.filter(tr => tr.kind === kind);
  let tr = cands.find(tr => !ST.p.clips.some(c => c.track === tr.id && c.start < t + o.dur - 1e-3 && c.start + c.dur > t + 1e-3));
  const id = tr?.id || addTrack(kind);
  return addClip({ ...o, track: id, start: t });
}

// ---------------------------------------------------------------- duzenleme islemleri (studio.py ile ayni)
function splitClip(c, t) {
  if (!(c.start + .02 < t && t < c.start + c.dur - .02)) return null;
  const left = t - c.start, n = clone(c);
  n.id = uid(); n.start = t; n.dur = c.dur - left; n.in = (c.in || 0) + left * (c.speed || 1);
  if (n.words) { n.words = n.words.filter(w => w.e > left).map(w => ({ ...w, s: w.s - left, e: w.e - left })); c.words = c.words.filter(w => w.s < left); }
  if (c.zoom?.length) { const z = kfResolve(c.zoom, c.dur); n.zoom = z.filter(k => k.t >= left).map(k => ({ ...k, t: k.t - left })); if (!n.zoom.length) delete n.zoom; }
  n.fadeIn = 0; c.fadeOut = 0; c.dur = left;
  if (n.trans) delete n.trans;
  ST.p.clips.push(n); return n;
}
function rippleClose(track, t0, gap) { for (const c of ST.p.clips) if (c.track === track && c.start >= t0 - 1e-6) c.start = +(c.start - gap).toFixed(4); }
function removeRanges(c, ranges, pad = .08) {
  const sp = c.speed || 1; let n = 0;
  for (let [a, b] of [...ranges].sort((x, y) => y[0] - x[0])) {
    a += pad; b -= pad; if (b - a < .15) continue;
    const same = ST.p.clips.filter(x => x.track === c.track && x.asset === c.asset);
    for (const x of same) {
      let t0 = x.start + (a - (x.in || 0)) / sp, t1 = x.start + (b - (x.in || 0)) / sp;
      if (t1 <= x.start || t0 >= x.start + x.dur) continue;
      t0 = Math.max(x.start, t0); t1 = Math.min(x.start + x.dur, t1);
      const mid = t0 > x.start + .02 ? splitClip(x, t0) : x; if (!mid) continue;
      if (t1 < mid.start + mid.dur - .02) splitClip(mid, t1);
      ST.p.clips.splice(ST.p.clips.indexOf(mid), 1); ST.sel.delete(mid.id);
      rippleClose(c.track, t1, t1 - t0); n++; break;
    }
  }
  return n;
}
function kfResolve(kf, dur) { return (kf || []).map(k => ({ ...k, t: Math.max(0, k.t < 0 ? dur + k.t : k.t) })).sort((a, b) => a.t - b.t); }
const EASE = { out: u => 1 - (1 - u) * (1 - u), in: u => u * u, inout: u => u * u * (3 - 2 * u) };
function kfAt(kf, key, t, def) {
  const pts = kf.filter(k => key in k || key === "z");
  if (!pts.length) return def;
  if (t <= pts[0].t) return pts[0][key] ?? def;
  for (let i = 1; i < pts.length; i++) {
    if (t < pts[i].t) { const a = pts[i - 1], b = pts[i], u = (t - a.t) / Math.max(1e-3, b.t - a.t); const e = EASE[b.e] || (x => x); return (a[key] ?? def) + ((b[key] ?? def) - (a[key] ?? def)) * e(u); }
  }
  return pts.at(-1)[key] ?? def;
}
function deleteSel(ripple = ST.ripple) {
  const cs = selClips(); if (!cs.length) return;
  snap();
  for (const c of cs.sort((a, b) => b.start - a.start)) { ST.p.clips.splice(ST.p.clips.indexOf(c), 1); if (ripple) rippleClose(c.track, c.start + c.dur, c.dur); }
  ST.sel.clear(); changed();
}
function splitAtPlayhead() {
  let cs = selClips().filter(c => c.start < ST.t && c.start + c.dur > ST.t);
  if (!cs.length) cs = ST.p.clips.filter(c => c.start < ST.t && c.start + c.dur > ST.t && !trackOf(c).lock);
  if (!cs.length) return;
  snap(); const news = cs.map(c => splitClip(c, ST.t)).filter(Boolean); ST.sel = new Set(news.map(c => c.id)); changed();
}
function dupSel() {
  const cs = selClips(); if (!cs.length) return; snap();
  const ns = cs.map(c => { const n = clone(c); n.id = uid(); n.start = c.start + c.dur; ST.p.clips.push(n); resolveOverlap(n); return n; });
  ST.sel = new Set(ns.map(c => c.id)); changed();
}
function overlaps(c, track = c.track, start = c.start) {
  return ST.p.clips.some(x => x !== c && x.track === track && x.start < start + c.dur - 1e-3 && x.start + x.dur > start + 1e-3);
}
function resolveOverlap(c) {
  if (!overlaps(c)) return;
  const kind = trackOf(c).kind;
  const alt = ST.p.tracks.find(t => t.kind === kind && !overlaps(c, t.id));
  c.track = alt ? alt.id : addTrack(kind);
}
let clipboard = [];
function copySel() { clipboard = clone(selClips()); if (clipboard.length) toast(`${clipboard.length} klip kopyalandı`); }
function paste() {
  if (!clipboard.length) return; snap();
  const t0 = Math.min(...clipboard.map(c => c.start));
  const ns = clipboard.map(c => { const n = clone(c); n.id = uid(); n.start = ST.t + (c.start - t0); ST.p.clips.push(n); resolveOverlap(n); return n; });
  ST.sel = new Set(ns.map(c => c.id)); changed();
}

// ---------------------------------------------------------------- onizleme
const view = $("#view"), vctx = view.getContext("2d");
const clipBuf = document.createElement("canvas"), cbx = clipBuf.getContext("2d");
const fitBuf = document.createElement("canvas"), fbx = fitBuf.getContext("2d");
let PW = 960, PH = 540, PS = .5;
function layoutView() {
  if (!ST.p) return;
  const area = $("#viewArea").getBoundingClientRect();
  const ar = ST.p.w / ST.p.h, mw = area.width - 24, mh = area.height - 24;
  let w = mw, h = w / ar; if (h > mh) { h = mh; w = h * ar; }
  const wrap = $("#viewWrap"); wrap.style.width = Math.round(w) + "px"; wrap.style.height = Math.round(h) + "px";
  PS = Math.min(1, (w * devicePixelRatio * ST.pq) / ST.p.w, 1);
  PW = Math.max(2, Math.round(ST.p.w * PS)); PH = Math.max(2, Math.round(ST.p.h * PS));
  for (const c of [view, clipBuf, fitBuf]) { c.width = PW; c.height = PH; }
  assResize(Math.round(w), Math.round(h));
  draw(); renderHandles();
}
function mediaEl(c) {
  let r = ST.rt[c.id];
  const a = assetOf(c);
  if (r && r.src === a.url) return r;
  if (r) dropEl(c.id);
  const isV = a.kind === "video" && !a.gif;
  const el = document.createElement(isV ? "video" : "audio");
  el.preload = "auto"; el.crossOrigin = "anonymous"; el.src = a.url; el.playsInline = true;
  if (isV) { el.muted = !a.audio; el.addEventListener("seeked", () => { if (!ST.playing) draw(); }); el.addEventListener("loadeddata", () => draw()); }
  r = ST.rt[c.id] = { el, src: a.url, isV };
  return r;
}
function dropEl(id) { const r = ST.rt[id]; if (!r) return; try { r.el.pause(); r.el.removeAttribute("src"); r.el.load(); } catch { } delete ST.rt[id]; }
function stopAll() { for (const id of Object.keys(ST.rt)) dropEl(id); }
// gercek klip-klip gecis: sonraki bitisik klibin giris gecisi suresince bu klip altta devam eder (studio.py trans_tail)
function transTail(c) {
  if (c.freeze || c.ramp) return 0;
  const end = c.start + c.dur, n = ST.p.clips.find(x => x !== c && x.track === c.track && Math.abs(x.start - end) < .05);
  const tr = n?.trans; if (!tr?.in || tr.in === "none" || tr.over === false) return 0;
  const want = tr.dur || .35, a = ST.p.assets[c.asset] || {};
  if (a.kind === "image" || a.gif) return want;
  const sp = c.speed || 1; return Math.max(0, Math.min(want, ((a.dur || 0) - (c.in || 0) - c.dur * sp) / sp));
}
function activeAt(t, kind) { return ST.p.clips.filter(c => t >= c.start - 1e-4 && t < c.start + c.dur && !trackOf(c).hide && (!kind || trackOf(c).kind === kind)); }
function trackOrder(id) { const i = ST.p.tracks.findIndex(t => t.id === id); return ST.p.tracks.length - i; }
// hiz rampasi: [tl0, tl1, src0, src1, hiz] dilimleri (studio.py ramp_table ile ayni)
const RAMP_N = 24;
function rampSpeed(pts, p) {
  const ps = [...pts].sort((a, b) => a.p - b.p);
  if (p <= ps[0].p) return ps[0].s;
  for (let i = 1; i < ps.length; i++) if (p <= ps[i].p) { const a = ps[i - 1], b = ps[i]; return a.s + (b.s - a.s) * (p - a.p) / Math.max(1e-6, b.p - a.p); }
  return ps.at(-1).s;
}
function rampTable(c) {
  const L = c.srcLen || c.dur * (c.speed || 1), out = []; let t = 0;
  for (let i = 0; i < RAMP_N; i++) { const a0 = L * i / RAMP_N, a1 = L * (i + 1) / RAMP_N, sp = Math.max(.05, rampSpeed(c.ramp, (i + .5) / RAMP_N)); const d = (a1 - a0) / sp; out.push([t, t + d, a0, a1, sp]); t += d; }
  return out;
}
function rampAt(c, local) {
  const tab = c._rt && c._rk === JSON.stringify([c.ramp, c.srcLen, c.dur]) ? c._rt : (c._rk = JSON.stringify([c.ramp, c.srcLen, c.dur]), c._rt = rampTable(c));
  for (const [t0, t1, a0, , sp] of tab) if (local < t1) return [a0 + (local - t0) * sp, sp];
  const l = tab.at(-1); return [l[3], l[4]];
}
function rampApply(c, pts) {
  if (!pts) { if (c.srcLen) c.dur = c.srcLen / (c.speed || 1); delete c.ramp; delete c.srcLen; return; }
  c.srcLen ||= c.dur * (c.speed || 1); c.ramp = pts; c.dur = +rampTable(c).at(-1)[1].toFixed(3);
}
function srcTime(c, t) {
  if (c.freeze) return c.in || 0;
  if (c.ramp?.length) return (c.in || 0) + rampAt(c, t - c.start)[0];
  return (c.in || 0) + (t - c.start) * (c.speed || 1);
}
function curSpeed(c, t) { return c.freeze ? 0 : c.ramp?.length ? rampAt(c, t - c.start)[1] : (c.speed || 1); }
function clipVol(c, t) {
  const tr = trackOf(c); if (tr.mute) return 0;
  let v = c.vol ?? 1; const l = t - c.start;
  if (tr.duck && ST.p.clips.some(x => x !== c && !trackOf(x).duck && !trackOf(x).mute && (trackOf(x).kind === "audio" || (trackOf(x).kind === "video" && assetOf(x)?.audio)) && t >= x.start && t < x.start + x.dur))
    v *= 1 - .7 * ((ST.p.master || {}).duck ?? .6);
  if (c.fadeIn > 0 && l < c.fadeIn) v *= l / c.fadeIn;
  if (c.fadeOut > 0 && c.dur - l < c.fadeOut) v *= Math.max(0, (c.dur - l) / c.fadeOut);
  return clamp(v, 0, 2);
}
// medya ogelerini zamana gore ayarla (oynatirken surekli, dururken seek)
function syncMedia(t, hard = false) {
  const keep = new Set();
  for (const c of ST.p.clips) {
    const a = assetOf(c); if (!a || a.missing) continue;
    const tk = trackOf(c).kind;
    if (!(a.kind === "audio" || (a.kind === "video" && !a.gif))) continue;
    if (tk !== "video" && tk !== "audio") continue;
    const act = t >= c.start && t < c.start + c.dur && !trackOf(c).hide;
    const soon = !act && c.start > t && c.start - t < 1.5;
    if (!act && !soon && !(ST.rt[c.id] && Math.abs(c.start - t) < 10)) continue;
    keep.add(c.id);
    const r = mediaEl(c), el = r.el;
    if (act) {
      const want = srcTime(c, t), vol = clipVol(c, t);
      const gain = Math.min(1, vol);
      el.volume = gain; el.muted = !(a.audio || a.kind === "audio") || vol <= 0 || c.freeze;
      el.playbackRate = clamp(curSpeed(c, t) || 1, .0625, 16);
      if (ST.playing && !c.freeze) {
        if (el.paused) { el.currentTime = want; el.play().catch(() => {}); }
        else if (Math.abs(el.currentTime - want) > .25) el.currentTime = want;
      } else {
        if (!el.paused) el.pause();
        if (hard || Math.abs(el.currentTime - want) > .5 / ST.p.fps) el.currentTime = want;
      }
    } else {
      if (!el.paused) el.pause();
      if (soon && Math.abs(el.currentTime - (c.in || 0)) > .2) el.currentTime = c.in || 0;
    }
  }
  for (const id of Object.keys(ST.rt)) if (!keep.has(id)) dropEl(id);
}
function sourceOf(c) {
  const a = assetOf(c); if (!a) return null;
  if (a.kind === "image" || a.gif) { const m = ST.media[a.path]; return m?.img?.complete && m.img.naturalWidth ? { src: m.img, w: m.img.naturalWidth, h: m.img.naturalHeight } : null; }
  const r = ST.rt[c.id] || mediaEl(c);
  return r.el.readyState >= 2 && r.el.videoWidth ? { src: r.el, w: r.el.videoWidth, h: r.el.videoHeight } : null;
}
function fxCss(ids) { return (ids || []).map(id => ST.cat.fx[id]?.css).filter(Boolean).join(" "); }
function adjCss(a) {
  if (!a) return "";
  const f = [];
  if (a.bri) f.push(`brightness(${1 + a.bri / 100})`);
  if (a.con) f.push(`contrast(${1 + a.con / 100})`);
  if (a.sat) f.push(`saturate(${1 + a.sat / 100})`);
  if (a.hue) f.push(`hue-rotate(${a.hue}deg)`);
  if (a.temp) f.push(`sepia(${Math.max(0, a.temp) / 250})`);
  if (a.blur) f.push(`blur(${a.blur * PS}px)`);
  return f.join(" ");
}
// efekt yerlesimi (Giris / Cikis / Tum sure) ve klip animasyonlari: disa aktarimla ayni hesap (studio_anim.py)
function activeFx(c, local) {
  return (c.fx || []).filter(id => {
    const p = c.fxAt?.[id]; if (!p || !p.at || p.at === "all") return true;
    const d = Math.max(.05, +p.d || 1);
    return p.at === "in" ? local <= d : local >= c.dur - d;
  });
}
const AEASE = {
  linear: p => p, out: p => 1 - (1 - p) ** 3,
  back: p => 1 + 2.70158 * (p - 1) ** 3 + 1.70158 * (p - 1) ** 2,
  elastic: p => 1 - Math.exp(-6 * p) * Math.cos(12 * p),
  bounce: p => 1 - Math.abs(Math.cos(p * Math.PI * 1.5)) * Math.exp(-4 * p),
};
function clipAnim(c, L) {
  const r = { s: 1, sx: 1, sy: 1, x: 0, y: 0, r: 0, a: 1, b: 0 }, an = c.anim, cat = ST.cat.canim;
  if (!an || !cat) return r;
  const d = c.dur, ai = cat.in[an.in], ao = cat.out[an.out], al = cat.loop[an.loop];
  const di = ai ? Math.min(d, Math.max(.05, +an.inDur || .5)) : 0, dd = ao ? Math.min(d - di, Math.max(.05, +an.outDur || .5)) : 0;
  const clip01 = v => Math.min(1, Math.max(0, v));
  if (ai) {
    const p = clip01(L / di), e = (AEASE[an.inEase || ai.ease || "out"] || AEASE.out)(p), inv = 1 - e;
    for (const k of ["s", "sx", "sy"]) if (k in ai) r[k] *= 1 + (ai[k] - 1) * inv;
    for (const k of ["x", "y", "r"]) if (k in ai) r[k] += ai[k] * inv * (ai.shake ? Math.sin(L * 70) : 1);
    if (ai.a) r.a *= p; if (ai.b) r.b = Math.max(r.b, ai.b * (1 - p));
  }
  if (ao) {
    const q = clip01((L - (d - dd)) / dd), ez = an.outEase || ao.ease || "out", e = ez === "out" || ez === "linear" ? q ** 3 : AEASE[ez](q);
    for (const k of ["s", "sx", "sy"]) if (k in ao) r[k] *= 1 + (ao[k] - 1) * e;
    for (const k of ["x", "y", "r"]) if (k in ao) r[k] += ao[k] * e * (ao.shake ? Math.sin(L * 70) : 1);
    if (ao.a) r.a *= 1 - q; if (ao.b) r.b = Math.max(r.b, ao.b * q);
  }
  if (al) {
    const k = +an.loopAmt || 1, sp = +an.loopSpeed || 1, w = 2 * Math.PI * (al.f || 1) * sp * L;
    if (al.s) r.s *= 1 + al.s * k * Math.sin(w);
    if (al.beat) r.s *= 1 + al.beat * k * Math.max(0, Math.sin(w)) ** 8;
    if (al.sx) r.sx *= 1 - al.sx * k * (1 + Math.sin(w)) / 2;
    if (al.x) r.x += al.x * k * Math.sin(w);
    if (al.y) r.y += al.y * k * Math.cos(w * 1.13);
    if (al.r) r.r += al.r * k * Math.sin(w * .9);
    if (al.spin) r.r += al.spin * k * sp * L;
    if (al.grow) r.s *= 1 + al.grow * k * clip01(L / d);
    if (al.pan) r.x += al.pan * k * clip01(L / d);
  }
  return r;
}
function drawClip(c, t) {
  const s = sourceOf(c); if (!s) return;
  const W = PW, H = PH, local = t - c.start, fxOn = activeFx(c, local), A = clipAnim(c, local);
  // 1) kirp (dikey cerceve) + sigdir -> fitBuf
  let sx = 0, sy = 0, sw = s.w, sh = s.h;
  if (c.reframe?.length) {
    const cw = Math.min(s.w, s.h * ST.p.w / ST.p.h), ch = Math.min(s.h, s.w * ST.p.h / ST.p.w);
    const cx = kfAt(c.reframe.map(r => ({ t: r.t, cx: r.cx })), "cx", srcTime(c, t), .5);
    sx = clamp(cx * s.w - cw / 2, 0, s.w - cw); sy = (s.h - ch) / 2; sw = cw; sh = ch;
  }
  const fit = defaultFit(c);
  fbx.setTransform(1, 0, 0, 1, 0, 0); fbx.clearRect(0, 0, W, H);
  fbx.filter = [adjCss(c.adj), fxCss(fxOn)].filter(Boolean).join(" ") || "none";
  let dw = W, dh = H;
  if (c.crop === "half-w" || c.crop === "half-h") {   // yan yana: kutuya kapla, kutu disi saydam
    const bw = c.crop === "half-w" ? W / 2 : W, bh = c.crop === "half-h" ? H / 2 : H, k = Math.max(bw / sw, bh / sh);
    const cw = bw / k, chh = bh / k;
    fbx.drawImage(s.src, sx + (sw - cw) / 2, sy + (sh - chh) / 2, cw, chh, (W - bw) / 2, (H - bh) / 2, bw, bh);
  } else {
    if (fit === "cover") { const k = Math.max(W / sw, H / sh); dw = sw * k; dh = sh * k; }
    else if (fit === "contain") { const k = Math.min(W / sw, H / sh); dw = sw * k; dh = sh * k; }
    fbx.drawImage(s.src, sx, sy, sw, sh, (W - dw) / 2, (H - dh) / 2, dw, dh);
  }
  fbx.filter = "none";
  if (SGL.ok && SGL.active(c)) {
    if (c.grade?.lut && !SGL.has(c.grade.lut)) loadLut(c.grade.lut);
    const out = SGL.process(fitBuf, W, H, c);
    if (out) { fbx.clearRect(0, 0, W, H); fbx.drawImage(out, 0, 0); }
  }
  // 2) zoom + efekt katmanlari -> clipBuf
  let src = fitBuf;
  const zk = c.zoom?.length ? kfResolve(c.zoom, c.dur) : null;
  const tr = c.trans?.in ? SFX.transIn(c.trans.in, local, c.trans.dur || .35) : null;
  const zt = (zk ? kfAt(zk, "z", local, 1) : 1) * (tr?.zoom || 1);
  cbx.setTransform(1, 0, 0, 1, 0, 0); cbx.clearRect(0, 0, W, H);
  if (zt > 1.0005) {
    const z = Math.max(1, zt), cxk = zk ? kfAt(zk, "cx", local, .5) : .5, cyk = zk ? kfAt(zk, "cy", local, .5) : .5;
    const vw = W / z, vh = H / z, vx = clamp(cxk * W - vw / 2, 0, W - vw), vy = clamp(cyk * H - vh / 2, 0, H - vh);
    cbx.drawImage(fitBuf, vx, vy, vw, vh, 0, 0, W, H);
  } else cbx.drawImage(fitBuf, 0, 0);
  src = clipBuf;
  for (const id of fxOn) for (const ov of ST.cat.fx[id]?.ov || []) SFX.overlay(cbx, ov, W, H, t, local);
  if (tr?.flash) SFX.tint(cbx, W, H, "#fff", "lighter", tr.flash);
  if (tr?.leak) SFX.tint(cbx, W, H, "#ff9a3c", "lighter", tr.leak);
  if (tr?.dark) SFX.tint(cbx, W, H, "#000", "source-atop", tr.dark);
  if (tr?.pink) SFX.tint(cbx, W, H, "#ff4fa0", "lighter", tr.pink);
  if (tr?.roll) {   // VHS sarma: goruntu dikeyde kayar (ffmpeg: crop y=mod(ih*4*(1-u),ih)) + gren
    const oy = H * ((4 * tr.roll) % 1), cp = SFX.copy(cbx, W, H);
    cbx.clearRect(0, 0, W, H); cbx.drawImage(cp, 0, -oy); cbx.drawImage(cp, 0, H - oy); SFX.overlay(cbx, "grain", W, H, t, local);
  }
  if (tr?.rgb) SFX.overlay(cbx, "rgb-strong", W, H, t, local);
  // 3) donusum + saydamlik -> ana tuval
  let alpha = c.opacity ?? 1;
  const fi = Math.max(c.fadeIn || 0, c.trans?.in === "fade" ? (c.trans.dur || .35) : 0);
  if (fi > 0 && local < fi) alpha *= local / fi;
  if (c.fadeOut > 0 && c.dur - local < c.fadeOut) alpha *= Math.max(0, (c.dur - local) / c.fadeOut);
  const [shx, shy] = SFX.shakeOffset(fxOn.flatMap(id => ST.cat.fx[id]?.ov || []), t, W);
  alpha *= A.a;
  vctx.save();
  vctx.globalAlpha = clamp(alpha, 0, 1);
  const bl = Math.max(tr?.blur || 0, A.b * .45);
  if (bl > .05) vctx.filter = `blur(${bl * PS}px)`;
  if (tr?.mask) SFX.transMask(vctx, tr.mask, W, H);
  const sc = c.scale ?? 1, rot = ((c.rot || 0) + A.r + (tr?.rot || 0)) * Math.PI / 180;
  // contain'de bos kenarlar saydam: transform merkezi = cizilen goruntunun merkezi
  vctx.translate(W / 2 + ((c.x || 0) + A.x) * W + shx + (tr?.dx || 0) * W, H / 2 + ((c.y || 0) + A.y) * H + shy + (tr?.dy || 0) * H);
  if (rot) vctx.rotate(rot);
  const ksx = sc * A.s * A.sx * (tr?.sx || 1), ksy = sc * A.s * A.sy * (tr?.sy || 1);
  if (ksx !== 1 || ksy !== 1) vctx.scale(Math.max(1e-4, ksx), Math.max(1e-4, ksy));
  vctx.drawImage(src, -W / 2, -H / 2);
  if (tr?.pix > .01) { vctx.globalAlpha *= tr.pix; vctx.drawImage(SFX.pixelate(src, W, H, 1), -W / 2, -H / 2); }   // ffmpeg: pikselli kopya ile karisim
  vctx.restore();
}
const lutLoading = new Set();
async function loadLut(name) {
  if (lutLoading.has(name)) return; lutLoading.add(name);
  try { const r = await job("studio_lut_read", [name]); SGL.setLut(name, r.n, r.data); draw(); } catch (e) { toast("LUT okunamadı: " + name); }
}
let drawQ = false;
function draw() { if (!drawQ) { drawQ = true; requestAnimationFrame(() => { drawQ = false; drawNow(); }); } }
function drawNow() {
  if (!ST.p) return;
  const t = ST.t, W = PW, H = PH;
  vctx.setTransform(1, 0, 0, 1, 0, 0); vctx.filter = "none"; vctx.globalAlpha = 1; vctx.globalCompositeOperation = "source-over";
  vctx.fillStyle = ST.p.bg || "#000"; vctx.fillRect(0, 0, W, H);
  const vis = ST.p.clips.filter(c => trackOf(c).kind === "video" && !trackOf(c).hide && t >= c.start - 1e-4 && t < c.start + c.dur + transTail(c))
    .sort((a, b) => trackOrder(a.track) - trackOrder(b.track) || a.start - b.start);
  for (const c of vis) { try { drawClip(c, t); } catch (e) { /* cerceve hazir degil */ } }
  for (const c of activeAt(t, "fx").sort((a, b) => trackOrder(a.track) - trackOrder(b.track))) {
    const fx = ST.cat.fx[c.mode]; if (!fx) continue;
    const local = t - c.start;
    if (fx.css) { const cp = SFX.copy(vctx, W, H); vctx.save(); vctx.filter = fx.css; vctx.drawImage(cp, 0, 0); vctx.restore(); }
    const [sx, sy] = SFX.shakeOffset(fx.ov || [], t, W);
    if (sx || sy) { const cp = SFX.copy(vctx, W, H); vctx.save(); vctx.translate(sx, sy); vctx.scale(1.04, 1.04); vctx.translate(-W * .02, -H * .02); vctx.drawImage(cp, 0, 0); vctx.restore(); }
    for (const ov of fx.ov || []) SFX.overlay(vctx, ov, W, H, t, local);
  }
  $("#emptyHint").hidden = ST.p.clips.length > 0;
  updateTC();
}
function updateTC() {
  $("#tc").innerHTML = `<b>${fmt(ST.t)}</b> <span>/ ${fmt(projEnd())}</span>`;
  $("#playhead").style.left = (ST.t * ST.px) + "px";
}
// ---- oynatma saati
let wall0 = 0, t0 = 0, raf = 0;
function play(on = !ST.playing) {
  if (on && ST.t >= projEnd() - .02) ST.t = 0;
  ST.playing = on; $("#playBtn").textContent = on ? "❚❚" : "▶"; document.body.classList.toggle("playing", on);
  if (on) { wall0 = performance.now(); t0 = ST.t; syncMedia(ST.t, true); assTime(); raf = requestAnimationFrame(tick); }
  else { cancelAnimationFrame(raf); syncMedia(ST.t, true); assTime(); draw(); }
}
function tick(now) {
  if (!ST.playing) return;
  ST.t = t0 + (now - wall0) / 1000;
  const end = projEnd();
  if (ST.t >= end) { ST.t = end; play(false); return; }
  syncMedia(ST.t); drawNow(); followPlayhead();
  if ((now | 0) % 1000 < 17) assTime();
  raf = requestAnimationFrame(tick);
}
function seek(t) {
  ST.t = clamp(t, 0, Math.max(projEnd(), 0));
  if (ST.playing) { wall0 = performance.now(); t0 = ST.t; }
  syncMedia(ST.t, true); assTime(); draw(); renderHandles();
}
function followPlayhead() {
  const sc = $("#tlScroll"), x = ST.t * ST.px;
  if (x > sc.scrollLeft + sc.clientWidth - 60) sc.scrollLeft = x - 120;
  else if (x < sc.scrollLeft) sc.scrollLeft = Math.max(0, x - 40);
}

// ---------------------------------------------------------------- metin katmani: JASSUB (disa aktarimla ayni ASS)
let jas = null, assTimer = 0, assLast = "", jasBlob = null;
async function assInit() {
  if (!window.JASSUB || !ST.cat.jassub) return;
  try {
    jasBlob ||= URL.createObjectURL(new Blob([await (await fetch(ST.cat.jassub + "jassub-worker.js")).text()], { type: "text/javascript" }));
    assLast = await api.studio_ass({ ...ST.p, assets: {} });
    jas = new JASSUB({
      canvas: $("#assView"), subContent: assLast, workerUrl: jasBlob,
      wasmUrl: ST.cat.jassub + "jassub-worker.wasm", modernWasmUrl: ST.cat.jassub + "jassub-worker-modern.wasm",
      fonts: ST.cat.fontUrls || [], availableFonts: { "liberation sans": ST.cat.jassub + "default.woff2", ...Object.fromEntries(Object.entries(ST.fontMap || {}).map(([k, v]) => [k.toLowerCase(), v])) }, fallbackFont: "liberation sans",
      onDemandRender: false, targetFps: 30, prescaleFactor: 1, prescaleHeightLimit: 2160,
    });
    const r = $("#viewWrap").getBoundingClientRect(); assResize(Math.round(r.width), Math.round(r.height));
    assDirty(true);
  } catch (e) { console.warn("JASSUB", e); jas = null; }
}
window.jasReloadFonts = async () => { try { jas?.destroy(); } catch { } jas = null; assLast = ""; await assInit(); };
function assResize(w, h) {
  if (!jas || !ST.p) return;
  jas._videoWidth = ST.p.w; jas._videoHeight = ST.p.h;
  const k = devicePixelRatio || 1;
  try { jas.resize(Math.round(w * k), Math.round(h * k), 0, 0); } catch (e) { console.warn(e); }
  $("#assView").style.width = w + "px"; $("#assView").style.height = h + "px";
}
function assDirty(now = false) {
  clearTimeout(assTimer);
  assTimer = setTimeout(async () => {
    if (!jas || !ST.p) return;
    const p = { ...ST.p, assets: {} };
    const s = await api.studio_ass(p);
    if (s !== assLast) { assLast = s; jas.setTrack(s); assTime(); }
  }, now ? 0 : 180);
}
function assTime() { try { jas?.setCurrentTime(!ST.playing, ST.t, 1); } catch { } }

// ---------------------------------------------------------------- tuval ustu tutamaclar (secili gorsel klibi tasi/olcekle)
function renderHandles() {
  const box = $("#handles"); box.innerHTML = "";
  const c = selClips()[0]; if (!c || ST.sel.size !== 1) return;
  const k = trackOf(c).kind; if (!(k === "video" || (k === "text" && (c.text || c.subscribe)))) return;
  if (!(ST.t >= c.start && ST.t < c.start + c.dur)) return;
  const wr = $("#viewWrap").getBoundingClientRect(), W = wr.width, H = wr.height;
  let x, y, w, h;
  if (k === "video") {
    const a = assetOf(c); if (!a?.w) return;
    const fit = defaultFit(c), ar = a.w / a.h, var_ = ST.p.w / ST.p.h;
    let dw = W, dh = H;
    if (fit === "contain") { if (ar > var_) dh = W / ar; else dw = H * ar; }
    const sc = c.scale ?? 1; dw *= sc; dh *= sc;
    x = W / 2 + (c.x || 0) * W - dw / 2; y = H / 2 + (c.y || 0) * H - dh / 2; w = dw; h = dh;
  } else {
    const st = c.style || {}; const pos = st.pos || (c.subscribe ? "custom" : "bottom");
    const cx = pos === "custom" || c.subscribe ? (st.x ?? .5) : .5, cy = c.subscribe ? (st.y ?? .8) : pos === "top" ? .1 : pos === "center" ? .5 : pos === "bottom" ? .88 : (st.y ?? .5);
    w = W * .4; h = H * .1; x = cx * W - w / 2; y = cy * H - h / 2;
  }
  const hb = document.createElement("div"); hb.className = "hbox"; hb.style.cssText = `left:${x}px;top:${y}px;width:${w}px;height:${h}px;transform:rotate(${k === "video" ? c.rot || 0 : 0}deg)`;
  if (k === "video") hb.innerHTML = "<i></i>";
  box.appendChild(hb);
  hb.onpointerdown = e => {
    e.preventDefault(); hb.setPointerCapture(e.pointerId);
    const res = e.target.tagName === "I"; const x0 = e.clientX, y0 = e.clientY;
    const st0 = clone(c); let moved = false;
    hb.onpointermove = ev => {
      const dx = (ev.clientX - x0) / W, dy = (ev.clientY - y0) / H;
      if (!moved) { snap(); moved = true; }
      if (k === "video") {
        if (res) c.scale = +clamp((st0.scale ?? 1) * (1 + (dx + dy)), .05, 8).toFixed(3);
        else { c.x = +(st0.x || 0) + dx; c.y = +(st0.y || 0) + dy; if (Math.abs(c.x) < .01) c.x = 0; if (Math.abs(c.y) < .01) c.y = 0; }
      } else {
        c.style = { ...(c.style || {}) };
        const bx = c.subscribe ? (st0.style?.x ?? .5) : (st0.style?.pos === "custom" ? st0.style.x : .5);
        const pos0 = st0.style?.pos || "bottom";
        const by = c.subscribe ? (st0.style?.y ?? .8) : pos0 === "custom" ? st0.style.y : pos0 === "top" ? .1 : pos0 === "center" ? .5 : .88;
        if (!c.subscribe) c.style.pos = "custom";
        c.style.x = +clamp(bx + dx, 0, 1).toFixed(3); c.style.y = +clamp(by + dy, 0, 1).toFixed(3);
        assDirty();
      }
      draw(); renderHandles2(hb, c);
    };
    hb.onpointerup = () => { hb.onpointermove = null; if (moved) changed(false); renderHandles(); };
  };
}
function renderHandles2() { /* surukleme sirasinda kutu yeniden cizilmez; birakinca */ }

// ---------------------------------------------------------------- zaman cizelgesi
const lanes = $("#lanes"), heads = $("#tlHeads"), scroller = $("#tlScroll");
function laneH(t) { return TRACK_H[t.kind] || 48; }
function renderTimeline() {
  if (!ST.p) return;
  const end = Math.max(projEnd() + 30, scroller.clientWidth / ST.px + 5);
  const width = end * ST.px;
  $("#tlInner").style.width = width + "px";
  heads.innerHTML = ST.p.tracks.map(t => `<div class="th" style="--h:${laneH(t)}px" data-tid="${t.id}"><i style="background:${KIND_COL[t.kind]}"></i><b title="${esc(t.name)}">${esc(t.name)}</b>` +
    (t.kind === "video" || t.kind === "audio" ? `<button data-th="mute" class="${t.mute ? "on" : ""}" title="Sessiz">${t.mute ? "🔇" : "🔊"}</button>` : "") +
    `<button data-th="hide" class="${t.hide ? "on" : ""}" title="Gizle">${t.hide ? "◌" : "◉"}</button><button data-th="lock" class="${t.lock ? "on" : ""}" title="Kilitle">${t.lock ? "🔒" : "🔓"}</button></div>`).join("");
  const frag = document.createDocumentFragment();
  for (const t of ST.p.tracks) {
    const ln = document.createElement("div"); ln.className = "lane" + (t.lock ? " locked" : ""); ln.dataset.tid = t.id; ln.style.setProperty("--h", laneH(t) + "px");
    for (const c of ST.p.clips.filter(c => c.track === t.id)) ln.appendChild(clipEl(c, t));
    frag.appendChild(ln);
  }
  lanes.innerHTML = ""; lanes.appendChild(frag);
  for (const m of $$(".mk", $("#tlInner"))) m.remove();
  for (const m of ST.p.markers || []) { const d = document.createElement("div"); d.className = "mk " + (m.kind || ""); d.style.left = (m.t * ST.px) + "px"; $("#tlInner").appendChild(d); }
  drawRuler(); updateTC();
  const n = ST.sel.size; $("#selInfo").textContent = n ? `${n} klip seçili` : "";
}
function clipEl(c, t) {
  const k = clipKind(c), a = assetOf(c), el = document.createElement("div");
  el.className = `clip ${k}${ST.sel.has(c.id) ? " sel" : ""}`; el.dataset.cid = c.id;
  const w = Math.max(3, c.dur * ST.px);
  el.style.left = (c.start * ST.px) + "px"; el.style.width = w + "px";
  let label = "";
  if (k === "text") label = c.subscribe ? `🔔 ${ST.cat.subscribe[c.subscribe] || c.subscribe}` : c.graphic ? `◆ ${ST.cat.graphics?.[c.graphic] || c.graphic}` : c.words ? `≡ Altyazı (${c.words.length} kelime)` : "T " + (c.text || "");
  else if (k === "fx") label = "✦ " + (ST.cat.fx[c.mode]?.name || c.mode);
  else label = a?.name || "?";
  const tags = [];
  if ((c.speed || 1) !== 1) tags.push(`${c.speed}×`);
  if (c.ramp?.length) tags.push("⤳"); if (c.freeze) tags.push("❄"); if (c.key?.on) tags.push("▣"); if (c.grade && SGL.active({ grade: c.grade })) tags.push("◐"); if (c.afx?.length) tags.push("♪" + c.afx.length);
  if (c.fx?.length) tags.push("✦" + c.fx.length);
  if (c.zoom?.length) tags.push("⊕");
  if (c.reframe?.length) tags.push("▯");
  if (c.trans?.in && c.trans.in !== "none") tags.push("⇋");
  el.innerHTML = `<div class="lb">${esc(label)}${tags.length ? `<em>${tags.join(" ")}</em>` : ""}</div><div class="eg l"></div><div class="eg r"></div>`;
  const m = a ? ST.media[a.path] : null;
  if (k === "video" && m?.thumbs?.sprite) {
    const s = document.createElement("div"); s.className = "strip";
    const th = laneH(t) - 6 - 14, sp = c.speed || 1;
    // serit tum kaynagi kaplar: zaman cizelgesindeki uzunluga gerilir, klibin in noktasina kaydirilir
    const full = (a.dur || c.dur) / sp * ST.px, off = (c.in || 0) / sp * ST.px;
    s.style.backgroundImage = `url(${m.thumbs.sprite})`; s.style.backgroundSize = `${full}px ${th}px`; s.style.backgroundPosition = `${-off}px 0`;
    s.style.backgroundRepeat = "no-repeat";
    el.appendChild(s);
  } else if (k === "image" && a?.url) {
    const s = document.createElement("div"); s.className = "strip"; s.style.backgroundImage = `url("${a.url}")`; s.style.backgroundSize = "auto 100%"; el.appendChild(s);
  }
  if ((k === "audio" || (k === "video" && a?.audio)) && m?.peaks) el.appendChild(waveCanvas(c, m.peaks, w, laneH(t) - 6 - 14, k === "audio"));
  if (c.fadeIn > 0) { const f = document.createElement("div"); f.className = "fade"; f.style.width = c.fadeIn * ST.px + "px"; el.appendChild(f); }
  if (c.fadeOut > 0) { const f = document.createElement("div"); f.className = "fade o"; f.style.width = c.fadeOut * ST.px + "px"; el.appendChild(f); }
  for (const z of kfResolve(c.zoom || [], c.dur)) { const d = document.createElement("div"); d.className = "kfm"; d.style.left = z.t * ST.px + "px"; el.appendChild(d); }
  return el;
}
function waveCanvas(c, pk, w, h, big) {
  const cv = document.createElement("canvas"), W = Math.min(8000, Math.ceil(w)), sp = c.speed || 1;
  cv.width = W; cv.height = Math.max(8, h); cv.className = "wave"; cv.style.width = W + "px";
  const g = cv.getContext("2d"), hex = pk.peaks, per = pk.per_sec, n = hex.length / 2;
  g.fillStyle = big ? "#2EE6A6" : "rgba(46,230,166,.55)";
  const vol = Math.min(1.5, c.vol ?? 1);
  for (let x = 0; x < W; x++) {
    const tt = (c.in || 0) + (x / ST.px) * sp, i = Math.floor(tt * per);
    if (i < 0 || i >= n) continue;
    const v = parseInt(hex.substr(i * 2, 2), 16) / 255 * vol, hh = Math.max(1, v * cv.height * (big ? .95 : .6));
    g.fillRect(x, big ? (cv.height - hh) / 2 : cv.height - hh, 1, hh);
  }
  return cv;
}
function drawRuler() {
  const cv = $("#ruler canvas"), w = Math.min(32000, $("#tlInner").clientWidth), x0 = 0;
  cv.width = w; cv.height = 26; cv.style.width = w + "px";
  const g = cv.getContext("2d"); g.clearRect(0, 0, w, 26); g.fillStyle = "#8E86A3"; g.strokeStyle = "#3A2E58"; g.font = "10px Chakra Petch";
  const steps = [0.1, 0.25, .5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  const major = steps.find(s => s * ST.px >= 70) || 600, minor = major / 5;
  for (let t = 0; t * ST.px < w; t += minor) {
    const x = Math.round(t * ST.px) + .5 - x0, isM = Math.abs(t / major - Math.round(t / major)) < 1e-6;
    g.beginPath(); g.moveTo(x, isM ? 10 : 18); g.lineTo(x, 26); g.stroke();
    if (isM) { const tt = Math.round(t * 1000) / 1000; g.fillText(major < 1 ? tt + "s" : fmt(tt + 1e-6, false), x + 3, 10); }
  }
  g.fillStyle = "rgba(255,181,71,.8)";
  for (const m of ST.p.markers || []) g.fillRect(Math.round(m.t * ST.px) - 1, 20, 3, 6);
}
function tAt(clientX) { const r = scroller.getBoundingClientRect(); return Math.max(0, (clientX - r.left + scroller.scrollLeft) / ST.px); }
function laneAt(clientY) { return $$(".lane", lanes).find(l => { const r = l.getBoundingClientRect(); return clientY >= r.top && clientY < r.bottom; }); }
function snapTargets(exclude) {
  const ts = [ST.t, 0];
  for (const c of ST.p.clips) if (!exclude.has(c.id)) ts.push(c.start, c.start + c.dur);
  for (const m of ST.p.markers || []) ts.push(m.t);
  return ts;
}
function snapT(t, targets) {
  if (!ST.snap) return [t, null];
  let best = null, bd = 8 / ST.px;
  for (const s of targets) { const d = Math.abs(s - t); if (d < bd) { bd = d; best = s; } }
  return best == null ? [t, null] : [best, best];
}
function showSnap(t) { let l = $(".snapline"); if (t == null) { l?.remove(); return; } if (!l) { l = document.createElement("div"); l.className = "snapline"; $("#tlInner").appendChild(l); } l.style.left = t * ST.px + "px"; }
const KIND_OK = { video: ["video"], image: ["video"], audio: ["audio"], text: ["text"], fx: ["fx"] };

lanes.addEventListener("pointerdown", e => {
  const ce = e.target.closest(".clip");
  if (!ce) {   // bos alan: oynatma kafasi + secimi temizle / dikdortgen secim
    if (!e.shiftKey) ST.sel.clear();
    seek(tAt(e.clientX));
    const sx = e.clientX, sy = e.clientY, mq = document.createElement("div"); mq.id = "marquee";
    const ir = $("#tlInner").getBoundingClientRect();
    let on = false;
    const mv = ev => {
      if (!on && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) { seek(tAt(ev.clientX)); return; }
      if (!on) { on = true; $("#tlInner").appendChild(mq); }
      const x1 = Math.min(sx, ev.clientX), x2 = Math.max(sx, ev.clientX), y1 = Math.min(sy, ev.clientY), y2 = Math.max(sy, ev.clientY);
      mq.style.cssText = `left:${x1 - ir.left}px;top:${y1 - ir.top}px;width:${x2 - x1}px;height:${y2 - y1}px`;
      for (const el of $$(".clip", lanes)) { const r = el.getBoundingClientRect(); const hit = r.right > x1 && r.left < x2 && r.bottom > y1 && r.top < y2; el.classList.toggle("sel", hit || ST.sel.has(el.dataset.cid)); }
    };
    const up = () => {
      document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up);
      if (on) { for (const el of $$(".clip.sel", lanes)) ST.sel.add(el.dataset.cid); mq.remove(); }
      renderTimeline(); renderInsp(); renderHandles();
    };
    document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    return;
  }
  const c = ST.p.clips.find(x => x.id === ce.dataset.cid); if (!c) return;
  if (trackOf(c).lock) return;
  e.preventDefault();
  if (e.shiftKey || e.ctrlKey) { ST.sel.has(c.id) ? ST.sel.delete(c.id) : ST.sel.add(c.id); }
  else if (!ST.sel.has(c.id)) { ST.sel = new Set([c.id]); }
  const edge = e.target.classList.contains("eg") ? (e.target.classList.contains("l") ? "l" : "r") : "";
  const group = selClips(), st0 = group.map(x => ({ c: x, start: x.start, dur: x.dur, in: x.in || 0, track: x.track }));
  const x0 = e.clientX, tg = snapTargets(new Set(group.map(x => x.id)));
  let moved = false;
  renderInsp();
  for (const el of $$(".clip", lanes)) el.classList.toggle("sel", ST.sel.has(el.dataset.cid));
  const mv = ev => {
    const dx = (ev.clientX - x0) / ST.px;
    if (!moved && Math.abs(ev.clientX - x0) < 3) return;
    if (!moved) { snap(); moved = true; }
    if (edge) {
      const s0 = st0.find(s => s.c === c), a = assetOf(c), sp = c.speed || 1;
      const maxSrc = a && (a.kind !== "image" || a.gif) ? a.dur : Infinity;
      if (edge === "l") {
        let ns = s0.start + dx; const [sn, hit] = snapT(ns, tg); ns = sn; showSnap(hit);
        let d = ns - s0.start;
        d = clamp(d, -(maxSrc === Infinity || trackOf(c).kind === "text" || trackOf(c).kind === "fx" ? s0.start : Math.min(s0.start, s0.in / sp)), s0.dur - .05);
        c.start = s0.start + d; c.dur = s0.dur - d; if (a) c.in = s0.in + d * sp;
        if (c.words) c.words = st0Words(c, d);
      } else {
        let ne = s0.start + s0.dur + dx; const [sn, hit] = snapT(ne, tg); ne = sn; showSnap(hit);
        const maxDur = maxSrc === Infinity ? 1e6 : (maxSrc - s0.in) / sp;
        c.dur = clamp(ne - s0.start, .05, maxDur);
      }
    } else {
      // tasima: grubun en solu yapisir
      let lead = st0.reduce((m, s) => s.start < m.start ? s : m, st0[0]);
      let ns = lead.start + dx, best = null;
      for (const cand of [ns, ns + lead.dur]) { const [s2, hit] = snapT(cand, tg); if (hit != null) { best = hit - (cand - ns); showSnap(hit); break; } }
      if (best == null) showSnap(null);
      const d = Math.max(-Math.min(...st0.map(s => s.start)), (best ?? ns) - lead.start);
      const ln = laneAt(ev.clientY), tid = ln?.dataset.tid;
      for (const s of st0) {
        s.c.start = +(s.start + d).toFixed(4);
        if (group.length === 1 && tid && tid !== s.c.track) {
          const tk = ST.p.tracks.find(t => t.id === tid);
          if (tk && !tk.lock && KIND_OK[clipKind(s.c)]?.includes(tk.kind)) s.c.track = tid;
        }
      }
    }
    for (const s of st0) { const el = lanes.querySelector(`[data-cid="${s.c.id}"]`); if (!el) continue;
      if (el.parentElement.dataset.tid !== s.c.track) lanes.querySelector(`.lane[data-tid="${s.c.track}"]`)?.appendChild(el);
      el.style.left = s.c.start * ST.px + "px"; el.style.width = Math.max(3, s.c.dur * ST.px) + "px"; }
    draw();
  };
  const up = () => {
    document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); showSnap(null);
    if (moved) { for (const s of st0) if (overlaps(s.c)) resolveOverlap(s.c); changed(); }
    else { renderTimeline(); renderHandles(); if (!edge && !e.shiftKey) seekIfOutside(c, e); }
  };
  document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
});
function st0Words(c, d) { return c.words; }   // altyazi kelimeleri klip basina gore: sol kirpmada kaydir
function seekIfOutside(c, e) { seek(tAt(e.clientX)); }
lanes.addEventListener("dblclick", e => { const ce = e.target.closest(".clip"); if (ce) { ST.sel = new Set([ce.dataset.cid]); window.focusInsp?.(); } });
$("#ruler").addEventListener("pointerdown", e => {
  seek(tAt(e.clientX));
  const mv = ev => seek(tAt(ev.clientX)), up = () => { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); };
  document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
});
heads.addEventListener("click", e => {
  const b = e.target.closest("[data-th]"), row = e.target.closest(".th"); if (!row) return;
  const t = ST.p.tracks.find(x => x.id === row.dataset.tid);
  if (b) { snap(); t[b.dataset.th] = !t[b.dataset.th]; changed(); return; }
});
heads.addEventListener("dblclick", async e => {
  const row = e.target.closest(".th"); if (!row) return;
  const t = ST.p.tracks.find(x => x.id === row.dataset.tid);
  const n = await promptText("İz adı", t.name, "Boş iz silinebilir: adı sil ve Tamam'a bas."); if (n == null) return;
  snap();
  if (!n.trim() && !ST.p.clips.some(c => c.track === t.id)) ST.p.tracks.splice(ST.p.tracks.indexOf(t), 1); else t.name = n.trim() || t.name;
  changed();
});
scroller.addEventListener("scroll", () => { heads.scrollTop = scroller.scrollTop; });
scroller.addEventListener("wheel", e => {
  if (e.ctrlKey || e.altKey) { e.preventDefault(); const t = tAt(e.clientX), dx = e.clientX - scroller.getBoundingClientRect().left; setZoom(ST.px * (e.deltaY < 0 ? 1.18 : 1 / 1.18)); scroller.scrollLeft = t * ST.px - dx; }
  else if (!e.shiftKey && Math.abs(e.deltaY) > Math.abs(e.deltaX) && !e.target.closest(".lane")) { }
}, { passive: false });
function setZoom(px) { ST.px = clamp(px, 4, 800); $("#tlZoom").value = Math.round(ST.px); renderTimeline(); }
// medya kutusundan surukle-birak
lanes.addEventListener("dragover", e => {
  if (!e.dataTransfer.types.includes("text/kami-asset") && !e.dataTransfer.types.includes("text/kami-item")) return;
  e.preventDefault(); $$(".lane.drop").forEach(l => l.classList.remove("drop")); laneAt(e.clientY)?.classList.add("drop");
});
lanes.addEventListener("dragleave", () => $$(".lane.drop").forEach(l => l.classList.remove("drop")));
lanes.addEventListener("drop", e => {
  $$(".lane.drop").forEach(l => l.classList.remove("drop"));
  const aid = e.dataTransfer.getData("text/kami-asset"), item = e.dataTransfer.getData("text/kami-item");
  if (!aid && !item) return;
  e.preventDefault();
  const t = snapT(tAt(e.clientX), snapTargets(new Set()))[0], ln = laneAt(e.clientY);
  if (item) { window.dropItem?.(JSON.parse(item), t, ln?.dataset.tid); return; }
  dropAsset(aid, t, ln?.dataset.tid);
});
// isletim sisteminden dosya birakma: WebView2 dosyayi tarayicida (Edge) acmasin; yollar pywebview drop olayindan gelir
const isFiles = e => [...(e.dataTransfer?.types || [])].includes("Files");
document.addEventListener("dragover", e => {
  if (!isFiles(e)) return;
  e.preventDefault(); e.dataTransfer.dropEffect = "copy";
  document.body.classList.add("osdrag");
  $$(".lane.drop").forEach(l => l.classList.remove("drop"));
  if (e.target.closest?.("#tl")) laneAt(e.clientY)?.classList.add("drop");
});
document.addEventListener("dragleave", e => { if (!e.relatedTarget) { document.body.classList.remove("osdrag"); $$(".lane.drop").forEach(l => l.classList.remove("drop")); } });
document.addEventListener("drop", e => {
  document.body.classList.remove("osdrag");
  if (!isFiles(e)) return;
  e.preventDefault();
  $$(".lane.drop").forEach(l => l.classList.remove("drop"));
  ST.osDrop = e.target.closest?.("#tl .lanes, #tl") ? { at: Date.now(), t: Math.max(0, tAt(e.clientX)), tid: laneAt(e.clientY)?.dataset.tid } : null;
});
function dropAsset(aid, t, tid) {
  const a = ST.p.assets[aid]; if (!a) return;
  const want = a.kind === "audio" ? "audio" : "video";
  let tk = ST.p.tracks.find(x => x.id === tid);
  if (!tk || tk.kind !== want) tk = ST.p.tracks.find(x => x.id === trackFor(want));
  snap();
  const c = addClip({ asset: aid, track: tk.id, start: t, dur: a.dur, in: 0 });
  if (a.kind === "image" && tk.id !== "v1") { c.fit = "contain"; }
  resolveOverlap(c); ST.sel = new Set([c.id]); changed();
}

// ---------------------------------------------------------------- denetci
function fld(label, key, min, max, step, val, unit = "") {
  return `<label class="fld"><span>${label}</span><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${val}"><input type="number" class="num" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${+(+val).toFixed(3)}"></label>`;
}
function sel(label, key, opts, val) { return `<label class="fld w2"><span>${label}</span><select class="in" data-k="${key}">${Object.entries(opts).map(([k, v]) => `<option value="${k}"${k === String(val) ? " selected" : ""}>${esc(v)}</option>`).join("")}</select></label>`; }
function color(label, key, val) { return `<label class="fld w2"><span>${label}</span><input type="color" data-k="${key}" value="${val || "#ffffff"}"></label>`; }
function chk(label, key, val) { return `<label class="fld w2"><span>${label}</span><input type="checkbox" data-k="${key}" ${val ? "checked" : ""} style="justify-self:start;accent-color:var(--violet)"></label>`; }
function getK(c, k) { return k.split(".").reduce((o, p) => o?.[p], c); }
function setK(c, k, v) { const ps = k.split("."); let o = c; for (const p of ps.slice(0, -1)) o = (o[p] ||= {}); if (v === "" || v == null) delete o[ps.at(-1)]; else o[ps.at(-1)] = v; }
function renderInsp() {
  const box = $("#insp"); if (!ST.p) return;
  const cs = selClips();
  if (!cs.length) { box.innerHTML = projInsp(); return; }
  if (cs.length > 1) { box.innerHTML = `<div class="ph"><b>${cs.length} klip</b></div>${multiInsp(cs)}`; return; }
  const c = cs[0], k = clipKind(c), a = assetOf(c);
  let h = `<div class="ph"><b>${{ video: "Video", image: "Görsel", audio: "Ses", text: c.subscribe ? "Abone" : c.words ? "Altyazı" : "Metin", fx: "Efekt" }[k]}</b><span class="sp"></span><span class="hint">${fmt(c.start)} · ${c.dur.toFixed(2)} sn</span></div>`;
  if (a) h += `<div class="hint" style="margin-top:-4px">${esc(a.name)}${a.missing ? ' <b style="color:var(--red)">(dosya yok)</b>' : ""}</div>`;
  if (k === "video" || k === "image") {
    h += `<div class="sec">Görüntü</div>` + `<div class="fld w2"><span>Sığdır</span><div class="seg" data-seg="fit">${[["cover", "Kapla"], ["contain", "Sığdır"], ["stretch", "Uzat"]].map(([v, l]) => `<button data-v="${v}" class="${defaultFit(c) === v ? "on" : ""}">${l}</button>`).join("")}</div></div>` +
      fld("Ölçek", "scale", .05, 4, .01, c.scale ?? 1) + fld("Konum X", "x", -1, 1, .005, c.x || 0) + fld("Konum Y", "y", -1, 1, .005, c.y || 0) +
      fld("Döndür", "rot", -180, 180, 1, c.rot || 0) + fld("Opaklık", "opacity", 0, 1, .01, c.opacity ?? 1);
  }
  if (k === "video" || k === "audio") {
    h += `<div class="sec">Hız</div>` + fld("Hız", "speed", .1, 8, .05, c.speed || 1) +
      `<div class="row tight">${[.25, .5, 1, 1.5, 2, 4].map(v => `<button class="tb" data-speed="${v}">${v}×</button>`).join("")}</div>`;
    if (k === "video") h += `<div class="sec">Hız rampası</div><div class="grid3 ramps">${Object.entries(RAMPS).map(([id, r]) => `<button class="tb${(id === "none" && !c.ramp) ? " on" : ""}" data-ramp="${id}">${r.n}</button>`).join("")}</div>` +
      (c.ramp ? `<canvas id="rampCv" width="270" height="96" title="Noktayı sürükle · çift tık: nokta ekle · sağ tık: sil"></canvas><div class="hint">Yukarı = hızlı, aşağı = yavaş. Klip süresi kendiliğinden ayarlanır.</div>` : "");
  }
  if (k === "audio" || (k === "video" && a?.audio)) {
    h += `<div class="sec">Ses</div>` + fld("Ses düzeyi", "vol", 0, 2, .01, c.vol ?? 1) + fld("Açılış", "fadeIn", 0, 5, .05, c.fadeIn || 0) + fld("Kapanış", "fadeOut", 0, 5, .05, c.fadeOut || 0);
  } else if (k === "video" || k === "image") h += `<div class="sec">Belir / kaybol</div>` + fld("Açılış", "fadeIn", 0, 5, .05, c.fadeIn || 0) + fld("Kapanış", "fadeOut", 0, 5, .05, c.fadeOut || 0);
  if (k === "video" || k === "image") {
    const ad = c.adj || {};
    h += `<div class="sec">Renk</div>` + fld("Parlaklık", "adj.bri", -50, 50, 1, ad.bri || 0) + fld("Kontrast", "adj.con", -50, 80, 1, ad.con || 0) +
      fld("Doygunluk", "adj.sat", -100, 150, 1, ad.sat || 0) + fld("Ton", "adj.hue", -180, 180, 1, ad.hue || 0) + fld("Sıcaklık", "adj.temp", -100, 100, 1, ad.temp || 0) + fld("Bulanık", "adj.blur", 0, 20, .5, ad.blur || 0);
    h += window.animBox ? animBox(c, "clip") : "";
    h += `<div class="sec">Efektler</div>` + (window.fxRows ? fxRows(c) : "");
    h += `<div class="sec">Giriş geçişi</div>` + sel("Geçiş", "trans.in", ST.cat.trans, c.trans?.in || "none") + fld("Süre", "trans.dur", .1, 2, .05, c.trans?.dur || .35) +
        chk("Önceki klip altta devam etsin (A→B)", "trans.over", c.trans?.over !== false);
    h += zoomInsp(c);
    h += `<div class="sec">Dikey çerçeve</div><div class="row"><button class="tb" data-a2="reframe">▯ Yüzü takip et</button>${c.reframe?.length ? '<button class="tb" data-a2="unreframe">Kaldır</button>' : ""}</div>`;
  }
  if (k === "audio" || (k === "video" && a?.audio)) h += `<div class="sec">Ses düzeltme</div><div class="chips">${Object.entries(ST.cat.afx || {}).map(([id, n]) => `<button class="tb${(c.afx || []).includes(id) ? " on" : ""}" data-afx="${id}" style="font-size:11px;padding:4px 8px">${esc(n)}</button>`).join("")}</div><div class="hint">Önizlemede duyulmaz, dışa aktarımda uygulanır. Sesin altına müzik girsin istiyorsan müzik izinde “Kıs” (Ses sayfası).</div>`;
  if (k === "video" || k === "image") {
    const ky = c.key || {};
    h += `<div class="sec">Perde (yeşil/mavi) · arka plan</div>` + chk("Perdeyi sil", "key.on", ky.on) +
      (ky.on ? color("Perde rengi", "key.color", ky.color || "#00ff00") + fld("Benzerlik", "key.sim", .01, .6, .005, ky.sim ?? .15) + fld("Yumuşaklık", "key.smooth", 0, .4, .005, ky.smooth ?? .08) + chk("Taşmayı temizle", "key.spill", ky.spill ?? true) +
        `<div class="row"><button class="tb" data-a2="pipette">⌖ Pipet: önizlemeden renk al</button></div>` : "") +
      (k === "video" ? `<div class="row"><button class="tb" data-a2="matte">✂ Yapay zekayla arka planı sil</button></div>` : "") +
      `<div class="row"><button class="tb" data-a2="tocolor">◐ Renk sayfasında düzenle</button></div>`;
  }
  if (k === "audio" || k === "video") h += `<div class="sec">Akıllı</div><div class="row"><button class="tb" data-a2="silence">Sessizlikleri kırp</button><button class="tb" data-a2="beats">Vuruşları bul</button></div>`;
  if (k === "text") h += textInsp(c);
  if (k === "fx") {
    const opts = Object.fromEntries(Object.entries(ST.cat.fx).map(([id, f]) => [id, `${f.pack} · ${f.name}`]));
    h += `<div class="sec">Mod</div>` + sel("Efekt", "mode", opts, c.mode);
    if (["vhs", "cctv", "nightvision", "found", "bodycam"].includes(c.mode)) h += `<label class="fld w2"><span>Tarih</span><input class="in" data-k="date" value="${esc(c.date || "")}" placeholder="bugün"></label>`;
    if (c.mode === "cctv") h += `<label class="fld w2"><span>Kamera adı</span><input class="in" data-k="cam" value="${esc(c.cam || "CAM 03")}"></label>`;
  }
  h += `<div class="sec">Zaman</div>` + `<div class="grid2"><label class="fld w2" style="grid-template-columns:44px 1fr"><span>Başla</span><input type="number" class="in" data-k="start" step="0.01" value="${c.start.toFixed(2)}"></label><label class="fld w2" style="grid-template-columns:44px 1fr"><span>Süre</span><input type="number" class="in" data-k="dur" step="0.01" value="${c.dur.toFixed(2)}"></label></div>`;
  box.innerHTML = h;
  rampCanvas(c);
}
function zoomInsp(c) {
  const kf = kfResolve(c.zoom || [], c.dur);
  return `<div class="sec">Zoom</div><div class="kfl">${kf.map((k, i) => `<div class="kf"><b>${k.t.toFixed(2)}s</b><span>×${(+k.z || 1).toFixed(2)}${k.cx != null ? ` · ${(+k.cx).toFixed(2)},${(+(k.cy ?? .5)).toFixed(2)}` : ""}${k.e ? " · " + k.e : ""}</span><button data-kfdel="${i}" title="Sil">✕</button></div>`).join("") || '<span class="hint">Oynatma kafasına kare ekle ya da Zoom panelinden şablon seç.</span>'}</div>` +
    `<div class="fld"><span>Yakınlık</span><input type="range" id="zz" min="1" max="3" step="0.01" value="${(ST.t >= c.start && ST.t <= c.start + c.dur && kf.length) ? kfAt(kf, "z", ST.t - c.start, 1).toFixed(2) : 1.3}"><input class="num" id="zzn" readonly value=""></div>` +
    `<div class="fld"><span>Merkez X</span><input type="range" id="zcx" min="0" max="1" step="0.01" value="0.5"><span></span></div><div class="fld"><span>Merkez Y</span><input type="range" id="zcy" min="0" max="1" step="0.01" value="0.5"><span></span></div>` +
    `<div class="row"><select class="tb" id="zease"><option value="">Doğrusal</option><option value="out" selected>Hızlı başla</option><option value="in">Yavaş başla</option><option value="inout">Yumuşak</option></select><button class="tb" data-a2="kfadd">◆ Kare ekle</button></div>` +
    `<div class="row"><button class="tb" data-a2="kfsave" ${kf.length ? "" : "disabled"}>Şablon kaydet</button><button class="tb" data-a2="kfclear" ${kf.length ? "" : "disabled"}>Temizle</button></div>`;
}
function textInsp(c) {
  const st = c.style || {};
  const fonts = Object.fromEntries((ST.cat.fonts || []).map(f => [f, f]));
  const fontIn = (key, val) => `<label class="fld w2"><span>Font</span><input class="in" list="fontList" data-k="${key}" value="${esc(val)}" spellcheck="false"></label>`;
  let h = "";
  if (c.graphic) {
    const G = c.graphic;
    h += `<div class="sec">Grafik</div>` + sel("Tür", "graphic", ST.cat.graphics || {}, G) +
      (["lower", "lower-min", "location", "chapter", "callout", "highlight", "quote"].includes(G) ? `<label class="fld w2"><span>Başlık</span><input class="in" data-k="style.title" value="${esc(st.title || "")}"></label>` : "") +
      (["lower", "lower-min", "location", "quote"].includes(G) ? `<label class="fld w2"><span>Alt yazı</span><input class="in" data-k="style.sub" value="${esc(st.sub || "")}"></label>` : "") +
      (G === "chapter" ? `<label class="fld w2"><span>Numara</span><input class="in" data-k="style.num" value="${esc(st.num || "01")}"></label>` : "") +
      (G === "counter" ? `<label class="fld w2"><span>Başla</span><input type="number" class="in" data-k="style.from" value="${st.from ?? 0}"></label><label class="fld w2"><span>Bitir</span><input type="number" class="in" data-k="style.to" value="${st.to ?? 1000}"></label><label class="fld w2"><span>Ön ek</span><input class="in" data-k="style.prefix" value="${esc(st.prefix || "")}"></label><label class="fld w2"><span>Son ek</span><input class="in" data-k="style.suffix" value="${esc(st.suffix || "")}"></label>` : "") +
      (G === "endscreen" ? `<label class="fld w2"><span>Kutu 1</span><input class="in" data-k="style.v1" value="${esc(st.v1 || "Önerilen video")}"></label><label class="fld w2"><span>Kutu 2</span><input class="in" data-k="style.v2" value="${esc(st.v2 || "Son video")}"></label>` : "") +
      color("Vurgu rengi", "style.color", st.color || (G === "highlight" ? "#FFE600" : "#8B5CF6")) + fld("Boyut", "style.size", 30, 250, 1, st.size ?? 100) +
      fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .5) + fontIn("style.font", st.font || "Segoe UI");
    return h;
  }
  if (c.subscribe) {
    h += `<div class="sec">Abone animasyonu</div>` + sel("Tür", "subscribe", ST.cat.subscribe, c.subscribe) +
      `<label class="fld w2"><span>Yazı</span><input class="in" data-k="style.label" value="${esc(st.label || "ABONE OL")}"></label>` +
      `<label class="fld w2"><span>Sonra</span><input class="in" data-k="style.done" value="${esc(st.done || "ABONE OLUNDU")}"></label>` +
      color("Renk", "style.color", st.color || "#ff1f1f") + fld("Boyut", "style.size", 30, 250, 1, st.size ?? 100) +
      fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .8) + fontIn("style.font", st.font || (c.subscribe.startsWith("yt") || c.subscribe === "channel" ? "Segoe UI" : "Chakra Petch")) +
      (c.subscribe === "channel" ? `<label class="fld w2"><span>Kanal</span><input class="in" data-k="style.channel" value="${esc(st.channel || "Kanal Adı")}"></label><label class="fld w2"><span>Abone</span><input class="in" data-k="style.subs" value="${esc(st.subs || "1,2 Mn abone")}"></label>` + color("Avatar", "style.avatarColor", st.avatarColor || "#8B5CF6") : "") +
      (c.subscribe === "social" ? ["yt", "ig", "tt"].map(x => `<label class="fld w2"><span>${{ yt: "YouTube", ig: "Instagram", tt: "TikTok" }[x]}</span><input class="in" data-k="style.${x}" value="${esc(st[x] ?? "@kanal")}"></label>`).join("") : "");
    return h;
  }
  if (c.words) {
    h += `<div class="sec">Altyazı stili</div>` + sel("Stil", "style.caption", ST.cat.captions, st.caption || "hormozi") +
      color("Vurgu", "style.highlight", st.highlight || "#FFE600") + fld("Satırda kelime", "style.perLine", 1, 8, 1, st.perLine ?? (st.caption === "word" ? 1 : 3)) +
      chk("BÜYÜK HARF", "style.upper", st.upper ?? ["hormozi", "word"].includes(st.caption || "hormozi")) + fld("Dikey konum", "style.y", .05, .95, .005, st.y ?? .72);
    h += `<div class="sec">Kelimeler</div><textarea class="in" id="wordsEd" spellcheck="false" title="Yazım düzelt: kelime sayısı aynı kalırsa zamanlar korunur">${esc(c.words.map(w => w.w).join(" "))}</textarea><div class="row"><button class="tb" data-a2="words">Uygula</button></div>`;
  } else {
    h += `<div class="sec">Metin</div><textarea class="in" data-k="text" spellcheck="false">${esc(c.text || "")}</textarea>` +
      `<div class="fld w2"><span>Konum</span><div class="seg" data-seg="style.pos">${[["top", "Üst"], ["center", "Orta"], ["bottom", "Alt"], ["custom", "Serbest"]].map(([v, l]) => `<button data-v="${v}" class="${(st.pos || "bottom") === v ? "on" : ""}">${l}</button>`).join("")}</div></div>` +
      ((st.pos || "bottom") === "custom" ? fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .5) : "") +
      (window.animBox ? animBox(c, "text") : "");
  }
  h += `<div class="sec">Yazı tipi</div>` + fontIn("style.font", st.font || "Chakra Petch") + fld("Boyut", "style.size", 2, 30, .1, st.size ?? (c.words ? 7.5 : 7)) +
    color("Renk", "style.color", st.color || "#ffffff") + color("Kenar rengi", "style.outlineColor", st.outlineColor || "#000000") + fld("Kenar", "style.outline", 0, 20, .5, st.outline ?? 6) +
    fld("Gölge", "style.shadow", 0, 20, .5, st.shadow || 0) + chk("Parlama", "style.glow", st.glow) + (st.glow ? color("Parlama rengi", "style.glowColor", st.glowColor || st.color || "#ffffff") : "") +
    chk("Kalın", "style.bold", st.bold ?? true) + chk("İtalik", "style.italic", st.italic) + chk("Kutulu", "style.box", st.box) + (st.box ? color("Kutu rengi", "style.boxColor", st.boxColor || "#000000") : "") +
    fld("Harf aralığı", "style.spacing", -10, 40, 1, st.spacing || 0) + fld("Eğim", "style.rot", -45, 45, 1, st.rot || 0);
  return h;
}
function projInsp() {
  return `<div class="ph"><b>Proje</b></div>` +
    `<label class="fld w2"><span>Ad</span><input class="in" data-pk="name" value="${esc(ST.p.name)}"></label>` +
    `<label class="fld w2"><span>Genişlik</span><input type="number" class="in" data-pk="w" value="${ST.p.w}"></label>` +
    `<label class="fld w2"><span>Yükseklik</span><input type="number" class="in" data-pk="h" value="${ST.p.h}"></label>` +
    `<label class="fld w2"><span>FPS</span><select class="in" data-pk="fps">${[24, 25, 30, 50, 60].map(f => `<option${f === ST.p.fps ? " selected" : ""}>${f}</option>`).join("")}</select></label>` +
    `<label class="fld w2"><span>Arka plan</span><input type="color" data-pk="bg" value="${ST.p.bg || "#000000"}"></label>` +
    `<div class="sec">Özet</div><div class="hint">${ST.p.clips.length} klip · ${Object.keys(ST.p.assets).length} medya · ${fmt(projEnd())}<br>${(ST.p.markers || []).length} işaret ${(ST.p.markers || []).length ? '· <a href="#" data-a2="clearmk" style="color:var(--em)">temizle</a>' : ""}</div>` +
    `<div class="sec">İpucu</div><div class="hint">Klibe tıkla: ayarları burada. Çift tıkla: odaklan.<br>Boşluk oynat · S böl · Del sil · Ctrl+Z geri · 1-9 hızlı ses.<br>Kami AI (MCP) bağlıysa ona “şu videoyu kes, altyazı ekle” diyebilirsin; değişiklikler burada anında görünür.</div>` +
    (ST.path ? `<div class="sec">Dosya</div><div class="hint" style="word-break:break-all">${esc(ST.path)}</div>` : "");
}
function multiInsp(cs) {
  return `<div class="hint">Toplu ayar: değerler seçili tüm kliplere uygulanır.</div>` + fld("Ses düzeyi", "vol", 0, 2, .01, cs[0].vol ?? 1) + fld("Hız", "speed", .1, 8, .05, cs[0].speed || 1) +
    fld("Opaklık", "opacity", 0, 1, .01, cs[0].opacity ?? 1) + `<div class="row"><button class="tb" data-a2="align">Uç uca diz</button><button class="tb" data-a2="del">Sil</button></div>`;
}
const RAMPS = {
  none: { n: "Yok", p: null },
  montage: { n: "Montaj", p: [{ p: 0, s: 3 }, { p: .4, s: .35 }, { p: .6, s: .35 }, { p: 1, s: 3 }] },
  slow: { n: "Yavaşla", p: [{ p: 0, s: 1 }, { p: .5, s: 1 }, { p: 1, s: .3 }] },
  fast: { n: "Hızlan", p: [{ p: 0, s: .4 }, { p: 1, s: 3 }] },
  bullet: { n: "Bullet time", p: [{ p: 0, s: 1.5 }, { p: .45, s: .2 }, { p: .55, s: .2 }, { p: 1, s: 1.5 }] },
  flash: { n: "Flaş hız", p: [{ p: 0, s: 4 }, { p: .5, s: 1 }, { p: 1, s: 4 }] },
  hit: { n: "Vuruş anı", p: [{ p: 0, s: 1 }, { p: .47, s: 1.2 }, { p: .5, s: .22 }, { p: .7, s: .22 }, { p: .73, s: 1.2 }, { p: 1, s: 1 }] },
  speedup: { n: "Hızlı giriş", p: [{ p: 0, s: 5 }, { p: .3, s: 1 }, { p: 1, s: 1 }] },
  slowend: { n: "Ağır çıkış", p: [{ p: 0, s: 1 }, { p: .7, s: 1 }, { p: 1, s: .25 }] },
};
function drawRamp(c) {
  const cv = $("#rampCv"); if (!cv || !c.ramp) return;
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, y = s => H - 8 - (Math.log2(s) + 3.3) / 6.3 * (H - 16);
  g.clearRect(0, 0, W, H); g.fillStyle = "#07050C"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "rgba(255,255,255,.08)"; for (const s of [.25, .5, 1, 2, 4]) { g.beginPath(); g.moveTo(0, y(s)); g.lineTo(W, y(s)); g.stroke(); }
  g.fillStyle = "#8E86A3"; g.font = "9px Chakra Petch"; for (const s of [.25, 1, 4]) g.fillText(s + "×", 3, y(s) - 2);
  g.strokeStyle = "#2EE6A6"; g.lineWidth = 2; g.beginPath();
  for (let i = 0; i <= 100; i++) { const p = i / 100, X = p * W, Y = y(rampSpeed(c.ramp, p)); i ? g.lineTo(X, Y) : g.moveTo(X, Y); }
  g.stroke(); g.fillStyle = "#FFB547"; for (const q of c.ramp) { g.beginPath(); g.arc(q.p * W, y(q.s), 4.5, 0, 7); g.fill(); }
}
function rampCanvas(c) {
  const cv = $("#rampCv"); if (!cv) return;
  drawRamp(c);
  const W = cv.width, H = cv.height, sOf = Y => clamp(2 ** ((H - 8 - Y) / (H - 16) * 6.3 - 3.3), .1, 8), y = s => H - 8 - (Math.log2(s) + 3.3) / 6.3 * (H - 16);
  const pos = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
  cv.oncontextmenu = e => { e.preventDefault(); const [X, Y] = pos(e); const pts = c.ramp; const i = pts.findIndex(q => Math.hypot(q.p * W - X, y(q.s) - Y) < 9); if (i > 0 && i < pts.length - 1) { snap(); pts.splice(i, 1); rampApply(c, pts); changed(); } };
  cv.ondblclick = e => { const [X, Y] = pos(e); snap(); const pts = [...c.ramp, { p: clamp(X / W, .01, .99), s: +sOf(Y).toFixed(2) }].sort((a, b) => a.p - b.p); rampApply(c, pts); changed(); };
  cv.onpointerdown = e => {
    const [X, Y] = pos(e), pts = c.ramp, i = pts.findIndex(q => Math.hypot(q.p * W - X, y(q.s) - Y) < 9); if (i < 0) return;
    cv.setPointerCapture(e.pointerId); snap();
    cv.onpointermove = ev => { const [x2, y2] = pos(ev); const q = pts[i];
      if (i > 0 && i < pts.length - 1) q.p = +clamp(x2 / W, pts[i - 1].p + .01, pts[i + 1].p - .01).toFixed(3);
      q.s = +sOf(y2).toFixed(2); rampApply(c, pts); drawRamp(c); draw(); };
    cv.onpointerup = () => { cv.onpointermove = null; changed(); };
  };
}
let pipette = false;
$("#view").addEventListener("click", e => {
  if (!pipette) return; pipette = false; document.body.style.cursor = "";
  const r = view.getBoundingClientRect(), x = Math.round((e.clientX - r.left) * PW / r.width), y = Math.round((e.clientY - r.top) * PH / r.height);
  const c = selClips()[0]; if (!c) return;
  const keyOn = c.key?.on; if (keyOn) c.key.on = false; drawNow();
  const d = vctx.getImageData(x, y, 1, 1).data; if (keyOn) c.key.on = true;
  snap(); c.key = { ...(c.key || {}), on: true, color: "#" + [d[0], d[1], d[2]].map(v => v.toString(16).padStart(2, "0")).join("") }; changed();
});
let inspSnap = false;
$("#insp").addEventListener("pointerdown", () => { inspSnap = false; });
function inspSet(k, v, live) {
  const cs = selClips(); if (!cs.length) return;
  if (!inspSnap) { snap(); inspSnap = true; }
  for (const c of cs) {
    if (k === "speed") { const a = assetOf(c), old = c.speed || 1; c.speed = v; c.dur = c.dur * old / v; if (a && a.kind !== "image") c.dur = Math.min(c.dur, (a.dur - (c.in || 0)) / v); }
    else if (k === "start" || k === "dur") c[k] = Math.max(k === "dur" ? .05 : 0, v);
    else setK(c, k, v);
  }
  const textual = k === "text" || k.startsWith("style.") || k === "subscribe" || k === "graphic" || k === "mode" || k === "date" || k === "cam";
  if (textual) assDirty();
  if (live) { draw(); if (k === "speed" || k === "start" || k === "dur" || k === "vol" || k.startsWith("fade")) renderTimeline(); renderHandles(); ST.dirty = true; scheduleSave(); }
  else changed();
}
$("#insp").addEventListener("input", e => {
  const el = e.target, k = el.dataset.k;
  if (el.dataset.pk) return;
  if (!k) { if (el.id === "zz") $("#zzn").value = (+el.value).toFixed(2); return; }
  let v = el.type === "checkbox" ? el.checked : el.type === "range" || el.type === "number" ? +el.value : el.value;
  if (el.type === "range") { const n = el.parentElement.querySelector(`input.num[data-k="${k}"]`); if (n) n.value = (+v).toFixed(3).replace(/\.?0+$/, ""); }
  if (el.type === "number" && el.classList.contains("num")) { const r = el.parentElement.querySelector(`input[type=range][data-k="${k}"]`); if (r) r.value = v; }
  if (el.tagName === "TEXTAREA" || (el.tagName === "INPUT" && el.type === "text") || el.classList.contains("in") && el.tagName === "INPUT" && el.type !== "number") { inspSet(k, v, true); return; }
  if (el.tagName === "SELECT" || el.type === "checkbox" || el.type === "color") return;
  inspSet(k, v, true);
});
$("#insp").addEventListener("change", e => {
  const el = e.target, k = el.dataset.k, pk = el.dataset.pk;
  if (pk) { snap(); ST.p[pk] = el.type === "number" || pk === "fps" ? Math.max(16, Math.round(+el.value)) : el.value; if (pk === "name") $("#pname").value = el.value; if (pk === "w" || pk === "h") afterLoad(true); else changed(); return; }
  if (!k) return;
  const v = el.type === "checkbox" ? el.checked : el.type === "range" || el.type === "number" ? +el.value : el.value;
  if (el.tagName === "SELECT" || el.type === "checkbox" || el.type === "color") { inspSet(k, v, false); return; }
  inspSnap = false; changed();
});
$("#insp").addEventListener("click", async e => {
  const b = e.target.closest("button, a[data-a2]"); if (!b) return;
  e.preventDefault();
  const c = selClips()[0];
  if (b.closest("[data-seg]")) { inspSet(b.closest("[data-seg]").dataset.seg, b.dataset.v, false); return; }
  if (b.dataset.speed) { inspSet("speed", +b.dataset.speed, false); return; }
  if (b.dataset.ramp) { snap(); rampApply(c, RAMPS[b.dataset.ramp].p && clone(RAMPS[b.dataset.ramp].p)); changed(); return; }
  if (b.dataset.afx) { snap(); const s2 = new Set(c.afx || []); s2.has(b.dataset.afx) ? s2.delete(b.dataset.afx) : s2.add(b.dataset.afx); c.afx = [...s2]; if (!c.afx.length) delete c.afx; changed(false); renderInsp(); return; }
  if (b.dataset.unfx) { snap(); c.fx = c.fx.filter(x => x !== b.dataset.unfx); if (!c.fx.length) delete c.fx; changed(); return; }
  if (b.dataset.kfdel != null) { snap(); const kf = kfResolve(c.zoom, c.dur); kf.splice(+b.dataset.kfdel, 1); c.zoom = kf.length ? kf : undefined; if (!c.zoom) delete c.zoom; changed(); return; }
  const a2 = b.dataset.a2;
  if (a2 === "kfadd") {
    const l = clamp(ST.t - c.start, 0, c.dur); snap();
    const kf = kfResolve(c.zoom || [], c.dur).filter(k => Math.abs(k.t - l) > .02);
    if (!kf.length && l > .05) kf.push({ t: 0, z: 1 });
    kf.push({ t: +l.toFixed(3), z: +(+$("#zz").value).toFixed(3), cx: +$("#zcx").value, cy: +$("#zcy").value, ...($("#zease").value ? { e: $("#zease").value } : {}) });
    c.zoom = kf.sort((a, b) => a.t - b.t); changed();
  } else if (a2 === "kfclear") { snap(); delete c.zoom; changed(); }
  else if (a2 === "kfsave") {
    const n = await promptText("Zoom şablonu adı", "Benim zoom'um", "Başka kliplere Zoom panelinden uygulanır. Son kare klip sonuna göre değilse sabit sürede kalır."); if (!n) return;
    const kf = kfResolve(c.zoom, c.dur), last = kf.at(-1);
    if (last && Math.abs(last.t - c.dur) < .05) last.t = -0.001;   // klip sonuna kilitli kare: her uzunluga uysun
    ST.cat.zoom = [...ST.cat.zoom.filter(z => !z.user), ...await api.studio_template_save(n, kf)]; toast("Şablon kaydedildi"); window.renderPanel?.();
  } else if (a2 === "words") {
    const ws = $("#wordsEd").value.trim().split(/\s+/); snap();
    if (ws.length === c.words.length) c.words = c.words.map((w, i) => ({ ...w, w: ws[i] }));
    else { const s0 = c.words[0]?.s || 0, e0 = c.words.at(-1)?.e || c.dur, step = (e0 - s0) / ws.length; c.words = ws.map((w, i) => ({ w, s: +(s0 + i * step).toFixed(3), e: +(s0 + (i + 1) * step).toFixed(3) })); }
    changed();
  } else if (a2 === "clearmk") { snap(); ST.p.markers = []; changed(); }
  else if (a2 === "align") { snap(); let t = Math.min(...selClips().map(x => x.start)); for (const x of selClips().sort((a, b) => a.start - b.start)) { x.start = t; t += x.dur; } changed(); }
  else if (a2 === "del") deleteSel();
  else if (a2 === "pipette") { pipette = true; document.body.style.cursor = "crosshair"; toast("Önizlemede perde rengine tıkla"); }
  else if (a2 === "tocolor") window.setPage?.("color");
  else if (a2) window.aiAction?.(a2, c);
});
window.focusInsp = () => { renderInsp(); $("#insp").scrollTop = 0; };

// ---------------------------------------------------------------- disa aktarim
async function exportVideo() {
  if (!ST.p.clips.length) { toast("Zaman çizelgesi boş"); return; }
  if (play) play(false);
  const sel = selClips();
  const range = sel.length ? [Math.min(...sel.map(c => c.start)), Math.max(...sel.map(c => c.start + c.dur))] : null;
  const opts = await modal(`<h3>Dışa aktar</h3>
    <div class="hint">${ST.p.w}×${ST.p.h} · ${ST.p.fps} fps · ${fmt(projEnd())} · H.264 MP4 (NVENC varsa ekran kartıyla). Her zaman asıl dosyalardan, tam kalitede işlenir.</div>
    <label class="fld w2"><span>Kalite</span><select class="in" id="xq"><option value="high">Yüksek (YouTube)</option><option value="medium">Orta (küçük dosya)</option></select></label>
    <label class="fld w2"><span>Aralık</span><select class="in" id="xr"><option value="all">Tüm video</option>${range ? `<option value="sel">Seçili klipler (${fmt(range[0])}–${fmt(range[1])})</option>` : ""}<option value="mk">İşaretler arası (ilk–son)</option></select></label>
    <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">Kaydet…</button></div>`,
    { collect: () => ({ quality: $("#xq").value, r: $("#xr").value }) });
  if (!opts) return;
  const o = { quality: opts.quality };
  if (opts.r === "sel" && range) o.range = range;
  if (opts.r === "mk" && ST.p.markers?.length > 1) { const ts = ST.p.markers.map(m => m.t).sort((a, b) => a - b); o.range = [ts[0], ts.at(-1)]; }
  const out = await api.studio_pick_save(ST.p.name, ".mp4"); if (!out) return;
  await save();
  const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
  const r = await api.studio_export(p, out, o);
  if (!r?.ok) { toast("Başlatılamadı: " + r?.error); return; }
  const t0 = Date.now();
  const m = $("#modal"); m.hidden = false;
  m.innerHTML = `<div class="mbox cut"><h3>Dışa aktarılıyor…</h3><div class="hint" id="xs">${esc(out)}</div><div class="bar"><i id="xb"></i></div><div class="hint" id="xp">%0</div><div class="row"><button class="tb" id="xc">İptal</button></div></div>`;
  $("#xc").onclick = () => api.studio_cancel(r.job);
  for (;;) {
    await new Promise(res => setTimeout(res, 500));
    const j = await api.studio_job(r.job);
    const p = j.p || 0, el = (Date.now() - t0) / 1000;
    $("#xb").style.width = (p * 100).toFixed(1) + "%";
    $("#xp").textContent = `%${(p * 100).toFixed(0)}` + (p > .03 ? ` · kalan ~${Math.max(0, el / p - el).toFixed(0)} sn` : "");
    if (j.state === "running") continue;
    if (j.state === "done") {
      m.innerHTML = `<div class="mbox cut"><h3>Hazır ✓</h3><div class="hint">${esc(out)}<br>${j.secs} sn · ${j.encoder === "h264_nvenc" ? "ekran kartı (NVENC)" : "işlemci (x264)"}</div><div class="row"><button class="tb" id="xo">Klasörü aç</button><button class="tb" id="xv">Oynat</button><button class="tb pri" id="xk">Tamam</button></div></div>`;
      $("#xo").onclick = () => api.open_path_folder(out); $("#xv").onclick = () => api.open_path(out); $("#xk").onclick = () => { m.hidden = true; };
    } else if (j.state === "error") {
      m.innerHTML = `<div class="mbox cut"><h3>Dışa aktarılamadı</h3><pre class="code">${esc(j.error || "")}</pre><div class="row"><button class="tb pri" id="xk">Kapat</button></div></div>`;
      $("#xk").onclick = () => { m.hidden = true; };
    } else m.hidden = true;
    break;
  }
}

// ---------------------------------------------------------------- dugmeler, klavye
document.addEventListener("click", e => {
  const b = e.target.closest("[data-a]"); if (!b || b.closest("#insp")) return;
  const a = b.dataset.a;
  ({
    undo, redo, play: () => play(), home: () => seek(0), end: () => seek(projEnd()),
    back: () => seek(ST.t - 1 / ST.p.fps), fwd: () => seek(ST.t + 1 / ST.p.fps),
    split: splitAtPlayhead, del: () => deleteSel(), dup: dupSel, save: () => save(), export: exportVideo,
    open: async () => { const p = await api.studio_pick_project(); if (p) openProject(p); },
    new: newProject,
    marker: () => { snap(); (ST.p.markers ||= []).push({ t: +ST.t.toFixed(3), kind: "note" }); changed(); },
    snap: () => { ST.snap = !ST.snap; b.classList.toggle("on", ST.snap); },
    ripple: () => { ST.ripple = !ST.ripple; b.classList.toggle("on", ST.ripple); },
    smartcut: async () => {
      const id = [...ST.sel][0]; const c = ST.p?.clips.find(x => x.id === id);
      const asset = c && ST.p?.assets?.[c.asset];
      if (!c || !asset?.path) return toast("Önce bir video/ses klibi seç");
      busy("Kayıpsız Smart Cut…");
      const r = await api.studio_smart_cut(asset.path, c.in || 0, c.out || 0, "");
      busy(null);
      toast(r?.ok ? "Smart Cut kaydedildi: " + r.path.split(/[\\/]/).pop() : (r?.error || "Smart Cut başarısız"));
    },
    enhance: async () => {
      const id = [...ST.sel][0]; const c = ST.p?.clips.find(x => x.id === id);
      const asset = c && ST.p?.assets?.[c.asset];
      if (!c || !asset?.path) return toast("Önce ses/video klibi seç");
      busy("Ses netleştiriliyor (-14 LUFS)…");
      const r = await api.studio_audio_enhance(asset.path, "", "medium");
      busy(null);
      toast(r?.ok ? "Ses iyileştirildi: " + r.path.split(/[\\/]/).pop() : (r?.error || "Ses hatası"));
    },
    compound: async () => {
      const ids = [...ST.sel];
      if (!ids.length || !ST.p) return toast("Önce klip seç");
      const first = ST.p.clips.find(x => x.id === ids[0]);
      snap();
      if (ids.length === 1 && first?.kind === "compound") {
        const r = await api.studio_compound_expand(ST.p.clips, first.id);
        if (r?.ok) { ST.p.clips = r.clips; ST.sel.clear(); changed(); toast("Bileşik klip açıldı"); }
      } else {
        const r = await api.studio_compound_create(ST.p.clips, ids, "Bileşik Klip");
        if (r?.ok) { ST.p.clips = r.clips; ST.sel = new Set([r.compound.id]); changed(); toast("Bileşik klip oluşturuldu"); }
      }
    },
    scopes: async () => {
      if (!window.SScopes) return toast("Scopes yüklenemedi");
      const p = modal(`<h3>Colorist Scopes</h3>
        <div class="row" style="gap:6px;margin-bottom:8px">
          <button class="tb pri" data-sc="waveform">Waveform</button>
          <button class="tb" data-sc="parade">RGB Parade</button>
          <button class="tb" data-sc="vectorscope">Vectorscope</button>
          <button class="tb" data-sc="histogram">Histogram</button>
        </div>
        <canvas id="scopeCanvas" width="420" height="200" style="width:100%;border-radius:8px;border:1px solid #3A2E52"></canvas>
        <div class="row" style="margin-top:8px"><button class="tb" data-v="ok">Kapat</button></div>`);
      const mEl = $("#modal");
      const scCv = mEl.querySelector("#scopeCanvas");
      const drawMode = (m) => { if (scCv && typeof view !== "undefined") SScopes.renderScope(view, scCv, m); };
      drawMode("waveform");
      mEl.querySelectorAll("[data-sc]").forEach(btn => btn.addEventListener("click", () => drawMode(btn.dataset.sc)));
      await p;
    },
    viral: async () => {
      const list = (await api.studio_recipes_list?.()) || [];
      const btns = list.map(r => `<button class="tb" data-v="${esc(r.id)}" style="text-align:left;width:100%"><b>${esc(r.name)}</b><br><small style="opacity:.75">${esc(r.desc)}</small></button>`).join("");
      const pick = await modal(`<h3>Viral Kurgu Paketleri (Faz 9)</h3><div style="display:flex;flex-direction:column;gap:6px;max-width:420px">${btns}</div><div class="row" style="margin-top:8px"><button class="tb" data-v="">İptal</button></div>`);
      if (!pick || !ST.p) return;
      snap();
      const res = await api.studio_run_recipe(ST.p, pick);
      if (res?.ok) { ST.p = res.project; changed(); toast(`Paket uygulandı: ${pick}`); }
      else toast(res?.error || "Paket uygulanamadı");
    },
    addtrack: async () => { const k = await modal(`<h3>İz ekle</h3><div class="row" style="justify-content:stretch">${[["video", "Video / görsel"], ["audio", "Ses"], ["text", "Metin"], ["fx", "Efekt"]].map(([k, l]) => `<button class="tb" data-v="${k}">${l}</button>`).join("")}</div>`); if (k) { snap(); addTrack(k); changed(); } },
    zin: () => setZoom(ST.px * 1.4), zout: () => setZoom(ST.px / 1.4),
    zfit: () => setZoom((scroller.clientWidth - 40) / Math.max(5, projEnd())),
    snapshot: async () => { busy("Kare kaydediliyor…"); const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url; const r = await api.studio_frame_png(p, ST.t, ""); busy(null); if (r.ok) { toast("Kaydedildi: " + r.path.split(/[\\/]/).pop()); } else toast(r.error || "olmadı"); },
    safe: () => document.body.classList.toggle("safe"),
    full: () => { const w = $("#viewArea"); document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen(); },
    snapshotOld: () => { const a2 = document.createElement("a"); const cv = document.createElement("canvas"); cv.width = PW; cv.height = PH; const g = cv.getContext("2d"); g.drawImage(view, 0, 0); g.drawImage($("#assView"), 0, 0, PW, PH); a2.href = cv.toDataURL("image/png"); a2.download = `${ST.p.name}-${fmt(ST.t).replace(/[:.]/g, "-")}.png`; a2.click(); },
    keys: () => modal(`<h3>Kısayollar</h3><div class="keys">${[["Boşluk", "Oynat / durdur"], ["S", "Oynatma kafasında böl"], ["Del", "Sil (Shift: boşluğu kapat)"], ["Ctrl+Z / Y", "Geri al / yinele"], ["Ctrl+C / V / D", "Kopyala / yapıştır / çoğalt"], ["← →", "1 kare (Shift: 1 sn)"], ["Home / End", "Başa / sona"], ["M", "İşaret koy"], ["+ / −", "Zaman ölçeği (Ctrl+tekerlek)"], ["1-9", "Hızlı ses/meme (Ses panelinde ★ ile ata)"], ["F", "Tam ekran önizleme"], ["Ctrl+S / E / O", "Kaydet / dışa aktar / aç"]].map(([k, v]) => `<kbd>${k}</kbd><span>${v}</span>`).join("")}</div><div class="row"><button class="tb pri" data-v="ok">Tamam</button></div>`),
  })[a]?.();
});
document.addEventListener("keydown", e => {
  if (!ST.p || !$("#modal").hidden) return;
  const tag = document.activeElement?.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") { if (e.key === "Escape") document.activeElement.blur(); return; }
  const k = e.key, ctrl = e.ctrlKey || e.metaKey;
  if (k === " ") { e.preventDefault(); play(); }
  else if (ctrl && k.toLowerCase() === "z") { e.preventDefault(); e.shiftKey ? redo() : undo(); }
  else if (ctrl && k.toLowerCase() === "y") { e.preventDefault(); redo(); }
  else if (ctrl && k.toLowerCase() === "s") { e.preventDefault(); save(e.shiftKey); }
  else if (ctrl && k.toLowerCase() === "e") { e.preventDefault(); exportVideo(); }
  else if (ctrl && k.toLowerCase() === "o") { e.preventDefault(); $('[data-a="open"]').click(); }
  else if (ctrl && k.toLowerCase() === "c") copySel();
  else if (ctrl && k.toLowerCase() === "v") paste();
  else if (ctrl && k.toLowerCase() === "d") { e.preventDefault(); dupSel(); }
  else if (ctrl && k.toLowerCase() === "a") { e.preventDefault(); ST.sel = new Set(ST.p.clips.map(c => c.id)); renderTimeline(); renderInsp(); }
  else if (k === "Delete" || k === "Backspace") deleteSel(e.shiftKey || ST.ripple);
  else if (k.toLowerCase() === "s" && !ctrl) splitAtPlayhead();
  else if (k.toLowerCase() === "m") $('[data-a="marker"]').click();
  else if (k.toLowerCase() === "f") $('[data-a="full"]').click();
  else if (k === "ArrowLeft") { e.preventDefault(); seek(ST.t - (e.shiftKey ? 1 : 1 / ST.p.fps)); }
  else if (k === "ArrowRight") { e.preventDefault(); seek(ST.t + (e.shiftKey ? 1 : 1 / ST.p.fps)); }
  else if (k === "Home") seek(0);
  else if (k === "End") seek(projEnd());
  else if (k === "+" || k === "=") setZoom(ST.px * 1.4);
  else if (k === "-") setZoom(ST.px / 1.4);
  else if (k === "Escape") { ST.sel.clear(); renderTimeline(); renderInsp(); renderHandles(); }
  else if (/^[1-9]$/.test(k)) window.quickSlot?.(+k);
});
$("#tlZoom").addEventListener("input", e => setZoom(+e.target.value));
$("#pname").addEventListener("change", e => { snap(); ST.p.name = e.target.value.trim() || "Proje"; changed(false); });
$("#ratio").addEventListener("change", e => { const [w, h] = e.target.value.split("x").map(Number); snap(); ST.p.w = w; ST.p.h = h; afterLoad(true); toast(`${w}×${h} — dikeyde “Akıllı > Dikey çerçeve” yüzü ortalar`); });
$("#pq").addEventListener("change", e => { ST.pq = +e.target.value; layoutView(); });
new ResizeObserver(() => layoutView()).observe($("#viewArea"));
// zaman cizelgesi yuksekligi
$("#split").addEventListener("pointerdown", e => {
  const y0 = e.clientY, h0 = $("#tl").getBoundingClientRect().height;
  const mv = ev => { document.documentElement.style.setProperty("--tl-h", clamp(h0 - (ev.clientY - y0), 150, innerHeight - 260) + "px"); };
  const up = () => { document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up); try { localStorage.kstTl = getComputedStyle(document.documentElement).getPropertyValue("--tl-h"); } catch { } };
  document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
});
try { if (localStorage.kstTl) document.documentElement.style.setProperty("--tl-h", localStorage.kstTl); } catch { }

// ---------------------------------------------------------------- baslangic + gelen kutusu (surukle-birak, MCP)
async function inbox() {
  try {
    const q = await api.studio_poll();
    const proj = q.filter(p => p.toLowerCase().endsWith(".kstudio")), med = q.filter(p => !p.toLowerCase().endsWith(".kstudio"));
    if (proj.length) await openProject(proj[0]);
    if (med.length) {
      const d = ST.osDrop; ST.osDrop = null;
      const added = await importPaths(med);
      if (d && Date.now() - d.at < 8000 && added.length) {   // zaman cizelgesine birakildi: oraya yerlestir
        let t = d.t; for (const aid of added) { dropAsset(aid, t, d.tid); t += ST.p.assets[aid]?.dur || 5; }
      }
    }
    const mcp = await api.studio_current();
    if (mcp && mcp !== ST.path) { if (ST.dirty) await save(); await openProject(mcp); toast("Kami AI yeni bir proje açtı"); }
    else if (ST.path && await api.studio_changed(ST.path)) {   // Kami AI (MCP) ya da baska yerden duzenlendi
      const r = await job("studio_open", [ST.path]);
      if (r?.ok) { ST.undo.push(JSON.stringify(ST.p)); ST.p = r.project; ST.p.markers ||= []; afterLoad(true); ST.dirty = false; $("#saved").textContent = "↻ Kami AI düzenledi"; }
    }
  } catch (e) { console.warn(e); }
  setTimeout(inbox, 900);
}
async function boot() {
  api = window.pywebview.api;
  ST.cat = await api.studio_catalog();
  ST.p = await api.studio_new();
  afterLoad();
  window.renderPanel?.("media");
  assInit();
  $("#editModeSel")?.addEventListener("change", (e) => {
    ST.editMode = e.target.value;
    if (ST.editMode === "ripple") { ST.ripple = true; $("#rippleBtn")?.classList.add("on"); }
  });
  inbox();
}
window.addEventListener("pywebviewready", boot);
window.addEventListener("beforeunload", () => { if (ST.dirty) save(); });
Object.assign(window, { ST, toast, modal, ask, promptText, busy, job, waitStudioJob, snap, changed, importPaths, addClip, placeAt, addTrack, trackFor,
  selClips, splitClip, removeRanges, kfResolve, fmt, esc, clone, clipKind, assetOf, trackOf, seek, draw, projEnd, openProject, dropAsset, resolveOverlap, renderTimeline, renderInsp, assDirty, layoutView });
