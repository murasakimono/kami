"use strict";
// Kami Studio onizleme efektleri: disa aktarimdaki ffmpeg zincirlerinin (studio.py FX) tuval yaklasiklari.
// css = ctx.filter (klip cizilirken), ov = cizimden sonra ust katmanlar.
const SFX = (() => {
  const noise = [];
  function noiseTiles() {
    if (noise.length) return noise;
    for (let k = 0; k < 4; k++) {
      const c = document.createElement("canvas"); c.width = c.height = 256;
      const g = c.getContext("2d"), d = g.createImageData(256, 256);
      for (let i = 0; i < d.data.length; i += 4) { const v = Math.random() * 255; d.data[i] = d.data[i + 1] = d.data[i + 2] = v; d.data[i + 3] = 255; }
      g.putImageData(d, 0, 0); noise.push(c);
    }
    return noise;
  }
  let scan = null;
  function scanPat(ctx) {
    if (!scan) { const c = document.createElement("canvas"); c.width = 4; c.height = 4; const g = c.getContext("2d"); g.fillStyle = "rgba(0,0,0,.28)"; g.fillRect(0, 0, 4, 1); scan = c; }
    return ctx.createPattern(scan, "repeat");
  }
  const tmp = document.createElement("canvas"), tg = tmp.getContext("2d");
  function copy(ctx, W, H) {
    if (tmp.width !== W || tmp.height !== H) { tmp.width = W; tmp.height = H; }
    tg.clearRect(0, 0, W, H); tg.drawImage(ctx.canvas, 0, 0); return tmp;
  }
  function rnd(seed) { const x = Math.sin(seed * 12.9898) * 43758.5453; return x - Math.floor(x); }
  function vignette(ctx, W, H, a, col = "0,0,0") {
    const g = ctx.createRadialGradient(W / 2, H / 2, Math.min(W, H) * .3, W / 2, H / 2, Math.hypot(W, H) * .55);
    g.addColorStop(0, `rgba(${col},0)`); g.addColorStop(1, `rgba(${col},${a})`);
    ctx.fillStyle = g; ctx.fillRect(0, 0, W, H);
  }
  function tint(ctx, W, H, col, op, a) { ctx.save(); ctx.globalCompositeOperation = op; ctx.globalAlpha = a; ctx.fillStyle = col; ctx.fillRect(0, 0, W, H); ctx.restore(); }

  // t: zaman cizelgesi sn, local: efektin baslangicindan beri sn
  function overlay(ctx, id, W, H, t, local) {
    const f = Math.floor(t * 24);
    switch (id) {
      case "grain": { ctx.save(); ctx.globalCompositeOperation = "overlay"; ctx.globalAlpha = .22; const n = noiseTiles()[f % 4];
        ctx.fillStyle = ctx.createPattern(n, "repeat"); ctx.translate((f * 37) % 256, (f * 91) % 256); ctx.fillRect(-256, -256, W + 512, H + 512); ctx.restore(); break; }
      case "scan": ctx.save(); ctx.fillStyle = scanPat(ctx); ctx.fillRect(0, 0, W, H); ctx.restore(); break;
      case "vignette": vignette(ctx, W, H, .55); break;
      case "vignette-hard": vignette(ctx, W, H, .85); break;
      case "red-vignette": vignette(ctx, W, H, .6, "120,0,0"); break;
      case "rgb": case "rgb-strong": {
        const s = (id === "rgb" ? 3 : 9) * W / 1280, src = copy(ctx, W, H);
        ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = .45;
        ctx.filter = "sepia(1) saturate(8) hue-rotate(-50deg)"; ctx.drawImage(src, -s, 0);
        ctx.filter = "sepia(1) saturate(8) hue-rotate(170deg)"; ctx.drawImage(src, s, 0); ctx.restore(); break; }
      case "vhs-jitter": case "glitch-bars": {
        const src = copy(ctx, W, H), n = id === "vhs-jitter" ? 2 : 6;
        for (let i = 0; i < n; i++) {
          if (rnd(f * 7 + i) > (id === "vhs-jitter" ? .55 : .35)) continue;
          const y = rnd(f * 3 + i) * H, h = (id === "vhs-jitter" ? 4 : 18) * H / 720 * (1 + rnd(f + i) * 3), dx = (rnd(f * 11 + i) - .5) * W * (id === "vhs-jitter" ? .02 : .08);
          ctx.drawImage(src, 0, y, W, h, dx, y, W, h);
        }
        break; }
      case "shake": case "shake-soft": break;   // cizim donusumunde (shakeOffset)
      case "letterbox": ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H * .11); ctx.fillRect(0, H * .89, W, H * .11); break;
      case "flash": { const a = Math.max(0, .9 * (1 - local / .22)); if (a > 0) tint(ctx, W, H, "#fff", "lighter", a); break; }
      case "strobe": if ((t * 8) % 1 < .5) tint(ctx, W, H, "#fff", "lighter", .45); break;
      case "bloom": { const src = copy(ctx, W, H); ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = .5; ctx.filter = `blur(${Math.round(W / 90)}px)`; ctx.drawImage(src, 0, 0); ctx.restore(); break; }
      case "pixel": case "pixel-strong": {
        const k = id === "pixel" ? 3 : 8, src = copy(ctx, W, H), w = Math.max(1, Math.round(W / k)), h = Math.max(1, Math.round(H / k));
        ctx.save(); ctx.imageSmoothingEnabled = true; ctx.drawImage(src, 0, 0, w, h); const sm = copy(ctx, W, H); ctx.imageSmoothingEnabled = false;
        ctx.clearRect(0, 0, W, H); ctx.drawImage(sm, 0, 0, w, h, 0, 0, W, H); ctx.restore(); break; }
      case "fisheye": vignette(ctx, W, H, .45); break;
      case "teal": tint(ctx, W, H, "#0d6e7a", "soft-light", .35); break;
      case "blue-tint": tint(ctx, W, H, "#2a4f9e", "soft-light", .4); break;
      case "warm-tint": tint(ctx, W, H, "#c27a2a", "soft-light", .35); break;
      case "flicker": tint(ctx, W, H, "#fff", "lighter", Math.max(0, .06 * Math.sin(t * 31))); break;
      case "scratches": { ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.35)"; ctx.lineWidth = 1;
        for (let i = 0; i < 3; i++) if (rnd(f * 5 + i) > .6) { const x = rnd(f * 13 + i) * W; ctx.beginPath(); ctx.moveTo(x, 0); ctx.lineTo(x + (rnd(f + i) - .5) * 8, H); ctx.stroke(); }
        ctx.restore(); break; }
      case "double": { const src = copy(ctx, W, H); ctx.save(); ctx.globalAlpha = .5; ctx.drawImage(src, Math.sin(t * 1.7) * W * .012, Math.cos(t * 1.3) * H * .012); ctx.restore(); break; }
      case "zoom": { const src = copy(ctx, W, H); ctx.save(); ctx.globalAlpha = .5; ctx.filter = "blur(4px)"; ctx.drawImage(src, -W * .04, -H * .04, W * 1.08, H * 1.08); ctx.restore(); break; }
    }
  }
  function shakeOffset(ids, t, W) {
    let a = 0;
    if (ids.includes("shake")) a = W * .016; else if (ids.includes("shake-soft")) a = W * .006;
    if (!a) return [0, 0];
    return [Math.sin(t * 61) * a, Math.cos(t * 53) * a];
  }
  // klip girisi gecisleri (studio.py _trans_in ile ayni sure mantigi)
  // u: dogrusal ilerleme, e: cubic ease-out (ffmpeg tarafiyla ayni egri)
  function transIn(kind, local, d) {
    const u = Math.min(1, Math.max(0, local / d)), e = 1 - Math.pow(1 - u, 3);
    const r = { alpha: 1, flash: 0, leak: 0, blur: 0, zoom: 1, dx: 0, dy: 0, rot: 0, pix: 0, mask: null, rgb: false };
    if (u >= 1) return r;
    if (kind === "fade") r.alpha = u;
    else if (kind === "flash") r.flash = .9 * (1 - u);
    else if (kind === "lightleak") { r.leak = .65 * (1 - u); r.flash = .25 * (1 - u); }
    else if (kind === "blur") r.blur = 20 * (1 - u);
    else if (kind === "pixel") r.pix = 1 - u;
    else if (kind === "zoom") r.zoom = 1.35 - .35 * e;
    else if (kind === "zoomblur") { r.zoom = 1.35 - .35 * e; r.blur = 20 * (1 - u); }
    else if (kind === "slide") r.dx = 1 - e;
    else if (kind === "slide-r") r.dx = -(1 - e);
    else if (kind === "slide-u") r.dy = 1 - e;
    else if (kind === "slide-d") r.dy = -(1 - e);
    else if (kind === "whip") { r.dx = 1 - e; r.blur = 18 * (1 - u); }
    else if (kind === "spin") r.rot = -90 * (1 - e);
    else if (kind === "shake-in") { const k = 1 - e; r.dx = .0125 * Math.sin(local * 73) * k; r.dy = .022 * Math.cos(local * 61) * k; }
    else if (kind === "glitch") r.rgb = true;
    else if (/^(wipe-|barn-|iris|eye|clock)/.test(kind)) r.mask = { kind, e };
    return r;
  }
  // maske gecisleri: tuval koordinatinda klip yolu (studio.py _trans_in geq maskeleriyle ayni sekiller)
  function transMask(ctx, m, W, H) {
    const e = m.e, cx = W / 2, cy = H / 2;
    ctx.beginPath();
    switch (m.kind) {
      case "wipe-r": ctx.rect(0, 0, W * e, H); break;
      case "wipe-l": ctx.rect(W * (1 - e), 0, W * e, H); break;
      case "wipe-d": ctx.rect(0, 0, W, H * e); break;
      case "wipe-u": ctx.rect(0, H * (1 - e), W, H * e); break;
      case "barn-v": ctx.rect(cx - e * cx, 0, W * e, H); break;
      case "barn-h": ctx.rect(0, cy - e * cy, W, H * e); break;
      case "iris": ctx.arc(cx, cy, Math.max(.5, e * Math.hypot(W, H) / 2), 0, Math.PI * 2); break;
      case "eye": {   // |y-cy| < e*H*1.2*sqrt(1-((x-cx)/(0.62W))^2)
        const rx = W * .62, steps = 48;
        for (let i = 0; i <= steps; i++) { const x = cx - rx + 2 * rx * i / steps, q = (x - cx) / rx; ctx.lineTo(x, cy - e * H * 1.2 * Math.sqrt(Math.max(0, 1 - q * q))); }
        for (let i = steps; i >= 0; i--) { const x = cx - rx + 2 * rx * i / steps, q = (x - cx) / rx; ctx.lineTo(x, cy + e * H * 1.2 * Math.sqrt(Math.max(0, 1 - q * q))); }
        break;
      }
      case "clock": { const R = Math.hypot(W, H); ctx.moveTo(cx, cy); ctx.arc(cx, cy, R, -Math.PI / 2, -Math.PI / 2 + e * Math.PI * 2); ctx.closePath(); break; }
      default: ctx.rect(0, 0, W, H);
    }
    ctx.clip();
  }
  // pikselden netles: kucult + en yakin komsu ile buyut (ffmpeg: scale=iw/32 + blend)
  const pixC = document.createElement("canvas"), pixG = pixC.getContext("2d"), pixO = document.createElement("canvas"), pixOG = pixO.getContext("2d");
  function pixelate(src, W, H, amt) {
    const f = 1 + 31 * amt, w = Math.max(1, Math.round(W / f)), h = Math.max(1, Math.round(H / f));
    pixC.width = w; pixC.height = h; pixG.drawImage(src, 0, 0, w, h);
    if (pixO.width !== W || pixO.height !== H) { pixO.width = W; pixO.height = H; }
    pixOG.clearRect(0, 0, W, H); pixOG.imageSmoothingEnabled = false; pixOG.drawImage(pixC, 0, 0, W, H);
    return pixO;
  }
  return { overlay, shakeOffset, transIn, transMask, pixelate, tint, copy };
})();
