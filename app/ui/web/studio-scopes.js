"use strict";
// Kami Studio Faz 9.3: Gercek zamanli Colorist Scopes (Waveform, RGB Parade, Vectorscope, Histogram, Zebra).
const SScopes = (() => {
  function samplePixels(srcCanvas, targetW = 160, targetH = 90) {
    const tmp = document.createElement("canvas");
    tmp.width = targetW;
    tmp.height = targetH;
    const ctx = tmp.getContext("2d", { willReadFrequently: true });
    ctx.drawImage(srcCanvas, 0, 0, targetW, targetH);
    return ctx.getImageData(0, 0, targetW, targetH);
  }

  function drawHistogram(imgData, outCanvas) {
    const { data } = imgData;
    const W = outCanvas.width, H = outCanvas.height;
    const ctx = outCanvas.getContext("2d");
    const hr = new Uint32Array(256), hg = new Uint32Array(256), hb = new Uint32Array(256);
    for (let i = 0; i < data.length; i += 4) {
      hr[data[i]]++;
      hg[data[i + 1]]++;
      hb[data[i + 2]]++;
    }
    let peak = 1;
    for (let i = 4; i < 252; i++) {
      peak = Math.max(peak, hr[i], hg[i], hb[i]);
    }
    ctx.fillStyle = "#09070E";
    ctx.fillRect(0, 0, W, H);
    ctx.globalCompositeOperation = "lighter";
    const chans = [[hr, "rgba(239,68,68,0.65)"], [hg, "rgba(46,230,166,0.65)"], [hb, "rgba(96,165,250,0.65)"]];
    for (const [hist, col] of chans) {
      ctx.fillStyle = col;
      ctx.beginPath();
      ctx.moveTo(0, H);
      for (let x = 0; x < 256; x++) {
        const px = (x / 255) * W;
        const py = H - Math.min(1, hist[x] / peak) * (H - 8);
        ctx.lineTo(px, py);
      }
      ctx.lineTo(W, H);
      ctx.closePath();
      ctx.fill();
    }
    ctx.globalCompositeOperation = "source-over";
  }

  function drawWaveform(imgData, outCanvas) {
    const { data, width, height } = imgData;
    const W = outCanvas.width, H = outCanvas.height;
    const ctx = outCanvas.getContext("2d");
    ctx.fillStyle = "#09070E";
    ctx.fillRect(0, 0, W, H);
    ctx.fillStyle = "rgba(46,230,166,0.22)";
    for (let x = 0; x < width; x++) {
      const ox = (x / width) * W;
      for (let y = 0; y < height; y++) {
        const idx = (y * width + x) * 4;
        const luma = 0.2126 * data[idx] + 0.7152 * data[idx + 1] + 0.0722 * data[idx + 2];
        const oy = H - (luma / 255) * H;
        ctx.fillRect(ox, oy, 1.5, 1.5);
      }
    }
  }

  function drawParade(imgData, outCanvas) {
    const { data, width, height } = imgData;
    const W = outCanvas.width, H = outCanvas.height;
    const ctx = outCanvas.getContext("2d");
    ctx.fillStyle = "#09070E";
    ctx.fillRect(0, 0, W, H);
    const third = W / 3;
    const cols = ["rgba(239,68,68,0.24)", "rgba(46,230,166,0.24)", "rgba(96,165,250,0.24)"];
    for (let c = 0; c < 3; c++) {
      ctx.fillStyle = cols[c];
      const baseX = c * third;
      for (let x = 0; x < width; x++) {
        const ox = baseX + (x / width) * third;
        for (let y = 0; y < height; y++) {
          const val = data[(y * width + x) * 4 + c];
          const oy = H - (val / 255) * H;
          ctx.fillRect(ox, oy, 1.4, 1.4);
        }
      }
    }
  }

  function drawVectorscope(imgData, outCanvas) {
    const { data } = imgData;
    const W = outCanvas.width, H = outCanvas.height;
    const ctx = outCanvas.getContext("2d");
    const cx = W / 2, cy = H / 2, rad = Math.min(W, H) * 0.44;
    ctx.fillStyle = "#09070E";
    ctx.fillRect(0, 0, W, H);
    ctx.strokeStyle = "rgba(167,139,250,0.25)";
    ctx.beginPath();
    ctx.arc(cx, cy, rad, 0, Math.PI * 2);
    ctx.stroke();
    ctx.fillStyle = "rgba(167,139,250,0.25)";
    for (let i = 0; i < data.length; i += 4) {
      const r = data[i] / 255, g = data[i + 1] / 255, b = data[i + 2] / 255;
      const cb = -0.1687 * r - 0.3313 * g + 0.5 * b;
      const cr = 0.5 * r - 0.4187 * g - 0.0813 * b;
      ctx.fillRect(cx + cb * rad * 2, cy - cr * rad * 2, 1.5, 1.5);
    }
  }

  function renderScope(srcCanvas, outCanvas, mode = "waveform") {
    if (!srcCanvas || !outCanvas) return;
    const imgData = samplePixels(srcCanvas);
    if (mode === "parade") return drawParade(imgData, outCanvas);
    if (mode === "vectorscope") return drawVectorscope(imgData, outCanvas);
    if (mode === "histogram") return drawHistogram(imgData, outCanvas);
    return drawWaveform(imgData, outCanvas);
  }

  return { renderScope, samplePixels, drawHistogram, drawWaveform, drawParade, drawVectorscope };
})();
