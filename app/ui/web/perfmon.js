/* Kami v1.30 performans izleyici: Ctrl+Shift+P (ya da Ctrl+K > "Performans izleyici"). Suruklenebilir kucuk panel:
   sistem CPU/RAM/GPU, Kami'nin kendi payi (WebView2, aria2, ffmpeg, yt-dlp, yapay zeka ayri), disk ve ag hizi. */
(function () {
  const P = { on: false, el: null, t: 0, hist: [] };
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const B = (n) => { n = +n || 0; const u = ["B", "KB", "MB", "GB"]; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return n.toFixed(i > 1 ? 1 : 0) + " " + u[i]; };
  const css = document.createElement("style");
  css.textContent = `#kperf{position:fixed;right:16px;bottom:16px;z-index:9998;width:290px;background:#0F0B16f2;border:1px solid rgba(167,139,250,.35);border-radius:12px;
   box-shadow:0 12px 40px #000a;color:#E7E2EF;font:12px/1.45 "Segoe UI",system-ui,sans-serif;padding:10px 12px;user-select:none}
  #kperf h6{margin:0 0 6px;font:600 11px "Chakra Petch","Segoe UI",sans-serif;letter-spacing:2px;text-transform:uppercase;color:#A78BFA;cursor:move;display:flex}
  #kperf h6 span{flex:1}#kperf h6 b{cursor:pointer;color:#8E86A3;font-weight:400}
  #kperf .r{display:grid;grid-template-columns:62px 1fr 64px;gap:6px;align-items:center;margin:3px 0}
  #kperf .bar{height:6px;background:#241B33;border-radius:3px;overflow:hidden}#kperf .bar i{display:block;height:100%;background:linear-gradient(90deg,#7C3AED,#2EE6A6)}
  #kperf .v{text-align:right;font-variant-numeric:tabular-nums;color:#C9B3FF}#kperf small{color:#8E86A3}
  #kperf .g{display:grid;grid-template-columns:1fr 48px 64px;gap:4px;margin-top:6px;border-top:1px solid #2B2238;padding-top:6px}
  #kperf canvas{width:100%;height:34px;display:block;margin-top:6px}`;
  document.head.appendChild(css);
  function row(lbl, pct, val) { return `<div class="r"><small>${lbl}</small><div class="bar"><i style="width:${Math.min(100, Math.max(0, pct))}%"></i></div><span class="v">${val}</span></div>`; }
  async function tick() {
    if (!P.on) return;
    const api = window.pywebview?.api;
    const s = api?.perf_stats ? await api.perf_stats().catch(() => null) : null;
    if (s?.ok && P.el) {
      P.hist.push(s.kami_cpu); if (P.hist.length > 60) P.hist.shift();
      const body = P.el.querySelector(".body");
      body.innerHTML = row("CPU", s.cpu, s.cpu.toFixed(0) + "%") + row("RAM", s.ram, B(s.ram_used)) +
        (s.gpu ? row("GPU", s.gpu.util, `${s.gpu.util.toFixed(0)}% ${s.gpu.temp.toFixed(0)}°`) + row("VRAM", (s.gpu.mem / s.gpu.mem_total) * 100, (s.gpu.mem / 1024).toFixed(1) + " GB") : "") +
        row("Kami", s.kami_cpu, `${s.kami_cpu.toFixed(1)}% · ${B(s.kami_mem)}`) +
        `<div class="r"><small>${L("İndirme", "Download")}</small><span></span><span class="v">${B(s.dl_speed)}/s</span></div>` +
        `<div class="r"><small>Disk</small><small>R ${B(s.disk_r)}/s</small><span class="v">W ${B(s.disk_w)}/s</span></div>` +
        `<div class="r"><small>${L("Ağ", "Net")}</small><small>↓ ${B(s.net_rx)}/s</small><span class="v">↑ ${B(s.net_tx)}/s</span></div>` +
        `<div class="g">${s.groups.map((g) => `<small>${g.name}${g.n > 1 ? ` ×${g.n}` : ""}</small><span class="v">${g.cpu.toFixed(1)}%</span><span class="v">${B(g.mem)}</span>`).join("")}</div>` +
        `<canvas width="560" height="68"></canvas>`;
      const cv = body.querySelector("canvas"), g = cv.getContext("2d"), mx = Math.max(10, ...P.hist);
      g.strokeStyle = "#2EE6A6"; g.lineWidth = 2; g.beginPath();
      P.hist.forEach((v, i) => { const x = (i / 59) * 560, y = 66 - (v / mx) * 62; i ? g.lineTo(x, y) : g.moveTo(x, y); }); g.stroke();
    }
    P.t = setTimeout(tick, 1000);
  }
  function toggle(on = !P.on) {
    P.on = on;
    if (!on) { P.el?.remove(); P.el = null; clearTimeout(P.t); try { localStorage.setItem("kami.perf", "0"); } catch {} return; }
    P.el = document.createElement("div"); P.el.id = "kperf";
    P.el.innerHTML = `<h6><span>${L("Performans", "Performance")}</span><b title="${L("Kapat", "Close")}">✕</b></h6><div class="body"><small>…</small></div>`;
    document.body.appendChild(P.el);
    P.el.querySelector("h6 b").onclick = () => toggle(false);
    const h = P.el.querySelector("h6");
    h.onpointerdown = (e) => { if (e.target.tagName === "B") return; const r = P.el.getBoundingClientRect(), ox = e.clientX - r.left, oy = e.clientY - r.top;
      const mv = (ev) => { P.el.style.left = ev.clientX - ox + "px"; P.el.style.top = ev.clientY - oy + "px"; P.el.style.right = P.el.style.bottom = "auto"; };
      const up = () => { removeEventListener("pointermove", mv); removeEventListener("pointerup", up); };
      addEventListener("pointermove", mv); addEventListener("pointerup", up); };
    try { localStorage.setItem("kami.perf", "1"); } catch {}
    tick();
  }
  window.kamiPerf = toggle;
  document.addEventListener("keydown", (e) => { if (e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "p") { e.preventDefault(); toggle(); } }, true);
  (window.KPAL = window.KPAL || []).push(() => [{ t: L("Performans izleyici (Ctrl+Shift+P)", "Performance monitor (Ctrl+Shift+P)"), ic: "📈", run: () => toggle(true) }]);
  window.addEventListener("pywebviewready", () => { try { if (localStorage.getItem("kami.perf") === "1") setTimeout(() => toggle(true), 800); } catch {} });
})();
