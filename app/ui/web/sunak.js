// Kami "Sunak" katmani. Eski DOM ve JS'e dokunmaz; ustune biner, durumu STATE_HOOKS ile alir.
"use strict";

const SK = { autoPlay: new Set(JSON.parse((() => { try { return localStorage.getItem("kami.autoplay") || "[]"; } catch { return "[]"; } })())), sel: null, page: 0, peak: 1, happyUntil: 0, prevStatus: new Map(), eye: null, orbit: 0, speedFrac: 0, built: false, multi: new Set(), hidden: new Set(), undo: null };
const SK_RING_R = 132, SK_RING_C = 2 * Math.PI * SK_RING_R;
const SK_STRIP_W = 162;   // 150 + bosluk

const skIcon = {
  pause: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M6 4h4v16H6zM14 4h4v16h-4z"/></svg>',
  play: '<svg viewBox="0 0 24 24" fill="currentColor"><path d="M7 4l13 8-13 8z"/></svg>',
  file: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M6 2h8l5 5v15H6z M14 2v5h5"/></svg>',
  folder: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h7l2 2h9v12H3z"/></svg>',
  x: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M5 5l14 14M19 5L5 19"/></svg>',
  sub: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 5h18v14H3z M6 12h5 M13 12h5 M6 15h9"/></svg>',
  voc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 10v4 M8 7v10 M12 4v16 M16 8v8 M20 11v2"/></svg>',
  list: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 6h16M4 12h16M4 18h16"/></svg>',
  rd: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 2L4 14h7l-1 8 9-12h-7z"/></svg>',
  follow: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M2 12s4-7 10-7 10 7 10 7-4 7-10 7S2 12 2 12z"/></svg>',
  hist: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 2"/></svg>',
  batch: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>',
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"><circle cx="12" cy="12" r="3.2"/><path d="M19.4 13a7.6 7.6 0 0 0 0-2l2-1.6-2-3.4-2.4 1a7.4 7.4 0 0 0-1.7-1L15 3.5h-6l-.3 2.5a7.4 7.4 0 0 0-1.7 1l-2.4-1-2 3.4L4.6 11a7.6 7.6 0 0 0 0 2l-2 1.6 2 3.4 2.4-1a7.4 7.4 0 0 0 1.7 1l.3 2.5h6l.3-2.5a7.4 7.4 0 0 0 1.7-1l2.4 1 2-3.4z"/></svg>',
  retry: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 12a8 8 0 1 0 3-6.2M4 4v5h5"/></svg>',
};

// Kami Player artik ayri pencere: istekler Python kuyruguna gider, pencere acilir / one gelir
function playerOpen(id) { return api.player_show({ id }); }
function playerOpenUrl(url) { return api.player_show({ url }); }
function playerLibrary() { return api.player_show({ library: true }); }

const skTr = () => state.lang !== "en";
const skL = (tr, en) => (skTr() ? tr : en);
const skPct = (d) => (d.status === "complete" ? 100 : d.size ? Math.min(100, Math.floor((d.downloaded / d.size) * 100)) : 0);
const skKind = { video: ["VİDEO", "VIDEO"], music: ["MÜZİK", "MUSIC"], archive: ["ARŞİV", "ARCHIVE"], program: ["PROGRAM", "PROGRAM"], document: ["BELGE", "DOC"], other: ["DOSYA", "FILE"] };

function skBuild() {
  document.body.classList.add("sunak");
  const root = document.createElement("div");
  root.id = "sunak";
  root.innerHTML = `
  <div class="sk-main">
    <div class="sk-head"><span class="sk-logo">KAMI</span>
      <nav class="sk-tabs" id="skTabs">
        <button type="button" class="sk-tab" data-mod="player" title="Player (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><polygon points="7 4 20 12 7 20 7 4"/></svg><span>Player</span></button>
        <button type="button" class="sk-tab" data-mod="studio" title="Studio (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 9h18M8 5v4M16 5v4"/></svg><span>Studio</span></button>
        <button type="button" class="sk-tab" data-mod="picture" title="Picture (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg><span>Picture</span></button>
        <button type="button" class="sk-tab" data-mod="reader" title="Reader (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M4 5a2 2 0 0 1 2-2h13v16H6a2 2 0 0 0-2 2z"/><path d="M4 19V5"/></svg><span>Reader</span></button>
        <button type="button" class="sk-tab" data-mod="games" title="Games (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><rect x="2" y="7" width="20" height="10" rx="5"/><path d="M7 10v4M5 12h4M15.5 11h.01M18 13h.01"/></svg><span>Games</span></button>
        <button type="button" class="sk-tab" data-mod="music" title="Kamify (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M9 18V5l11-2v13"/><circle cx="6" cy="18" r="3"/><circle cx="17" cy="16" r="3"/></svg><span>Kamify</span></button>
        <button type="button" class="sk-tab" data-mod="cleaner" title="Cleaner (ayrı pencerede açılır)"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round"><path d="M3 5h18l-7 8v6l-4 2v-8z"/></svg><span>Cleaner</span></button>
      </nav>
      <div class="sk-status"><button type="button" class="sk-docdot" id="skDocDot" hidden title="Kami Doktor: Sorun tespit edildi (tıkla)" aria-label="Kami Doktor uyarısı"></button><button type="button" class="sk-room sk-roompill" data-mod="room" id="skRoomPill" title="Kami Oda: sesli oda, ekran paylaşımı, birlikte izleme"><i class="sk-dot"></i><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3z"/><path d="M19 11a7 7 0 0 1-14 0M12 18v3"/></svg><span>${skL("Oda", "Room")}</span><i class="sk-tab-badge" id="skRoomN"></i></button><span class="sk-chip">${skL("motor", "engine")} <b id="skEngine">…</b></span><span class="sk-chip">${skL("köprü", "bridge")} <b id="skBridge">…</b></span></div></div>
    <div class="sk-top">
      <div class="sk-altar" id="skAltar">
        <svg class="sk-ring" viewBox="0 0 300 300">
          <defs><linearGradient id="skRingG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="var(--sk-violet)" style="stop-color:var(--sk-violet)"/><stop offset="1" stop-color="#2EE6A6"/></linearGradient></defs>
          <circle cx="150" cy="150" r="${SK_RING_R}" fill="none" stroke="#1C1228" stroke-width="10"/>
          <circle class="sk-ring-fill" cx="150" cy="150" r="${SK_RING_R}" fill="none" stroke="url(#skRingG)" stroke-width="10" stroke-linecap="butt"
            stroke-dasharray="${SK_RING_C}" stroke-dashoffset="${SK_RING_C}" transform="rotate(-90 150 150)"/>
          <g id="skOrbit"><circle cx="150" cy="${150 - SK_RING_R - 14}" r="3" fill="#C4B5FD"/><circle cx="150" cy="${150 + SK_RING_R + 14}" r="2" fill="#2EE6A6"/></g>
        </svg>
        <canvas class="sk-char" id="skEye" width="403" height="614"></canvas>
      </div>
      <div class="sk-speed">
        <div class="sk-speed-num"><span id="skNum">0</span><small id="skUnit">B/s</small></div>
        <div class="sk-speed-sub" id="skSub"></div>
        <div class="sk-speed-cnt" id="skCnt"></div>
        <canvas class="sk-spark" id="skSpark" width="640" height="128"></canvas>
        <div class="sk-mood" id="skMood"></div>
      </div>
      <div class="sk-gauges" id="skGauges"></div>
    </div>
    <div class="sk-strips">
      <button class="sk-arrow prev" id="skPrev" aria-label="${skL("önceki", "previous")}"></button>
      <div class="sk-track-wrap" id="skWrap"><div class="sk-track" id="skTrack"></div></div>
      <button class="sk-arrow next" id="skNext" aria-label="${skL("sonraki", "next")}"></button>
    </div>
    <div class="sk-dots" id="skDots"></div>
    <div class="sk-bar" id="skBar"></div>
    <div class="sk-detail" id="skDetail"></div>
    <div class="sk-cmd" id="skCmd"><span>›</span></div>
  </div>
  <nav class="sk-dock" id="skDock">
    <button data-sk="library" title="${skL("Kütüphane (Kami Player)", "Library (Kami Player)")}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h4v16H4zM10 4h4v16h-4zM16 5l4 1-3 14-4-1z"/></svg></button>
    <button data-sk="list" title="${skL("Liste", "List")}">${skIcon.list}</button>
    <button data-sk="notifs" title="${skL("Bildirimler", "Notifications")}" style="position:relative"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9"/><path d="M13.73 21a2 2 0 0 1-3.46 0"/></svg><b class="sk-notif-badge" id="skNotifN" hidden></b></button>
    <button data-sk="rd" title="Real-Debrid">${skIcon.rd}</button>
    <button data-sk="follow" title="${skL("Takip", "Follow")}">${skIcon.follow}<b id="skFollowN" hidden></b></button>
    <button data-sk="history" title="${skL("Geçmiş", "History")}">${skIcon.hist}</button>
    <button data-sk="batch" title="${skL("Toplu", "Batch")}">${skIcon.batch}</button>
    <button data-sk="convert" title="${skL("Dönüştürücü", "Converter")}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8h13l-3-3M20 16H7l3 3"/></svg></button>
    <button data-sk="ai" class="ai" title="${skL("AI altyazı / vokal", "AI subtitle / vocals")}">${skIcon.sub}</button>
    <button data-sk="fx" title="${skL("Arka plan efektleri aç / kapat", "Background effects on / off")}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 3l1.8 4.6L18 9l-4.2 1.4L12 15l-1.8-4.6L6 9l4.2-1.4zM18 15l.9 2.1L21 18l-2.1.9L18 21l-.9-2.1L15 18l2.1-.9z"/></svg></button>
    <button data-sk="settings" title="${skL("Ayarlar", "Settings")}">${skIcon.gear}</button>
  </nav>
  <div class="sk-backdrop" id="skBackdrop"></div>
  <button class="sk-drawer-close" id="skClose" aria-label="${skL("kapat", "close")}">${skIcon.x}<span>${skL("Kapat", "Close")}</span></button>`;
  document.body.prepend(root);
  root.querySelector("#skDocDot")?.addEventListener("click", () => window.KamiDoctor?.open?.());
  // eski ekleme formu komut satirina tasinir (dinleyicileri onunla gelir)
  const form = $("#addForm");
  if (form) {
    form.classList.add("add"); $("#skCmd").appendChild(form);
    form.addEventListener("submit", () => window.KamiFX?.sparkFrom?.($("#skCmd"), $("#skAltar")));
    const watch = document.createElement("button");   // indirmeden izle (yt-dlp / Real-Debrid / dogrudan)
    watch.type = "button"; watch.className = "btn sk-watch"; watch.textContent = skL("İzle", "Watch");
    watch.title = skL("İndirmeden Kami Player'da izle", "Stream in Kami Player without downloading");
    watch.onclick = () => { const u = $("#addInput").value.trim(); if (u) playerOpenUrl(u.split(/\s+/)[0]); else $("#addInput").focus(); };
    form.querySelector('button[type="submit"]')?.before(watch);
  }
  $("#addInput")?.setAttribute("placeholder", skL("Bağlantı yapıştır ya da dosyayı ruha bırak…", "Paste a link or drop a file on the spirit…"));
  skBind();
  if (window.KamiEye) {
    // Sunak'ta tam boy karakter; sadece goz kesiti (eye/assets) eklenti ve widget icin
    SK.eye = new KamiEye($("#skEye"), { assets: "eye/char/", eyeY: 0.38, mirrorFrame: true });
    SK.eye.ready.then(() => {
      if (window.KamiSunakGPU?.available?.()) {
        window.KamiSunakGPU.initAltar($("#skAltar"), SK.eye).then((ok) => {
          if (!ok) SK.eye.start();
        });
      } else {
        SK.eye.start();
      }
    }).catch((e) => console.error(e));
  }
  requestAnimationFrame(skFrame);
  SK.built = true;
}

function skBind() {
  $("#skPrev").addEventListener("click", () => skPage(-1));
  $("#skNext").addEventListener("click", () => skPage(1));
  $("#skWrap").addEventListener("wheel", (e) => { if (Math.abs(e.deltaY) + Math.abs(e.deltaX) > 8) { e.preventDefault(); skPage((e.deltaY || e.deltaX) > 0 ? 1 : -1); } }, { passive: false });
  $("#skTrack").addEventListener("dblclick", (e) => {
    const b = e.target.closest(".sk-strip"); const d = b && state.items.find((x) => String(x.id) === b.dataset.id);
    if (d && d.status === "complete" && ["video", "music"].includes(d.category)) playerOpen(d.id);
  });
  $("#skTrack").addEventListener("click", (e) => {
    if (e.target.closest(".sk-star")) { const id = e.target.closest(".sk-strip")?.dataset.id; const d = state.items.find((x) => String(x.id) === id); if (d) { e.stopPropagation(); skFav(d); } return; }
    const b = e.target.closest(".sk-strip"); if (!b) return;
    const its = skItems(), id = its.find((d) => String(d.id) === b.dataset.id)?.id;
    if (id == null) return;
    if (e.shiftKey && SK.sel != null) {   // aralik: secili karttan tiklanana kadar
      const a = its.findIndex((d) => d.id === SK.sel), z = its.findIndex((d) => d.id === id);
      if (!e.ctrlKey) SK.multi.clear();
      for (let i = Math.min(a, z); i <= Math.max(a, z); i++) SK.multi.add(its[i].id);
    } else if (e.ctrlKey || e.metaKey) {
      if (!SK.multi.size && SK.sel != null) SK.multi.add(SK.sel);
      SK.multi.has(id) ? SK.multi.delete(id) : SK.multi.add(id);
      if (SK.multi.size === 1 && SK.multi.has(id) && id !== SK.sel) { /* tek secim */ }
    } else SK.multi.clear();
    SK.sel = id; skRender(true);
  });
  $("#skDots").addEventListener("click", (e) => { const i = e.target.dataset.i; if (i != null) { SK.sel = skItems()[+i]?.id; skRender(); } });
  $("#skBar").addEventListener("click", skBarAction);
  $("#skDock").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) skDock(b.dataset.sk); });
  $("#skClose").addEventListener("click", skCloseDrawer);
  $("#skBackdrop").addEventListener("click", skCloseDrawer);   // cekmece disina tiklayinca kapanir
  document.addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, select") || document.querySelector("dialog[open]")) return;
    if (e.key === "Escape" && SK.multi.size && !document.body.classList.contains("sk-drawer")) { SK.multi.clear(); skRender(true); return; }
    if (e.key === "Escape") skCloseDrawer();
    if (document.body.classList.contains("sk-drawer")) return;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "a") { e.preventDefault(); skItems().forEach((d) => SK.multi.add(d.id)); skRender(true); return; }
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "z" && SK.undo) { e.preventDefault(); skUndo(); return; }
    if (e.key === "Delete") { e.preventDefault(); skDeleteSel(e.shiftKey); return; }
    if (e.key === "F2") { e.preventDefault(); skRename(); return; }
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { skMoveSel(e.key === "ArrowRight" ? 1 : -1); e.preventDefault(); }
  });
  const altar = $("#skAltar");
  altar.addEventListener("mouseenter", () => SK.eye?.set({ lid: 1 }));
  altar.addEventListener("mouseleave", () => SK.eye?.set({ lid: 0 }));
  $("#skEye")?.addEventListener("click", () => {
    SK.eye?.poke?.();
    const act = (state.items || []).filter((x) => x.status === "active").length;
    toast(act ? skL(`🔥 ${act} aktif indirme işleniyor`, `🔥 ${act} active downloads`) : skL("👁 Kami Tılsım Ruhu hazır · Çift tıkla: kostüm", "👁 Kami Spirit ready · Double-click: costume"));
  });
  const COSTUME_CYCLE = ["", "studio", "player", "reader", "chill"];
  const COSTUME_NAMES = { "": "Normal", studio: "Studio", player: "Player", reader: "Reader", chill: "Gece / Dinlenme" };
  $("#skEye")?.addEventListener("dblclick", () => {
    const cur = SK.eye?.target?.costume || "";
    const next = COSTUME_CYCLE[(COSTUME_CYCLE.indexOf(cur) + 1) % COSTUME_CYCLE.length];
    SK.eye?.set({ costume: next });
    try { localStorage.setItem("kami.costume", next); } catch {}
    toast(`🎭 Kostüm: ${COSTUME_NAMES[next] || next}`);
  });
  try { const savedC = localStorage.getItem("kami.costume"); if (savedC) SK.eye?.set({ costume: savedC }); } catch {}
  let tipEl = null;   // sag ray etiketi (title -> data-tip; yerel ipucu ile cift cikmasin)
  $("#skDock")?.addEventListener("mouseover", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.title) { b.dataset.tip = b.title; b.setAttribute("aria-label", b.title); b.removeAttribute("title"); }
    if (!b.dataset.tip) return;
    if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "sk-tip"; document.body.appendChild(tipEl); }
    const r = b.getBoundingClientRect();
    tipEl.textContent = b.dataset.tip;
    tipEl.style.left = (r.left - 8) + "px"; tipEl.style.top = (r.top + r.height / 2) + "px";
    tipEl.classList.add("on");
  });
  $("#skDock")?.addEventListener("mouseout", (e) => { if (!e.relatedTarget?.closest?.("#skDock button") || e.relatedTarget.closest("button") !== e.target.closest("button")) tipEl?.classList.remove("on"); });
  let peekT = 0, peekEl = null;
  const hidePeek = () => { clearTimeout(peekT); peekEl?.classList.remove("on"); };
  $("#skTrack")?.addEventListener("mouseover", (e) => {
    const st = e.target.closest(".sk-strip"); if (!st) return;
    if (st.title) st.removeAttribute("title");   // onizleme karti var; yerel ipucu ustune binmesin
    if (peekEl?.classList.contains("on") && peekEl.dataset.id === st.dataset.id) return;
    clearTimeout(peekT);
    peekT = setTimeout(() => {
      const d = (state.items || []).find((x) => String(x.id) === st.dataset.id); if (!d) return;
      if (!peekEl) { peekEl = document.createElement("div"); peekEl.className = "sk-peek"; document.body.appendChild(peekEl); }
      const r = st.getBoundingClientRect();
      peekEl.innerHTML = `<b>${escapeHtml(d.filename || d.url || "")}</b><small>${(skKind[d.category] || skKind.other)[skTr() ? 0 : 1]} · ${d.size ? fmtBytes(d.size) : "?"} · %${skPct(d)}</small>`;
      peekEl.style.left = Math.max(12, Math.min(window.innerWidth - 292, r.left)) + "px";
      peekEl.style.top = Math.max(12, r.top - 72) + "px";
      peekEl.dataset.id = st.dataset.id;
      peekEl.classList.add("on");
      if (d.status === "complete" && ["video", "music"].includes(d.category)) {   // medya ozeti (+ video karesi)
        const id = st.dataset.id;
        api.item_peek(d.id).then((m) => {
          if (!m || !peekEl.classList.contains("on") || peekEl.dataset.id !== id) return;
          const res = m.h ? (m.h >= 2100 ? "4K" : m.h >= 1400 ? "1440p" : m.h >= 1000 ? "1080p" : m.h >= 700 ? "720p" : m.h + "p") : "";
          const bits = [res, m.duration ? fmtEta(m.duration) : "", [m.vcodec, m.acodec].filter(Boolean).join(" / ").toUpperCase()].filter(Boolean);
          peekEl.insertAdjacentHTML("afterbegin", m.thumb ? `<img class="sk-peek-th" src="${m.thumb}" alt="">` : "");
          if (bits.length) peekEl.insertAdjacentHTML("beforeend", `<small class="sk-peek-m">${escapeHtml(bits.join(" · "))}</small>`);
          const r2 = st.getBoundingClientRect();
          peekEl.style.top = Math.max(12, r2.top - peekEl.offsetHeight - 8) + "px";
        }).catch(() => {});
      }
    }, 360);
  });
  $("#skTrack")?.addEventListener("mouseout", (e) => {   // seritler her yenilemede yeniden cizilir: ayni seride gecis kapatmasin
    const st = e.target.closest(".sk-strip"); if (!st) return;
    if (e.relatedTarget?.closest?.(".sk-strip")?.dataset.id === st.dataset.id) return;
    hidePeek();
  });
  document.addEventListener("mousemove", (e) => SK.eye?.lookAt(e.clientX, e.clientY));
  // Modul baslatici: her uygulama kendi ayri penceresinde acilir (tam ekran ve kisayollar bozulmaz)
  const LAUNCHERS = {
    player: () => api?.player_show?.({}),
    studio: () => api?.studio_show?.(""),
    picture: () => api?.picture_open?.(""),
    reader: () => api?.reader_show?.(""),
    room: () => api?.room_open?.(true),
    games: () => api?.games_open?.(),
    music: () => api?.music_open?.(),
    cleaner: () => api?.cleaner_open?.(),
  };
  const MOD_COSTUMES = { player: "player", studio: "studio", reader: "reader", music: "player", games: "speed", picture: "done", cleaner: "" };
  $("#skTabs")?.addEventListener("click", (e) => {
    const b = e.target.closest(".sk-tab[data-mod], #skRoomPill");
    if (!b) return;
    const mod = b.dataset.mod;
    if (mod === "home") { skCloseDrawer?.(); return; }
    if (mod in MOD_COSTUMES) SK.eye?.set({ costume: MOD_COSTUMES[mod] });
    LAUNCHERS[mod]?.();
  });
  window.addEventListener("focus", () => {
    try { SK.eye?.set({ costume: localStorage.getItem("kami.costume") || "" }); } catch {}
  });
  $("#skRoomPill")?.addEventListener("click", () => LAUNCHERS.room?.());
  // dosya surukleme: ruh uyanir, birakinca yutar (asil ekleme extras.js'teki drop dinleyicisinde)
  let depth = 0;
  document.addEventListener("dragenter", () => { depth++; altar.classList.add("drop"); SK.eye?.set({ mood: "alert" }); window.KamiSunakGPU?.setState?.({ drop: true, mood: "alert" }); });
  document.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; altar.classList.remove("drop"); SK.eye?.set({ mood: "idle" }); window.KamiSunakGPU?.setState?.({ drop: false, mood: "idle" }); } });
  document.addEventListener("drop", () => {
    depth = 0; altar.classList.remove("drop"); altar.classList.remove("swallow"); void altar.offsetWidth; altar.classList.add("swallow");
    window.KamiSunakGPU?.triggerSwallow?.();
    SK.eye?.set({ mood: "happy" }); SK.happyUntil = Date.now() + 1500;
  });
}

// listede gosterilecekler: once aktif, sonra bekleyen/duraklatilan, sonra hata, en son biten
const SK_ORDER = { active: 0, waiting: 1, queued: 1, confirm: 1, paused: 2, error: 3, complete: 4 };
function skItems() {
  const key = (d) => (d.status === "active" ? 0 : d.extra?.fav ? 0.5 : SK_ORDER[d.status] ?? 5);   // favoriler aktiflerden hemen sonra
  return (state.items || []).filter((d) => d.status !== "removed" && !SK.hidden.has(d.id))
    .map((d, i) => [d, i]).sort((a, b) => key(a[0]) - key(b[0]) || a[1] - b[1]).map((x) => x[0]);
}
// ---------- coklu secim: sil / geri al / yeniden adlandir / favori ----------
function skDeleteSel(withFiles) {
  const its = skItems();
  const ids = SK.multi.size ? [...SK.multi] : SK.sel != null ? [SK.sel] : [];
  if (!ids.length) return;
  if (SK.undo) skCommitUndo();   // onceki bekleyen silme kesinlessin
  const firstIdx = Math.min(...ids.map((id) => its.findIndex((d) => d.id === id)).filter((i) => i >= 0));
  ids.forEach((id) => SK.hidden.add(id));
  SK.multi.clear();
  const rest = skItems();
  SK.sel = rest[Math.min(firstIdx, rest.length - 1)]?.id ?? null;   // yanindaki kart secilir: basa atmaz
  const page = SK.page;
  skRender(true); SK.page = page; skRender(true);
  const n = ids.length;
  SK.undo = { ids, withFiles, t: setTimeout(skCommitUndo, 6000) };
  skUndoToast(withFiles ? skL(`${n} dosya Çöp Kutusu'na gidecek`, `${n} file(s) will go to the Recycle Bin`) : skL(`${n} indirme listeden kaldırıldı`, `${n} download(s) removed`));
}
function skCommitUndo() {
  const u = SK.undo; if (!u) return;
  clearTimeout(u.t); SK.undo = null;
  $("#skUndo")?.remove();
  u.ids.forEach((id) => api.remove(id, !!u.withFiles).catch?.(() => {}));
  setTimeout(() => u.ids.forEach((id) => SK.hidden.delete(id)), 4000);   // liste yenilenince zaten gider
}
function skUndo() {
  const u = SK.undo; if (!u) return;
  clearTimeout(u.t); SK.undo = null;
  u.ids.forEach((id) => SK.hidden.delete(id));
  $("#skUndo")?.remove();
  SK.sel = u.ids[0]; skRender();
}
function skUndoToast(msg) {
  $("#skUndo")?.remove();
  const el = document.createElement("div");
  el.id = "skUndo"; el.className = "sk-undo";
  el.innerHTML = `<span>${escapeHtml(msg)}</span><button type="button">${skL("Geri al", "Undo")} <kbd>Ctrl+Z</kbd></button><i></i>`;
  el.querySelector("button").onclick = skUndo;
  document.body.appendChild(el);
}
async function skFav(d) {
  await api.set_favorite(d.id, !d.extra?.fav);
  d.extra = { ...(d.extra || {}), fav: !d.extra?.fav };
  skRender(true);
}
function skRename() {
  const d = state.items.find((x) => x.id === SK.sel);
  if (!d || d.status !== "complete") { toast(skL("Sadece biten dosyalar yeniden adlandırılabilir", "Only finished files can be renamed"), true); return; }
  const name = $("#skBar .sk-bar-name"); if (!name) return;
  const full = d.filename || "", dot = full.lastIndexOf(".");
  const inp = document.createElement("input");
  inp.className = "sk-rename"; inp.value = full; inp.spellcheck = false;
  name.replaceWith(inp); inp.focus(); inp.setSelectionRange(0, dot > 0 ? dot : full.length);
  let done = false;
  const finish = async (save) => {
    if (done) return; done = true;
    inp.remove(); $("#skBar").innerHTML = "";   // kutu kalkmazsa cubuk hic yenilenmiyordu
    if (save && inp.value.trim() && inp.value.trim() !== full) {
      const r = await api.rename_download(d.id, inp.value.trim());
      if (!r?.ok) toast(skL("Yeniden adlandırılamadı: ", "Rename failed: ") + ({ exists: skL("bu adda dosya var", "name exists"), no_file: skL("dosya bulunamadı", "file missing") }[r?.error] || r?.error || "?"), true);
      else { d.filename = r.path.split(/[\\/]/).pop(); d.path = r.path; }
    }
    skRender(true);
  };
  inp.addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") finish(true); if (e.key === "Escape") finish(false); });
  inp.addEventListener("blur", () => finish(true));
}
function skPerPage() { return Math.max(1, Math.floor(($("#skWrap").clientWidth + 12) / SK_STRIP_W)); }
function skPage(dir) {
  const n = skItems().length, per = skPerPage();
  SK.page = Math.max(0, Math.min(Math.max(0, n - per), SK.page + dir * per));
  SK.sel = skItems()[SK.page]?.id ?? SK.sel;   // secim yeni sayfaya gecer, sonraki tick geri kaydirmasin
  skRender(true);
}
function skMoveSel(dir) {
  const its = skItems(); if (!its.length) return;
  const i = Math.max(0, its.findIndex((d) => d.id === SK.sel));
  SK.sel = its[Math.max(0, Math.min(its.length - 1, i + dir))].id;
  skRender();
}

function skLiquidColors(d) {
  if (d.status === "complete") return ["#2EE6A6", "#0FA37A"];
  if (d.status === "error") return ["#FF4D6A", "#8E1D33"];
  if (d.status === "active") return [getComputedStyle(document.documentElement).getPropertyValue("--sk-violet").trim() || "#7C4DFF", "#2EE6A6"];
  return ["#4A3D63", "#2A2238"];
}
function skWave(color, amp) {
  // iki tam dalga (300px), kayarak dongu yapar
  let p = `M0 ${10}`;
  for (let x = 0; x < 300; x += 75) p += ` Q${x + 18.75} ${10 - amp} ${x + 37.5} 10 T${x + 75} 10`;
  return `<svg class="sk-wave" viewBox="0 0 300 20" height="20" style="top:-10px" preserveAspectRatio="none"><path d="${p} V20 H0 Z" fill="${color}"/></svg>`;
}
function skStripHtml(d) {
  const pct = skPct(d), [c1, c2] = skLiquidColors(d);
  const kind = (skKind[d.category] || skKind.other)[skTr() ? 0 : 1];
  const x = d.extra || {};
  const tags = [];
  if (x.ai_whisper === "done") tags.push(`<span class="sk-tag ok">SRT</span>`);
  else if (["queued", "running"].includes(x.ai_whisper)) tags.push(`<span class="sk-tag">AI ${x.ai_whisper_p || 0}%</span>`);
  if (x.ai_uvr === "done") tags.push(`<span class="sk-tag ok">${skL("VOKAL", "STEMS")}</span>`);
  else if (["queued", "running"].includes(x.ai_uvr)) tags.push(`<span class="sk-tag">UVR ${x.ai_uvr_p || 0}%</span>`);
  if (d.media_format) tags.push(`<span class="sk-tag">${escapeHtml(String(d.media_format).toUpperCase())}</span>`);
  let sub = "";
  if (d.status === "active") sub = `${fmtBytes(d.speed || 0)}/s${d.size && d.speed ? " · " + fmtEta((d.size - d.downloaded) / d.speed) : ""}`;
  else if (d.status === "complete") sub = d.size ? fmtBytes(d.size) : skL("bitti", "done");
  else if (d.status === "error") sub = skL("hata", "error");
  else if (d.status === "paused") sub = skL("duraklatıldı", "paused");
  else sub = skL("sırada", "queued");
  const bubbles = d.status === "active" ? [18, 52, 88, 120].map((l, i) => `<i class="sk-bubble" style="left:${l}px;animation-delay:${i * 0.7}s"></i>`).join("") : "";
  const h = Math.max(pct, d.status === "active" ? 4 : 0), wavy = h >= 8;
  return `<button class="sk-strip ${d.status === "active" ? "" : "calm"} ${d.id === SK.sel ? "sel" : ""} ${SK.multi.has(d.id) ? "msel" : ""} ${d.extra?.fav ? "fav" : ""}" data-id="${escapeHtml(d.id)}" title="${escapeHtml(d.filename || d.url)}">
    <span class="sk-star" title="${skL("Favori", "Favorite")}">★</span>
    <div class="sk-paper">
      <div class="sk-liquid" style="height:${h}%;background:linear-gradient(180deg,${c1}cc,${c2})">${wavy ? skWave(c1 + "88", 5).replace("sk-wave", "sk-wave back") + skWave(c1 + "cc", 7) : ""}${bubbles}</div>
      <div class="sk-band"></div>
      <div class="sk-strip-body"><span class="sk-kind">${kind}</span><span class="sk-name">${escapeHtml(d.filename || d.url)}</span><span class="sk-tags">${tags.join("")}</span></div>
      <div class="sk-foot"><span class="sk-pct">${d.status === "error" ? "!" : pct + "%"}</span><span class="sk-sub">${escapeHtml(sub)}</span></div>
    </div></button>`;
}

function skRender(onlyMove) {
  if (!SK.built) return;
  const its = skItems();
  if (!its.find((d) => d.id === SK.sel)) SK.sel = its[0]?.id ?? null;
  const per = skPerPage();
  const selIdx = its.findIndex((d) => d.id === SK.sel);
  if (!onlyMove && selIdx >= 0 && (selIdx < SK.page || selIdx >= SK.page + per)) SK.page = Math.max(0, Math.min(selIdx, its.length - per));
  SK.page = Math.max(0, Math.min(SK.page, Math.max(0, its.length - per)));
  const track = $("#skTrack");
  if (!its.length) track.innerHTML = `<div class="sk-empty">${skL("Sunak boş. Bir bağlantı yapıştır ya da dosyayı ruha bırak.", "The altar is empty. Paste a link or drop a file on the spirit.")}</div>`;
  else skPatchStrips(track, its);
  track.style.transform = `translateX(${-SK.page * SK_STRIP_W}px)`;
  $("#skPrev").classList.toggle("on", SK.page > 0);
  $("#skNext").classList.toggle("on", SK.page + per < its.length);
  const dotsBox = $("#skDots");
  if (its.length > per) {
    const maxDots = 9;
    const half = Math.floor(maxDots / 2);
    const start = Math.max(0, Math.min(SK.page - 1, its.length - maxDots));
    const end = Math.min(its.length, start + maxDots);
    const curPage = Math.floor(SK.page / Math.max(1, per)) + 1;
    const totPages = Math.max(1, Math.ceil(its.length / Math.max(1, per)));
    dotsBox.innerHTML = its.slice(start, end).map((d, j) => {
      const i = start + j;
      return `<i data-i="${i}" class="${d.id === SK.sel ? "sel" : i >= SK.page && i < SK.page + per ? "vis" : ""}"></i>`;
    }).join("") + `<span class="sk-dot-count">${curPage} / ${totPages}</span>`;
  } else {
    dotsBox.innerHTML = "";
  }
  skRenderBar(its.find((d) => d.id === SK.sel));
}
// seritleri yeniden kurmadan guncelle (dalga animasyonu kesilmesin)
function skPatchStrips(track, its) {
  const old = new Map([...track.querySelectorAll(".sk-strip")].map((el) => [el.dataset.id, el]));
  if (track.querySelector(".sk-empty")) track.innerHTML = "";
  const frag = [];
  for (const d of its) {
    const id = String(d.id);
    let el = old.get(id);
    const t = document.createElement("template"); t.innerHTML = skStripHtml(d).trim();
    const nu = t.content.firstChild;
    if (el && el.dataset.status === d.status) {
      // ayni durum: canli elemani YERINDE guncelle (yeniden kurulursa sivi gecisi kesilir, ziplar)
      const liq = el.querySelector(".sk-liquid"), nliq = nu.querySelector(".sk-liquid");
      if (liq && nliq && liq.style.height !== nliq.style.height) {
        if (!liq.querySelector(".sk-wave") && nliq.querySelector(".sk-wave")) liq.innerHTML = nliq.innerHTML;   // dalga yeni basladi
        liq.style.height = nliq.style.height;
      }
      for (const sel of [".sk-strip-body", ".sk-foot"]) {
        const a = el.querySelector(sel), b2 = nu.querySelector(sel);
        if (a && b2 && a.innerHTML !== b2.innerHTML) a.innerHTML = b2.innerHTML;
      }
      el.classList.toggle("sel", d.id === SK.sel);
      el.classList.toggle("msel", SK.multi.has(d.id));
      el.classList.toggle("fav", !!d.extra?.fav);
      el.classList.toggle("calm", d.status !== "active");
      el.title = nu.title;
    } else {
      if (el) nu.classList.add(d.status === "complete" ? "burst" : "slosh");
      nu.dataset.status = d.status;
      if (el) {   // durum degisti: sivi eski yuksekligi korusun, sonra yeni yukseklige aksin
        const h = nu.querySelector(".sk-liquid")?.style.height, oh = el.querySelector(".sk-liquid")?.style.height;
        if (oh && h) { nu.querySelector(".sk-liquid").style.height = oh; requestAnimationFrame(() => requestAnimationFrame(() => { const q = nu.querySelector(".sk-liquid"); if (q) q.style.height = h; })); }
      }
      el = nu;
    }
    frag.push(el);
    old.delete(id);
  }
  const cur = [...track.children];
  if (cur.length !== frag.length || frag.some((x, i) => x !== cur[i])) track.replaceChildren(...frag);   // sadece sira/uye degisince
}

function skRenderBar(d) {
  const bar = $("#skBar");
  if (bar.querySelector(".sk-rename")) return;   // yeniden adlandirma suruyor: kutu silinmesin
  if (!d) { bar.className = "sk-bar wait"; bar.innerHTML = `<span class="sk-bar-info">${skL("Seçili indirme yok", "Nothing selected")}</span>`; return; }
  bar.className = "sk-bar" + (d.status === "error" ? " err" : d.status === "active" || d.status === "complete" ? "" : " wait");
  const B = (act, icon, label, cls = "") => `<button class="sk-btn ${cls}" data-act="${act}">${skIcon[icon]}${label}</button>`;
  const btns = [];
  if (d.status === "confirm") { btns.push(B("confirm", "play", skL("Onayla", "Confirm"), "pri")); btns.push(B("reject", "x", skL("Reddet", "Reject"))); }
  if (["active", "waiting", "queued"].includes(d.status)) btns.push(B("pause", "pause", skL("Duraklat", "Pause")));
  if (["active", "waiting", "queued", "paused"].includes(d.status) && ["video", "music"].includes(d.category))
    btns.push(B("autoplay", "play", SK.autoPlay.has(d.id) ? skL("Bitince oynatılacak ✓", "Will play when done ✓") : skL("Bitince oynat", "Play when done"), SK.autoPlay.has(d.id) ? "ok" : ""));
  if (d.status === "paused") btns.push(B("resume", "play", skL("Sürdür", "Resume"), "pri"));
  if (d.status === "error") btns.push(B("resume", "retry", skL("Yeniden dene", "Retry"), "pri"));
  const media = d.status === "complete" && ["video", "music"].includes(d.category);
  if (media) btns.push(B("play", "play", skL("Oynat", "Play"), "pri"));
  if (d.status === "complete") btns.push(B("open_file", "file", media ? skL("Dışarıda aç", "Open externally") : skL("Aç", "Open"), media ? "" : "pri"));
  if (d.status === "complete" && ["video", "music"].includes(d.category)) {
    btns.push(B("mtools", "sub", skL("AI altyazı", "AI subtitle"), "ai"));
    btns.push(B("mtools", "voc", skL("Vokal ayır", "Split vocals"), "ai"));
  }
  if (d.path || d.status === "complete") btns.push(B("open_folder", "folder", skL("Klasör", "Folder")));
  btns.push(B("remove", "x", skL("Kaldır", "Remove"), "danger"));
  let info = "";
  if (d.status === "error") info = d.error || skL("hata", "error");
  else if (d.size) info = `${fmtBytes(d.downloaded)} / ${fmtBytes(d.size)}${d.connections ? " · " + d.connections + skL(" bağlantı", " conn") : ""}`;
  else if (d.downloaded) info = fmtBytes(d.downloaded);
  bar.innerHTML = `<span class="sk-bar-name" title="${escapeHtml(d.filename || d.url)}">${escapeHtml(d.filename || d.url)}</span><span class="sk-bar-info">${escapeHtml(info)}</span>${btns.join("")}`;
  skRenderDetail(d);
}

// ---------- ayrinti paneli (yuksek pencerede alttaki bosluk) ----------
const SK_HIST = new Map();   // id -> son hizlar (her tick)
function skTrackSpeeds() {
  for (const d of state.items || []) {
    if (d.status !== "active") continue;
    const h = SK_HIST.get(d.id) || [];
    h.push(d.speed || 0); if (h.length > 120) h.shift();
    SK_HIST.set(d.id, h);
  }
}
function skHost(u) { try { return new URL(u).host.replace(/^www\./, ""); } catch { return ""; } }
function skRenderDetail(d) {
  const box = $("#skDetail"); if (!box) return;
  if (!d) { box.innerHTML = ""; return; }
  const x = d.extra || {};
  const when = (t) => { if (!t) return ""; const dt = new Date(typeof t === "number" ? t * 1000 : t); return isNaN(dt) ? "" : dt.toLocaleString(skTr() ? "tr-TR" : "en-GB", { dateStyle: "medium", timeStyle: "short" }); };
  const rows = [
    [skL("Kaynak", "Source"), skHost(d.page_url || d.url) || "—", d.page_url || d.url],
    [skL("Klasör", "Folder"), d.directory || "—", d.directory],
    [skL("Boyut", "Size"), d.size ? fmtBytes(d.size) : d.downloaded ? fmtBytes(d.downloaded) : "—"],
    [skL("Eklendi", "Added"), when(d.created_at) || "—"],
    [skL("Bitti", "Finished"), when(d.finished_at) || (d.status === "complete" ? "—" : skL("sürüyor", "in progress"))],
    [skL("Bağlantı", "Connections"), d.connections ? String(d.connections) : "—"],
  ];
  if (x.sha256) rows.push(["SHA-256", x.sha256.slice(0, 16) + "…", x.sha256]);
  if (x.scan) rows.push([skL("Tarama", "Scan"), String(x.scan)]);
  const hist = SK_HIST.get(d.id) || [];
  let chunkHtml = "";
  if (["active", "waiting", "paused"].includes(d.status) && d.bitfield) {
    const bits = [];
    for (let i = 0; i < d.bitfield.length; i++) {
      const nib = parseInt(d.bitfield[i], 16) || 0;
      bits.push((nib >> 3) & 1, (nib >> 2) & 1, (nib >> 1) & 1, nib & 1);
    }
    const cols = 32;
    const cells = Array.from({ length: cols }, (_, ci) => {
      const s0 = Math.floor((ci * bits.length) / cols);
      const s1 = Math.max(s0 + 1, Math.floor(((ci + 1) * bits.length) / cols));
      let hit = 0;
      for (let bi = s0; bi < s1 && bi < bits.length; bi++) hit += bits[bi];
      const on = hit > 0 && hit >= (s1 - s0) / 2;
      return `<i class="sk-chunk-cell${on ? " on" : ""}"></i>`;
    }).join("");
    chunkHtml = `<div class="sk-chunk-bar" title="${skL("Parça Doluluk Haritası (32 Segment)", "Piece Completion Heatmap (32 Segments)")}">${cells}</div>`;
  }
  box.innerHTML = `<div class="sk-dt-grid">${rows.map(([k, v, full]) => `<div><span>${escapeHtml(k)}</span><b title="${escapeHtml(full || v)}">${escapeHtml(v)}</b></div>`).join("")}</div>
    <div class="sk-dt-graph"><span>${skL("Bu indirmenin hızı", "This download's speed")}</span>${hist.length > 1 ? skSparkSvg(hist) : `<em>${d.status === "complete" ? skL("İndirme bitti", "Finished") : skL("Hız verisi bekleniyor", "Waiting for speed data")}</em>`}${chunkHtml}</div>`;
}
function skSparkSvg(h) {
  const max = Math.max(...h, 1), w = 400, ht = 70;
  const pts = h.map((v, i) => `${(i / (h.length - 1)) * w},${ht - (v / max) * (ht - 6) - 3}`).join(" ");
  return `<svg viewBox="0 0 ${w} ${ht}" preserveAspectRatio="none"><defs><linearGradient id="skDtG" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#2EE6A6" stop-opacity=".35"/><stop offset="1" stop-color="#2EE6A6" stop-opacity="0"/></linearGradient></defs>
    <polygon points="0,${ht} ${pts} ${w},${ht}" fill="url(#skDtG)"/><polyline points="${pts}" fill="none" stroke="#2EE6A6" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><small>${skL("en yüksek", "peak")} ${fmtBytes(max)}/s</small>`;
}

async function skBarAction(e) {
  const b = e.target.closest("[data-act]"); if (!b || !SK.sel) return;
  const id = SK.sel, act = b.dataset.act;
  try {
    if (act === "mtools") return openMediaTools(id);
    if (act === "play") return playerOpen(id);
    if (act === "autoplay") { SK.autoPlay.has(id) ? SK.autoPlay.delete(id) : SK.autoPlay.add(id); skAutoSave(); return skRender(); }
    if (act === "remove") await api.remove(id, false);
    else if (act === "confirm") await api.confirm(id, true);
    else if (act === "reject") await api.confirm(id, false);
    else await api[act](id);
  } catch (err) { console.error(err); toast(String(err), true); }
  tick();
}

function skAutoSave() { try { localStorage.setItem("kami.autoplay", JSON.stringify([...SK.autoPlay])); } catch { /* yok */ } }

function skDock(k) {
  if (k === "settings") { $("#settingsBtn")?.click(); return; }
  if (k === "notifs") { skOpenNotifs(); return; }
  if (k === "pano") return;   // kami-pano.js kendi cekmecesini acar
  if (k === "library") { playerLibrary(); return; }
  if (k === "fx") {
    const order = ["obsidian", "spirit_fire", "particles", "off"];
    const cur = document.body.dataset.bgMode || "obsidian";
    const next = order[(order.indexOf(cur) + 1) % order.length];
    window.KamiFX?.setMode?.(next);
    window.fxApplyMode?.(next);
    api?.set_setting?.("sunak_bg_mode", next);
    const names = { obsidian: skL("Arka plan: Akan Obsidian", "BG: Flowing Obsidian"), spirit_fire: skL("Arka plan: Ruh Ateşi", "BG: Spirit Fire"), particles: skL("Arka plan: Klasik Parçacık", "BG: Classic Particles"), off: skL("Arka plan: Kapalı", "BG: Off") };
    toast(names[next]);
    return;
  }
  if (k === "ai") {
    const d = state.items.find((x) => x.id === SK.sel) || null;
    if (typeof window.openKamiAiLyricsStudio === "function") {
      window.openKamiAiLyricsStudio(d);
    } else if (d) {
      openMediaTools(d.id);
    }
    return;
  }
  const go = () => {
    document.body.classList.add("sk-drawer");
    document.body.classList.toggle("sk-list", k === "list");
    $$("#skDock button").forEach((b) => b.classList.toggle("on", b.dataset.sk === k));
    const nav = k === "list" ? $('.nav-item[data-filter="all"]') : $(`.nav-item[data-view="${k}"]`);
    nav?.click();
  };
  window.KamiFX?.vt ? window.KamiFX.vt(go) : go();
}
function skCloseDrawer() {
  const go = () => {
    document.body.classList.remove("sk-drawer", "sk-list");
    $$("#skDock button").forEach((b) => b.classList.remove("on"));
    if (typeof showRd === "function") showRd(false);
    showView(null);
  };
  window.KamiFX?.vt ? window.KamiFX.vt(go) : go();
}

function skMood(s, active) {
  if (!s.engine_ok) return skL("Motor uyuyor. aria2 cevap vermiyor.", "The engine is asleep. aria2 is not answering.");
  if (active) return skL("Ruh besleniyor…", "The spirit is feeding…");
  if (Date.now() < SK.happyUntil) return skL("Tok. Bir tane daha?", "Fed. One more?");
  return skL("Bekliyor. Bir bağlantı ver.", "Waiting. Give it a link.");
}

function skState(s) {
  if (!SK.built) return;
  const its = s.items || [];
  const active = its.filter((d) => d.status === "active");
  for (const d of its) {
    const p = SK.prevStatus.get(d.id);
    if (p && p !== "complete" && d.status === "complete") {
      SK.happyUntil = Date.now() + 4000;
      window.KamiFX?.pulse?.();
      if (SK.autoPlay.has(d.id)) { SK.autoPlay.delete(d.id); skAutoSave(); playerOpen(d.id); }   // bitince oynat
    }
    SK.prevStatus.set(d.id, d.status);
  }
  const spd = s.total_speed || 0;
  SK.peak = Math.max(SK.peak * 0.995, spd, 1024 * 1024);
  SK.speedFrac = active.length ? Math.min(1, spd / SK.peak) : 0;
  const [num, unit] = splitBytes(spd);
  $("#skNum").textContent = num; $("#skUnit").textContent = unit + "/s";
  const mbit = (spd * 8) / 1e6;
  $("#skSub").textContent = active.length ? `${mbit >= 100 ? Math.round(mbit) : mbit.toFixed(1)} Mbit/s` : skL("boşta", "idle");
  const left = active.reduce((a, d) => a + Math.max(0, (d.size || 0) - d.downloaded), 0);
  $("#skCnt").textContent = `${skL(active.length + " aktif", active.length + " active")} · ${its.filter((d) => ["queued", "waiting", "confirm"].includes(d.status)).length} ${skL("sırada", "queued")}${left && spd ? " · " + skL("kalan ", "eta ") + fmtEta(left / spd) : ""}`;
  $("#skMood").textContent = skMood(s, active.length);
  const eng = $("#skEngine"); eng.textContent = s.engine_ok ? "aria2" : skL("kapalı", "down"); eng.classList.toggle("bad", !s.engine_ok);
  $("#skBridge").textContent = s.bridge_port || "—";
  const fill = $(".sk-ring-fill");
  fill.setAttribute("stroke-dashoffset", String(SK_RING_C * (1 - SK.speedFrac)));
  $("#skAltar").classList.toggle("full", SK.speedFrac > 0.92);
  const sel = its.find((d) => d.id === SK.sel);
  const moodNow = Date.now() < SK.happyUntil ? "happy" : $("#skAltar").classList.contains("drop") ? "alert" : "idle";
  const errNow = !s.engine_ok || (sel && sel.status === "error");
  SK.eye?.set({
    isDownloading: active.length > 0,
    downloadSpeed: Math.min(1, spd / (125 * 1024 * 1024)),
    isError: errNow,
    mood: moodNow,
  });
  window.KamiSunakGPU?.setState?.({
    speedFrac: SK.speedFrac,
    isDownloading: active.length > 0,
    isError: errNow,
    mood: moodNow,
    drop: $("#skAltar").classList.contains("drop"),
  });
  window.KamiFX?.setSpeed?.(SK.speedFrac);
  // Windows gorev cubugu ilerleme cubugu (ITaskbarList3)
  let tbState = "none", tbPct = 0;
  if (active.length) {
    const totSz = active.reduce((a, d) => a + (d.size || 0), 0);
    const totDl = active.reduce((a, d) => a + (d.downloaded || 0), 0);
    tbState = "normal";
    tbPct = totSz > 0 ? Math.min(100, Math.round((totDl / totSz) * 100)) : 50;
  } else if (its.some((d) => d.status === "error")) {
    tbState = "error"; tbPct = 100;
  } else if (its.some((d) => d.status === "paused")) {
    tbState = "paused"; tbPct = 50;
  }
  if (SK._tbLast !== `${tbState}:${tbPct}`) {
    SK._tbLast = `${tbState}:${tbPct}`;
    api?.taskbar_progress?.(tbPct, tbState)?.catch?.(() => {});
  }
  skTrackSpeeds();
  const fc = $("#followCount")?.textContent; const fn = $("#skFollowN");
  if (fn) { fn.hidden = !fc || fc === "0"; fn.textContent = fc || ""; }
  skRender();
  skSpark();
}

function skSpark() {
  const c = $("#skSpark"); const ctx = c.getContext("2d"); const h = state.history.slice(-80);
  const w = c.width, ht = c.height, max = Math.max(...h, 1);
  ctx.clearRect(0, 0, w, ht);
  const g = ctx.createLinearGradient(0, 0, 0, ht); g.addColorStop(0, "rgba(139,92,246,.45)"); g.addColorStop(1, "rgba(139,92,246,0)");
  ctx.beginPath(); ctx.moveTo(0, ht);
  h.forEach((v, i) => ctx.lineTo((i / (h.length - 1)) * w, ht - 6 - (v / max) * (ht - 14)));
  ctx.lineTo(w, ht); ctx.closePath(); ctx.fillStyle = g; ctx.fill();
  ctx.beginPath();
  h.forEach((v, i) => { const x = (i / (h.length - 1)) * w, y = ht - 6 - (v / max) * (ht - 14); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = "#2EE6A6"; ctx.lineWidth = 3; ctx.stroke();
}

// hiz halkasi yorungesi: hiz arttikca hizlanir
let skLast = 0;
function skFrame(t) {
  const dt = Math.min(0.1, (t - skLast) / 1000 || 0); skLast = t;
  if (!window.KamiSunakGPU?.altarReady) {
    SK.orbit = (SK.orbit + dt * (8 + SK.speedFrac * 260)) % 360;
    const o = $("#skOrbit"); if (o) o.setAttribute("transform", `rotate(${SK.orbit} 150 150)`);
  }
  requestAnimationFrame(skFrame);
}

// ---------- arka plan: suzulen muskalar, yukselen kivilcimlar, yerde sis, ruh isiklari (hepsi dusuk opaklik) ----------
const FX = { on: (() => { try { return localStorage.getItem("kami.fx") !== "0"; } catch { return true; } })(), parts: [], last: 0 };
function fxSprite(w, h, draw) { const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d"), w, h); return c; }
function fxInit() {
  const fog = document.createElement("div"); fog.id = "skFog"; document.body.prepend(fog);
  if (window.KamiSunakGPU?.available?.()) {
    window.KamiSunakGPU.initBg().then((ok) => {
      if (!ok) fxInit2D();
    });
    document.body.classList.toggle("fx-off", !FX.on);
    return;
  }
  fxInit2D();
}
function fxInit2D() {
  const c = document.createElement("canvas");
  c.id = "skFx"; document.body.prepend(c);
  const ctx = c.getContext("2d");
  let W = 0, H = 0, dpr = 1;
  const resize = () => { dpr = Math.min(2, devicePixelRatio || 1); W = innerWidth; H = innerHeight; c.width = W * dpr; c.height = H * dpr; ctx.setTransform(dpr, 0, 0, dpr, 0, 0); };
  resize(); addEventListener("resize", resize);
  // muska sprite: lavanta kagit, ust mor serit, yirtik alt kenar, zumrut muhur, firca yazilari
  const paper = (blur) => fxSprite(70, 150, (g, w, h) => {
    if (blur) g.filter = `blur(${blur}px)`;
    g.translate(w / 2, h / 2);
    const grd = g.createLinearGradient(0, -60, 0, 60); grd.addColorStop(0, "#EDE6FF"); grd.addColorStop(1, "#B9A6F2");
    g.fillStyle = grd; g.beginPath(); g.moveTo(-20, -62); g.lineTo(20, -62); g.lineTo(20, 52);
    for (let x = 20; x >= -20; x -= 5) g.lineTo(x, 52 + ((x / 5) % 2 ? 7 : 1));
    g.closePath(); g.fill();
    g.fillStyle = "#6D28D9"; g.fillRect(-20, -62, 40, 9);
    g.strokeStyle = "#3B1580"; g.lineWidth = 2.6; g.lineCap = "round";
    g.beginPath(); g.moveTo(0, -44); g.lineTo(0, 30); g.moveTo(-10, -30); g.quadraticCurveTo(0, -24, 10, -32); g.moveTo(-11, -10); g.lineTo(9, -4);
    g.moveTo(-8, 10); g.quadraticCurveTo(2, 18, 10, 8); g.stroke();
    g.fillStyle = "#0FA37A"; g.beginPath(); g.arc(0, 38, 6.5, 0, 6.28); g.fill();
  });
  const glow = (col) => fxSprite(64, 64, (g) => { const r = g.createRadialGradient(32, 32, 0, 32, 32, 32); r.addColorStop(0, col.replace("A", "1")); r.addColorStop(0.25, col.replace("A", ".55")); r.addColorStop(1, col.replace("A", "0")); g.fillStyle = r; g.fillRect(0, 0, 64, 64); });
  const SPR = { near: paper(0), mid: paper(1.2), far: paper(2.4), vio: glow("rgba(167,139,250,A)"), em: glow("rgba(46,230,166,A)"), wisp: glow("rgba(196,181,253,A)") };
  const rnd = (a, b) => a + Math.random() * (b - a);
  const LAYERS = [["far", 0.35, 0.05, 5], ["mid", 0.55, 0.075, 4], ["near", 0.8, 0.1, 3]];   // derinlik: boyut, opaklik, adet
  const tal = (layer, y) => { const [n, sc, a] = layer; return { kind: "t", spr: n, sc: sc * rnd(0.85, 1.15), a, x: rnd(0, W), y: y ?? rnd(0, H), vy: -rnd(6, 14) * sc, sway: rnd(10, 26) * sc, ph: rnd(0, 6.28), rot: rnd(-0.4, 0.4), spin: rnd(0.4, 1.1) }; };
  for (const L of LAYERS) for (let i = 0; i < L[3]; i++) FX.parts.push(tal(L));
  const loop = (now) => {
    requestAnimationFrame(loop);
    if (!FX.on || document.hidden) { if (FX.drawn) { ctx.clearRect(0, 0, W, H); FX.drawn = false; } FX.last = now; return; }
    if (now - FX.last < 30) return;   // ~33 fps
    const dt = Math.min(0.1, (now - FX.last) / 1000); FX.last = now;
    const t = now / 1000;
    const rate = 1.2 + (SK.speedFrac || 0) * 6;   // kivilcim: indirme hizlandikca artar
    if (Math.random() < rate * dt && FX.parts.length < 48) FX.parts.push({ kind: "e", x: rnd(0, W), y: H + 8, vx: rnd(-6, 6), vy: -rnd(22, 48), life: rnd(5, 10), t: 0, s: rnd(6, 13), g: Math.random() < 0.3, fl: rnd(0, 6.28) });
    if (Math.random() < 0.07 * dt && FX.parts.filter((p) => p.kind === "w").length < 3)
      FX.parts.push({ kind: "w", x: rnd(W * 0.1, W * 0.9), y: rnd(H * 0.25, H * 0.75), vx: rnd(-18, 18), vy: rnd(-8, 8), life: rnd(7, 12), t: 0, s: rnd(26, 44), trail: [] });
    ctx.clearRect(0, 0, W, H); FX.drawn = true;
    FX.parts = FX.parts.filter((p) => {
      if (p.kind === "t") {   // muska: yukari suzulur, saga sola salinir, kendi ekseninde yavasca doner (kagit cevrilme hissi)
        p.y += p.vy * dt;
        const x = p.x + Math.sin(t * 0.5 + p.ph) * p.sway;
        if (p.y < -90) Object.assign(p, tal(LAYERS.find((L) => L[0] === p.spr), H + 90));
        ctx.save(); ctx.translate(x, p.y); ctx.rotate(p.rot + Math.sin(t * 0.35 + p.ph) * 0.35);
        const fl = Math.cos(t * p.spin * 0.45 + p.ph);
        ctx.scale(p.sc * (Math.sign(fl) || 1) * (0.3 + 0.7 * Math.abs(fl)), p.sc);   // yatay olcek -> 3B donus (cubuk gibi incelmez)
        ctx.globalAlpha = p.a; ctx.drawImage(SPR[p.spr], -35, -75); ctx.restore();
        return true;
      }
      p.t += dt; p.x += p.vx * dt; p.y += p.vy * dt;
      const k = p.t / p.life, fade = Math.sin(Math.min(1, k) * Math.PI);
      ctx.globalCompositeOperation = "lighter";
      if (p.kind === "e") {
        const fl = 0.75 + 0.25 * Math.sin(t * 9 + p.fl);
        ctx.globalAlpha = 0.28 * fade * fl;
        const xx = p.x + Math.sin(p.t * 1.7 + p.fl) * 8;
        ctx.drawImage(p.g ? SPR.em : SPR.vio, xx - p.s, p.y - p.s, p.s * 2, p.s * 2);
      } else {
        p.trail.push([p.x, p.y]); if (p.trail.length > 14) p.trail.shift();
        p.trail.forEach(([tx, ty], i) => { ctx.globalAlpha = 0.05 * fade * (i / p.trail.length); const ss = p.s * (0.4 + 0.6 * i / p.trail.length); ctx.drawImage(SPR.wisp, tx - ss, ty - ss, ss * 2, ss * 2); });
        ctx.globalAlpha = 0.16 * fade; ctx.drawImage(SPR.wisp, p.x - p.s, p.y - p.s, p.s * 2, p.s * 2);
        p.vx += Math.sin(t + p.s) * 4 * dt; p.vy += Math.cos(t * 0.7 + p.s) * 4 * dt;
      }
      ctx.globalCompositeOperation = "source-over"; ctx.globalAlpha = 1;
      return p.t < p.life;
    });
  };
  requestAnimationFrame(loop);
  document.body.classList.toggle("fx-off", !FX.on);
}
function fxToggle(on) { FX.on = on; window.KamiSunakGPU?.setFx?.(on); document.body.classList.toggle("fx-off", !on); try { localStorage.setItem("kami.fx", on ? "1" : "0"); } catch { /* yok */ } }
window.fxApplyMode = function (mode) {
  const m = (mode === "particles" || mode === "off") ? mode : "obsidian";
  if (m === "obsidian") {
    // Obsidian WebGL arka plan acik; klasik parcacik katmani gizlenir ki ust uste binmesin
    window.KamiSunakGPU?.setFx?.(false);
    document.body.classList.add("fx-off");
    FX.on = false;
  } else if (m === "particles") {
    fxToggle(true);
  } else {
    fxToggle(false);
  }
};

skBuild();
fxInit();
STATE_HOOKS.push(skState);

// Istege bagli: Kamify calarken kapak rengini Sunak arka planina hafifce yansit
(() => {
  let lastCov = "";
  const clearTint = () => {
    window.KamiFX?.setTint?.(0, 0, 0);
    document.body.style.backgroundImage = "";
  };
  setInterval(async () => {
    if (document.hidden || !state?.settings?.sunak_kamify_sync) {
      if (lastCov) { lastCov = ""; clearTint(); }
      return;
    }
    try {
      const now = await api?.music_spotify_now?.();
      const cov = now?.playing ? (now.cover || "") : "";
      if (!cov) { if (lastCov) { lastCov = ""; clearTint(); } return; }
      if (cov === lastCov) return;
      lastCov = cov;
      const im = new Image(); im.crossOrigin = "anonymous";
      im.onload = () => {
        try {
          const cv = document.createElement("canvas"); cv.width = 6; cv.height = 6;
          const g = cv.getContext("2d"); g.drawImage(im, 0, 0, 6, 6);
          const d = g.getImageData(0, 0, 6, 6).data;
          let r = 0, gr = 0, b = 0, n = 0;
          for (let i = 0; i < d.length; i += 4) { if (d[i] + d[i+1] + d[i+2] > 30) { r += d[i]; gr += d[i+1]; b += d[i+2]; n++; } }
          if (n) {
            const rr = Math.round(r / n), gg = Math.round(gr / n), bb = Math.round(b / n);
            window.KamiFX?.setTint?.(rr, gg, bb);
            document.body.style.backgroundImage = `radial-gradient(ellipse 60% 55% at 24% 28%, rgba(${rr},${gg},${bb},.22), transparent 70%)`;
          }
        } catch {}
      };
      im.src = cov;
    } catch {}
  }, 5000);
})();

// v1.32.1 Sag ray sadelestirme: 12 dugme -> ana isler + "Araclar" izgarasi + Ayarlar.
// Orijinal dugmeler DOM'da (gizli) kalir; dosemeler onlara tiklatir -> tum mevcut isleyiciler aynen calisir.
(() => {
  const CORE = ["library", "list", "notifs", "history", "pano"];
  const isTool = (b) => b.id !== "skToolsBtn" && !CORE.includes(b.dataset.sk) && b.dataset.sk !== "settings";
  let pop = null;
  const SHORT = { fx: ["Efektler", "Effects"], ai: ["AI altyazı · vokal", "AI subs · vocals"], kfDockBtn: ["Akış & Copilot", "Flow & Copilot"] };
  const label = (b) => { const s = SHORT[b.dataset.sk] || SHORT[b.id]; return s ? skL(s[0], s[1]) : (b.dataset.tip || b.title || b.getAttribute("aria-label") || ""); };
  let arranging = false;
  function arrange() {
    if (arranging) return;
    const dock = $("#skDock"); if (!dock) return;
    arranging = true;
    try {
      let tb = $("#skToolsBtn");
      if (!tb) {
        tb = document.createElement("button");
        tb.id = "skToolsBtn"; tb.dataset.sk = "tools"; tb.title = skL("Araçlar", "Tools");
        tb.innerHTML = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/></svg><b id="skToolsN" hidden></b>';
        dock.appendChild(tb);
      }
      const btns = [...dock.querySelectorAll(":scope > button")];
      const lib = btns.filter((b) => b.dataset.sk === "library");
      lib.slice(1).forEach((b) => b.remove());
      const order = [...CORE.map((k) => btns.find((b) => b.dataset.sk === k)), tb, btns.find((b) => b.dataset.sk === "settings")].filter(Boolean);
      const curTail = [...dock.children].slice(-order.length);
      if (curTail.length !== order.length || order.some((b, i) => curTail[i] !== b)) {
        order.forEach((b) => dock.appendChild(b));
      }
      btns.forEach((b) => {
        const want = isTool(b);
        if (b.classList.contains("sk-intool") !== want) b.classList.toggle("sk-intool", want);
      });
      const fn = $("#skFollowN"), tn = $("#skToolsN");
      if (tn) {
        const hid = !fn || fn.hidden, txt = fn?.textContent || "";
        if (tn.hidden !== hid) tn.hidden = hid;
        if (tn.textContent !== txt) tn.textContent = txt;
      }
    } finally {
      arranging = false;
    }
  }
  function openTools() {
    const dock = $("#skDock"), tb = $("#skToolsBtn");
    if (pop?.classList.contains("on")) { pop.classList.remove("on"); tb.classList.remove("on"); return; }
    if (!pop) { pop = document.createElement("div"); pop.className = "sk-tools"; document.body.appendChild(pop); }
    const tools = [...dock.querySelectorAll(":scope > button.sk-intool")];
    pop.innerHTML = `<b class="sk-tools-h">${skL("Araçlar", "Tools")}</b><div class="sk-tools-g">${tools.map((b, i) => `<button type="button" data-i="${i}" class="${b.classList.contains("ai") ? "ai" : ""}">${b.querySelector("svg")?.outerHTML || ""}<span>${escapeHtml(label(b).replace(/\s*\(.*\)\s*$/, ""))}</span>${b.querySelector("b:not([hidden])") ? `<i>${escapeHtml(b.querySelector("b").textContent)}</i>` : ""}</button>`).join("")}</div>`;
    pop.querySelectorAll("[data-i]").forEach((x) => x.onclick = (e) => { e.stopPropagation(); pop.classList.remove("on"); tb.classList.remove("on"); tools[+x.dataset.i].click(); });
    const r = tb.getBoundingClientRect();
    pop.style.right = (innerWidth - r.left + 10) + "px";
    pop.style.top = Math.max(12, Math.min(innerHeight - 330, r.top - 120)) + "px";
    pop.classList.add("on"); tb.classList.add("on");
  }
  document.addEventListener("click", (e) => {
    if (e.target.closest?.("#skToolsBtn")) { e.stopImmediatePropagation(); openTools(); return; }
    if (pop?.classList.contains("on") && !e.target.closest?.(".sk-tools")) { pop.classList.remove("on"); $("#skToolsBtn")?.classList.remove("on"); }
  }, true);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && pop?.classList.contains("on")) { pop.classList.remove("on"); $("#skToolsBtn")?.classList.remove("on"); } });
  const boot = () => {
    const dock = $("#skDock"); if (!dock) return setTimeout(boot, 300);
    arrange();
    let t = 0;
    new MutationObserver(() => { clearTimeout(t); t = setTimeout(arrange, 50); }).observe(dock, { childList: true, subtree: true, attributes: true, attributeFilter: ["hidden"] });
  };
  boot();
})();

// v1.32.1 ust alan gosterge paneli (disk / bugun / hafta / RD) — 20 sn'de bir, ucuz
(() => {
  const g = (ic, v, t, warn) => `<div class="sk-g${warn ? " warn" : ""}"><i>${ic}</i><b>${v}</b><span>${t}</span></div>`;
  async function upd() {
    const box = $("#skGauges"); if (!box || document.hidden) return;
    let d; try { d = await api.dash_stats(); } catch { return; }
    const free = d.disk_free ?? null, pct = d.disk_total ? free / d.disk_total : 1;
    box.innerHTML = [
      free != null ? g(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><circle cx="16" cy="12" r="2"/><path d="M7 9h4"/></svg>`, fmtBytes(free), skL("boş disk", "free disk"), pct < 0.08) : "",
      g(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 4v11m-5-5 5 5 5-5M5 20h14"/></svg>`, d.today ? fmtBytes(d.today) : "0", skL(`bugün · ${d.today_n || 0} dosya`, `today · ${d.today_n || 0} files`)),
      g(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 18l5-6 4 3 7-8M15 7h5v5"/></svg>`, d.week ? fmtBytes(d.week) : "0", skL("son 7 gün", "last 7 days")),
      d.rd_days != null ? g(`<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M13 3 5 14h6l-1 7 8-11h-6z"/></svg>`, `${d.rd_days} ${skL("gün", "d")}`, "Real-Debrid", d.rd_days < 5) : "",
    ].join("");
  }
  setTimeout(upd, 1200); setInterval(upd, 20000);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) upd(); });
})();

// v1.38.0 Dalga 1: Hiz profili kapsulu, Bildirim Merkezi cekmecesi ve arka planda animasyon duraklatma
(() => {
  const PROF_ORDER = ["full", "stream", "game", "room", "night"];
  const PROF_NAMES = {
    full: skL("Tam Hız", "Full Speed"),
    stream: skL("Yayın", "Stream"),
    game: skL("Oyun", "Game"),
    room: skL("Oda", "Room"),
    night: skL("Gece", "Night"),
  };
  let curProf = "full";
  function applyProfUi(prof, autoReason) {
    curProf = prof || "full";
    const btn = $("#skProfCap"), lbl = $("#skProfLbl");
    if (!btn || !lbl) return;
    lbl.textContent = (PROF_NAMES[curProf] || curProf) + (autoReason ? " · Oto" : "");
    btn.classList.toggle("is-auto", !!autoReason);
    btn.classList.toggle("is-throttle", curProf !== "full" && curProf !== "night");
  }
  document.addEventListener("click", async (e) => {
    const cap = e.target.closest?.("#skProfCap");
    if (!cap) return;
    const next = PROF_ORDER[(PROF_ORDER.indexOf(curProf) + 1) % PROF_ORDER.length];
    try {
      const r = await api?.speed_profile_set?.(next, false);
      if (r?.current) applyProfUi(r.current, r.auto_reason);
      if (typeof toast === "function") toast(`${skL("Hız profili", "Speed profile")}: ${PROF_NAMES[next] || next}`);
    } catch {}
  });
  let notifDlg = null;
  window.skOpenNotifs = async function skOpenNotifs() {
    if (!notifDlg) {
      notifDlg = document.createElement("dialog");
      notifDlg.id = "skNotifDlg";
      notifDlg.style.cssText = "background:#110E17;color:#EDE9F6;border:1px solid rgba(157,107,255,.35);border-radius:12px;width:min(520px,92vw);padding:16px;";
      document.body.appendChild(notifDlg);
      notifDlg.addEventListener("click", (e) => { if (e.target === notifDlg) notifDlg.close(); });
    }
    const r = await api?.notifications_list?.(60) || { items: [] };
    const its = r.items || [];
    const fmtT = (ts) => {
      try { return new Date(ts * 1000).toLocaleTimeString(skTr() ? "tr-TR" : "en-GB", { hour: "2-digit", minute: "2-digit" }); } catch { return ""; }
    };
    notifDlg.innerHTML = `<div class="sk-notif-head"><b>${skL("Bildirim Merkezi", "Notification Center")}</b><span class="spacer"></span><button type="button" class="btn ghost" id="skNMark">${skL("Okundu İşaretle", "Mark Read")}</button><button type="button" class="btn ghost" id="skNClr">${skL("Temizle", "Clear")}</button><button type="button" class="btn ghost" id="skNCls">✕</button></div>
      <div class="sk-notif-list">${its.length ? its.map((n) => `<div class="sk-notif-row${n.read ? "" : " unread"}${n.kind === "error" ? " err" : ""}"><div class="sk-notif-body"><div class="sk-notif-title">${escapeHtml(n.title || "")}</div><div class="sk-notif-msg">${escapeHtml(n.message || "")}</div></div><span class="sk-notif-time">${fmtT(n.ts)}</span></div>`).join("") : `<p class="hint" style="margin:12px 0">${skL("Henüz bildirim yok.", "No notifications yet.")}</p>`}</div>`;
    notifDlg.querySelector("#skNCls").onclick = () => notifDlg.close();
    notifDlg.querySelector("#skNMark").onclick = async () => { await api?.notifications_mark_read?.(); const b = $("#skNotifN"); if (b) b.hidden = true; notifDlg.close(); };
    notifDlg.querySelector("#skNClr").onclick = async () => { await api?.notifications_clear?.(); const b = $("#skNotifN"); if (b) b.hidden = true; notifDlg.close(); };
    if (!notifDlg.open) notifDlg.showModal();
    await api?.notifications_mark_read?.();
    const b = $("#skNotifN");
    if (b) b.hidden = true;
  };
  if (typeof STATE_HOOKS !== "undefined" && Array.isArray(STATE_HOOKS)) {
    STATE_HOOKS.push((s) => {
      applyProfUi(s.speed_profile, s.speed_profile_auto);
      const b = $("#skNotifN");
      if (b) {
        const u = Number(s.notif_unread || 0);
        b.hidden = u <= 0;
        if (u > 0) b.textContent = u > 9 ? "9+" : String(u);
      }
    });
  }
  const syncVis = () => document.body.classList.toggle("kami-hidden", !!document.hidden);
  document.addEventListener("visibilitychange", syncVis);
  syncVis();
})();
