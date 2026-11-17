// Faz 16.3 — Kami Pano (Sunak Uyumlu Yüzen Raf)
"use strict";
(() => {
  const PANO = { items: [], open: false };

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
      const d = document.createElement("div");
      d.style.cssText = "padding:6px 8px;background:rgba(139,92,246,.08);border:1px solid rgba(139,92,246,.22);clip-path:polygon(6px 0,100% 0,100% calc(100% - 6px),calc(100% - 6px) 100%,0 100%,0 6px);display:flex;justify-content:space-between;align-items:center;gap:6px;cursor:pointer;font-size:11px";
      const sp = document.createElement("span");
      sp.style.cssText = "overflow:hidden;text-overflow:ellipsis;white-space:nowrap;flex:1";
      sp.textContent = x.label || x.value || "";
      d.title = x.value || x.label || "";
      d.onclick = () => {
        if (x.value && navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(x.value).catch(() => {});
          d.style.borderColor = "#2EE6A6";
          setTimeout(() => (d.style.borderColor = "rgba(139,92,246,.22)"), 600);
        }
      };
      d.appendChild(sp);
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
    const dock = document.createElement("button");
    dock.id = "kamiPanoDock";
    dock.type = "button";
    dock.title = "Kami Pano Rafı";
    dock.style.cssText = "position:fixed;right:78px;bottom:18px;z-index:55;height:30px;padding:0 12px;display:flex;align-items:center;gap:6px;background:rgba(17,14,23,.92);border:1px solid rgba(139,92,246,.45);color:#EDE9F6;font:600 11px 'Chakra Petch',sans-serif;letter-spacing:.06em;cursor:pointer;clip-path:polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px);backdrop-filter:blur(8px)";
    dock.innerHTML = `<svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#8B5CF6" stroke-width="2"><rect x="8" y="2" width="8" height="4" rx="1"/><path d="M16 4h2a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h2"/></svg><span>RAF</span>`;

    const drawer = document.createElement("div");
    drawer.id = "kamiPanoDrawer";
    drawer.style.cssText = "position:fixed;right:78px;bottom:56px;z-index:56;width:260px;max-height:320px;overflow:auto;background:rgba(13,10,20,.96);border:1px solid rgba(139,92,246,.5);padding:10px;color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;display:none;gap:8px;clip-path:polygon(10px 0,100% 0,100% calc(100% - 10px),calc(100% - 10px) 100%,0 100%,0 10px);box-shadow:0 12px 32px rgba(0,0,0,.6)";
    drawer.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;border-bottom:1px solid rgba(139,92,246,.25);padding-bottom:6px"><b style="color:#C4B5FD;letter-spacing:.05em">PANO RAFI</b><button id="kpClose" type="button" style="background:none;border:none;color:#A39BB5;cursor:pointer;font-size:13px">✕</button></div><div id="kpList" style="display:grid;gap:5px"></div>`;

    dock.onclick = async () => {
      PANO.open = !PANO.open;
      drawer.style.display = PANO.open ? "grid" : "none";
      if (PANO.open) await refresh();
    };
    document.body.appendChild(dock);
    document.body.appendChild(drawer);
    document.getElementById("kpClose")?.addEventListener("click", () => { PANO.open = false; drawer.style.display = "none"; });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountPano);
  else mountPano();

  window.KamiPano = { state: PANO, mountPano, refresh };
})();
