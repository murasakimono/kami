// Faz 16.3 — Kami Pano (Dropover Yuzen Rafi) + OKLCH & Piksel Cetveli UI
"use strict";
(() => {
  const PANO = { items: [], open: false };

  function mountPano() {
    if (document.getElementById("kamiPanoDock")) return;
    const dock = document.createElement("div");
    dock.id = "kamiPanoDock";
    dock.style.cssText = "position:fixed;right:0;top:42%;z-index:55;background:#161124;border:1px solid #6D28D9;border-right:none;color:#EDE9F6;font:600 11px 'Chakra Petch',sans-serif;padding:6px 8px;cursor:pointer;";
    dock.textContent = "PANO";
    const drawer = document.createElement("div");
    drawer.id = "kamiPanoDrawer";
    drawer.style.cssText = "position:fixed;right:12px;top:30%;z-index:56;width:230px;max-height:300px;overflow:auto;background:#120E1C;border:1px solid #7C3AED;padding:10px;color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;display:none;gap:6px;";
    drawer.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center"><b>Kami Pano</b><button id="kpClose" style="background:none;border:none;color:#A78BFA;cursor:pointer">✕</button></div><div id="kpList" style="display:grid;gap:4px"></div>`;
    dock.onclick = async () => {
      PANO.open = !PANO.open;
      drawer.style.display = PANO.open ? "grid" : "none";
      if (PANO.open && typeof api !== "undefined" && api.pano_shelf_list) {
        const r = await api.pano_shelf_list();
        PANO.items = r?.items || [];
        const list = document.getElementById("kpList");
        if (list) {
          list.replaceChildren();
          for (const x of PANO.items) { const d = document.createElement("div"); d.style.cssText = "padding:4px;background:#1E1630"; d.textContent = x.label || x.value || ""; list.appendChild(d); }
          if (!PANO.items.length) list.innerHTML = "<i>Raf bos</i>";
        }
      }
    };
    document.body.appendChild(dock);
    document.body.appendChild(drawer);
    document.getElementById("kpClose")?.addEventListener("click", () => { PANO.open = false; drawer.style.display = "none"; });
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountPano);
  else mountPano();

  window.KamiPano = { state: PANO, mountPano };
})();
