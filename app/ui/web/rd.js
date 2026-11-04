// Real-Debrid arayuzu: sol menude "Real-Debrid" gorunumu (yapistir-gec + hesap listesi), Ayarlar'da token,
// RD destekli hoster linkinde "RD ile / dogrudan" sorusu. app.js'ten sonra yuklenir (onun yardimcilarini kullanir).
"use strict";

const rd = { view: false, lastRefresh: 0, busy: false, ask: null };

// Hata metni: bilinen kod -> anlasilir metin; rd_failed (bilinmeyen RD hatasi) -> metin + RD'nin ham hata adi
function rdErr(code, detail) {
  const c = code || "rd_failed";
  const txt = T("err_" + c);
  return c === "rd_failed" && detail ? `${txt} (${detail})` : txt;
}

// app.js'teki ekleme sonucunu ortak isler: "plain" (dogrudan aria2'ye eklendi) | "handled" | "error"
function dispatchAdd(r, url, ctx) {
  if (!r || !r.ok) { toast(rdErr(r && r.error, r && r.detail), true); return "error"; }
  if (r.rd_ask) { askRd(url, ctx); return "handled"; }
  if (r.torrent_ask) { askTorrent(r.torrent_ask); return "handled"; }
  if (r.torrent_local) { openTorrentLocal(r.torrent_local); return "handled"; }
  if (r.rd) { rdResultToast(r); if (rd.view) rdRefresh(); return "handled"; }
  if (r.media) { openMedia(r, ctx && ctx.url ? ctx : { url }); return "handled"; }
  if (r.cloud) { openCloud(r.cloud); return "handled"; }
  return "plain";
}

function rdResultToast(r) {
  const parts = [];
  if (r.torrents) parts.push(T("rd_ev_torrent_n", r.torrents));
  if (r.added) parts.push(T("rd_ev_added_n", r.added));
  toast(parts.join(" · ") || T("added"), !!r.partial);
}

function rdEvent(ev) {
  if (ev.kind === "error") toast((ev.name ? ev.name + ": " : "") + rdErr(ev.error, ev.detail), true);
  else if (ev.kind === "torrent") toast(T("rd_ev_torrent"));
  else if (ev.kind === "queued") toast(T("rd_ev_queued", ev.name, ev.count));
  if (rd.view) rdRefresh();
}

// ---------- "RD ile mi, dogrudan mi?" ----------
// Ayni pencere iki is icin: RD destekli hoster (RD / dogrudan) ve torrent (RD / yerel torrent)
function setAskTexts(torrent) {
  $("#rdAskTitle").textContent = T(torrent ? "tor_ask_title" : "rd_ask_title");
  $("#rdAsk .hint").textContent = T(torrent ? "tor_ask_body" : "rd_ask_body");
  $("#rdAskRd").textContent = T(torrent ? "tor_ask_rd" : "rd_ask_rd");
  $("#rdAskDirect").textContent = T(torrent ? "tor_ask_local" : "rd_ask_direct");
}

function askRd(url, ctx) {
  rd.ask = { url, ctx: ctx || {} };
  setAskTexts(false);
  $("#rdAskUrl").textContent = url;
  $("#rdAsk").showModal();
}

function askTorrent(t) {
  if ($("#rdAsk").open) return;
  rd.ask = { torrent: t };
  setAskTexts(true);
  $("#rdAskUrl").textContent = t.name || t.src;
  $("#rdAsk").showModal();
}

// Yerel torrent: magnet'te aria2 once meta veriyi alir (arka planda; ustte "meta veri aranıyor - N eş"),
// gelince dosya secim penceresi. .torrent dosyasi/linki: dogrudan liste.
const metaJobs = new Map();   // jid -> {name, peers, seeders, elapsed}

function magnetName(src) {
  try { return new URLSearchParams(String(src).replace(/^magnet:\?/i, "")).get("dn") || ""; } catch { return ""; }
}

async function openTorrentLocal(t) {
  toast(T("resolving"), false, true);
  let r;
  try { r = await api.torrent_open(t.src || "", t.token || ""); } finally { toastDone(); }
  if (!r || !r.ok) { toast(T("err_" + ((r && r.error) || "torrent_meta_failed")), true); return; }
  if (r.cloud) { openCloud(r.cloud); return; }
  const jid = r.meta_job;
  metaJobs.set(jid, { name: t.name || magnetName(t.src) || T("tor_magnet"), peers: 0, seeders: 0, elapsed: 0 });
  renderLive();
  while (metaJobs.has(jid)) {
    await new Promise((res) => setTimeout(res, 1000));
    let s;
    try { s = await api.torrent_meta(jid); } catch { continue; }
    if (!metaJobs.has(jid)) return;                       // iptal edildi
    if (s.state === "done") { metaJobs.delete(jid); renderLive(); openCloud(s.cloud); return; }
    if (s.state === "error") {
      metaJobs.delete(jid); renderLive();
      if (s.error !== "cancelled") toast(T("err_" + (s.error || "torrent_meta_failed")), true);
      return;
    }
    Object.assign(metaJobs.get(jid), { peers: s.peers || 0, seeders: s.seeders || 0, elapsed: s.elapsed || 0 });
    renderLive();
  }
}

// Ustteki "hazirlaniyor" seridi: magnet meta veri isleri + Real-Debrid'de inen torrentler
function renderLive() {
  const ul = $("#liveList");
  const rows = [];
  for (const [jid, j] of metaJobs) {
    rows.push(`<li><span class="live-name">${escapeHtml(j.name)}</span>` +
      `<span class="live-st">${T("live_meta", j.peers, j.seeders)} · ${fmtEta(j.elapsed) || "0"}</span>` +
      `<button class="btn ghost" data-meta-cancel="${escapeHtml(jid)}">${T("cancel")}</button></li>`);
  }
  for (const p of state.rdProgress || []) {
    const k = "rd_st_" + p.status, st = T(k);
    const bits = [st === k ? p.status : st];
    if (p.status === "downloading" || p.progress) bits.push(state.lang === "tr" ? "%" + Math.floor(p.progress) : Math.floor(p.progress) + "%");
    if (p.seeders != null) bits.push(T("live_seeders", p.seeders));
    if (p.speed) bits.push(fmtBytes(p.speed) + "/s");
    rows.push(`<li><span class="live-name">${escapeHtml(p.name || "Real-Debrid")}</span>` +
      `<span class="live-st">RD: ${bits.join(" · ")}</span><i class="live-bar" style="--p:${Math.min(100, p.progress || 0)}%"></i></li>`);
  }
  ul.innerHTML = rows.join("");
  ul.hidden = rows.length === 0;
}

function bindLive() {
  $("#liveList").addEventListener("click", (e) => {
    const b = e.target.closest("[data-meta-cancel]");
    if (!b) return;
    const jid = b.dataset.metaCancel;
    metaJobs.delete(jid); renderLive();
    api.torrent_meta_cancel(jid);
  });
}

async function rdAskAnswer(viaRd) {
  const a = rd.ask; rd.ask = null;
  $("#rdAsk").close();
  if (!a) return;
  if (a.torrent) {
    if (!viaRd) { openTorrentLocal(a.torrent); return; }
    toast(T("resolving"), false, true);
    let r;
    try { r = await api.torrent_choose(a.torrent.src || "", a.torrent.token || "", "rd"); } finally { toastDone(); }
    dispatchAdd(r, a.torrent.src, {});   // RD reddederse sadece sebep (yerele otomatik gecis YOK)
    return;
  }
  toast(T("resolving"), false, true);
  let r;
  try {
    if (viaRd) r = await api.rd_add(a.url);
    else if (a.ctx.headers !== undefined) r = await api.media_probe(a.url, a.ctx.headers || {}, true);  // eklentiden
    else r = await api.add_url(a.url, "", true);
  } finally { toastDone(); }
  if (dispatchAdd(r, a.url, a.ctx) === "plain") { toast(T("added")); tick(); }
}

// ---------- gorunum ----------
function showRd(on) {
  rd.view = on;
  $(".main").classList.toggle("rd-mode", on);
  $$(".nav-item").forEach((b) => b.classList.toggle("active", on ? b.dataset.view === "rd" : b.dataset.filter === state.filter));
  if (on) rdRefresh();
}

const RD_STATUS = {
  downloaded: "rd_st_ready", downloading: "rd_st_downloading", queued: "rd_st_queued",
  magnet_conversion: "rd_st_magnet", waiting_files_selection: "rd_st_select",
  compressing: "rd_st_processing", uploading: "rd_st_processing",
  magnet_error: "rd_st_error", error: "rd_st_error", virus: "rd_st_error", dead: "rd_st_error",
};

function rdRow(name, meta, actions) {
  return `<li class="rd-item"><div class="rd-name" title="${escapeHtml(name)}">${escapeHtml(name)}</div>` +
         `<div class="rd-meta">${meta}</div><div class="rd-acts">${actions}</div></li>`;
}

async function rdRefresh() {
  if (rd.busy) return;
  rd.busy = true; rd.lastRefresh = Date.now();
  try {
    const st = await api.rd_status();
    $("#rdNoToken").hidden = !!st.has_token;
    $("#rdBody").hidden = !st.has_token;
    if (!st.has_token) { $("#rdUser").textContent = ""; return; }
    $("#rdUser").textContent = st.ok ? T("rd_user", st.username, st.type, st.premium_days) : T("err_" + st.error);
    const l = await api.rd_lists();
    if (!l.ok) { $("#rdTorrents").innerHTML = `<li class="rd-empty">${escapeHtml(T("err_" + l.error))}</li>`; return; }
    rd.downloads = l.downloads;
    $("#rdTorrents").innerHTML = l.torrents.map((t) => {
      const ready = t.status === "downloaded";
      const meta = [T(RD_STATUS[t.status] || "rd_st_processing") + (ready ? "" : ` ${Math.round(t.progress)}%`),
                    t.size ? fmtBytes(t.size) : "", t.kami ? T("rd_auto") : ""].filter(Boolean).map(escapeHtml).join(" · ");
      const acts = (ready ? `<button class="btn primary" data-rd="qt" data-id="${escapeHtml(t.id)}">${T("rd_dl")}</button>` : "") +
                   `<button class="btn ghost" data-rd="del" data-kind="torrent" data-id="${escapeHtml(t.id)}">${T("rd_del")}</button>`;
      return rdRow(t.name, meta, acts);
    }).join("") || `<li class="rd-empty">${T("rd_none")}</li>`;
    $("#rdDownloads").innerHTML = l.downloads.map((d, i) => {
      const meta = [d.host, d.size ? fmtBytes(d.size) : ""].filter(Boolean).map(escapeHtml).join(" · ");
      const acts = `<button class="btn primary" data-rd="qd" data-i="${i}">${T("rd_dl")}</button>` +
                   `<button class="btn ghost" data-rd="del" data-kind="download" data-id="${escapeHtml(d.id)}">${T("rd_del")}</button>`;
      return rdRow(d.name, meta, acts);
    }).join("") || `<li class="rd-empty">${T("rd_none")}</li>`;
  } finally { rd.busy = false; }
}

async function rdAction(btn) {
  const kind = btn.dataset.rd;
  if (kind === "del" && btn.dataset.armed !== "1") {     // silme iki tik: hesaptan siler
    btn.dataset.armed = "1"; btn.textContent = T("rd_del_sure");
    setTimeout(() => { if (btn.isConnected) { btn.dataset.armed = ""; btn.textContent = T("rd_del"); } }, 3000);
    return;
  }
  btn.disabled = true;
  let r;
  if (kind === "qt") r = await api.rd_queue_torrent(btn.dataset.id);
  else if (kind === "qd") r = await api.rd_queue_download(rd.downloads[Number(btn.dataset.i)]);
  else r = await api.rd_delete(btn.dataset.kind, btn.dataset.id);
  if (!r.ok) { toast(rdErr(r.error, r.detail), true); btn.disabled = false; return; }
  if (kind !== "del") { toast(r.added ? T("rd_ev_added_n", r.added) : T("rd_ev_torrent")); tick(); }
  rdRefresh();
}

// ---------- ayarlar: token ----------
async function rdSettingsState() {
  const st = await api.rd_status();
  $("#rdTokenState").textContent = !st.has_token ? T("s_rd_none")
    : st.ok ? T("s_rd_saved", st.username, st.premium_days) : T("err_" + st.error);
  $("#rdTokenClear").hidden = !st.has_token;
}

async function rdSaveToken() {
  const el = $("#rdToken");
  const value = el.value.trim();
  el.value = "";                       // token arayuzde kalmasin
  if (!value) return;
  $("#rdTokenState").textContent = T("resolving");
  const r = await api.rd_set_token(value);
  if (!r.ok) { $("#rdTokenState").textContent = T("err_" + r.error); return; }
  rdSettingsState();
  if (rd.view) rdRefresh();
}

function bindRd() {
  $("#rdForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const text = $("#rdInput").value.trim();
    if (!text) return;
    const btn = $("#rdSend"); btn.disabled = true;
    toast(T("resolving"), false, true);
    try {
      const r = await api.rd_add(text);
      toastDone();
      if (r.ok) { $("#rdInput").value = ""; rdResultToast(r); tick(); } else toast(rdErr(r.error, r.detail), true);
    } finally { btn.disabled = false; rdRefresh(); }
  });
  $("#rdInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || !e.shiftKey) && !e.isComposing) { e.preventDefault(); $("#rdForm").requestSubmit(); }
  });
  $("#rdPick").addEventListener("click", async () => {
    const r = await api.rd_pick_torrent();
    if (r.cancelled) return;
    if (r.ok) rdResultToast(r); else toast(rdErr(r.error, r.detail), true);
    rdRefresh();
  });
  $("#torrentPick").addEventListener("click", async () => {   // .torrent dosyasi -> RD / sor / yerel (ayara gore)
    const r = await api.torrent_pick_file();
    if (r.cancelled) return;
    if (dispatchAdd(r, "", {}) === "plain") tick();
  });
  $("#rdRefresh").addEventListener("click", rdRefresh);
  $("#rdOpenSettings").addEventListener("click", () => { openSettings().then(() => $("#rdToken").focus()); });
  $("#rdView").addEventListener("click", (e) => { const b = e.target.closest("button[data-rd]"); if (b) rdAction(b); });

  $("#rdAskRd").addEventListener("click", () => rdAskAnswer(true));
  $("#rdAskDirect").addEventListener("click", () => rdAskAnswer(false));
  $("#rdAsk").addEventListener("close", () => { rd.ask = null; });

  $("#rdTokenSave").addEventListener("click", rdSaveToken);
  $("#rdToken").addEventListener("keydown", (e) => { if (e.key === "Enter") { e.preventDefault(); rdSaveToken(); } });
  $("#rdTokenClear").addEventListener("click", async () => { await api.rd_clear_token(); rdSettingsState(); if (rd.view) rdRefresh(); });
  $("#settingsBtn").addEventListener("click", rdSettingsState);
  $("#settings").addEventListener("close", () => { $("#rdToken").value = ""; });
}
