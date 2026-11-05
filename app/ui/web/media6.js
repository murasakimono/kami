// Asama 6b arayuzu: medya araclari penceresi (soz, arsiv, Whisper, UVR), Takip gorunumu, Ayarlar > Medya ekstralari.
// Asama 6c gorunumleri de showView ile ayni duzende acilir.
"use strict";

// ---------- genel gorunum gecisi (Real-Debrid disindakiler) ----------
const VIEW_OPEN = {};   // ad -> acilinca calisan yenileme
function showView(name) {
  const main = $(".main");
  if (name) main.dataset.view = name; else delete main.dataset.view;
  if (name) $$(".nav-item").forEach((b) => b.classList.toggle("active", b.dataset.view === name));
  if (name && VIEW_OPEN[name]) VIEW_OPEN[name]();
}

// ---------- rozetler: extraBadges'i genislet ----------
const _baseBadges = extraBadges;
extraBadges = function (d) {   // eslint-disable-line no-global-assign
  const x = d.extra || {}, out = [_baseBadges(d)];
  if (["synced", "plain", "pasted"].includes(x.lyrics)) out.push(`<span class="badge ok">${T("b_lyrics")}</span>`);
  if (x.lyrics === "ai") out.push(`<span class="badge ok" title="${escapeHtml(T("ly_ai"))}">${T("b_lyrics_ai")}</span>`);
  if (x.ai_lyrics === "running") out.push(`<span class="badge prog">${T("b_lyrics_ai")} ${Math.round((x.ai_lyrics_p || 0) * 100)}%</span>`);
  for (const k of ["whisper", "uvr"]) {
    const st = x["ai_" + k];
    if (st === "running") out.push(`<span class="badge prog">${k === "whisper" ? "Whisper" : "UVR5"} ${Math.round((x["ai_" + k + "_p"] || 0) * 100)}%</span>`);
    else if (st === "queued") out.push(`<span class="badge">${k === "whisper" ? "Whisper" : "UVR5"} · ${T("ai_queued")}</span>`);
    else if (st === "done") out.push(`<span class="badge ok">${T(k === "whisper" ? "b_sub" : "b_uvr")}</span>`);
    else if (st === "error") out.push(`<span class="badge bad">${k === "whisper" ? "Whisper" : "UVR5"} ✕</span>`);
  }
  return out.join("");
};

// ---------- medya araclari penceresi ----------
const mt = { id: 0 };
function mtItem() { return state.items.find((x) => x.id === mt.id); }

function aiLine(x, k) {
  const st = x["ai_" + k];
  if (!st) return "";
  if (st === "running") return T("ai_running", x["ai_" + k + "_p"] || 0);
  if (st === "error") return T("ai_error", x["ai_" + k + "_err"] || "?");
  return T("ai_" + st);
}

function fillMediaTools() {
  const d = mtItem();
  if (!d || !$("#mtools").open) return;
  const x = d.extra || {};
  const audio = d.category === "music";
  $("#mtName").textContent = d.filename || d.url;
  $("#mtLyricsRow").hidden = !audio;
  $("#mtPasteRow").hidden = !audio;
  $("#mtArchiveRow").hidden = !audio;
  $("#mtUvrRow").hidden = !audio;
  const aiL = aiLine(x, "lyrics");
  $("#mtLyrics").textContent = (x.lyrics ? T("ly_" + x.lyrics) : "") + (aiL && x.lyrics !== "ai" ? " · AI: " + aiL : "");
  $("#mtLyricsAiBtn").textContent = T(["queued", "running"].includes(x.ai_lyrics) ? "mt_cancel" : "mt_lyrics_ai");
  const links = x.lyrics_links || {};
  const L = [];
  if (links.genius_song) L.push(["ly_genius_song", links.genius_song]);
  if (x.lyrics && !["synced", "instrumental", "pasted"].includes(x.lyrics)) {
    if (links.genius) L.push(["ly_genius", links.genius]);
    if (links.azlyrics) L.push(["ly_azlyrics", links.azlyrics]);
  }
  $("#mtLinks").innerHTML = L.map(([k, u]) => `<button type="button" class="link-btn" data-link="${escapeHtml(u)}">${T(k)}</button>`).join("") +
    (x.lyrics_lrc ? `<button type="button" class="link-btn" data-path="${escapeHtml(x.lyrics_lrc)}">.${escapeHtml(x.lyrics_lrc.split(".").pop())}</button>` : "");
  $("#mtArchive").textContent = x.archive === "ok" ? T("ar_ok", d.filename, x.album, x.archive_source) : x.archive === "nomatch" ? T("ar_nomatch") : "";
  const w = aiLine(x, "whisper"), u = aiLine(x, "uvr");
  $("#mtWhisper").innerHTML = escapeHtml(w) + (x.ai_whisper_srt ? ` <button type="button" class="link-btn" data-path="${escapeHtml(x.ai_whisper_srt)}">${T("mt_open")}</button>` : "");
  $("#mtUvr").innerHTML = escapeHtml(u) + ((x.ai_uvr_files || [])[0] ? ` <button type="button" class="link-btn" data-path="${escapeHtml(x.ai_uvr_files[0])}">${T("mt_open")}</button>` : "");
  const busy = (k) => ["queued", "running"].includes(x["ai_" + k]);
  $("#mtWhisperBtn").textContent = T(busy("whisper") ? "mt_cancel" : "mt_run");
  $("#mtUvrBtn").textContent = T(busy("uvr") ? "mt_cancel" : "mt_run");
}

function openMediaTools(id) {
  mt.id = id;
  $("#mtWhisperLang").value = state.settings.whisper_lang || "auto";
  $("#mtools").showModal();
  fillMediaTools();
}

async function runAi(kind) {
  const d = mtItem();
  if (!d) return;
  const x = d.extra || {};
  if (["queued", "running"].includes(x["ai_" + kind])) { await api.ai_cancel(kind, d.id); return; }
  const r = await api.ai_run(kind, d.id, kind !== "uvr" ? $("#mtWhisperLang").value : "");
  if (r.ok) { tick(); return; }
  if (r.error === "tool_missing") {
    // agir indirme: once sor (defter: modeller ilk kullanimda iner, once sorulur)
    if (confirm(T("ai_ask", r.tool === "whisper" ? "Whisper" : "UVR5", r.size_gb))) {
      await api.ai_install(r.tool);
      toast(T("ai_install_started"));
    }
    return;
  }
  toast(T("err_" + r.error) || r.error, true);
}

function bindMediaTools() {
  $("#mtLyricsBtn").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try { const r = await slow("media_lyrics", mt.id); if (!r.ok) toast(T("err_" + r.error), true); } finally { e.target.disabled = false; }
    await tick(); fillMediaTools();
  });
  $("#mtArchiveBtn").addEventListener("click", async (e) => {
    e.target.disabled = true;
    try { await slow("media_archive", mt.id); } finally { e.target.disabled = false; }
    await tick(); fillMediaTools();
  });
  $("#mtLyricsAiBtn").addEventListener("click", () => runAi("lyrics"));
  $("#mtPasteBtn").addEventListener("click", async () => {
    const txt = $("#mtPaste").value;
    if (!txt.trim()) return;
    const r = await api.media_lyrics_paste(mt.id, txt);
    if (!r.ok) { toast(T("err_" + r.error) || r.error, true); return; }
    $("#mtPaste").value = "";
    toast(T("mt_paste_ok", (r.lrc || r.txt || "").split(".").pop()));
    await tick(); fillMediaTools();
  });
  $("#mtWhisperBtn").addEventListener("click", () => runAi("whisper"));
  $("#mtUvrBtn").addEventListener("click", () => runAi("uvr"));
  $("#mtools").addEventListener("click", (e) => {
    const l = e.target.closest("[data-link]"); if (l) api.open_link(l.dataset.link);
    const p = e.target.closest("[data-path]"); if (p) api.open_path(p.dataset.path);
  });
}

// ---------- Takip gorunumu ----------
const fw = { list: [] };
const fmtAgo = (ts) => { if (!ts) return "—"; const m = Math.round((Date.now() / 1000 - ts) / 60); return m < 60 ? `${m} dk` : `${Math.round(m / 60)} sa`; };

async function followRefresh() {
  fw.list = await api.follow_list();
  $("#followCount").textContent = fw.list.length || "";
  $("#followEmpty").hidden = fw.list.length > 0;
  $("#followList").innerHTML = fw.list.map((f) =>
    rdRow(f.name || f.url,
      `<span>${f.format.toUpperCase()}</span><span>${T("fw_seen", f.seen_count)}</span><span>${T("fw_last", fmtAgo(f.last_check))}</span>` +
      (f.error ? `<span class="st-error">${escapeHtml(f.error.slice(0, 80))}</span>` : ""),
      `<select data-fw="fmt" data-id="${f.id}"><option value="mp4"${f.format === "mp4" ? " selected" : ""}>MP4</option><option value="mp3"${f.format === "mp3" ? " selected" : ""}>MP3</option></select>` +
      `<button type="button" class="btn ghost" data-fw="toggle" data-id="${f.id}">${T(f.enabled ? "fw_on" : "fw_off")}</button>` +
      `<button type="button" class="btn ghost" data-fw="check" data-id="${f.id}">${T("fw_check")}</button>` +
      `<button type="button" class="btn ghost danger" data-fw="remove" data-id="${f.id}">${T("fw_remove")}</button>`)).join("");
}
VIEW_OPEN.follow = followRefresh;

function bindFollow() {
  $("#followForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const url = $("#followUrl").value.trim();
    if (!url) return;
    const btn = e.target.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const r = await slow("follow_add", url, $("#followFmt").value, "best", Number($("#followBack").value || 0));
      if (!r.ok) { toast(T("err_" + r.error), true); return; }
      $("#followUrl").value = "";
      toast(T("fw_added", r.follow.name));
      followRefresh();
    } finally { btn.disabled = false; }
  });
  $("#followCheckAll").addEventListener("click", async () => { await slow("follow_check_now", ""); followRefresh(); tick(); });
  $("#followList").addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-fw]");
    if (!b) return;
    const f = fw.list.find((x) => x.id === b.dataset.id);
    if (b.dataset.fw === "toggle") await api.follow_update(f.id, { enabled: !f.enabled });
    else if (b.dataset.fw === "remove") await api.follow_remove(f.id);
    else if (b.dataset.fw === "check") { b.disabled = true; await slow("follow_check_now", f.id); tick(); }
    followRefresh();
  });
  $("#followList").addEventListener("change", async (e) => {
    const s = e.target.closest("select[data-fw=fmt]");
    if (s) { await api.follow_update(s.dataset.id, { format: s.value }); followRefresh(); }
  });
  api.follow_list().then((l) => { $("#followCount").textContent = l.length || ""; });
}

// ---------- Ayarlar > Medya ekstralari ----------
async function refreshMediaSettings() {
  const st = await api.ai_status();
  const fill = (sel, list, cur) => { sel.innerHTML = list.map((m) => `<option value="${m}">${m}</option>`).join(""); sel.value = cur; };
  fill($("#whisperModelSel"), st.whisper_models, state.settings.whisper_model);
  fill($("#uvrModelSel"), st.uvr_models, state.settings.uvr_model);
  const one = (t) => t.installing ? T("ai_installing", t.installing) : T(t.installed ? "ai_inst" : "ai_missing");
  $("#aiState").textContent = T("ai_state", one(st.whisper), one(st.uvr));
  const g = await api.genius_status();
  $("#geniusState").textContent = T(g.has_token ? "s_genius_ok" : "s_genius_none");
  $("#geniusClear").hidden = !g.has_token;
  $("#musicDir").textContent = state.settings.music_dir || T("reset_dir");
}

function bindMediaSettings() {
  $("#settingsBtn").addEventListener("click", () => setTimeout(refreshMediaSettings, 50));
  $("#geniusSave").addEventListener("click", async () => {
    const v = $("#geniusToken").value.trim();
    if (!v) return;
    const r = await slow("genius_set_token", v);
    $("#geniusToken").value = "";
    if (!r.ok) toast(T("err_" + r.error) || r.error, true);
    refreshMediaSettings();
  });
  $("#geniusClear").addEventListener("click", async () => { await api.genius_clear(); refreshMediaSettings(); });
  $("#musicDirChange").addEventListener("click", async () => {
    const dir = await api.choose_folder();
    if (dir) { await setSetting("music_dir", dir); refreshMediaSettings(); }
  });
  $("#musicDirReset").addEventListener("click", async () => { await setSetting("music_dir", ""); refreshMediaSettings(); });
}

// ---------- get_state: AI olaylari + kurulum durumu ----------
function onAiEvents(evs) {
  for (const ev of evs || []) {
    const [k, what, ...rest] = String(ev).split(":");
    if (k === "follow") { toast(T("fw_new", what, rest.join(":"))); if ($(".main").dataset.view === "follow") followRefresh(); continue; }
    if (what === "installed" || what === "install_failed") { toast(T("ai_ev_" + what, k === "whisper" ? "Whisper" : "UVR5"), what !== "installed"); continue; }
    if (what === "cpu") { toast(rest.join(":"), true); continue; }
    if (what === "done") toast(T("ai_ev_done", k, rest.join(":")));
  }
  fillMediaTools();
}

// app.js tick() her get_state sonrasi cagirir (6c de buraya ekler)
const STATE_HOOKS = [(s) => { if ((s.ai_events || []).length) onAiEvents(s.ai_events); else fillMediaTools(); }];
function onStateExtras(s) { for (const h of STATE_HOOKS) { try { h(s); } catch (e) { console.error(e); } } }

window.addEventListener("pywebviewready", () => {   // app.js init'ten sonra (api hazir)
  bindMediaTools();
  bindFollow();
  bindMediaSettings();
});
