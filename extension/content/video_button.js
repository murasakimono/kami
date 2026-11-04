// Video ustu "Kami ile indir" butonu (her site, YouTube dahil). Shadow DOM: sitenin CSS'i karismaz.
// Imlec bir videonun ustundeyken sag ustte belirir; tiklayinca MP4 / MP3 / Kami'de sec menusu.
(() => {
  "use strict";
  if (window.__kamiVideoButton) return;
  window.__kamiVideoButton = true;
  // bulut paylasim sayfasi (MEGA vb.): video butonu yerine sayfa butonu (cloud_button.js)
  const onCloudShare = () => {
    try { return globalThis.kamiCloudKind && globalThis.kamiCloudKind(window.top === window ? location.href : document.referrer) === "share"; }
    catch (_) { return false; }
  };

  const MIN_W = 220, MIN_H = 120, HIDE_MS = 2200;
  const t = (k, fb) => { try { return chrome.i18n.getMessage(k) || fb; } catch (_) { return fb; } };

  let host = null, root = null, btn = null, menu = null;
  let current = null, hideTimer = 0, overUi = false, busy = false;

  function build() {
    host = document.createElement("kami-video-button");
    host.style.cssText = "all:initial;position:fixed;z-index:2147483647;top:0;left:0;display:none;";
    root = host.attachShadow({ mode: "open" });
    root.innerHTML = `
      <style>
        :host { all: initial; }
        .wrap { font: 600 13px/1 "Segoe UI Variable Text","Segoe UI",system-ui,sans-serif; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
        button { all: unset; box-sizing: border-box; cursor: pointer; }
        .main { display: inline-flex; align-items: center; gap: 7px; height: 32px; padding: 0 12px 0 10px;
                background: #7C4DFF; color: #fff; border-radius: 8px; box-shadow: 0 4px 16px rgba(0,0,0,.45);
                transition: filter .12s, transform .12s; }
        .main:hover { filter: brightness(1.1); }
        .main:active { transform: scale(.97); }
        .main svg { width: 16px; height: 16px; flex: none; }
        .main.ok { background: #2E9E6E; } .main.err { background: #D9485A; }
        .menu { display: none; min-width: 168px; background: #15111C; color: #E7E2EF; border: 1px solid #2A2236;
                border-radius: 8px; padding: 4px; box-shadow: 0 8px 28px rgba(0,0,0,.55); }
        .menu.open { display: block; }
        .menu button { display: block; width: 100%; padding: 9px 12px; border-radius: 6px; font-weight: 500; }
        .menu button:hover, .menu button:focus-visible { background: #2A2236; }
        .menu small { color: #9A91AB; font-weight: 400; margin-left: 6px; }
      </style>
      <div class="wrap">
        <button class="main" part="main" aria-haspopup="menu">
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M12 4v11m0 0-4.5-4.5M12 15l4.5-4.5M5 19h14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"/></svg>
          <span class="label"></span>
        </button>
        <div class="menu" role="menu">
          <button role="menuitem" data-mode="mp4">MP4<small></small></button>
          <button role="menuitem" data-mode="mp3">MP3<small></small></button>
          <button role="menuitem" data-mode="choose"></button>
        </div>
      </div>`;
    btn = root.querySelector(".main");
    menu = root.querySelector(".menu");
    root.querySelector(".label").textContent = t("btn_download", "Kami ile indir");
    root.querySelector('[data-mode="mp4"] small').textContent = t("btn_mp4_hint", "video");
    root.querySelector('[data-mode="mp3"] small').textContent = t("btn_mp3_hint", "ses");
    root.querySelector('[data-mode="choose"]').textContent = t("btn_choose", "Kami'de seç…");

    // tiklamalar sayfaya (oynaticiya) ulasmasin
    for (const ev of ["pointerdown", "mousedown", "mouseup", "click", "dblclick", "contextmenu"]) {
      host.addEventListener(ev, (e) => e.stopPropagation());
    }
    host.addEventListener("mouseenter", () => { overUi = true; clearTimeout(hideTimer); });
    host.addEventListener("mouseleave", () => { overUi = false; scheduleHide(); });
    btn.addEventListener("click", (e) => { e.preventDefault(); menu.classList.toggle("open"); });
    menu.addEventListener("click", (e) => {
      const item = e.target.closest("button[data-mode]");
      if (item) { e.preventDefault(); send(item.dataset.mode); }
    });
    mount();
  }

  function mount() {
    const parent = document.fullscreenElement || document.documentElement;
    if (host && host.parentNode !== parent) parent.appendChild(host);
  }

  function findVideo(x, y) {
    for (const el of document.elementsFromPoint(x, y)) {
      if (el === host) return current;
      if (el instanceof HTMLVideoElement) return el;
    }
    // ustune katman konmus oynaticilar: imlec hangi videonun dikdortgeninde?
    for (const v of document.querySelectorAll("video")) {
      const r = v.getBoundingClientRect();
      if (x >= r.left && x <= r.right && y >= r.top && y <= r.bottom) return v;
    }
    return null;
  }

  function place() {
    if (!current || !current.isConnected) { hide(); return; }
    const r = current.getBoundingClientRect();
    if (r.width < MIN_W || r.height < MIN_H) { hide(); return; }
    const top = Math.max(r.top, 0) + 10;
    const right = Math.min(r.right, window.innerWidth) - 10;
    host.style.display = "block";
    host.style.top = `${top}px`;
    host.style.left = "0px";
    const w = host.getBoundingClientRect().width || 150;
    host.style.left = `${Math.max(4, right - w)}px`;
  }

  function hide() {
    if (!host || busy) return;
    host.style.display = "none";
    menu.classList.remove("open");
    current = null;
  }

  function scheduleHide() {
    clearTimeout(hideTimer);
    hideTimer = setTimeout(() => { if (!overUi) hide(); }, HIDE_MS);
  }

  let raf = 0;
  document.addEventListener("pointermove", (e) => {
    if (raf) return;
    raf = requestAnimationFrame(() => {
      raf = 0;
      const v = findVideo(e.clientX, e.clientY);
      if (v && onCloudShare()) { hide(); return; }
      if (v) {
        if (!host) build();
        if (v !== current) { current = v; menu.classList.remove("open"); }
        place();
        scheduleHide();
      }
    });
  }, { passive: true, capture: true });
  window.addEventListener("scroll", () => { if (current) place(); }, { passive: true, capture: true });
  window.addEventListener("resize", () => { if (current) place(); });
  document.addEventListener("fullscreenchange", () => { mount(); if (current) place(); });

  async function send(mode) {
    if (busy || !current) return;
    busy = true;
    menu.classList.remove("open");
    const src = current.currentSrc || current.src || "";
    let res;
    try {
      res = await chrome.runtime.sendMessage({
        type: "video-button", mode, src: /^blob:/i.test(src) ? "" : src,
        pageUrl: location.href, title: document.title,
      });
    } catch (_) {
      res = { ok: false };
    }
    const ok = res && res.ok && res.accepted;
    btn.classList.add(ok ? "ok" : "err");
    const label = root.querySelector(".label");
    const old = label.textContent;
    label.textContent = ok ? (mode === "choose" ? t("btn_opened", "Kami'de açıldı") : t("btn_added", "Kuyruğa eklendi"))
                           : (res && res.ok ? t("btn_rejected", "İndirilemedi") : t("btn_offline", "Kami kapalı"));
    setTimeout(() => {
      btn.classList.remove("ok", "err");
      label.textContent = old;
      busy = false;
      scheduleHide();
    }, 1800);
  }
})();
