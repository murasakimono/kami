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
      case "bulge": { const src = copy(ctx, W, H); ctx.save(); ctx.drawImage(src, -W * .04, -H * .04, W * 1.08, H * 1.08); vignette(ctx, W, H, .2, "255,255,255"); ctx.restore(); break; }
      case "mirror-h": { const src = copy(ctx, W, H); ctx.save(); ctx.translate(W, 0); ctx.scale(-1, 1); ctx.drawImage(src, 0, 0, W / 2, H, 0, 0, W / 2, H); ctx.restore(); break; }
      case "mirror-v": { const src = copy(ctx, W, H); ctx.save(); ctx.translate(0, H); ctx.scale(1, -1); ctx.drawImage(src, 0, 0, W, H / 2, 0, 0, W, H / 2); ctx.restore(); break; }
      case "flip-h": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); ctx.translate(W, 0); ctx.scale(-1, 1); ctx.drawImage(src, 0, 0); ctx.restore(); break; }
      case "flip-v": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); ctx.translate(0, H); ctx.scale(1, -1); ctx.drawImage(src, 0, 0); ctx.restore(); break; }
      case "quad": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); for (let y = 0; y < 2; y++) for (let x = 0; x < 2; x++) ctx.drawImage(src, 0, 0, W, H, x * W / 2, y * H / 2, W / 2, H / 2); ctx.restore(); break; }
      case "split3-v": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); for (let i = 0; i < 3; i++) ctx.drawImage(src, W / 3, 0, W / 3, H, i * W / 3, 0, W / 3, H); ctx.restore(); break; }
      case "grid9": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); for (let y = 0; y < 3; y++) for (let x = 0; x < 3; x++) ctx.drawImage(src, 0, 0, W, H, x * W / 3, y * H / 3, W / 3, H / 3); ctx.restore(); break; }
      case "kaleido": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); ctx.drawImage(src, 0, 0, W / 2, H / 2, 0, 0, W / 2, H / 2);
        ctx.save(); ctx.translate(W, 0); ctx.scale(-1, 1); ctx.drawImage(src, 0, 0, W / 2, H / 2, 0, 0, W / 2, H / 2); ctx.restore();
        ctx.save(); ctx.translate(0, H); ctx.scale(1, -1); ctx.drawImage(src, 0, 0, W / 2, H / 2, 0, 0, W / 2, H / 2); ctx.restore();
        ctx.save(); ctx.translate(W, H); ctx.scale(-1, -1); ctx.drawImage(src, 0, 0, W / 2, H / 2, 0, 0, W / 2, H / 2); ctx.restore(); ctx.restore(); break; }
      case "zoom-crop": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); ctx.drawImage(src, W * .115, H * .115, W / 1.3, H / 1.3, 0, 0, W, H); ctx.restore(); break; }
      case "mirror-floor": { const src = copy(ctx, W, H); ctx.save(); ctx.clearRect(0, 0, W, H); ctx.drawImage(src, 0, 0, W, H * .72, 0, 0, W, H * .72);
        ctx.save(); ctx.translate(0, H); ctx.scale(1, -1); ctx.globalAlpha = .72; ctx.drawImage(src, 0, 0, W, H * .28, 0, 0, W, H * .28); ctx.restore(); ctx.restore(); break; }
      case "pillarbox": { const src = copy(ctx, W, H); ctx.save(); ctx.filter = "blur(18px) brightness(.9)"; ctx.drawImage(src, 0, 0); ctx.filter = "none"; ctx.drawImage(src, W * .22, H * .22, W * .56, H * .56); ctx.restore(); break; }
      case "pillarbox-9x16": { const src = copy(ctx, W, H); const cw = Math.min(W, H * 9 / 16); ctx.save(); ctx.fillStyle = "#000"; ctx.fillRect(0, 0, W, H); ctx.drawImage(src, (W - cw) / 2, 0, cw, H, (W - cw) / 2, 0, cw, H); ctx.restore(); break; }
      case "frame-white": { const src = copy(ctx, W, H); ctx.save(); ctx.fillStyle = "#fff"; ctx.fillRect(0, 0, W, H); ctx.drawImage(src, W * .05, H * .05, W * .9, H * .9); ctx.restore(); break; }
      case "frame-polaroid": { const src = copy(ctx, W, H); ctx.save(); ctx.fillStyle = "#f4f1ea"; ctx.fillRect(0, 0, W, H); ctx.drawImage(src, W * .08, H * .06, W * .84, H * .78); ctx.restore(); break; }
      case "frame-rec": { ctx.save(); ctx.strokeStyle = "rgba(255,255,255,.45)"; ctx.lineWidth = Math.max(2, W / 640); ctx.strokeRect(W * .018, H * .025, W * .964, H * .95);
        if ((t * 2) % 1 < .65) { ctx.fillStyle = "#ff2a2a"; const s = Math.max(8, W * .013); ctx.fillRect(W * .035, H * .045, s, s); } ctx.restore(); break; }
      case "pulse": tint(ctx, W, H, "#fff", "lighter", Math.abs(Math.sin(t * Math.PI * 2)) * .16); break;
      case "crisp": vignette(ctx, W, H, .08); break;
      case "halation": {
        const src = copy(ctx, W, H);
        ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = .38;
        ctx.filter = `blur(${Math.max(4, Math.round(W / 60))}px) sepia(1) saturate(4) hue-rotate(-35deg)`;
        ctx.drawImage(src, 0, 0); ctx.restore(); break;
      }
      case "prism": {
        const s = 6 * W / 1280, src = copy(ctx, W, H);
        ctx.save(); ctx.globalCompositeOperation = "screen"; ctx.globalAlpha = .35;
        ctx.filter = "hue-rotate(-40deg) saturate(2)"; ctx.drawImage(src, -s, -s * .5);
        ctx.filter = "hue-rotate(150deg) saturate(2)"; ctx.drawImage(src, s, s * .5);
        ctx.restore(); break;
      }
      case "paper-grain": {
        ctx.save(); ctx.globalCompositeOperation = "multiply"; ctx.globalAlpha = .16;
        const n = noiseTiles()[0]; ctx.fillStyle = ctx.createPattern(n, "repeat"); ctx.fillRect(0, 0, W, H); ctx.restore(); break;
      }
      case "rain": {
        ctx.save(); ctx.strokeStyle = "rgba(180,220,255,.35)"; ctx.lineWidth = Math.max(1, W / 960);
        for (let i = 0; i < 42; i++) {
          const rx = rnd(i * 17 + f * 3) * W, ry = ((rnd(i * 31) + t * (1.8 + rnd(i) * .8)) % 1) * H;
          ctx.beginPath(); ctx.moveTo(rx, ry); ctx.lineTo(rx - 4 * W / 1280, ry + 26 * H / 720); ctx.stroke();
        }
        ctx.restore(); break;
      }
      case "snow": {
        ctx.save(); ctx.fillStyle = "rgba(255,255,255,.72)";
        for (let i = 0; i < 36; i++) {
          const sx = (rnd(i * 19) + Math.sin(t * 1.4 + i) * .02) * W, sy = ((rnd(i * 23) + t * (.22 + rnd(i) * .2)) % 1) * H;
          ctx.beginPath(); ctx.arc(sx, sy, Math.max(1.5, (1.5 + rnd(i * 7) * 2.5) * W / 1280), 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore(); break;
      }
      case "sparks": {
        ctx.save(); ctx.globalCompositeOperation = "lighter";
        for (let i = 0; i < 28; i++) {
          const ex = (rnd(i * 29) + Math.sin(t * 2.5 + i) * .04) * W, ey = (1 - ((rnd(i * 11) + t * (.35 + rnd(i) * .3)) % 1)) * H;
          ctx.fillStyle = i % 2 ? "rgba(255,140,40,.85)" : "rgba(255,220,100,.8)";
          ctx.beginPath(); ctx.arc(ex, ey, Math.max(1.5, 2.2 * W / 1280), 0, Math.PI * 2); ctx.fill();
        }
        ctx.restore(); break;
      }
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
    // faz 5b (studio_trans2.py ile ayni egriler)
    else if (kind === "pop-in") { r.sx = r.sy = .3 + .7 * e; }
    else if (kind === "bounce-in") { const b = 1 + 2.70158 * Math.pow(u - 1, 3) + 1.70158 * Math.pow(u - 1, 2); r.sx = r.sy = Math.max(.05, b); }
    else if (kind === "flip-h") r.sx = Math.max(.02, e);
    else if (kind === "flip-v") r.sy = Math.max(.02, e);
    else if (kind === "dip-black") r.dark = .9 * (1 - u);
    else if (kind === "dip-pink") r.pink = .55 * (1 - u);
    else if (kind === "dip-cyan") r.cyan = .55 * (1 - u);
    else if (kind === "whip-v") { r.dy = 1 - e; r.blur = 18 * (1 - u); }
    else if (kind === "spin180") r.rot = -180 * (1 - e);
    else if (kind === "vhs-roll") { r.roll = 1 - u; r.rgb = true; }
    else if (kind === "cube-l") { r.sx = Math.max(.05, e); r.dx = .45 * (1 - e); }
    else if (kind === "cube-r") { r.sx = Math.max(.05, e); r.dx = -.45 * (1 - e); }
    else if (kind === "rgb-tear") r.rgb = true;
    else if (kind === "zoom-spin") { r.zoom = 1.6 - .6 * e; r.rot = -135 * (1 - e); }
    else if (kind === "lens-flare") { r.flash = .65 * Math.exp(-Math.pow((u - .15) * 4, 2)); r.leak = .4 * (1 - u); }
    else if (kind === "burn-wipe") { r.leak = .55 * (1 - u); r.mask = { kind: "wipe-r", e }; }
    else if (kind === "glitch-snap") { r.rgb = true; r.dx = .014 * Math.sin(local * 120) * (1 - u); }
    else if (kind === "iris-in") r.mask = { kind: "iris", e };
    else if (kind === "flash-warm") { r.flash = .45 * (1 - u); r.leak = .65 * (1 - u); }
    else if (kind === "whip-blur-fast") { r.dx = 1 - e; r.blur = 24 * (1 - u); }
    // Dalga 7 (TRANS_PACK2)
    else if (kind === "morph-zoom" || kind === "zoom-elastic-out") { r.zoom = (kind === "morph-zoom" ? 1.65 - .65 * e : 1 + .45 * (1 - e)); if (kind === "morph-zoom") r.blur = 8 * (1 - u); }
    else if (kind === "elastic-pop") { const el = 1 - Math.pow(2, -10 * u) * Math.cos(u * Math.PI * 3.5); r.sx = r.sy = Math.max(.2, .5 + .5 * el); }
    else if (kind === "hyper-whip-r") { r.dx = -(1 - e); r.blur = 28 * (1 - u); }
    else if (kind === "hyper-whip-l") { r.dx = 1 - e; r.blur = 28 * (1 - u); }
    else if (kind === "prism-swipe") { r.dx = 1 - e; r.rgb = true; }
    else if (kind === "kaleido-spin") { r.rot = 180 * (1 - e); r.rgb = true; }
    else if (kind === "burn-flash") r.flash = .75 * (1 - u);
    else if (kind === "burn-orange") { r.flash = .3 * (1 - u); r.leak = .85 * (1 - u); }
    else if (kind === "glitch-tear-v" || kind === "glass-shatter") { r.rgb = true; r.dx = .012 * Math.sin(local * 95) * (1 - u); }
    else if (kind === "squeeze-h") r.sx = Math.max(.04, e);
    else if (kind === "squeeze-v") r.sy = Math.max(.04, e);
    else if (kind === "prism-whip") { r.rgb = true; r.blur = 16 * (1 - u); r.dx = .45 * (1 - e); }
    else if (kind === "broken-glass-cut") { r.rgb = true; r.flash = .45 * (1 - u); }
    else if (kind === "burning-edge") { r.leak = .85 * (1 - u); r.mask = { kind: "wipe-r", e }; }
    else if (kind === "datamosh-cut") { r.rgb = true; r.dx = .02 * Math.sin(local * 110) * (1 - u); }
    else if (kind === "camera-flash-bulb") { r.flash = .92 * Math.exp(-Math.pow(u * 4.2, 2)); }
    else if (/^(liquid-splash-wipe|retro-tv-off|kinetic-tile-flip|ink-splatter-wipe|cyberpunk-slice|liquid-drip|crt-off|crt-on|ink-splat|strip-blind-|paper-tear-slide|checker-dissolve|tile-flip)/.test(kind)) r.mask = { kind, e };
    else if (/^(wipe-|barn-|iris|eye|clock|diag-|wave-wipe|corner|diamond|heart|cross|blinds-|checker|stripes|blocks|dissolve|page-curl|split-curtain)/.test(kind)) r.mask = { kind, e };
    return r;
  }
  const TRANS2_MASK = {
    "liquid-splash-wipe": (c, e, W, H) => { c.moveTo(0, 0); c.lineTo(W, 0); c.lineTo(W, H * e); for (let x = W; x >= 0; x -= W / 30) c.lineTo(x, H * e + Math.sin(x * .03) * H * .08 * (1 - e)); },
    "retro-tv-off": (c, e, W, H) => { const h = Math.max(3, H * e); c.rect(0, (H - h) / 2, W, h); },
    "kinetic-tile-flip": (c, e, W, H) => { const bw = W / 6; for (let i = 0; i < 6; i++) c.rect(i * bw, 0, bw * e + 1, H); },
    "ink-splatter-wipe": (c, e, W, H) => { const r = Math.hypot(W, H) * .62 * e; for (let i = 0; i <= 48; i++) { const a = (i / 48) * Math.PI * 2, rr = Math.max(1, r + Math.sin(a * 7) * W * .05); const px = W / 2 + Math.cos(a) * rr, py = H / 2 + Math.sin(a) * rr; i ? c.lineTo(px, py) : c.moveTo(px, py); } c.closePath(); },
    "cyberpunk-slice": (c, e, W, H) => { const bh = H / 8; for (let i = 0; i < 8; i++) { const off = (i % 2) * W * .45; c.rect(0, i * bh, Math.max(0, W * e * 1.45 - off), bh + 1); } },
    "liquid-drip": (c, e, W, H) => { c.moveTo(0, 0); c.lineTo(W, 0); c.lineTo(W, H * e); for (let x = W; x >= 0; x -= W / 24) c.lineTo(x, H * e + Math.sin(x / 28) * 28 * (1 - e)); },
    "crt-off": (c, e, W, H) => { const h = Math.max(3, H * (1 - e)); c.rect(0, (H - h) / 2, W, h); },
    "crt-on": (c, e, W, H) => { const h = Math.max(3, H * e); c.rect(0, (H - h) / 2, W, h); },
    "ink-splat": (c, e, W, H) => { c.arc(W / 2, H / 2, Math.max(2, e * Math.hypot(W, H) * .6), 0, Math.PI * 2); },
    "strip-blind-v": (c, e, W, H) => { for (let i = 0; i < 8; i++) c.rect(i * W / 8, 0, e * W / 8 + 1, H); },
    "strip-blind-h": (c, e, W, H) => { for (let i = 0; i < 6; i++) c.rect(0, i * H / 6, W, e * H / 6 + 1); },
    "paper-tear-slide": (c, e, W, H) => { c.moveTo(0, 0); for (let y = 0; y <= H; y += H / 24) c.lineTo(W * e + Math.sin(y / 14) * 14, y); c.lineTo(0, H); },
    "checker-dissolve": (c, e, W, H) => { const bw = W / 10, bh = H / 8; for (let i = 0; i < 10; i++) for (let j = 0; j < 8; j++) if (((i + j) % 2) * .5 < e) c.rect(i * bw, j * bh, bw + 1, bh + 1); },
    "tile-flip": (c, e, W, H) => { const bw = W / 6, bh = H / 4; for (let i = 0; i < 6; i++) for (let j = 0; j < 4; j++) c.rect(i * bw, j * bh, bw * e + 1, bh * e + 1); },
    "page-curl": (c, e, W, H) => { const p = 1.5 * e; c.moveTo(0, 0); c.lineTo(W * p, 0); c.lineTo(0, H * 2 * p); },
    "split-curtain": (c, e, W, H) => { c.rect(0, 0, W * e * .5, H); c.rect(W * (1 - e * .5), 0, W * e * .5, H); },
    "diag-tl": (c, e, W, H) => { c.moveTo(0, 0); c.lineTo(2 * e * W, 0); c.lineTo(0, 2 * e * H); },
    "diag-br": (c, e, W, H) => { c.moveTo(W, H); c.lineTo(W - 2 * e * W, H); c.lineTo(W, H - 2 * e * H); },
    "diag-tr": (c, e, W, H) => { c.moveTo(W, 0); c.lineTo(W - 2 * e * W, 0); c.lineTo(W, 2 * e * H); },
    "diag-bl": (c, e, W, H) => { c.moveTo(0, H); c.lineTo(2 * e * W, H); c.lineTo(0, H - 2 * e * H); },
    "wipe-soft": (c, e, W, H) => { c.rect(0, 0, W * 1.25 * e - W * .125, H); },
    "wave-wipe": (c, e, W, H) => { c.moveTo(0, 0); for (let y = 0; y <= H; y += H / 40) c.lineTo(W * 1.1 * e - W * .05 + Math.sin(y / H * 14) * W * .04 * (1 - e), y); c.lineTo(0, H); },
    "corner": (c, e, W, H) => { c.moveTo(0, 0); c.arc(0, 0, Math.max(.5, e * Math.hypot(W, H)), 0, Math.PI / 2); },
    "diamond": (c, e, W, H) => { c.moveTo(W / 2, H / 2 - e * H); c.lineTo(W / 2 + e * W, H / 2); c.lineTo(W / 2, H / 2 + e * H); c.lineTo(W / 2 - e * W, H / 2); },
    "heart": (c, e, W, H) => { if (e > .999) { c.rect(0, 0, W, H); return; } const s = H * e * .9 + 1;
      for (let i = 0; i <= 64; i++) { const t = i / 64 * Math.PI * 2, x = Math.pow(Math.sin(t), 3) * .3, y = (13 * Math.cos(t) - 5 * Math.cos(2 * t) - 2 * Math.cos(3 * t) - Math.cos(4 * t)) / 16 * .3;
        c.lineTo(W / 2 + x * s, H * .45 - y * s); } },
    "cross": (c, e, W, H) => { c.rect(W / 2 - e * W / 2, 0, e * W, H); c.rect(0, H / 2 - e * H / 2, W, e * H); },
    "blinds-h": (c, e, W, H) => { for (let i = 0; i < 8; i++) c.rect(0, i * H / 8, W, e * H / 8 + 1); },
    "blinds-v": (c, e, W, H) => { for (let i = 0; i < 10; i++) c.rect(i * W / 10, 0, e * W / 10 + 1, H); },
    "checker": (c, e, W, H) => { const bw = W / 8, bh = H / 6; for (let i = 0; i < 8; i++) for (let j = 0; j < 6; j++) { const p = ((i + j) % 2) * .5, k = Math.max(0, Math.min(1, (e - p) * 2)); if (k > 0) c.rect(i * bw, j * bh, bw * k, bh); } },
    "stripes": (c, e, W, H) => { const s = W / 6; for (let k = -H; k < W + H; k += s) { c.moveTo(k, 0); c.lineTo(k + e * s + 1, 0); c.lineTo(k + e * s + 1 - H, H); c.lineTo(k - H, H); c.closePath(); } },
    "blocks": (c, e, W, H) => { const bw = W / 16, bh = H / 9; for (let i = 0; i < 16; i++) for (let j = 0; j < 9; j++) if (((i * 7 + j * 13) % 17) / 17 < e * 1.06) c.rect(i * bw, j * bh, bw + .5, bh + .5); },
    "dissolve": (c, e, W, H) => { const b = Math.max(14, Math.round(W / 60)); for (let x = 0; x < W; x += b) for (let y = 0; y < H; y += b) { const h = Math.sin(x * 12.9898 + y * 78.233) * 43758.5453; if (h - Math.floor(h) < e * 1.05) c.rect(x, y, b, b); } },
  };
  // maske gecisleri: tuval koordinatinda klip yolu (studio.py _trans_in geq maskeleriyle ayni sekiller)
  function transMask(ctx, m, W, H) {
    const e = m.e, cx = W / 2, cy = H / 2;
    ctx.beginPath();
    if (TRANS2_MASK[m.kind]) { TRANS2_MASK[m.kind](ctx, e, W, H); ctx.clip(); return; }
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

  // Faz 7.3: Akilli Kare / Segment Onbellegi (LRU) + WebCodecs yetenek bilgisi
  function createSmartCache(maxEntries = 48) {
    const map = new Map();
    let hits = 0, misses = 0;
    const keyOf = (clipId, frameIdx, sig = "") => `${clipId}|${frameIdx}|${sig}`;
    function get(clipId, frameIdx, sig = "") {
      const k = keyOf(clipId, frameIdx, sig);
      if (!map.has(k)) { misses++; return null; }
      const val = map.get(k);
      map.delete(k);
      map.set(k, val);
      hits++;
      return val;
    }
    function put(clipId, frameIdx, sig, bitmap) {
      const k = keyOf(clipId, frameIdx, sig);
      if (map.has(k)) {
        const prev = map.get(k);
        if (prev && prev !== bitmap && typeof prev.close === "function") { try { prev.close(); } catch {} }
        map.delete(k);
      }
      map.set(k, bitmap);
      while (map.size > maxEntries) {
        const oldestKey = map.keys().next().value;
        const oldest = map.get(oldestKey);
        map.delete(oldestKey);
        if (oldest && typeof oldest.close === "function") { try { oldest.close(); } catch {} }
      }
      return bitmap;
    }
    function invalidate(clipId) {
      const prefix = `${clipId}|`;
      for (const [k, v] of [...map.entries()]) {
        if (k.startsWith(prefix)) {
          map.delete(k);
          if (v && typeof v.close === "function") { try { v.close(); } catch {} }
        }
      }
    }
    function clear() {
      for (const v of map.values()) {
        if (v && typeof v.close === "function") { try { v.close(); } catch {} }
      }
      map.clear();
      hits = 0;
      misses = 0;
    }
    function stats() {
      const total = hits + misses;
      return { size: map.size, maxEntries, hits, misses, hitRate: total ? +(hits / total).toFixed(3) : 0 };
    }
    return { get, put, has: (c, f, s = "") => map.has(keyOf(c, f, s)), invalidate, clear, stats };
  }

  const SmartCache = createSmartCache(48);
  function webCodecsInfo() {
    return {
      videoDecoder: typeof VideoDecoder !== "undefined",
      videoEncoder: typeof VideoEncoder !== "undefined",
      crossOriginIsolated: typeof window !== "undefined" ? Boolean(window.crossOriginIsolated) : false,
      sharedArrayBuffer: typeof SharedArrayBuffer !== "undefined",
    };
  }

  function evalBezier(p1x, p1y, p2x, p2y, u) {
    u = Math.max(0, Math.min(1, u));
    if (u <= 0) return 0; if (u >= 1) return 1;
    const ax = 3 * p1x - 3 * p2x + 1, bx = 3 * p2x - 6 * p1x, cx = 3 * p1x;
    let t = u;
    for (let i = 0; i < 6; i++) {
      const xt = ((ax * t + bx) * t + cx) * t - u;
      const dx = (3 * ax * t + 2 * bx) * t + cx;
      if (Math.abs(xt) < 1e-5 || Math.abs(dx) < 1e-6) break;
      t = Math.max(0, Math.min(1, t - xt / dx));
    }
    const t2 = t * t, t3 = t2 * t, mt = 1 - t;
    return 3 * mt * mt * t * p1y + 3 * mt * t2 * p2y + t3;
  }

  const BLEND_JS = {
    normal: "source-over", screen: "screen", overlay: "overlay", multiply: "multiply",
    lighten: "lighten", darken: "darken", dodge: "color-dodge", difference: "difference", addition: "lighter",
  };

  const maskC = document.createElement("canvas"), maskG = maskC.getContext("2d");
  const shapeC = document.createElement("canvas"), shapeG = shapeC.getContext("2d");
  function _drawMaskShape(g, mask, W, H) {
    const t = mask.type;
    const cx = (mask.x ?? 0.5) * W, cy = (mask.y ?? 0.5) * H;
    const rx = Math.max(2, (mask.w ?? 0.55) * W * 0.5), ry = Math.max(2, (mask.h ?? 0.55) * H * 0.5);
    const rad = ((mask.rot || 0) * Math.PI) / 180;
    g.save();
    g.translate(cx, cy);
    if (rad) g.rotate(rad);
    g.beginPath();
    if (t === "circle") g.ellipse(0, 0, rx, ry, 0, 0, Math.PI * 2);
    else if (t === "rect") g.rect(-rx, -ry, rx * 2, ry * 2);
    else if (t === "split") g.rect(-W * 2, -H * 2, W * 2, H * 4);
    else if (t === "mirror") g.rect(-W * 2, -ry, W * 4, ry * 2);
    else if (t === "filmstrip") {
      const sw = Math.max(8, W / 5), gap = sw * 0.14;
      for (let x = -W; x < W; x += sw) g.rect(x - sw * 0.5 + gap, -ry, sw - gap, ry * 2);
    } else if (t === "star") {
      for (let i = 0; i < 10; i++) {
        const a = -Math.PI / 2 + (i * Math.PI) / 5, r = i % 2 === 0 ? 1 : 0.42;
        const px = Math.cos(a) * rx * r, py = Math.sin(a) * ry * r;
        i ? g.lineTo(px, py) : g.moveTo(px, py);
      }
      g.closePath();
    } else if (t === "heart") {
      for (let i = 0; i <= 64; i++) {
        const a = (i / 64) * Math.PI * 2;
        const hx = Math.pow(Math.sin(a), 3), hy = -(13 * Math.cos(a) - 5 * Math.cos(2 * a) - 2 * Math.cos(3 * a) - Math.cos(4 * a)) / 16;
        const px = hx * rx * 0.85, py = (hy + 0.15) * ry * 0.85;
        i ? g.lineTo(px, py) : g.moveTo(px, py);
      }
      g.closePath();
    }
    g.restore();
  }
  function applyMask(src, mask, W, H, PS = 1) {
    if (!mask || !mask.type || mask.type === "none") return src;
    if (maskC.width !== W || maskC.height !== H) { maskC.width = shapeC.width = W; maskC.height = shapeC.height = H; }
    shapeG.setTransform(1, 0, 0, 1, 0, 0);
    shapeG.clearRect(0, 0, W, H);
    shapeG.fillStyle = "#fff";
    if (mask.invert) {
      shapeG.fillRect(0, 0, W, H);
      shapeG.globalCompositeOperation = "destination-out";
    }
    _drawMaskShape(shapeG, mask, W, H);
    shapeG.fill();
    shapeG.globalCompositeOperation = "source-over";

    maskG.setTransform(1, 0, 0, 1, 0, 0);
    maskG.clearRect(0, 0, W, H);
    maskG.globalCompositeOperation = "source-over";
    maskG.filter = "none";
    maskG.drawImage(src, 0, 0, W, H);
    maskG.globalCompositeOperation = "destination-in";
    if ((mask.feather || 0) > 0.5) maskG.filter = `blur(${(mask.feather * PS).toFixed(1)}px)`;
    maskG.drawImage(shapeC, 0, 0);
    maskG.filter = "none";
    maskG.globalCompositeOperation = "source-over";
    return maskC;
  }

  return { overlay, shakeOffset, transIn, transMask, pixelate, tint, copy, SmartCache, createSmartCache, webCodecsInfo, evalBezier, BLEND_JS, applyMask };
})();
