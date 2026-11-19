// Kami Picture — Photopea Arac Paketi:
// 1) Klasik Sihirli Degnek (Magic Wand: Tolerance/Contiguous/Feather, 0ms flood-fill)
// 2) Boya Kovasi (Flood Fill) & Degrade (Linear/Radial Gradient)
// 3) Vektor Sekiller (Dikdortgen/Elips/Cizgi/Ok/Yildiz/Cokgen)
// 4) Secim Genisletmeleri (Elips Secim, Cokgen Kement, Genislet/Daralt/Yumusat, Ctrl+Shift+I)
// 5) AI'siz Hizli Rotus Fircalari (Spot Heal, Dodge, Burn, Blur, Smudge)
// 6) Tahribatsiz Katman Stilleri (fx paneli) & Kirpma Maskesi (Clipping Mask, Ctrl+Alt+G)
// 7) Tuval Uzerinde Interaktif Serbest Donusum (Ctrl+T: 8 tutamac + dondurme + Ctrl perspektif)
// 8) Katmanli .PSD Acma
"use strict";

(function () {
  if (typeof TOOLS === "undefined" || typeof ED === "undefined") return;

  // Mevcut AI Tikla-Sec kisayolunu y'ye al, W klasik anlik Sihirli Degnek olsun
  const aiMagic = TOOLS.find((t) => t.id === "magic");
  if (aiMagic) { aiMagic.k = "y"; aiMagic.tr = "AI Seç"; }

  const NEW_TOOLS = [
    { id: "wand", k: "w", tr: "Sihirli değnek", ic: '<path d="M4 20L15 9"/><path d="M15 3v3M19 5l-2 2M21 9h-3M11 5l2 2M15 12v2"/>' },
    { id: "bucket", k: "f", tr: "Boya kovası", ic: '<path d="M19 11l-8-8-8.5 8.5a2.1 2.1 0 0 0 0 3l5 5a2.1 2.1 0 0 0 3 0L19 11z"/><path d="M5 2l5 5"/><path d="M2 13h15"/><path d="M22 20a2 2 0 1 1-4 0c0-1.6 2-3.5 2-3.5s2 1.9 2 3.5z"/>' },
    { id: "gradient", k: "d", tr: "Degrade", ic: '<rect x="3" y="3" width="18" height="18" rx="2"/><path d="M3 15l18-6M3 19l18-6" opacity=".6"/>' },
    { id: "shape", k: "u", tr: "Şekil", ic: '<rect x="3" y="3" width="8" height="8" rx="1.5"/><circle cx="16.5" cy="16.5" r="4.5"/><path d="M14 4l7 7"/>' },
    { id: "retouch", k: "r", tr: "Rötuş", ic: '<path d="M12 2.7l5.7 5.7a8 8 0 1 1-11.4 0z"/><path d="M9 14c.8 1.4 2.1 2 3.5 2"/>' },
  ];
  for (const nt of NEW_TOOLS) {
    if (!TOOLS.some((x) => x.id === nt.id)) TOOLS.push(nt);
  }

  const PP = {
    wandTol: 32,
    wandContig: true,
    wandFeather: 0,
    bucketTol: 32,
    bucketContig: true,
    gradType: "linear",
    gradC1: "#8B5CF6",
    gradC2: "#2EE6A6",
    gradDrag: null,
    shapeType: "rect",
    shapeFill: true,
    shapeStroke: true,
    shapeStrokeW: 3,
    shapeStrokeC: "#FFFFFF",
    shapeRadius: 12,
    shapeDrag: null,
    selMode: "rect",      // rect | ellipse
    lassoMode: "free",    // free | poly
    polyPts: [],
    retouchMode: "spot",  // spot | dodge | burn | blur | smudge
    retouchStr: 0.45,
    smudgeBuf: null,
    retouchDrag: false,
    tr: null,             // aktif interaktif Ctrl+T durumu
  };

  // ---- Stiller (fx penceresi & katman ikonlari) ----
  const st = document.createElement("style");
  st.textContent = `
    .ed-ly .ctl .pp-btn{padding:2px 6px;border-radius:6px;border:1px solid #2D2345;background:#181226;color:#C4B5FD;font-size:10.5px;cursor:pointer;line-height:1.2}
    .ed-ly .ctl .pp-btn.on{background:#7C3AED;border-color:#A855F7;color:#fff}
    .ed-ly .ctl .pp-btn.clip-on{background:#10B981;border-color:#2EE6A6;color:#07130E;font-weight:700}
    .ed-ly.clipped{border-left:3px solid #2EE6A6 !important;padding-left:6px}
    #ppFxModal{position:fixed;inset:0;z-index:180;background:rgba(5,4,10,.72);display:grid;place-items:center}
    #ppFxModal .bx{width:min(420px,92vw);max-height:86vh;overflow:auto;background:#120E1C;border:1px solid #35294D;border-radius:14px;padding:16px;color:#EDE9F6;display:flex;flex-direction:column;gap:10px;box-shadow:0 24px 64px rgba(0,0,0,.7)}
    #ppFxModal .fxr{background:#181326;border:1px solid #28203D;border-radius:10px;padding:8px 10px;display:flex;flex-direction:column;gap:6px}
    #ppFxModal .fxh{display:flex;align-items:center;justify-content:space-between;font-size:12.5px;font-weight:600}
    #ppFxModal .fxc{display:flex;flex-wrap:wrap;gap:8px;align-items:center;font-size:11.5px;color:#B8AFCE}
    #ppFxModal .fxc input[type=range]{width:84px}
    #ppFxModal .fxc input[type=number]{width:52px;background:#0B0812;color:#EDE9F6;border:1px solid #31264A;border-radius:6px;padding:2px 4px}
    #ppTrBar{position:fixed;top:54px;left:50%;transform:translateX(-50%);z-index:165;background:rgba(16,12,26,.95);border:1px solid #3D2E5E;border-radius:999px;padding:6px 14px;display:flex;align-items:center;gap:8px;color:#EDE9F6;font-size:12px;box-shadow:0 12px 32px rgba(0,0,0,.55)}
    #ppTrBar button{background:#1F1733;color:#EDE9F6;border:1px solid #3A2C59;border-radius:8px;padding:4px 10px;cursor:pointer;font-size:11.5px}
    #ppTrBar button.pri{background:#7C3AED;border-color:#A855F7;color:#fff}
  `;
  document.head.appendChild(st);

  // ---- Yardimcilar: Hex -> RGBA, Maske -> Yuruyen Karinca Outline ----
  function hexToRgb(hex) {
    const h = String(hex || "#FFFFFF").replace("#", "");
    const v = h.length === 3 ? h.split("").map((c) => c + c).join("") : h.padEnd(6, "0");
    return [parseInt(v.slice(0, 2), 16) || 0, parseInt(v.slice(2, 4), 16) || 0, parseInt(v.slice(4, 6), 16) || 0];
  }

  function buildOutlineFromMask(mask, W, H) {
    const p = new Path2D();
    let minX = W, minY = H, maxX = -1, maxY = -1;
    const step = W * H > 1800000 ? 2 : 1;
    for (let y = 0; y < H; y += step) {
      const row = y * W;
      for (let x = 0; x < W; x += step) {
        if (!mask[row + x]) continue;
        if (x < minX) minX = x; if (x > maxX) maxX = x;
        if (y < minY) minY = y; if (y > maxY) maxY = y;
        const up = y === 0 || !mask[(y - step) * W + x];
        const dn = y + step >= H || !mask[(y + step) * W + x];
        const lf = x === 0 || !mask[row + (x - step)];
        const rt = x + step >= W || !mask[row + (x + step)];
        if (up) { p.moveTo(x, y); p.lineTo(x + step, y); }
        if (dn) { p.moveTo(x, y + step); p.lineTo(x + step, y + step); }
        if (lf) { p.moveTo(x, y); p.lineTo(x, y + step); }
        if (rt) { p.moveTo(x + step, y); p.lineTo(x + step, y + step); }
      }
    }
    return { path: p, box: maxX >= minX ? [minX, minY, maxX - minX + 1, maxY - minY + 1] : [0, 0, 0, 0] };
  }

  function maskToCanvas(mask, W, H, featherPx = 0) {
    const c = document.createElement("canvas");
    c.width = W; c.height = H;
    const g = c.getContext("2d");
    const id = g.createImageData(W, H);
    const d = id.data;
    for (let i = 0; i < mask.length; i++) {
      const v = mask[i];
      if (v) {
        const j = i * 4;
        d[j] = 255; d[j + 1] = 255; d[j + 2] = 255; d[j + 3] = v;
      }
    }
    g.putImageData(id, 0, 0);
    if (featherPx > 0) {
      const f = document.createElement("canvas");
      f.width = W; f.height = H;
      const fg = f.getContext("2d");
      fg.filter = `blur(${featherPx}px)`;
      fg.drawImage(c, 0, 0);
      return f;
    }
    return c;
  }

  function getCurrentSelectionMask() {
    const W = ED.W, H = ED.H;
    if (ED.sel?.rawMask && ED.sel.rawMask.length === W * H) return new Uint8Array(ED.sel.rawMask);
    const c = document.createElement("canvas"); c.width = W; c.height = H;
    const g = c.getContext("2d");
    if (ED.sel?.maskCanvas) {
      g.drawImage(ED.sel.maskCanvas, 0, 0);
    } else if (ED.sel?.path) {
      g.fillStyle = "#fff";
      g.fill(ED.sel.path, ED.sel.rule || "nonzero");
    } else {
      return new Uint8Array(W * H);
    }
    const d = g.getImageData(0, 0, W, H).data;
    const out = new Uint8Array(W * H);
    for (let i = 0; i < out.length; i++) out[i] = d[i * 4 + 3] > 127 ? 255 : 0;
    return out;
  }

  function applyBinaryMaskSelection(mask, feather = PP.wandFeather) {
    const W = ED.W, H = ED.H;
    let any = false;
    for (let i = 0; i < mask.length; i++) { if (mask[i]) { any = true; break; } }
    if (!any) { ED.sel = null; edRender(); return; }
    const { path, box } = buildOutlineFromMask(mask, W, H);
    const maskCanvas = maskToCanvas(mask, W, H, feather);
    ED.sel = { rawMask: mask, maskCanvas, outline: path, path, box };
    edRender();
  }

  // ---- 1. Klasik Sihirli Degnek (Magic Wand) ----
  function computeWandMask(docX, docY, tol, contiguous) {
    const W = ED.W, H = ED.H;
    const sx = Math.floor(docX), sy = Math.floor(docY);
    if (sx < 0 || sy < 0 || sx >= W || sy >= H) return null;
    const l = cl();
    // Aktif katmanin belge koordinatindaki goruntusunu al
    const tmp = document.createElement("canvas"); tmp.width = W; tmp.height = H;
    tmp.getContext("2d").drawImage(l.c, l.x, l.y);
    const data = tmp.getContext("2d").getImageData(0, 0, W, H).data;
    const idx0 = (sy * W + sx) * 4;
    const tr = data[idx0], tg = data[idx0 + 1], tb = data[idx0 + 2], ta = data[idx0 + 3];
    const thr = tol * tol * 4;
    const match = (p) => {
      const i = p * 4;
      const dr = data[i] - tr, dg = data[i + 1] - tg, db = data[i + 2] - tb, da = data[i + 3] - ta;
      return (dr * dr + dg * dg + db * db + da * da) <= thr;
    };

    const mask = new Uint8Array(W * H);
    if (!contiguous) {
      for (let p = 0; p < W * H; p++) if (match(p)) mask[p] = 255;
      return mask;
    }
    // Hizli scanline flood-fill
    const stack = [sx, sy];
    while (stack.length) {
      const y = stack.pop(), x0 = stack.pop();
      let xl = x0;
      const row = y * W;
      while (xl >= 0 && !mask[row + xl] && match(row + xl)) xl--;
      xl++;
      let xr = x0;
      while (xr < W && !mask[row + xr] && match(row + xr)) xr++;
      let spanUp = false, spanDn = false;
      for (let x = xl; x < xr; x++) {
        mask[row + x] = 255;
        if (y > 0) {
          const up = (y - 1) * W + x;
          const mUp = !mask[up] && match(up);
          if (!spanUp && mUp) { stack.push(x, y - 1); spanUp = true; }
          else if (spanUp && !mUp) spanUp = false;
        }
        if (y < H - 1) {
          const dn = (y + 1) * W + x;
          const mDn = !mask[dn] && match(dn);
          if (!spanDn && mDn) { stack.push(x, y + 1); spanDn = true; }
          else if (spanDn && !mDn) spanDn = false;
        }
      }
    }
    return mask;
  }

  function runMagicWand(x, y, add, sub) {
    const m = computeWandMask(x, y, PP.wandTol, PP.wandContig);
    if (!m) return;
    if ((add || sub) && ED.sel) {
      const cur = getCurrentSelectionMask();
      for (let i = 0; i < cur.length; i++) {
        if (add && m[i]) cur[i] = 255;
        else if (sub && m[i]) cur[i] = 0;
      }
      applyBinaryMaskSelection(cur, PP.wandFeather);
    } else {
      applyBinaryMaskSelection(m, PP.wandFeather);
    }
  }

  // ---- 2. Boya Kovasi (Flood Fill) ----
  function runBucket(docX, docY) {
    const l = cl();
    if (!l || !l.vis || l.adj) { toast(edL("Bu katmana boyanamaz", "Cannot fill this layer")); return; }
    const m = computeWandMask(docX, docY, PP.bucketTol, PP.bucketContig);
    if (!m) return;
    edSnap(edL("Boya kovası", "Paint bucket"));
    const W = ED.W, H = ED.H;
    const [cr, cg, cb] = hexToRgb(ED.color);
    const fillC = document.createElement("canvas"); fillC.width = W; fillC.height = H;
    const fg = fillC.getContext("2d");
    const id = fg.createImageData(W, H);
    const d = id.data;
    const alpha = Math.round(Math.max(0.01, Math.min(1, ED.opacity)) * 255);
    for (let i = 0; i < m.length; i++) {
      if (m[i]) { const j = i * 4; d[j] = cr; d[j + 1] = cg; d[j + 2] = cb; d[j + 3] = alpha; }
    }
    fg.putImageData(id, 0, 0);
    if (ED.sel?.maskCanvas) {
      fg.globalCompositeOperation = "destination-in";
      fg.drawImage(ED.sel.maskCanvas, 0, 0);
    } else if (ED.sel?.path) {
      const clipC = document.createElement("canvas"); clipC.width = W; clipC.height = H;
      const cg2 = clipC.getContext("2d"); cg2.clip(ED.sel.path, ED.sel.rule || "nonzero"); cg2.drawImage(fillC, 0, 0);
      fg.clearRect(0, 0, W, H); fg.drawImage(clipC, 0, 0);
    }
    l.c.getContext("2d").drawImage(fillC, -l.x, -l.y);
    edBump(); edRender(); edLayerThumb(ED.cur);
  }

  // ---- 3. Degrade (Gradient) ----
  function applyGradient(x0, y0, x1, y1) {
    const l = cl();
    if (!l || !l.vis || l.adj) return;
    edSnap(edL("Degrade", "Gradient"));
    const tmp = document.createElement("canvas"); tmp.width = ED.W; tmp.height = ED.H;
    const g = tmp.getContext("2d");
    const r = Math.max(1, Math.hypot(x1 - x0, y1 - y0));
    const grd = PP.gradType === "radial"
      ? g.createRadialGradient(x0, y0, 0, x0, y0, r)
      : g.createLinearGradient(x0, y0, x1, y1);
    grd.addColorStop(0, PP.gradC1);
    grd.addColorStop(1, PP.gradC2);
    g.globalAlpha = ED.opacity;
    g.fillStyle = grd;
    g.fillRect(0, 0, ED.W, ED.H);
    if (ED.sel?.maskCanvas) {
      g.globalCompositeOperation = "destination-in";
      g.drawImage(ED.sel.maskCanvas, 0, 0);
    } else if (ED.sel?.path) {
      const c2 = document.createElement("canvas"); c2.width = ED.W; c2.height = ED.H;
      const g2 = c2.getContext("2d"); g2.clip(ED.sel.path, ED.sel.rule || "nonzero"); g2.drawImage(tmp, 0, 0);
      g.clearRect(0, 0, ED.W, ED.H); g.drawImage(c2, 0, 0);
    }
    l.c.getContext("2d").drawImage(tmp, -l.x, -l.y);
    edBump(); edRender(); edLayerThumb(ED.cur);
  }

  // ---- 4. Vektor Sekiller (Shape) ----
  function drawShapeOnCtx(g, s) {
    const x = Math.min(s.x0, s.x1), y = Math.min(s.y0, s.y1);
    const w = Math.abs(s.x1 - s.x0), h = Math.abs(s.y1 - s.y0);
    if (w < 1 && h < 1) return;
    g.save();
    g.globalAlpha = ED.opacity;
    g.fillStyle = ED.color;
    g.strokeStyle = PP.shapeStrokeC;
    g.lineWidth = Math.max(1, PP.shapeStrokeW);
    g.lineCap = "round"; g.lineJoin = "round";
    g.beginPath();
    if (PP.shapeType === "rect") {
      const r = Math.min(PP.shapeRadius, w / 2, h / 2);
      if (g.roundRect) g.roundRect(x, y, w, h, r); else g.rect(x, y, w, h);
    } else if (PP.shapeType === "ellipse") {
      g.ellipse(x + w / 2, y + h / 2, w / 2, h / 2, 0, 0, Math.PI * 2);
    } else if (PP.shapeType === "line" || PP.shapeType === "arrow") {
      g.moveTo(s.x0, s.y0); g.lineTo(s.x1, s.y1);
      if (PP.shapeType === "arrow") {
        const ang = Math.atan2(s.y1 - s.y0, s.x1 - s.x0);
        const hl = Math.max(12, PP.shapeStrokeW * 4);
        g.moveTo(s.x1, s.y1); g.lineTo(s.x1 - hl * Math.cos(ang - 0.5), s.y1 - hl * Math.sin(ang - 0.5));
        g.moveTo(s.x1, s.y1); g.lineTo(s.x1 - hl * Math.cos(ang + 0.5), s.y1 - hl * Math.sin(ang + 0.5));
      }
    } else if (PP.shapeType === "star" || PP.shapeType === "poly") {
      const cx = x + w / 2, cy = y + h / 2, rx = w / 2, ry = h / 2;
      const pts = PP.shapeType === "star" ? 10 : 6;
      for (let i = 0; i < pts; i++) {
        const a = -Math.PI / 2 + (i * Math.PI * 2) / pts;
        const k = PP.shapeType === "star" && i % 2 === 1 ? 0.45 : 1;
        const px = cx + Math.cos(a) * rx * k, py = cy + Math.sin(a) * ry * k;
        if (i === 0) g.moveTo(px, py); else g.lineTo(px, py);
      }
      g.closePath();
    }
    const isLine = PP.shapeType === "line" || PP.shapeType === "arrow";
    if (!isLine && PP.shapeFill) g.fill();
    if (isLine || PP.shapeStroke) g.stroke();
    g.restore();
  }

  // ---- 5. AI'siz Hizli Rotus Fircalari (Spot Heal / Dodge / Burn / Blur / Smudge) ----
  function retouchDab(docX, docY) {
    const l = cl();
    if (!l || !l.vis || l.adj) return;
    const r = Math.max(2, Math.round(ED.size / 2));
    const lx = Math.round(docX - l.x), ly = Math.round(docY - l.y);
    const g = l.c.getContext("2d");
    const bx = Math.max(0, lx - r), by = Math.max(0, ly - r);
    const bw = Math.min(l.c.width, lx + r) - bx, bh = Math.min(l.c.height, ly + r) - by;
    if (bw <= 1 || bh <= 1) return;

    if (PP.retouchMode === "smudge") {
      if (!PP.smudgeBuf) {
        PP.smudgeBuf = document.createElement("canvas");
        PP.smudgeBuf.width = r * 2; PP.smudgeBuf.height = r * 2;
        PP.smudgeBuf.getContext("2d").drawImage(l.c, lx - r, ly - r, r * 2, r * 2, 0, 0, r * 2, r * 2);
        return;
      }
      g.save();
      g.beginPath(); g.arc(lx, ly, r, 0, Math.PI * 2); g.clip();
      g.globalAlpha = PP.retouchStr;
      g.drawImage(PP.smudgeBuf, lx - r, ly - r);
      g.restore();
      PP.smudgeBuf.getContext("2d").clearRect(0, 0, r * 2, r * 2);
      PP.smudgeBuf.getContext("2d").drawImage(l.c, lx - r, ly - r, r * 2, r * 2, 0, 0, r * 2, r * 2);
      edRender();
      return;
    }

    if (PP.retouchMode === "blur" || PP.retouchMode === "spot") {
      const pad = Math.min(20, Math.max(4, Math.round(r * 0.4)));
      const sx = Math.max(0, bx - pad), sy = Math.max(0, by - pad);
      const sw = Math.min(l.c.width, bx + bw + pad) - sx, sh = Math.min(l.c.height, by + bh + pad) - sy;
      const tmp = document.createElement("canvas"); tmp.width = sw; tmp.height = sh;
      const tg = tmp.getContext("2d");
      tg.filter = `blur(${PP.retouchMode === "spot" ? Math.max(3, Math.round(r * 0.35)) : Math.max(1.5, PP.retouchStr * 8)}px)`;
      tg.drawImage(l.c, sx, sy, sw, sh, 0, 0, sw, sh);
      g.save();
      g.beginPath(); g.arc(lx, ly, r, 0, Math.PI * 2); g.clip();
      g.globalAlpha = PP.retouchMode === "spot" ? 0.92 : PP.retouchStr;
      g.drawImage(tmp, sx, sy);
      g.restore();
      edRender();
      return;
    }

    // Dodge (aydinlat) / Burn (koyulastir)
    const id = g.getImageData(bx, by, bw, bh);
    const d = id.data;
    const isDodge = PP.retouchMode === "dodge";
    const amt = PP.retouchStr * 0.25;
    for (let y = 0; y < bh; y++) {
      for (let x = 0; x < bw; x++) {
        const dx = (bx + x) - lx, dy = (by + y) - ly;
        const dist = Math.hypot(dx, dy) / r;
        if (dist >= 1) continue;
        const fall = (1 - dist * dist) * amt;
        const i = (y * bw + x) * 4;
        if (isDodge) {
          d[i] = Math.min(255, d[i] + (255 - d[i]) * fall);
          d[i + 1] = Math.min(255, d[i + 1] + (255 - d[i + 1]) * fall);
          d[i + 2] = Math.min(255, d[i + 2] + (255 - d[i + 2]) * fall);
        } else {
          const k = 1 - fall;
          d[i] = Math.max(0, d[i] * k);
          d[i + 1] = Math.max(0, d[i + 1] * k);
          d[i + 2] = Math.max(0, d[i + 2] * k);
        }
      }
    }
    g.putImageData(id, bx, by);
    edRender();
  }

  // ---- 6. Secim Islemleri (Genislet / Daralt / Yumusat / Ters Cevir) ----
  function morphSelection(deltaPx) {
    if (!ED.sel) return;
    const W = ED.W, H = ED.H;
    const cur = getCurrentSelectionMask();
    const out = new Uint8Array(W * H);
    const rad = Math.max(1, Math.min(24, Math.abs(deltaPx)));
    const expand = deltaPx > 0;
    // Hizli ayrik yatay + dikey 1B gecis (O(W*H*r) yerine hizli kutu cekirdegi)
    const mid = new Uint8Array(W * H);
    for (let y = 0; y < H; y++) {
      const row = y * W;
      for (let x = 0; x < W; x++) {
        let hit = expand ? 0 : 255;
        const x0 = Math.max(0, x - rad), x1 = Math.min(W - 1, x + rad);
        for (let k = x0; k <= x1; k++) {
          if (expand) { if (cur[row + k]) { hit = 255; break; } }
          else { if (!cur[row + k]) { hit = 0; break; } }
        }
        mid[row + x] = hit;
      }
    }
    for (let x = 0; x < W; x++) {
      for (let y = 0; y < H; y++) {
        let hit = expand ? 0 : 255;
        const y0 = Math.max(0, y - rad), y1 = Math.min(H - 1, y + rad);
        for (let k = y0; k <= y1; k++) {
          if (expand) { if (mid[k * W + x]) { hit = 255; break; } }
          else { if (!mid[k * W + x]) { hit = 0; break; } }
        }
        out[y * W + x] = hit;
      }
    }
    applyBinaryMaskSelection(out, PP.wandFeather);
  }

  function invertSelectionSmart() {
    if (!ED.sel) return;
    const cur = getCurrentSelectionMask();
    for (let i = 0; i < cur.length; i++) cur[i] = cur[i] ? 0 : 255;
    applyBinaryMaskSelection(cur, PP.wandFeather);
  }

  function featherSelection(px = 6) {
    if (!ED.sel) return;
    const cur = getCurrentSelectionMask();
    applyBinaryMaskSelection(cur, px);
    toast(edL(`Seçim ${px}px yumuşatıldı`, `Selection feathered ${px}px`));
  }

  // ---- 7. Tahribatsiz Katman Stilleri (fx) Penceresi ----
  function openFxModal(layerIdx) {
    const l = ED.layers[layerIdx];
    if (!l) return;
    document.getElementById("ppFxModal")?.remove();
    const fx = JSON.parse(JSON.stringify(l.fx || {}));
    const def = {
      dropShadow: { on: false, color: "#000000", blur: 14, dx: 6, dy: 8, opacity: 0.65, ...(fx.dropShadow || {}) },
      stroke: { on: false, color: "#FFFFFF", width: 3, ...(fx.stroke || {}) },
      outerGlow: { on: false, color: "#8B5CF6", blur: 18, ...(fx.outerGlow || {}) },
      innerGlow: { on: false, color: "#2EE6A6", blur: 16, ...(fx.innerGlow || {}) },
      colorOverlay: { on: false, color: "#8B5CF6", opacity: 0.6, ...(fx.colorOverlay || {}) },
      gradientOverlay: { on: false, color1: "#8B5CF6", color2: "#2EE6A6", angle: 135, opacity: 0.75, ...(fx.gradientOverlay || {}) },
      bevel: { on: false, strength: 0.4, ...(fx.bevel || {}) },
      halftone: { on: false, dotSize: 8, bg: "", ...(fx.halftone || {}) },
    };
    const m = document.createElement("div");
    m.id = "ppFxModal";
    m.innerHTML = `<div class="bx">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <strong>✨ ${edL("Katman Stilleri (fx)", "Layer Styles (fx)")} — ${esc(l.name)}</strong>
        <button id="ppFxX" style="background:none;border:0;color:#9A90AB;cursor:pointer;font-size:15px">✕</button>
      </div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="dropShadow.on" ${def.dropShadow.on ? "checked" : ""}> Dış Gölge (Drop Shadow)</span><input type="color" data-k="dropShadow.color" value="${def.dropShadow.color}"></label>
        <div class="fxc">Bulanık <input type="range" min="0" max="60" data-k="dropShadow.blur" value="${def.dropShadow.blur}"> X <input type="number" data-k="dropShadow.dx" value="${def.dropShadow.dx}"> Y <input type="number" data-k="dropShadow.dy" value="${def.dropShadow.dy}"> Opaklık <input type="range" min="10" max="100" data-pct="1" data-k="dropShadow.opacity" value="${Math.round(def.dropShadow.opacity * 100)}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="stroke.on" ${def.stroke.on ? "checked" : ""}> Kontur (Stroke)</span><input type="color" data-k="stroke.color" value="${def.stroke.color}"></label>
        <div class="fxc">Kalınlık <input type="range" min="1" max="30" data-k="stroke.width" value="${def.stroke.width}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="outerGlow.on" ${def.outerGlow.on ? "checked" : ""}> Dış Işıma (Outer Glow)</span><input type="color" data-k="outerGlow.color" value="${def.outerGlow.color}"></label>
        <div class="fxc">Yayılım <input type="range" min="2" max="60" data-k="outerGlow.blur" value="${def.outerGlow.blur}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="innerGlow.on" ${def.innerGlow.on ? "checked" : ""}> İç Işıma (Inner Glow)</span><input type="color" data-k="innerGlow.color" value="${def.innerGlow.color}"></label>
        <div class="fxc">Yayılım <input type="range" min="2" max="50" data-k="innerGlow.blur" value="${def.innerGlow.blur}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="colorOverlay.on" ${def.colorOverlay.on ? "checked" : ""}> Renk Kaplama</span><input type="color" data-k="colorOverlay.color" value="${def.colorOverlay.color}"></label>
        <div class="fxc">Opaklık <input type="range" min="5" max="100" data-pct="1" data-k="colorOverlay.opacity" value="${Math.round(def.colorOverlay.opacity * 100)}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="gradientOverlay.on" ${def.gradientOverlay.on ? "checked" : ""}> Degrade Kaplama</span><span><input type="color" data-k="gradientOverlay.color1" value="${def.gradientOverlay.color1}"> <input type="color" data-k="gradientOverlay.color2" value="${def.gradientOverlay.color2}"></span></label>
        <div class="fxc">Açı <input type="range" min="0" max="360" data-k="gradientOverlay.angle" value="${def.gradientOverlay.angle}"> Opaklık <input type="range" min="5" max="100" data-pct="1" data-k="gradientOverlay.opacity" value="${Math.round(def.gradientOverlay.opacity * 100)}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="bevel.on" ${def.bevel.on ? "checked" : ""}> Eğim & Kabartma (Bevel)</span></label>
        <div class="fxc">Güç <input type="range" min="10" max="85" data-pct="1" data-k="bevel.strength" value="${Math.round(def.bevel.strength * 100)}"></div></div>
      <div class="fxr"><label class="fxh"><span><input type="checkbox" data-k="halftone.on" ${def.halftone.on ? "checked" : ""}> Halftone / Risograph</span></label>
        <div class="fxc">Nokta <input type="range" min="4" max="24" data-k="halftone.dotSize" value="${def.halftone.dotSize}"></div></div>
      <div style="display:flex;justify-content:flex-end;gap:8px;margin-top:4px">
        <button id="ppFxClr" style="background:#1F1733;color:#EDE9F6;border:1px solid #35294D;border-radius:8px;padding:6px 12px;cursor:pointer">Tümünü Sıfırla</button>
        <button id="ppFxOk" style="background:#7C3AED;color:#fff;border:0;border-radius:8px;padding:6px 14px;cursor:pointer;font-weight:600">Tamam</button>
      </div>
    </div>`;
    document.body.appendChild(m);
    const sync = () => {
      m.querySelectorAll("[data-k]").forEach((el) => {
        const [sec, prop] = el.dataset.k.split(".");
        if (el.type === "checkbox") def[sec][prop] = el.checked;
        else if (el.dataset.pct) def[sec][prop] = (+el.value) / 100;
        else if (el.type === "range" || el.type === "number") def[sec][prop] = +el.value;
        else def[sec][prop] = el.value;
      });
      l.fx = JSON.parse(JSON.stringify(def));
      l._fxK = "";
      edBump(); edRender();
    };
    m.addEventListener("input", sync);
    m.addEventListener("change", sync);
    m.querySelector("#ppFxClr").onclick = () => { l.fx = null; l._fxK = ""; edBump(); edLayersUi(); edRender(); m.remove(); };
    m.querySelector("#ppFxX").onclick = () => { edLayersUi(); m.remove(); };
    m.querySelector("#ppFxOk").onclick = () => { sync(); edLayersUi(); m.remove(); };
  }

  // ---- 8. Tuval Uzerinde Interaktif Serbest Donusum (Ctrl+T: 8 tutamac + dondurme + Ctrl perspektif) ----
  function startInteractiveTransform() {
    const l = cl();
    if (!l || !l.c || l.adj) return;
    if (PP.tr) cancelInteractiveTransform();
    const snap = document.createElement("canvas");
    snap.width = l.c.width; snap.height = l.c.height;
    snap.getContext("2d").drawImage(l.c, 0, 0);
    PP.tr = {
      layer: l,
      origCanvas: snap,
      origX: l.x, origY: l.y,
      cx: l.x + l.c.width / 2,
      cy: l.y + l.c.height / 2,
      w: l.c.width, h: l.c.height,
      rot: 0,
      skewX: 0, skewY: 0,
      flipX: false, flipY: false,
      drag: null,
    };
    showTrBar();
    edRender();
  }

  function renderTransformPreview() {
    const t = PP.tr;
    if (!t) return;
    const rad = t.rot;
    const sx = (t.w / Math.max(1, t.origCanvas.width)) * (t.flipX ? -1 : 1);
    const sy = (t.h / Math.max(1, t.origCanvas.height)) * (t.flipY ? -1 : 1);
    const cos = Math.abs(Math.cos(rad)), sin = Math.abs(Math.sin(rad));
    const padX = Math.abs(t.skewX) * t.h, padY = Math.abs(t.skewY) * t.w;
    const rw = Math.max(2, Math.ceil((t.w + padX) * cos + (t.h + padY) * sin) + 4);
    const rh = Math.max(2, Math.ceil((t.w + padX) * sin + (t.h + padY) * cos) + 4);
    const out = document.createElement("canvas");
    out.width = rw; out.height = rh;
    const g = out.getContext("2d");
    g.translate(rw / 2, rh / 2);
    g.rotate(rad);
    g.transform(1, t.skewY, t.skewX, 1, 0, 0);
    g.scale(sx, sy);
    g.drawImage(t.origCanvas, -t.origCanvas.width / 2, -t.origCanvas.height / 2);
    t.layer.c = out;
    t.layer.x = Math.round(t.cx - rw / 2);
    t.layer.y = Math.round(t.cy - rh / 2);
    edBump(); edRender();
  }

  function showTrBar() {
    document.getElementById("ppTrBar")?.remove();
    const b = document.createElement("div");
    b.id = "ppTrBar";
    b.innerHTML = `<b>Serbest Dönüşüm</b>
      <span style="color:#9A90AB;font-size:11px">Köşe: Ölçek · Üst: Döndür · Ctrl+Kenar: Eğme</span>
      <button id="ppTrFh">⇋</button><button id="ppTrFv">⇵</button>
      <button id="ppTrOk" class="pri">✓ Uygula (Enter)</button><button id="ppTrNo">✕ İptal (Esc)</button>`;
    document.body.appendChild(b);
    b.querySelector("#ppTrFh").onclick = () => { if (PP.tr) { PP.tr.flipX = !PP.tr.flipX; renderTransformPreview(); } };
    b.querySelector("#ppTrFv").onclick = () => { if (PP.tr) { PP.tr.flipY = !PP.tr.flipY; renderTransformPreview(); } };
    b.querySelector("#ppTrOk").onclick = commitInteractiveTransform;
    b.querySelector("#ppTrNo").onclick = cancelInteractiveTransform;
  }

  function commitInteractiveTransform() {
    if (!PP.tr) return;
    const t = PP.tr;
    const finalC = t.layer.c, fx = t.layer.x, fy = t.layer.y;
    t.layer.c = t.origCanvas; t.layer.x = t.origX; t.layer.y = t.origY;
    edSnap(edL("Serbest Dönüşüm", "Free Transform"));
    t.layer.c = finalC; t.layer.x = fx; t.layer.y = fy;
    PP.tr = null;
    document.getElementById("ppTrBar")?.remove();
    edBump(); edLayersUi(); edRender();
  }

  function cancelInteractiveTransform() {
    if (!PP.tr) return;
    const t = PP.tr;
    t.layer.c = t.origCanvas; t.layer.x = t.origX; t.layer.y = t.origY;
    PP.tr = null;
    document.getElementById("ppTrBar")?.remove();
    edBump(); edRender();
  }

  function getTrHandles(t) {
    const hw = t.w / 2, hh = t.h / 2;
    const pt = (lx, ly) => {
      const c = Math.cos(t.rot), s = Math.sin(t.rot);
      return [t.cx + lx * c - ly * s, t.cy + lx * s + ly * c];
    };
    return {
      tl: pt(-hw, -hh), tc: pt(0, -hh), tr: pt(hw, -hh),
      ml: pt(-hw, 0), mr: pt(hw, 0),
      bl: pt(-hw, hh), bc: pt(0, hh), br: pt(hw, hh),
      rot: pt(0, -hh - 28 / ED.z),
    };
  }

  // Override Ctrl+T
  window.edTransformOpen = startInteractiveTransform;

  // ---- Tuval Overlay Cizimi (Degrade cizgisi, Sekil onizleme, Cokgen Kement, Ctrl+T kutusu) ----
  window.edDrawOverlay = function (g) {
    if (PP.gradDrag) {
      g.save();
      g.lineWidth = 2 / ED.z; g.strokeStyle = "#2EE6A6";
      g.beginPath(); g.moveTo(PP.gradDrag.x0, PP.gradDrag.y0); g.lineTo(PP.gradDrag.x1, PP.gradDrag.y1); g.stroke();
      g.fillStyle = PP.gradC1; g.beginPath(); g.arc(PP.gradDrag.x0, PP.gradDrag.y0, 5 / ED.z, 0, Math.PI * 2); g.fill();
      g.fillStyle = PP.gradC2; g.beginPath(); g.arc(PP.gradDrag.x1, PP.gradDrag.y1, 5 / ED.z, 0, Math.PI * 2); g.fill();
      g.restore();
    }
    if (PP.shapeDrag) {
      drawShapeOnCtx(g, PP.shapeDrag);
    }
    if (PP.polyPts.length) {
      g.save();
      g.lineWidth = 1.5 / ED.z; g.strokeStyle = "#2EE6A6";
      g.beginPath();
      PP.polyPts.forEach((p, i) => (i ? g.lineTo(p[0], p[1]) : g.moveTo(p[0], p[1])));
      if (ED.hover) g.lineTo(ED.hover[0], ED.hover[1]);
      g.stroke();
      for (const p of PP.polyPts) {
        g.fillStyle = "#fff"; g.beginPath(); g.arc(p[0], p[1], 3.5 / ED.z, 0, Math.PI * 2); g.fill();
      }
      g.restore();
    }
    if (PP.tr) {
      const hs = getTrHandles(PP.tr);
      g.save();
      g.lineWidth = 1.5 / ED.z; g.strokeStyle = "#2EE6A6";
      g.beginPath();
      g.moveTo(...hs.tl); g.lineTo(...hs.tr); g.lineTo(...hs.br); g.lineTo(...hs.bl); g.closePath();
      g.moveTo(...hs.tc); g.lineTo(...hs.rot);
      g.stroke();
      const r = 5 / ED.z;
      for (const [k, [hx, hy]] of Object.entries(hs)) {
        g.fillStyle = k === "rot" ? "#A855F7" : "#FFFFFF";
        g.strokeStyle = "#0B0910";
        g.lineWidth = 1.2 / ED.z;
        g.beginPath();
        if (k === "rot") g.arc(hx, hy, r * 1.15, 0, Math.PI * 2);
        else g.rect(hx - r, hy - r, r * 2, r * 2);
        g.fill(); g.stroke();
      }
      g.restore();
    }
  };

  // ---- Katman Paneli Sarmalayicisi (fx & Clipping Mask dugmeleri) ----
  const _origLayersUi = window.edLayersUi;
  if (typeof _origLayersUi === "function") {
    window.edLayersUi = function () {
      _origLayersUi.apply(this, arguments);
      document.querySelectorAll("#edLayers .ed-ly").forEach((el) => {
        const idx = +el.dataset.i;
        const l = ED.layers[idx];
        if (!l) return;
        if (l.clipToBelow) el.classList.add("clipped");
        const ctls = el.querySelectorAll(".ctl");
        const lastCtl = ctls[ctls.length - 1];
        if (lastCtl && !lastCtl.querySelector("[data-pp-fx]")) {
          const fxOn = typeof EFX !== "undefined" && EFX.hasActiveStyles?.(l.fx);
          const bFx = document.createElement("button");
          bFx.className = "pp-btn" + (fxOn ? " on" : "");
          bFx.dataset.ppFx = String(idx);
          bFx.title = "Katman Stilleri (Drop Shadow, Stroke, Glow…)";
          bFx.textContent = "fx";
          const bClip = document.createElement("button");
          bClip.className = "pp-btn" + (l.clipToBelow ? " clip-on" : "");
          bClip.dataset.ppClip = String(idx);
          bClip.title = "Kırpma Maskesi (Ctrl+Alt+G)";
          bClip.textContent = "↳";
          lastCtl.append(bFx, bClip);
        }
      });
    };
  }

  // ---- Arac Secenekleri (edOptExtra sarmalayicisi) ----
  const _origOptExtra = window.edOptExtra;
  window.edOptExtra = function (t) {
    if (t === "wand") {
      return `<label>Tolerans <input type="range" min="0" max="200" value="${PP.wandTol}" data-pp="wandTol"><em>${PP.wandTol}</em></label>
        <label><input type="checkbox" data-pp="wandContig" ${PP.wandContig ? "checked" : ""}> Bitişik</label>
        <label>Yumuşat <input type="range" min="0" max="20" value="${PP.wandFeather}" data-pp="wandFeather"><em>${PP.wandFeather}</em></label>
        <button data-pp-act="expand">+4px</button><button data-pp-act="contract">-4px</button><button data-pp-act="inv">Ters</button>
        <button data-x="sellayer">Katmana al</button><button data-x="selclear">Sil</button><button data-x="selnone">Kaldır</button>`;
    }
    if (t === "bucket") {
      return `<label>Tolerans <input type="range" min="0" max="200" value="${PP.bucketTol}" data-pp="bucketTol"><em>${PP.bucketTol}</em></label>
        <label><input type="checkbox" data-pp="bucketContig" ${PP.bucketContig ? "checked" : ""}> Bitişik</label>
        <label>Opaklık <input type="range" min="5" max="100" value="${Math.round(ED.opacity * 100)}" data-o="opacity"></label>
        <input type="color" value="${ED.color}" data-o="color">`;
    }
    if (t === "gradient") {
      return `<select data-pp="gradType"><option value="linear" ${PP.gradType === "linear" ? "selected" : ""}>Doğrusal</option><option value="radial" ${PP.gradType === "radial" ? "selected" : ""}>Radyal</option></select>
        <input type="color" value="${PP.gradC1}" data-pp="gradC1" title="Başlangıç rengi">
        <input type="color" value="${PP.gradC2}" data-pp="gradC2" title="Bitiş rengi">
        <label>Opaklık <input type="range" min="5" max="100" value="${Math.round(ED.opacity * 100)}" data-o="opacity"></label>
        <span>Tuvalde sürükle</span>`;
    }
    if (t === "shape") {
      return `<select data-pp="shapeType">
          <option value="rect" ${PP.shapeType === "rect" ? "selected" : ""}>Dikdörtgen</option>
          <option value="ellipse" ${PP.shapeType === "ellipse" ? "selected" : ""}>Elips</option>
          <option value="line" ${PP.shapeType === "line" ? "selected" : ""}>Çizgi</option>
          <option value="arrow" ${PP.shapeType === "arrow" ? "selected" : ""}>Ok</option>
          <option value="star" ${PP.shapeType === "star" ? "selected" : ""}>Yıldız</option>
          <option value="poly" ${PP.shapeType === "poly" ? "selected" : ""}>Altıgen</option>
        </select>
        <label><input type="checkbox" data-pp="shapeFill" ${PP.shapeFill ? "checked" : ""}> Dolgu</label><input type="color" value="${ED.color}" data-o="color">
        <label><input type="checkbox" data-pp="shapeStroke" ${PP.shapeStroke ? "checked" : ""}> Kontur</label><input type="color" value="${PP.shapeStrokeC}" data-pp="shapeStrokeC">
        <label>Kalınlık <input type="range" min="1" max="30" value="${PP.shapeStrokeW}" data-pp="shapeStrokeW"></label>
        ${PP.shapeType === "rect" ? `<label>Köşe <input type="range" min="0" max="80" value="${PP.shapeRadius}" data-pp="shapeRadius"></label>` : ""}`;
    }
    if (t === "retouch") {
      return `<select data-pp="retouchMode">
          <option value="spot" ${PP.retouchMode === "spot" ? "selected" : ""}>Hızlı Leke (Spot Heal)</option>
          <option value="dodge" ${PP.retouchMode === "dodge" ? "selected" : ""}>Aydınlat (Dodge)</option>
          <option value="burn" ${PP.retouchMode === "burn" ? "selected" : ""}>Koyulaştır (Burn)</option>
          <option value="blur" ${PP.retouchMode === "blur" ? "selected" : ""}>Bulanıklaştır (Blur)</option>
          <option value="smudge" ${PP.retouchMode === "smudge" ? "selected" : ""}>Bulaştır (Smudge)</option>
        </select>
        <label>Boyut <input type="range" min="4" max="300" value="${ED.size}" data-o="size"></label>
        <label>Güç <input type="range" min="5" max="100" value="${Math.round(PP.retouchStr * 100)}" data-pp="retouchStr"></label>`;
    }
    if (t === "select") {
      return `<select data-pp="selMode"><option value="rect" ${PP.selMode === "rect" ? "selected" : ""}>Dikdörtgen</option><option value="ellipse" ${PP.selMode === "ellipse" ? "selected" : ""}>Elips</option></select>
        <button data-x="selall">Tümü</button><button data-x="selnone">Kaldır</button><button data-pp-act="inv">Ters</button>
        <button data-pp-act="expand">+4px</button><button data-pp-act="contract">-4px</button><button data-pp-act="feather">Yumuşat</button>
        <button data-x="sellayer">Katmana al</button><button data-x="selcut">Kes</button><button data-x="selfill">Doldur</button><button data-x="selclear">Temizle</button><input type="color" value="${ED.color}" data-o="color">`;
    }
    if (t === "lasso") {
      return `<select data-pp="lassoMode"><option value="free" ${PP.lassoMode === "free" ? "selected" : ""}>Serbest Kement</option><option value="poly" ${PP.lassoMode === "poly" ? "selected" : ""}>Çokgen Kement</option></select>
        <button data-x="selnone">Kaldır</button><button data-pp-act="inv">Ters</button><button data-pp-act="expand">+4px</button><button data-pp-act="feather">Yumuşat</button>
        <button data-x="sellayer">Katmana al</button><button data-x="selcut">Kes</button><button data-x="selclear">Temizle</button>`;
    }
    return _origOptExtra ? _origOptExtra(t) : null;
  };

  // ---- Pointer Olaylari (edDown / edMove / edUp sarmalayicilari) ----
  const _origDown = window.edDown;
  const _origMove = window.edMove;
  const _origUp = window.edUp;

  window.edDown = function (e) {
    if (e.button === 2 || e.button === 1 || ED.space) return _origDown(e);
    const [x, y] = toDoc(e.offsetX, e.offsetY);

    // Interaktif Ctrl+T tutamaclari
    if (PP.tr) {
      const hs = getTrHandles(PP.tr);
      const hitR = 11 / ED.z;
      let hit = null;
      for (const [k, [hx, hy]] of Object.entries(hs)) {
        if (Math.hypot(x - hx, y - hy) <= hitR) { hit = k; break; }
      }
      $("#edView").setPointerCapture(e.pointerId);
      PP.tr.drag = {
        kind: hit || "move",
        sx: x, sy: y,
        cx0: PP.tr.cx, cy0: PP.tr.cy,
        w0: PP.tr.w, h0: PP.tr.h,
        rot0: PP.tr.rot,
        skewX0: PP.tr.skewX, skewY0: PP.tr.skewY,
        ctrl: e.ctrlKey,
      };
      return;
    }

    const t = ED.tool;
    if (t === "wand") { runMagicWand(x, y, e.shiftKey, e.altKey); return; }
    if (t === "bucket") { runBucket(x, y); return; }
    if (t === "gradient") { $("#edView").setPointerCapture(e.pointerId); PP.gradDrag = { x0: x, y0: y, x1: x, y1: y }; edRender(); return; }
    if (t === "shape") { $("#edView").setPointerCapture(e.pointerId); PP.shapeDrag = { x0: x, y0: y, x1: x, y1: y }; edRender(); return; }
    if (t === "retouch") {
      const l = cl(); if (!l || !l.vis || l.adj) return;
      edSnap(edL("Rötuş", "Retouch"));
      $("#edView").setPointerCapture(e.pointerId);
      PP.smudgeBuf = null; PP.retouchDrag = true;
      retouchDab(x, y);
      return;
    }
    if (t === "lasso" && PP.lassoMode === "poly") {
      if (PP.polyPts.length >= 3 && Math.hypot(x - PP.polyPts[0][0], y - PP.polyPts[0][1]) < 12 / ED.z) {
        edSelPoly(PP.polyPts); PP.polyPts = []; edRender(); return;
      }
      PP.polyPts.push([x, y]); edRender(); return;
    }
    return _origDown(e);
  };

  window.edMove = function (e) {
    const [x, y] = toDoc(e.offsetX, e.offsetY);
    ED.hover = [x, y];
    if (PP.tr?.drag) {
      const t = PP.tr, d = t.drag;
      if (d.kind === "move") {
        t.cx = d.cx0 + (x - d.sx);
        t.cy = d.cy0 + (y - d.sy);
      } else if (d.kind === "rot") {
        t.rot = Math.atan2(y - t.cy, x - t.cx) + Math.PI / 2;
      } else if (d.ctrl) {
        t.skewX = Math.max(-1.5, Math.min(1.5, d.skewX0 + (x - d.sx) / Math.max(40, t.h)));
        t.skewY = Math.max(-1.5, Math.min(1.5, d.skewY0 + (y - d.sy) / Math.max(40, t.w)));
      } else {
        const dx = x - t.cx, dy = y - t.cy;
        const c = Math.cos(-t.rot), s = Math.sin(-t.rot);
        const lx = dx * c - dy * s, ly = dx * s + dy * c;
        if (d.kind.includes("l") || d.kind.includes("r")) t.w = Math.max(8, Math.abs(lx) * 2);
        if (d.kind.includes("t") || d.kind.includes("b")) t.h = Math.max(8, Math.abs(ly) * 2);
        if (e.shiftKey && d.w0 > 0) t.h = Math.max(8, t.w * (d.h0 / d.w0));
      }
      renderTransformPreview();
      return;
    }
    if (PP.gradDrag) { PP.gradDrag.x1 = x; PP.gradDrag.y1 = y; edRender(); return; }
    if (PP.shapeDrag) {
      let x1 = x, y1 = y;
      if (e.shiftKey) {
        const dx = x1 - PP.shapeDrag.x0, dy = y1 - PP.shapeDrag.y0;
        const sz = Math.max(Math.abs(dx), Math.abs(dy));
        x1 = PP.shapeDrag.x0 + Math.sign(dx || 1) * sz;
        y1 = PP.shapeDrag.y0 + Math.sign(dy || 1) * sz;
      }
      PP.shapeDrag.x1 = x1; PP.shapeDrag.y1 = y1; edRender(); return;
    }
    if (PP.retouchDrag) { retouchDab(x, y); return; }
    if (PP.polyPts.length) { edRender(); return; }
    // Elips secim destegi
    if (ED.tool === "select" && PP.selMode === "ellipse" && typeof edDrag !== "undefined" && edDrag?.t === "select") {
      let w = x - edDrag.x0, h = y - edDrag.y0;
      if (e.shiftKey) h = Math.sign(h || 1) * Math.abs(w);
      const rx = Math.abs(w) / 2, ry = Math.abs(h) / 2;
      const cx = Math.min(edDrag.x0, edDrag.x0 + w) + rx, cy = Math.min(edDrag.y0, edDrag.y0 + h) + ry;
      const p = new Path2D(); p.ellipse(cx, cy, Math.max(1, rx), Math.max(1, ry), 0, 0, Math.PI * 2);
      ED.sel = { path: p, box: [cx - rx, cy - ry, rx * 2, ry * 2] };
      edRender();
      return;
    }
    return _origMove(e);
  };

  window.edUp = function (e) {
    if (PP.tr?.drag) { PP.tr.drag = null; return; }
    if (PP.gradDrag) {
      const d = PP.gradDrag; PP.gradDrag = null;
      applyGradient(d.x0, d.y0, d.x1, d.y1);
      return;
    }
    if (PP.shapeDrag) {
      const s = PP.shapeDrag; PP.shapeDrag = null;
      const l = cl();
      if (l && l.vis && !l.adj) {
        edSnap(edL("Şekil", "Shape"));
        const g = l.c.getContext("2d");
        g.save(); g.translate(-l.x, -l.y); drawShapeOnCtx(g, s); g.restore();
        edBump(); edRender(); edLayerThumb(ED.cur);
      }
      return;
    }
    if (PP.retouchDrag) { PP.retouchDrag = false; PP.smudgeBuf = null; edBump(); edLayerThumb(ED.cur); return; }
    return _origUp(e);
  };

  // ---- UI Tiklama / Degisim / Klavye Dinleyicileri ----
  document.addEventListener("input", (e) => {
    const k = e.target?.dataset?.pp;
    if (!k) return;
    if (e.target.type === "checkbox") PP[k] = e.target.checked;
    else if (k === "retouchStr") PP[k] = (+e.target.value) / 100;
    else if (["wandTol", "wandFeather", "bucketTol", "shapeStrokeW", "shapeRadius"].includes(k)) {
      PP[k] = +e.target.value;
      if (e.target.nextElementSibling?.tagName === "EM") e.target.nextElementSibling.textContent = e.target.value;
    } else PP[k] = e.target.value;
    if (k === "shapeType") edOpt();
  });

  document.addEventListener("change", (e) => {
    const k = e.target?.dataset?.pp;
    if (!k) return;
    if (e.target.type === "checkbox") PP[k] = e.target.checked;
    else PP[k] = e.target.value;
    if (k === "shapeType" || k === "lassoMode") { PP.polyPts = []; edOpt(); }
  });

  document.addEventListener("click", async (e) => {
    if (!ED.on) return;
    const fxBtn = e.target.closest("[data-pp-fx]");
    if (fxBtn) { e.stopPropagation(); openFxModal(+fxBtn.dataset.ppFx); return; }
    const clipBtn = e.target.closest("[data-pp-clip]");
    if (clipBtn) {
      e.stopPropagation();
      const idx = +clipBtn.dataset.ppClip;
      if (idx === 0) { toast("En alt katman kırpma maskesi olamaz"); return; }
      ED.layers[idx].clipToBelow = !ED.layers[idx].clipToBelow;
      edBump(); edLayersUi(); edRender();
      return;
    }
    const act = e.target.closest("[data-pp-act]")?.dataset?.ppAct;
    if (act === "expand") { morphSelection(4); return; }
    if (act === "contract") { morphSelection(-4); return; }
    if (act === "feather") { featherSelection(6); return; }
    if (act === "inv") { invertSelectionSmart(); return; }

    // .PSD Acma
    if (e.target.closest('[data-x="openpsd"]')) {
      const r = await api?.editor_psd_open?.("");
      if (!r?.ok) { if (r?.error) toast("PSD açılamadı: " + r.error); return; }
      const doc = {
        v: 2, W: r.W, H: r.H, cur: Math.max(0, (r.layers?.length || 1) - 1), name: r.name || "PSD",
        layers: (r.layers || []).map((ly, idx) => ({
          id: "psd_" + idx + "_" + Math.random().toString(36).slice(2, 6),
          name: ly.name || ("Katman " + (idx + 1)),
          x: ly.x || 0, y: ly.y || 0, w: ly.w, h: ly.h,
          vis: ly.vis !== false, op: ly.op ?? 1, blend: ly.blend || "source-over",
          clipToBelow: !!ly.clip, text: null, adj: null, fx: null, png: ly.png, mask: null,
        })),
      };
      await edDeserialize(doc);
      edFit(); edRender();
      toast(`PSD açıldı (${doc.layers.length} katman)`);
    }
  });

  document.addEventListener("dblclick", (e) => {
    if (!ED.on || !PP.polyPts.length) return;
    if (e.target.id === "edView" && PP.polyPts.length >= 3) {
      edSelPoly(PP.polyPts); PP.polyPts = []; edRender();
    }
  });

  document.addEventListener("keydown", (e) => {
    if (!ED.on || e.target.matches?.("input, textarea, [contenteditable]")) return;
    const k = e.key.toLowerCase();
    if (PP.tr) {
      if (k === "enter") { e.preventDefault(); e.stopImmediatePropagation(); commitInteractiveTransform(); return; }
      if (k === "escape") { e.preventDefault(); e.stopImmediatePropagation(); cancelInteractiveTransform(); return; }
    }
    if (PP.polyPts.length && (k === "enter" || k === "escape")) {
      e.preventDefault(); e.stopImmediatePropagation();
      if (k === "enter" && PP.polyPts.length >= 3) edSelPoly(PP.polyPts);
      PP.polyPts = []; edRender(); return;
    }
    // Ctrl+Shift+I: Secimi Ters Cevir
    if (e.ctrlKey && e.shiftKey && k === "i") { e.preventDefault(); invertSelectionSmart(); return; }
    // Ctrl+Alt+G: Kirpma Maskesi (Clipping Mask)
    if (e.ctrlKey && e.altKey && k === "g") {
      e.preventDefault();
      if (ED.cur > 0) {
        ED.layers[ED.cur].clipToBelow = !ED.layers[ED.cur].clipToBelow;
        edBump(); edLayersUi(); edRender();
        toast(ED.layers[ED.cur].clipToBelow ? "Kırpma Maskesi açık" : "Kırpma Maskesi kapalı");
      }
    }
  }, true);
})();
