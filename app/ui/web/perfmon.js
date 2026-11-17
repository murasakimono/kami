/* Kami performans izleyici: Ctrl+Shift+P (ya da Ctrl+K > "Performans izleyici"). Suruklenebilir HUD:
   sistem CPU/RAM/GPU halka gostergeleri + alt kirilim cubuklari + 60 sn grafigi. */
(function () {
  const P = { on: false, el: null, t: 0, hist: [] };
  const en = () => (document.documentElement.lang || "tr").startsWith("en");
  const L = (tr, e) => (en() ? e : tr);
  const B = (n) => { n = +n || 0; const u = ["B", "KB", "MB", "GB"]; let i = 0; while (n >= 1024 && i < 3) { n /= 1024; i++; } return n.toFixed(i > 1 ? 1 : 0) + " " + u[i]; };
  const css = document.createElement("style");
  css.textContent = `#kperf{position:fixed;right:16px;bottom:16px;z-index:9998;width:308px;background:rgba(15,11,22,.96);border:1px solid rgba(157,107,255,.38);border-radius:12px;
   box-shadow:0 12px 40px #000a;color:#EDE9F6;font:12px/1.4 "Segoe UI Variable","Segoe UI",system-ui,sans-serif;padding:10px 12px;user-select:none}
  #kperf h6{margin:0 0 8px;font:600 11px "Chakra Petch","Segoe UI",sans-serif;letter-spacing:2px;text-transform:uppercase;color:#A78BFA;cursor:move;display:flex;align-items:center}
  #kperf h6 span{flex:1}#kperf h6 button{background:none;border:0;cursor:pointer;color:#8E86A3;font:inherit;padding:2px 4px;border-radius:4px}
  #kperf h6 button:focus-visible{outline:2px solid #9D6BFF}
  #kperf .rings{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:8px}
  #kperf .ring{background:#151022;border:1px solid #2A2140;border-radius:8px;padding:6px;display:flex;flex-direction:column;align-items:center;gap:2px}
  #kperf .ring svg{transform:rotate(-90deg)}
  #kperf .ring b{font:700 12px "Chakra Petch",sans-serif;color:#EDE9F6}
  #kperf .ring small{font-size:10px;color:#9E96B8}
  #kperf .r{display:grid;grid-template-columns:68px 1fr 66px;gap:6px;align-items:center;margin:3px 0}
  #kperf .bar{height:5px;background:#241B33;border-radius:3px;overflow:hidden}#kperf .bar i{display:block;height:100%;background:linear-gradient(90deg,#7C3AED,#2EE6A6)}
  #kperf .v{text-align:right;font-variant-numeric:tabular-nums;color:#C9B3FF}#kperf small{color:#8E86A3}
  #kperf .g{margin-top:7px;border-top:1px solid #2B2238;padding-top:6px;display:grid;gap:3px}
  #kperf canvas{width:100%;height:34px;display:block;margin-top:6px}`;
  document.head.appendChild(css);

  function ring(lbl, pct, sub, col = "#2EE6A6") {
    const p = Math.min(100, Math.max(0, +pct || 0)), c = 2 * Math.PI * 16;
    return `<div class="ring"><svg width="40" height="40" viewBox="0 0 40 40"><circle cx="20" cy="20" r="16" fill="none" stroke="#241B33" stroke-width="4"/><circle cx="20" cy="20" r="16" fill="none" stroke="${col}" stroke-width="4" stroke-dasharray="${c.toFixed(1)}" stroke-dashoffset="${(c * (1 - p / 100)).toFixed(1)}" stroke-linecap="round"/></svg><b>${p.toFixed(0)}%</b><small>${lbl}${sub ? ` · ${sub}` : ""}</small></div>`;
  }
  function row(lbl, pct, val) { return `<div class="r"><small>${lbl}</small><div class="bar"><i style="width:${Math.min(100, Math.max(0, pct))}%"></i></div><span class="v">${val}</span></div>`; }

  async function tick() {
    if (!P.on) return;
    const api = window.pywebview?.api;
    const s = api?.perf_stats ? await api.perf_stats().catch(() => null) : null;
    if (s?.ok && P.el) {
      P.hist.push(s.kami_cpu); if (P.hist.length > 60) P.hist.shift();
      const body = P.el.querySelector(".body");
      const maxMem = Math.max(1, ...s.groups.map((g) => g.mem || 0));
      body.innerHTML =
        `<div class="rings">${ring("CPU", s.cpu, s.kami_cpu.toFixed(0) + "% Kami", "#9D6BFF")}${ring("RAM", s.ram, B(s.ram_used), "#2EE6A6")}${s.gpu ? ring("GPU", s.gpu.util, `${s.gpu.temp.toFixed(0)}°`, "#C084FC") : ring("Kami", Math.min(100, s.kami_cpu), B(s.kami_mem), "#C084FC")}</div>` +
        `<div class="r"><small>${L("İndirme", "Download")}</small><small>R ${B(s.disk_r)}/s · W ${B(s.disk_w)}/s</small><span class="v">${B(s.dl_speed)}/s</span></div>` +
        `<div class="r"><small>${L("Ağ", "Net")}</small><small>↓ ${B(s.net_rx)}/s</small><span class="v">↑ ${B(s.net_tx)}/s</span></div>` +
        `<div class="g">${s.groups.map((g) => row(`${g.name}${g.n > 1 ? ` ×${g.n}` : ""}`, (g.mem / maxMem) * 100, `${g.cpu.toFixed(1)}% · ${B(g.mem)}`)).join("")}</div>` +
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
    P.el.innerHTML = `<h6><span>${L("Performans", "Performance")}</span><button type="button" title="${L("Kapat", "Close")}" aria-label="${L("Kapat", "Close")}">✕</button></h6><div class="body"><small>…</small></div>`;
    document.body.appendChild(P.el);
    P.el.querySelector("h6 button").onclick = () => toggle(false);
    const h = P.el.querySelector("h6");
    h.onpointerdown = (e) => { if (e.target.tagName === "BUTTON") return; const r = P.el.getBoundingClientRect(), ox = e.clientX - r.left, oy = e.clientY - r.top;
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
