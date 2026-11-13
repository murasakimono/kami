// Kami Picture editoru (odak modu): katmanlar, firca/silgi, secim (dikdortgen/kement), tasima, metin efektleri,
// kirpma, egriler/seviyeler/renk ayarlari, filtre onayarlari, sablonlar, .kami proje, sinirsiz geri al.
// Sag tik ya da bosluk tusu: imlecin etrafinda radyal arac carki. Tab: katman seridi.
"use strict";
const ED = {
  on: false, W: 0, H: 0, layers: [], cur: 0, tool: "brush", z: 1, ox: 0, oy: 0, name: "", path: "", projPath: "",
  color: "#C4B5FD", size: 24, hard: 0.7, opacity: 1, sel: null, undo: [], redo: [], dirty: false, textOpt: null,
};
const edL = (tr, en) => (typeof L === "function" ? L(tr, en) : tr);
const TOOLS = [
  { id: "brush", k: "b", tr: "Fırça", ic: '<path d="M14 4l6 6-9 9H5v-6z"/><path d="M12 6l6 6"/>' },
  { id: "erase", k: "e", tr: "Silgi", ic: '<path d="M7 20h10M5 15l8-8 6 6-6 6H9z"/>' },
  { id: "select", k: "m", tr: "Seç", ic: '<path d="M4 4h4M12 4h4M20 4v4M20 12v4M20 20h-4M12 20H8M4 20v-4M4 12V8"/>' },
  { id: "lasso", k: "l", tr: "Kement", ic: '<path d="M12 4c5 0 8 2.5 8 5.5S16 15 12 15s-8-2-8-5.5S7 4 12 4zM7 14l-2 6"/>' },
  { id: "move", k: "v", tr: "Taşı", ic: '<path d="M12 3v18M3 12h18M12 3l-3 3M12 3l3 3M12 21l-3-3M12 21l3-3M3 12l3-3M3 12l3 3M21 12l-3-3M21 12l-3 3"/>' },
  { id: "text", k: "t", tr: "Metin", ic: '<path d="M5 5h14M12 5v14M9 19h6"/>' },
  { id: "crop", k: "c", tr: "Kırp", ic: '<path d="M6 2v16h16M2 6h16v16"/>' },
  { id: "pick", k: "i", tr: "Renk al", ic: '<path d="M14 4l6 6-2 2-6-6zM12 6l-8 8v4h4l8-8"/>' },
  { id: "adjust", k: "a", tr: "Ayarlar", ic: '<path d="M4 6h10M18 6h2M4 12h4M12 12h8M4 18h12M20 18h0"/><circle cx="16" cy="6" r="2"/><circle cx="10" cy="12" r="2"/><circle cx="18" cy="18" r="2"/>' },
];
const BLEND = ["source-over", "multiply", "screen", "overlay", "darken", "lighten", "color-dodge", "color-burn", "hard-light", "soft-light", "difference", "hue", "color", "luminosity"];
const BLEND_TR = ["Normal", "Çarp", "Ekran", "Bindirme", "Koyulaştır", "Açıklaştır", "Renk soldur", "Renk yak", "Sert ışık", "Yumuşak ışık", "Fark", "Ton", "Renk", "Parlaklık"];

// ---------------------------------------------------------------- belge
function edLayer(name, w = ED.W, h = ED.H) {
  const c = document.createElement("canvas"); c.width = w; c.height = h;
  return { id: Math.random().toString(36).slice(2, 9), name, c, x: 0, y: 0, vis: true, op: 1, blend: "source-over", text: null };
}
async function edOpenImage(src, name, path) {
  const img = await new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
  edNew(img.naturalWidth, img.naturalHeight, name, path);
  ED.layers[0].c.getContext("2d").drawImage(img, 0, 0);
  ED.layers[0].name = edL("Arka plan", "Background");
  edFit(); edRender(); edLayersUi(); ED.dirty = false;
}
function edNew(w, h, name, path = "", fill = null) {
  ED.W = w; ED.H = h; ED.name = name || edL("Adsız", "Untitled"); ED.path = path; ED.projPath = "";
  ED.layers = [edLayer(edL("Arka plan", "Background"))]; ED.cur = 0; ED.sel = null; ED.undo = []; ED.redo = [];
  if (fill) { const g = ED.layers[0].c.getContext("2d"); g.fillStyle = fill; g.fillRect(0, 0, w, h); }
  $("#edName").textContent = ED.name; $("#edSize").textContent = `${w}×${h}`;
}
function cl() { return ED.layers[ED.cur]; }

// ---------------------------------------------------------------- gorunum
function edFit() {
  const v = $("#edView"), m = 80;
  ED.z = Math.min((v.clientWidth - m) / ED.W, (v.clientHeight - m * 1.6) / ED.H, 4);
  ED.ox = (v.clientWidth - ED.W * ED.z) / 2; ED.oy = (v.clientHeight - ED.H * ED.z) / 2 + 10;
}
const toDoc = (x, y) => [(x - ED.ox) / ED.z, (y - ED.oy) / ED.z];
let rq = 0;
function edRender() { if (!rq) rq = requestAnimationFrame(edDraw); }
function edDraw() {
  rq = 0;
  const v = $("#edView"), dpr = devicePixelRatio || 1;
  if (v.width !== v.clientWidth * dpr || v.height !== v.clientHeight * dpr) { v.width = v.clientWidth * dpr; v.height = v.clientHeight * dpr; }
  const g = v.getContext("2d");
  g.setTransform(1, 0, 0, 1, 0, 0); g.clearRect(0, 0, v.width, v.height);
  g.setTransform(dpr * ED.z, 0, 0, dpr * ED.z, dpr * ED.ox, dpr * ED.oy);
  // seffaflik damali
  g.fillStyle = edChecker(g); g.fillRect(0, 0, ED.W, ED.H);
  g.imageSmoothingEnabled = ED.z < 2; g.imageSmoothingQuality = "high";
  for (const l of ED.layers) {
    if (!l.vis) continue;
    g.globalAlpha = l.op; g.globalCompositeOperation = l.blend;
    g.drawImage(l === ED.stroke?.layer ? ED.stroke.preview : ED.preview && l === cl() ? ED.preview : l.c, l.x, l.y);
  }
  g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
  if (ED.overlay) { g.globalAlpha = 0.55; g.drawImage(ED.overlay, 0, 0); g.globalAlpha = 1; }
  // belge kenari
  g.lineWidth = 1 / ED.z; g.strokeStyle = "rgba(139,92,246,.5)"; g.strokeRect(0, 0, ED.W, ED.H);
  // secim: yuruyen karincalar
  if (ED.sel?.outline) {
    g.lineWidth = 1.5 / ED.z; g.strokeStyle = "#fff"; g.setLineDash([5 / ED.z, 5 / ED.z]); g.lineDashOffset = -(performance.now() / 60) / ED.z; g.stroke(ED.sel.outline);
    g.strokeStyle = "#000"; g.lineDashOffset += 5 / ED.z; g.stroke(ED.sel.outline); g.setLineDash([]); edRender();
  } else if (ED.sel?.path) {
    g.setLineDash([6 / ED.z, 6 / ED.z]); g.lineDashOffset = -(performance.now() / 60) / ED.z;
    g.strokeStyle = "#fff"; g.stroke(ED.sel.path); g.lineDashOffset += 6 / ED.z; g.strokeStyle = "#000"; g.stroke(ED.sel.path); g.setLineDash([]);
    edRender();
  }
  if (ED.cropR) {
    const r = ED.cropR; g.fillStyle = "rgba(0,0,0,.55)";
    g.fillRect(0, 0, ED.W, r.y); g.fillRect(0, r.y + r.h, ED.W, ED.H - r.y - r.h); g.fillRect(0, r.y, r.x, r.h); g.fillRect(r.x + r.w, r.y, ED.W - r.x - r.w, r.h);
    g.strokeStyle = "#2EE6A6"; g.lineWidth = 2 / ED.z; g.strokeRect(r.x, r.y, r.w, r.h);
    g.lineWidth = 1 / ED.z; g.strokeStyle = "rgba(46,230,166,.4)";
    for (let k = 1; k < 3; k++) { g.beginPath(); g.moveTo(r.x + r.w * k / 3, r.y); g.lineTo(r.x + r.w * k / 3, r.y + r.h); g.moveTo(r.x, r.y + r.h * k / 3); g.lineTo(r.x + r.w, r.y + r.h * k / 3); g.stroke(); }
  }
  // firca imleci
  if (ED.hover && ["brush", "erase", "heal", "clone", "liquify"].includes(ED.tool)) {
    g.beginPath(); g.arc(ED.hover[0], ED.hover[1], ED.size / 2, 0, Math.PI * 2);
    g.lineWidth = 1.5 / ED.z; g.strokeStyle = "rgba(255,255,255,.85)"; g.stroke();
    g.lineWidth = 0.75 / ED.z; g.strokeStyle = "rgba(0,0,0,.8)"; g.stroke();
  }
}
let checkerPat = null;
function edChecker(g) { if (checkerPat) return checkerPat; const c = document.createElement("canvas"); c.width = c.height = 16; const x = c.getContext("2d"); x.fillStyle = "#1a1622"; x.fillRect(0, 0, 16, 16); x.fillStyle = "#26212f"; x.fillRect(0, 0, 8, 8); x.fillRect(8, 8, 8, 8); checkerPat = g.createPattern(c, "repeat"); return checkerPat; }

// ---------------------------------------------------------------- geri al
function edSnap(label, layers = [ED.cur]) {
  const snap = { label, cur: ED.cur, W: ED.W, H: ED.H, items: layers.map((i) => { const l = ED.layers[i]; return { id: l.id, data: l.c.getContext("2d").getImageData(0, 0, l.c.width, l.c.height), x: l.x, y: l.y, w: l.c.width, h: l.c.height }; }) };
  ED.undo.push(snap); if (ED.undo.length > 80) ED.undo.shift(); ED.redo = []; ED.dirty = true;
}
function edSnapAll(label) {   // katman ekleme/silme/kirpma: tum belge
  ED.undo.push({ label, full: edSerialize(true) }); if (ED.undo.length > 40) ED.undo.shift(); ED.redo = []; ED.dirty = true;
}
function edApplySnap(s, into) {
  if (s.full) { into.push({ label: s.label, full: edSerialize(true) }); edDeserialize(s.full); return; }
  into.push({ label: s.label, cur: ED.cur, items: s.items.map((it) => { const l = ED.layers.find((x) => x.id === it.id); return l && { id: l.id, data: l.c.getContext("2d").getImageData(0, 0, l.c.width, l.c.height), x: l.x, y: l.y, w: l.c.width, h: l.c.height }; }).filter(Boolean) });
  for (const it of s.items) {
    const l = ED.layers.find((x) => x.id === it.id); if (!l) continue;
    if (l.c.width !== it.w || l.c.height !== it.h) { l.c.width = it.w; l.c.height = it.h; }
    l.c.getContext("2d").putImageData(it.data, 0, 0); l.x = it.x; l.y = it.y;
  }
}
function edUndo() { const s = ED.undo.pop(); if (!s) return; edApplySnap(s, ED.redo); edRender(); edLayersUi(); }
function edRedo() { const s = ED.redo.pop(); if (!s) return; edApplySnap(s, ED.undo); edRender(); edLayersUi(); }

// ---------------------------------------------------------------- secim
function edSelRect(x, y, w, h) { const p = new Path2D(); p.rect(x, y, w, h); ED.sel = { path: p, box: [x, y, w, h] }; }
function edSelPoly(pts) {
  if (pts.length < 3) { ED.sel = null; return; }
  const p = new Path2D(); p.moveTo(...pts[0]); for (const q of pts.slice(1)) p.lineTo(...q); p.closePath();
  const xs = pts.map((q) => q[0]), ys = pts.map((q) => q[1]);
  ED.sel = { path: p, box: [Math.min(...xs), Math.min(...ys), Math.max(...xs) - Math.min(...xs), Math.max(...ys) - Math.min(...ys)] };
}
function edClip(g, l) { if (ED.sel?.path) { g.translate(-l.x, -l.y); g.clip(ED.sel.path); g.translate(l.x, l.y); } }
function edSelMask() {   // secimin maske tuvali (yapay zeka araclari icin)
  const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H;
  const g = c.getContext("2d"); g.fillStyle = "#000"; g.fillRect(0, 0, ED.W, ED.H);
  if (ED.sel?.path) { g.fillStyle = "#fff"; g.fill(ED.sel.path); }
  return c;
}

// ---------------------------------------------------------------- firca
function edStrokeStart(x, y) {
  const l = cl(); if (!l.vis) { toast(edL("Katman gizli", "Layer hidden")); return; }
  edSnap(ED.tool === "erase" ? edL("Sil", "Erase") : edL("Fırça", "Brush"));
  const tmp = document.createElement("canvas"); tmp.width = l.c.width; tmp.height = l.c.height;
  const pv = document.createElement("canvas"); pv.width = l.c.width; pv.height = l.c.height;
  ED.stroke = { layer: l, tmp, preview: pv, last: [x - l.x, y - l.y], erase: ED.tool === "erase" };
  edDab(x - l.x, y - l.y); edStrokeCompose();
}
function edDab(x, y) {
  const g = ED.stroke.tmp.getContext("2d"), r = ED.size / 2;
  const grd = g.createRadialGradient(x, y, r * ED.hard * 0.98, x, y, r);
  grd.addColorStop(0, ED.color); grd.addColorStop(1, ED.color + "00");
  g.save(); edClip(g, ED.stroke.layer); g.fillStyle = ED.hard >= 0.99 ? ED.color : grd; g.beginPath(); g.arc(x, y, r, 0, Math.PI * 2); g.fill(); g.restore();
}
function edStrokeMove(x, y) {
  const s = ED.stroke, l = s.layer; x -= l.x; y -= l.y;
  const [lx, ly] = s.last, d = Math.hypot(x - lx, y - ly), step = Math.max(1, ED.size * 0.12);
  for (let t = step; t <= d; t += step) edDab(lx + (x - lx) * t / d, ly + (y - ly) * t / d);
  if (d >= step) s.last = [x, y];
  edStrokeCompose();
}
function edStrokeCompose() {
  const s = ED.stroke, g = s.preview.getContext("2d");
  g.clearRect(0, 0, s.preview.width, s.preview.height); g.globalCompositeOperation = "source-over"; g.globalAlpha = 1;
  g.drawImage(s.layer.c, 0, 0);
  g.globalAlpha = ED.opacity; g.globalCompositeOperation = s.erase ? "destination-out" : "source-over";
  g.drawImage(s.tmp, 0, 0); g.globalAlpha = 1; g.globalCompositeOperation = "source-over";
  edRender();
}
function edStrokeEnd() {
  const s = ED.stroke; if (!s) return;
  const g = s.layer.c.getContext("2d"); g.clearRect(0, 0, s.layer.c.width, s.layer.c.height); g.drawImage(s.preview, 0, 0);
  ED.stroke = null; edRender(); edLayerThumb(ED.cur);
}

// ---------------------------------------------------------------- isaretci
let edDrag = null;
function edDown(e) {
  if (e.button === 2) return;
  const v = $("#edView"); v.setPointerCapture(e.pointerId);
  const [x, y] = toDoc(e.offsetX, e.offsetY);
  if (e.button === 1 || ED.space || ED.tool === "move" && e.altKey) { edDrag = { pan: true, sx: e.clientX - ED.ox, sy: e.clientY - ED.oy }; $("#ed").classList.add("pan"); return; }
  const t = ED.tool;
  if (t === "brush" || t === "erase") { edStrokeStart(x, y); edDrag = { t }; }
  else if (t === "select" || t === "crop") edDrag = { t, x0: x, y0: y };
  else if (t === "lasso") edDrag = { t, pts: [[x, y]] };
  else if (t === "move") { edSnap(edL("Taşı", "Move")); const l = cl(); edDrag = { t, sx: x - l.x, sy: y - l.y }; }
  else if (t === "text") edTextAt(x, y);
  else if (t === "pick") edPick(x, y);
}
function edMove(e) {
  const [x, y] = toDoc(e.offsetX, e.offsetY);
  ED.hover = [x, y];
  if (!edDrag) { if (["brush", "erase", "heal", "clone", "liquify"].includes(ED.tool)) edRender(); return; }
  if (edDrag.pan) { ED.ox = e.clientX - edDrag.sx; ED.oy = e.clientY - edDrag.sy; edRender(); return; }
  if (edDrag.t === "brush" || edDrag.t === "erase") edStrokeMove(x, y);
  else if (edDrag.t === "select" || edDrag.t === "crop") {
    let w = x - edDrag.x0, h = y - edDrag.y0;
    if (e.shiftKey || ED.cropRatio) { const k = edDrag.t === "crop" && ED.cropRatio ? ED.cropRatio : 1; h = Math.sign(h || 1) * Math.abs(w) / k; }
    const r = { x: Math.min(edDrag.x0, edDrag.x0 + w), y: Math.min(edDrag.y0, edDrag.y0 + h), w: Math.abs(w), h: Math.abs(h) };
    if (edDrag.t === "select") edSelRect(r.x, r.y, r.w, r.h); else ED.cropR = r;
    edRender();
  } else if (edDrag.t === "lasso") { edDrag.pts.push([x, y]); edSelPoly(edDrag.pts); edRender(); }
  else if (edDrag.t === "move") { const l = cl(); l.x = Math.round(x - edDrag.sx); l.y = Math.round(y - edDrag.sy); edRender(); }
}
function edUp() {
  if (!edDrag) return;
  if (edDrag.t === "brush" || edDrag.t === "erase") edStrokeEnd();
  if (edDrag.t === "select" && ED.sel && ED.sel.box[2] < 2) ED.sel = null;
  if (edDrag.t === "crop" && ED.cropR?.w > 4) edOpt();
  edDrag = null; $("#ed").classList.remove("pan"); edRender();
}
function edPick(x, y) {
  const v = $("#edView"), dpr = devicePixelRatio || 1;
  const d = v.getContext("2d").getImageData((x * ED.z + ED.ox) * dpr, (y * ED.z + ED.oy) * dpr, 1, 1).data;
  ED.color = "#" + [d[0], d[1], d[2]].map((n) => n.toString(16).padStart(2, "0")).join("");
  ED.tool = "brush"; edOpt(); toast(edL("Renk alındı ", "Picked ") + ED.color);
}

// ---------------------------------------------------------------- metin (efektli)
function edTextDefaults() {
  return ED.textOpt ||= { font: "Chakra Petch", size: 72, weight: 700, color: "#FFFFFF", color2: "#C4B5FD", grad: false, stroke: 0, strokeColor: "#000000",
    shadow: 0, glow: 0, glowColor: "#8B5CF6", depth: 0, align: "left", meme: false };
}
function edTextRender(l) {
  const t = l.text, o = t.o, g = l.c.getContext("2d");
  const lines = t.str.split("\n"), lh = o.size * 1.15;
  g.font = `${o.weight} ${o.size}px "${o.font}"`;
  const w = Math.ceil(Math.max(10, ...lines.map((s) => g.measureText(s).width))) + o.stroke * 2 + o.glow * 2 + o.depth + o.shadow * 2 + 8;
  const h = Math.ceil(lines.length * lh + o.stroke * 2 + o.glow * 2 + o.depth + o.shadow * 2 + 8);
  l.c.width = w; l.c.height = h;
  g.font = `${o.weight} ${o.size}px "${o.font}"`; g.textBaseline = "top"; g.lineJoin = "round";
  const pad = 4 + o.stroke + o.glow + o.shadow;
  const xFor = (s) => o.align === "center" ? (w - g.measureText(s).width) / 2 : o.align === "right" ? w - pad - g.measureText(s).width - o.depth : pad;
  const fill = () => { if (!o.grad) return o.color; const gr = g.createLinearGradient(0, pad, 0, pad + lines.length * lh); gr.addColorStop(0, o.color); gr.addColorStop(1, o.color2); return gr; };
  lines.forEach((s, i) => {
    const x = xFor(s), y = pad + i * lh;
    for (let d = o.depth; d > 0; d--) { g.fillStyle = shade(o.color2, -0.45); g.fillText(s, x + d, y + d); }   // 3B derinlik
    if (o.shadow) { g.save(); g.shadowColor = "rgba(0,0,0,.75)"; g.shadowBlur = o.shadow; g.shadowOffsetX = g.shadowOffsetY = o.shadow / 2; g.fillStyle = "#000"; g.fillText(s, x, y); g.restore(); }
    if (o.glow) { g.save(); g.shadowColor = o.glowColor; g.shadowBlur = o.glow; for (let k = 0; k < 3; k++) { g.fillStyle = o.glowColor; g.fillText(s, x, y); } g.restore(); }
    if (o.stroke) { g.lineWidth = o.stroke * 2; g.strokeStyle = o.strokeColor; g.strokeText(s, x, y); }
    g.fillStyle = fill(); g.fillText(s, x, y);
  });
}
function shade(hex, k) { const n = parseInt(hex.slice(1), 16); const f = (v) => Math.max(0, Math.min(255, Math.round(v + (k < 0 ? v * k : (255 - v) * k)))); return `rgb(${f(n >> 16)},${f((n >> 8) & 255)},${f(n & 255)})`; }
function edTextAt(x, y, layer) {
  const l = layer || (cl().text ? cl() : null);
  const hit = !layer && ED.layers.findIndex((q) => q.text && x >= q.x && y >= q.y && x <= q.x + q.c.width && y <= q.y + q.c.height);
  const target = layer || (hit >= 0 ? ED.layers[hit] : null);
  if (target) { ED.cur = ED.layers.indexOf(target); edEditText(target); return; }
  edSnapAll(edL("Metin", "Text"));
  const nl = edLayer(edL("Metin", "Text"), 10, 10); nl.x = Math.round(x); nl.y = Math.round(y);
  nl.text = { str: "", o: { ...edTextDefaults() } };
  ED.layers.splice(ED.cur + 1, 0, nl); ED.cur++;
  edEditText(nl, true);
}
function edEditText(l, fresh) {
  ED.tool = "text"; edOpt();
  const old = $("#ed .ed-textbox"); if (old) old.blur();
  const ta = document.createElement("textarea"); ta.className = "ed-textbox"; ta.value = l.text.str;
  const place = () => { ta.style.left = ED.ox + l.x * ED.z + "px"; ta.style.top = ED.oy + l.y * ED.z + "px"; ta.style.font = `${l.text.o.weight} ${l.text.o.size * ED.z}px "${l.text.o.font}"`; ta.style.width = Math.max(60, l.c.width * ED.z) + "px"; ta.style.height = Math.max(30, l.c.height * ED.z) + "px"; };
  ta.oninput = () => { l.text.str = ta.value; l.name = ta.value.split("\n")[0].slice(0, 24) || edL("Metin", "Text"); edTextRender(l); place(); edRender(); };
  ta.onblur = () => { if (ta._gone) return; ta._gone = true; setTimeout(() => ta.isConnected && ta.remove(), 0); if (!l.text.str.trim() && fresh) { ED.layers.splice(ED.layers.indexOf(l), 1); ED.cur = Math.max(0, ED.cur - 1); } edLayersUi(); edRender(); };
  ta.onkeydown = (e) => { if (e.key === "Escape") ta.blur(); e.stopPropagation(); };
  $("#ed").appendChild(ta); edTextRender(l); place(); setTimeout(() => ta.focus(), 0);
  ED.editing = l; edLayersUi();
}
function edTextOpt(k, v) {
  const l = ED.editing && ED.layers.includes(ED.editing) ? ED.editing : cl().text ? cl() : null;
  const o = l ? l.text.o : edTextDefaults();
  o[k] = v; if (!l) return;
  edTextRender(l); edRender(); edLayerThumb(ED.layers.indexOf(l));
  const ta = $("#ed .ed-textbox"); if (ta) { ta.style.font = `${o.weight} ${o.size * ED.z}px "${o.font}"`; ta.style.width = l.c.width * ED.z + "px"; ta.style.height = l.c.height * ED.z + "px"; }
}
function edMeme() {   // ust/alt meme yazisi: Impact, beyaz, kalin siyah kontur
  edSnapAll("Meme");
  for (const [txt, pos] of [[edL("ÜST YAZI", "TOP TEXT"), "top"], [edL("ALT YAZI", "BOTTOM TEXT"), "bottom"]]) {
    const nl = edLayer("Meme " + (pos === "top" ? "↑" : "↓"), 10, 10);
    nl.text = { str: txt, o: { ...edTextDefaults(), font: "Impact", weight: 400, size: Math.round(ED.W / 10), color: "#FFFFFF", grad: false, stroke: Math.max(3, Math.round(ED.W / 220)), strokeColor: "#000000", glow: 0, depth: 0, shadow: 0, align: "center" } };
    edTextRender(nl); nl.x = Math.round((ED.W - nl.c.width) / 2); nl.y = pos === "top" ? Math.round(ED.H * 0.03) : Math.round(ED.H * 0.97 - nl.c.height);
    ED.layers.push(nl);
  }
  ED.cur = ED.layers.length - 1; edLayersUi(); edRender(); toast(edL("Yazıya çift tıklayıp değiştir", "Double-click text to edit"));
}

// ---------------------------------------------------------------- kirpma
function edCropApply() {
  const r = ED.cropR; if (!r || r.w < 2) return;
  edSnapAll(edL("Kırp", "Crop"));
  const x = Math.round(r.x), y = Math.round(r.y), w = Math.round(r.w), h = Math.round(r.h);
  for (const l of ED.layers) { l.x -= x; l.y -= y; if (!l.text) { const c = document.createElement("canvas"); c.width = w; c.height = h; c.getContext("2d").drawImage(l.c, l.x, l.y); l.c = c; l.x = 0; l.y = 0; } }
  ED.W = w; ED.H = h; ED.cropR = null; ED.sel = null; $("#edSize").textContent = `${w}×${h}`;
  edFit(); edRender(); edLayersUi(); edOpt();
}

// ---------------------------------------------------------------- ayarlar: egriler, seviyeler, renk, filtreler
const ADJ = { bright: 0, contrast: 0, sat: 0, hue: 0, temp: 0, vib: 0, expo: 0, blur: 0, sharp: 0, grain: 0, vign: 0, lvIn0: 0, lvIn1: 255, lvGamma: 1 };
const CURVE = { rgb: [[0, 0], [255, 255]], r: [[0, 0], [255, 255]], g: [[0, 0], [255, 255]], b: [[0, 0], [255, 255]], ch: "rgb" };
function curveLut(pts) {   // monoton kubik interpolasyon -> 256 degerlik tablo
  const p = [...pts].sort((a, b) => a[0] - b[0]), n = p.length, lut = new Uint8ClampedArray(256);
  const dx = [], m = [], s = [];
  for (let i = 0; i < n - 1; i++) { dx[i] = p[i + 1][0] - p[i][0] || 1; s[i] = (p[i + 1][1] - p[i][1]) / dx[i]; }
  m[0] = s[0]; m[n - 1] = s[n - 2];
  for (let i = 1; i < n - 1; i++) m[i] = s[i - 1] * s[i] <= 0 ? 0 : (s[i - 1] + s[i]) / 2;
  for (let x = 0; x < 256; x++) {
    let i = 0; while (i < n - 2 && x > p[i + 1][0]) i++;
    if (x <= p[0][0]) { lut[x] = p[0][1]; continue; } if (x >= p[n - 1][0]) { lut[x] = p[n - 1][1]; continue; }
    const h = dx[i], t = (x - p[i][0]) / h, t2 = t * t, t3 = t2 * t;
    lut[x] = (2 * t3 - 3 * t2 + 1) * p[i][1] + (t3 - 2 * t2 + t) * h * m[i] + (-2 * t3 + 3 * t2) * p[i + 1][1] + (t3 - t2) * h * m[i + 1];
  }
  return lut;
}
function edAdjustData(src, a = ADJ, cv = CURVE) {
  const d = new ImageData(new Uint8ClampedArray(src.data), src.width, src.height), px = d.data;
  const lr = curveLut(cv.r), lg = curveLut(cv.g), lb = curveLut(cv.b), la = curveLut(cv.rgb);
  const c = (a.contrast / 100 + 1) ** 2, br = a.bright * 2.55, ex = 2 ** (a.expo / 50);
  const sat = 1 + a.sat / 100, vib = a.vib / 100, tmp = a.temp * 0.6;
  const hr = (a.hue * Math.PI) / 180, cosH = Math.cos(hr), sinH = Math.sin(hr);
  const lv = new Uint8ClampedArray(256);
  for (let i = 0; i < 256; i++) lv[i] = 255 * Math.pow(Math.min(1, Math.max(0, (i - a.lvIn0) / Math.max(1, a.lvIn1 - a.lvIn0))), 1 / a.lvGamma);
  const W = src.width, H = src.height, cx = W / 2, cy = H / 2, md = Math.hypot(cx, cy);
  for (let i = 0; i < px.length; i += 4) {
    let r = px[i], g = px[i + 1], b = px[i + 2];
    r = lv[r]; g = lv[g]; b = lv[b];
    r *= ex; g *= ex; b *= ex;
    r = (r - 128) * c + 128 + br; g = (g - 128) * c + 128 + br; b = (b - 128) * c + 128 + br;
    r += tmp; b -= tmp;
    if (a.hue) { const y = 0.299 * r + 0.587 * g + 0.114 * b, u = r - y, w = b - y; const u2 = u * cosH - w * sinH, w2 = u * sinH + w * cosH; r = y + u2; b = y + w2; g = (y - 0.299 * r - 0.114 * b) / 0.587; }
    const y = 0.299 * r + 0.587 * g + 0.114 * b;
    const mx = Math.max(r, g, b), mn = Math.min(r, g, b), cur = mx ? (mx - mn) / mx : 0;
    const k = sat + vib * (1 - cur);
    r = y + (r - y) * k; g = y + (g - y) * k; b = y + (b - y) * k;
    if (a.vign) { const p = (i / 4), xx = p % W, yy = (p / W) | 0, dd = Math.hypot(xx - cx, yy - cy) / md, f = 1 - (a.vign / 100) * dd * dd; r *= f; g *= f; b *= f; }
    if (a.grain) { const n = (Math.random() - 0.5) * a.grain * 1.2; r += n; g += n; b += n; }
    px[i] = la[lr[Math.max(0, Math.min(255, r | 0))]]; px[i + 1] = la[lg[Math.max(0, Math.min(255, g | 0))]]; px[i + 2] = la[lb[Math.max(0, Math.min(255, b | 0))]];
  }
  return d;
}
function edConvolve(d, kernel) {
  const W = d.width, H = d.height, s = d.data, o = new Uint8ClampedArray(s), k = kernel, kw = 3;
  for (let y = 1; y < H - 1; y++) for (let x = 1; x < W - 1; x++) {
    for (let ch = 0; ch < 3; ch++) {
      let v = 0; for (let j = 0; j < 3; j++) for (let i = 0; i < 3; i++) v += s[((y + j - 1) * W + (x + i - 1)) * 4 + ch] * k[j * kw + i];
      o[(y * W + x) * 4 + ch] = v;
    }
  }
  return new ImageData(o, W, H);
}
function edAdjPreview() {   // hizli onizleme: kucultulmus kopya uzerinde
  const l = cl(); if (l.text) return;
  const sc = Math.min(1, 900 / Math.max(l.c.width, l.c.height));
  const w = Math.max(1, Math.round(l.c.width * sc)), h = Math.max(1, Math.round(l.c.height * sc));
  if (!ED.adjSrc || ED.adjSrc.lid !== l.id) {
    const c = document.createElement("canvas"); c.width = w; c.height = h; c.getContext("2d").drawImage(l.c, 0, 0, w, h);
    ED.adjSrc = { lid: l.id, data: c.getContext("2d").getImageData(0, 0, w, h) };
  }
  let d = edAdjustData(ED.adjSrc.data);
  const pv = document.createElement("canvas"); pv.width = w; pv.height = h; pv.getContext("2d").putImageData(d, 0, 0);
  const big = document.createElement("canvas"); big.width = l.c.width; big.height = l.c.height;
  const g = big.getContext("2d");
  if (ADJ.blur) g.filter = `blur(${ADJ.blur * sc}px)`;
  g.drawImage(pv, 0, 0, l.c.width, l.c.height); g.filter = "none";
  if (ED.sel?.path) { const m = document.createElement("canvas"); m.width = l.c.width; m.height = l.c.height; const mg = m.getContext("2d"); mg.drawImage(l.c, 0, 0); mg.save(); mg.translate(-l.x, -l.y); mg.clip(ED.sel.path); mg.translate(l.x, l.y); mg.clearRect(0, 0, m.width, m.height); mg.drawImage(big, 0, 0); mg.restore(); ED.preview = m; }
  else ED.preview = big;
  ED.previewHide = true; edRender();
}
function edAdjApply() {
  const l = cl(); if (l.text) { toast(edL("Metin katmanında ayar yok", "No adjustments on text")); return; }
  edSnap(edL("Ayarlar", "Adjust"));
  const g = l.c.getContext("2d");
  let d = edAdjustData(g.getImageData(0, 0, l.c.width, l.c.height));
  if (ADJ.sharp) { const a = ADJ.sharp / 50; d = edConvolve(d, [0, -a, 0, -a, 1 + 4 * a, -a, 0, -a, 0]); }
  const tmp = document.createElement("canvas"); tmp.width = l.c.width; tmp.height = l.c.height; const tg = tmp.getContext("2d");
  tg.putImageData(d, 0, 0);
  if (ADJ.blur) { const b = document.createElement("canvas"); b.width = tmp.width; b.height = tmp.height; const bg = b.getContext("2d"); bg.filter = `blur(${ADJ.blur}px)`; bg.drawImage(tmp, 0, 0); tg.clearRect(0, 0, tmp.width, tmp.height); tg.drawImage(b, 0, 0); }
  g.save(); edClip(g, l); g.clearRect(0, 0, l.c.width, l.c.height); g.drawImage(tmp, 0, 0); g.restore();
  edAdjReset(false); ED.preview = null; ED.adjSrc = null; edRender(); edLayerThumb(ED.cur); toast(edL("Uygulandı", "Applied"));
}
function edAdjReset(redraw = true) {
  Object.assign(ADJ, { bright: 0, contrast: 0, sat: 0, hue: 0, temp: 0, vib: 0, expo: 0, blur: 0, sharp: 0, grain: 0, vign: 0, lvIn0: 0, lvIn1: 255, lvGamma: 1 });
  for (const k of ["rgb", "r", "g", "b"]) CURVE[k] = [[0, 0], [255, 255]];
  if (redraw) { ED.preview = null; edCard("adjust"); edRender(); }
}
const PRESETS = [   // filtre onayarlari (egriler + renk)
  { n: "Sinematik", a: { contrast: 18, sat: -10, temp: -8, vign: 35 }, c: { b: [[0, 30], [128, 128], [255, 220]], r: [[0, 0], [128, 136], [255, 255]] } },
  { n: "Sıcak film", a: { temp: 22, contrast: 10, grain: 18, vign: 25 }, c: { rgb: [[0, 22], [128, 132], [255, 240]] } },
  { n: "Soğuk mavi", a: { temp: -26, sat: -8, contrast: 8 } },
  { n: "Siyah-beyaz", a: { sat: -100, contrast: 25 }, c: { rgb: [[0, 10], [70, 55], [190, 205], [255, 250]] } },
  { n: "Solgun", a: { sat: -35, contrast: -10 }, c: { rgb: [[0, 40], [128, 135], [255, 235]] } },
  { n: "Canlı", a: { vib: 45, contrast: 12 } },
  { n: "Mor gece", a: { hue: -12, sat: 10, contrast: 15 }, c: { r: [[0, 20], [255, 255]], b: [[0, 40], [255, 255]], g: [[0, 0], [255, 215]] } },
  { n: "Retro", a: { sat: -20, grain: 25, vign: 30 }, c: { r: [[0, 30], [255, 250]], g: [[0, 15], [255, 240]], b: [[0, 50], [255, 200]] } },
  { n: "Dram", a: { contrast: 40, sat: -25, vign: 50, expo: -6 } },
];
function edPresetApply(p) {
  edAdjReset(false); Object.assign(ADJ, p.a || {});
  for (const k of ["rgb", "r", "g", "b"]) if (p.c?.[k]) CURVE[k] = p.c[k].map((q) => [...q]);
  edCard("adjust"); edAdjPreview();
}

// ---------------------------------------------------------------- katman islemleri
function edLayerAdd(name, from) {
  edSnapAll(edL("Katman ekle", "Add layer"));
  const nl = edLayer(name || edL("Katman", "Layer") + " " + (ED.layers.length + 1));
  if (from) nl.c.getContext("2d").drawImage(from, 0, 0);
  ED.layers.splice(ED.cur + 1, 0, nl); ED.cur++; edLayersUi(); edRender();
}
function edLayerDup() { const l = cl(); edLayerAdd(l.name + " " + edL("kopya", "copy")); const n = cl(); n.c.width = l.c.width; n.c.height = l.c.height; n.c.getContext("2d").drawImage(l.c, 0, 0); n.x = l.x; n.y = l.y; n.text = l.text && JSON.parse(JSON.stringify(l.text)); n.op = l.op; n.blend = l.blend; edLayersUi(); edRender(); }
function edLayerDel() { if (ED.layers.length < 2) return; edSnapAll(edL("Katman sil", "Delete layer")); ED.layers.splice(ED.cur, 1); ED.cur = Math.max(0, ED.cur - 1); edLayersUi(); edRender(); }
function edLayerMergeDown() {
  if (ED.cur < 1) return; edSnapAll(edL("Birleştir", "Merge"));
  const top = cl(), bot = ED.layers[ED.cur - 1];
  const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H; const g = c.getContext("2d");
  g.globalAlpha = bot.op; g.drawImage(bot.c, bot.x, bot.y); g.globalAlpha = top.op; g.globalCompositeOperation = top.blend; g.drawImage(top.c, top.x, top.y);
  bot.c = c; bot.x = bot.y = 0; bot.op = 1; bot.text = null;
  ED.layers.splice(ED.cur, 1); ED.cur--; edLayersUi(); edRender();
}
function edSelToLayer(cut) {
  if (!ED.sel) return; const l = cl();
  edSnapAll(cut ? edL("Kes", "Cut") : edL("Seçimden katman", "Layer from selection"));
  const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H; const g = c.getContext("2d");
  g.save(); g.clip(ED.sel.path); g.drawImage(l.c, l.x, l.y); g.restore();
  if (cut) { const lg = l.c.getContext("2d"); lg.save(); edClip(lg, l); lg.clearRect(0, 0, l.c.width, l.c.height); lg.restore(); }
  const nl = edLayer(edL("Seçim", "Selection")); nl.c = c; ED.layers.splice(ED.cur + 1, 0, nl); ED.cur++; ED.sel = null; edLayersUi(); edRender();
}
function edClearSel() { if (!ED.sel) return; const l = cl(); edSnap(edL("Temizle", "Clear")); const g = l.c.getContext("2d"); g.save(); edClip(g, l); g.clearRect(0, 0, l.c.width, l.c.height); g.restore(); edRender(); edLayerThumb(ED.cur); }
function edFillSel() { const l = cl(); edSnap(edL("Doldur", "Fill")); const g = l.c.getContext("2d"); g.save(); edClip(g, l); g.fillStyle = ED.color; g.fillRect(0, 0, l.c.width, l.c.height); g.restore(); edRender(); edLayerThumb(ED.cur); }
function edFlipLayer(h) { const l = cl(); edSnap(edL("Çevir", "Flip")); const c = document.createElement("canvas"); c.width = l.c.width; c.height = l.c.height; const g = c.getContext("2d"); g.translate(h ? c.width : 0, h ? 0 : c.height); g.scale(h ? -1 : 1, h ? 1 : -1); g.drawImage(l.c, 0, 0); const lg = l.c.getContext("2d"); lg.clearRect(0, 0, c.width, c.height); lg.drawImage(c, 0, 0); edRender(); edLayerThumb(ED.cur); }
function edFlatten() {
  const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H; const g = c.getContext("2d");
  for (const l of ED.layers) { if (!l.vis) continue; g.globalAlpha = l.op; g.globalCompositeOperation = l.blend; g.drawImage(l.c, l.x, l.y); }
  return c;
}

// ---------------------------------------------------------------- katman seridi
function edLayersUi() {
  const row = $("#edLayers .row"); if (!row) return;
  row.innerHTML = ED.layers.map((l, i) => `<div class="ed-ly${i === ED.cur ? " on" : ""}${l.vis ? "" : " hidden"}" data-i="${i}" draggable="true">
    <canvas width="116" height="72"></canvas><div class="nm" contenteditable="true" spellcheck="false">${esc(l.name)}</div>
    <div class="ctl"><button data-l="vis" title="${edL("Göster/gizle", "Show/hide")}">${l.vis ? "◉" : "○"}</button><input type="range" min="0" max="100" value="${Math.round(l.op * 100)}" data-l="op" title="${edL("Opaklık", "Opacity")}"></div>
    <div class="ctl"><select data-l="blend">${BLEND.map((b, k) => `<option value="${b}" ${b === l.blend ? "selected" : ""}>${BLEND_TR[k]}</option>`).join("")}</select></div></div>`).reverse().join("") +
    `<div class="ed-addly"><button data-l="add">+ ${edL("Katman", "Layer")}</button><button data-l="dup">${edL("Çoğalt", "Duplicate")}</button><button data-l="merge">${edL("Aşağı birleştir", "Merge down")}</button><button data-l="del">${edL("Sil", "Delete")}</button></div>`;
  ED.layers.forEach((_, i) => edLayerThumb(i));
  $("#edLayers .grip span").textContent = `${edL("Katmanlar", "Layers")} · ${ED.layers.length}`;
}
function edLayerThumb(i) {
  const el = document.querySelector(`#edLayers .ed-ly[data-i="${i}"] canvas`); if (!el) return;
  const l = ED.layers[i], g = el.getContext("2d"); g.clearRect(0, 0, 116, 72); g.fillStyle = edChecker(g); g.fillRect(0, 0, 116, 72);
  const k = Math.min(116 / ED.W, 72 / ED.H); g.drawImage(l.c, (116 - ED.W * k) / 2 + l.x * k, (72 - ED.H * k) / 2 + l.y * k, l.c.width * k, l.c.height * k);
}

// ---------------------------------------------------------------- arac secenekleri kapsulu
function edOpt() {
  const t = ED.tool, box = $("#edOpt");
  document.querySelector("#ed").className = "on tool-" + t;
  const T = TOOLS.find((x) => x.id === t);
  let h = `<span class="tl">${edL(T.tr, T.id)}</span>`;
  if (window.edOptExtra && window.edOptExtra(t) != null) h += window.edOptExtra(t);
  else if (t === "brush" || t === "erase") h += `<label>${edL("Boyut", "Size")} <input type="range" min="1" max="400" value="${ED.size}" data-o="size"></label>
    <label>${edL("Sertlik", "Hardness")} <input type="range" min="0" max="100" value="${ED.hard * 100}" data-o="hard"></label>
    <label>${edL("Opaklık", "Opacity")} <input type="range" min="1" max="100" value="${ED.opacity * 100}" data-o="opacity"></label>` + (t === "brush" ? `<input type="color" value="${ED.color}" data-o="color">` : "");
  else if (t === "select" || t === "lasso") h += `<button data-x="selall">${edL("Tümü", "All")}</button><button data-x="selnone">${edL("Kaldır", "None")}</button><button data-x="selinv">${edL("Ters", "Invert")}</button><button data-x="sellayer">${edL("Katmana al", "To layer")}</button><button data-x="selcut">${edL("Kes", "Cut")}</button><button data-x="selfill">${edL("Doldur", "Fill")}</button><button data-x="selclear">${edL("Temizle", "Clear")}</button><input type="color" value="${ED.color}" data-o="color">`;
  else if (t === "move") h += `<button data-x="fliph">⇋ ${edL("Yatay çevir", "Flip H")}</button><button data-x="flipv">⇵ ${edL("Dikey çevir", "Flip V")}</button><button data-x="center">${edL("Ortala", "Center")}</button>`;
  else if (t === "crop") h += `<select data-o="cropRatio"><option value="0">${edL("Serbest", "Free")}</option><option value="1">1:1</option><option value="1.7778">16:9</option><option value="0.5625">9:16</option><option value="0.8">4:5</option><option value="1.3333">4:3</option></select>
    <button class="pri" data-x="cropok" ${ED.cropR ? "" : "disabled"}>${edL("Kırp", "Crop")}</button><button data-x="cropno">${edL("Vazgeç", "Cancel")}</button>`;
  else if (t === "text") { const o = (ED.editing?.text?.o) || edTextDefaults(); h += `<select data-t="font">${["Chakra Petch", "Damnation", "Impact", "Arial Black", "Segoe UI", "Georgia", "Bahnschrift", "Comic Sans MS", "Consolas"].map((f) => `<option ${f === o.font ? "selected" : ""}>${f}</option>`).join("")}</select>
    <input type="number" min="8" max="600" value="${o.size}" data-t="size" style="width:58px"><input type="color" value="${o.color}" data-t="color">
    <label><input type="checkbox" data-t="grad" ${o.grad ? "checked" : ""}>${edL("Gradyan", "Gradient")}</label><input type="color" value="${o.color2}" data-t="color2">
    <label>${edL("Kontur", "Stroke")} <input type="range" min="0" max="30" value="${o.stroke}" data-t="stroke"></label><input type="color" value="${o.strokeColor}" data-t="strokeColor">
    <label>${edL("Neon", "Glow")} <input type="range" min="0" max="60" value="${o.glow}" data-t="glow"></label><input type="color" value="${o.glowColor}" data-t="glowColor">
    <label>${edL("Gölge", "Shadow")} <input type="range" min="0" max="40" value="${o.shadow}" data-t="shadow"></label>
    <label>3B <input type="range" min="0" max="30" value="${o.depth}" data-t="depth"></label>
    <select data-t="align"><option value="left">⟸</option><option value="center" ${o.align === "center" ? "selected" : ""}>≡</option><option value="right" ${o.align === "right" ? "selected" : ""}>⟹</option></select><button data-x="meme">Meme</button>`; }
  else if (t === "pick") h += `<span>${edL("Görselden renk almak için tıkla", "Click the image to pick a colour")}</span>`;
  else if (t === "adjust") h += `<span>${edL("Sağdaki karttan ayarla, Uygula ile kaydet", "Adjust in the card, Apply to commit")}</span>`;
  box.innerHTML = h;
  const cr = box.querySelector('[data-o="cropRatio"]'); if (cr) cr.value = String(ED.cropRatio || 0);
  if (t === "adjust" && cl().text) { const i = ED.layers.map((q, k) => [q, k]).filter(([q, k]) => !q.text && k <= ED.cur).pop(); if (i) { ED.cur = i[1]; edLayersUi(); } }
  $("#edCard").hidden = t !== "adjust"; if (t === "adjust") edCard("adjust"); else if (ED.preview) { ED.preview = null; edRender(); }
}
function edCard() {
  const c = $("#edCard"), s = (k, lbl, mn, mx, st = 1) => `<label>${lbl}<input type="range" min="${mn}" max="${mx}" step="${st}" value="${ADJ[k]}" data-a="${k}"><em>${ADJ[k]}</em></label>`;
  c.innerHTML = `<h4>${edL("Hazır görünümler", "Looks")}</h4><div class="ed-presets">${PRESETS.map((p, i) => `<button data-p="${i}"><canvas width="90" height="54"></canvas>${p.n}</button>`).join("")}</div>
    <h4>${edL("Eğriler", "Curves")}</h4><div class="ed-chan">${["rgb", "r", "g", "b"].map((k) => `<button data-ch="${k}" class="${CURVE.ch === k ? "on" : ""}">${k.toUpperCase()}</button>`).join("")}</div><canvas class="ed-curve" width="256" height="256"></canvas>
    <h4>${edL("Seviyeler", "Levels")}</h4>${s("lvIn0", edL("Siyah", "Black"), 0, 254)}${s("lvGamma", "Gamma", 0.2, 3, 0.01)}${s("lvIn1", edL("Beyaz", "White"), 1, 255)}
    <h4>${edL("Işık ve renk", "Light & colour")}</h4>${s("expo", edL("Pozlama", "Exposure"), -100, 100)}${s("bright", edL("Parlaklık", "Brightness"), -100, 100)}${s("contrast", edL("Kontrast", "Contrast"), -100, 100)}${s("sat", edL("Doygunluk", "Saturation"), -100, 100)}${s("vib", edL("Canlılık", "Vibrance"), -100, 100)}${s("temp", edL("Sıcaklık", "Warmth"), -50, 50)}${s("hue", edL("Ton", "Hue"), -180, 180)}
    <h4>${edL("Detay", "Detail")}</h4>${s("sharp", edL("Netlik", "Sharpen"), 0, 100)}${s("blur", edL("Bulanık", "Blur"), 0, 40)}${s("grain", edL("Gren", "Grain"), 0, 100)}${s("vign", edL("Vinyet", "Vignette"), 0, 100)}
    <div class="btns"><button class="pri" data-c="apply">${edL("Uygula", "Apply")}</button><button data-c="reset">${edL("Sıfırla", "Reset")}</button></div>
    <p style="color:#6E6684;margin:8px 0 0">${edL("Seçim varsa yalnızca seçili alana uygulanır.", "Applies only to the selection if there is one.")}</p>`;
  edCurveDraw(); edPresetThumbs();
}
function edPresetThumbs() {
  const l = { c: edFlatten() };
  const src = document.createElement("canvas"); src.width = 90; src.height = 54; const sg = src.getContext("2d");
  const k = Math.max(90 / l.c.width, 54 / l.c.height); sg.drawImage(l.c, (90 - l.c.width * k) / 2, (54 - l.c.height * k) / 2, l.c.width * k, l.c.height * k);
  const base = sg.getImageData(0, 0, 90, 54);
  document.querySelectorAll("#edCard .ed-presets canvas").forEach((cv, i) => {
    const p = PRESETS[i], a = { ...ADJ, bright: 0, contrast: 0, sat: 0, hue: 0, temp: 0, vib: 0, expo: 0, blur: 0, sharp: 0, grain: 0, vign: 0, lvIn0: 0, lvIn1: 255, lvGamma: 1, ...p.a };
    const cv2 = { rgb: [[0, 0], [255, 255]], r: [[0, 0], [255, 255]], g: [[0, 0], [255, 255]], b: [[0, 0], [255, 255]], ...(p.c || {}) };
    cv.getContext("2d").putImageData(edAdjustData(base, a, cv2), 0, 0);
  });
}
function edCurveDraw() {
  const cv = document.querySelector("#edCard .ed-curve"); if (!cv) return;
  const g = cv.getContext("2d"); g.clearRect(0, 0, 256, 256);
  g.strokeStyle = "#1E1730"; for (let k = 64; k < 256; k += 64) { g.beginPath(); g.moveTo(k, 0); g.lineTo(k, 256); g.moveTo(0, k); g.lineTo(256, k); g.stroke(); }
  const col = { rgb: "#EDE9F6", r: "#FF5A6E", g: "#2EE6A6", b: "#60A5FA" }[CURVE.ch];
  const lut = curveLut(CURVE[CURVE.ch]);
  g.strokeStyle = col; g.lineWidth = 2; g.beginPath(); for (let x = 0; x < 256; x++) g[x ? "lineTo" : "moveTo"](x, 255 - lut[x]); g.stroke();
  g.fillStyle = col; for (const [x, y] of CURVE[CURVE.ch]) { g.beginPath(); g.arc(x, 255 - y, 4, 0, Math.PI * 2); g.fill(); }
}
function edCurveEvents(cv) {
  let hold = -1;
  const pos = (e) => { const r = cv.getBoundingClientRect(); return [Math.max(0, Math.min(255, (e.clientX - r.left) / r.width * 256)), Math.max(0, Math.min(255, 255 - (e.clientY - r.top) / r.height * 256))]; };
  cv.onpointerdown = (e) => {
    const p = pos(e), pts = CURVE[CURVE.ch];
    hold = pts.findIndex((q) => Math.hypot(q[0] - p[0], q[1] - p[1]) < 12);
    if (e.button === 2 || e.altKey) { if (hold > 0 && hold < pts.length - 1) pts.splice(hold, 1); hold = -1; edCurveDraw(); edAdjPreview(); return; }
    if (hold < 0) { pts.push(p); pts.sort((a, b) => a[0] - b[0]); hold = pts.indexOf(p); }
    cv.setPointerCapture(e.pointerId);
  };
  cv.onpointermove = (e) => { if (hold < 0) return; const pts = CURVE[CURVE.ch]; pts[hold] = pos(e); if (hold === 0) pts[0][0] = Math.min(pts[0][0], (pts[1]?.[0] ?? 255) - 1); edCurveDraw(); clearTimeout(ED._ct); ED._ct = setTimeout(edAdjPreview, 30); };
  cv.onpointerup = () => { hold = -1; CURVE[CURVE.ch].sort((a, b) => a[0] - b[0]); };
  cv.oncontextmenu = (e) => e.preventDefault();
}

// ---------------------------------------------------------------- radyal cark
function edWheel(x, y) {
  const w = $("#edWheel");
  w.style.left = x + "px"; w.style.top = y + "px";
  w.innerHTML = TOOLS.map((t, i) => { const a = -Math.PI / 2 + (i / TOOLS.length) * Math.PI * 2, R = 124; return `<button data-tool="${t.id}" class="${t.id === ED.tool ? "cur" : ""}" style="left:${160 + Math.cos(a) * R}px;top:${160 + Math.sin(a) * R}px" title="${t.k.toUpperCase()}"><svg viewBox="0 0 24 24">${t.ic}</svg>${edL(t.tr, t.id)}</button>`; }).join("") +
    `<button class="mid" data-x="undo">↶<br>${edL("Geri al", "Undo")}</button>`;
  w.classList.add("on"); ED.wheelAt = [x, y];
}
function edWheelClose() { $("#edWheel").classList.remove("on"); }

// ---------------------------------------------------------------- kaydet / proje
function edSerialize(raw) {
  return { v: 1, W: ED.W, H: ED.H, cur: ED.cur, name: ED.name, layers: ED.layers.map((l) => ({ id: l.id, name: l.name, x: l.x, y: l.y, vis: l.vis, op: l.op, blend: l.blend, text: l.text,
    w: l.c.width, h: l.c.height, png: raw ? l.c.getContext("2d").getImageData(0, 0, l.c.width, l.c.height) : l.c.toDataURL("image/png") })) };
}
async function edDeserialize(s) {
  ED.W = s.W; ED.H = s.H; ED.cur = s.cur || 0; ED.name = s.name || ED.name;
  ED.layers = await Promise.all(s.layers.map(async (q) => {
    const l = edLayer(q.name, q.w, q.h); Object.assign(l, { id: q.id, x: q.x, y: q.y, vis: q.vis, op: q.op, blend: q.blend, text: q.text });
    if (q.png instanceof ImageData) l.c.getContext("2d").putImageData(q.png, 0, 0);
    else { const img = await new Promise((ok) => { const i = new Image(); i.onload = () => ok(i); i.src = q.png; }); l.c.getContext("2d").drawImage(img, 0, 0); }
    return l;
  }));
  $("#edSize").textContent = `${ED.W}×${ED.H}`; $("#edName").textContent = ED.name;
  edLayersUi(); edRender();
}
async function edSaveProject() {
  const r = await api.editor_project_save(ED.projPath || "", ED.name, JSON.stringify(edSerialize(false)));
  if (r?.ok) { ED.projPath = r.path; ED.dirty = false; toast(edL("Proje kaydedildi: ", "Project saved: ") + r.path.split(/[\\/]/).pop()); }
}
async function edExport(fmt) {
  const c = edFlatten(), mime = { png: "image/png", jpg: "image/jpeg", webp: "image/webp" }[fmt];
  if (fmt === "jpg") { const b = document.createElement("canvas"); b.width = c.width; b.height = c.height; const g = b.getContext("2d"); g.fillStyle = "#fff"; g.fillRect(0, 0, b.width, b.height); g.drawImage(c, 0, 0); c.getContext("2d").drawImage(b, 0, 0); }
  const r = await api.editor_export(ED.path || "", ED.name, fmt, c.toDataURL(mime, 0.94));
  if (r?.ok) { ED.dirty = false; toast(edL("Kaydedildi: ", "Saved: ") + r.path.split(/[\\/]/).pop()); }
}

// ---------------------------------------------------------------- sablonlar
const TEMPLATES = [
  { n: "YouTube kapağı", w: 1280, h: 720, bg: "#120E19" }, { n: "Story / Reels", w: 1080, h: 1920, bg: "#120E19" },
  { n: "Instagram gönderi", w: 1080, h: 1350, bg: "#120E19" }, { n: "Kare gönderi", w: 1080, h: 1080, bg: "#120E19" },
  { n: "Profil fotoğrafı", w: 1024, h: 1024, bg: "#2A1650" }, { n: "Twitter / X başlık", w: 1500, h: 500, bg: "#120E19" },
  { n: "Masaüstü duvar kâğıdı", w: 1920, h: 1080, bg: "#07060B" }, { n: "Telefon duvar kâğıdı", w: 1170, h: 2532, bg: "#07060B" },
  { n: "Şeffaf boş", w: 1600, h: 1200, bg: null },
];
function edTemplates() {
  const m = document.createElement("div"); m.className = "ed-modal";
  m.innerHTML = `<div><h3>${edL("Yeni belge", "New document")}</h3><div class="ed-tpls">${TEMPLATES.map((t, i) => { const k = 64 / Math.max(t.w, t.h); return `<button data-tp="${i}"><i style="width:${t.w * k}px;height:${t.h * k}px"></i>${t.n}<small>${t.w}×${t.h}</small></button>`; }).join("")}
    <button data-tp="meme"><i style="width:64px;height:48px;background:#333"></i>Meme<small>${edL("açık görsel + üst/alt yazı", "open image + top/bottom text")}</small></button></div>
    <div class="btns" style="display:flex;gap:8px;margin-top:14px;justify-content:flex-end"><button class="ed-cl" style="border:0;background:#1E1730;color:#D9CCFF;padding:8px 14px;cursor:pointer">${edL("Kapat", "Close")}</button></div></div>`;
  m.onclick = (e) => {
    const b = e.target.closest("[data-tp]");
    if (b) {
      if (b.dataset.tp === "meme") { if (ED.layers.length) edMeme(); }
      else { const t = TEMPLATES[+b.dataset.tp]; edNew(t.w, t.h, t.n, "", t.bg); edFit(); edLayersUi(); edRender(); }
      m.remove(); return;
    }
    if (e.target === m || e.target.closest(".ed-cl")) m.remove();
  };
  $("#ed").appendChild(m);
}

// ---------------------------------------------------------------- kurulum
function edMount() {
  if ($("#ed")) return;
  const d = document.createElement("div"); d.id = "ed";
  d.innerHTML = `<canvas id="edView"></canvas>
    <div class="ed-top"><b id="edName"></b><span id="edSize"></span>
      <button data-x="new">${edL("Yeni", "New")}</button><button data-x="open">${edL("Proje aç", "Open project")}</button><button data-x="saveproj">.kami</button>
      <button data-x="exp-png" class="pri">${edL("Kaydet PNG", "Save PNG")}</button><button data-x="exp-jpg">JPG</button><button data-x="exp-webp">WebP</button>
      <button data-x="undo" title="Ctrl+Z">↶</button><button data-x="redo" title="Ctrl+Y">↷</button><button data-x="close">✕</button></div>
    <div class="ed-opt" id="edOpt"></div><div class="ed-card" id="edCard" hidden></div><div class="ed-wheel" id="edWheel"></div>
    <div class="ed-layers" id="edLayers"><div class="grip"><span></span> · Tab</div><div class="row"></div></div>
    <div class="ed-hint">${edL("Sağ tık / Boşluk: araç çarkı · B fırça · E silgi · M seç · L kement · V taşı · T metin · C kırp · A ayarlar · [ ] boyut · Ctrl+Z geri al · orta tuş: kaydır · tekerlek: yakınlaş", "Right-click / Space: tool wheel · B brush · E eraser · M select · L lasso · V move · T text · C crop · A adjust · [ ] size · Ctrl+Z undo · middle: pan · wheel: zoom")}</div>`;
  document.body.appendChild(d);
  const v = $("#edView");
  v.addEventListener("pointerdown", (e) => edDown(e)); v.addEventListener("pointermove", (e) => edMove(e)); v.addEventListener("pointerup", (e) => edUp(e));
  v.addEventListener("pointerleave", () => { ED.hover = null; edRender(); });
  v.addEventListener("dblclick", (e) => { const [x, y] = toDoc(e.offsetX, e.offsetY); const i = ED.layers.findIndex((q) => q.text && x >= q.x && y >= q.y && x <= q.x + q.c.width && y <= q.y + q.c.height); if (i >= 0) { ED.cur = i; edEditText(ED.layers[i]); } });
  v.addEventListener("wheel", (e) => { e.preventDefault(); const f = e.deltaY < 0 ? 1.12 : 1 / 1.12, [x, y] = toDoc(e.offsetX, e.offsetY); ED.z = Math.max(0.02, Math.min(40, ED.z * f)); ED.ox = e.offsetX - x * ED.z; ED.oy = e.offsetY - y * ED.z; edRender(); }, { passive: false });
  v.addEventListener("contextmenu", (e) => { e.preventDefault(); edWheel(e.clientX, e.clientY); });
  d.addEventListener("click", edClick); d.addEventListener("input", edInput); d.addEventListener("change", edInput);
  $("#edLayers .grip").onclick = () => $("#edLayers").classList.toggle("open");
  // katman surukle-birak siralama
  const row = $("#edLayers .row");
  row.addEventListener("dragstart", (e) => { const c = e.target.closest(".ed-ly"); if (c) e.dataTransfer.setData("text", c.dataset.i); });
  row.addEventListener("dragover", (e) => { e.preventDefault(); document.querySelectorAll(".ed-ly.drop").forEach((x) => x.classList.remove("drop")); e.target.closest(".ed-ly")?.classList.add("drop"); });
  row.addEventListener("drop", (e) => { e.preventDefault(); const to = e.target.closest(".ed-ly"); if (!to) return; const from = +e.dataTransfer.getData("text"), dst = +to.dataset.i; if (from === dst) return; edSnapAll(edL("Sırala", "Reorder")); const [l] = ED.layers.splice(from, 1); ED.layers.splice(dst, 0, l); ED.cur = dst; edLayersUi(); edRender(); });
  row.addEventListener("focusout", (e) => { const n = e.target.closest(".nm"); if (n) { const i = +n.closest(".ed-ly").dataset.i; ED.layers[i].name = n.textContent.trim() || ED.layers[i].name; } });
  let idle; document.addEventListener("pointermove", () => { d.classList.remove("idle"); clearTimeout(idle); idle = setTimeout(() => d.classList.add("idle"), 2500); });
  addEventListener("resize", () => ED.on && edRender());
}
function edClick(e) {
  const tb = e.target.closest("[data-tool]"); if (tb) { ED.tool = tb.dataset.tool; edWheelClose(); edOpt(); return; }
  if (!e.target.closest("#edWheel")) edWheelClose();
  const p = e.target.closest("[data-p]"); if (p && e.target.closest("#edCard")) { edPresetApply(PRESETS[+p.dataset.p]); return; }
  const ch = e.target.closest("[data-ch]"); if (ch) { CURVE.ch = ch.dataset.ch; edCard(); return; }
  const c = e.target.closest("[data-c]"); if (c) { c.dataset.c === "apply" ? edAdjApply() : edAdjReset(); return; }
  const ly = e.target.closest(".ed-ly");
  const lb = e.target.closest("[data-l]");
  if (lb && lb.tagName === "BUTTON") {
    const k = lb.dataset.l;
    if (k === "vis") { const l = ED.layers[+ly.dataset.i]; l.vis = !l.vis; edLayersUi(); edRender(); }
    else if (k === "add") edLayerAdd(); else if (k === "dup") edLayerDup(); else if (k === "del") edLayerDel(); else if (k === "merge") edLayerMergeDown();
    return;
  }
  if (ly && !e.target.closest("input, select, .nm")) { ED.cur = +ly.dataset.i; ED.adjSrc = null; edLayersUi(); if (ED.tool === "adjust") edCard(); return; }
  const x = e.target.closest("[data-x]"); if (!x) return;
  const a = x.dataset.x;
  if (a === "undo") { edUndo(); edWheelClose(); } else if (a === "redo") edRedo();
  else if (a === "close") edClose();
  else if (a === "new") edTemplates();
  else if (a === "open") api.editor_project_open().then((r) => r?.ok && edDeserialize(JSON.parse(r.data)).then(() => { ED.projPath = r.path; edFit(); edRender(); }));
  else if (a === "saveproj") edSaveProject();
  else if (a.startsWith("exp-")) edExport(a.slice(4));
  else if (a === "selall") { edSelRect(0, 0, ED.W, ED.H); edRender(); } else if (a === "selnone") { ED.sel = null; edRender(); }
  else if (a === "selinv" && ED.sel) { const pth = new Path2D(); pth.rect(0, 0, ED.W, ED.H); pth.addPath(ED.sel.path); ED.sel = { path: pth, box: [0, 0, ED.W, ED.H], even: true }; edSelEven(); edRender(); }
  else if (a === "sellayer") edSelToLayer(false); else if (a === "selcut") edSelToLayer(true); else if (a === "selfill") edFillSel(); else if (a === "selclear") edClearSel();
  else if (a === "fliph") edFlipLayer(true); else if (a === "flipv") edFlipLayer(false);
  else if (a === "center") { const l = cl(); edSnap(edL("Ortala", "Center")); l.x = Math.round((ED.W - l.c.width) / 2); l.y = Math.round((ED.H - l.c.height) / 2); edRender(); }
  else if (a === "cropok") edCropApply(); else if (a === "cropno") { ED.cropR = null; edRender(); edOpt(); }
  else if (a === "meme") edMeme();
}
function edSelEven() {   // ters secim: evenodd kuralini Path2D clip/fill'e uygula
  const p = ED.sel.path; const orig = CanvasRenderingContext2D.prototype;
  ED.sel.path = p; ED.sel.rule = "evenodd";
  if (!orig._kamiEven) { const c0 = orig.clip, f0 = orig.fill; orig.clip = function (pp, r) { return pp === ED.sel?.path && ED.sel?.rule ? c0.call(this, pp, ED.sel.rule) : c0.apply(this, arguments); }; orig.fill = function (pp, r) { return pp === ED.sel?.path && ED.sel?.rule ? f0.call(this, pp, ED.sel.rule) : f0.apply(this, arguments); }; orig._kamiEven = true; }
}
function edInput(e) {
  const o = e.target.dataset.o, t = e.target.dataset.t, a = e.target.dataset.a, l = e.target.dataset.l;
  if (o) { const v = e.target.value; if (o === "size") ED.size = +v; else if (o === "hard") ED.hard = v / 100; else if (o === "opacity") ED.opacity = v / 100; else if (o === "color") ED.color = v; else if (o === "cropRatio") ED.cropRatio = +v || 0; edRender(); }
  else if (t) edTextOpt(t, e.target.type === "checkbox" ? e.target.checked : e.target.type === "number" || e.target.type === "range" ? +e.target.value : e.target.value);
  else if (a && e.target.closest("#edCard")) { ADJ[a] = +e.target.value; e.target.nextElementSibling.textContent = e.target.value; clearTimeout(ED._at); ED._at = setTimeout(edAdjPreview, 40); }
  else if (l === "op" && e.type === "input") { const ly = ED.layers[+e.target.closest(".ed-ly").dataset.i]; ly.op = e.target.value / 100; edRender(); }
  else if (l === "blend") { const ly = ED.layers[+e.target.closest(".ed-ly").dataset.i]; ly.blend = e.target.value; edRender(); }
}
document.addEventListener("keydown", (e) => {
  if (!ED.on || e.target.matches?.("input, textarea, [contenteditable]")) return;
  const k = e.key.toLowerCase();
  if (e.ctrlKey && k === "z") { e.preventDefault(); e.shiftKey ? edRedo() : edUndo(); }
  else if (e.ctrlKey && k === "y") { e.preventDefault(); edRedo(); }
  else if (e.ctrlKey && k === "s") { e.preventDefault(); e.shiftKey ? edSaveProject() : edExport("png"); }
  else if (e.ctrlKey && k === "j") { e.preventDefault(); ED.sel ? edSelToLayer(false) : edLayerDup(); }
  else if (e.ctrlKey && k === "a") { e.preventDefault(); edSelRect(0, 0, ED.W, ED.H); edRender(); }
  else if (e.ctrlKey && k === "d") { e.preventDefault(); ED.sel = null; edRender(); }
  else if (e.ctrlKey && k === "t") { e.preventDefault(); edTransformOpen(); }
  else if (k === " " && !e.repeat) { e.preventDefault(); ED.space = true; if (ED.hover) { const v = $("#edView").getBoundingClientRect(); edWheel(v.left + ED.hover[0] * ED.z + ED.ox, v.top + ED.hover[1] * ED.z + ED.oy); } }
  else if (k === "tab") { e.preventDefault(); $("#edLayers").classList.toggle("open"); }
  else if (k === "[") { ED.size = Math.max(1, Math.round(ED.size / 1.2)); edOpt(); edRender(); }
  else if (k === "]") { ED.size = Math.min(400, Math.round(ED.size * 1.2)); edOpt(); edRender(); }
  else if (k === "delete" || k === "backspace") { e.preventDefault(); ED.sel ? edClearSel() : edLayerDel(); }
  else if (k === "enter" && ED.tool === "crop") edCropApply();
  else if (k === "escape") { if ($("#edWheel").classList.contains("on")) edWheelClose(); else if (ED.cropR) { ED.cropR = null; edRender(); } else if (ED.sel) { ED.sel = null; edRender(); } }
  else if (k === "0") { edFit(); edRender(); }
  else { const t = TOOLS.find((x) => x.k === k); if (t && !e.ctrlKey) { ED.tool = t.id; edOpt(); } }
}, true);
document.addEventListener("keyup", (e) => { if (e.key === " " && ED.on) { ED.space = false; const w = $("#edWheel"); if (w.classList.contains("on")) { const hot = w.querySelector("button:hover"); if (hot) hot.click(); else edWheelClose(); } } }, true);

async function edOpen(path) {
  edMount();
  $("#ed").classList.add("on"); ED.on = true;
  if (path) {
    const r = await api.image_data(path, 12000);
    if (!r?.ok) { toast(edL("Görsel açılamadı", "Can't open image")); return; }
    await edOpenImage(r.url, path.split(/[\\/]/).pop().replace(/\.[^.]+$/, ""), path);
  } else if (!ED.layers.length) edTemplates();
  ED.tool = "brush"; edOpt(); edLayersUi(); edFit(); edRender();
  setTimeout(() => $("#edLayers").classList.add("open"), 200); setTimeout(() => $("#edLayers").classList.remove("open"), 2200);
  edCurveHook();
}
function edCurveHook() { new MutationObserver(() => { const cv = document.querySelector("#edCard .ed-curve"); if (cv && !cv._h) { cv._h = 1; edCurveEvents(cv); } }).observe($("#edCard"), { childList: true }); }

function edTransformLayer(scalePct, deg, flipX, flipY) {
  const l = cl();
  if (!l || !l.c) return;
  edSnap(edL("Dönüştür", "Transform"));
  const sc = Math.max(0.05, Math.min(8, Number(scalePct || 100) / 100));
  const rad = (Number(deg || 0) * Math.PI) / 180;
  const nw = Math.max(1, Math.round(l.c.width * sc));
  const nh = Math.max(1, Math.round(l.c.height * sc));
  const cos = Math.abs(Math.cos(rad)), sin = Math.abs(Math.sin(rad));
  const rw = Math.max(1, Math.round(nw * cos + nh * sin));
  const rh = Math.max(1, Math.round(nw * sin + nh * cos));
  const out = document.createElement("canvas");
  out.width = rw; out.height = rh;
  const ctx = out.getContext("2d");
  ctx.translate(rw / 2, rh / 2);
  ctx.rotate(rad);
  ctx.scale((flipX ? -1 : 1) * sc, (flipY ? -1 : 1) * sc);
  ctx.drawImage(l.c, -l.c.width / 2, -l.c.height / 2);
  l.x = Math.round(l.x + (l.c.width - rw) / 2);
  l.y = Math.round(l.y + (l.c.height - rh) / 2);
  l.c = out;
  edLayersUi();
  edRender();
}

function edTransformOpen() {
  const l = cl();
  if (!l) return;
  const card = $("#edCard");
  card.innerHTML = `<div class="ed-tr-box" style="display:flex;flex-direction:column;gap:8px;padding:10px">
    <strong>${edL("Serbest Dönüştürme (Ctrl+T)", "Free Transform (Ctrl+T)")}</strong>
    <label style="font-size:12px">${edL("Ölçek (%)", "Scale (%)")}: <input id="edTrSc" type="number" min="5" max="800" value="100" style="width:74px"></label>
    <label style="font-size:12px">${edL("Döndür (°)", "Rotate (°)")}: <input id="edTrDeg" type="number" min="-360" max="360" value="0" style="width:74px"></label>
    <div style="display:flex;gap:10px;font-size:12px">
      <label><input id="edTrFx" type="checkbox"> ${edL("Yatay çevir", "Flip H")}</label>
      <label><input id="edTrFy" type="checkbox"> ${edL("Dikey çevir", "Flip V")}</label>
    </div>
    <div style="display:flex;gap:6px">
      <button id="edTrOk">${edL("Uygula", "Apply")}</button>
      <button id="edTrNo">${edL("İptal", "Cancel")}</button>
    </div>
  </div>`;
  card.classList.add("on");
  card.querySelector("#edTrOk").onclick = () => {
    edTransformLayer(card.querySelector("#edTrSc").value, card.querySelector("#edTrDeg").value,
      card.querySelector("#edTrFx").checked, card.querySelector("#edTrFy").checked);
    card.classList.remove("on");
  };
  card.querySelector("#edTrNo").onclick = () => card.classList.remove("on");
}

function edPasteImageBlob(blob) {
  if (!blob) return;
  const url = URL.createObjectURL(blob);
  const im = new Image();
  im.onload = () => {
    URL.revokeObjectURL(url);
    edSnapAll(edL("Yapıştır", "Paste"));
    edLayerAdd(edL("Pano", "Clipboard"));
    const l = cl();
    l.c.width = im.naturalWidth;
    l.c.height = im.naturalHeight;
    l.c.getContext("2d").drawImage(im, 0, 0);
    l.x = Math.max(0, Math.round((ED.W - l.c.width) / 2));
    l.y = Math.max(0, Math.round((ED.H - l.c.height) / 2));
    edLayersUi();
    edRender();
    toast(edL("Panodan katman eklendi", "Pasted as layer"));
  };
  im.src = url;
}

window.addEventListener("paste", (e) => {
  if (!ED.on || e.target.matches?.("input, textarea, [contenteditable]")) return;
  const items = e.clipboardData?.items || [];
  for (const it of items) {
    if (it.type && it.type.startsWith("image/")) {
      e.preventDefault();
      edPasteImageBlob(it.getAsFile());
      return;
    }
  }
});
async function edClose() {
  if (ED.dirty && !await kAsk(edL("Kaydedilmemiş değişiklikler var. Kapatılsın mı?", "Unsaved changes. Close anyway?"), edL("Kapat", "Close"), edL("Vazgeç", "Cancel"), true)) return;
  ED.on = false; $("#ed").classList.remove("on");
}
window.kamiEditor = { open: edOpen, openImage: edOpenImage };
