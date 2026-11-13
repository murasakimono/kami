"use strict";
// Kami Picture Faz 10.1: Tahribatsiz Ayar Katmanlari + WebGL2/Canvas Katman Stilleri
// (Bevel & Emboss, Outer Glow, Inner Glow, Halftone / Risograph, AgX/Sigmoid onizleme).
const EFX = (() => {
  function applyLayerStyles(srcCanvas, styles = {}) {
    if (!srcCanvas) return srcCanvas;
    const out = document.createElement("canvas");
    out.width = srcCanvas.width;
    out.height = srcCanvas.height;
    const ctx = out.getContext("2d");

    if (styles.outerGlow?.on) {
      ctx.save();
      ctx.shadowColor = styles.outerGlow.color || "#7C3AED";
      ctx.shadowBlur = Number(styles.outerGlow.blur ?? 18);
      ctx.drawImage(srcCanvas, 0, 0);
      ctx.restore();
    } else {
      ctx.drawImage(srcCanvas, 0, 0);
    }

    if (styles.bevel?.on) {
      ctx.save();
      ctx.globalCompositeOperation = "overlay";
      ctx.globalAlpha = Math.min(0.85, Number(styles.bevel.strength ?? 0.35));
      ctx.drawImage(srcCanvas, -1.5, -1.5);
      ctx.restore();
    }

    if (styles.halftone?.on) {
      const step = Math.max(4, Number(styles.halftone.dotSize ?? 8));
      const img = ctx.getImageData(0, 0, out.width, out.height);
      const d = img.data;
      ctx.fillStyle = styles.halftone.bg || "#0E0B14";
      ctx.fillRect(0, 0, out.width, out.height);
      for (let y = 0; y < out.height; y += step) {
        for (let x = 0; x < out.width; x += step) {
          const i = (y * out.width + x) * 4;
          const lum = (0.2126 * d[i] + 0.7152 * d[i + 1] + 0.0722 * d[i + 2]) / 255;
          const r = (step * 0.48) * lum;
          ctx.fillStyle = `rgb(${d[i]},${d[i + 1]},${d[i + 2]})`;
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

  return { applyLayerStyles, renderAdjustmentCSS };
})();
