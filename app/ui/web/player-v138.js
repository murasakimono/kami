// Kami Player v1.38.0 — Idle CTAs, Library Filter, Unshuffle, Transcript Tab, asbplayer Recipes & Picture/Studio/AnkiConnect Bridges
"use strict";
(() => {
  const callApi = () => window.pywebview?.api;
  const css = document.createElement("style");
  css.textContent = `
    .pl-v138-bar { display:flex; align-items:center; gap:6px; flex-wrap:wrap; margin-right:6px; }
    .pl-v138-pill { height:28px; padding:0 9px; border:1px solid rgba(157,107,255,.32); background:#140F20; color:#D8CCF8; border-radius:7px; font:600 11.5px "Chakra Petch",sans-serif; cursor:pointer; white-space:nowrap; }
    .pl-v138-pill:hover { border-color:#2EE6A6; color:#fff; }
    .pl-v138-pill.on { border-color:#2EE6A6; color:#2EE6A6; background:rgba(46,230,166,.12); }
    #plChapNow { font-size:11.5px; color:#2EE6A6; margin-left:6px; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; max-width:240px; }
    .px-filter { width:100%; margin:6px 0 8px; padding:7px 10px; background:#0A0810; border:1px solid #35294D; color:#EDE9F6; border-radius:8px; font:inherit; outline:none; }
    .px-filter:focus { border-color:#8B5CF6; }
    .px-tr-row { display:flex; gap:8px; width:100%; text-align:left; padding:7px 9px; margin-bottom:4px; border:1px solid transparent; border-radius:8px; background:#120E1D; color:#DCD4EE; cursor:pointer; font:inherit; font-size:12px; }
    .px-tr-row:hover { border-color:#8B5CF6; background:#1B142B; }
    .px-tr-row.on { border-color:#2EE6A6; background:rgba(46,230,166,.10); color:#fff; }
    .px-tr-row b { color:#2EE6A6; min-width:44px; font-variant-numeric:tabular-nums; font-size:11px; }
    .pl-bridge-row { display:flex; gap:6px; flex-wrap:wrap; margin-top:8px; }
    .pl-url-ov { position:fixed; inset:0; z-index:95; background:rgba(5,4,10,.76); backdrop-filter:blur(8px); display:grid; place-items:center; }
    .pl-url-box { width:min(460px,92vw); background:#130E1E; border:1px solid rgba(157,107,255,.45); border-radius:12px; padding:18px; display:grid; gap:10px; color:#EDE9F6; }
    .pl-url-box input { background:#09070F; border:1px solid #35294D; border-radius:8px; padding:9px 11px; color:#fff; font:inherit; outline:none; }
  `;
  document.head.appendChild(css);

  // ---- 1. Idle Dosya Ac & URL Izle ----
  document.addEventListener("click", async (e) => {
    if (e.target.closest?.("#plEmptyPick")) {
      const p = await callApi()?.player_pick_file?.();
      if (p && typeof playerOpenPath === "function") playerOpenPath(p);
    } else if (e.target.closest?.("#plEmptyUrl")) {
      const ov = document.createElement("div");
      ov.className = "pl-url-ov";
      ov.innerHTML = `<div class="pl-url-box"><b>${plL("URL'den İzle / Akış", "Stream URL")}</b><input id="plUIn" placeholder="https://..."><div style="display:flex;justify-content:flex-end;gap:8px"><button class="pl-b" id="plUNo">${plL("İptal", "Cancel")}</button><button class="pl-b pri" id="plUOk">${plL("Başlat", "Open")}</button></div></div>`;
      document.body.appendChild(ov);
      const inp = ov.querySelector("#plUIn");
      const go = async () => {
        const u = inp.value.trim(); ov.remove();
        if (!u) return;
        if (typeof playerOpenUrl === "function") {
          await playerOpenUrl(u);
          return;
        }
        const r = await callApi()?.player_open_url?.(u).catch(() => null);
        if (r?.ok && typeof plStart === "function") plStart(r);
        else if (typeof toast === "function") toast(r?.error || "URL açılamadı", true);
      };
      ov.querySelector("#plUNo").onclick = () => ov.remove();
      ov.querySelector("#plUOk").onclick = go;
      ov.onclick = (ev) => { if (ev.target === ov) ov.remove(); };
      inp.onkeydown = (ev) => { if (ev.key === "Enter") go(); else if (ev.key === "Escape") ov.remove(); };
      setTimeout(() => inp.focus(), 20);
    }
  });

  // ---- 2. asbplayer Playback Recipes & Chapter Pill & Bridges ----
  const RECIPES = { focus: false, gap3x: false, hover: false, autoPause: false };
  let _lastPausedCueIdx = -1, _hoverPaused = false, _userBaseRate = 1;

  function mountTopControls() {
    const ttl = document.querySelector("#player .pl-title");
    if (ttl && !document.getElementById("plChapNow")) {
      const ch = document.createElement("span");
      ch.id = "plChapNow";
      ttl.appendChild(ch);
    }
    // Eski ust bar kalabaligini kaldir; yalnizca Ayarlar (⚙) > Araclar sekmesinin icine yerlestir
    const panel = document.getElementById("plPanel");
    if (!panel || document.getElementById("plV138Bar")) return;
    const secs = [...panel.querySelectorAll(".px-sec")];
    const toolsSec = secs[secs.length - 1] || panel;
    const bar = document.createElement("div");
    bar.id = "plV138Bar";
    bar.className = "pl-v138-bar";
    bar.style.cssText = "margin-top:10px;padding-top:10px;border-top:1px solid rgba(157,107,255,.22);display:flex;flex-wrap:wrap;gap:6px";
    bar.innerHTML = `
      <span style="width:100%;font-size:11px;color:#9F96B8;margin-bottom:2px">Dil Öğrenme &amp; Köprü Araçları</span>
      <button type="button" class="pl-v138-pill" data-rec="focus" title="Altyazı olmayan boşlukları azalt / diyaloğa odaklan">Diyalog Odak</button>
      <button type="button" class="pl-v138-pill" data-rec="gap3x" title="Konuşmalar arası boşlukta hızı 3× yap">Boşluk 3×</button>
      <button type="button" class="pl-v138-pill" data-rec="hover" title="Altyazı üzerine gelince duraklat">Hover Duraklat</button>
      <button type="button" class="pl-v138-pill" data-rec="autoPause" title="Her cümle sonunda otomatik duraklat">Oto-Duraklat</button>
      <button type="button" class="pl-v138-pill" id="plBrPic" title="Mevcut kareyi Picture Beautify'a gönder">Beautify</button>
      <button type="button" class="pl-v138-pill" id="plBrSt" title="Bu klibi Kami Studio'da aç">Studio</button>
      <button type="button" class="pl-v138-pill" id="plBrAnki" title="Aktif altyazı cümlesi + kareyi Anki'ye gönder">Anki</button>
    `;
    toolsSec.appendChild(bar);

    bar.addEventListener("click", async (e) => {
      const rb = e.target.closest("[data-rec]");
      if (rb) {
        const k = rb.dataset.rec;
        RECIPES[k] = !RECIPES[k];
        if (k === "focus" && RECIPES.focus) RECIPES.gap3x = true;
        rb.classList.toggle("on", RECIPES[k]);
        bar.querySelector('[data-rec="gap3x"]')?.classList.toggle("on", RECIPES.gap3x);
        const v = document.getElementById("plVideo");
        if (!RECIPES.gap3x && v) v.playbackRate = _userBaseRate || 1;
        return;
      }
      if (e.target.id === "plBrPic") {
        const snap = captureVideoFrame();
        if (!snap) { window.toast?.("Görüntü karesi yakalanamadı", true); return; }
        await callApi()?.player_send_frame_picture?.(snap, true);
        window.toast?.("Kare Kami Picture Beautify'a gönderildi ✓");
      } else if (e.target.id === "plBrSt") {
        if (!PL.info?.path) return;
        await callApi()?.player_send_clip_studio?.(PL.info.path, typeof plNow === "function" ? plNow() : 0);
        window.toast?.("Kami Studio açıldı ✓");
      } else if (e.target.id === "plBrAnki") {
        const cue = currentCue();
        const img = captureVideoFrame();
        const r = await callApi()?.player_anki_mine?.("", cue?.text || document.getElementById("plTitle")?.textContent || "", "", "", "Kami", "Basic", "", img || "");
        window.toast?.(r?.ok ? "Anki'ye kart gönderildi ✓" : (r?.error === "anki_offline" ? "Anki (AnkiConnect 8765) açık değil" : (r?.error || "Gönderilemedi")), !r?.ok);
      }
    });

    const subs = document.getElementById("plSubs");
    if (subs) {
      subs.style.pointerEvents = "auto";
      subs.addEventListener("mouseenter", () => {
        const v = document.getElementById("plVideo");
        if (RECIPES.hover && v && !v.paused) { _hoverPaused = true; v.pause(); }
      });
      subs.addEventListener("mouseleave", () => {
        const v = document.getElementById("plVideo");
        if (RECIPES.hover && _hoverPaused && v && v.paused) { _hoverPaused = false; v.play().catch(() => {}); }
      });
    }
  }

  function captureVideoFrame() {
    const v = document.getElementById("plVideo");
    if (!v || !v.videoWidth || !v.videoHeight) return "";
    try {
      const c = document.createElement("canvas");
      c.width = v.videoWidth; c.height = v.videoHeight;
      c.getContext("2d").drawImage(v, 0, 0, c.width, c.height);
      return c.toDataURL("image/png");
    } catch { return ""; }
  }

  function currentCueIdx() {
    if (!window.PL?.cues?.length) return -1;
    const t = (typeof plNow === "function" ? plNow() : 0) + (PL.subShift || 0);
    return PL.cues.findIndex((c) => t >= c.s && t <= c.e);
  }
  function currentCue() {
    const i = currentCueIdx();
    return i >= 0 ? PL.cues[i] : null;
  }

  // ---- 3. Playback Recipe Engine + Chapter Name Tick ----
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mountTopControls, { once: true });
  else mountTopControls();
  setInterval(() => {
    if (!window.PL?.open) return;
    mountTopControls();
    const v = document.getElementById("plVideo");
    if (!v) return;
    const t = typeof plNow === "function" ? plNow() : 0;
    const chEl = document.getElementById("plChapNow");
    if (chEl) {
      const ch = (PL.info?.chapters || []).filter((c) => c.start <= t).pop();
      chEl.textContent = ch?.title ? `· ${ch.title}` : "";
    }
    if (!v.paused) {
      const rSel = document.getElementById("plRate");
      if (!RECIPES.gap3x) _userBaseRate = +(rSel?.value || 1);
      if (PL.cues?.length) {
        const idx = currentCueIdx();
        if (RECIPES.autoPause) {
          const nearEnd = PL.cues.findIndex((c) => Math.abs((t + (PL.subShift || 0)) - c.e) < 0.14);
          if (nearEnd >= 0 && nearEnd !== _lastPausedCueIdx) {
            _lastPausedCueIdx = nearEnd;
            v.pause();
            return;
          }
        }
        if (RECIPES.gap3x) {
          const nextCue = PL.cues.find((c) => c.s > t + (PL.subShift || 0));
          const gap = idx < 0 && nextCue ? (nextCue.s - (t + (PL.subShift || 0))) : 0;
          const wantRate = (gap > 1.8) ? 3 : (_userBaseRate || 1);
          if (Math.abs(v.playbackRate - wantRate) > 0.05) v.playbackRate = wantRate;
        }
      }
    }
  }, 320);

  // ---- 4. Library Search Filter, Unshuffle & Searchable Transcript Tab ----
  let _preShuffleQueue = null;
  const _origDrawer = window.plDrawer;
  function enhanceDrawer() {
    const d = document.getElementById("plDrawer");
    const body = document.getElementById("pxBody");
    if (!d || d.hidden || !body) return;
    const tabs = d.querySelector(".px-tabs");
    if (tabs && !tabs.querySelector('[data-tab="transcript"]')) {
      const btn = document.createElement("button");
      btn.dataset.tab = "transcript";
      btn.textContent = "Transkript";
      const cls = tabs.querySelector('[data-tab="close"]');
      tabs.insertBefore(btn, cls || null);
      btn.onclick = () => {
        tabs.querySelectorAll("button").forEach((b) => b.classList.toggle("on", b === btn));
        renderTranscript(body);
      };
    }
    if (!body.querySelector("#pxSearchFilter") && !body.querySelector("#pxTrFilter")) {
      const inp = document.createElement("input");
      inp.id = "pxSearchFilter";
      inp.className = "px-filter";
      inp.placeholder = "Kütüphanede veya sırada ara…";
      body.prepend(inp);
      inp.oninput = () => {
        const q = inp.value.toLocaleLowerCase("tr").trim();
        body.querySelectorAll(".px-row, .px-acard, .px-series").forEach((el) => {
          el.hidden = q ? !el.textContent.toLocaleLowerCase("tr").includes(q) : false;
        });
      };
    }
    // Unshuffle butonu (siralamayi geri yukle)
    if (window.PX?.libTab === "queue" && _preShuffleQueue && !body.querySelector("#pxUnshuf")) {
      const ub = document.createElement("button");
      ub.id = "pxUnshuf";
      ub.className = "pl-b";
      ub.style.cssText = "width:100%;margin-bottom:8px";
      ub.textContent = "⤺ Karıştırmayı Geri Al (Unshuffle)";
      ub.onclick = () => {
        if (_preShuffleQueue && window.PX) {
          PX.queue = _preShuffleQueue.slice();
          PX.qi = PX.queue.indexOf(PL.info?.path || "");
          _preShuffleQueue = null;
          window.pxDrawerRender?.();
          window.toast?.("Orijinal sıra geri yüklendi ✓");
        }
      };
      body.querySelector("#pxSearchFilter")?.after(ub);
    }
  }
  function renderTranscript(body) {
    const cues = window.PL?.cues || [];
    body.innerHTML = `<input id="pxTrFilter" class="px-filter" placeholder="Transkript içinde ara…"><div id="pxTrList"></div>`;
    const listEl = body.querySelector("#pxTrList");
    const draw = (q = "") => {
      const low = q.toLocaleLowerCase("tr").trim();
      const filtered = cues.filter((c) => !low || String(c.text || "").toLocaleLowerCase("tr").includes(low));
      listEl.innerHTML = filtered.length ? filtered.map((c) => `<button class="px-tr-row" data-t="${c.s}"><b>${fmtT(c.s)}</b><span>${String(c.text || "").replace(/</g, "&lt;")}</span></button>`).join("")
        : `<p class="px-empty">${cues.length ? "Eşleşen replik yok." : "Bu medya için yüklü altyazı yok."}</p>`;
    };
    draw();
    body.querySelector("#pxTrFilter").oninput = (e) => draw(e.target.value);
    listEl.onclick = (e) => {
      const row = e.target.closest("[data-t]");
      if (row && typeof plSeek === "function") plSeek(parseFloat(row.dataset.t));
    };
  }
  if (typeof _origDrawer === "function") {
    window.plDrawer = function (...args) {
      const r = _origDrawer.apply(this, args);
      setTimeout(enhanceDrawer, 20);
      return r;
    };
  }
  const _origRender = window.pxDrawerRender;
  if (typeof _origRender === "function") {
    window.pxDrawerRender = function (...args) {
      const r = _origRender.apply(this, args);
      setTimeout(enhanceDrawer, 20);
      return r;
    };
  }
  document.addEventListener("click", (e) => {
    if (e.target.closest?.('[data-act="ashuf"]') && window.PX?.albums?.[PX.album]) {
      _preShuffleQueue = PX.albums[PX.album].tracks.map((x) => x.path);
    }
  }, true);
})();
