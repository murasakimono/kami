// Kami arayuz mantigi. Python tarafi: pywebview.api.*
"use strict";

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];

const state = {
  lang: "tr",
  filter: "all",
  items: [],
  history: new Array(120).fill(0),   // son 60 sn (0.5 sn aralik)
  settings: {},
  known: new Map(),                   // id -> status (bitis bildirimi icin)
};
let api = null;

const T = (key, ...args) => {
  const v = (I18N[state.lang] || I18N.tr)[key];
  return typeof v === "function" ? v(...args) : (v ?? key);
};

// ---------- bicimlendirme ----------
const UNITS = ["B", "KB", "MB", "GB", "TB"];
function splitBytes(n) {
  let i = 0;
  while (n >= 1024 && i < UNITS.length - 1) { n /= 1024; i++; }
  const num = i === 0 ? String(Math.round(n)) : n.toFixed(n < 10 ? 2 : n < 100 ? 1 : 0);
  return [num, UNITS[i]];
}
const fmtBytes = (n) => splitBytes(n).join(" ");
function fmtEta(sec) {
  if (!isFinite(sec) || sec <= 0) return "";
  sec = Math.round(sec);
  const h = Math.floor(sec / 3600), m = Math.floor((sec % 3600) / 60), s = sec % 60;
  const tr = state.lang === "tr";
  if (h) return tr ? `${h} sa ${m} dk` : `${h}h ${m}m`;
  if (m) return tr ? `${m} dk ${s} sn` : `${m}m ${s}s`;
  return tr ? `${s} sn` : `${s}s`;
}

// ---------- i18n uygula ----------
function applyI18n() {
  document.documentElement.lang = state.lang;
  $$("[data-i18n]").forEach((el) => { el.textContent = T(el.dataset.i18n); });
  $$("[data-i18n-placeholder]").forEach((el) => { el.placeholder = T(el.dataset.i18nPlaceholder); });
  $$("[data-i18n-title]").forEach((el) => { el.title = T(el.dataset.i18nTitle); el.setAttribute("aria-label", T(el.dataset.i18nTitle)); });
  $$("[data-i18n-aria]").forEach((el) => { el.setAttribute("aria-label", T(el.dataset.i18nAria)); });
  $("#list").innerHTML = "";
  render();
}

function applyTheme(theme) {
  document.documentElement.dataset.theme = theme === "light" ? "light" : "dark";
  drawSpeed();
}

// ---------- filtre ----------
const ACTIVE = new Set(["active", "waiting", "queued", "confirm"]);
function matches(d, f) {
  if (f === "all") return true;
  if (f === "active") return ACTIVE.has(d.status);
  if (f.startsWith("cat:")) return d.category === f.slice(4);
  return d.status === f;
}

// ---------- liste ----------
const ICONS = {
  pause: '<svg viewBox="0 0 24 24"><path d="M8 5v14M16 5v14" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>',
  resume: '<svg viewBox="0 0 24 24"><path d="M7 5l12 7-12 7z" fill="currentColor"/></svg>',
  folder: '<svg viewBox="0 0 24 24"><path d="M3 7h6l2 2h10v10H3z" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
  open: '<svg viewBox="0 0 24 24"><path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/></svg>',
  remove: '<svg viewBox="0 0 24 24"><path d="M6 6l12 12M18 6 6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg>',
  mtools: '<svg viewBox="0 0 24 24"><path d="M9 18V6l10-2v12" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/><circle cx="6.5" cy="18" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/><circle cx="16.5" cy="16" r="2.5" fill="none" stroke="currentColor" stroke-width="1.8"/></svg>',
  hash: '<svg viewBox="0 0 24 24"><path d="M9 4 7 20M17 4l-2 16M4 9h16M3 15h16" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/></svg>',
  trash: '<svg viewBox="0 0 24 24"><path d="M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linejoin="round"/></svg>',
};

function actionsFor(d) {
  const b = (act, icon, label, cls = "") =>
    `<button data-act="${act}" class="${cls}" title="${label}" aria-label="${label}">${icon}</button>`;
  switch (d.status) {
    case "confirm":
      return `<button data-act="confirm-yes" class="yes">${T("confirm_yes")}</button>` +
             `<button data-act="confirm-no">${T("confirm_no")}</button>`;
    case "active": case "waiting": case "queued":
      return b("pause", ICONS.pause, T("pause")) + b("remove", ICONS.remove, T("remove"), "danger");
    case "paused":
      return b("resume", ICONS.resume, T("resume")) + b("remove", ICONS.remove, T("remove"), "danger");
    case "error":
      return b("resume", ICONS.resume, T("retry")) + b("remove", ICONS.remove, T("remove"), "danger");
    case "complete":
      return b("open", ICONS.open, T("open_file")) + b("folder", ICONS.folder, T("open_folder")) +
             b("hash", ICONS.hash, T("hash_btn")) +
             (["video", "music"].includes(d.category) ? b("mtools", ICONS.mtools, T("mt_title")) : "") +
             b("remove", ICONS.remove, T("remove")) + b("delete", ICONS.trash, T("remove_file"), "danger");
    default:
      return b("remove", ICONS.remove, T("remove"), "danger");
  }
}

function metaFor(d) {
  const parts = [];
  const st = `<span class="st-${d.status}">${d.status === "error" && d.error ? `${T("st_error")}: ${escapeHtml(d.error === "yt_bot" ? T("err_yt_bot") : d.error)}` : d.status === "confirm" ? T("confirm_q") : d.phase === "processing" ? T("phase_processing") : d.phase === "seeding" ? T("phase_seeding") : T("st_" + d.status)}</span>`;
  parts.push(st);
  if (d.status === "complete" || d.status === "confirm") {
    if (d.size) parts.push(`<span>${fmtBytes(d.size)}</span>`);
  } else if (d.size) {
    const pct = Math.floor((d.downloaded / d.size) * 100);
    parts.push(`<span>${fmtBytes(d.downloaded)} / ${fmtBytes(d.size)}</span>`, `<span>${state.lang === "tr" ? "%" + pct : pct + "%"}</span>`);
  } else if (d.downloaded) {
    parts.push(`<span>${fmtBytes(d.downloaded)}</span>`);
  }
  if (d.status === "active") {
    if (d.speed) parts.push(`<span class="speedtxt">${fmtBytes(d.speed)}/s</span>`);
    if (d.speed && d.size) parts.push(`<span>${T("eta", fmtEta((d.size - d.downloaded) / d.speed))}</span>`);
    if (d.connections) parts.push(`<span>${T("connections", d.connections)}</span>`);
  }
  const badges = extraBadges(d);
  if (badges) parts.push(badges);
  return parts.join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const catVar = (c) => (["video", "music", "archive", "program", "document", "torrent"].includes(c) ? `var(--cat-${c})` : "var(--muted)");

function render() {
  const list = $("#list");
  const visible = state.items.filter((d) => matches(d, state.filter));
  const existing = new Map($$(".item", list).map((li) => [Number(li.dataset.id), li]));
  const seen = new Set();

  visible.forEach((d, idx) => {
    seen.add(d.id);
    let li = existing.get(d.id);
    if (!li) {
      li = document.createElement("li");
      li.className = "item";
      li.dataset.id = d.id;
      li.draggable = true;   // surukle-sirala (extras.js)
      li.innerHTML = `<div class="ficon"></div><div class="name"></div><div class="actions"></div><div class="meta"></div><div class="bar"><i></i></div>`;
    }
    const sig = `${d.status}|${d.filename}|${d.downloaded}|${d.size}|${d.speed}|${d.connections}|${d.error}|${d.phase}|${JSON.stringify(d.extra || {})}`;
    if (li.dataset.sig !== sig) {
      li.className = `item st-${d.status}`;
      const name = d.filename || d.url;
      const nameEl = $(".name", li);
      nameEl.textContent = name;
      nameEl.title = d.path || d.url;
      $(".ficon", li).style.setProperty("--cat", catVar(d.category));
      $(".meta", li).innerHTML = metaFor(d);
      $(".bar i", li).style.width = d.size ? `${Math.min(100, (d.downloaded / d.size) * 100)}%` : "0";
      if (li.dataset.status !== d.status) {
        $(".actions", li).innerHTML = actionsFor(d);
        li.dataset.status = d.status;
      }
      li.dataset.sig = sig;
    }
    if (list.children[idx] !== li) list.insertBefore(li, list.children[idx] || null);
  });
  existing.forEach((li, id) => { if (!seen.has(id)) li.remove(); });

  const empty = $("#empty");
  empty.hidden = visible.length > 0;
  $("#emptyBody").textContent = state.items.length ? T("empty_filter") : T("empty_body");
  list.hidden = visible.length === 0;

  // sayaclar
  const counts = {};
  for (const f of $$("[data-count]").map((el) => el.dataset.count)) {
    counts[f] = state.items.filter((d) => matches(d, f)).length;
  }
  $$("[data-count]").forEach((el) => { const n = counts[el.dataset.count]; el.textContent = n ? n : ""; });
}

// ---------- hiz grafigi ----------
function drawSpeed() {
  const cv = $("#speedCanvas");
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth, h = cv.clientHeight;
  if (!w || !h) return;
  if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
    cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
  }
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  const css = getComputedStyle(document.documentElement);
  const accent = css.getPropertyValue("--accent").trim();
  const line = css.getPropertyValue("--line").trim();

  const data = state.history;
  const peak = Math.max(1024 * 1024, ...data) * 1.25;
  const top = 14, bottom = h;
  const xStep = w / (data.length - 1);
  const y = (v) => bottom - (v / peak) * (bottom - top);

  // ince yatay kilavuz (zirvenin yarisi)
  ctx.strokeStyle = line; ctx.lineWidth = 1; ctx.setLineDash([3, 5]);
  ctx.beginPath(); ctx.moveTo(0, Math.round(y(peak / 2)) + .5); ctx.lineTo(w, Math.round(y(peak / 2)) + .5); ctx.stroke();
  ctx.setLineDash([]);

  const path = new Path2D();
  path.moveTo(0, y(data[0]));
  for (let i = 1; i < data.length; i++) {
    const x0 = (i - 1) * xStep, x1 = i * xStep, xm = (x0 + x1) / 2;
    path.bezierCurveTo(xm, y(data[i - 1]), xm, y(data[i]), x1, y(data[i]));
  }
  const area = new Path2D(path);
  area.lineTo(w, bottom); area.lineTo(0, bottom); area.closePath();
  const grad = ctx.createLinearGradient(0, top, 0, bottom);
  grad.addColorStop(0, hexA(accent, .34));
  grad.addColorStop(1, hexA(accent, 0));
  ctx.fillStyle = grad; ctx.fill(area);
  ctx.strokeStyle = accent; ctx.lineWidth = 2; ctx.lineJoin = "round"; ctx.stroke(path);

  // olcek etiketi: zirvenin yarisi
  ctx.fillStyle = css.getPropertyValue("--muted").trim();
  ctx.font = `12px ${css.getPropertyValue("--font")}`;
  ctx.textAlign = "right";
  ctx.fillText(`${fmtBytes(peak / 2)}/s`, w - 12, y(peak / 2) - 6);
}
function hexA(hex, a) {
  const m = hex.replace("#", "").match(/.{2}/g);
  if (!m) return hex;
  const [r, g, b] = m.map((x) => parseInt(x, 16));
  return `rgba(${r},${g},${b},${a})`;
}

// ---------- veri dongusu ----------
let ticking = false;
async function tick() {
  if (ticking) return;            // onceki cevap gelmeden yenisini yigma
  ticking = true;
  try {
    const s = await api.get_state();
    state.items = s.items;
    (s.media_requests || []).forEach(handleMediaRequest);
    if ((s.clip_offers || []).length) showClipOffer(s.clip_offers[s.clip_offers.length - 1]);
    (s.rd_events || []).forEach(rdEvent);
    if (typeof onStateExtras === "function") onStateExtras(s);
    state.rdProgress = s.rd_progress || [];
    if (s.update) showUpdate(s.update);
    renderLive();
    (s.torrent_requests || []).forEach((t) => (t.route === "ask" ? askTorrent : openTorrentLocal)(t));
    if (rd.view && Date.now() - rd.lastRefresh > 5000) rdRefresh();
    state.history.push(s.total_speed); state.history.shift();
    const [num, unit] = splitBytes(s.total_speed);
    $("#speedNum").textContent = num;
    $("#speedUnit").textContent = unit + "/s";
    const active = s.items.filter((d) => d.status === "active").length;
    $("#activeCount").textContent = T("active_n", active);
    const eng = $("#engineStatus");
    eng.textContent = s.engine_ok ? "aria2" : T("engine_down");
    eng.classList.toggle("bad", !s.engine_ok);
    $("#bridgeStatus").textContent = T("bridge", s.bridge_port);
    notifyFinished(s.items);
    render();
    drawSpeed();
  } catch (e) {
    console.error(e);
  } finally { ticking = false; }
}

function notifyFinished(items) {
  for (const d of items) {
    const prev = state.known.get(d.id);
    if (prev && prev !== "complete" && d.status === "complete") toast(T("completed", d.filename));
    state.known.set(d.id, d.status);
  }
}

let toastTimer = 0;
function toast(msg, isErr = false, sticky = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
  el.hidden = false;
  clearTimeout(toastTimer);
  if (!sticky) toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}
function toastDone() { const el = $("#toast"); if (el.textContent === T("resolving")) el.hidden = true; }

// ---------- olaylar ----------
function bindEvents() {
  $("#addForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("#addInput");
    const urls = input.value.split(/\s+/).filter(Boolean);
    if (!urls.length) return;
    let ok = 0;
    for (const u of urls) {
      toast(T("resolving"), false, true);    // yavas servislerde (Pixeldrain ~20 sn) cevap gelene kadar kalir
      let r;
      try { r = await slow("add_url", u); } finally { toastDone(); }
      const how = dispatchAdd(r, u, { url: u });   // rd.js: RD sorusu / medya / bulut penceresi
      if (how === "plain") ok++;
      else if (how === "handled") input.value = "";
    }
    if (ok) { input.value = ""; toast(T("added")); tick(); }
  });
  bindMedia();
  bindCloud();
  bindClipboard();

  $("#sidebar").addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-item");
    if (!btn) return;
    if (btn.dataset.view === "rd") { showView(null); showRd(true); return; }
    if (btn.dataset.view) { showRd(false); showView(btn.dataset.view); return; }
    state.filter = btn.dataset.filter;
    showView(null);
    showRd(false);
    render();
  });

  $("#list").addEventListener("click", async (e) => {
    const btn = e.target.closest("button[data-act]");
    if (!btn) return;
    const id = Number(btn.closest(".item").dataset.id);
    const act = btn.dataset.act;
    const calls = {
      "pause": () => api.pause(id),
      "resume": () => api.resume(id),
      "remove": () => api.remove(id, false),
      "delete": () => api.remove(id, true),
      "open": () => api.open_file(id),
      "folder": () => api.open_folder(id),
      "confirm-yes": () => api.confirm(id, true),
      "confirm-no": () => api.confirm(id, false),
      "hash": () => openHash(id),
      "mtools": () => openMediaTools(id),
    };
    if (calls[act]) { await calls[act](); tick(); }
  });
  $("#list").addEventListener("dblclick", (e) => {
    const li = e.target.closest(".item.st-complete");
    if (li && !e.target.closest("button")) api.open_file(Number(li.dataset.id));
  });

  $("#pauseAll").addEventListener("click", () => api.pause_all().then(tick));
  $("#resumeAll").addEventListener("click", () => api.resume_all().then(tick));
  $("#clearFinished").addEventListener("click", () => api.clear_finished().then(tick));
  $("#openDownloads").addEventListener("click", () => api.open_downloads_dir());
  $("#settingsBtn").addEventListener("click", openSettings);
  window.addEventListener("resize", drawSpeed);

  // Ctrl+V: odak bir alanda degilse linki dogrudan kutuya koy
  document.addEventListener("paste", (e) => {
    if (e.target.closest("input, textarea")) return;
    const text = e.clipboardData.getData("text");
    if (text) { $("#addInput").value = text.trim(); $("#addInput").focus(); }
  });
}

// ---------- pano: yapistir butonu, sag tik menusu, pano izleme onerisi ----------
function insertText(el, text) {
  el.focus();
  const a = el.selectionStart ?? el.value.length, b = el.selectionEnd ?? el.value.length;
  el.setRangeText(text, a, b, "end");
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

let clipTimer = 0;
function showClipOffer(url) {
  if ($("#media").open || $("#cloud").open || $("#rdAsk").open || $("#addInput").value.trim() === url) return;
  $("#clipUrl").textContent = url;
  $("#clipUrl").title = url;
  $("#clipOffer").dataset.url = url;
  $("#clipOffer").hidden = false;
  clearTimeout(clipTimer);
  clipTimer = setTimeout(() => { $("#clipOffer").hidden = true; }, 15000);
}

function bindClipboard() {
  $("#pasteBtn").addEventListener("click", async () => {
    const text = (await api.read_clipboard() || "").trim();
    if (!text) { toast(T("clip_empty"), true); return; }
    $("#addInput").value = text;
    $("#addInput").focus();
  });
  $("#clipYes").addEventListener("click", () => {
    const url = $("#clipOffer").dataset.url || "";
    $("#clipOffer").hidden = true;
    if (!url) return;
    $("#addInput").value = url;
    $("#addForm").requestSubmit();
  });
  $("#clipNo").addEventListener("click", () => { $("#clipOffer").hidden = true; });

  // pywebview varsayilan sag tik menusunu kapatiyor: metin alanlarinda kendi menumuz
  const menu = $("#ctxMenu");
  let target = null;
  const hide = () => { menu.hidden = true; target = null; };
  document.addEventListener("contextmenu", (e) => {
    const el = e.target.closest("input[type=text], input[type=number], input:not([type]), textarea");
    if (!el || el.disabled) { hide(); return; }
    e.preventDefault();
    target = el;
    const hasSel = el.selectionStart !== el.selectionEnd;
    menu.querySelector('[data-cmd="cut"]').disabled = !hasSel || el.readOnly;
    menu.querySelector('[data-cmd="copy"]').disabled = !hasSel;
    menu.querySelector('[data-cmd="paste"]').disabled = el.readOnly;
    menu.hidden = false;
    const r = menu.getBoundingClientRect();
    menu.style.left = Math.min(e.clientX, innerWidth - r.width - 4) + "px";
    menu.style.top = Math.min(e.clientY, innerHeight - r.height - 4) + "px";
    // dialog acikken menu ust katmanda kalsin
    const dlg = el.closest("dialog");
    if (dlg && menu.parentNode !== dlg) dlg.appendChild(menu);
    else if (!dlg && menu.parentNode !== document.body) document.body.appendChild(menu);
  });
  menu.addEventListener("mousedown", (e) => e.preventDefault());   // alan secimi kaybolmasin
  menu.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-cmd]");
    if (!b || !target) return;
    const el = target, cmd = b.dataset.cmd;
    hide();
    el.focus();
    if (cmd === "selectAll") el.select();
    else if (cmd === "paste") insertText(el, await api.read_clipboard() || "");
    else { api.own_copy(); document.execCommand(cmd); }
  });
  document.addEventListener("mousedown", (e) => { if (!menu.contains(e.target)) hide(); });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") hide();
    if (e.ctrlKey && /^[cx]$/i.test(e.key)) api.own_copy();   // Kami icinden kopyalanan link sorulmasin
  });
  window.addEventListener("blur", hide);
}

// ---------- medya (yt-dlp) penceresi ----------
const media = { info: null, ctx: null, pending: [], busy: false };
const STD_HEIGHTS = [2160, 1440, 1080, 720, 480, 360];

async function handleMediaRequest(req) {
  if (media.busy || $("#media").open || $("#cloud").open) { media.pending.push(req); return; }
  media.busy = true;
  toast(T("resolving"), false, true);
  try {
    let r;
    try { r = await slow("media_probe", req.url, req.headers || {}); } finally { toastDone(); }
    dispatchAdd(r, req.url, { ...req, headers: req.headers || {} });
  } finally { media.busy = false; }
}

function openMedia(res, ctx) {
  const info = res.media, def = res.defaults || {};
  media.info = info; media.ctx = ctx;
  const form = $("#mediaForm");
  $("#mName").textContent = info.title;
  const thumb = $("#mThumb");
  thumb.hidden = !info.thumbnail; if (info.thumbnail) thumb.src = info.thumbnail;
  const isList = info.kind === "playlist";
  const sub = [];
  if (info.duration) sub.push(fmtEta(info.duration));
  if (info.is_live) sub.push(T("m_live"));
  if (isList) sub.push(T("m_items", info.entries.length));
  $("#mSub").textContent = sub.join(" · ");

  $("#mListBox").hidden = !isList;
  $("#mOnlyRow").hidden = !(isList && info.single_url);
  $("#mOnly").checked = !!(isList && info.single_url);
  $("#mAll").checked = true;
  $("#mEntries").innerHTML = (info.entries || []).map((e, i) =>
    `<li><label><input type="checkbox" data-i="${i}" checked><span>${escapeHtml(e.title)}</span>` +
    `<small>${e.duration ? fmtEta(e.duration) : ""}</small></label></li>`).join("");

  const heights = info.heights && info.heights.length ? info.heights.filter((h) => h >= 144) : STD_HEIGHTS;
  $("#mQuality").innerHTML = `<option value="best">${T("m_best")}</option>` +
    heights.map((h) => `<option value="${h}">${h}p</option>`).join("");
  const q = String(def.quality || "best");
  $("#mQuality").value = [...$("#mQuality").options].some((o) => o.value === q) ? q : "best";
  form.elements.format.value = def.format || "mp4";
  $("#mKbps").value = String(def.audio_kbps || 320);
  form.elements.subs.checked = def.subs !== false;
  form.elements.embed.checked = def.embed !== false;
  form.elements.sponsorblock.value = def.sponsorblock || "mark";
  form.elements.start.value = ""; form.elements.end.value = "";
  syncMedia();
  $("#media").showModal();
}

function syncMedia() {
  const form = $("#mediaForm");
  const mp3 = form.elements.format.value === "mp3";
  $("#mQuality").hidden = mp3; $("#mKbps").hidden = !mp3;
  $("#mSubsRow").hidden = mp3;
  const info = media.info || {};
  const only = $("#mOnly").checked && !$("#mOnlyRow").hidden;
  const list = info.kind === "playlist" && !only;
  $("#mRangeRow").hidden = list;
  $$("#mEntries input, #mAll").forEach((el) => { el.disabled = only; });
  const checked = $$("#mEntries input:checked").length;
  $("#mCount").textContent = info.kind === "playlist" ? `(${checked}/${info.entries.length})` : "";
}

function bindMedia() {
  const form = $("#mediaForm");
  form.addEventListener("change", (e) => {
    if (e.target.id === "mAll") $$("#mEntries input").forEach((el) => { el.checked = e.target.checked; });
    syncMedia();
  });
  $("#media").addEventListener("close", () => {
    const next = media.pending.shift();
    if (next) setTimeout(() => handleMediaRequest(next), 50);
  });
  $("#mGo").addEventListener("click", async () => {
    const info = media.info, ctx = media.ctx || {};
    const only = $("#mOnly").checked && !$("#mOnlyRow").hidden;
    let items;
    if (info.kind !== "playlist") items = [{ url: info.url, title: info.title }];
    else if (only) items = [{ url: info.single_url, title: "" }];
    else items = $$("#mEntries input:checked").map((el) => info.entries[Number(el.dataset.i)]);
    if (!items.length) return;
    const el = form.elements;
    const mp3 = el.format.value === "mp3";
    const opts = {
      format: el.format.value, quality: el.quality.value, audio_kbps: Number(el.audio_kbps.value),
      subs: !mp3 && el.subs.checked, embed: el.embed.checked, sponsorblock: el.sponsorblock.value,
      start: $("#mRangeRow").hidden ? "" : el.start.value.trim(),
      end: $("#mRangeRow").hidden ? "" : el.end.value.trim(),
    };
    const r = await api.add_media(items, opts, ctx.headers || {}, ctx.page_url || "");
    if (!r.ok) { toast(T("err_" + (r.error || "media_unsupported")), true); return; }
    $("#media").close();
    toast(T("added")); tick();
    // son secimler varsayilan olsun (video ustu butondaki hizli MP4/MP3 de bunlari kullanir)
    const remember = { media_format: opts.format, media_audio_kbps: opts.audio_kbps, media_embed: opts.embed,
                       media_sponsorblock: opts.sponsorblock };
    if (!mp3) { remember.media_quality = opts.quality; remember.media_subs = opts.subs; }
    for (const [k, v] of Object.entries(remember)) api.set_setting(k, v);
  });
  $("#media").addEventListener("click", (e) => { if (e.target === $("#media")) $("#media").close(); });
}

// ---------- bulut paylasimi penceresi ----------
const cloud = { data: null };

function openCloud(c) {
  cloud.data = c;
  $("#cName").textContent = c.title;
  const sub = [T("c_files", c.files.length)];
  if (c.total) sub.push(fmtBytes(c.total));
  if (c.note) sub.push(c.note);
  $("#cSub").textContent = sub.join(" · ");
  $("#cAll").checked = true;
  // dosyalar yola gore siralanir; her yeni klasor icin bir baslik satiri
  const order = c.files.map((f, i) => i).sort((a, b) => c.files[a].path.localeCompare(c.files[b].path));
  const seen = new Set(), rows = [];
  for (const i of order) {
    const parts = c.files[i].path.split("/");
    for (let d = 1; d < parts.length; d++) {
      const dir = parts.slice(0, d).join("/");
      if (seen.has(dir)) continue;
      seen.add(dir);
      rows.push(`<li class="c-dir" style="--d:${d - 1}"><label><input type="checkbox" data-dir="${escapeHtml(dir)}" checked>` +
                `<span>📁 ${escapeHtml(parts[d - 1])}</span></label></li>`);
    }
    rows.push(`<li style="--d:${parts.length - 1}"><label><input type="checkbox" data-i="${i}" data-path="${escapeHtml(c.files[i].path)}" checked>` +
              `<span>${escapeHtml(parts[parts.length - 1])}</span><small>${c.files[i].size ? fmtBytes(c.files[i].size) : ""}</small></label></li>`);
  }
  $("#cEntries").innerHTML = rows.join("");
  syncCloud();
  $("#cloud").showModal();
}

function syncCloud() {
  const c = cloud.data; if (!c) return;
  const sel = $$("#cEntries input[data-i]:checked").map((el) => c.files[Number(el.dataset.i)]);
  const size = sel.reduce((a, f) => a + (f.size || 0), 0);
  $("#cCount").textContent = `(${sel.length}/${c.files.length}${size ? " · " + fmtBytes(size) : ""})`;
}

function bindCloud() {
  $("#cloudForm").addEventListener("change", (e) => {
    const t = e.target;
    if (t.id === "cAll") $$("#cEntries input").forEach((el) => { el.checked = t.checked; });
    else if (t.dataset.dir !== undefined) {
      const pre = t.dataset.dir + "/";
      $$("#cEntries input").forEach((el) => {
        const p = el.dataset.path || el.dataset.dir + "/";
        if (p.startsWith(pre)) el.checked = t.checked;
      });
    }
    syncCloud();
  });
  $("#cGo").addEventListener("click", async () => {
    const idx = $$("#cEntries input[data-i]:checked").map((el) => Number(el.dataset.i));
    if (!idx.length) return;
    const btn = $("#cGo"); btn.disabled = true;
    try {
      const r = cloud.data.kind === "torrent" ? await api.torrent_add(cloud.data.token, idx)
                                             : await slow("add_cloud", cloud.data.token, idx);
      if (!r.ok) { toast(T("err_" + (r.error || "cloud_failed")), true); return; }
      $("#cloud").close();
      if (r.failed) toast(T("c_partial", r.ids.length, r.failed), true); else toast(T("added"));
      tick();
    } finally { btn.disabled = false; }
  });
  $("#cloud").addEventListener("close", () => {
    const next = media.pending.shift();
    if (next) setTimeout(() => handleMediaRequest(next), 50);
  });
  $("#cloud").addEventListener("click", (e) => { if (e.target === $("#cloud")) $("#cloud").close(); });
}

// ---------- ayarlar ----------
const LIST_KEYS = new Set(["capture_exclude_hosts", "confirm_extensions"]);

async function openSettings() {
  state.settings = await api.get_settings();
  const form = $("#settingsForm");
  for (const el of form.elements) {
    if (!el.name || !(el.name in state.settings)) continue;
    const v = state.settings[el.name];
    if (el.type === "checkbox") el.checked = !!v;
    else el.value = LIST_KEYS.has(el.name) ? v.join(", ") : v;
  }
  $("#dirPath").textContent = state.settings._effective_download_dir;
  $("#settings").showModal();
  refreshFirewall();
  refreshDesktop();
}

async function refreshFirewall() {
  const r = await api.firewall_status();
  $("#fwState").textContent = T(r.rule ? "s_tor_fw_ok" : "s_tor_fw_no");
  $("#fwAllow").hidden = !!r.rule;
}

function bindSettings() {
  $("#fwAllow").addEventListener("click", async () => {
    await slow("firewall_allow");
    setTimeout(refreshFirewall, 4000); setTimeout(refreshFirewall, 12000);   // UAC onayi sonrasi
  });
  const form = $("#settingsForm");
  form.addEventListener("change", async (e) => {
    const el = e.target;
    if (!el.name) return;
    const value = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
    const r = await api.set_setting(el.name, value);
    if (!r.ok) { toast(T(r.error), true); return; }
    if (el.type === "number") el.value = r.value;
    state.settings[el.name] = r.value;
    syncToolbar();
    if (["hotkey", "hotkey_enabled", "autostart"].includes(el.name)) setTimeout(refreshDesktop, 300);
    if (el.name === "language") { state.lang = r.value; applyI18n(); }
    if (el.name === "theme") applyTheme(r.value);
  });
  $("#dirChange").addEventListener("click", async () => {
    const dir = await api.choose_folder();
    if (dir) { await api.set_setting("download_dir", dir); $("#dirPath").textContent = dir; }
  });
  $("#dirReset").addEventListener("click", async () => {
    await api.set_setting("download_dir", "");
    $("#dirPath").textContent = (await api.get_settings())._effective_download_dir;
  });
  $("#settings").addEventListener("click", (e) => { if (e.target === $("#settings")) $("#settings").close(); });
}

// Ag/uzun isler: Python hemen is kimligi doner (job_start), sonuc job_result ile beklenir -> api cagrisi
// hicbir zaman uzun sure acik kalmaz (defter 24: IPv6 yuzunden 42 sn bekleyen cagrilar).
async function slow(name, ...args) {
  const j = await api.job_start(name, args);
  if (!j || !j.ok) return { ok: false, error: (j && j.error) || "job_failed" };
  for (let wait = 60; ; wait = Math.min(wait * 1.5, 400)) {
    await new Promise((r) => setTimeout(r, wait));
    const r = await api.job_result(j.job);
    if (r.state === "done") return r.result;
    if (r.state === "lost") return { ok: false, error: "job_lost" };
  }
}

// ---------- baslangic ----------
async function init() {
  api = window.pywebview.api;
  state.settings = await api.get_settings();
  state.lang = state.settings.language || "tr";
  applyTheme(state.settings.theme);
  applyI18n();
  bindEvents();
  bindSettings();
  bindRd();
  bindLive();
  bindExtras();
  await tick();
  setInterval(() => { if (!document.hidden) tick(); }, 500);
}

window.addEventListener("pywebviewready", init);
