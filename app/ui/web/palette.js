// Kami Ctrl+K komut paleti: Komutlar + Dosyalar/Icerik ayrimi, sabit satir yuksekligi ve yukleme iskeleti.
"use strict";
(() => {
  const L = (tr, en) => ((typeof state !== "undefined" && state.lang === "en") || document.documentElement.lang === "en" ? en : tr);
  window.KPAL = window.KPAL || [];
  const extra = () => [
    { t: L("Kami Player'ı aç (kütüphane)", "Open Kami Player (library)"), run: () => window.pywebview?.api?.player_show({ library: true }) },
    { t: L("Ayarlar", "Settings"), run: () => document.getElementById("settings")?.showModal?.() },
    { t: L("Bildirim Merkezini Aç", "Open Notification Center"), run: () => document.querySelector('#skDock button[data-sk="notifs"]')?.click() },
    { t: L("Mini-Ada'yı Aç/Gizle", "Toggle Mini-Island"), run: () => window.pywebview?.api?.mini_island_toggle?.() },
    { t: L("Reader'ı Aç", "Open Kami Reader"), run: () => window.pywebview?.api?.reader_open?.() },
    { t: L("Kamify'ı Aç", "Open Kamify"), run: () => window.pywebview?.api?.music_open?.() },
    { t: L("Studio'yu Aç", "Open Kami Studio"), run: () => window.pywebview?.api?.studio_open?.() },
    { t: L("Picture'ı Aç", "Open Kami Picture"), run: () => window.pywebview?.api?.picture_open?.("") },
    { t: L("Games'i Aç", "Open Kami Games"), run: () => window.pywebview?.api?.games_open?.() },
    { t: L("Cleaner'ı Aç", "Open Kami Cleaner"), run: () => window.pywebview?.api?.cleaner_open?.() },
  ];
  const parseParamCmd = (raw) => {
    const s = String(raw || "").trim();
    if (!s.startsWith(">")) return [];
    const arg = s.slice(1).trim();
    const low = arg.toLocaleLowerCase("tr");
    const mSpd = low.match(/^h[ıi]z\s+(\d+(?:\.\d+)?)\s*(k|kb|kib|m|mb|mib)?$/i);
    if (mSpd) {
      const val = parseFloat(mSpd[1]);
      const unit = (mSpd[2] || "m").toLowerCase();
      const kib = Math.round(unit.startsWith("k") ? val : val * 1024);
      return [{ t: L(`Hız sınırını ${kib ? kib + " KB/s" : "sınırsız"} yap`, `Set speed limit to ${kib ? kib + " KB/s" : "unlimited"}`), ic: "⚡", run: async () => { await window.pywebview?.api?.set_setting?.("speed_limit_kib", kib); if (typeof toast === "function") toast(L("Hız güncellendi", "Speed updated")); } }];
    }
    const pMap = { tam: "full", full: "full", yayin: "stream", yayın: "stream", stream: "stream", oyun: "game", game: "game", oda: "room", room: "room", gece: "night", night: "night" };
    const mProf = low.match(/^profil\s+(\S+)/i);
    if (mProf && pMap[mProf[1]]) {
      const pk = pMap[mProf[1]];
      return [{ t: L(`Hız profilini '${pk}' yap`, `Switch speed profile to '${pk}'`), ic: "⚡", run: () => window.pywebview?.api?.speed_profile_set?.(pk) }];
    }
    const quick = [
      { k: "temizle", t: L("Bitenleri Temizle", "Clear Finished"), ic: "🧹", run: () => window.pywebview?.api?.clear_finished?.() },
      { k: "ada", t: L("Mini-Ada Aç / Kapat", "Toggle Mini-Island"), ic: "◎", run: () => window.pywebview?.api?.mini_island_toggle?.() },
      { k: "bildirim", t: L("Bildirim Merkezi", "Notification Center"), ic: "🔔", run: () => document.querySelector('#skDock button[data-sk="notifs"]')?.click() },
      { k: "reader", t: L("Kami Reader'ı Aç", "Open Kami Reader"), ic: "📖", run: () => window.pywebview?.api?.reader_open?.() },
      { k: "kamify", t: L("Kamify'ı Aç", "Open Kamify"), ic: "♪", run: () => window.pywebview?.api?.music_open?.() },
      { k: "studio", t: L("Kami Studio'yu Aç", "Open Kami Studio"), ic: "🎬", run: () => window.pywebview?.api?.studio_open?.() },
      { k: "player", t: L("Kami Player'ı Aç", "Open Kami Player"), ic: "▶", run: () => window.pywebview?.api?.player_show?.({ library: true }) },
      { k: "games", t: L("Kami Games'i Aç", "Open Kami Games"), ic: "🎮", run: () => window.pywebview?.api?.games_open?.() },
      { k: "picture", t: L("Kami Picture'ı Aç", "Open Kami Picture"), ic: "🖼", run: () => window.pywebview?.api?.picture_open?.("") },
    ];
    return quick.filter((x) => !low || x.k.includes(low) || x.t.toLocaleLowerCase("tr").includes(low));
  };
  const label = (b) => (b.getAttribute("title") || b.getAttribute("aria-label") || b.textContent || "").replace(/\s+/g, " ").trim();
  function items() {
    const seen = new Set(), out = [];
    for (const f of window.KPAL) { try { out.push(...(f() || [])); } catch { /* saglayici hatasi */ } }
    if (!window.KAMI_PLAYER_WINDOW) out.push(...extra());
    for (const b of document.querySelectorAll("button, [role=button], a[href='#']")) {
      if (b.closest("#kpal") || b.disabled || !b.offsetParent) continue;
      const t = label(b); if (!t || t.length < 2 || t.length > 70 || seen.has(t)) continue;
      seen.add(t); out.push({ t, run: () => b.click() });
    }
    return out;
  }
  let box, list, rows, inp, syncGlider, cur = [], sel = 0, remote = [], rq = "", rt = 0, loadingRemote = false;
  const ICON = { download: "⬇", file: "📄", book: "📖", series: "📚", studio: "🎬", rss: "📡" };
  function syncSel(scroll = true) {
    if (!rows) return;
    rows.querySelectorAll(".kp-i").forEach((el) => {
      el.classList.toggle("on", Number(el.dataset.i) === sel);
    });
    if (scroll) rows.querySelector(".kp-i.on")?.scrollIntoView?.({ block: "nearest" });
    syncGlider?.();
  }
  function fetchRemote(q) {
    clearTimeout(rt);
    if (q.length < 2) { remote = []; loadingRemote = false; return; }
    loadingRemote = true;
    rt = setTimeout(async () => {
      const api = window.pywebview?.api;
      if (!api?.global_search) { loadingRemote = false; return; }
      try {
        const r = (await api.global_search(q)) || [];
        if (!box || inp.value.trim() !== q) return;
        rq = q; remote = r.map((x) => ({ t: x.t, sub: x.sub, ic: ICON[x.kind] || "•", remote: true, run: () => api.global_open(x) }));
      } catch { /* yok */ }
      loadingRemote = false;
      if (box && inp.value.trim() === q) render(true);
    }, 180);
  }
  function render(fromRemote) {
    if (!list || !rows) return;
    const prevH = list.getBoundingClientRect().height;
    const q = inp.value.toLowerCase().trim(), qRaw = inp.value.trim();
    if (!fromRemote && !qRaw.startsWith(">")) fetchRemote(qRaw);
    const norm = (x) => x.toLocaleLowerCase("tr").normalize("NFD").replace(/[\u0300-\u036f]/g, "").replace(/ı/g, "i");
    const cmdHits = parseParamCmd(qRaw);
    const qq = norm(q).split(/\s+/).filter(Boolean);
    const local = qRaw.startsWith(">") ? cmdHits : items().filter((x) => { const h = norm(x.t + " " + (x.sub || "")); return qq.every((w) => h.includes(w)); }).slice(0, 10);
    const rem = (!qRaw.startsWith(">") && rq && qRaw === rq) ? remote.slice(0, 14) : [];
    cur = [...local, ...rem];
    sel = Math.min(sel, Math.max(0, cur.length - 1));
    const esc = (t) => String(t).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
    const rowHtml = (x, i) => `<div class="kp-i${i === sel ? " on" : ""}" data-i="${i}">${x.ic ? `<em>${x.ic}</em>` : ""}<span>${esc(x.t)}</span>${x.sub ? `<small>${esc(x.sub)}</small>` : ""}</div>`;
    let html = "";
    if (local.length) html += `<div class="kp-sec">${L("Komutlar", "Commands")}</div>` + local.map((x, idx) => rowHtml(x, idx)).join("");
    if (rem.length) html += `<div class="kp-sec">${L("Dosyalar ve içerik", "Files & content")}</div>` + rem.map((x, idx) => rowHtml(x, local.length + idx)).join("");
    else if (loadingRemote && qRaw.length >= 2) html += `<div class="kp-sec">${L("Dosyalar ve içerik", "Files & content")}</div><div class="kp-skel"></div><div class="kp-skel"></div>`;
    rows.innerHTML = html || `<div class="kp-e">${L("Sonuç yok", "No results")}</div>`;
    if (prevH > 0) {
      list.style.height = `${prevH}px`;
      void list.offsetHeight;
      list.style.height = "auto";
    }
    syncGlider?.();
  }
  function close() { box?.remove(); box = null; list = null; rows = null; syncGlider = null; }
  function open() {
    if (box) return close();
    box = document.createElement("div"); box.id = "kpal";
    box.innerHTML = `<div class="kp-w"><input aria-label="${L("Ara", "Search")}" placeholder="${L("Dosya, özellik ya da komut ara… (Esc kapatır)", "Search files, features, commands… (Esc)")}"><div class="kp-l"><div class="kp-rows"></div></div></div>`;
    document.body.appendChild(box);
    inp = box.querySelector("input"); list = box.querySelector(".kp-l"); rows = box.querySelector(".kp-rows");
    syncGlider = window.KamiMotion?.bindGlider?.(list, ".kp-i", "on") || null;
    box.addEventListener("click", (e) => { const it = e.target.closest(".kp-i"); if (it) { const x = cur[+it.dataset.i]; close(); x?.run(); } else if (e.target === box) close(); });
    list.addEventListener("pointermove", (e) => {
      const it = e.target.closest(".kp-i");
      if (!it) return;
      const idx = +it.dataset.i;
      if (!Number.isNaN(idx) && idx !== sel) { sel = idx; syncSel(false); }
    }, { passive: true });
    inp.addEventListener("input", () => { sel = 0; render(); });
    inp.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { sel = Math.min(cur.length - 1, sel + 1); syncSel(true); e.preventDefault(); }
      else if (e.key === "ArrowUp") { sel = Math.max(0, sel - 1); syncSel(true); e.preventDefault(); }
      else if (e.key === "Enter") { const x = cur[sel]; close(); x?.run(); }
      else if (e.key === "Escape") close();
      e.stopPropagation();
    });
    render(); inp.focus();
  }
  document.addEventListener("keydown", (e) => { if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); e.stopPropagation(); open(); } }, true);
  const st = document.createElement("style");
  st.textContent = `#kpal{position:fixed;inset:0;z-index:9999;background:rgba(5,4,8,.55);display:flex;justify-content:center;padding-top:14vh}
  #kpal .kp-w{width:min(560px,90vw);height:max-content;background:#0F0B16;border:1px solid rgba(157,107,255,.45);border-radius:12px;box-shadow:0 20px 60px rgba(0,0,0,.6),0 0 30px rgba(124,58,237,.22);overflow:hidden;font:14px "Segoe UI Variable","Segoe UI",system-ui,sans-serif;color:#EDE9F6}
  #kpal input{width:100%;box-sizing:border-box;padding:14px 16px;border:0;border-bottom:1px solid #2B2238;background:none;color:#fff;font:600 15px "Chakra Petch","Segoe UI",sans-serif;outline:none}
  #kpal .kp-l{max-height:52vh;overflow:auto;padding:6px}
  #kpal .kp-sec{font:600 10.5px "Chakra Petch",sans-serif;letter-spacing:.08em;text-transform:uppercase;color:#8E86A3;padding:6px 10px 3px}
  #kpal .kp-i{height:36px;box-sizing:border-box;padding:0 12px;border-radius:8px;cursor:pointer;display:flex;align-items:center;gap:10px}
  #kpal .kp-i em{font-style:normal;width:18px;text-align:center;opacity:.88}#kpal .kp-i span{flex:1;min-width:0;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  #kpal .kp-i small{color:#8E86A3;font-size:11.5px;max-width:45%;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}#kpal .kp-i.on,#kpal .kp-i:hover{background:#3B1580}
  #kpal .kp-skel{height:30px;margin:4px 8px;border-radius:6px;background:linear-gradient(90deg,#191326 25%,#261D3A 50%,#191326 75%);background-size:200% 100%;animation:kpSk 1.1s infinite}
  @keyframes kpSk{0%{background-position:200% 0}100%{background-position:-200% 0}}
  #kpal .kp-e{padding:12px;color:#8E86A3}`;
  document.head.appendChild(st);
})();
