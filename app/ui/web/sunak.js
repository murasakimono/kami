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
  gear: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="3"/><path d="M12 2v3M12 19v3M2 12h3M19 12h3M4.9 4.9l2.1 2.1M17 17l2.1 2.1M4.9 19.1L7 17M17 7l2.1-2.1"/></svg>',
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
      <div class="sk-status"><span>${skL("motor", "engine")} <b id="skEngine">…</b></span><span>${skL("köprü", "bridge")} <b id="skBridge">…</b></span></div></div>
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
  // eski ekleme formu komut satirina tasinir (dinleyicileri onunla gelir)
  const form = $("#addForm");
  if (form) {
    form.classList.add("add"); $("#skCmd").appendChild(form);
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
    if (e.target.matches("input, textarea, select") || document.querySelector("dialog[open]")) return;
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
  document.addEventListener("mousemove", (e) => SK.eye?.lookAt(e.clientX, e.clientY));
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
  return state.items.filter((d) => d.status !== "removed" && !SK.hidden.has(d.id))
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
  $("#skDots").innerHTML = its.length > per ? its.map((d, i) => `<i data-i="${i}" class="${d.id === SK.sel ? "sel" : i >= SK.page && i < SK.page + per ? "vis" : ""}"></i>`).join("") : "";
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
  box.innerHTML = `<div class="sk-dt-grid">${rows.map(([k, v, full]) => `<div><span>${escapeHtml(k)}</span><b title="${escapeHtml(full || v)}">${escapeHtml(v)}</b></div>`).join("")}</div>
    <div class="sk-dt-graph"><span>${skL("Bu indirmenin hızı", "This download's speed")}</span>${hist.length > 1 ? skSparkSvg(hist) : `<em>${d.status === "complete" ? skL("İndirme bitti", "Finished") : skL("Hız verisi bekleniyor", "Waiting for speed data")}</em>`}</div>`;
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
  if (k === "library") { playerLibrary(); return; }
  if (k === "fx") { fxToggle(!FX.on); toast(FX.on ? skL("Arka plan efektleri açık", "Background effects on") : skL("Arka plan efektleri kapalı", "Background effects off")); return; }
  if (k === "ai") { const d = state.items.find((x) => x.id === SK.sel); if (d) openMediaTools(d.id); else toast(skL("Önce bir video ya da şarkı seç", "Select a video or song first")); return; }
  document.body.classList.add("sk-drawer");
  document.body.classList.toggle("sk-list", k === "list");
  $$("#skDock button").forEach((b) => b.classList.toggle("on", b.dataset.sk === k));
  const nav = k === "list" ? $('.nav-item[data-filter="all"]') : $(`.nav-item[data-view="${k}"]`);
  nav?.click();
}
function skCloseDrawer() {
  document.body.classList.remove("sk-drawer", "sk-list");
  $$("#skDock button").forEach((b) => b.classList.remove("on"));
  if (typeof showRd === "function") showRd(false);
  showView(null);
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
  SK.orbit = (SK.orbit + dt * (8 + SK.speedFrac * 260)) % 360;
  const o = $("#skOrbit"); if (o) o.setAttribute("transform", `rotate(${SK.orbit} 150 150)`);
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

skBuild();
fxInit();
STATE_HOOKS.push(skState);
