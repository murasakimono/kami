// Kami Picture editoru: rotus + yapay zeka araclari.
// Leke iyilestir / nesne sil (LaMa), tikla-sec (SAM2), klon damgasi, sivilastir, arka plan kaldir, 4x buyut,
// yuz duzelt, secimi icerige duyarli doldur, icerige duyarli tasi. Yapay zeka yerel GPU'da (IOPaint).
"use strict";
TOOLS.splice(5, 0, { id: "magic", k: "w", tr: "Tıkla-seç", ic: '<path d="M5 19l9-9M14 4v3M18 6l-2 2M20 10h-3M15 3l1 2"/><circle cx="16" cy="8" r="1"/>' });
TOOLS.splice(TOOLS.length - 1, 0,
  { id: "heal", k: "j", tr: "Nesne sil", ic: '<path d="M4 20l4-1 11-11-3-3L5 16zM14 6l3 3"/><path d="M3 4l3 3M7 3v2M3 8h2"/>' },
  { id: "clone", k: "s", tr: "Klon", ic: '<circle cx="8" cy="8" r="4"/><circle cx="16" cy="16" r="4"/><path d="M11 11l2 2"/>' },
  { id: "liquify", k: "q", tr: "Sıvılaştır", ic: '<path d="M3 12c3-6 6 6 9 0s6 6 9 0"/><path d="M3 17c3-4 6 4 9 0s6 4 9 0"/>' });
TOOLS.push({ id: "ai", k: "g", tr: "Yapay zekâ", ic: '<path d="M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z"/><path d="M19 15l1 2 2 1-2 1-1 2-1-2-2-1 2-1z"/>' });

const AI = { clicks: [], liq: { mode: "push" }, cloneSrc: null };
function edBusy(t) { let b = $("#ed .ed-busy"); if (!t) { b?.remove(); return; } if (!b) { b = document.createElement("div"); b.className = "ed-busy"; $("#ed").appendChild(b); } b.textContent = t; }

// ---------------------------------------------------------------- kurulum / cagri
async function aiReady() {
  const st = await api.pic_ai_status();
  if (st?.installed) return true;
  if (st?.installing) { toast(edL("Yapay zekâ araçları kuruluyor: ", "Installing AI tools: ") + (st.installing || "")); return false; }
  if (!await kAsk(edL(`Yapay zekâ araçları (nesne silme, tıkla-seç, arka plan, 4x büyütme, yüz düzeltme) bir kez kurulacak: yaklaşık ${st?.size_gb || 4.5} GB, ekran kartında çalışır. Kurulsun mu?`,
    `AI tools will be installed once (~${st?.size_gb || 4.5} GB, runs on your GPU). Install?`))) return false;
  await api.ai_install("iopaint");
  edBusy(edL("Yapay zekâ araçları kuruluyor… (birkaç dakika sürer, Kami açık kalsın)", "Installing AI tools…"));
  for (;;) {
    await new Promise((ok) => setTimeout(ok, 3000));
    const s = await api.pic_ai_status();
    if (s?.installed && !s.installing) { edBusy(""); toast(edL("Yapay zekâ araçları hazır", "AI tools ready")); return true; }
    if (!s?.installing && s?.error) { edBusy(""); toast(edL("Kurulum olmadı: ", "Install failed: ") + s.error); return false; }
    if (s?.installing) edBusy(edL("Kuruluyor: ", "Installing: ") + s.installing);
  }
}
async function aiCall(op, image, mask, clicks, label) {
  if (!(await aiReady())) return null;
  edBusy((label || edL("Yapay zekâ çalışıyor…", "AI working…")) + (ED._aiFirst ? "" : edL(" (ilk sefer modeller iner)", " (first run downloads models)")));
  const r = await api.pic_ai(op, image, mask || "", clicks || [], 4);
  ED._aiFirst = true; edBusy("");
  if (!r?.ok) { toast(edL("Olmadı: ", "Failed: ") + (r?.error || "")); return null; }
  return r.image;
}
const loadImg = (src) => new Promise((ok, no) => { const i = new Image(); i.onload = () => ok(i); i.onerror = no; i.src = src; });
function layerDataUrl(l) { return l.c.toDataURL("image/png"); }

// ---------------------------------------------------------------- nesne sil / leke iyilestir: boya, birak, LaMa doldursun
function healStart(x, y) {
  const l = cl();
  if (!ED.overlay || ED.overlay.width !== ED.W || ED.overlay.height !== ED.H) { ED.overlay = document.createElement("canvas"); ED.overlay.width = ED.W; ED.overlay.height = ED.H; }
  ED.healLast = [x, y]; healDab(x, y);
}
function healDab(x, y) {
  const g = ED.overlay.getContext("2d"); g.fillStyle = "#FF3B6B"; g.beginPath(); g.arc(x, y, ED.size / 2, 0, Math.PI * 2); g.fill();
}
function healMove(x, y) {
  const [lx, ly] = ED.healLast, d = Math.hypot(x - lx, y - ly), st = Math.max(1, ED.size * 0.2);
  for (let t = st; t <= d; t += st) healDab(lx + (x - lx) * t / d, ly + (y - ly) * t / d);
  if (d >= st) ED.healLast = [x, y];
  edRender();
}
async function healApply(maskDoc) {
  const l = cl();
  if (l.text) { toast(edL("Metin katmanında olmaz; resim katmanını seç", "Pick an image layer")); ED.overlay = null; edRender(); return; }
  // maske katmanin koordinatlarina
  const m = document.createElement("canvas"); m.width = l.c.width; m.height = l.c.height; const mg = m.getContext("2d");
  mg.fillStyle = "#000"; mg.fillRect(0, 0, m.width, m.height);
  mg.globalCompositeOperation = "lighter"; const tmp = document.createElement("canvas"); tmp.width = ED.W; tmp.height = ED.H; const tg = tmp.getContext("2d");
  tg.drawImage(maskDoc, 0, 0); tg.globalCompositeOperation = "source-in"; tg.fillStyle = "#fff"; tg.fillRect(0, 0, ED.W, ED.H);
  mg.drawImage(tmp, -l.x, -l.y);
  const res = await aiCall("erase", layerDataUrl(l), m.toDataURL("image/png"), null, edL("Siliniyor ve dolduruluyor…", "Erasing and filling…"));
  ED.overlay = null;
  if (res) { edSnap(edL("Nesne sil", "Remove object")); const img = await loadImg(res); const g = l.c.getContext("2d"); g.clearRect(0, 0, l.c.width, l.c.height); g.drawImage(img, 0, 0); edLayerThumb(ED.cur); }
  edRender();
}

// ---------------------------------------------------------------- tikla-sec (SAM2): maske -> secim
async function magicClick(x, y, neg, add) {
  const key = ED.undo.length + ":" + ED.layers.length;
  if (!add || AI.segKey !== key) AI.clicks = [];
  if (AI.segKey !== key || !AI.segImg) { AI.segKey = key; AI.segImg = edFlatten().toDataURL("image/jpeg", 0.92); }
  AI.clicks.push([Math.round(x), Math.round(y), neg ? 0 : 1]);
  const res = await aiCall("seg", AI.segImg, "", AI.clicks, edL("Nesne seçiliyor…", "Selecting…"));
  if (!res) return;
  const img = await loadImg(res);
  maskToSelection(img);
  toast(edL("Seçildi. Shift+tık ekle, Alt+tık çıkar · Delete sil · Ctrl+J katmana al · Yapay zekâ kartından nesneyi sil/taşı", "Selected. Shift+click add, Alt+click subtract"));
}
function maskToSelection(img) {   // maske -> satir dikdortgenleri (kirpma) + kenar cizgisi (gosterim)
  const k = Math.min(1, 700 / Math.max(img.width, img.height)), w = Math.max(1, Math.round(img.width * k)), h = Math.max(1, Math.round(img.height * k));
  const c = document.createElement("canvas"); c.width = w; c.height = h; const g = c.getContext("2d"); g.drawImage(img, 0, 0, w, h);
  const d = g.getImageData(0, 0, w, h).data, inside = (x, y) => x >= 0 && y >= 0 && x < w && y < h && d[(y * w + x) * 4 + 3] > 100;
  const sx = ED.W / w, sy = ED.H / h, path = new Path2D(), outline = new Path2D();
  let any = false, minx = w, miny = h, maxx = 0, maxy = 0;
  for (let y = 0; y < h; y++) {
    let x = 0;
    while (x < w) {
      while (x < w && !inside(x, y)) x++;
      const s0 = x; while (x < w && inside(x, y)) x++;
      if (x > s0) { path.rect(s0 * sx, y * sy, (x - s0) * sx + 0.5, sy + 0.5); any = true; minx = Math.min(minx, s0); maxx = Math.max(maxx, x); miny = Math.min(miny, y); maxy = Math.max(maxy, y + 1); }
    }
  }
  for (let y = 0; y <= h; y++) for (let x = 0; x <= w; x++) {   // kenarlar: icerisi/disarisi degisen hucre sinirlari
    if (inside(x, y) !== inside(x, y - 1)) { outline.moveTo(x * sx, y * sy); outline.lineTo((x + 1) * sx, y * sy); }
    if (inside(x, y) !== inside(x - 1, y)) { outline.moveTo(x * sx, y * sy); outline.lineTo(x * sx, (y + 1) * sy); }
  }
  ED.sel = any ? { path, outline, box: [minx * sx, miny * sy, (maxx - minx) * sx, (maxy - miny) * sy] } : null;
  edRender();
}

// ---------------------------------------------------------------- klon damgasi (Alt+tik kaynak)
function cloneStart(x, y, alt) {
  const l = cl();
  if (alt) { AI.cloneSrc = [x, y]; toast(edL("Kaynak alındı; şimdi boya", "Source set; now paint")); return false; }
  if (!AI.cloneSrc) { toast(edL("Önce Alt+tık ile kaynak seç", "Alt+click to set the source first")); return false; }
  edSnap(edL("Klon", "Clone"));
  AI.cloneOff = [AI.cloneSrc[0] - x, AI.cloneSrc[1] - y];
  AI.cloneSnap = document.createElement("canvas"); AI.cloneSnap.width = l.c.width; AI.cloneSnap.height = l.c.height; AI.cloneSnap.getContext("2d").drawImage(l.c, 0, 0);
  AI.cloneLast = [x, y]; cloneDab(x, y); return true;
}
function cloneDab(x, y) {
  const l = cl(), g = l.c.getContext("2d"), r = ED.size / 2, lx = x - l.x, ly = y - l.y;
  g.save(); edClip(g, l); g.beginPath(); g.arc(lx, ly, r, 0, Math.PI * 2); g.clip();
  g.globalAlpha = ED.opacity;
  g.drawImage(AI.cloneSnap, AI.cloneOff[0], AI.cloneOff[1]);
  g.restore();
}
function cloneMove(x, y) {
  const [lx, ly] = AI.cloneLast, d = Math.hypot(x - lx, y - ly), st = Math.max(1, ED.size * 0.15);
  for (let t = st; t <= d; t += st) cloneDab(lx + (x - lx) * t / d, ly + (y - ly) * t / d);
  if (d >= st) AI.cloneLast = [x, y];
  edRender();
}

// ---------------------------------------------------------------- sivilastir: it / sisir / daralt / dondur
function liqStart(x, y) {
  const l = cl(); if (l.text) { toast(edL("Resim katmanı seç", "Pick an image layer")); return false; }
  edSnap(edL("Sıvılaştır", "Liquify"));
  AI.liqData = l.c.getContext("2d").getImageData(0, 0, l.c.width, l.c.height); AI.liqLast = [x - l.x, y - l.y];
  return true;
}
function liqMove(x, y) {
  const l = cl(), d = AI.liqData, W = d.width, H = d.height, px = d.data;
  x -= l.x; y -= l.y;
  const [lx, ly] = AI.liqLast, dx = x - lx, dy = y - ly, R = ED.size / 2, mode = AI.liq.mode, str = ED.opacity;
  if (mode === "push" && Math.hypot(dx, dy) < 1) return;
  const x0 = Math.max(0, Math.floor(x - R)), y0 = Math.max(0, Math.floor(y - R)), x1 = Math.min(W - 1, Math.ceil(x + R)), y1 = Math.min(H - 1, Math.ceil(y + R));
  if (x1 <= x0 || y1 <= y0) return;
  const src = new Uint8ClampedArray(px);
  for (let yy = y0; yy <= y1; yy++) for (let xx = x0; xx <= x1; xx++) {
    const ox = xx - x, oy = yy - y, dist = Math.hypot(ox, oy); if (dist >= R) continue;
    const f = (1 - dist / R) ** 2 * str;
    let sx = xx, sy = yy;
    if (mode === "push") { sx -= dx * f; sy -= dy * f; }
    else if (mode === "bloat") { sx -= ox * f * 0.25; sy -= oy * f * 0.25; }
    else if (mode === "pinch") { sx += ox * f * 0.25; sy += oy * f * 0.25; }
    else if (mode === "twirl") { const a = 0.15 * f, c = Math.cos(a), s = Math.sin(a); sx = x + ox * c - oy * s; sy = y + ox * s + oy * c; }
    const ix = Math.max(0, Math.min(W - 1, Math.round(sx))), iy = Math.max(0, Math.min(H - 1, Math.round(sy))), si = (iy * W + ix) * 4, di = (yy * W + xx) * 4;
    px[di] = src[si]; px[di + 1] = src[si + 1]; px[di + 2] = src[si + 2]; px[di + 3] = src[si + 3];
  }
  l.c.getContext("2d").putImageData(d, 0, 0, x0, y0, x1 - x0 + 1, y1 - y0 + 1);
  AI.liqLast = [x, y]; edRender();
}

// ---------------------------------------------------------------- yapay zeka karti
function aiCard() {
  const c = $("#edCard"); c.hidden = false;
  c.innerHTML = `<h4>${edL("Yapay zekâ (yerel, ekran kartı)", "AI (local GPU)")}</h4>
    <div class="btns" style="flex-direction:column;align-items:stretch">
      <button data-ai="nobg">✦ ${edL("Arka planı kaldır (yeni katman)", "Remove background (new layer)")}</button>
      <button data-ai="selfill">${edL("Seçimi sil ve çevreyle doldur", "Delete selection, fill from surroundings")}</button>
      <button data-ai="selmove">${edL("İçeriğe duyarlı taşı (seçimi katmana al, yeri dolsun)", "Content-aware move")}</button>
      <button data-ai="upscale">${edL("4x büyüt (Real-ESRGAN, tüm görsel)", "Upscale 4x (whole image)")}</button>
      <button data-ai="face">${edL("Yüzleri düzelt (GFPGAN)", "Restore faces (GFPGAN)")}</button>
    </div>
    <h4>${edL("Vektör ve animasyon", "Vector & animation")}</h4>
    <div class="btns" style="flex-direction:column;align-items:stretch">
      <button data-ai="vec-color">${edL("Vektöre çevir: renkli logo/çizim (SVG)", "Vectorize: colour logo (SVG)")}</button>
      <button data-ai="vec-bw">${edL("Vektöre çevir: siyah-beyaz çizgi", "Vectorize: line art")}</button>
      <button data-ai="vec-photo">${edL("Vektöre çevir: ayrıntılı", "Vectorize: detailed")}</button>
      <button data-ai="gif">${edL("GIF yap (her katman bir kare)", "Make GIF (each layer a frame)")}</button>
      <button data-ai="mp4">${edL("MP4 yap (her katman bir kare)", "Make MP4 (each layer a frame)")}</button>
      <button data-ai="webp-sheet">${edL("Hareketli WebP Çıkartma Yap", "Make Animated WebP Sheet")}</button>
      <label style="display:flex;gap:8px;align-items:center">${edL("Kare süresi", "Frame time")} <input type="number" id="aiMs" value="120" min="20" max="5000" style="width:70px;background:#0A0810;color:#EDE9F6;border:1px solid #2A2140"> ms</label>
    </div>
    <h4>${edL("Photoshop Pro & Makro (MCP)", "Photoshop Pro & Macro (MCP)")}</h4>
    <div class="btns" style="flex-direction:column;align-items:stretch">
      <button data-ai="pro-contact-shadow">🛍️ ${edL("Temas Gölgesi + E-Ticaret (1200px)", "Contact Shadow + E-Com (1200px)")}</button>
      <button data-ai="pro-freq-sep">🩹 ${edL("Frekans Ayrıştırma (Doku/Renk)", "Frequency Separation")}</button>
      <button data-ai="pro-oklch">🎨 ${edL("OKLCH Renk Paleti Çıkar", "Extract OKLCH Palette")}</button>
      <button data-ai="pro-wm-embed">🔒 ${edL("Görünmez Telif İmzası Göm", "Embed Invisible Watermark")}</button>
      <button data-ai="pro-wm-read">🔍 ${edL("Telif İmzasını Oku", "Read Invisible Watermark")}</button>
      <button data-ai="pro-send-studio">🎬 ${edL("Studio Medyaya Gönder", "Send to Kami Studio")}</button>
      <div style="display:flex;gap:4px;margin-top:2px">
        <select id="proMacroSel" style="flex:1;background:#0A0810;color:#EDE9F6;border:1px solid #2A2140;padding:4px"></select>
        <button data-ai="pro-macro-run" style="flex:none">▶ ${edL("Uygula", "Run")}</button>
      </div>
      <div id="proPaletteOut" style="display:flex;gap:4px;flex-wrap:wrap;margin-top:4px"></div>
    </div>
    <h4>${edL("İpuçları", "Tips")}</h4>
    <p style="color:#8E86A3;line-height:1.5;margin:0">${edL("Nesne sil (J): üzerinden boya, bırakınca silinir. Tıkla-seç (W): nesneye tıkla. Klon (S): Alt+tık kaynak. Sıvılaştır (Q): it/şişir/daralt/döndür.", "Remove (J): paint over it. Click-select (W): click an object. Clone (S): Alt+click source. Liquify (Q).")}</p>
    <p id="aiState" style="color:#6E6684;margin:8px 0 0"></p>`;
  api.pic_ai_status().then((s) => { const e = $("#aiState"); if (e) e.textContent = s?.installed ? edL("Kurulu", "Installed") + (s.device ? " · " + s.device : "") : edL("İlk kullanımda kurulur (~4.5 GB)", "Installs on first use (~4.5 GB)"); });
  api.pic_macro_list?.().then((ms) => {
    const arr = Array.isArray(ms) ? ms : (ms?.macros || []);
    const sel = $("#proMacroSel"); if (!sel || !arr.length) return;
    sel.innerHTML = arr.map((m) => `<option value="${String(m.id || "").replace(/"/g, "&quot;")}">${m.name || m.id}</option>`).join("");
  });
}
async function aiAction(a) {
  const l = cl();
  if (a === "nobg") {
    if (l.text) return toast(edL("Resim katmanı seç", "Pick an image layer"));
    const r = await aiCall("nobg", layerDataUrl(l), "", null, edL("Arka plan kaldırılıyor…", "Removing background…")); if (!r) return;
    const img = await loadImg(r); edLayerAdd(l.name + " · " + edL("dekupe", "cutout")); const n = cl(); n.c.width = img.width; n.c.height = img.height; n.x = l.x; n.y = l.y; n.c.getContext("2d").drawImage(img, 0, 0);
    l.vis = false; edLayersUi(); edRender();
  } else if (a === "selfill" || a === "selmove") {
    if (!ED.sel) return toast(edL("Önce bir seçim yap (M, L ya da W)", "Make a selection first"));
    if (a === "selmove") edSelToLayer(false), ED.cur--;   // nesne yeni katmanda, alttakinin yeri doldurulacak
    const m = document.createElement("canvas"); m.width = ED.W; m.height = ED.H; const g = m.getContext("2d");
    const sel = a === "selmove" ? ED._lastSel : ED.sel;
    g.fillStyle = "#fff"; if (sel?.path) g.fill(sel.path);
    // kenarlari biraz genislet: LaMa daha temiz doldurur
    const m2 = document.createElement("canvas"); m2.width = ED.W; m2.height = ED.H; const g2 = m2.getContext("2d"); g2.filter = "blur(6px)"; g2.drawImage(m, 0, 0); g2.filter = "none";
    const d = g2.getImageData(0, 0, ED.W, ED.H); for (let i = 3; i < d.data.length; i += 4) d.data[i] = d.data[i] > 10 ? 255 : 0; g2.putImageData(d, 0, 0);
    await healApply(m2);
    if (a === "selmove") { ED.cur++; ED.tool = "move"; edOpt(); edLayersUi(); toast(edL("Nesneyi sürükle", "Drag the object")); }
  } else if (a === "upscale") {
    if (ED.W * ED.H > 4096 * 4096 / 4) return toast(edL("Görsel zaten çok büyük", "Image already large"));
    const r = await aiCall("upscale", edFlatten().toDataURL("image/png"), "", null, edL("4x büyütülüyor…", "Upscaling 4x…")); if (!r) return;
    const img = await loadImg(r); edSnapAll(edL("4x büyüt", "Upscale"));
    edNew(img.width, img.height, ED.name + " 4x", ED.path); ED.layers[0].c.getContext("2d").drawImage(img, 0, 0); edFit(); edLayersUi(); edRender();
  } else if (a.startsWith("vec-")) {
    edBusy(edL("Vektöre çevriliyor…", "Vectorizing…"));
    const src = l.text ? edFlatten() : l.c;
    const r = await api.editor_vectorize(ED.path || "", ED.name, src.toDataURL("image/png"), a.slice(4)); edBusy("");
    if (!r?.ok) return toast(edL("Olmadı: ", "Failed: ") + (r?.error || ""));
    const img = await loadImg("data:image/svg+xml;base64," + btoa(unescape(encodeURIComponent(r.svg))));
    edLayerAdd(edL("Vektör önizleme", "Vector preview")); cl().c.getContext("2d").drawImage(img, 0, 0, src.width, src.height); edLayersUi(); edRender();
    toast(edL("SVG kaydedildi: ", "SVG saved: ") + r.path.split(/[\\/]/).pop());
  } else if (a === "gif" || a === "mp4") {
    const frames = ED.layers.filter((q) => q.vis).map((q) => { const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H; const g = c.getContext("2d"); g.globalAlpha = q.op; g.drawImage(q.c, q.x, q.y); return c.toDataURL("image/png"); });
    if (frames.length < 2) return toast(edL("En az 2 görünür katman gerekli (her biri bir kare)", "Need at least 2 visible layers"));
    edBusy(edL("Animasyon yapılıyor…", "Building animation…"));
    const r = await api.editor_gif(ED.path || "", ED.name, frames, +($("#aiMs")?.value || 120), a); edBusy("");
    toast(r?.ok ? edL("Kaydedildi: ", "Saved: ") + r.path.split(/[\\/]/).pop() : edL("Olmadı", "Failed"));
  } else if (a === "face") {
    if (l.text) return toast(edL("Resim katmanı seç", "Pick an image layer"));
    const r = await aiCall("face", layerDataUrl(l), "", null, edL("Yüzler düzeltiliyor…", "Restoring faces…")); if (!r) return;
    const img = await loadImg(r); edSnap(edL("Yüz düzelt", "Restore faces")); const g = l.c.getContext("2d"); g.clearRect(0, 0, l.c.width, l.c.height); g.drawImage(img, 0, 0, l.c.width, l.c.height); edLayerThumb(ED.cur); edRender();
  } else if (a === "webp-sheet") {
    const frames = ED.layers.filter((q) => q.vis).map((q) => { const c = document.createElement("canvas"); c.width = ED.W; c.height = ED.H; const g = c.getContext("2d"); g.globalAlpha = q.op; g.drawImage(q.c, q.x, q.y); return c.toDataURL("image/png"); });
    if (frames.length < 2) return toast(edL("En az 2 görünür katman gerekli", "Need at least 2 visible layers"));
    edBusy(edL("Hareketli WebP üretiliyor…", "Exporting animated WebP…"));
    const saved = [];
    for (let i = 0; i < frames.length; i++) {
      const s = await api.pic_save_temp_png(frames[i], `webp_f_${i}`);
      if (s?.ok) saved.push(s.path);
    }
    const r = await api.pic_export_webp_sheet(saved, "", +($("#aiMs")?.value || 140));
    edBusy("");
    toast(r?.ok ? edL("WebP kaydedildi: ", "WebP saved: ") + r.path.split(/[\\/]/).pop() : (r?.error || edL("Olmadı", "Failed")));
  } else if (a.startsWith("pro-")) {
    const tmp = await api.pic_save_temp_png(edFlatten().toDataURL("image/png"), (ED.name || "kami_pic").replace(/\.[^.]+$/, ""));
    if (!tmp?.ok) return toast(edL("Geçici görsel yazılamadı", "Could not stage image"));
    const srcPath = tmp.path;
    const loadResultToNewDoc = async (outPath, title) => {
      const idata = await api.image_data(outPath);
      if (!idata?.ok) return toast(edL("Çıktı açılamadı", "Could not open output"));
      const im = await loadImg(idata.url);
      edSnapAll(title); edNew(im.width, im.height, title, outPath);
      ED.layers[0].c.getContext("2d").drawImage(im, 0, 0); edFit(); edLayersUi(); edRender();
    };
    if (a === "pro-contact-shadow") {
      edBusy(edL("Temas gölgesi & Stüdyo 1200px…", "Contact shadow & Studio 1200px…"));
      const r = await api.pic_contact_shadow(srcPath, "#FFFFFF", 0.12, 1200, true, "");
      edBusy("");
      if (r?.ok) { await loadResultToNewDoc(r.path, ED.name + " · E-Com"); toast(edL("Temas gölgeli stüdyo çıktısı hazır", "Studio pack ready")); }
      else toast(r?.error || edL("Olmadı", "Failed"));
    } else if (a === "pro-freq-sep") {
      edBusy(edL("Frekans ayrıştırılıyor…", "Separating frequencies…"));
      const r = await api.pic_freq_sep(srcPath, 4.0);
      edBusy("");
      if (r?.ok) {
        const lowD = await api.image_data(r.low_path), highD = await api.image_data(r.high_path);
        if (lowD?.ok) { const imL = await loadImg(lowD.url); edLayerAdd(edL("Düşük Frekans (Renk)", "Low Freq (Color)")); cl().c.getContext("2d").drawImage(imL, 0, 0); }
        if (highD?.ok) { const imH = await loadImg(highD.url); edLayerAdd(edL("Yüksek Frekans (Doku)", "High Freq (Texture)")); cl().c.getContext("2d").drawImage(imH, 0, 0); }
        edLayersUi(); edRender(); toast(edL("Düşük/Yüksek katmanlar eklendi", "Low/High layers added"));
      } else toast(r?.error || edL("Olmadı", "Failed"));
    } else if (a === "pro-oklch") {
      const r = await api.pic_oklch_palette(srcPath, 6);
      const box = $("#proPaletteOut");
      if (r?.ok && box) {
        box.innerHTML = (r.colors || []).map((c) => `<span title="${c.hex} (${c.css || ""})" style="display:inline-flex;align-items:center;gap:4px;padding:2px 6px;border-radius:6px;background:#161026;border:1px solid #2E2346;font-size:10px"><i style="width:12px;height:12px;border-radius:3px;background:${c.hex};display:inline-block"></i>${c.hex}</span>`).join("");
        toast(edL("OKLCH renk paleti çıkarıldı", "OKLCH palette extracted"));
      }
    } else if (a === "pro-wm-embed") {
      const wmTxt = (typeof prompt === "function" ? prompt(edL("Görünmez telif imzası metni:", "Watermark text:"), "Kami Picture © 2026") : "") || "Kami Picture © 2026";
      const r = await api.pic_watermark_embed(srcPath, wmTxt, "");
      if (r?.ok) { await loadResultToNewDoc(r.path, ED.name + " · WM"); toast(edL("Telif imzası gömüldü", "Watermark embedded")); }
      else toast(r?.error || edL("Olmadı", "Failed"));
    } else if (a === "pro-wm-read") {
      const targetPath = (ED.path && String(ED.path)) || srcPath;
      const r = await api.pic_watermark_read(targetPath);
      toast(r?.ok ? edL("İmza: ", "Watermark: ") + r.text : (r?.error || edL("İmza bulunamadı", "No watermark found")));
    } else if (a === "pro-send-studio") {
      const r = await api.pic_send_to_studio(srcPath, "Gorseller");
      toast(r?.ok ? edL("Studio Medya/Gorseller'e gönderildi: ", "Sent to Studio: ") + r.name : (r?.error || edL("Olmadı", "Failed")));
    } else if (a === "pro-macro-run") {
      const mid = $("#proMacroSel")?.value;
      if (!mid) return toast(edL("Makro seç", "Pick a macro"));
      edBusy(edL("Makro çalışıyor…", "Running macro…"));
      const r = await api.pic_macro_run(srcPath, mid, "");
      edBusy("");
      if (r?.ok && r.path) { await loadResultToNewDoc(r.path, ED.name + " · " + mid); toast(edL("Makro tamamlandı", "Macro finished")); }
      else toast(r?.error || edL("Olmadı", "Failed"));
    }
  }
}

// ---------------------------------------------------------------- editor kancalari
window.edOptExtra = (t) => {
  if (t === "heal") return `<label>${edL("Boyut", "Size")} <input type="range" min="4" max="400" value="${ED.size}" data-o="size"></label><span>${edL("Silinecek yeri boya, bırakınca yapay zekâ doldurur", "Paint over it; AI fills on release")}</span>`;
  if (t === "magic") return `<span>${edL("Nesneye tıkla · Shift+tık ekle · Alt+tık çıkar", "Click an object · Shift add · Alt subtract")}</span><button data-x="selnone">${edL("Kaldır", "None")}</button><button data-x="sellayer">${edL("Katmana al", "To layer")}</button><button data-ai="selfill">${edL("Sil ve doldur", "Delete & fill")}</button>`;
  if (t === "clone") return `<label>${edL("Boyut", "Size")} <input type="range" min="2" max="300" value="${ED.size}" data-o="size"></label><label>${edL("Opaklık", "Opacity")} <input type="range" min="5" max="100" value="${ED.opacity * 100}" data-o="opacity"></label><span>${edL("Alt+tık: kaynak", "Alt+click: source")}</span>`;
  if (t === "liquify") return `<select data-liq="mode"><option value="push">${edL("İt", "Push")}</option><option value="bloat">${edL("Şişir", "Bloat")}</option><option value="pinch">${edL("Daralt", "Pinch")}</option><option value="twirl">${edL("Döndür", "Twirl")}</option></select><label>${edL("Boyut", "Size")} <input type="range" min="10" max="400" value="${ED.size}" data-o="size"></label><label>${edL("Güç", "Strength")} <input type="range" min="5" max="100" value="${ED.opacity * 100}" data-o="opacity"></label>`;
  if (t === "ai") { setTimeout(aiCard, 0); return `<span>${edL("Sağdaki karttan seç", "Pick in the card")}</span>`; }
  return null;
};
const _edDown = edDown, _edMove = edMove, _edUp = edUp;
edDown = function (e) {   // eslint-disable-line no-func-assign
  if (e.button === 2 || e.button === 1 || ED.space) return _edDown(e);
  const t = ED.tool, [x, y] = toDoc(e.offsetX, e.offsetY);
  if (t === "heal") { $("#edView").setPointerCapture(e.pointerId); healStart(x, y); edDrag = { t }; return; }
  if (t === "magic") { magicClick(x, y, e.altKey, e.shiftKey || e.altKey); return; }
  if (t === "clone") { if (cloneStart(x, y, e.altKey)) { $("#edView").setPointerCapture(e.pointerId); edDrag = { t }; } return; }
  if (t === "liquify") { if (liqStart(x, y)) { $("#edView").setPointerCapture(e.pointerId); edDrag = { t }; } return; }
  return _edDown(e);
};
edMove = function (e) {   // eslint-disable-line no-func-assign
  const t = edDrag?.t;
  if (t === "heal" || t === "clone" || t === "liquify") {
    const [x, y] = toDoc(e.offsetX, e.offsetY); ED.hover = [x, y];
    if (t === "heal") healMove(x, y); else if (t === "clone") cloneMove(x, y); else liqMove(x, y);
    return;
  }
  return _edMove(e);
};
edUp = function (e) {   // eslint-disable-line no-func-assign
  const t = edDrag?.t;
  if (t === "heal") { edDrag = null; healApply(ED.overlay); return; }
  if (t === "clone" || t === "liquify") { edDrag = null; edLayerThumb(ED.cur); edRender(); return; }
  return _edUp(e);
};
document.addEventListener("click", (e) => { const b = e.target.closest("[data-ai]"); if (b && ED.on) { ED._lastSel = ED.sel; aiAction(b.dataset.ai); } });
document.addEventListener("change", (e) => { if (e.target.dataset.liq) AI.liq.mode = e.target.value; });
const _edSelToLayer = edSelToLayer;
edSelToLayer = function (cut) { ED._lastSel = ED.sel; return _edSelToLayer(cut); };   // eslint-disable-line no-func-assign
