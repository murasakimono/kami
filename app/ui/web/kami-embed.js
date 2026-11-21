// Tek pencere sekme mimarisi: iframe icinde acilan modul sayfalarini ana pencerenin pywebview.api koprusune baglar.
"use strict";
(() => {
  if (window.pywebview || window.parent === window) return;
  let seq = 1;
  const pending = new Map();
  window.addEventListener("message", (e) => {
    const d = e.data;
    if (!d || typeof d.__kamiRes !== "number") return;
    const p = pending.get(d.__kamiRes);
    if (!p) return;
    pending.delete(d.__kamiRes);
    if (d.ok) p.res(d.data);
    else p.rej(new Error(d.error || "api_error"));
  });
  const api = new Proxy({}, {
    get(_t, fn) {
      if (typeof fn !== "string" || fn === "then") return undefined;
      return (...args) => new Promise((res, rej) => {
        const id = seq++;
        pending.set(id, { res, rej });
        window.parent.postMessage({ __kamiApi: id, fn, args }, "*");
        setTimeout(() => {
          if (pending.has(id)) { pending.delete(id); rej(new Error("api_timeout")); }
        }, 120000);
      });
    },
  });
  window.pywebview = { api };
  const fireReady = () => window.dispatchEvent(new Event("pywebviewready"));
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", () => setTimeout(fireReady, 0));
  else setTimeout(fireReady, 0);
})();

// Kami 2.0 Global OS Layer (A2 Scratchpad, A3 Auto-Hide Job HUD, A4 F1/Alt+K Cheat-Sheet, #13 Fitts Radial Ring + Motion Layer)
(() => {
  const load20 = () => {
    if (document.getElementById("kami20Script") || location.pathname.endsWith("mini-island.html") || location.pathname.endsWith("pin.html")) return;
    const base = document.querySelector('script[src*="kami-embed.js"]')?.getAttribute("src")?.startsWith("s/") ? "s/" : "";
    if (!document.getElementById("kamiMotionCss") && document.head) {
      const l = document.createElement("link");
      l.id = "kamiMotionCss";
      l.rel = "stylesheet";
      l.href = base + "kami-motion.css";
      document.head.appendChild(l);
    }
    if (!document.getElementById("kamiMotionJs") && document.body) {
      const m = document.createElement("script");
      m.id = "kamiMotionJs";
      m.src = base + "kami-motion.js";
      // Alt pencereler (player/games/music/studio/picture/reader/cleaner/room) main app.js gibi
      // applySettings çağırmıyordu -> animasyon ayarları hep false kalıyordu. Burada yüklenince çek + uygula.
      m.onload = () => {
        try {
          const a = window.pywebview?.api;
          if (a?.get_settings) a.get_settings().then((s) => { if (s && window.KamiMotion) window.KamiMotion.applySettings(s); }).catch(() => {});
        } catch (_) { /* get_settings yoksa sessiz gec */ }
      };
      document.body.appendChild(m);
    }
    const s = document.createElement("script");
    s.id = "kami20Script";
    s.src = base + "kami-20.js";
    document.body?.appendChild(s);
  };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", load20);
  else load20();
})();
