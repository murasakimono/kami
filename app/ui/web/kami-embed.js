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
