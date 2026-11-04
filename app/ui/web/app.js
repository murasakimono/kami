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
             b("remove", ICONS.remove, T("remove")) + b("delete", ICONS.trash, T("remove_file"), "danger");
    default:
      return b("remove", ICONS.remove, T("remove"), "danger");
  }
}

function metaFor(d) {
  const parts = [];
  const st = `<span class="st-${d.status}">${d.status === "error" && d.error ? `${T("st_error")}: ${escapeHtml(d.error)}` : d.status === "confirm" ? T("confirm_q") : T("st_" + d.status)}</span>`;
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
  return parts.join("");
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}

const CAT_VAR = { video: "#7C8CF8", music: "#E07BB5", archive: "#D9A54C", program: "#67C08A", document: "#8FA3B8", torrent: "#B48CF2" };

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
      li.innerHTML = `<div class="ficon"></div><div class="name"></div><div class="actions"></div><div class="meta"></div><div class="bar"><i></i></div>`;
    }
    const sig = `${d.status}|${d.filename}|${d.downloaded}|${d.size}|${d.speed}|${d.connections}|${d.error}`;
    if (li.dataset.sig !== sig) {
      li.className = `item st-${d.status}`;
      const name = d.filename || d.url;
      const nameEl = $(".name", li);
      nameEl.textContent = name;
      nameEl.title = d.path || d.url;
      $(".ficon", li).style.setProperty("--cat", CAT_VAR[d.category] || "var(--muted)");
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
async function tick() {
  try {
    const s = await api.get_state();
    state.items = s.items;
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
  }
}

function notifyFinished(items) {
  for (const d of items) {
    const prev = state.known.get(d.id);
    if (prev && prev !== "complete" && d.status === "complete") toast(T("completed", d.filename));
    state.known.set(d.id, d.status);
  }
}

let toastTimer = 0;
function toast(msg, isErr = false) {
  const el = $("#toast");
  el.textContent = msg;
  el.classList.toggle("err", isErr);
  el.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => { el.hidden = true; }, 3500);
}

// ---------- olaylar ----------
function bindEvents() {
  $("#addForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const input = $("#addInput");
    const urls = input.value.split(/\s+/).filter(Boolean);
    if (!urls.length) return;
    let ok = 0;
    for (const u of urls) {
      const r = await api.add_url(u);
      if (r.ok) ok++; else toast(T("err_" + r.error), true);
    }
    if (ok) { input.value = ""; toast(T("added")); tick(); }
  });

  $("#sidebar").addEventListener("click", (e) => {
    const btn = e.target.closest(".nav-item");
    if (!btn) return;
    $$(".nav-item").forEach((b) => b.classList.toggle("active", b === btn));
    state.filter = btn.dataset.filter;
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
}

function bindSettings() {
  const form = $("#settingsForm");
  form.addEventListener("change", async (e) => {
    const el = e.target;
    if (!el.name) return;
    const value = el.type === "checkbox" ? el.checked : el.type === "number" ? Number(el.value) : el.value;
    const r = await api.set_setting(el.name, value);
    if (!r.ok) { toast(r.error, true); return; }
    if (el.type === "number") el.value = r.value;
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

// ---------- baslangic ----------
async function init() {
  api = window.pywebview.api;
  state.settings = await api.get_settings();
  state.lang = state.settings.language || "tr";
  applyTheme(state.settings.theme);
  applyI18n();
  bindEvents();
  bindSettings();
  await tick();
  setInterval(() => { if (!document.hidden) tick(); }, 500);
}

window.addEventListener("pywebviewready", init);
