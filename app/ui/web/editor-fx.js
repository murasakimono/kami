"use strict";
// Kami Picture: Tahribatsiz Katman Stilleri (Drop Shadow, Stroke, Outer/Inner Glow,
// Color/Gradient Overlay, Bevel & Emboss, Halftone) + Ayar CSS yardimcisi.
const EFX = (() => {
  function hasActiveStyles(styles) {
    if (!styles || typeof styles !== "object") return false;
    return !!(
      styles.dropShadow?.on ||
      styles.stroke?.on ||
      styles.outerGlow?.on ||
      styles.innerGlow?.on ||
      styles.colorOverlay?.on ||
      styles.gradientOverlay?.on ||
      styles.bevel?.on ||
      styles.halftone?.on
    );
  }

  function applyLayerStyles(srcCanvas, styles = {}) {
    if (!srcCanvas || !hasActiveStyles(styles)) return srcCanvas;
    const w = srcCanvas.width;
    const h = srcCanvas.height;
    const out = document.createElement("canvas");
    out.width = w;
    out.height = h;
    const ctx = out.getContext("2d");

    // 1. Dis Golge (Drop Shadow)
    if (styles.dropShadow?.on) {
      ctx.save();
      ctx.globalAlpha = Math.max(0.05, Math.min(1, Number(styles.dropShadow.opacity ?? 0.65)));
      ctx.shadowColor = styles.dropShadow.color || "#000000";
      ctx.shadowBlur = Math.max(0, Number(styles.dropShadow.blur ?? 14));
      ctx.shadowOffsetX = Number(styles.dropShadow.dx ?? 6);
      ctx.shadowOffsetY = Number(styles.dropShadow.dy ?? 8);
      ctx.drawImage(srcCanvas, 0, 0);
      ctx.restore();
    }

    // 2. Dis Isima (Outer Glow)
    if (styles.outerGlow?.on) {
      ctx.save();
      ctx.shadowColor = styles.outerGlow.color || "#8B5CF6";
      ctx.shadowBlur = Math.max(1, Number(styles.outerGlow.blur ?? 18));
      ctx.shadowOffsetX = 0;
      ctx.shadowOffsetY = 0;
      ctx.drawImage(srcCanvas, 0, 0);
      ctx.restore();
    }

    // 3. Kontur (Stroke — 16 yonlu temiz alfa genisletme)
    if (styles.stroke?.on && Number(styles.stroke.width || 0) > 0) {
      const sw = Math.max(1, Math.min(40, Number(styles.stroke.width || 3)));
      const sil = document.createElement("canvas");
      sil.width = w;
      sil.height = h;
      const sg = sil.getContext("2d");
      sg.drawImage(srcCanvas, 0, 0);
      sg.globalCompositeOperation = "source-in";
      sg.fillStyle = styles.stroke.color || "#FFFFFF";
      sg.fillRect(0, 0, w, h);
      const steps = Math.max(8, Math.min(24, Math.round(sw * 2.4)));
      ctx.save();
      for (let i = 0; i < steps; i++) {
        const a = (i / steps) * Math.PI * 2;
        ctx.drawImage(sil, Math.cos(a) * sw, Math.sin(a) * sw);
      }
      ctx.restore();
    }

    // Ana icerik katmani (Color/Gradient Overlay ve Inner Glow icin gecici tuval)
    const body = document.createElement("canvas");
    body.width = w;
    body.height = h;
    const bg = body.getContext("2d");
    bg.drawImage(srcCanvas, 0, 0);

    // 4. Renk Kaplama (Color Overlay)
    if (styles.colorOverlay?.on) {
      bg.save();
      bg.globalCompositeOperation = "source-atop";
      bg.globalAlpha = Math.max(0.05, Math.min(1, Number(styles.colorOverlay.opacity ?? 0.65)));
      bg.fillStyle = styles.colorOverlay.color || "#8B5CF6";
      bg.fillRect(0, 0, w, h);
      bg.restore();
    }

    // 5. Degrade Kaplama (Gradient Overlay)
    if (styles.gradientOverlay?.on) {
      const rad = (Number(styles.gradientOverlay.angle ?? 135) * Math.PI) / 180;
      const cx = w / 2, cy = h / 2;
      const r = Math.hypot(cx, cy);
      const grd = bg.createLinearGradient(
        cx - Math.cos(rad) * r, cy - Math.sin(rad) * r,
        cx + Math.cos(rad) * r, cy + Math.sin(rad) * r
      );
      grd.addColorStop(0, styles.gradientOverlay.color1 || "#8B5CF6");
      grd.addColorStop(1, styles.gradientOverlay.color2 || "#2EE6A6");
      bg.save();
      bg.globalCompositeOperation = "source-atop";
      bg.globalAlpha = Math.max(0.05, Math.min(1, Number(styles.gradientOverlay.opacity ?? 0.75)));
      bg.fillStyle = grd;
      bg.fillRect(0, 0, w, h);
      bg.restore();
    }

    // 6. Ic Isima (Inner Glow)
    if (styles.innerGlow?.on) {
      const inv = document.createElement("canvas");
      inv.width = w;
      inv.height = h;
      const ig = inv.getContext("2d");
      ig.fillStyle = styles.innerGlow.color || "#2EE6A6";
      ig.fillRect(0, 0, w, h);
      ig.globalCompositeOperation = "destination-out";
      ig.drawImage(srcCanvas, 0, 0);
      bg.save();
      bg.globalCompositeOperation = "source-atop";
      bg.shadowColor = styles.innerGlow.color || "#2EE6A6";
      bg.shadowBlur = Math.max(2, Number(styles.innerGlow.blur ?? 16));
      bg.drawImage(inv, 0, 0);
      bg.restore();
    }

    // 7. Egim & Kabartma (Bevel & Emboss)
    if (styles.bevel?.on) {
      const str = Math.min(0.85, Math.max(0.05, Number(styles.bevel.strength ?? 0.4)));
      bg.save();
      bg.globalCompositeOperation = "source-atop";
      bg.globalAlpha = str;
      bg.filter = "brightness(1.45)";
      bg.drawImage(srcCanvas, -2, -2);
      bg.filter = "brightness(0.55)";
      bg.drawImage(srcCanvas, 2, 2);
      bg.filter = "none";
      bg.restore();
    }

    ctx.drawImage(body, 0, 0);

    // 8. Halftone / Risograph
    if (styles.halftone?.on) {
      const step = Math.max(4, Number(styles.halftone.dotSize ?? 8));
      const img = ctx.getImageData(0, 0, w, h);
      const d = img.data;
      ctx.clearRect(0, 0, w, h);
      if (styles.halftone.bg) {
        ctx.fillStyle = styles.halftone.bg;
        ctx.fillRect(0, 0, w, h);
      }
      for (let y = 0; y < h; y += step) {
        for (let x = 0; x < w; x += step) {
          const i = (y * w + x) * 4;
          if (d[i + 3] < 12) continue;
          const lum = (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
          const r = (step * 0.48) * lum;
          ctx.fillStyle = `rgba(${d[i]},${d[i + 1]},${d[i + 2]},${(d[i + 3] / 255).toFixed(2)})`;
          ctx.beginPath();
          ctx.arc(x + step / 2, y + step / 2, r, 0, Math.PI * 2);
          ctx.fill();
        }
      }
    }
    return out;
  }

  function renderAdjustmentCSS(adj = {}) {
    const exp = Number(adj.exposure || 0);
    const bri = Math.max(0.2, 1 + exp * 0.35);
    const con = Math.max(0.2, 1 + Number(adj.clarity || 0) * 0.25);
    const sat = Math.max(0.0, 1 + Number(adj.vibrance || 0) * 0.4);
    return `brightness(${bri.toFixed(2)}) contrast(${con.toFixed(2)}) saturate(${sat.toFixed(2)})`;
  }

  return { hasActiveStyles, applyLayerStyles, renderAdjustmentCSS };
})();
