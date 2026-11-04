// Real-Debrid arayuzu: sol menude "Real-Debrid" gorunumu (yapistir-gec + hesap listesi), Ayarlar'da token,
// RD destekli hoster linkinde "RD ile / dogrudan" sorusu. app.js'ten sonra yuklenir (onun yardimcilarini kullanir).
"use strict";

const rd = { view: false, lastRefresh: 0, busy: false, ask: null };

// app.js'teki ekleme sonucunu ortak isler: "plain" (dogrudan aria2'ye eklendi) | "handled" | "error"
function dispatchAdd(r, url, ctx) {
  if (!r || !r.ok) { toast(T("err_" + ((r && r.error) || "rd_failed")), true); return "error"; }
  if (r.rd_ask) { askRd(url, ctx); return "handled"; }
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
  if (ev.kind === "error") toast(T("err_" + ev.error), true);
  else if (ev.kind === "torrent") toast(T("rd_ev_torrent"));
  else if (ev.kind === "queued") toast(T("rd_ev_queued", ev.name, ev.count));
  if (rd.view) rdRefresh();
}

// ---------- "RD ile mi, dogrudan mi?" ----------
function askRd(url, ctx) {
  rd.ask = { url, ctx: ctx || {} };
  $("#rdAskUrl").textContent = url;
  $("#rdAsk").showModal();
}

async function rdAskAnswer(viaRd) {
  const a = rd.ask; rd.ask = null;
  $("#rdAsk").close();
  if (!a) return;
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
  if (!r.ok) { toast(T("err_" + r.error), true); btn.disabled = false; return; }
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
      if (r.ok) { $("#rdInput").value = ""; rdResultToast(r); tick(); } else toast(T("err_" + r.error), true);
    } finally { btn.disabled = false; rdRefresh(); }
  });
  $("#rdInput").addEventListener("keydown", (e) => {
    if (e.key === "Enter" && (e.ctrlKey || !e.shiftKey) && !e.isComposing) { e.preventDefault(); $("#rdForm").requestSubmit(); }
  });
  $("#rdPick").addEventListener("click", async () => {
    const r = await api.rd_pick_torrent();
    if (r.cancelled) return;
    if (r.ok) rdResultToast(r); else toast(T("err_" + r.error), true);
    rdRefresh();
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
