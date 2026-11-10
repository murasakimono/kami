// Kami "Sunak" katmani. Eski DOM ve JS'e dokunmaz; ustune biner, durumu STATE_HOOKS ile alir.
"use strict";

const SK = { autoPlay: new Set(JSON.parse((() => { try { return localStorage.getItem("kami.autoplay") || "[]"; } catch { return "[]"; } })())), sel: null, page: 0, peak: 1, happyUntil: 0, prevStatus: new Map(), eye: null, orbit: 0, speedFrac: 0, built: false };
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
          <defs><linearGradient id="skRingG" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#8B5CF6"/><stop offset="1" stop-color="#2EE6A6"/></linearGradient></defs>
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
    <div class="sk-cmd" id="skCmd"><span>›</span></div>
  </div>
  <nav class="sk-dock" id="skDock">
    <button data-sk="list" title="${skL("Liste", "List")}">${skIcon.list}</button>
    <button data-sk="rd" title="Real-Debrid">${skIcon.rd}</button>
    <button data-sk="follow" title="${skL("Takip", "Follow")}">${skIcon.follow}<b id="skFollowN" hidden></b></button>
    <button data-sk="history" title="${skL("Geçmiş", "History")}">${skIcon.hist}</button>
    <button data-sk="batch" title="${skL("Toplu", "Batch")}">${skIcon.batch}</button>
    <button data-sk="ai" class="ai" title="${skL("AI altyazı / vokal", "AI subtitle / vocals")}">${skIcon.sub}</button>
    <button data-sk="settings" title="${skL("Ayarlar", "Settings")}">${skIcon.gear}</button>
  </nav>
  <button class="sk-drawer-close" id="skClose" aria-label="${skL("kapat", "close")}">${skIcon.x}</button>`;
  document.body.prepend(root);
  // eski ekleme formu komut satirina tasinir (dinleyicileri onunla gelir)
  const form = $("#addForm");
  if (form) {
    form.classList.add("add"); $("#skCmd").appendChild(form);
    const watch = document.createElement("button");   // indirmeden izle (yt-dlp / Real-Debrid / dogrudan)
    watch.type = "button"; watch.className = "btn sk-watch"; watch.textContent = skL("İzle", "Watch");
    watch.title = skL("İndirmeden Kami Player'da izle", "Stream in Kami Player without downloading");
    watch.onclick = () => { const u = $("#addInput").value.trim(); if (u && typeof playerOpenUrl === "function") playerOpenUrl(u.split(/\s+/)[0]); else $("#addInput").focus(); };
    form.querySelector('button[type="submit"]')?.before(watch);
  }
  $("#addInput")?.setAttribute("placeholder", skL("Bağlantı yapıştır ya da dosyayı ruha bırak…", "Paste a link or drop a file on the spirit…"));
  skBind();
  if (window.KamiEye) {
    // Sunak'ta tam boy karakter; sadece goz kesiti (eye/assets) eklenti ve widget icin
    SK.eye = new KamiEye($("#skEye"), { assets: "eye/char/", eyeY: 0.38, mirrorFrame: true });
    SK.eye.ready.then(() => SK.eye.start()).catch((e) => console.error(e));
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
  $("#skTrack").addEventListener("click", (e) => { const b = e.target.closest(".sk-strip"); if (b) { SK.sel = skItems().find((d) => String(d.id) === b.dataset.id)?.id ?? null; skRender(); } });
  $("#skDots").addEventListener("click", (e) => { const i = e.target.dataset.i; if (i != null) { SK.sel = skItems()[+i]?.id; skRender(); } });
  $("#skBar").addEventListener("click", skBarAction);
  $("#skDock").addEventListener("click", (e) => { const b = e.target.closest("button"); if (b) skDock(b.dataset.sk); });
  $("#skClose").addEventListener("click", skCloseDrawer);
  document.addEventListener("keydown", (e) => {
    if (e.target.matches("input, textarea, select") || document.querySelector("dialog[open]")) return;
    if (e.key === "Escape") skCloseDrawer();
    if (document.body.classList.contains("sk-drawer")) return;
    if (e.key === "ArrowRight" || e.key === "ArrowLeft") { skMoveSel(e.key === "ArrowRight" ? 1 : -1); e.preventDefault(); }
  });
  const altar = $("#skAltar");
  altar.addEventListener("mouseenter", () => SK.eye?.set({ lid: 1 }));
  altar.addEventListener("mouseleave", () => SK.eye?.set({ lid: 0 }));
  document.addEventListener("mousemove", (e) => SK.eye?.lookAt(e.clientX, e.clientY));
  // dosya surukleme: ruh uyanir, birakinca yutar (asil ekleme extras.js'teki drop dinleyicisinde)
  let depth = 0;
  document.addEventListener("dragenter", () => { depth++; altar.classList.add("drop"); SK.eye?.set({ mood: "alert" }); });
  document.addEventListener("dragleave", () => { if (--depth <= 0) { depth = 0; altar.classList.remove("drop"); SK.eye?.set({ mood: "idle" }); } });
  document.addEventListener("drop", () => {
    depth = 0; altar.classList.remove("drop"); altar.classList.remove("swallow"); void altar.offsetWidth; altar.classList.add("swallow");
    SK.eye?.set({ mood: "happy" }); SK.happyUntil = Date.now() + 1500;
  });
}

// listede gosterilecekler: once aktif, sonra bekleyen/duraklatilan, sonra hata, en son biten
const SK_ORDER = { active: 0, waiting: 1, queued: 1, confirm: 1, paused: 2, error: 3, complete: 4 };
function skItems() {
  return state.items.filter((d) => d.status !== "removed")
    .map((d, i) => [d, i]).sort((a, b) => (SK_ORDER[a[0].status] ?? 5) - (SK_ORDER[b[0].status] ?? 5) || a[1] - b[1]).map((x) => x[0]);
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
  if (d.status === "active") return ["#7C4DFF", "#2EE6A6"];
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
  return `<button class="sk-strip ${d.status === "active" ? "" : "calm"} ${d.id === SK.sel ? "sel" : ""}" data-id="${escapeHtml(d.id)}" title="${escapeHtml(d.filename || d.url)}">
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
    const key = [d.status, skPct(d), d.id === SK.sel, d.filename, d.speed > 0 ? Math.round(d.speed / 65536) : 0, JSON.stringify(d.extra?.ai_whisper ?? "") + (d.extra?.ai_whisper_p ?? "") + (d.extra?.ai_uvr ?? "") + (d.extra?.ai_uvr_p ?? "")].join("|");
    let el = old.get(d.id);
    if (!el || el.dataset.key !== key) {
      const t = document.createElement("template"); t.innerHTML = skStripHtml(d).trim();
      const nu = t.content.firstChild;
      if (el) {   // ayni seritte sadece sivi yuksekligi degisirse eski sivi elemanini koru: yukseklik gecisi kayar
        const oldLiq = el.querySelector(".sk-liquid"), newLiq = nu.querySelector(".sk-liquid");
        if (oldLiq && newLiq && el.dataset.status === d.status) { oldLiq.style.height = newLiq.style.height; newLiq.replaceWith(oldLiq); }
        if (el.dataset.status !== d.status) nu.classList.add(d.status === "complete" ? "burst" : "slosh");
      }
      nu.dataset.key = key; nu.dataset.status = d.status;
      el = nu;
    }
    frag.push(el);
    old.delete(d.id);
  }
  track.replaceChildren(...frag);
}

function skRenderBar(d) {
  const bar = $("#skBar");
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
  bar.innerHTML = `<span class="sk-bar-name">${escapeHtml(d.filename || d.url)}</span><span class="sk-bar-info">${escapeHtml(info)}</span>${btns.join("")}`;
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
      SK.happyUntil = Date.now() + 3000;
      if (SK.autoPlay.has(d.id)) { SK.autoPlay.delete(d.id); skAutoSave(); if (typeof playerOpen === "function") playerOpen(d.id); }   // bitince oynat
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
  SK.eye?.set({
    isDownloading: active.length > 0,
    downloadSpeed: Math.min(1, spd / (125 * 1024 * 1024)),
    isError: !s.engine_ok || (sel && sel.status === "error"),
    mood: Date.now() < SK.happyUntil ? "happy" : $("#skAltar").classList.contains("drop") ? "alert" : "idle",
  });
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

skBuild();
STATE_HOOKS.push(skState);
