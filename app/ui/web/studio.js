"use strict";
// Kami Studio: proje durumu, onizleme (tuval + JASSUB), zaman cizelgesi, denetci. Paneller: studio-panels.js
const $ = (s, r = document) => r.querySelector(s);
const $$ = (s, r = document) => [...r.querySelectorAll(s)];
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
const esc = s => String(s ?? "").replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
let api = null;

const ST = {
  p: null, path: "", sel: new Set(), cutSel: new Set(), t: 0, playing: false, px: 80, snap: true, ripple: false, linkTracks: true,
  loopIn: null, loopOut: null, loopOn: false, scrubAudio: false, compoundStack: [],
  undo: [], redo: [], cat: { fx: {}, trans: {}, zoom: [], captions: {}, anims: {}, subscribe: {}, fonts: [], stickers: {}, voiceChangers: {} },
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
function rootProjectClone() {
  const p = clone(ST.p);
  if (ST.compoundStack?.length) {
    let cur = p.clips;
    for (let i = ST.compoundStack.length - 1; i >= 0; i--) {
      const fr = ST.compoundStack[i];
      const host = clone(fr.clips);
      const target = host.find(x => x.id === fr.id);
      if (target) {
        target.children = cur;
        target.dur = +Math.max(0.1, ...cur.map(x => (x.start || 0) + (x.dur || 0))).toFixed(4);
      }
      cur = host;
    }
    p.clips = cur;
  }
  return p;
}
function renderCompCrumb() {
  const el = $("#compCrumb");
  if (!el) return;
  if (!ST.compoundStack?.length) { el.hidden = true; el.innerHTML = ""; return; }
  el.hidden = false;
  el.innerHTML = `<button type="button" data-a="exitComp">‹ Ana Kurguya Dön</button><span>${esc(ST.compoundStack.map(x => x.name).join(" › "))}</span>`;
}
function enterCompound(c) {
  if (!c || c.kind !== "compound") return;
  snap();
  ST.compoundStack.push({ id: c.id, name: c.name || "Bileşik Klip", clips: clone(ST.p.clips) });
  ST.p.clips = clone(c.children || []);
  ST.sel.clear(); ST.t = 0;
  renderCompCrumb(); renderTimeline(); renderInsp(); draw();
  toast("Bileşik klip içi açıldı");
}
function exitCompound() {
  if (!ST.compoundStack?.length) return;
  const fr = ST.compoundStack.pop();
  const host = fr.clips;
  const target = host.find(x => x.id === fr.id);
  if (target) {
    target.children = clone(ST.p.clips);
    target.dur = +Math.max(0.1, ...target.children.map(x => (x.start || 0) + (x.dur || 0))).toFixed(4);
  }
  ST.p.clips = host;
  ST.sel = target ? new Set([target.id]) : new Set();
  renderCompCrumb(); changed();
  toast("Üst zaman çizelgesine dönüldü");
}
async function save(as = false) {
  clearTimeout(saveT);
  ST.p.name = $("#pname").value.trim() || "Proje";
  let path = ST.path;
  if (as || !path) {
    if (as) { path = await api.studio_pick_save(ST.p.name, ".kstudio"); if (!path) return; }
  }
  const p = rootProjectClone();
  for (const a of Object.values(p.assets)) { delete a.url; delete a.missing; }
  const r = await job("studio_save", [p, path || ""]);
  if (r?.ok) { ST.path = r.path; ST.dirty = false; $("#saved").textContent = "✓ kaydedildi"; $("#saved").classList.remove("dirty"); }
}
function afterLoad(keepSel = false) {
  if (!keepSel) { ST.sel.clear(); ST.cutSel.clear(); } else {
    for (const id of [...ST.sel]) if (!ST.p.clips.some(c => c.id === id)) ST.sel.delete(id);
    for (const id of [...ST.cutSel]) if (!(ST.p.cuts || []).some(ct => ct.id === id)) ST.cutSel.delete(id);
  }
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
    stopAll(); ST.p = r.project; ST.path = r.path; ST.undo = []; ST.redo = []; ST.compoundStack = []; ST.t = 0; ST.dirty = false;
    ST.p.markers ||= []; renderCompCrumb();
    afterLoad(); $("#saved").textContent = "✓ açık"; $("#saved").classList.remove("dirty");
    const miss = Object.values(ST.p.assets).filter(a => a.missing).length;
    if (miss) toast(`${miss} medya dosyası bulunamadı (taşınmış olabilir)`, 4000);
  } catch (e) { toast("Açılamadı: " + e.message, 4000); }
  busy(null);
}
async function newProject() {
  if (ST.dirty) await save();
  stopAll(); ST.p = await api.studio_new(); ST.path = ""; ST.undo = []; ST.redo = []; ST.compoundStack = []; ST.t = 0; renderCompCrumb();
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
function rippleClose(track, t0, gap) {
  for (const c of ST.p.clips) if (c.track === track && c.start >= t0 - 1e-6) c.start = +(c.start - gap).toFixed(4);
  for (const ct of ST.p.cuts || []) if (ct.track === track && ct.seamStart >= t0 - 1e-6) ct.seamStart = +(ct.seamStart - gap).toFixed(4);
}
function rippleOpen(track, t0, gap) {
  for (const c of ST.p.clips) if (c.track === track && c.start >= t0 - 1e-6) c.start = +(c.start + gap).toFixed(4);
  for (const ct of ST.p.cuts || []) if (ct.track === track && ct.seamStart >= t0 - 1e-6) ct.seamStart = +(ct.seamStart + gap).toFixed(4);
}
function removeRanges(c, ranges, padAfter = .08, padBefore = padAfter) {
  const sp = c.speed || 1; let n = 0;
  ST.p.cuts ||= [];
  for (let [a, b] of [...ranges].sort((x, y) => y[0] - x[0])) {
    a += padAfter; b -= padBefore; if (b - a < .08) continue;
    const same = ST.p.clips.filter(x => x.track === c.track && x.asset === c.asset);
    for (const x of same) {
      let t0 = x.start + (a - (x.in || 0)) / sp, t1 = x.start + (b - (x.in || 0)) / sp;
      if (t1 <= xsOr(x) || t0 >= x.start + x.dur) continue;
      t0 = Math.max(x.start, t0); t1 = Math.min(x.start + x.dur, t1);
      const mid = t0 > x.start + .02 ? splitClip(x, t0) : x; if (!mid) continue;
      if (t1 < mid.start + mid.dur - .02) splitClip(mid, t1);
      const cutSnap = clone(mid);
      ST.p.clips.splice(ST.p.clips.indexOf(mid), 1); ST.sel.delete(mid.id);
      rippleClose(c.track, t1, t1 - t0);
      ST.p.cuts.push({ id: "cut_" + uid(), track: c.track, seamStart: +t0.toFixed(4), dur: +cutSnap.dur.toFixed(4), clip: cutSnap });
      n++; break;
    }
  }
  return n;
}
function xsOr(x) { return x.start; }
function restoreCuts(ids) {
  const wanted = new Set(ids);
  const cuts = ST.p.cuts || [];
  const targets = cuts.filter(ct => wanted.has(ct.id)).sort((a, b) => b.seamStart - a.seamStart);
  if (!targets.length) return 0;
  snap(); ST.sel.clear();
  for (const ct of targets) {
    const seam = ct.seamStart;
    const restored = clone(ct.clip);
    rippleOpen(ct.track, seam, restored.dur);
    restored.start = +seam.toFixed(4);
    ST.p.clips.push(restored);
    ST.sel.add(restored.id);
    const idx = cuts.indexOf(ct);
    if (idx >= 0) cuts.splice(idx, 1);
  }
  ST.cutSel.clear();
  changed();
  return targets.length;
}
function dropCuts(ids) {
  const wanted = new Set(ids);
  if (!wanted.size || !ST.p.cuts) return;
  snap();
  ST.p.cuts = ST.p.cuts.filter(ct => !wanted.has(ct.id));
  ST.cutSel.clear();
  changed();
}
function kfResolve(kf, dur) { return (kf || []).map(k => ({ ...k, t: Math.max(0, k.t < 0 ? dur + k.t : k.t) })).sort((a, b) => a.t - b.t); }
const EASE = { out: u => 1 - (1 - u) * (1 - u), in: u => u * u, inout: u => u * u * (3 - 2 * u) };
function _kfEaseVal(b, u) {
  const bz = Array.isArray(b.bez) && b.bez.length === 4 ? b.bez : (typeof b.bez === "string" ? ST.cat.bezierPresets?.[b.bez] : null);
  if (bz && SFX.evalBezier) return SFX.evalBezier(+bz[0], +bz[1], +bz[2], +bz[3], u);
  return (EASE[b.e] || (x => x))(u);
}
function kfAt(kf, key, t, def) {
  const pts = kf.filter(k => key in k || (key === "z" && !("scale" in k)));
  if (!pts.length) return def;
  if (t <= pts[0].t) return pts[0][key] ?? def;
  for (let i = 1; i < pts.length; i++) {
    if (t < pts[i].t) { const a = pts[i - 1], b = pts[i], u = (t - a.t) / Math.max(1e-3, b.t - a.t); return (a[key] ?? def) + ((b[key] ?? def) - (a[key] ?? def)) * _kfEaseVal(b, u); }
  }
  return pts.at(-1)[key] ?? def;
}
function deleteSel(ripple = ST.ripple) {
  const cs = selClips(); if (!cs.length) return;
  snap();
  for (const c of cs.sort((a, b) => b.start - a.start)) { ST.p.clips.splice(ST.p.clips.indexOf(c), 1); if (ripple) rippleClose(c.track, c.start + c.dur, c.dur); }
  ST.sel.clear(); changed();
}
function linkedPeers(c) {
  if (!ST.linkTracks || !ST.p || c.unlinked) return [c];
  const k = clipKind(c);
  const peers = ST.p.clips.filter(x => x === c || (!x.unlinked && ((c.linkId && x.linkId === c.linkId) ||
    (!c.linkId && !x.linkId && x.asset && x.asset === c.asset && Math.abs(x.start - c.start) < 0.05 &&
      Math.abs(x.dur - c.dur) < 0.05 && ((k === "video" && clipKind(x) === "audio") || (k === "audio" && clipKind(x) === "video"))))));
  return peers.length ? peers : [c];
}
function unlinkClip(c) {
  if (!c) return;
  snap();
  for (const p of linkedPeers(c)) { delete p.linkId; p.unlinked = true; }
  delete c.linkId; c.unlinked = true;
  changed(false); toast("Klip bağı kaldırıldı (J/L Cut hazır)");
}
function closeTrackGaps(tid) {
  if (!ST.p || !tid) return 0;
  const seq = ST.p.clips.filter(x => x.track === tid).sort((a, b) => a.start - b.start);
  let cur = 0, moved = 0;
  for (const x of seq) {
    const st = +cur.toFixed(4);
    if (Math.abs(x.start - st) > 1e-4) { if (!moved) snap(); x.start = st; moved++; }
    cur = st + x.dur;
  }
  if (moved) { changed(); toast(`${moved} klibin boşluğu kapatıldı`); } else toast("İzde kapatılacak boşluk yok");
  return moved;
}
window.unlinkClip = unlinkClip;
window.closeTrackGaps = closeTrackGaps;
function splitAtPlayhead() {
  let cs = selClips().filter(c => c.start < ST.t && c.start + c.dur > ST.t);
  if (!cs.length) cs = ST.p.clips.filter(c => c.start < ST.t && c.start + c.dur > ST.t && !trackOf(c).lock);
  if (!cs.length) return;
  if (ST.linkTracks) {
    const exp = new Set(cs);
    for (const c of cs) for (const p of linkedPeers(c)) if (!trackOf(p).lock && p.start < ST.t && p.start + p.dur > ST.t) exp.add(p);
    cs = [...exp];
  }
  snap();
  const lL = "lnk_" + uid(), lR = "lnk_" + uid();
  const news = [];
  for (const c of cs) {
    const n = splitClip(c, ST.t);
    if (n) {
      if (cs.length > 1) { c.linkId = lL; n.linkId = lR; }
      news.push(n);
    }
  }
  ST.sel = new Set(news.map(c => c.id)); changed();
}
function trimSide(side) {
  let cs = selClips().filter(c => c.start < ST.t && c.start + c.dur > ST.t);
  if (!cs.length) cs = ST.p.clips.filter(c => c.start < ST.t && c.start + c.dur > ST.t && !trackOf(c).lock);
  if (!cs.length) { toast("Oynatma kafasının altında klip yok"); return; }
  if (ST.linkTracks) {
    const exp = new Set(cs);
    for (const c of cs) for (const p of linkedPeers(c)) if (!trackOf(p).lock && p.start < ST.t && p.start + p.dur > ST.t) exp.add(p);
    cs = [...exp];
  }
  snap();
  for (const c of cs) {
    const a = assetOf(c), sp = c.speed || 1;
    if (side === "l") {
      const d = clamp(ST.t - c.start, 0, c.dur - 0.05);
      c.start = +(c.start + d).toFixed(4);
      c.dur = +(c.dur - d).toFixed(4);
      if (a) c.in = +((c.in || 0) + d * sp).toFixed(4);
      if (ST.ripple) {
        for (const oc of ST.p.clips) if (oc !== c && oc.track === c.track && oc.start >= c.start - 0.01) oc.start = Math.max(0, +(oc.start - d).toFixed(4));
        if (c.track === ST.p.tracks[0]?.id) ST.t = Math.max(0, +(ST.t - d).toFixed(4));
      }
    } else {
      const oldEnd = c.start + c.dur;
      const nd = clamp(ST.t - c.start, 0.05, c.dur);
      const cut = +(c.dur - nd).toFixed(4);
      c.dur = +nd.toFixed(4);
      if (ST.ripple && cut > 0) {
        for (const oc of ST.p.clips) if (oc !== c && oc.track === c.track && oc.start >= oldEnd - 0.05) oc.start = Math.max(0, +(oc.start - cut).toFixed(4));
      }
    }
  }
  changed();
  toast(side === "l" ? "Sol kısım silindi" : "Sağ kısım silindi");
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
function dropEl(id) {
  const r = ST.rt[id]; if (!r) return;
  try { r.el.pause(); r.el.removeAttribute("src"); r.el.load(); } catch { }
  try { r.au?.gain?.disconnect(); r.au?.src?.disconnect(); } catch { }
  delete ST.rt[id];
}
function stopAll() { for (const id of Object.keys(ST.rt)) dropEl(id); }
const EQ_BANDS_HZ = [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
function studioTrackBus(tid) {
  const ac = ST.ac; if (!ac) return null;
  ST.acTr ||= {};
  if (!ST.acMaster) {
    ST.acMaster = ac.createAnalyser();
    ST.acMaster.fftSize = 256;
    ST.acMaster.connect(ac.destination);
  }
  if (!ST.acTr[tid]) {
    const g = ac.createGain(), an = ac.createAnalyser();
    an.fftSize = 256;
    g.connect(an);
    an.connect(ST.acMaster);
    ST.acTr[tid] = { gain: g, analyser: an };
  }
  return ST.acTr[tid];
}
function ensureAudioNode(r, c) {
  if (!r || r.auTried) return r?.au || null;
  if (!ST.ac) {
    const Ctx = window.AudioContext || window.webkitAudioContext;
    if (!Ctx) { r.auTried = true; return null; }
    try { ST.ac = new Ctx(); } catch { r.auTried = true; return null; }
  }
  if (ST.ac.state === "suspended") ST.ac.resume().catch(() => {});
  r.auTried = true;
  try {
    const ac = ST.ac, src = ac.createMediaElementSource(r.el);
    const eq = EQ_BANDS_HZ.map((f, i) => {
      const b = ac.createBiquadFilter();
      b.type = i === 0 ? "lowshelf" : i === EQ_BANDS_HZ.length - 1 ? "highshelf" : "peaking";
      b.frequency.value = f; b.Q.value = 1.4; b.gain.value = 0;
      return b;
    });
    const pan = ac.createStereoPanner ? ac.createStereoPanner() : null;
    const vf = ac.createBiquadFilter();
    vf.type = "allpass"; vf.frequency.value = 1000;
    const vd = ac.createDelay(0.2); vd.delayTime.value = 0.025;
    const vdg = ac.createGain(); vdg.gain.value = 0;
    const gain = ac.createGain();
    let prev = src;
    for (const b of eq) { prev.connect(b); prev = b; }
    prev.connect(vf);
    vf.connect(vd); vd.connect(vdg);
    if (pan) { vf.connect(pan); vdg.connect(pan); prev = pan; }
    else { const mx = ac.createGain(); vf.connect(mx); vdg.connect(mx); prev = mx; }
    prev.connect(gain);
    const bus = studioTrackBus(c.track);
    if (bus) { gain.connect(bus.gain); r.track = c.track; }
    else gain.connect(ac.destination);
    r.au = { src, eq, vf, vd, vdg, pan, gain };
    return r.au;
  } catch { return null; }
}
function updateAudioNode(r, c, vol, audible) {
  const au = ensureAudioNode(r, c);
  if (!au) { r.el.volume = Math.min(1, vol); return; }
  if (r.track !== c.track) {
    const nb = studioTrackBus(c.track);
    if (nb) { try { au.gain.disconnect(); au.gain.connect(nb.gain); r.track = c.track; } catch { } }
  }
  r.el.volume = 1;
  au.gain.gain.value = audible ? clamp(vol, 0, 2) : 0;
  if (au.pan) au.pan.pan.value = clamp(c.pan || 0, -1, 1);
  const gArr = c.eq || [];
  au.eq.forEach((b, i) => { b.gain.value = clamp(+(gArr[i] || 0), -18, 18); });
  if (au.vf) {
    const vc = c.voice || "none";
    if (vc === "megaphone") { au.vf.type = "bandpass"; au.vf.frequency.value = 1400; au.vf.Q.value = 1.6; au.vdg.gain.value = 0; }
    else if (vc === "robot") { au.vf.type = "allpass"; au.vd.delayTime.value = 0.022; au.vdg.gain.value = 0.55; }
    else if (vc === "demon") { au.vf.type = "lowpass"; au.vf.frequency.value = 650; au.vd.delayTime.value = 0.035; au.vdg.gain.value = 0.45; }
    else if (vc === "deep") { au.vf.type = "lowpass"; au.vf.frequency.value = 1100; au.vdg.gain.value = 0; }
    else if (vc === "chipmunk") { au.vf.type = "highpass"; au.vf.frequency.value = 280; au.vdg.gain.value = 0; }
    else { au.vf.type = "allpass"; au.vdg.gain.value = 0; }
  }
}
// gercek klip-klip gecis: sonraki bitisik klibin giris gecisi suresince bu klip altta devam eder (studio.py trans_tail)
function transTail(c) {
  if (c.freeze || c.ramp) return 0;
  const end = c.start + c.dur, n = ST.p.clips.find(x => x !== c && x.track === c.track && Math.abs(x.start - end) < .05);
  const tr = n?.trans; if (!tr?.in || tr.in === "none" || tr.over === false) return 0;
  const want = tr.dur || .35, a = ST.p.assets[c.asset] || {};
  if (a.kind === "image" || a.gif) return want;
  const sp = c.speed || 1; return Math.max(0, Math.min(want, ((a.dur || 0) - (c.in || 0) - c.dur * sp) / sp));
}
// bilesik klipler (kind=compound) cizimde gercek kliplerine acilir (studio.py flatten_clips)
function flatClips(list = ST.p.clips) {
  const out = [];
  for (const c of list) {
    if (c.kind === "compound") out.push(...flatClips((c.children || []).map(ch => ({ ...ch, start: +(c.start + (ch.start || 0)).toFixed(4) }))));
    else out.push(c);
  }
  return out;
}
function activeAt(t, kind) { return flatClips().filter(c => t >= c.start - 1e-4 && t < c.start + c.dur && !trackOf(c).hide && (!kind || trackOf(c).kind === kind)); }
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
  if (c.reverse && assetOf(c)?.kind === "video") return Math.max(0, (c.in || 0) + Math.max(0, c.dur - (t - c.start)) * (c.speed || 1));
  return (c.in || 0) + (t - c.start) * (c.speed || 1);
}
function curSpeed(c, t) { return c.freeze ? 0 : c.ramp?.length ? rampAt(c, t - c.start)[1] : (c.speed || 1); }
function clipVol(c, t) {
  const tr = trackOf(c); if (tr.mute) return 0;
  const hasSolo = ST.p.tracks.some(x => (x.kind === "audio" || x.kind === "video") && x.solo);
  if (hasSolo && !tr.solo) return 0;
  const l = t - c.start, ukf = c.kf?.length ? kfResolve(c.kf, c.dur) : null;
  let v = ukf ? kfAt(ukf, "vol", l, c.vol ?? 1) : (c.vol ?? 1);
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
    const aLead = a.audio ? Math.max(-c.dur * .8, +(c.audioLead || 0)) : 0;
    const aTail = a.audio ? Math.max(-c.dur * .8, +(c.audioTail || 0)) : 0;
    const vAct = t >= c.start && t < c.start + c.dur && !trackOf(c).hide;
    const aAct = Boolean(a.audio || a.kind === "audio") && t >= c.start - aLead && t < c.start + c.dur + aTail && !trackOf(c).mute;
    const act = vAct || aAct;
    const soon = !act && c.start > t && c.start - t < 1.5;
    if (!act && !soon && !(ST.rt[c.id] && Math.abs(c.start - t) < 10)) continue;
    keep.add(c.id);
    const r = mediaEl(c), el = r.el;
    if (act) {
      const want = Math.max(0, srcTime(c, t)), vol = clipVol(c, t);
      const audible = aAct && vol > 0 && !c.freeze && !c.reverse && (ST.playing || ST._scrubActive);
      el.muted = !audible;
      if (ST.playing || ST.ac) updateAudioNode(r, c, vol, audible);
      else el.volume = Math.min(1, vol);
      el.playbackRate = clamp(curSpeed(c, t) || 1, .0625, 16);
      if ((ST.playing || ST._scrubActive) && !c.freeze && !c.reverse) {
        if (el.paused) { el.currentTime = want; el.play().catch(() => {}); }
        else if (Math.abs(el.currentTime - want) > .25) el.currentTime = want;
      } else {
        if (!el.paused) el.pause();
        const tol = c.reverse && ST.playing ? .035 : .5 / ST.p.fps;
        if (hard || Math.abs(el.currentTime - want) > tol) el.currentTime = want;
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
  if (c.crop && typeof c.crop === "object") {
    const cl = clamp(c.crop.l || 0, 0, .9), cr_ = clamp(c.crop.r || 0, 0, .9 - cl);
    const ct = clamp(c.crop.t || 0, 0, .9), cb = clamp(c.crop.b || 0, 0, .9 - ct);
    sx += sw * cl; sy += sh * ct; sw = Math.max(4, sw * (1 - cl - cr_)); sh = Math.max(4, sh * (1 - ct - cb));
  }
  if (c.reframe?.length) {
    const cw = Math.min(sw, sh * ST.p.w / ST.p.h), ch = Math.min(sh, sw * ST.p.h / ST.p.w);
    const cx = kfAt(c.reframe.map(r => ({ t: r.t, cx: r.cx })), "cx", srcTime(c, t), .5);
    sx = clamp(sx + cx * sw - cw / 2, 0, s.w - cw); sy = clamp(sy + (sh - ch) / 2, 0, s.h - ch); sw = cw; sh = ch;
  }
  const fit = defaultFit(c);
  fbx.setTransform(1, 0, 0, 1, 0, 0); fbx.clearRect(0, 0, W, H);
  fbx.filter = [adjCss(c.adj), fxCss(fxOn)].filter(Boolean).join(" ") || "none";
  let dw = W, dh = H, pipW = W, pipH = H;
  if (c.crop === "half-w" || c.crop === "half-h") {   // yan yana: kutuya kapla, kutu disi saydam
    const bw = c.crop === "half-w" ? W / 2 : W, bh = c.crop === "half-h" ? H / 2 : H, k = Math.max(bw / sw, bh / sh);
    const cw = bw / k, chh = bh / k;
    pipW = bw; pipH = bh;
    fbx.drawImage(s.src, sx + (sw - cw) / 2, sy + (sh - chh) / 2, cw, chh, (W - bw) / 2, (H - bh) / 2, bw, bh);
  } else {
    if (fit === "cover") { const k = Math.max(W / sw, H / sh); dw = sw * k; dh = sh * k; }
    else if (fit === "contain") { const k = Math.min(W / sw, H / sh); dw = sw * k; dh = sh * k; pipW = dw; pipH = dh; }
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
  if (tr?.cyan) SFX.tint(cbx, W, H, "#00e5ff", "lighter", tr.cyan);
  if (tr?.roll) {   // VHS sarma: goruntu dikeyde kayar (ffmpeg: crop y=mod(ih*4*(1-u),ih)) + gren
    const oy = H * ((4 * tr.roll) % 1), cp = SFX.copy(cbx, W, H);
    cbx.clearRect(0, 0, W, H); cbx.drawImage(cp, 0, -oy); cbx.drawImage(cp, 0, H - oy); SFX.overlay(cbx, "grain", W, H, t, local);
  }
  if (tr?.rgb) SFX.overlay(cbx, "rgb-strong", W, H, t, local);
  if (c.mask?.type && c.mask.type !== "none" && SFX.applyMask) src = SFX.applyMask(src, c.mask, W, H, PS) || src;
  // 3) donusum + ebeveyn katman + hareket bulanikligi + evrensel anahtar kare + blend -> ana tuval
  const clipXformAt = (cl, gt) => {
    const loc = clamp(gt - cl.start, 0, cl.dur), kf = cl.kf?.length ? kfResolve(cl.kf, cl.dur) : null;
    return {
      x: kf ? kfAt(kf, "x", loc, cl.x || 0) : (cl.x || 0),
      y: kf ? kfAt(kf, "y", loc, cl.y || 0) : (cl.y || 0),
      sc: kf ? kfAt(kf, "scale", loc, cl.scale ?? 1) : (cl.scale ?? 1),
      rot: kf ? kfAt(kf, "rot", loc, cl.rot || 0) : (cl.rot || 0),
      op: kf ? kfAt(kf, "opacity", loc, cl.opacity ?? 1) : (cl.opacity ?? 1),
    };
  };
  const xf = clipXformAt(c, t);
  let alpha = xf.op;
  const fi = Math.max(c.fadeIn || 0, c.trans?.in === "fade" ? (c.trans.dur || .35) : 0);
  if (fi > 0 && local < fi) alpha *= local / fi;
  if (c.fadeOut > 0 && c.dur - local < c.fadeOut) alpha *= Math.max(0, (c.dur - local) / c.fadeOut);
  const [shx, shy] = SFX.shakeOffset(fxOn.flatMap(id => ST.cat.fx[id]?.ov || []), t, W);
  alpha *= A.a;
  let mblur = 0;
  if ((c.shutterAngle || 0) >= 45) {
    const dt = 1 / Math.max(12, ST.p.fps || 30), pxf = clipXformAt(c, t - dt);
    const vel = Math.hypot((xf.x - pxf.x) * W, (xf.y - pxf.y) * H) + Math.abs(xf.sc - pxf.sc) * 80 + Math.abs(xf.rot - pxf.rot) * .45;
    mblur = Math.min(18, vel * (c.shutterAngle / 180) * .55);
  }
  vctx.save();
  vctx.globalAlpha = clamp(alpha, 0, 1);
  if (c.blend && c.blend !== "normal" && SFX.BLEND_JS?.[c.blend]) vctx.globalCompositeOperation = SFX.BLEND_JS[c.blend];
  const bl = Math.max(tr?.blur || 0, A.b * .45, mblur);
  if (bl > .05) vctx.filter = `blur(${bl * PS}px)`;
  if (tr?.mask) SFX.transMask(vctx, tr.mask, W, H);
  // AE ebeveynlik zinciri (uzerinden konum/olcek/dondurme mirasi)
  const pChain = [];
  if (c.parent) {
    const seen = new Set([c.id]); let cur = ST.p.clips.find(x => x.id === c.parent);
    while (cur && !seen.has(cur.id)) { seen.add(cur.id); pChain.unshift(cur); cur = cur.parent ? ST.p.clips.find(x => x.id === cur.parent) : null; }
  }
  vctx.translate(W / 2, H / 2);
  for (const pc of pChain) {
    const px = clipXformAt(pc, t);
    vctx.translate(px.x * W, px.y * H);
    if (px.rot) vctx.rotate(px.rot * Math.PI / 180);
    if (px.sc !== 1) vctx.scale(Math.max(1e-4, px.sc), Math.max(1e-4, px.sc));
  }
  const sc = xf.sc, kx = xf.x, ky = xf.y, kr = xf.rot;
  const rot = (kr + A.r + (tr?.rot || 0)) * Math.PI / 180;
  vctx.translate((kx + A.x) * W + shx + (tr?.dx || 0) * W, (ky + A.y) * H + shy + (tr?.dy || 0) * H);
  if (rot) vctx.rotate(rot);
  const ksx = sc * A.s * A.sx * (tr?.sx || 1), ksy = sc * A.s * A.sy * (tr?.sy || 1);
  if (ksx !== 1 || ksy !== 1 || c.flipH || c.flipV) {
    vctx.scale((c.flipH ? -1 : 1) * Math.max(1e-4, ksx), (c.flipV ? -1 : 1) * Math.max(1e-4, ksy));
  }
  const pipRad = (c.radius || 0) * 0.5 * Math.min(pipW, pipH);
  const pipBw = (c.borderW || 0) * PS;
  const pipSh = (c.shadow || 0) * PS;
  if (pipRad > .5 || pipBw > .25 || pipSh > .5) {
    const rx = -pipW / 2, ry = -pipH / 2;
    if (pipSh > .5 && alpha > .8) {
      vctx.save(); vctx.shadowColor = "rgba(0,0,0,.65)"; vctx.shadowBlur = pipSh; vctx.shadowOffsetY = pipSh * .35;
      vctx.fillStyle = "rgba(0,0,0,.9)"; vctx.beginPath(); vctx.roundRect(rx, ry, pipW, pipH, pipRad); vctx.fill();
      vctx.restore();
    }
    vctx.save();
    vctx.beginPath(); vctx.roundRect(rx, ry, pipW, pipH, pipRad); vctx.clip();
    vctx.drawImage(src, -W / 2, -H / 2);
    if (tr?.pix > .01) { vctx.globalAlpha *= tr.pix; vctx.drawImage(SFX.pixelate(src, W, H, 1), -W / 2, -H / 2); }
    vctx.restore();
    if (pipBw > .25) {
      vctx.strokeStyle = c.borderColor || "#8B5CF6"; vctx.lineWidth = pipBw * 2;
      vctx.beginPath(); vctx.roundRect(rx, ry, pipW, pipH, pipRad); vctx.stroke();
    }
  } else {
    vctx.drawImage(src, -W / 2, -H / 2);
    if (tr?.pix > .01) { vctx.globalAlpha *= tr.pix; vctx.drawImage(SFX.pixelate(src, W, H, 1), -W / 2, -H / 2); }
  }
  vctx.restore();
}
const lutLoading = new Set();
async function loadLut(name) {
  if (lutLoading.has(name)) return; lutLoading.add(name);
  try { const r = await job("studio_lut_read", [name]); SGL.setLut(name, r.n, r.data); draw(); } catch (e) { toast("LUT okunamadı: " + name); }
}
let drawQ = false;
function draw() { if (!drawQ) { drawQ = true; requestAnimationFrame(() => { drawQ = false; drawNow(); }); } }
const avImgCache = new Map();
function drawBgPattern(g, W, H, pat, c1, c2) {
  if (pat?.startsWith("gradient") || pat === "aurora") {
    const map = {
      "gradient-violet": ["#140B2E", "#6D28D9"],
      "gradient-sunset": ["#230B2E", "#EC4899"],
      "gradient-neon": ["#09182C", "#10B981"],
      "aurora": ["#0A1226", "#7C3AED"],
    };
    const [a, b] = map[pat] || [c1, c2];
    const gr = g.createLinearGradient(0, 0, 0, H); gr.addColorStop(0, a); gr.addColorStop(1, b);
    g.fillStyle = gr; g.fillRect(0, 0, W, H); return;
  }
  g.fillStyle = c1; g.fillRect(0, 0, W, H);
  g.strokeStyle = c2; g.fillStyle = c2;
  const step = Math.max(24, Math.round(W / 24));
  if (pat === "grid") {
    g.lineWidth = Math.max(1, W / 960);
    for (let x = 0; x < W; x += step) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x, H); g.stroke(); }
    for (let y = 0; y < H; y += step) { g.beginPath(); g.moveTo(0, y); g.lineTo(W, y); g.stroke(); }
  } else if (pat === "dots") {
    const r = Math.max(2, step / 10);
    for (let x = step / 2; x < W; x += step) for (let y = step / 2; y < H; y += step) { g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); }
  } else if (pat === "stripes") {
    g.lineWidth = Math.max(4, step / 3);
    for (let x = -H; x < W + H; x += step) { g.beginPath(); g.moveTo(x, 0); g.lineTo(x + H, H); g.stroke(); }
  }
}
function drawNow() {
  if (!ST.p) return;
  const t = ST.t, W = PW, H = PH;
  vctx.setTransform(1, 0, 0, 1, 0, 0); vctx.filter = "none"; vctx.globalAlpha = 1; vctx.globalCompositeOperation = "source-over";
  if (ST.p.bgMode === "pattern" && ST.p.bgPattern) {
    drawBgPattern(vctx, W, H, ST.p.bgPattern, ST.p.bg || "#140D24", ST.p.bg2 || "#5B21B6");
  } else {
    vctx.fillStyle = ST.p.bg || "#000"; vctx.fillRect(0, 0, W, H);
  }
  const vis = flatClips().filter(c => trackOf(c).kind === "video" && !trackOf(c).hide && t >= c.start - 1e-4 && t < c.start + c.dur + transTail(c))
    .sort((a, b) => trackOrder(a.track) - trackOrder(b.track) || a.start - b.start);
  if (ST.p.bgMode === "blur" && (ST.p.bgBlur ?? 45) > 0 && vis.length) {
    const bc = vis[0], bs = clipMedia(bc);
    if (bs) {
      const k = Math.max(W / bs.w, H / bs.h), dw = bs.w * k, dh = bs.h * k;
      vctx.save();
      vctx.filter = `blur(${((ST.p.bgBlur ?? 45) * 0.45 * PS).toFixed(1)}px) brightness(0.85)`;
      vctx.drawImage(bs.src, (W - dw) / 2, (H - dh) / 2, dw, dh);
      vctx.restore();
    }
  }
  for (const c of vis) { try { drawClip(c, t); } catch (e) { /* cerceve hazir degil */ } }
  for (const c of activeAt(t, "fx").sort((a, b) => trackOrder(a.track) - trackOrder(b.track))) {
    const local = t - c.start;
    const fids = [...(c.mode && c.mode !== "adjustment" ? [c.mode] : []), ...(c.fx || [])];
    const hasFilter = adjCss(c.adj) || fxCss(fids) || (SGL.ok && SGL.active(c)) || (c.blend && c.blend !== "normal") || ((c.opacity ?? 1) < 0.999);
    if (hasFilter) {
      cbx.setTransform(1, 0, 0, 1, 0, 0); cbx.clearRect(0, 0, W, H);
      cbx.filter = [adjCss(c.adj), fxCss(fids)].filter(Boolean).join(" ") || "none";
      cbx.drawImage(view, 0, 0, W, H); cbx.filter = "none";
      if (SGL.ok && SGL.active(c)) {
        if (c.grade?.lut && !SGL.has(c.grade.lut)) loadLut(c.grade.lut);
        const out = SGL.process(clipBuf, W, H, c);
        if (out) { cbx.clearRect(0, 0, W, H); cbx.drawImage(out, 0, 0); }
      }
      vctx.save();
      vctx.globalAlpha = clamp(c.opacity ?? 1, 0, 1);
      if (c.blend && c.blend !== "normal" && SFX.BLEND_JS?.[c.blend]) vctx.globalCompositeOperation = SFX.BLEND_JS[c.blend];
      vctx.drawImage(clipBuf, 0, 0);
      vctx.restore();
    }
    for (const id of fids) {
      const fx = ST.cat.fx[id]; if (!fx) continue;
      const [sx, sy] = SFX.shakeOffset(fx.ov || [], t, W);
      if (sx || sy) { const cp = SFX.copy(vctx, W, H); vctx.save(); vctx.translate(sx, sy); vctx.scale(1.04, 1.04); vctx.translate(-W * .02, -H * .02); vctx.drawImage(cp, 0, 0); vctx.restore(); }
      for (const ov of fx.ov || []) SFX.overlay(vctx, ov, W, H, t, local);
    }
  }
  for (const c of activeAt(t, "text")) {
    const av = c.style?.avatarImg;
    if (!av || (c.graphic !== "endscreen" && c.subscribe !== "channel")) continue;
    let im = avImgCache.get(av);
    if (!im) { im = new Image(); im.onload = () => draw(); im.src = av; avImgCache.set(av, im); }
    if (!im.complete || !im.naturalWidth) continue;
    const sz = Math.max(24, 126 * (H / 1080) * ((c.style?.size ?? 100) / 100));
    const cx = c.graphic === "endscreen" ? W / 2 : W * (c.style?.x ?? 0.5) - 225 * (H / 1080);
    const cy = c.graphic === "endscreen" ? H * 0.82 : H * (c.style?.y ?? 0.8);
    vctx.save();
    vctx.beginPath(); vctx.arc(cx, cy, sz / 2, 0, Math.PI * 2); vctx.closePath(); vctx.clip();
    vctx.drawImage(im, cx - sz / 2, cy - sz / 2, sz, sz);
    vctx.restore();
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
  if (ST.loopOn && ST.loopIn != null && ST.loopOut != null && ST.loopOut > ST.loopIn + .05 && ST.t >= ST.loopOut) {
    ST.t = ST.loopIn; wall0 = now; t0 = ST.t; syncMedia(ST.t, true);
  }
  const end = projEnd();
  if (ST.t >= end) { ST.t = end; play(false); return; }
  syncMedia(ST.t); drawNow(); followPlayhead();
  if ((now | 0) % 1000 < 17) assTime();
  raf = requestAnimationFrame(tick);
}
function seek(t) {
  ST.t = clamp(t, 0, Math.max(projEnd(), 0));
  if (ST.playing) { wall0 = performance.now(); t0 = ST.t; }
  else if (ST.scrubAudio) {
    ST._scrubActive = true;
    clearTimeout(ST._scrubT);
    ST._scrubT = setTimeout(() => { ST._scrubActive = false; syncMedia(ST.t, false); }, 95);
  }
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
    (t.kind === "video" || t.kind === "audio" ? `<button data-th="mute" class="${t.mute ? "on" : ""}" title="Sessiz">${t.mute ? "🔇" : "🔊"}</button><button data-th="solo" class="${t.solo ? "on" : ""}" title="Solo (Sadece bu iz)">S</button>` : "") +
    `<button data-th="hide" class="${t.hide ? "on" : ""}" title="Gizle">${t.hide ? "◌" : "◉"}</button><button data-th="lock" class="${t.lock ? "on" : ""}" title="Kilitle">${t.lock ? "🔒" : "🔓"}</button></div>`).join("");
  const frag = document.createDocumentFragment();
  for (const t of ST.p.tracks) {
    const ln = document.createElement("div"); ln.className = "lane" + (t.lock ? " locked" : ""); ln.dataset.tid = t.id; ln.style.setProperty("--h", laneH(t) + "px");
    for (const c of ST.p.clips.filter(c => c.track === t.id)) ln.appendChild(clipEl(c, t));
    for (const ct of (ST.p.cuts || []).filter(x => x.track === t.id)) {
      const cm = document.createElement("div");
      cm.className = "cut-mark" + (ST.cutSel.has(ct.id) ? " sel" : "");
      cm.dataset.cutid = ct.id;
      cm.style.left = (ct.seamStart * ST.px) + "px";
      cm.title = `Kesilen bölge (${ct.dur.toFixed(2)} sn) — tıkla/çoklu seç ve eski haline getir`;
      ln.appendChild(cm);
    }
    frag.appendChild(ln);
  }
  lanes.innerHTML = ""; lanes.appendChild(frag);
  for (const m of $$(".mk", $("#tlInner"))) m.remove();
  for (const m of ST.p.markers || []) { const d = document.createElement("div"); d.className = "mk " + (m.kind || ""); d.style.left = (m.t * ST.px) + "px"; $("#tlInner").appendChild(d); }
  drawRuler(); updateTC();
  const n = ST.sel.size, cn = ST.cutSel.size;
  $("#selInfo").textContent = cn ? `${cn} kesim seçili` : n ? `${n} klip seçili` : "";
}
function clipEl(c, t) {
  const k = clipKind(c), a = assetOf(c), el = document.createElement("div");
  el.className = `clip ${k}${ST.sel.has(c.id) ? " sel" : ""}`; el.dataset.cid = c.id;
  const w = Math.max(3, c.dur * ST.px);
  el.style.left = (c.start * ST.px) + "px"; el.style.width = w + "px";
  let label = "";
  if (k === "text") label = c.subscribe ? `🔔 ${ST.cat.subscribe[c.subscribe] || c.subscribe}` : c.graphic ? `◆ ${ST.cat.graphics?.[c.graphic] || c.graphic}` : c.sticker ? `🎭 ${ST.cat.stickers?.[c.sticker]?.n || c.sticker}` : c.words ? `≡ Altyazı (${c.words.length} kelime)` : "T " + (c.text || "");
  else if (k === "fx") label = c.mode === "adjustment" ? "✨ Ayar Katmanı" : ("✦ " + (ST.cat.fx[c.mode]?.name || c.mode));
  else if (k === "compound") label = "⧉ " + (c.name || `Bileşik (${c.children?.length || 0} klip)`);
  else label = a?.name || "?";
  const tags = [];
  if (c.reverse) tags.push("◀");
  if ((c.speed || 1) !== 1) tags.push(`${c.speed}×`);
  if (c.ramp?.length) tags.push("⤳"); if (c.freeze) tags.push("❄"); if (c.key?.on) tags.push("▣"); if (c.grade && SGL.active({ grade: c.grade })) tags.push("◐"); if (c.afx?.length) tags.push("♪" + c.afx.length);
  if (c.fx?.length) tags.push("✦" + c.fx.length);
  if (c.kf?.length) tags.push("◆" + c.kf.length);
  if (c.mask?.type && c.mask.type !== "none") tags.push("◒");
  if (c.blend && c.blend !== "normal") tags.push("◧");
  if (c.parent) tags.push("↳");
  if (c.optFlow) tags.push("≈");
  if (c.eq?.some(x => Math.abs(x) >= .1)) tags.push("▥");
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
  for (const z of kfResolve(c.kf || [], c.dur)) { const d = document.createElement("div"); d.className = "kfm ukf"; d.style.left = z.t * ST.px + "px"; el.appendChild(d); }
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
  cv.width = w; cv.height = 38; cv.style.width = w + "px";
  const g = cv.getContext("2d"); g.clearRect(0, 0, w, 38);
  g.strokeStyle = "rgba(255,255,255,.06)"; g.beginPath(); g.moveTo(0, 20.5); g.lineTo(w, 20.5); g.stroke();
  g.fillStyle = "#8E86A3"; g.strokeStyle = "#3A2E58"; g.font = "10px Chakra Petch";
  const steps = [0.1, 0.25, .5, 1, 2, 5, 10, 15, 30, 60, 120, 300];
  const major = steps.find(s => s * ST.px >= 70) || 600, minor = major / 5;
  for (let t = 0; t * ST.px < w; t += minor) {
    const x = Math.round(t * ST.px) + .5 - x0, isM = Math.abs(t / major - Math.round(t / major)) < 1e-6;
    g.beginPath(); g.moveTo(x, isM ? 8 : 14); g.lineTo(x, 20); g.stroke();
    if (isM) { const tt = Math.round(t * 1000) / 1000; g.fillText(major < 1 ? tt + "s" : fmt(tt + 1e-6, false), x + 3, 10); }
  }
  g.fillStyle = "rgba(255,181,71,.85)";
  for (const m of ST.p.markers || []) g.fillRect(Math.round(m.t * ST.px) - 1, 22, 3, 14);
  if (ST.loopIn != null || ST.loopOut != null) {
    const x1 = Math.round((ST.loopIn ?? 0) * ST.px), x2 = Math.round((ST.loopOut ?? ST.loopIn ?? 0) * ST.px);
    if (x2 > x1) { g.fillStyle = ST.loopOn ? "rgba(46,230,166,.26)" : "rgba(46,230,166,.12)"; g.fillRect(x1, 0, x2 - x1, 8); }
    g.fillStyle = "#2EE6A6";
    if (ST.loopIn != null) g.fillRect(x1, 0, 2, 16);
    if (ST.loopOut != null) g.fillRect(x2 - 1, 0, 2, 16);
  }
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
  const cutEl = e.target.closest(".cut-mark");
  if (cutEl) {
    e.preventDefault();
    const cid = cutEl.dataset.cutid;
    ST.sel.clear();
    if (e.shiftKey || e.ctrlKey) { ST.cutSel.has(cid) ? ST.cutSel.delete(cid) : ST.cutSel.add(cid); }
    else { ST.cutSel = new Set([cid]); }
    renderTimeline(); renderInsp(); renderHandles();
    return;
  }
  const ce = e.target.closest(".clip");
  if (!ce) {   // bos alan: oynatma kafasi + secimi temizle / dikdortgen secim
    if (!e.shiftKey) { ST.sel.clear(); ST.cutSel.clear(); }
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
      for (const el of $$(".cut-mark", lanes)) { const r = el.getBoundingClientRect(); const hit = r.right > x1 && r.left < x2 && r.bottom > y1 && r.top < y2; el.classList.toggle("sel", hit || ST.cutSel.has(el.dataset.cutid)); }
    };
    const up = () => {
      document.removeEventListener("pointermove", mv); document.removeEventListener("pointerup", up);
      if (on) {
        for (const el of $$(".clip.sel", lanes)) ST.sel.add(el.dataset.cid);
        for (const el of $$(".cut-mark.sel", lanes)) ST.cutSel.add(el.dataset.cutid);
        mq.remove();
      }
      renderTimeline(); renderInsp(); renderHandles();
    };
    document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
    return;
  }
  const c = ST.p.clips.find(x => x.id === ce.dataset.cid); if (!c) return;
  if (trackOf(c).lock) return;
  ST.cutSel.clear();
  e.preventDefault();
  if (e.shiftKey || e.ctrlKey) { ST.sel.has(c.id) ? ST.sel.delete(c.id) : ST.sel.add(c.id); }
  else if (!ST.sel.has(c.id)) { ST.sel = new Set([c.id]); }
  const edge = e.target.classList.contains("eg") ? (e.target.classList.contains("l") ? "l" : "r") : "";
  let group = selClips();
  if (!edge && !e.altKey && ST.linkTracks && group.length === 1) {
    group = linkedPeers(group[0]).filter(x => !trackOf(x).lock);
  }
  const st0 = group.map(x => ({ c: x, start: x.start, dur: x.dur, in: x.in || 0, track: x.track }));
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
      if (ST.editMode === "slip" && group.length === 1) {
        const s0 = st0[0], a = assetOf(c), sp = c.speed || 1;
        const maxSrc = a && (a.kind !== "image" || a.gif) ? Math.max(0, a.dur - s0.dur * sp) : 1e6;
        c.in = clamp(+(s0.in - dx * sp).toFixed(4), 0, maxSrc);
        draw();
        return;
      }
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
    if (moved) {
      if (edge && (ST.editMode === "ripple" || ST.editMode === "roll") && group.length === 1 && api.studio_timeline_edit) {
        const s0 = st0[0];
        let targetId = c.id, targetEdge = edge === "l" ? "in" : "out", diff = edge === "r" ? (c.dur - s0.dur) : (c.start - s0.start);
        if (ST.editMode === "roll" && edge === "l") {
          const prev = ST.p.clips.filter(oc => oc !== c && oc.track === c.track && oc.start + oc.dur <= s0.start + 0.08).sort((a, b) => (b.start + b.dur) - (a.start + a.dur))[0];
          if (prev) { targetId = prev.id; targetEdge = "out"; } else diff = 0;
        }
        if (Math.abs(diff) > 1e-4) {
          c.start = s0.start; c.dur = s0.dur; c.in = s0.in;
          api.studio_timeline_edit(ST.p.clips, ST.editMode, targetId, diff, targetEdge).then(r => {
            if (r?.ok) { ST.p.clips = r.clips; changed(); }
          });
          return;
        }
      } else if (!edge && ST.editMode === "slide" && group.length === 1) {
        const s0 = st0[0], diff = +(c.start - s0.start).toFixed(4);
        if (Math.abs(diff) > 1e-4 && api.studio_timeline_edit) {
          c.start = s0.start;
          api.studio_timeline_edit(ST.p.clips, "slide", c.id, diff, "out").then(r => {
            if (r?.ok) { ST.p.clips = r.clips; changed(); }
          });
          return;
        }
      }
      if (ST.editMode !== "slip") { for (const s of st0) if (overlaps(s.c)) resolveOverlap(s.c); }
      changed();
    }
    else { renderTimeline(); renderHandles(); if (!edge && !e.shiftKey) seekIfOutside(c, e); }
  };
  document.addEventListener("pointermove", mv); document.addEventListener("pointerup", up);
});
function st0Words(c, d) { return c.words; }   // altyazi kelimeleri klip basina gore: sol kirpmada kaydir
function seekIfOutside(c, e) { seek(tAt(e.clientX)); }
lanes.addEventListener("dblclick", e => {
  const ce = e.target.closest(".clip"); if (!ce) return;
  const c = ST.p.clips.find(x => x.id === ce.dataset.cid);
  if (c?.kind === "compound") { enterCompound(c); return; }
  ST.sel = new Set([ce.dataset.cid]); window.focusInsp?.();
});
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
const UKF_DEFS = { scale: ["Ölçek", 1], x: ["X", 0], y: ["Y", 0], rot: ["Döndür", 0], opacity: ["Opaklık", 1], vol: ["Ses", 1] };
function ukfResolve(c) { return kfResolve(c.kf || [], c.dur); }
function ukfActiveIdx(kf, lt) {
  if (kf.length < 2) return -1;
  if (ST.bezIdx >= 1 && ST.bezIdx < kf.length) return ST.bezIdx;
  const i = kf.findIndex(k => k.t > lt);
  return i >= 1 ? i : kf.length - 1;
}
function fldkf(c, label, key, min, max, step, val) {
  const lt = clamp(ST.t - c.start, 0, c.dur);
  const kfs = c.kf || [];
  const near = kfs.some(k => key in k && Math.abs((k.t < 0 ? c.dur + k.t : k.t) - lt) < .06);
  const any = kfs.some(k => key in k);
  const cur = any && ST.t >= c.start && ST.t <= c.start + c.dur ? kfAt(ukfResolve(c), key, lt, val) : val;
  return `<label class="fld kfa"><button type="button" class="kfbtn${near ? " on" : any ? " has" : ""}" data-ukf="${key}" title="Oynatma kafasına anahtar kare (◆) ekle / kaldır">◆</button><span>${label}</span><input type="range" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${cur}"><input type="number" class="num" data-k="${key}" min="${min}" max="${max}" step="${step}" value="${+(+cur).toFixed(3)}"></label>`;
}
function ukfInsp(c) {
  const kf = ukfResolve(c), lt = clamp(ST.t - c.start, 0, c.dur);
  const ai = ukfActiveIdx(kf, lt);
  const rows = kf.map((k, i) => {
    const ps = Object.keys(UKF_DEFS).filter(p => p in k).map(p => `${UKF_DEFS[p][0]}:${(+k[p]).toFixed(2)}`).join(" · ");
    return `<div class="kf${i === ai ? " sel" : ""}" data-ukfpick="${i}" title="Tıkla: zamana git & eğriyi düzenle"><b>${k.t.toFixed(2)}s</b><span>${esc(ps || "kare")}</span><button data-ukfdel="${i}" title="Sil">✕</button></div>`;
  }).join("");
  const curBez = ai >= 1 ? (Array.isArray(kf[ai].bez) ? kf[ai].bez : (ST.cat.bezierPresets?.[kf[ai].bez] || [0, 0, 1, 1])) : [0, 0, 1, 1];
  const bezMap = { linear: "Doğrusal", ease: "Yumuşak", easeOutExpo: "Expo Out", snappy: "Keskin", filmEase: "Sinema", pop: "Yaylı" };
  let bHtml = "";
  if (kf.length >= 2 && ai >= 1) {
    const activeKey = typeof kf[ai].bez === "string" ? kf[ai].bez : "";
    bHtml = `<div class="bez-hd"><span class="hint">Eğri: ${kf[ai - 1].t.toFixed(2)}s → ${kf[ai].t.toFixed(2)}s</span></div>` +
      `<div class="catpills">${Object.entries(bezMap).map(([id, n]) => `<button type="button" class="${activeKey === id ? "on" : ""}" data-bez="${id}">${n}</button>`).join("")}</div>` +
      `<canvas id="bezCv" width="210" height="120" title="Mor/yeşil tutamaçları sürükle (overshoot için yukarı/aşağı taşıyabilirsin)"></canvas>` +
      `<div class="hint" style="margin-top:2px">P(${curBez.map(v => (+v).toFixed(2)).join(", ")})</div>`;
  }
  return `<div class="sec">Anahtar Kareler & Bezier ◆</div><div class="kfl">${rows || '<span class="hint">Özellik yanındaki ◆ simgesine tıkla (Ölçek, Konum, Döndür, Opaklık, Ses).</span>'}</div>` +
    bHtml + (kf.length ? `<div class="row" style="margin-top:4px"><button class="tb" data-a2="ukfclear">◆ Tümünü temizle</button></div>` : "");
}
function renderInsp() {
  const box = $("#insp"); if (!ST.p) return;
  if (ST.cutSel.size) {
    const selCuts = (ST.p.cuts || []).filter(ct => ST.cutSel.has(ct.id));
    if (selCuts.length) {
      const tot = selCuts.reduce((s, x) => s + x.dur, 0);
      box.innerHTML = `<div class="ph"><b>${selCuts.length === 1 ? "Kesilen bölge" : `${selCuts.length} kesilen bölge`}</b><span class="sp"></span><span class="hint">${tot.toFixed(2)} sn</span></div>` +
        `<div class="hint">Sadece seçtiğin bu kesim bölgeleri zaman çizelgesinde eski haline getirilir. Ctrl/Shift ile veya sürükleyerek çoklu seçebilirsin.</div>` +
        `<div class="row"><button class="tb pri" data-a2="restoreCuts">Eski haline getir (${selCuts.length})</button><button class="tb" data-a2="dropCuts">İzi sil</button></div>`;
      return;
    }
  }
  const cs = selClips();
  if (!cs.length) { box.innerHTML = projInsp(); return; }
  if (cs.length > 1) { box.innerHTML = `<div class="ph"><b>${cs.length} klip</b></div>${multiInsp(cs)}`; return; }
  const c = cs[0], k = clipKind(c), a = assetOf(c);
  let h = `<div class="ph"><b>${{ video: "Video", image: "Görsel", audio: "Ses", text: c.subscribe ? "Abone" : c.words ? "Altyazı" : "Metin", fx: c.mode === "adjustment" ? "Ayar Katmanı" : "Efekt" }[k]}</b><span class="sp"></span><span class="hint">${fmt(c.start)} · ${c.dur.toFixed(2)} sn</span></div>`;
  if (a) h += `<div class="hint" style="margin-top:-4px">${esc(a.name)}${a.missing ? ' <b style="color:var(--red)">(dosya yok)</b>' : ""}</div>`;
  if (k === "video" || k === "image") {
    const blends = ST.cat.blends || { normal: "Normal", screen: "Ekran (Screen)", overlay: "Kaplama (Overlay)", multiply: "Çarpma (Multiply)", lighten: "Aydınlat", darken: "Koyulaştır", dodge: "Soldur (Dodge)", difference: "Fark", addition: "Ekle (Add)" };
    const masks = ST.cat.masks || { none: "Yok", circle: "Daire / Elips", rect: "Dikdörtgen", split: "Bölünmüş", mirror: "Ayna", filmstrip: "Film Şeridi", star: "Yıldız", heart: "Kalp" };
    const mk = c.mask || {};
    h += `<div class="sec">Görüntü</div>` + `<div class="fld w2"><span>Sığdır</span><div class="seg" data-seg="fit">${[["cover", "Kapla"], ["contain", "Sığdır"], ["stretch", "Uzat"]].map(([v, l]) => `<button data-v="${v}" class="${defaultFit(c) === v ? "on" : ""}">${l}</button>`).join("")}</div></div>` +
      fldkf(c, "Ölçek", "scale", .05, 4, .01, c.scale ?? 1) + fldkf(c, "Konum X", "x", -1, 1, .005, c.x || 0) + fldkf(c, "Konum Y", "y", -1, 1, .005, c.y || 0) +
      fldkf(c, "Döndür", "rot", -180, 180, 1, c.rot || 0) +
      `<div class="row tight" style="margin-bottom:6px"><button class="tb" data-a2="rot90" title="90° saat yönünde döndür">↻ 90°</button><button class="tb${c.flipH ? " on" : ""}" data-a2="flipH" title="Yatay ayna">⇄ Ayna</button><button class="tb${c.flipV ? " on" : ""}" data-a2="flipV" title="Dikey ters çevir">⇅ Ters çevir</button><button class="tb" data-a2="resetXform" title="Dönüşümü sıfırla">↺</button></div>` +
      fldkf(c, "Opaklık", "opacity", 0, 1, .01, c.opacity ?? 1) +
      sel("Karışım", "blend", blends, c.blend || "normal") +
      fld("Hareket bulanıklığı", "shutterAngle", 0, 360, 15, c.shutterAngle || 0) +
      `<div class="sec">Kırpma (Crop)</div>`;
    const cr = typeof c.crop === "object" && c.crop ? c.crop : { l: 0, r: 0, t: 0, b: 0 };
    h += fld("Sol", "crop.l", 0, .45, .01, cr.l || 0) + fld("Sağ", "crop.r", 0, .45, .01, cr.r || 0) +
      fld("Üst", "crop.t", 0, .45, .01, cr.t || 0) + fld("Alt", "crop.b", 0, .45, .01, cr.b || 0) +
      `<div class="row tight" style="margin-bottom:6px"><button class="tb" data-a2="hudCrop" title="Üst HUD/panel kırpıp yaklaştır">🎯 HUD Yakın Kırp</button><button class="tb" data-a2="resetCrop">↺ Sıfırla</button></div>` +
      `<div class="sec">PiP Köşe / Kenarlık</div>` +
      fld("Yuvarlaklık", "radius", 0, 1, .02, c.radius || 0) + fld("Kenarlık px", "borderW", 0, 24, 1, c.borderW || 0) +
      color("Kenar rengi", "borderColor", c.borderColor || "#8B5CF6") + fld("Gölge", "shadow", 0, 48, 1, c.shadow || 0);
    const leadsToSelf = x => { const s = new Set([c.id]); let cur = x; while (cur) { if (s.has(cur.id)) return true; s.add(cur.id); cur = cur.parent ? ST.p.clips.find(z => z.id === cur.parent) : null; } return false; };
    const pOpts = { "": "Yok", ...Object.fromEntries(ST.p.clips.filter(x => x !== c && ["video", "image"].includes(clipKind(x)) && !leadsToSelf(x)).map(x => [x.id, `${assetOf(x)?.name || x.id} (${fmt(x.start, false)})`])) };
    h += sel("Ebeveyn katman", "parent", pOpts, c.parent || "");
    h += `<div class="sec">Maske</div>` + sel("Şekil", "mask.type", masks, mk.type || "none");
    if (mk.type && mk.type !== "none") {
      h += fld("Merkez X", "mask.x", 0, 1, .01, mk.x ?? .5) + fld("Merkez Y", "mask.y", 0, 1, .01, mk.y ?? .5) +
        fld("Genişlik", "mask.w", .05, 1.5, .01, mk.w ?? .55) + fld("Yükseklik", "mask.h", .05, 1.5, .01, mk.h ?? .55) +
        fld("Açı", "mask.rot", -180, 180, 1, mk.rot || 0) + fld("Yumuşaklık", "mask.feather", 0, 40, 1, mk.feather ?? 4) +
        chk("Ters çevir (İç↔Dış)", "mask.invert", mk.invert);
    }
  }
  if (k === "video" || k === "audio") {
    h += `<div class="sec">Hız</div>` + fld("Hız", "speed", .1, 8, .05, c.speed || 1) +
      `<div class="row tight">${[.25, .5, 1, 1.5, 2, 4].map(v => `<button class="tb" data-speed="${v}">${v}×</button>`).join("")}</div>`;
    if (k === "video") {
      h += chk("◀ Ters Oynat (Reverse)", "reverse", c.reverse) +
        chk("Optik Akış (Yumuşak yavaşlatma)", "optFlow", c.optFlow) +
        chk("Görüntü Sabitle (Deshake)", "stabilize", c.stabilize);
      h += `<div class="sec">Hız rampası</div><div class="grid3 ramps">${Object.entries(RAMPS).map(([id, r]) => `<button class="tb${(id === "none" && !c.ramp) ? " on" : ""}" data-ramp="${id}">${r.n}</button>`).join("")}</div>` +
        (c.ramp ? `<canvas id="rampCv" width="270" height="96" title="Noktayı sürükle · çift tık: nokta ekle · sağ tık: sil"></canvas><div class="hint">Yukarı = hızlı, aşağı = yavaş. Klip süresi kendiliğinden ayarlanır.</div>` : "");
    }
  }
  if (k === "audio" || (k === "video" && a?.audio)) {
    const curves = ST.cat.audioCurves || { tri: "Doğrusal", qsin: "Yumuşak (S-Eğri)", log: "Logaritmik", exp: "Keskin (Üstel)" };
    const eqPre = ST.cat.eqPresets || { flat: ["Düz", [0,0,0,0,0,0,0,0,0,0]], podcast: ["Podcast", [-6,-4,-2,-1,1,2,4,5,3,1]], bass: ["Bas", [6,5,4,2,0,-1,0,1,1,0]], bright: ["Tiz", [-1,-1,0,0,1,2,3,5,6,5]], radio: ["Radyo", [-12,-10,-6,2,5,6,4,-4,-9,-12]], cinema: ["Sinema", [3,2,1,0,-1,1,2,2,3,2]] };
    const vVoices = ST.cat.voiceChangers || { none: "Normal", chipmunk: "🐿️ Sincap (+7st)", deep: "🎙️ Kalın (-5st)", robot: "🤖 Robot", megaphone: "📢 Megafon", demon: "👹 Demon" };
    h += `<div class="sec">Ses</div>` + fldkf(c, "Ses düzeyi", "vol", 0, 2, .01, c.vol ?? 1) +
      fld("Perde (Pitch st)", "pitch", -12, 12, .5, c.pitch || 0) +
      sel("Ses Değiştirici", "voice", vVoices, c.voice || "none") +
      fld("Stereo Pan", "pan", -1, 1, .05, c.pan || 0) +
      fld("Açılış", "fadeIn", 0, 5, .05, c.fadeIn || 0) + fld("Kapanış", "fadeOut", 0, 5, .05, c.fadeOut || 0) +
      sel("Ses eğrisi", "fadeCurve", curves, c.fadeCurve || "tri") +
      (k === "video" ? fld("J-Cut Önden (sn)", "audioLead", 0, 4, .1, c.audioLead || 0) + fld("L-Cut Sona (sn)", "audioTail", 0, 4, .1, c.audioTail || 0) + `<div class="row tight"><button class="tb" data-a2="jlcut">⇄ J/L Doğrula</button></div>` : "") +
      `<div class="catpills">${Object.entries(eqPre).map(([id, [nm]]) => `<button type="button" data-eqp="${id}" title="10-bant EQ ön ayarı">${esc(nm)}</button>`).join("")}</div>` +
      `<div class="row"><button class="tb" data-a2="toaudio">▥ Mikserde 10-Bant EQ aç</button></div>`;
  } else if (k === "video" || k === "image") h += `<div class="sec">Belir / kaybol</div>` + fld("Açılış", "fadeIn", 0, 5, .05, c.fadeIn || 0) + fld("Kapanış", "fadeOut", 0, 5, .05, c.fadeOut || 0);
  if (k === "video" || k === "image" || k === "audio") h += ukfInsp(c);
  if (k === "video" || k === "image") {
    const ad = c.adj || {};
    h += `<div class="sec">Renk</div>` + fld("Parlaklık", "adj.bri", -50, 50, 1, ad.bri || 0) + fld("Kontrast", "adj.con", -50, 80, 1, ad.con || 0) +
      fld("Doygunluk", "adj.sat", -100, 150, 1, ad.sat || 0) + fld("Ton", "adj.hue", -180, 180, 1, ad.hue || 0) + fld("Sıcaklık", "adj.temp", -100, 100, 1, ad.temp || 0) + fld("Bulanık", "adj.blur", 0, 20, .5, ad.blur || 0);
    h += `<div class="sec">9-Nokta Sabitleme & Ease (AEJuice)</div><div class="row" style="align-items:center;gap:10px"><div class="anc9">${["tl", "tc", "tr", "ml", "center", "mr", "bl", "bc", "br"].map(pt => `<button class="${(c.anchor || "center") === pt ? "on" : ""}" data-anc="${pt}" title="Sabitle: ${pt}">•</button>`).join("")}</div><div style="display:flex;flex-direction:column;gap:4px"><button class="tb" data-a2="copyease" title="Shift+C">🎯 Ease Kopyala</button><button class="tb" data-a2="pasteease" title="Shift+V">📥 Ease Yapıştır</button></div></div>`;
    h += window.animBox ? animBox(c, "clip") : "";
    h += `<div class="sec">Efektler</div>` + (window.fxRows ? fxRows(c) : "");
    h += `<div class="sec">Giriş geçişi</div>` + sel("Geçiş", "trans.in", ST.cat.trans, c.trans?.in || "none") + fld("Süre", "trans.dur", .1, 2, .05, c.trans?.dur || .35) +
        chk("Önceki klip altta devam etsin (A→B)", "trans.over", c.trans?.over !== false);
    h += zoomInsp(c);
    h += `<div class="sec">Dikey çerçeve</div><div class="row"><button class="tb" data-a2="reframe">▯ Yüzü takip et</button>${c.reframe?.length ? '<button class="tb" data-a2="unreframe">Kaldır</button>' : ""}</div>`;
  }
  if (k === "audio" || (k === "video" && a?.audio)) h += `<div class="sec">Ses düzeltme & Akustik Mekan</div><div class="chips">${Object.entries(ST.cat.afx || {}).map(([id, n]) => `<button class="tb${(c.afx || []).includes(id) ? " on" : ""}" data-afx="${id}" style="font-size:11px;padding:4px 8px">${esc(n)}</button>`).join("")}</div>` +
    fld("Efekt Mix (Dry/Wet)", "afxMix", 0, 1, .05, c.afxMix ?? 1) +
    chk("Mono Sum (Stereo → Mono)", "monoSum", c.monoSum) +
    chk("Faz Tersle (180° Phase Invert)", "phaseInvert", c.phaseInvert) +
    (a?.path ? `<div class="row"><button class="tb" data-a2="similarsnd">🔍 Benzer Yerel Sesler (Find Similar)</button></div>` : "") +
    `<div class="hint">Önizlemede temel ayarlar, dışa aktarımda tüm akustik zincir (Place it + Shape it) uygulanır.</div>`;
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
    const opts = { adjustment: "✨ Ayar Katmanı (Renk + Yığma FX)", ...Object.fromEntries(Object.entries(ST.cat.fx).map(([id, f]) => [id, `${f.pack} · ${f.name}`])) };
    h += `<div class="sec">Mod</div>` + sel("Efekt", "mode", opts, c.mode);
    if (c.mode === "adjustment") {
      const ad = c.adj || {}, blends = ST.cat.blends || { normal: "Normal", screen: "Ekran (Screen)", overlay: "Kaplama (Overlay)", multiply: "Çarpma (Multiply)" };
      h += sel("Karışım", "blend", blends, c.blend || "normal") + fld("Opaklık", "opacity", 0, 1, .01, c.opacity ?? 1) +
        `<div class="sec">Renk</div>` + fld("Parlaklık", "adj.bri", -50, 50, 1, ad.bri || 0) + fld("Kontrast", "adj.con", -50, 80, 1, ad.con || 0) +
        fld("Doygunluk", "adj.sat", -100, 150, 1, ad.sat || 0) + fld("Ton", "adj.hue", -180, 180, 1, ad.hue || 0) +
        fld("Sıcaklık", "adj.temp", -100, 100, 1, ad.temp || 0) + fld("Bulanık", "adj.blur", 0, 20, .5, ad.blur || 0) +
        `<div class="sec">Efektler</div>` + (window.fxRows ? fxRows(c) : "") +
        `<div class="row"><button class="tb" data-a2="tocolor">◐ Renk sayfasında düzenle</button></div>`;
    } else {
      if (["vhs", "cctv", "nightvision", "found", "bodycam"].includes(c.mode)) h += `<label class="fld w2"><span>Tarih</span><input class="in" data-k="date" value="${esc(c.date || "")}" placeholder="bugün"></label>`;
      if (c.mode === "cctv") h += `<label class="fld w2"><span>Kamera adı</span><input class="in" data-k="cam" value="${esc(c.cam || "CAM 03")}"></label>`;
    }
  }
  h += `<div class="sec">Zaman</div>` + `<div class="grid2"><label class="fld w2" style="grid-template-columns:44px 1fr"><span>Başla</span><input type="number" class="in" data-k="start" step="0.01" value="${c.start.toFixed(2)}"></label><label class="fld w2" style="grid-template-columns:44px 1fr"><span>Süre</span><input type="number" class="in" data-k="dur" step="0.01" value="${c.dur.toFixed(2)}"></label></div>`;
  box.innerHTML = h;
  rampCanvas(c);
  bezCanvas(c);
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
  const allFonts = [...new Set([...(ST.cat.fonts || []), ...(st.font ? [st.font] : [])])];
  const fontIn = (key, val) => `<label class="fld w2"><span>Font</span><select class="in" data-k="${key}">${allFonts.map(f => `<option value="${esc(f)}"${f === val ? " selected" : ""} style="font-family:'${esc(f)}',sans-serif">${esc(f)}</option>`).join("")}</select></label>`;
  let h = "";
  if (c.sticker) {
    const sOpts = Object.fromEntries(Object.entries(ST.cat.stickers || {}).map(([k, v]) => [k, `${v.ico || "◆"} ${v.n || k}`]));
    h += `<div class="sec">Çıkartma (Sticker)</div>` + sel("Sembol", "sticker", sOpts, c.sticker) +
      color("Renk", "style.color", st.color || "#8B5CF6") + fld("Boyut", "style.size", 30, 300, 1, st.size ?? 100) +
      fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .5) + fontIn("style.font", st.font || "Chakra Petch");
    return h;
  }
  if (c.graphic) {
    const G = c.graphic;
    h += `<div class="sec">Grafik</div>` + sel("Tür", "graphic", ST.cat.graphics || {}, G) +
      (["lower", "lower-min", "location", "chapter", "callout", "highlight", "quote", "news-card", "split-card", "stat-table", "birazdan"].includes(G) ? `<label class="fld w2"><span>Başlık</span><input class="in" data-k="style.title" value="${esc(st.title || "")}"></label>` : "") +
      (["lower", "lower-min", "location", "quote", "news-card", "split-card", "birazdan"].includes(G) ? `<label class="fld w2"><span>Alt yazı</span><input class="in" data-k="style.sub" value="${esc(st.sub || "")}"></label>` : "") +
      (G === "news-card" ? `<label class="fld w2"><span>Etiket</span><input class="in" data-k="style.badge" value="${esc(st.badge || "SON DAKİKA")}"></label>` : "") +
      (G === "split-card" ? `<label class="fld w2"><span>Sol</span><input class="in" data-k="style.left" value="${esc(st.left || "ÖNCE")}"></label><label class="fld w2"><span>Sağ</span><input class="in" data-k="style.right" value="${esc(st.right || "SONRA")}"></label>` : "") +
      (G === "stat-table" ? `<label class="fld w2"><span>Satırlar</span><input class="in" data-k="style.rows" value="${esc(st.rows || "Hız:98|Kalite:99|Güç:95")}" placeholder="Etiket:Değer|..."></label>` : "") +
      (G === "chapter" ? `<label class="fld w2"><span>Numara</span><input class="in" data-k="style.num" value="${esc(st.num || "01")}"></label>` : "") +
      (G === "counter" ? `<label class="fld w2"><span>Başla</span><input type="number" class="in" data-k="style.from" value="${st.from ?? 0}"></label><label class="fld w2"><span>Bitir</span><input type="number" class="in" data-k="style.to" value="${st.to ?? 1000}"></label><label class="fld w2"><span>Ön ek</span><input class="in" data-k="style.prefix" value="${esc(st.prefix || "")}"></label><label class="fld w2"><span>Son ek</span><input class="in" data-k="style.suffix" value="${esc(st.suffix || "")}"></label>` : "") +
      (G === "endscreen" ? `<label class="fld w2"><span>Kutu 1</span><input class="in" data-k="style.v1" value="${esc(st.v1 || "Önerilen video")}"></label><label class="fld w2"><span>Kutu 2</span><input class="in" data-k="style.v2" value="${esc(st.v2 || "Son video")}"></label><label class="fld w2"><span>Kanal adı</span><input class="in" data-k="style.channel" value="${esc(st.channel || "")}" placeholder="İsteğe bağlı"></label><div class="row"><button class="tb" data-a2="avatarPick">🖼 Kanal fotosu seç</button>${st.avatarImg ? '<button class="tb" data-a2="avatarClear">✕ Kaldır</button>' : ""}</div>` : "") +
      color("Vurgu rengi", "style.color", st.color || (G === "highlight" ? "#FFE600" : "#8B5CF6")) + fld("Boyut", "style.size", 30, 250, 1, st.size ?? 100) +
      fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .5) + fontIn("style.font", st.font || "Chakra Petch");
    return h;
  }
  if (c.subscribe) {
    h += `<div class="sec">Abone animasyonu</div>` + sel("Tür", "subscribe", ST.cat.subscribe, c.subscribe) +
      `<label class="fld w2"><span>Yazı</span><input class="in" data-k="style.label" value="${esc(st.label || "ABONE OL")}"></label>` +
      `<label class="fld w2"><span>Sonra</span><input class="in" data-k="style.done" value="${esc(st.done || "ABONE OLUNDU")}"></label>` +
      color("Renk", "style.color", st.color || "#ff1f1f") + fld("Boyut", "style.size", 30, 250, 1, st.size ?? 100) +
      fld("X", "style.x", 0, 1, .005, st.x ?? .5) + fld("Y", "style.y", 0, 1, .005, st.y ?? .8) + fontIn("style.font", st.font || (c.subscribe.startsWith("yt") || c.subscribe === "channel" ? "Segoe UI" : "Chakra Petch")) +
      (c.subscribe === "channel" ? `<label class="fld w2"><span>Kanal</span><input class="in" data-k="style.channel" value="${esc(st.channel || "Kanal Adı")}"></label><label class="fld w2"><span>Abone</span><input class="in" data-k="style.subs" value="${esc(st.subs || "1,2 Mn abone")}"></label>` + color("Avatar", "style.avatarColor", st.avatarColor || "#8B5CF6") + `<div class="row"><button class="tb" data-a2="avatarPick">🖼 Kanal fotosu seç</button>${st.avatarImg ? '<button class="tb" data-a2="avatarClear">✕ Kaldır</button>' : ""}</div>` : "") +
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
      `<div class="row tight"><button class="tb" data-a2="kineticPlan" title="Kelimelere kinetik tipografi zamanlaması planla">⚡ Kinetik Planla</button></div>` +
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
  const bm = ST.p.bgMode || "color";
  const pats = [["gradient-violet", "Mor Gradyan"], ["gradient-sunset", "Gün Batımı"], ["gradient-neon", "Neon"], ["aurora", "Aurora"], ["grid", "Izgara"], ["dots", "Noktalı"], ["stripes", "Çizgili"]];
  return `<div class="ph"><b>Proje</b></div>` +
    `<label class="fld w2"><span>Ad</span><input class="in" data-pk="name" value="${esc(ST.p.name)}"></label>` +
    `<label class="fld w2"><span>Genişlik</span><input type="number" class="in" data-pk="w" value="${ST.p.w}"></label>` +
    `<label class="fld w2"><span>Yükseklik</span><input type="number" class="in" data-pk="h" value="${ST.p.h}"></label>` +
    `<label class="fld w2"><span>FPS</span><select class="in" data-pk="fps">${[24, 25, 30, 50, 60].map(f => `<option${f === ST.p.fps ? " selected" : ""}>${f}</option>`).join("")}</select></label>` +
    `<div class="sec">Tuval (Arka plan)</div>` +
    `<label class="fld w2"><span>Mod</span><select class="in" data-pk="bgMode"><option value="color"${bm === "color" ? " selected" : ""}>Renk</option><option value="blur"${bm === "blur" ? " selected" : ""}>Bulanıklık (%)</option><option value="pattern"${bm === "pattern" ? " selected" : ""}>Desen</option></select></label>` +
    (bm === "blur" ? `<label class="fld"><span>Bulanıklık %</span><input type="range" data-pk="bgBlur" min="0" max="100" step="1" value="${ST.p.bgBlur ?? 45}"><input class="num" type="number" data-pk="bgBlur" min="0" max="100" value="${ST.p.bgBlur ?? 45}"></label>` : "") +
    (bm === "pattern" ? `<label class="fld w2"><span>Desen</span><select class="in" data-pk="bgPattern">${pats.map(([k, n]) => `<option value="${k}"${(ST.p.bgPattern || "gradient-violet") === k ? " selected" : ""}>${n}</option>`).join("")}</select></label><label class="fld w2"><span>Ana renk</span><input type="color" data-pk="bg" value="${ST.p.bg || "#140D24"}"></label><label class="fld w2"><span>İkinci renk</span><input type="color" data-pk="bg2" value="${ST.p.bg2 || "#5B21B6"}"></label>` : "") +
    (bm === "color" ? `<label class="fld w2"><span>Arka plan</span><input type="color" data-pk="bg" value="${ST.p.bg || "#000000"}"></label>` : "") +
    `<div class="sec">Özet</div><div class="hint">${ST.p.clips.length} klip · ${Object.keys(ST.p.assets).length} medya · ${fmt(projEnd())}<br>${(ST.p.markers || []).length} işaret ${(ST.p.markers || []).length ? '· <a href="#" data-a2="clearmk" style="color:var(--em)">temizle</a>' : ""}</div>` +
    `<div class="sec">İpucu</div><div class="hint">Klibe tıkla: ayarları burada. Çift tıkla: odaklan.<br>Boşluk oynat · S böl · Q/W solu/sağı sil · Del sil · Ctrl+Z geri · 1-9 hızlı ses.<br>Kami AI (MCP) bağlıysa ona “şu videoyu kes, altyazı ekle” diyebilirsin; değişiklikler burada anında görünür.</div>` +
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
function drawBez(cv, bz) {
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, px = 16, py = 24, uw = W - 2 * px, uh = H - 2 * py;
  const X = u => px + u * uw, Y = v => H - py - v * uh;
  g.clearRect(0, 0, W, H); g.fillStyle = "#07050C"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "rgba(255,255,255,.1)"; g.lineWidth = 1; g.strokeRect(px, H - py - uh, uw, uh);
  g.setLineDash([3, 3]); g.beginPath(); g.moveTo(X(0), Y(0)); g.lineTo(X(1), Y(1)); g.stroke(); g.setLineDash([]);
  const [p1x, p1y, p2x, p2y] = bz;
  g.strokeStyle = "rgba(168,85,247,.5)"; g.beginPath(); g.moveTo(X(0), Y(0)); g.lineTo(X(p1x), Y(p1y)); g.moveTo(X(1), Y(1)); g.lineTo(X(p2x), Y(p2y)); g.stroke();
  g.strokeStyle = "#2EE6A6"; g.lineWidth = 2.2; g.beginPath();
  for (let i = 0; i <= 40; i++) { const u = i / 40, v = SFX.evalBezier ? SFX.evalBezier(p1x, p1y, p2x, p2y, u) : u; i ? g.lineTo(X(u), Y(v)) : g.moveTo(X(u), Y(v)); }
  g.stroke();
  for (const [cx, cy, col] of [[p1x, p1y, "#A855F7"], [p2x, p2y, "#FFB547"]]) { g.fillStyle = col; g.beginPath(); g.arc(X(cx), Y(cy), 5, 0, 7); g.fill(); }
}
function bezCanvas(c) {
  const cv = $("#bezCv"); if (!cv || !c.kf?.length) return;
  const list = c.kf.map(k => ({ k, t: Math.max(0, k.t < 0 ? c.dur + k.t : k.t) })).sort((a, b) => a.t - b.t);
  const ai = ukfActiveIdx(list, clamp(ST.t - c.start, 0, c.dur)); if (ai < 1) return;
  const tgt = list[ai].k;
  const getBz = () => Array.isArray(tgt.bez) && tgt.bez.length === 4 ? [...tgt.bez] : [...(ST.cat.bezierPresets?.[tgt.bez] || [0, 0, 1, 1])];
  drawBez(cv, getBz());
  const W = cv.width, H = cv.height, px = 16, py = 24, uw = W - 2 * px, uh = H - 2 * py;
  const X = u => px + u * uw, Y = v => H - py - v * uh;
  const pos = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
  cv.onpointerdown = e => {
    const [mx, my] = pos(e), bz = getBz();
    const d1 = Math.hypot(X(bz[0]) - mx, Y(bz[1]) - my), d2 = Math.hypot(X(bz[2]) - mx, Y(bz[3]) - my);
    const h = d1 <= d2 && d1 < 16 ? 0 : d2 < 16 ? 1 : -1; if (h < 0) return;
    cv.setPointerCapture(e.pointerId); snap();
    cv.onpointermove = ev => {
      const [x2, y2] = pos(ev);
      const nx = +clamp((x2 - px) / uw, 0, 1).toFixed(2), ny = +clamp((H - py - y2) / uh, -0.35, 1.45).toFixed(2);
      if (h === 0) { bz[0] = nx; bz[1] = ny; } else { bz[2] = nx; bz[3] = ny; }
      tgt.bez = [...bz]; drawBez(cv, bz); draw();
    };
    cv.onpointerup = () => {
      cv.onpointermove = null;
      api.studio_bezier_eval?.(bz[0], bz[1], bz[2], bz[3], .5).then(r => { if (r) toast(`Eğri t=0.5 → ${(+r.value).toFixed(2)}`); }).catch(() => {});
      changed();
    };
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
    else if (k === "mask.type") {
      if (!v || v === "none") delete c.mask;
      else c.mask = { x: .5, y: .5, w: .55, h: .55, rot: 0, feather: 4, invert: false, ...(c.mask || {}), type: v };
    } else if (k.startsWith("crop.")) {
      if (typeof c.crop !== "object" || !c.crop) c.crop = {};
      setK(c, k, v);
      if (!Object.values(c.crop).some(x => +x > .001)) delete c.crop;
    } else if (k in UKF_DEFS && c.kf?.some(q => k in q)) {
      const lt = +clamp(ST.t - c.start, 0, c.dur).toFixed(3);
      let hit = c.kf.find(q => Math.abs((q.t < 0 ? c.dur + q.t : q.t) - lt) < .06);
      if (!hit) { hit = { t: lt }; c.kf.push(hit); c.kf.sort((a, b) => (a.t < 0 ? c.dur + a.t : a.t) - (b.t < 0 ? c.dur + b.t : b.t)); }
      hit[k] = v;
    } else setK(c, k, v);
  }
  if (k === "shutterAngle" && api.studio_shutter_blur) {
    api.studio_shutter_blur(v, ST.p.fps || 30).then(r => { if (r) toast(`Hareket bulanıklığı: ${r.tmix_frames || 0} kare örnekleme`); }).catch(() => {});
  }
  const textual = k === "text" || k.startsWith("style.") || k === "subscribe" || k === "graphic" || k === "sticker" || k === "mode" || k === "date" || k === "cam";
  if (textual) assDirty();
  if (live) { draw(); if (k === "pan" || k === "vol") syncMedia(ST.t, false); if (k === "speed" || k === "start" || k === "dur" || k === "vol" || k.startsWith("fade")) renderTimeline(); renderHandles(); ST.dirty = true; scheduleSave(); }
  else changed();
}
$("#insp").addEventListener("input", e => {
  const el = e.target, k = el.dataset.k, pk = el.dataset.pk;
  if (pk) {
    if (pk === "bgBlur") { ST.p.bgBlur = clamp(+el.value, 0, 100); draw(); ST.dirty = true; scheduleSave(); }
    return;
  }
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
  if (pk) { snap(); ST.p[pk] = el.type === "number" || pk === "fps" || pk === "bgBlur" ? Math.max(pk === "bgBlur" ? 0 : 16, Math.round(+el.value)) : el.value; if (pk === "bgMode" && el.value === "pattern" && !ST.p.bgPattern) ST.p.bgPattern = "gradient-violet"; if (pk === "name") $("#pname").value = el.value; if (pk === "w" || pk === "h") afterLoad(true); else { changed(); if (pk === "bgMode") renderInsp(); } return; }
  if (!k) return;
  const v = el.type === "checkbox" ? el.checked : el.type === "range" || el.type === "number" ? +el.value : el.value;
  if (el.tagName === "SELECT" || el.type === "checkbox" || el.type === "color") { inspSet(k, v, false); return; }
  inspSnap = false; changed();
});
$("#insp").addEventListener("click", async e => {
  const pick = e.target.closest("[data-ukfpick]");
  const b = e.target.closest("button, a[data-a2]");
  const c = selClips()[0];
  if (pick && !b && c?.kf?.length) {
    const idx = +pick.dataset.ukfpick, kf = ukfResolve(c);
    if (kf[idx]) { ST.bezIdx = idx; seek(c.start + kf[idx].t); renderInsp(); }
    return;
  }
  if (!b) return;
  e.preventDefault();
  if (b.closest("[data-seg]")) { inspSet(b.closest("[data-seg]").dataset.seg, b.dataset.v, false); return; }
  if (b.dataset.speed) { inspSet("speed", +b.dataset.speed, false); return; }
  if (b.dataset.ramp) { snap(); rampApply(c, RAMPS[b.dataset.ramp].p && clone(RAMPS[b.dataset.ramp].p)); changed(); return; }
  if (b.dataset.afx) { snap(); const s2 = new Set(c.afx || []); s2.has(b.dataset.afx) ? s2.delete(b.dataset.afx) : s2.add(b.dataset.afx); c.afx = [...s2]; if (!c.afx.length) delete c.afx; changed(false); renderInsp(); return; }
  if (b.dataset.unfx) { snap(); c.fx = c.fx.filter(x => x !== b.dataset.unfx); if (!c.fx.length) delete c.fx; changed(); return; }
  if (b.dataset.kfdel != null) { snap(); const kf = kfResolve(c.zoom, c.dur); kf.splice(+b.dataset.kfdel, 1); c.zoom = kf.length ? kf : undefined; if (!c.zoom) delete c.zoom; changed(); return; }
  if (b.dataset.ukf && c) {
    const prop = b.dataset.ukf, def = UKF_DEFS[prop]?.[1] ?? 1, lt = +clamp(ST.t - c.start, 0, c.dur).toFixed(3);
    snap();
    c.kf ||= [];
    const hitIdx = c.kf.findIndex(k => Math.abs((k.t < 0 ? c.dur + k.t : k.t) - lt) < .06);
    if (hitIdx >= 0 && prop in c.kf[hitIdx]) {
      delete c.kf[hitIdx][prop];
      if (!Object.keys(UKF_DEFS).some(p => p in c.kf[hitIdx])) c.kf.splice(hitIdx, 1);
    } else {
      const curVal = c.kf.length ? kfAt(ukfResolve(c), prop, lt, c[prop] ?? def) : (c[prop] ?? def);
      if (hitIdx >= 0) c.kf[hitIdx][prop] = +(+curVal).toFixed(3);
      else c.kf.push({ t: lt, [prop]: +(+curVal).toFixed(3) });
    }
    c.kf.sort((a, b) => (a.t < 0 ? c.dur + a.t : a.t) - (b.t < 0 ? c.dur + b.t : b.t));
    if (!c.kf.length) delete c.kf;
    else ST.bezIdx = Math.max(1, c.kf.findIndex(k => Math.abs((k.t < 0 ? c.dur + k.t : k.t) - lt) < .06));
    changed(); return;
  }
  if (b.dataset.ukfdel != null && c?.kf) {
    const list = c.kf.map((k, ri) => ({ ri, t: Math.max(0, k.t < 0 ? c.dur + k.t : k.t) })).sort((a, b) => a.t - b.t);
    const hit = list[+b.dataset.ukfdel];
    if (hit) { snap(); c.kf.splice(hit.ri, 1); if (!c.kf.length) delete c.kf; changed(); }
    return;
  }
  if (b.dataset.bez && c?.kf?.length) {
    const list = c.kf.map(k => ({ k, t: Math.max(0, k.t < 0 ? c.dur + k.t : k.t) })).sort((a, b) => a.t - b.t);
    const ai = ukfActiveIdx(list, clamp(ST.t - c.start, 0, c.dur));
    if (ai >= 1) { snap(); list[ai].k.bez = b.dataset.bez; changed(); }
    return;
  }
  if (b.dataset.eqp && c) {
    const pre = ST.cat.eqPresets?.[b.dataset.eqp]?.[1];
    if (pre) { snap(); for (const x of selClips()) x.eq = [...pre]; changed(); syncMedia(ST.t, false); toast("EQ uygulandı: " + (ST.cat.eqPresets[b.dataset.eqp]?.[0] || b.dataset.eqp)); }
    return;
  }
  if (b.dataset.anc && c) {
    const pts = { tl: [.18, .18], tc: [.5, .18], tr: [.82, .18], ml: [.18, .5], center: [.5, .5], mr: [.82, .5], bl: [.18, .82], bc: [.5, .82], br: [.82, .82] };
    const pt = pts[b.dataset.anc]; if (!pt) return;
    snap(); for (const x of selClips()) { x.anchor = b.dataset.anc; x.cx = pt[0]; x.cy = pt[1]; } changed(); toast("Sabitleme noktası: " + b.dataset.anc.toUpperCase());
    return;
  }
  const a2 = b.dataset.a2;
  if (a2 === "copyease" && c) { ST.easeSrcId = c.id; toast("Ease & stil kopyalandı — hedef klibi seçip Ease Yapıştır (Shift+V)"); return; }
  if (a2 === "pasteease") {
    const dst = selClips().map(x => x.id).filter(id => id !== ST.easeSrcId);
    if (!ST.easeSrcId || !dst.length) { toast("Önce kaynak klipten Ease Kopyala (Shift+C), sonra farklı klip seç"); return; }
    const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
    const r = await api.studio_copy_ease(p, ST.easeSrcId, dst, true);
    if (r?.ok && r.project) { snap(); ST.p.clips = r.project.clips; changed(); toast(`${r.applied.length} klibe ease/stil yapıştırıldı`); } else toast(r?.error || "olmadı");
    return;
  }
  if (a2 === "similarsnd" && c) {
    const a = assetOf(c); if (!a?.path) return;
    busy("Benzer sesler taranıyor…");
    const r = await api.studio_sound_similar(a.path, 12); busy(null);
    if (!r?.ok || !r.matches?.length) { toast("Yerel Sesler/Muzik klasöründe benzer ses bulunamadı"); return; }
    modal(`<h3>🔍 Benzer Sesler (${esc(a.name)})</h3>` + r.matches.map(m => `<div class="snd"><b>${esc(m.name)}</b><small>${m.dur}s · %${Math.round(m.score * 100)}</small><button data-simadd="${esc(m.path)}">＋</button></div>`).join("") + `<div class="row"><button class="tb pri" data-v="ok">Kapat</button></div>`, {
      init: m => m.addEventListener("click", ev => { const ad = ev.target.closest("[data-simadd]"); if (ad) importPaths([ad.dataset.simadd]); })
    });
    return;
  }
  if (a2 === "toaudio") { window.setPage?.("audio"); return; }
  if (a2 === "ukfclear" && c) { snap(); delete c.kf; delete ST.bezIdx; changed(); return; }
  if (a2 === "restoreCuts") { const n = restoreCuts([...ST.cutSel]); toast(`${n} kesilen bölge eski haline getirildi`); return; }
  if (a2 === "dropCuts") { dropCuts([...ST.cutSel]); toast("Kesim izi temizlendi"); return; }
  if (a2 === "rot90" && c) { snap(); for (const x of selClips()) x.rot = (((x.rot || 0) + 90 + 180) % 360) - 180; changed(); return; }
  if (a2 === "flipH" && c) { snap(); for (const x of selClips()) x.flipH = !x.flipH; changed(); return; }
  if (a2 === "flipV" && c) { snap(); for (const x of selClips()) x.flipV = !x.flipV; changed(); return; }
  if (a2 === "resetXform" && c) { snap(); for (const x of selClips()) { delete x.rot; delete x.flipH; delete x.flipV; } changed(); return; }
  if (a2 === "hudCrop" && c) { snap(); c.crop = { l: .15, r: .15, t: .12, b: .12 }; c.scale = Math.max(c.scale ?? 1, 1.35); changed(); toast("HUD kenarları kırpılıp yakınlaştırıldı"); return; }
  if (a2 === "resetCrop" && c) { snap(); delete c.crop; delete c.radius; delete c.borderW; delete c.shadow; changed(); return; }
  if (a2 === "jlcut" && c && api.studio_jl_cut) {
    const r = await api.studio_jl_cut(c, c.audioLead || 0, c.audioTail || 0);
    if (r?.ok) { snap(); Object.assign(c, r.clip); changed(); toast("J/L Cut ses penceresi güncellendi"); }
    return;
  }
  if (a2 === "kineticPlan" && c && api.studio_kinetic_text) {
    const r = await api.studio_kinetic_text(c.text || "METİN", c.start, c.dur, "pop");
    if (r?.events?.length) {
      snap(); (c.style ||= {}); c.anim = { ...(c.anim || {}), in: "pop", inDur: .32 };
      changed(); toast(`Kinetik plan: ${r.events.length} vurgu adımı`);
    }
    return;
  }
  if (a2 === "avatarPick" && c) {
    const inp = document.createElement("input"); inp.type = "file"; inp.accept = "image/*";
    inp.onchange = () => {
      const f = inp.files?.[0]; if (!f) return;
      const rd = new FileReader(); rd.onload = () => { snap(); (c.style ||= {}).avatarImg = rd.result; assDirty(); changed(); };
      rd.readAsDataURL(f);
    };
    inp.click(); return;
  }
  if (a2 === "avatarClear" && c) { snap(); if (c.style) delete c.style.avatarImg; assDirty(); changed(); return; }
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
  const hasLoop = ST.loopIn != null && ST.loopOut != null && ST.loopOut > ST.loopIn + .05;
  const opts = await modal(`<h3>Dışa aktar</h3>
    <div class="hint">${ST.p.w}×${ST.p.h} · ${ST.p.fps} fps · ${fmt(projEnd())} · H.264 MP4 (NVENC varsa ekran kartıyla). Her zaman asıl dosyalardan, tam kalitede işlenir.</div>
    <label class="fld w2"><span>Kalite</span><select class="in" id="xq"><option value="high">Yüksek (YouTube)</option><option value="medium">Orta (küçük dosya)</option></select></label>
    <label class="fld w2"><span>Aralık</span><select class="in" id="xr"><option value="all">Tüm video</option>${hasLoop ? `<option value="loop">Döngü I–O (${fmt(ST.loopIn)}–${fmt(ST.loopOut)})</option>` : ""}${range ? `<option value="sel">Seçili klipler (${fmt(range[0])}–${fmt(range[1])})</option>` : ""}<option value="mk">İşaretler arası (ilk–son)</option></select></label>
    <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">Kaydet…</button></div>`,
    { collect: () => ({ quality: $("#xq").value, r: $("#xr").value }) });
  if (!opts) return;
  const o = { quality: opts.quality };
  if (opts.r === "loop" && hasLoop) o.range = [ST.loopIn, ST.loopOut];
  if (opts.r === "sel" && range) o.range = range;
  if (opts.r === "mk" && ST.p.markers?.length > 1) { const ts = ST.p.markers.map(m => m.t).sort((a, b) => a - b); o.range = [ts[0], ts.at(-1)]; }
  const out = await api.studio_pick_save(ST.p.name, ".mp4"); if (!out) return;
  await save();
  const p = rootProjectClone(); for (const a of Object.values(p.assets)) delete a.url;
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
    split: splitAtPlayhead, trimL: () => trimSide("l"), trimR: () => trimSide("r"), del: () => deleteSel(), dup: dupSel, save: () => save(), export: exportVideo,
    link: () => { ST.linkTracks = !ST.linkTracks; $("#linkBtn")?.classList.toggle("on", ST.linkTracks); toast(ST.linkTracks ? "Bağlı izler açık: video ve ses birlikte taşınır" : "Bağlı izler kapalı"); },
    transformMenu: async () => {
      const cs = selClips().filter(x => ["video", "image"].includes(clipKind(x)));
      if (!cs.length) return toast("Önce bir video veya görsel klibi seç");
      const pick = await modal(`<h3>Dönüşüm</h3><div style="display:flex;flex-direction:column;gap:6px;min-width:240px">` +
        `<button class="tb" data-v="rot90">↻ 90° Döndür</button>` +
        `<button class="tb" data-v="flipH">⇄ Ayna (Yatay çevir)</button>` +
        `<button class="tb" data-v="flipV">⇅ Ters çevir (Dikey)</button>` +
        `<button class="tb" data-v="reset">↺ Dönüşümü sıfırla</button></div><div class="row" style="margin-top:8px"><button class="tb" data-v="">Kapat</button></div>`);
      if (!pick) return;
      snap();
      for (const x of cs) {
        if (pick === "rot90") x.rot = (((x.rot || 0) + 90 + 180) % 360) - 180;
        else if (pick === "flipH") x.flipH = !x.flipH;
        else if (pick === "flipV") x.flipV = !x.flipV;
        else if (pick === "reset") { delete x.rot; delete x.flipH; delete x.flipV; }
      }
      changed();
    },
    open: async () => { const p = await api.studio_pick_project(); if (p) openProject(p); },
    new: newProject,
    marker: () => { snap(); (ST.p.markers ||= []).push({ t: +ST.t.toFixed(3), kind: "note" }); changed(); },
    snap: () => { ST.snap = !ST.snap; b.classList.toggle("on", ST.snap); },
    ripple: () => { ST.ripple = !ST.ripple; b.classList.toggle("on", ST.ripple); },
    loopIn: () => { ST.loopIn = +ST.t.toFixed(3); if (ST.loopOut != null && ST.loopOut <= ST.loopIn) ST.loopOut = null; drawRuler(); toast("Döngü girişi (I): " + fmt(ST.loopIn)); },
    loopOut: () => { ST.loopOut = +ST.t.toFixed(3); if (ST.loopIn == null || ST.loopIn >= ST.loopOut) ST.loopIn = 0; ST.loopOn = true; $("#loopBtn")?.classList.add("on"); drawRuler(); toast("Döngü çıkışı (O): " + fmt(ST.loopOut)); },
    loopToggle: () => { ST.loopOn = !ST.loopOn; $("#loopBtn")?.classList.toggle("on", ST.loopOn); drawRuler(); toast(ST.loopOn ? "I–O Döngüsü açık" : "Döngü kapalı"); },
    scrub: () => { ST.scrubAudio = !ST.scrubAudio; $("#scrubBtn")?.classList.toggle("on", ST.scrubAudio); toast(ST.scrubAudio ? "Sesli tarama (Scrub) açık" : "Sesli tarama kapalı"); },
    exitComp: exitCompound,
    smartcut: async () => {
      const id = [...ST.sel][0]; const c = ST.p?.clips.find(x => x.id === id);
      const asset = c && ST.p?.assets?.[c.asset];
      if (!c || !asset?.path) return toast("Önce bir video/ses klibi seç");
      busy("Hızlı kesim (Keyframe Copy)…");
      const r = await api.studio_smart_cut(asset.path, c.in || 0, (c.in || 0) + c.dur * (c.speed || 1), "");
      busy(null);
      toast(r?.ok ? "Kesim kaydedildi: " + r.path.split(/[\\/]/).pop() : (r?.error || "Kesim başarısız"));
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
      const selIds = [...ST.sel].filter(id => { const c = ST.p?.clips.find(x => x.id === id); return c && ["video", "image"].includes(clipKind(c)); });
      const scopeHint = selIds.length ? `🎯 Sadece seçili ${selIds.length} klibe uygulanacak.` : "ℹ Klip seçili değil — tüm video kliplere uygulanacak.";
      const btns = list.map(r => `<button class="tb viral-card" data-v="${esc(r.id)}"><b>${esc(r.name)}</b><small>${esc(r.desc)}</small></button>`).join("");
      const pick = await modal(`<h3>Viral Kurgu Paketleri (${list.length})</h3><div class="hint" style="margin-bottom:8px">${scopeHint}</div><div class="viral-grid">${btns}</div><div class="row" style="margin-top:8px"><button class="tb" data-v="">İptal</button></div>`);
      if (!pick || !ST.p) return;
      snap();
      const res = await api.studio_run_recipe(ST.p, pick, selIds.length ? selIds : null);
      if (res?.ok) { ST.p = res.project; changed(); toast(`Paket uygulandı (${res.applied_clips} klip): ${pick}`); }
      else toast(res?.error || "Paket uygulanamadı");
    },
    autostyle: async () => {
      if (!ST.p?.clips.length) return toast("Önce zaman çizelgesine video ekle");
      const styles = [
        { id: "roblox_lyric_pop", name: "🧱 Roblox 9:16 Dikey", sil: true, beats: true, desc: "1.12x ritim mikro-vuruşları, enerjik oyun zıplaması ve beat işaretleme." },
        { id: "fragmovie_velocity", name: "🎯 CS2 / Valorant Fragmovie", sil: false, beats: true, desc: "Beat vuruş işaretleme, camgöbeği flaş, RSMB savurma ve 2.0x velocity." },
        { id: "neon_void_vfx", name: "✨ Neon Void 3D VFX Edit", sil: false, beats: true, desc: "Derin glow, ayna zemin yansıması, pembe flaş ve hızlı beat işaretleme." },
        { id: "dark_trap_mv", name: "🦇 Dark Trap / 2.39:1 Klip", sil: false, beats: true, desc: "Anamorfik 2.39:1 bar, film yanığı, ember kıvılcım ve beat işaretleri." },
        { id: "tr_shitpost_kick", name: "🔥 TR Shitpost / Kick Derleme", sil: true, beats: false, desc: "Sıkı sessizlik kırpma (0.3s), jump-cut crop, yamuk facecam ve rage titreşimi." },
        { id: "tr_max_loud_intro", name: "📢 Max-Loud TR Monolog (-7 LUFS)", sil: true, beats: false, desc: "0 ölü hava kesimi, 9:16 dikey odak ve yüksek ses/bas meme modu." },
        { id: "tech_commentary", name: "🎙 Tech Yorum & B-Roll (MKBHD)", sil: true, beats: false, desc: "Konuşma netleştirme EQ, yumuşak dolly yaklaşma ve editorial temiz ton." },
        { id: "editorial_essay", name: "📰 Editorial Hareketli (Tasarımcı Dayı)", sil: true, beats: false, desc: "50/50 bölünmüş odak, net ses ve temiz kutulu bilgi anlatımı." },
        { id: "mrbeast_retention", name: "⚡ YouTube Retention / MrBeast", sil: true, beats: false, desc: "Sıkı sessizlik kırpma, hızlı dolly-in zoom ve dinamik geçişler." },
        { id: "podcast_clip", name: "🎙 Podcast / Reels Kesiti", sil: true, beats: false, desc: "Konuşma netleştirme, yumuşak nefes zoom ve temiz kutulu altyazı stili." },
      ];
      const selIds = [...ST.sel].filter(id => { const c = ST.p?.clips.find(x => x.id === id); return c && ["video", "image"].includes(clipKind(c)); });
      const cards = styles.map(s => `<button class="tb viral-card" data-v="${s.id}"><b>${s.name}</b><small>${s.desc}</small></button>`).join("");
      const pick = await modal(`<h3>🤖 Oto-Kurgu (Kanal / Tür Tarzı)</h3><div class="hint" style="margin-bottom:6px">${selIds.length ? `🎯 Seçili ${selIds.length} klip` : "🎬 Tüm video"} seçilen kanal/tür tarzına göre otomatik düzenlenir.</div>` +
        `<div class="row" style="gap:12px;margin-bottom:8px"><label class="chk"><input type="checkbox" id="autoSil" checked> Sessizlikleri otomatik kırp</label><label class="chk"><input type="checkbox" id="autoBeat" checked> Vuruş/beat işaretleri koy</label></div>` +
        `<div class="viral-grid">${cards}</div><div class="row" style="margin-top:8px"><button class="tb" data-v="">İptal</button></div>`);
      if (!pick) return;
      const doSil = $("#autoSil")?.checked ?? true, doBeat = $("#autoBeat")?.checked ?? true;
      snap();
      const targetClips = (selIds.length ? ST.p.clips.filter(x => selIds.includes(x.id)) : ST.p.clips).filter(x => ["video", "image"].includes(clipKind(x)));
      let cutCount = 0, beatCount = 0;
      if (doSil) {
        for (const vc of [...targetClips]) {
          const a = assetOf(vc); if (!a?.path || !a.audio) continue;
          const sp = vc.speed || 1, rng = await job("studio_silences", [a.path, vc.in || 0, vc.dur * sp, -35, 0.35]);
          if (rng?.length) cutCount += removeRanges(vc, rng, 0.08, 0.12);
        }
      }
      if (doBeat) {
        const audioC = ST.p.clips.find(x => x.kind === "audio" && assetOf(x)?.path) || targetClips.find(x => assetOf(x)?.audio && assetOf(x)?.path);
        const a = audioC ? assetOf(audioC) : null;
        if (a?.path) {
          const b = await job("studio_beats", [a.path]);
          const ts = (b?.beats || []).map(t => +(audioC.start + (t - (audioC.in || 0)) / (audioC.speed || 1)).toFixed(3)).filter(t => t >= 0);
          if (ts.length) {
            ST.p.markers = [...(ST.p.markers || []).filter(m => m.kind !== "beat"), ...ts.slice(0, 200).map(t => ({ t, kind: "beat" }))];
            beatCount = Math.min(ts.length, 200);
          }
        }
      }
      const postIds = selIds.length ? [...ST.sel] : null;
      const res = await api.studio_run_recipe(ST.p, pick, postIds);
      if (res?.ok) { ST.p = res.project; changed(); toast(`Oto-Kurgu: ${pick} (${res.applied_clips} klip${cutCount ? `, ${cutCount} sessizlik` : ""}${beatCount ? `, ${beatCount} beat` : ""})`); }
      else toast(res?.error || "Oto-Kurgu uygulanamadı");
    },
    addtrack: async () => { const k = await modal(`<h3>İz ekle</h3><div class="row" style="justify-content:stretch">${[["video", "Video / görsel"], ["audio", "Ses"], ["text", "Metin"], ["fx", "Efekt"]].map(([k, l]) => `<button class="tb" data-v="${k}">${l}</button>`).join("")}</div>`); if (k) { snap(); addTrack(k); changed(); } },
    zin: () => setZoom(ST.px * 1.4), zout: () => setZoom(ST.px / 1.4),
    zfit: () => setZoom((scroller.clientWidth - 40) / Math.max(5, projEnd())),
    snapshot: async () => { busy("Kare kaydediliyor…"); const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url; const r = await api.studio_frame_png(p, ST.t, ""); busy(null); if (r.ok) { toast("Kaydedildi: " + r.path.split(/[\\/]/).pop()); } else toast(r.error || "olmadı"); },
    safe: () => document.body.classList.toggle("safe"),
    full: () => { const w = $("#viewArea"); document.fullscreenElement ? document.exitFullscreen() : w.requestFullscreen(); },
    snapshotOld: () => { const a2 = document.createElement("a"); const cv = document.createElement("canvas"); cv.width = PW; cv.height = PH; const g = cv.getContext("2d"); g.drawImage(view, 0, 0); g.drawImage($("#assView"), 0, 0, PW, PH); a2.href = cv.toDataURL("image/png"); a2.download = `${ST.p.name}-${fmt(ST.t).replace(/[:.]/g, "-")}.png`; a2.click(); },
    keys: () => modal(`<h3>Kısayollar</h3><div class="keys">${[["Boşluk", "Oynat / durdur"], ["S", "Oynatma kafasında böl"], ["Q / W", "Solu / sağı sil"], ["I / O / L", "Döngü girişi / çıkışı / aç-kapat"], ["Del", "Sil (Shift: boşluğu kapat)"], ["Ctrl+Z / Y", "Geri al / yinele"], ["Ctrl+C / V / D", "Kopyala / yapıştır / çoğalt"], ["← →", "1 kare (Shift: 1 sn)"], ["Home / End", "Başa / sona"], ["M", "İşaret koy"], ["+ / −", "Zaman ölçeği (Ctrl+tekerlek)"], ["1-9", "Hızlı ses/meme (Ses panelinde ★ ile ata)"], ["F", "Tam ekran önizleme"], ["Ctrl+S / E / O", "Kaydet / dışa aktar / aç"]].map(([k, v]) => `<kbd>${k}</kbd><span>${v}</span>`).join("")}</div><div class="row"><button class="tb pri" data-v="ok">Tamam</button></div>`),
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
  else if (ctrl && e.shiftKey && k.toLowerCase() === "c") {
    e.preventDefault();
    const p = clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
    api.studio_clipboard_copy(p, ST.t, [...ST.sel]).then(r => toast(r?.ok ? "Kare panoya kopyalandı (Copy Pasta)" : (r?.error || "Kopyalanamadı")));
  }
  else if (!ctrl && e.shiftKey && k.toLowerCase() === "c") { const c = selClips()[0]; if (c) { ST.easeSrcId = c.id; toast("Ease & stil kopyalandı (Shift+V ile yapıştır)"); } }
  else if (!ctrl && e.shiftKey && k.toLowerCase() === "v") { $("#insp [data-a2='pasteease']")?.click(); }
  else if (ctrl && k.toLowerCase() === "c") copySel();
  else if (ctrl && k.toLowerCase() === "v") paste();
  else if (ctrl && k.toLowerCase() === "d") { e.preventDefault(); dupSel(); }
  else if (ctrl && k.toLowerCase() === "l") { e.preventDefault(); $('[data-a="link"]').click(); }
  else if (ctrl && k.toLowerCase() === "a") { e.preventDefault(); ST.sel = new Set(ST.p.clips.map(c => c.id)); renderTimeline(); renderInsp(); }
  else if (k === "Delete" || k === "Backspace") deleteSel(e.shiftKey || ST.ripple);
  else if (k.toLowerCase() === "q" && !ctrl) trimSide("l");
  else if (k.toLowerCase() === "w" && !ctrl) trimSide("r");
  else if (k.toLowerCase() === "s" && !ctrl) splitAtPlayhead();
  else if (k.toLowerCase() === "m") $('[data-a="marker"]').click();
  else if (k.toLowerCase() === "i" && !ctrl) $('[data-a="loopIn"]')?.click();
  else if (k.toLowerCase() === "o" && !ctrl) $('[data-a="loopOut"]')?.click();
  else if (k.toLowerCase() === "l" && !ctrl) $('[data-a="loopToggle"]')?.click();
  else if (k.toLowerCase() === "f") $('[data-a="full"]').click();
  else if (k === "ArrowLeft") {
    e.preventDefault();
    if (e.altKey && ST.sel.size) { snap(); const dt = (e.shiftKey ? 5 : 1) / ST.p.fps; for (const x of selClips()) x.start = Math.max(0, +(x.start - dt).toFixed(4)); changed(); }
    else seek(ST.t - (e.shiftKey ? 1 : 1 / ST.p.fps));
  }
  else if (k === "ArrowRight") {
    e.preventDefault();
    if (e.altKey && ST.sel.size) { snap(); const dt = (e.shiftKey ? 5 : 1) / ST.p.fps; for (const x of selClips()) x.start = +(x.start + dt).toFixed(4); changed(); }
    else seek(ST.t + (e.shiftKey ? 1 : 1 / ST.p.fps));
  }
  else if (k === "Home") seek(0);
  else if (k === "End") seek(projEnd());
  else if (k === "+" || k === "=") setZoom(ST.px * 1.4);
  else if (k === "-") setZoom(ST.px / 1.4);
  else if (k === "Escape") { if (ST.compoundStack?.length) exitCompound(); else { ST.sel.clear(); renderTimeline(); renderInsp(); renderHandles(); } }
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
    if (typeof mcp === "string" && mcp && mcp !== ST.path) { if (ST.dirty) await save(); await openProject(mcp); toast("Kami AI yeni bir proje açtı"); }
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
  selClips, splitClip, removeRanges, kfResolve, fmt, esc, clone, clipKind, assetOf, trackOf, seek, draw, projEnd, openProject, dropAsset, resolveOverlap, renderTimeline, renderInsp, assDirty, layoutView, EQ_BANDS_HZ, syncMedia, clipVol, rootProjectClone });
