// Kami arayuz bekcisi: tum pencerelerde JS hatalarini ve yakalanmamis promise hatalarini kami.log'a yazar
// (ayni hata dakikada bir kez, dakikada en cok 20 kayit). Tarayicida (Oda misafiri) sessizce hicbir sey yapmaz.
"use strict";
(() => {
  if (window.__kamiGuard) return;
  window.__kamiGuard = true;
  const page = (location.pathname.split("/").pop() || "index.html").replace(/\.html$/, "");
  const queue = [], seen = new Map();
  let windowStart = Date.now(), count = 0;
  const api = () => window.pywebview?.api;
  function flush() {
    const a = api();
    if (!a?.ui_error) return;
    while (queue.length) { const e = queue.shift(); try { a.ui_error(page, e.msg, e.src, e.stack); } catch { /* kapanirken */ } }
  }
  function report(msg, src, stack) {
    const now = Date.now();
    if (now - windowStart > 60000) { windowStart = now; count = 0; }
    const key = msg + "|" + src;
    if (now - (seen.get(key) || 0) < 60000 || count >= 20) return;
    seen.set(key, now); count++;
    queue.push({ msg: String(msg || "").slice(0, 500), src: String(src || "").slice(0, 300), stack: String(stack || "").slice(0, 1500) });
    if (queue.length > 50) queue.shift();
    flush();
  }
  window.addEventListener("error", (e) => {
    if (e.target && e.target !== window && (e.target.src || e.target.href)) {   // yuklenemeyen script/css/gorsel
      report("Kaynak yuklenemedi: " + (e.target.tagName || "?"), e.target.src || e.target.href, "");
      return;
    }
    report(e.message, `${(e.filename || "").split("/").pop()}:${e.lineno}:${e.colno}`, e.error?.stack);
  }, true);
  window.addEventListener("unhandledrejection", (e) => {
    const r = e.reason;
    report("Yakalanmamis promise: " + (r?.message || r), "", r?.stack);
  });
  window.addEventListener("pywebviewready", flush);
  window.KamiGuard = { report };
})();
