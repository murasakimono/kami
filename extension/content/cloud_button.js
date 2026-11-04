// Bulut paylasim sayfalarinda sabit "Kami ile indir" butonu (sag alt). Kisisel diskte "paylasim linki gerekli" ipucu.
// Sayfalar tek sayfa uygulamasi (MEGA, Yandex, Drive): adres degisimi saniyede bir kontrol edilir.
// Buton popover (ust katman) olarak acilir: sitenin modal pencereleri/katmanlari ustune cikamaz.
(() => {
  "use strict";
  if (window.top !== window || window.__kamiCloudButton) return;
  window.__kamiCloudButton = true;

  const t = (k, fb) => { try { return chrome.i18n.getMessage(k) || fb; } catch (_) { return fb; } };
  let host = null, root = null, btn = null, label = null, lastUrl = "", hintClosed = false, busy = false;

  function build() {
    host = document.createElement("kami-cloud-button");
    host.setAttribute("popover", "manual");
    host.style.cssText = "all:initial;position:fixed;inset:auto 20px 20px auto;margin:0;padding:0;border:0;" +
      "background:transparent;overflow:visible;z-index:2147483647;";
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .wrap { font: 600 13px/1.25 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif; display: flex; align-items: center; gap: 6px; }
        button { all: unset; box-sizing: border-box; cursor: pointer; }
        .main { display: inline-flex; align-items: center; gap: 8px; height: 40px; padding: 0 16px 0 12px;
                background: #7C4DFF; color: #fff; border-radius: 10px; box-shadow: 0 6px 22px rgba(0,0,0,.45);
                transition: filter .12s, transform .12s; }
        .main:hover { filter: brightness(1.1); }
        .main:active { transform: scale(.97); }
        .main:focus-visible { outline: 2px solid #C9B3FF; outline-offset: 2px; }
        .main svg { width: 18px; height: 18px; flex: none; }
        .main.ok { background: #2E9E6E; } .main.err { background: #D9485A; }
        .main.hint { background: #15111C; color: #E7E2EF; border: 1px solid #2A2236; cursor: default; font-weight: 500; height: auto; padding: 10px 14px; max-width: 320px; }
        .x { width: 26px; height: 26px; display: grid; place-items: center; border-radius: 13px; background: #15111C; color: #9A91AB;
             border: 1px solid #2A2236; font: 600 14px/1 system-ui; }
        .x:hover { color: #E7E2EF; }
      </style>
      <div class="wrap">
        <button class="main" part="main">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span class="label"></span>
        </button>
        <button class="x" aria-label="×">×</button>
      </div>`;
    btn = root.querySelector(".main");
    label = root.querySelector(".label");
    for (const ev of ["pointerdown", "mousedown", "mouseup", "click", "dblclick", "contextmenu"]) {
      host.addEventListener(ev, (e) => e.stopPropagation());
    }
    btn.addEventListener("click", onClick);
    root.querySelector(".x").addEventListener("click", () => { hintClosed = true; hide(); });
    (document.body || document.documentElement).appendChild(host);
  }

  function show() {
    if (!host) build();
    if (!host.isConnected) (document.body || document.documentElement).appendChild(host);
    try { if (!host.matches(":popover-open")) host.showPopover(); } catch (_) { host.style.display = "block"; }
  }

  function hide() {
    if (!host) return;
    try { host.hidePopover(); } catch (_) { host.style.display = "none"; }
  }

  function setState(kind, name) {
    btn.className = "main" + (kind === "personal" ? " hint" : "");
    btn.querySelector("svg").style.display = kind === "personal" ? "none" : "";
    label.textContent = kind === "personal"
      ? t("cloud_personal_hint", "Kami: bu kişisel diskiniz. İndirmek için dosya/klasörün paylaşım linkini açın.")
      : t("cloud_download", "Kami ile indir") + (name ? ` · ${name}` : "");
  }

  async function onClick() {
    if (busy || btn.classList.contains("hint")) return;
    busy = true;
    try {
      const res = await chrome.runtime.sendMessage({ type: "page-add", url: location.href, title: document.title });
      const ok = res && res.ok && res.accepted;
      btn.classList.add(ok ? "ok" : "err");
      label.textContent = ok ? t("cloud_sent", "Kami'de açıldı") : (res && res.ok ? t("cloud_rejected", "Kami bu linki alamadı") : t("cloud_offline", "Kami kapalı"));
    } catch (_) {
      btn.classList.add("err");
    }
    setTimeout(() => { busy = false; check(true); }, 2500);
  }

  function check(force = false) {
    const url = location.href;
    if (!force && url === lastUrl) return;
    lastUrl = url;
    const site = globalThis.kamiCloudSite ? globalThis.kamiCloudSite(url) : null;
    if (!site || (site.kind === "personal" && hintClosed)) { hide(); return; }
    show();
    setState(site.kind, site.name);
  }

  check();
  setInterval(check, 1000);
})();
