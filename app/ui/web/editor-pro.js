// Kami Picture Pro (v1.30): katman maskesi, tahribatsiz ayar katmanlari, gecmis paneli, toplu islem.
"use strict";
(() => {
  const L2 = (tr, en) => edL(tr, en);
  const ADJ0 = { bright: 0, contrast: 0, sat: 0, hue: 0, temp: 0, vib: 0, expo: 0, blur: 0, sharp: 0, grain: 0, vign: 0, lvIn0: 0, lvIn1: 255, lvGamma: 1 };
  const css = document.createElement("style");
  css.textContent = `
  .ed-ly .badges{position:absolute;top:8px;left:8px;display:flex;gap:3px}.ed-ly .badges i{font-style:normal;font-size:10px;background:#09060fe6;border:1px solid #8B5CF6;color:#C4B5FD;padding:1px 5px;border-radius:4px;font-weight:600;letter-spacing:.3px}
  .ed-ly .badges i.edit{background:#2EE6A6;color:#06120d;border-color:#2EE6A6}
  .ed-addly.pro{margin-top:4px;display:flex;flex-wrap:wrap;gap:5px;width:auto;flex-direction:row}
  .ed-addly.pro button,.ed-addly.pro select{flex:0 0 auto;border:1px solid #3a2a5a;background:#161024;color:#C4B5FD;border-radius:6px;padding:4px 8px;font:inherit;font-size:11px;cursor:pointer;transition:border-color .15s,background .15s,color .15s}
  .ed-addly.pro button:hover,.ed-addly.pro select:hover{border-color:#9D6BFF;background:#1f1633;color:#fff}
  #edHist{position:absolute;right:14px;top:64px;width:246px;max-height:60vh;overflow:auto;background:rgba(13,10,20,.94);backdrop-filter:blur(12px);border:1px solid #2A2140;border-radius:12px;z-index:40;padding:10px;font-size:12px;box-shadow:0 16px 40px rgba(0,0,0,.55)}
  #edHist[hidden]{display:none}#edHist h5{margin:2px 4px 8px;font-size:10px;letter-spacing:2px;text-transform:uppercase;color:#8E86A3;display:flex;justify-content:space-between}
  #edHist div{position:relative;padding:6px 10px 6px 20px;border-radius:7px;cursor:pointer;color:#EDE9F6;transition:background .12s}
  #edHist div::before{content:"";position:absolute;left:8px;top:50%;width:6px;height:6px;border-radius:50%;transform:translateY(-50%);background:#4B3E6B}
  #edHist div:hover{background:#1d1530}#edHist div.cur{background:linear-gradient(90deg,#6D28D9,#7C3AED);font-weight:600}
  #edHist div.cur::before{background:#2EE6A6;box-shadow:0 0 8px #2EE6A6}
  #edHist div.fut{color:#6E6684;opacity:.75}
  #edMaskHud{position:absolute;left:50%;top:60px;transform:translateX(-50%);background:rgba(46,230,166,.95);color:#06120d;font-weight:700;padding:6px 16px;border-radius:999px;z-index:40;font-size:12px;box-shadow:0 8px 24px rgba(46,230,166,.3);letter-spacing:.2px}
  #edMaskHud[hidden]{display:none}
  #edBatch{position:fixed;inset:0;background:rgba(5,3,10,.78);backdrop-filter:blur(6px);z-index:90;display:flex;align-items:center;justify-content:center}#edBatch[hidden]{display:none}
  #edBatch .bx{width:min(660px,94vw);max-height:90vh;overflow:auto;background:#110D19;border:1px solid #2A2140;border-radius:16px;padding:20px 22px;color:#EDE9F6;box-shadow:0 24px 64px rgba(0,0,0,.65)}
  #edBatch h3{margin:0 0 4px;font-size:17px}#edBatch p{color:#8E86A3;margin:0 0 12px;font-size:12px;line-height:1.45}
  #edBatch .b-step{background:#171123;border:1px solid #261D3B;border-radius:10px;padding:10px 12px;margin-bottom:10px}
  #edBatch .b-step-h{font-size:10px;letter-spacing:1.6px;text-transform:uppercase;color:#9D6BFF;font-weight:700;margin-bottom:6px}
  #edBatch label{display:flex;gap:8px;align-items:center;margin:7px 0;font-size:13px;flex-wrap:wrap}#edBatch select,#edBatch input[type=number],#edBatch input[type=text]{background:#0b0912;border:1px solid #2A2140;color:#EDE9F6;border-radius:7px;padding:6px 9px;font:inherit;font-size:12px}
  #edBatch .row{display:flex;gap:8px;align-items:center;flex-wrap:wrap}#edBatch button{border:1px solid #2A2140;background:#1d1530;color:#EDE9F6;border-radius:8px;padding:8px 14px;cursor:pointer;font:inherit;font-size:12px;transition:border-color .15s,background .15s}
  #edBatch button:hover{border-color:#9D6BFF;background:#261b40}
  #edBatch button.pri{background:#6D28D9;border-color:#8B5CF6;font-weight:600}#edBatch button.pri:hover{background:#7C3AED}
  #edBatch .prog{height:7px;background:#241B33;border-radius:4px;overflow:hidden;margin-top:10px}#edBatch .prog i{display:block;height:100%;width:0;background:linear-gradient(90deg,#7C3AED,#2EE6A6);transition:width .2s}
  #edBatch .files{font-size:11px;color:#C4B5FD;max-height:84px;overflow:auto;margin:6px 0 0;line-height:1.5}`;
  document.head.appendChild(css);

  // ---------------------------------------------------------------- maske
  function maskNew(fromSel) {
    const l = cl(); if (l.adj && !fromSel && l.mask) return;
    if (l.mask) { toast(L2("Bu katmanda zaten maske var", "Layer already has a mask")); return; }
    edSnapAll(L2("Maske ekle", "Add mask"));
    const m = document.createElement("canvas"); m.width = l.c.width; m.height = l.c.height; const g = m.getContext("2d");
    if (fromSel && ED.sel?.path) { g.fillStyle = "#000"; g.fillRect(0, 0, m.width, m.height); g.save(); g.translate(-l.x, -l.y); g.fillStyle = "#fff"; g.fill(ED.sel.path, ED.sel.even ? "evenodd" : "nonzero"); g.restore(); }
    else { g.fillStyle = "#fff"; g.fillRect(0, 0, m.width, m.height); }
    l.mask = m; l._maskV = 1; edBump(); edLayersUi(); edRender();
    toast(L2("Maske eklendi · K ile maskeyi boya (beyaz göster, siyah gizle)", "Mask added · press K to paint it (white shows, black hides)"));
  }
  function maskEdit(on = !cl()._swapped) {
    const l = cl(); if (!l.mask) return;
    if (!!l._swapped === on) return;
    [l.c, l.mask] = [l.mask, l.c]; l._swapped = on; l._maskV = (l._maskV || 0) + 1;
    if (on) { ED._prevColor = ED.color; ED.color = "#000000"; ED.tool = "brush"; edOpt(); }
    else if (ED._prevColor) { ED.color = ED._prevColor; edOpt(); }
    document.getElementById("edMaskHud").hidden = !on;
    edBump(); edLayersUi(); edRender();
  }
  function maskInvert() {
    const l = cl(); if (!l.mask) return;
    const mc = l._swapped ? l.c : l.mask;
    edSnapAll(L2("Maskeyi ters çevir", "Invert mask"));
    const g = mc.getContext("2d"), d = g.getImageData(0, 0, mc.width, mc.height);
    for (let i = 0; i < d.data.length; i += 4) { d.data[i] = 255 - d.data[i]; d.data[i + 1] = 255 - d.data[i + 1]; d.data[i + 2] = 255 - d.data[i + 2]; }
    g.putImageData(d, 0, 0); l._maskV = (l._maskV || 0) + 1; edBump(); edRender();
  }
  function maskApply(del) {   // del=false: maskeyi alfaya pisir; del=true: maskeyi sil
    const l = cl(); if (!l.mask) return;
    if (l._swapped) maskEdit(false);
    edSnapAll(del ? L2("Maskeyi sil", "Delete mask") : L2("Maskeyi uygula", "Apply mask"));
    if (!del && !l.adj) { const t = edMasked(l, l.c); const g = l.c.getContext("2d"); g.clearRect(0, 0, l.c.width, l.c.height); g.drawImage(t, 0, 0); }
    l.mask = null; l._mA = null; edBump(); edLayersUi(); edRender();
  }

  // ---------------------------------------------------------------- ayar katmani
  function adjNew(kind) {
    edSnapAll(L2("Ayar katmanı", "Adjustment layer"));
    const names = { curves: L2("Eğriler", "Curves"), levels: L2("Seviyeler", "Levels"), hue: L2("Ton/Doygunluk", "Hue/Saturation"), color: L2("Renk", "Colour"), bw: L2("Siyah-beyaz", "Black & white") };
    const l = edLayer("◐ " + (names[kind] || L2("Ayar", "Adjustment")));   // belge boyutu: maske de belge boyutunda
    l.adj = { kind, a: kind === "bw" ? { sat: -100 } : {}, cv: {} };
    ED.layers.splice(ED.cur + 1, 0, l); ED.cur++;
    edBump(); edLayersUi(); ED.tool = "adjust"; edOpt(); edCard(); edRender();
  }
  const _card = edCard;
  window.edCard = edCard = function () {
    const l = cl();
    if (l?.adj) {   // ayar katmani secili: kaydiricilar onun degerlerini gostersin
      Object.assign(ADJ, ADJ0, l.adj.a || {});
      for (const k of ["rgb", "r", "g", "b"]) CURVE[k] = (l.adj.cv?.[k] || [[0, 0], [255, 255]]).map((q) => [...q]);
    }
    _card.apply(this, arguments);
    if (l?.adj) {
      const c = document.getElementById("edCard"), pb = c.querySelector('[data-c="apply"]');
      if (pb) pb.textContent = L2("Ayar katmanına kaydet", "Save to adjustment layer");
      const note = document.createElement("p"); note.style.cssText = "color:#2EE6A6;margin:8px 0 0";
      note.textContent = L2("Tahribatsız: altındaki tüm katmanlara uygulanır, istediğin an değiştir ya da maskele.", "Non-destructive: affects all layers below; change or mask it any time.");
      c.appendChild(note);
    }
  };
  const _prev = edAdjPreview;
  window.edAdjPreview = edAdjPreview = function () {
    const l = cl();
    if (!l?.adj) return _prev.apply(this, arguments);
    l.adj.a = { ...ADJ }; l.adj.cv = { rgb: CURVE.rgb.map((q) => [...q]), r: CURVE.r.map((q) => [...q]), g: CURVE.g.map((q) => [...q]), b: CURVE.b.map((q) => [...q]) };
    edRender();
  };
  const _apply = edAdjApply;
  window.edAdjApply = edAdjApply = function () {
    const l = cl();
    if (!l?.adj) return _apply.apply(this, arguments);
    edSnapAll(L2("Ayar katmanı", "Adjustment layer"));
    edAdjPreview(); ED.dirty = true; toast(L2("Ayar katmanı güncellendi", "Adjustment layer updated"));
  };
  const _reset = edAdjReset;
  window.edAdjReset = edAdjReset = function (redraw = true) {
    _reset.call(this, redraw);
    const l = cl(); if (l?.adj && redraw) { l.adj.a = {}; l.adj.cv = {}; edRender(); }
  };
  const _merge = edLayerMergeDown;
  window.edLayerMergeDown = edLayerMergeDown = function () {
    const l = cl();
    if (!l || ED.cur === 0 || !(l.adj || l.mask)) { _merge.apply(this, arguments); edBump(); return; }
    if (l._swapped) maskEdit(false);
    if (!l.adj) {   // maskeli normal katman: maskeyi alfaya pisir, sonra olagan birlestirme
      const t = edMasked(l, l.c), g = l.c.getContext("2d"); g.clearRect(0, 0, l.c.width, l.c.height); g.drawImage(t, 0, 0);
      l.mask = null; l._mA = null; _merge.apply(this, arguments); edBump(); return;
    }
    // ayar katmani: yalniz hemen alttaki katmanin piksellerine uygulanir (maske ve opaklik dahil), sonra kaldirilir
    edSnapAll(L2("Ayarı aşağı uygula", "Apply adjustment down"));
    const below = ED.layers[ED.cur - 1];
    const doc = document.createElement("canvas"); doc.width = ED.W; doc.height = ED.H; const dg = doc.getContext("2d"); dg.drawImage(below.c, below.x, below.y);
    const a = Object.assign({}, ADJ0, l.adj.a || {}), cv = Object.assign({ rgb: [[0, 0], [255, 255]], r: [[0, 0], [255, 255]], g: [[0, 0], [255, 255]], b: [[0, 0], [255, 255]] }, l.adj.cv || {});
    let adjd = document.createElement("canvas"); adjd.width = ED.W; adjd.height = ED.H; const ag = adjd.getContext("2d");
    ag.putImageData(edAdjustData(dg.getImageData(0, 0, ED.W, ED.H), a, cv), 0, 0);
    if (l.mask) adjd = edMasked(l, adjd);
    dg.globalAlpha = l.op; dg.globalCompositeOperation = "source-atop"; dg.drawImage(adjd, 0, 0);
    const bg = below.c.getContext("2d"); bg.clearRect(0, 0, below.c.width, below.c.height); bg.drawImage(doc, -below.x, -below.y);
    ED.layers.splice(ED.cur, 1); ED.cur--; edBump(); edLayersUi(); edRender();
  };

  // ---------------------------------------------------------------- katman seridi ek dugmeler + rozetler
  const _lui = edLayersUi;
  window.edLayersUi = edLayersUi = function () {
    _lui.apply(this, arguments);
    document.querySelectorAll("#edLayers .ed-ly").forEach((el) => {
      const l = ED.layers[+el.dataset.i]; if (!l) return;
      const b = [];
      if (l.adj) b.push("<i>◐</i>");
      if (l.mask) b.push(`<i class="${l._swapped ? "edit" : ""}">${l._swapped ? L2("maske ✎", "mask ✎") : L2("maske", "mask")}</i>`);
      if (b.length) { const d = document.createElement("div"); d.className = "badges"; d.innerHTML = b.join(""); el.appendChild(d); }
      if (l.adj) { const cv = el.querySelector("canvas"), g = cv.getContext("2d"); g.fillStyle = "#1a1325"; g.fillRect(0, 0, 116, 72); g.fillStyle = "#C4B5FD"; g.font = "28px sans-serif"; g.textAlign = "center"; g.fillText("◐", 58, 46); }
    });
    const row = document.querySelector("#edLayers .row"); if (!row || row.querySelector(".ed-addly.pro")) return;
    const l = cl(), pro = document.createElement("div"); pro.className = "ed-addly pro";
    pro.innerHTML = (l?.mask
      ? `<button data-pro="medit">${l._swapped ? L2("✓ Maskeden çık", "✓ Exit mask") : L2("✎ Maskeyi boya (K)", "✎ Paint mask (K)")}</button><button data-pro="minv">${L2("Ters çevir", "Invert")}</button><button data-pro="mapply">${L2("Uygula", "Apply")}</button><button data-pro="mdel">${L2("Maskeyi sil", "Delete mask")}</button>`
      : `<button data-pro="mask">${L2("+ Maske", "+ Mask")}</button><button data-pro="masksel" title="${L2("Seçim beyaz, dışı siyah", "Selection white, rest black")}">${L2("Seçimden maske", "Mask from selection")}</button>`) +
      `<select data-pro="adj"><option value="">${L2("+ Ayar katmanı…", "+ Adjustment layer…")}</option><option value="curves">${L2("Eğriler", "Curves")}</option><option value="levels">${L2("Seviyeler", "Levels")}</option><option value="hue">${L2("Ton/Doygunluk", "Hue/Saturation")}</option><option value="color">${L2("Renk / ışık", "Colour / light")}</option><option value="bw">${L2("Siyah-beyaz", "Black & white")}</option></select>` +
      `<button data-pro="hist">${L2("Geçmiş (H)", "History (H)")}</button><button data-pro="batch">${L2("Toplu işlem…", "Batch…")}</button>`;
    row.appendChild(pro);
  };
  document.addEventListener("click", (e) => {
    const b = e.target.closest("[data-pro]"); if (!b || b.tagName === "SELECT") return;
    e.stopPropagation();
    const k = b.dataset.pro;
    if (k === "mask") maskNew(false); else if (k === "masksel") maskNew(true); else if (k === "medit") maskEdit();
    else if (k === "minv") maskInvert(); else if (k === "mapply") maskApply(false); else if (k === "mdel") maskApply(true);
    else if (k === "hist") histToggle(); else if (k === "batch") batchOpen();
  }, true);
  document.addEventListener("change", (e) => { const s = e.target.closest('select[data-pro="adj"]'); if (s && s.value) { adjNew(s.value); s.value = ""; } }, true);

  // ---------------------------------------------------------------- gecmis paneli
  function histEl() {
    let h = document.getElementById("edHist");
    if (!h) { h = document.createElement("div"); h.id = "edHist"; h.hidden = true; (document.getElementById("ed") || document.body).appendChild(h); }
    let m = document.getElementById("edMaskHud");
    if (!m) { m = document.createElement("div"); m.id = "edMaskHud"; m.hidden = true; m.textContent = L2("MASKE DÜZENLENİYOR · beyaz göster, siyah gizle · K çık · X siyah/beyaz", "EDITING MASK · white shows, black hides · K exit · X black/white"); (document.getElementById("ed") || document.body).appendChild(m); }
    return h;
  }
  function histRender() {
    const h = histEl(); if (h.hidden) return;
    const past = ED.undo.map((s) => s.label || "?"), fut = [...ED.redo].reverse().map((s) => s.label || "?");
    h.innerHTML = `<h5>${L2("Geçmiş", "History")} · ${past.length}</h5><div data-h="0" class="${past.length ? "" : "cur"}">◇ ${L2("Başlangıç", "Start")}</div>` +
      past.map((t, i) => `<div data-h="${i + 1}" class="${i === past.length - 1 ? "cur" : ""}">${esc(t)}</div>`).join("") +
      fut.map((t, i) => `<div data-h="${past.length + i + 1}" class="fut">${esc(t)}</div>`).join("");
  }
  function histToggle() { const h = histEl(); h.hidden = !h.hidden; histRender(); }
  document.addEventListener("click", (e) => {
    const it = e.target.closest("#edHist [data-h]"); if (!it) return;
    const target = +it.dataset.h; let n = ED.undo.length;
    while (n > target && ED.undo.length) { edUndo(); n--; }
    while (n < target && ED.redo.length) { edRedo(); n++; }
    histRender();
  });
  let lastSig = "";
  setInterval(() => { if (!ED.on || document.hidden) return; const sig = ED.undo.length + "|" + ED.redo.length; if (sig !== lastSig) { lastSig = sig; histRender(); } }, 500);

  document.addEventListener("keydown", (e) => {
    if (!ED.on || e.target.matches?.("input, textarea, select, [contenteditable=true]") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "h" || e.key === "H") { histToggle(); e.preventDefault(); }
    else if ((e.key === "k" || e.key === "K") && cl()?.mask) { maskEdit(); e.preventDefault(); e.stopImmediatePropagation(); }
    else if (e.key === "x" || e.key === "X") { if (cl()?._swapped) { ED.color = ED.color.toLowerCase() === "#000000" ? "#ffffff" : "#000000"; edOpt(); e.preventDefault(); } }
  }, true);

  // ---------------------------------------------------------------- toplu islem
  const B = { files: [], out: "" };
  function batchOpen() {
    let d = document.getElementById("edBatch");
    if (!d) { d = document.createElement("div"); d.id = "edBatch"; document.body.appendChild(d); }
    d.hidden = false;
    d.innerHTML = `<div class="bx"><h3>${L2("Toplu işlem", "Batch processing")}</h3>
      <p>${L2("Aynı görünümü, boyutu ve biçimi bir sürü görsele tek seferde uygula. Asıllar değişmez; sonuçlar seçtiğin klasöre (ya da yanlarına 'Kami toplu' klasörüne) yazılır.", "Apply the same look, size and format to many images at once. Originals are untouched.")}</p>
      <div class="b-step"><div class="b-step-h">1 · ${L2("Görseller", "Images")}</div>
        <div class="row"><button id="bPick">📁 ${L2("Görselleri seç", "Pick images")}</button><span id="bCount"></span></div><div class="files" id="bFiles"></div>
      </div>
      <div class="b-step"><div class="b-step-h">2 · ${L2("Görünüm, boyut ve filigran", "Look, size & watermark")}</div>
        <label>${L2("Görünüm", "Look")} <select id="bLook"><option value="">${L2("— yok —", "— none —")}</option><option value="__cur">${L2("Şu anki ayarlar (Ayarlar kartı)", "Current adjustment settings")}</option>${PRESETS.map((p, i) => `<option value="${i}">${esc(p.n)}</option>`).join("")}</select></label>
        <label>${L2("Boyut", "Size")} <select id="bFit"><option value="">${L2("Değiştirme", "Keep")}</option><option value="long">${L2("Uzun kenar", "Long edge")}</option><option value="square">${L2("Kare (doldur)", "Square (cover)")}</option><option value="pad">${L2("Kare (beyaz kenar)", "Square (white pad)")}</option></select> <input id="bPx" type="number" min="64" max="8000" value="1080"> px</label>
        <label>${L2("Filigran", "Watermark")} <input id="bWm" type="text" placeholder="${L2("boş = yok", "empty = none")}" style="flex:1"> <select id="bWmPos"><option value="br">↘</option><option value="bl">↙</option><option value="c">●</option><option value="tr">↗</option></select></label>
      </div>
      <div class="b-step"><div class="b-step-h">3 · ${L2("Biçim ve çıktı", "Format & output")}</div>
        <label>${L2("Biçim", "Format")} <select id="bFmt"><option value="jpg">JPG</option><option value="png">PNG</option><option value="webp">WEBP</option></select> ${L2("Kalite", "Quality")} <input id="bQ" type="number" min="40" max="100" value="92"> <span>${L2("Ad eki", "Suffix")}</span><input id="bSfx" type="text" value="_kami" style="width:90px"></label>
        <div class="row"><button id="bDir">📂 ${L2("Çıktı klasörü", "Output folder")}</button><span id="bOut" style="font-size:12px;color:#8E86A3">${L2("varsayılan: yanlarına 'Kami toplu'", "default: 'Kami toplu' next to each")}</span></div>
      </div>
      <div class="prog"><i id="bBar"></i></div><p id="bSt" style="margin-top:8px"></p>
      <div class="row" style="justify-content:flex-end"><button id="bClose">${L2("Kapat", "Close")}</button><button class="pri" id="bGo">${L2("Başlat", "Start")}</button></div></div>`;
    const show = () => { d.querySelector("#bCount").textContent = B.files.length ? L2(`${B.files.length} görsel`, `${B.files.length} images`) : ""; d.querySelector("#bFiles").textContent = B.files.map((f) => f.split(/[\\/]/).pop()).join(" · "); };
    show();
    d.querySelector("#bPick").onclick = async () => { B.files = (await api.pic_batch_pick()) || []; show(); };
    d.querySelector("#bDir").onclick = async () => { B.out = (await api.pic_batch_dir()) || ""; d.querySelector("#bOut").textContent = B.out || L2("varsayılan", "default"); };
    d.querySelector("#bClose").onclick = () => { d.hidden = true; };
    d.querySelector("#bGo").onclick = () => batchRun(d);
  }
  async function batchRun(d) {
    if (!B.files.length) return toast(L2("Önce görselleri seç", "Pick images first"));
    const look = d.querySelector("#bLook").value, fit = d.querySelector("#bFit").value, px = +d.querySelector("#bPx").value || 1080;
    const wm = d.querySelector("#bWm").value.trim(), wmPos = d.querySelector("#bWmPos").value, fmt = d.querySelector("#bFmt").value;
    const q = Math.max(0.4, Math.min(1, (+d.querySelector("#bQ").value || 92) / 100)), sfx = d.querySelector("#bSfx").value;
    let a = null, cv = null;
    if (look === "__cur") { a = { ...ADJ }; cv = { rgb: CURVE.rgb, r: CURVE.r, g: CURVE.g, b: CURVE.b }; }
    else if (look !== "") { const p = PRESETS[+look]; a = { ...ADJ0, ...(p.a || {}) }; cv = { rgb: [[0, 0], [255, 255]], r: [[0, 0], [255, 255]], g: [[0, 0], [255, 255]], b: [[0, 0], [255, 255]], ...(p.c || {}) }; }
    const go = d.querySelector("#bGo"); go.disabled = true;
    let ok = 0, fail = 0;
    for (let i = 0; i < B.files.length; i++) {
      const f = B.files[i];
      d.querySelector("#bSt").textContent = `${i + 1}/${B.files.length} · ${f.split(/[\\/]/).pop()}`;
      try {
        const r = await api.image_data(f, 12000); if (!r?.ok) throw new Error("okunamadi");
        const img = await new Promise((res, rej) => { const im = new Image(); im.onload = () => res(im); im.onerror = rej; im.src = r.url; });
        let W = img.naturalWidth, H = img.naturalHeight, dx = 0, dy = 0, dw = W, dh = H, cw = W, ch = H;
        if (fit === "long") { const k = px / Math.max(W, H); cw = dw = Math.round(W * k); ch = dh = Math.round(H * k); }
        else if (fit === "square") { const k = px / Math.min(W, H); dw = Math.round(W * k); dh = Math.round(H * k); cw = ch = px; dx = (px - dw) / 2; dy = (px - dh) / 2; }
        else if (fit === "pad") { const k = px / Math.max(W, H); dw = Math.round(W * k); dh = Math.round(H * k); cw = ch = px; dx = (px - dw) / 2; dy = (px - dh) / 2; }
        const c = document.createElement("canvas"); c.width = cw; c.height = ch; const g = c.getContext("2d");
        if (fit === "pad" || fmt === "jpg") { g.fillStyle = "#fff"; g.fillRect(0, 0, cw, ch); }
        g.imageSmoothingQuality = "high"; g.drawImage(img, dx, dy, dw, dh);
        if (a) g.putImageData(edAdjustData(g.getImageData(0, 0, cw, ch), a, cv), 0, 0);
        if (a?.sharp) g.putImageData(edConvolve(g.getImageData(0, 0, cw, ch), [0, -a.sharp / 50, 0, -a.sharp / 50, 1 + 4 * a.sharp / 50, -a.sharp / 50, 0, -a.sharp / 50, 0]), 0, 0);
        if (wm) {
          const fs = Math.max(14, Math.round(Math.min(cw, ch) * 0.04)); g.font = `600 ${fs}px "Segoe UI", sans-serif`;
          const tw = g.measureText(wm).width, m = fs * 0.8;
          const pos = { br: [cw - tw - m, ch - m], bl: [m, ch - m], tr: [cw - tw - m, m + fs], c: [(cw - tw) / 2, ch / 2] }[wmPos];
          g.globalAlpha = 0.55; g.lineWidth = Math.max(2, fs / 10); g.strokeStyle = "#000"; g.strokeText(wm, pos[0], pos[1]); g.fillStyle = "#fff"; g.fillText(wm, pos[0], pos[1]); g.globalAlpha = 1;
        }
        const mime = { jpg: "image/jpeg", png: "image/png", webp: "image/webp" }[fmt];
        const w = await api.pic_batch_write(f, B.out, sfx, fmt, c.toDataURL(mime, q));
        if (w?.ok) ok++; else fail++;
      } catch (_) { fail++; }
      d.querySelector("#bBar").style.width = `${Math.round(((i + 1) / B.files.length) * 100)}%`;
    }
    d.querySelector("#bSt").textContent = L2(`✓ ${ok} görsel hazır${fail ? `, ${fail} olmadı` : ""}`, `✓ ${ok} done${fail ? `, ${fail} failed` : ""}`);
    go.disabled = false;
  }

  // ---------------------------------------------------------------- AI Komut Cubugu & Sag Katman/Gecmis Paneli
  let sdTab = "layers";
  function ensureProDock() {
    const ed = document.getElementById("ed");
    if (!ed) return;
    if (!document.getElementById("edAiBar")) {
      const bar = document.createElement("div");
      bar.id = "edAiBar"; bar.className = "ed-aibar";
      bar.innerHTML = `
        <input id="edAiIn" placeholder="${L2("AI komut: arka plan sil, 4x, yüz, vektör, sb, maske…", "AI command: remove bg, 4x, face, vector, bw, mask…")}">
        <button class="pri" data-aic="run">✦ ${L2("Uygula", "Run")}</button>
        <button data-aic="nobg">✦ ${L2("Arka plan sil", "Remove BG")}</button>
        <button data-aic="upscale">↗ 4x</button>
        <button data-aic="face">☺ ${L2("Yüz", "Face")}</button>
        <button data-aic="vec-color">✎ SVG</button>
        <button data-aic="mask">⬚ ${L2("Maske", "Mask")}</button>
        <button data-aic="batch">⚡ ${L2("Toplu", "Batch")}</button>`;
      ed.appendChild(bar);
      const runCmd = (raw) => {
        const q = String(raw || "").toLowerCase().trim();
        if (!q) return;
        if (/(arka\s*plan|remove\s*bg|nobg|temizle)/.test(q)) window.aiAction?.("nobg");
        else if (/(4x|b[üu]y[üu]t|upscale|netle[şs]tir)/.test(q)) window.aiAction?.("upscale");
        else if (/(y[üu]z|face|gfpgan)/.test(q)) window.aiAction?.("face");
        else if (/(vekt[öo]r|svg)/.test(q)) window.aiAction?.(q.includes("siyah") || q.includes("bw") ? "vec-bw" : "vec-color");
        else if (/(maske|mask)/.test(q)) maskNew(q.includes("seç") || q.includes("sel"));
        else if (/(siyah|beyaz|bw|gray)/.test(q)) adjNew("bw");
        else if (/(e[ğg]ri|curve)/.test(q)) adjNew("curves");
        else if (/(seviye|level)/.test(q)) adjNew("levels");
        else if (/(renk|ton|hue|doygun)/.test(q)) adjNew("hue");
        else if (/(toplu|batch)/.test(q)) batchOpen();
        else toast(L2("Komut anlaşılamadı: arka plan, 4x, yüz, svg, maske, siyah-beyaz, toplu", "Unknown command: nobg, 4x, face, svg, mask, bw, batch"));
      };
      bar.addEventListener("click", (e) => {
        const b = e.target.closest("button[data-aic]"); if (!b) return;
        const c = b.dataset.aic;
        if (c === "run") runCmd(bar.querySelector("#edAiIn").value);
        else if (c === "mask") maskNew(false);
        else if (c === "batch") batchOpen();
        else window.aiAction?.(c);
      });
      bar.querySelector("#edAiIn")?.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") { e.preventDefault(); runCmd(e.target.value); }
      });
    }
    if (!document.getElementById("edSideToggle")) {
      const tg = document.createElement("button");
      tg.id = "edSideToggle"; tg.className = "ed-side-toggle";
      tg.textContent = L2("◧ Katman / Geçmiş", "◧ Layers / History");
      ed.appendChild(tg);
      const dk = document.createElement("aside");
      dk.id = "edSideDock"; dk.className = "ed-sidedock"; dk.hidden = true;
      dk.innerHTML = `
        <div class="ed-sd-tabs">
          <button data-sdt="layers" class="on">${L2("Katmanlar", "Layers")}</button>
          <button data-sdt="history">${L2("Geçmiş", "History")}</button>
        </div>
        <div class="ed-sd-body" id="edSdBody"></div>
        <div class="ed-sd-foot" id="edSdFoot">
          <button data-sda="add">+ ${L2("Katman", "Layer")}</button>
          <button data-sda="adj">◐ ${L2("Ayar", "Adj")}</button>
          <button data-sda="dup">⧉ ${L2("Çoğalt", "Dup")}</button>
          <button data-sda="del">✕ ${L2("Sil", "Del")}</button>
        </div>`;
      ed.appendChild(dk);
      tg.onclick = () => { dk.hidden = !dk.hidden; renderSideDock(); };
      dk.querySelector(".ed-sd-tabs").onclick = (e) => {
        const b = e.target.closest("button[data-sdt]"); if (!b) return;
        sdTab = b.dataset.sdt;
        dk.querySelectorAll(".ed-sd-tabs button").forEach((x) => x.classList.toggle("on", x === b));
        dk.querySelector("#edSdFoot").style.display = sdTab === "layers" ? "flex" : "none";
        renderSideDock();
      };
      dk.querySelector("#edSdFoot").onclick = (e) => {
        const b = e.target.closest("button[data-sda]"); if (!b) return;
        const a = b.dataset.sda;
        if (a === "add") { edLayerAdd?.(L2("Katman", "Layer")); renderSideDock(); }
        else if (a === "adj") { adjNew("color"); renderSideDock(); }
        else if (a === "dup") { edLayerDup?.(); renderSideDock(); }
        else if (a === "del") { edLayerDel?.(); renderSideDock(); }
      };
      dk.querySelector("#edSdBody").onclick = (e) => {
        const row = e.target.closest("[data-sdi]");
        if (row && sdTab === "layers") {
          const i = +row.dataset.sdi;
          const act = e.target.closest("button[data-sdl]")?.dataset.sdl;
          if (act === "vis") { ED.layers[i].vis = !ED.layers[i].vis; edLayersUi(); edRender(); }
          else if (act === "up" && i < ED.layers.length - 1) { const [x] = ED.layers.splice(i, 1); ED.layers.splice(i + 1, 0, x); ED.cur = i + 1; edLayersUi(); edRender(); }
          else if (act === "dn" && i > 0) { const [x] = ED.layers.splice(i, 1); ED.layers.splice(i - 1, 0, x); ED.cur = i - 1; edLayersUi(); edRender(); }
          else { ED.cur = i; edLayersUi(); }
          renderSideDock();
        } else if (row && sdTab === "history") {
          const target = +row.dataset.sdi; let n = ED.undo.length;
          while (n > target && ED.undo.length) { edUndo(); n--; }
          while (n < target && ED.redo.length) { edRedo(); n++; }
          renderSideDock();
        }
      };
    }
  }
  function renderSideDock() {
    const dk = document.getElementById("edSideDock"), body = document.getElementById("edSdBody");
    if (!dk || dk.hidden || !body) return;
    if (sdTab === "layers") {
      body.innerHTML = [...ED.layers].map((l, i) => ({ l, i })).reverse().map(({ l, i }) => `
        <div class="ed-sd-item ${i === ED.cur ? "on" : ""}" data-sdi="${i}">
          <button data-sdl="vis" title="Göster/Gizle">${l.vis ? "👁" : "◌"}</button>
          <span class="nm">${l.adj ? "◐ " : ""}${esc(l.name || "Katman")}</span>
          <button data-sdl="up" title="Yukarı">↑</button>
          <button data-sdl="dn" title="Aşağı">↓</button>
        </div>`).join("");
    } else {
      const past = ED.undo.map((s) => s.label || "?"), fut = [...ED.redo].reverse().map((s) => s.label || "?");
      body.innerHTML = `<div class="ed-sd-item ${past.length ? "" : "on"}" data-sdi="0"><span class="nm">◇ ${L2("Başlangıç", "Start")}</span></div>` +
        past.map((t, i) => `<div class="ed-sd-item ${i === past.length - 1 ? "on" : ""}" data-sdi="${i + 1}"><span class="nm">${esc(t)}</span></div>`).join("") +
        fut.map((t, i) => `<div class="ed-sd-item" style="opacity:.45" data-sdi="${past.length + i + 1}"><span class="nm">${esc(t)}</span></div>`).join("");
    }
  }
  const _lui2 = edLayersUi;
  window.edLayersUi = edLayersUi = function () { _lui2.apply(this, arguments); ensureProDock(); renderSideDock(); };
  setTimeout(ensureProDock, 200);
})();
