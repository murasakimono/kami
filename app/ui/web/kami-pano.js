// Faz 16.3 — Kami Pano (Sunak Uyumlu Yüzen Raf)
"use strict";
(() => {
  const PANO = { items: [], open: false };

  function kindBadge(v) {
    const s = String(v || "").trim();
    if (/youtube\.com|youtu\.be/i.test(s)) return { ic: "🎬", dl: true };
    if (/\.(png|jpe?g|webp|gif)(\?|$)/i.test(s)) return { ic: "🖼", dl: true };
    if (/^https?:\/\//i.test(s) || /^magnet:\?/i.test(s)) return { ic: "🔗", dl: true };
    return { ic: "📝", dl: false };
  }

  function renderList() {
    const list = document.getElementById("kpList");
    if (!list) return;
    list.replaceChildren();
    if (!PANO.items.length) {
      const em = document.createElement("div");
      em.style.cssText = "color:#8A829E;font-size:11px;padding:10px 4px;text-align:center";
      em.textContent = "Raf boş — kopyalanan link veya notlar buraya gelir";
      list.appendChild(em);
      return;
    }
    for (const x of PANO.items) {
      const kb = kindBadge(x.value);
      const d = document.createElement("div");
      d.style.cssText = "padding:6px 8px;background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.22);clip-path:polygon(6px 0,100% 0,100% calc(100% - 6px),calc(100% - 6px) 100%,0 100%,0 6px);display:flex;justify-content:space-between;align-items:center;gap:6px;cursor:pointer;font-size:11px";
      const sp = document.createElement("span");
      sp.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1";
      sp.textContent = `${kb.ic} ${x.label || x.value || ""}`;
      d.title = x.value || x.label || "";
      d.onclick = () => {
        if (x.value && navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(x.value).catch(() => {});
          d.style.borderColor = "#2EE6A6";
          setTimeout(() => (d.style.borderColor = "rgba(139,92,246,.22)"), 600);
        }
      };
      d.appendChild(sp);
      if (kb.dl && x.value) {
        const dl = document.createElement("button");
        dl.type = "button";
        dl.textContent = "⬇";
        dl.title = "İndirme kutusuna al";
        dl.style.cssText = "background:#2A1650;border:1px solid rgba(157,107,255,.45);color:#EDE9F6;border-radius:5px;padding:1px 6px;cursor:pointer;font-size:10px";
        dl.onclick = (ev) => {
          ev.stopPropagation();
          const inp = document.getElementById("addInput");
          if (inp) { inp.value = x.value; inp.focus(); }
        };
        d.appendChild(dl);
      }
      if (x.id) {
        const rm = document.createElement("button");
        rm.type = "button";
        rm.textContent = "✕";
        rm.title = "Raftan kaldır";
        rm.style.cssText = "background:none;border:none;color:#8A829E;cursor:pointer;font-size:11px;padding:0 3px";
        rm.onclick = async (ev) => {
          ev.stopPropagation();
          await api?.pano_shelf_remove?.(x.id).catch(() => {});
          refresh();
        };
        d.appendChild(rm);
      }
      list.appendChild(d);
    }
  }

  async function refresh() {
    if (typeof api !== "undefined" && api.pano_shelf_list) {
      try {
        const r = await api.pano_shelf_list();
        PANO.items = r?.items || [];
      } catch { PANO.items = []; }
    }
    renderList();
  }

  function mountPano() {
    if (document.getElementById("kamiPanoDock")) return;
    const ico = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg>`;
    const rail = document.getElementById("skDock");
    const dock = document.createElement("button");
    dock.id = "kamiPanoDock";
    dock.type = "button";
    dock.title = "Kami Pano Rafı";
    dock.setAttribute("aria-label", "Kami Pano Rafı");
    if (rail) {   // v1.31.1: sag altigen menude, diger simgelerle ayni gorunum (eskiden komut satirinin Indir dugmesine biniyordu)
      dock.dataset.sk = "pano";
      dock.innerHTML = ico;
      const st = rail.querySelector('[data-sk="settings"]');
      rail.insertBefore(dock, st || null);
    } else {
      dock.style.cssText = "position:fixed;right:18px;top:50%;z-index:55;width:36px;height:36px;display:grid;place-items:center;background:rgba(17,14,23,.92);border:1px solid rgba(139,92,246,.45);color:#C4B5FD;cursor:pointer;border-radius:10px";
      dock.innerHTML = ico.replace("<svg ", '<svg width="16" height="16" ');
      document.body.appendChild(dock);
    }

    const drawer = document.createElement("div");
    drawer.id = "kamiPanoDrawer";
    drawer.style.cssText = "position:fixed;z-index:56;width:280px;max-height:340px;overflow:auto;background:rgba(13,10,20,.96);border:1px solid rgba(139,92,246,.5);padding:10px;color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;display:none;gap:8px;clip-path:polygon(10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%,0 10px);box-shadow:0 12px 32px rgba(0,0,0,.6)";
    drawer.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(139,92,246,.25);padding-bottom:6px"><b style="color:#C4B5FD;letter-spacing:.05em">PANO RAFI</b><span style="flex:1"></span><button id="kpClear" type="button" title="Rafı temizle" style="background:none;border:1px solid rgba(139,92,246,.35);color:#A39BB5;cursor:pointer;font-size:10px;padding:1px 6px;margin-right:6px">Temizle</button><button id="kpClose" type="button" style="background:none;border:none;color:#A39BB5;cursor:pointer;font-size:13px">✕</button></div><div id="kpList" style="display:grid;gap:5px"></div>`;
    const place = () => {   // dugmenin soluna, ekrandan tasmadan
      const r = dock.getBoundingClientRect();
      drawer.style.right = Math.max(8, innerWidth - r.left + 10) + "px";
      drawer.style.top = Math.max(8, Math.min(innerHeight - 350, r.top - 140)) + "px";
    };
    const close = () => { PANO.open = false; drawer.style.display = "none"; dock.classList.remove("on"); };
    dock.onclick = async (e) => {
      e.stopPropagation();
      PANO.open = !PANO.open;
      if (!PANO.open) return close();
      place(); drawer.style.display = "grid"; dock.classList.add("on");
      await refresh();
    };
    document.body.appendChild(drawer);
    document.getElementById("kpClose")?.addEventListener("click", close);
    document.getElementById("kpClear")?.addEventListener("click", async (e) => { e.stopPropagation(); await api?.pano_shelf_clear?.().catch(() => {}); refresh(); });
    setInterval(() => { if (PANO.open) refresh(); }, 2500);   // acikken yeni kopyalar canli gelsin
    document.addEventListener("click", (e) => { if (PANO.open && !drawer.contains(e.target) && e.target !== dock) close(); });
    document.addEventListener("keydown", (e) => { if (e.key === "Escape" && PANO.open) close(); });
    addEventListener("resize", () => PANO.open && place());
  }

  function boot() { if (document.getElementById("skDock") || document.readyState === "complete") mountPano(); else setTimeout(boot, 200); }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();

  window.KamiPano = { state: PANO, mountPano, refresh };
})();
