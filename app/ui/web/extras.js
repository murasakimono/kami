// Asama 6a arayuzu: hiz siniri dugmesi, esZamanli indirme, surukle-sirala, surukle-birak, SHA256,
// guncelleme bildirimi, Ayarlar > Uygulama/Zamanlayici/Guvenlik/Hakkinda. app.js ve rd.js'ten sonra yuklenir.
"use strict";

// ---------- arac cubugu: hiz siniri + esZamanli indirme ----------
function syncToolbar() {
  const s = state.settings;
  const lim = Number(s.speed_limit_kib || 0);
  const btn = $("#speedToggle");
  btn.textContent = lim ? T("speed_on", fmtBytes(lim * 1024) + "/s") : T("speed_off");
  btn.classList.toggle("on", !!lim);
  const sel = $("#concSel");
  const cur = Number(s.max_concurrent || 3);
  if (!sel.options.length) {
    sel.innerHTML = Array.from({ length: 10 }, (_, i) => `<option value="${i + 1}">${i + 1}</option>`).join("");
  }
  if (cur > 10 && ![...sel.options].some((o) => o.value === String(cur))) sel.add(new Option(String(cur), String(cur)));
  sel.value = String(cur);
}

async function setSetting(k, v) {
  const r = await api.set_setting(k, v);
  if (r.ok) state.settings[k] = r.value; else toast(r.error, true);
  return r;
}

function bindToolbarExtras() {
  $("#speedToggle").addEventListener("click", async () => {
    const lim = Number(state.settings.speed_limit_kib || 0);
    await setSetting("speed_limit_kib", lim ? 0 : Number(state.settings.speed_limit_preset_kib || 2048));
    syncToolbar();
  });
  $("#concSel").addEventListener("change", async (e) => { await setSetting("max_concurrent", Number(e.target.value)); syncToolbar(); });
}

// ---------- rozetler (Defender / SHA256) + SHA256 penceresi ----------
function extraBadges(d) {
  const x = d.extra || {}, out = [];
  if (x.checksum_ok === true) out.push(`<span class="badge ok">SHA256 ✓</span>`);
  else if (x.checksum_ok === false) out.push(`<span class="badge bad">${T("hash_mismatch")}</span>`);
  if (x.scan === "scanning") out.push(`<span class="badge">${T("scan_running")}</span>`);
  else if (x.scan === "clean") out.push(`<span class="badge ok">${T("scan_clean")}</span>`);
  else if (x.scan === "threat") out.push(`<span class="badge bad">${T("scan_threat")}</span>`);
  return out.join("");
}

const hashDlg = { id: 0 };
async function openHash(id) {
  const d = state.items.find((x) => x.id === id);
  hashDlg.id = id;
  $("#hashName").textContent = d ? d.filename : "";
  $("#hashValue").textContent = T("hash_computing");
  $("#hashExpected").value = (d && d.extra && d.extra.checksum) || "";
  $("#hashResult").textContent = "";
  $("#hashDlg").showModal();
  const r = await slow("hash_file", id, "");
  if (hashDlg.id !== id) return;
  if (!r.ok) { $("#hashValue").textContent = T("err_" + r.error); return; }
  $("#hashValue").textContent = r.sha256;
  if (r.expected) showHashResult(r.match);
}
function showHashResult(match) {
  const el = $("#hashResult");
  el.textContent = T(match ? "hash_match" : "hash_mismatch");
  el.style.color = match ? "#4ade80" : "#f87171";
}
function bindHash() {
  $("#hashCheck").addEventListener("click", async () => {
    const v = $("#hashExpected").value.trim();
    if (!v) return;
    const r = await slow("hash_file", hashDlg.id, v);
    if (!r.ok) { $("#hashResult").textContent = T("err_" + r.error); $("#hashResult").style.color = ""; return; }
    $("#hashValue").textContent = r.sha256;
    showHashResult(r.match);
    tick();
  });
  $("#hashCopy").addEventListener("click", () => {
    const v = $("#hashValue").textContent;
    if (/^[0-9a-f]{64}$/.test(v)) { api.own_copy(); navigator.clipboard.writeText(v).then(() => toast(T("copied"))); }
  });
  $("#hashDlg").addEventListener("click", (e) => { if (e.target === $("#hashDlg")) $("#hashDlg").close(); });
}

// ---------- surukle-sirala (liste) ----------
const KAMI_DRAG = "application/x-kami-id";
let dragId = 0;
function bindReorder() {
  const list = $("#list");
  const clear = () => $$(".drop-before, .drop-after", list).forEach((el) => el.classList.remove("drop-before", "drop-after"));
  list.addEventListener("dragstart", (e) => {
    const li = e.target.closest(".item");
    if (!li) return;
    dragId = Number(li.dataset.id);
    e.dataTransfer.setData(KAMI_DRAG, String(dragId));
    e.dataTransfer.effectAllowed = "move";
    li.classList.add("dragging");
  });
  list.addEventListener("dragend", (e) => { e.target.closest(".item")?.classList.remove("dragging"); clear(); dragId = 0; });
  list.addEventListener("dragover", (e) => {
    if (!dragId) return;
    const li = e.target.closest(".item");
    if (!li) return;
    e.preventDefault();
    clear();
    const r = li.getBoundingClientRect();
    li.classList.add(e.clientY < r.top + r.height / 2 ? "drop-before" : "drop-after");
  });
  list.addEventListener("drop", async (e) => {
    if (!dragId) return;
    e.preventDefault();
    const li = e.target.closest(".item");
    const before = li && li.classList.contains("drop-before");
    clear();
    if (!li || Number(li.dataset.id) === dragId) return;
    // gorunen (filtreli) sirayi degistir, sonra tum listedeki yerlerine yerlestir
    const visible = state.items.filter((d) => matches(d, state.filter)).map((d) => d.id).filter((id) => id !== dragId);
    let at = visible.indexOf(Number(li.dataset.id));
    if (!before) at += 1;
    visible.splice(at, 0, dragId);
    const slots = state.items.map((d, i) => (matches(d, state.filter) ? i : -1)).filter((i) => i >= 0);
    const full = state.items.map((d) => d.id);
    slots.forEach((slot, k) => { full[slot] = visible[k]; });
    const byId = new Map(state.items.map((d) => [d.id, d]));
    state.items = full.map((id) => byId.get(id));
    render();
    await api.reorder(full);
    tick();
  });
}

// ---------- surukle-birak (disaridan link / .torrent) ----------
function isExternal(e) {
  const t = [...(e.dataTransfer?.types || [])];
  return !t.includes(KAMI_DRAG) && (t.includes("Files") || t.includes("text/uri-list") || t.includes("text/plain"));
}
function fileToB64(file) {
  return new Promise((res, rej) => {
    const fr = new FileReader();
    fr.onload = () => res(String(fr.result).split(",", 2)[1] || "");
    fr.onerror = rej;
    fr.readAsDataURL(file);
  });
}
function bindDrop() {
  let depth = 0;
  const veil = $("#dropVeil");
  document.addEventListener("dragenter", (e) => { if (!isExternal(e)) return; depth++; veil.hidden = false; });
  document.addEventListener("dragleave", (e) => { if (!isExternal(e)) return; if (--depth <= 0) { depth = 0; veil.hidden = true; } });
  document.addEventListener("dragover", (e) => { if (isExternal(e)) e.preventDefault(); });
  document.addEventListener("drop", async (e) => {
    if (!isExternal(e)) return;
    e.preventDefault();
    depth = 0; veil.hidden = true;
    const files = [...(e.dataTransfer.files || [])];
    if (files.length) {
      for (const f of files) {
        if (!/\.torrent$/i.test(f.name) || f.size > 10 * 1024 * 1024) { toast(T("drop_only_torrent"), true); continue; }
        const r = await api.drop_torrent(await fileToB64(f));
        dispatchAdd(r, f.name, {});
      }
      return;
    }
    const text = (e.dataTransfer.getData("text/uri-list") || e.dataTransfer.getData("text/plain") || "")
      .split(/\r?\n/).map((x) => x.trim()).filter((x) => x && !x.startsWith("#"));
    if (!text.length) return;
    $("#addInput").value = text.join(" ");
    $("#addForm").requestSubmit();
  });
}

// ---------- guncelleme ----------
function showUpdate(u) {
  if (!u || !u.version) return;
  const a = $("#updateLink");
  a.textContent = T("update_avail", u.version) + (u.asset ? " · " + T("update_install") : "");
  a.hidden = false;
  a.dataset.install = u.asset ? "1" : "";
  toast(T("update_avail", u.version));
}

async function installUpdate() {
  if (!confirm(T("update_confirm"))) return;
  toast(T("update_downloading"), false, true);
  let r;
  try { r = await slow("install_update"); } finally { toastDone(); }
  toast(r.ok ? T("update_started") : T("update_err") + (r.detail ? ` (${r.detail})` : ""), !r.ok);
}

// ---------- Ayarlar ek parcalari ----------
async function refreshDesktop() {
  const r = await api.desktop_status();
  $("#appVersion").textContent = r.version;
  $("#defenderState").hidden = !!r.defender;
  const hk = $("#hotkeyState");
  hk.hidden = !r.hotkey_error;
  hk.textContent = r.hotkey_error ? T("hotkey_" + r.hotkey_error) : "";
  hk.style.color = "#f87171";
  const auto = $('#settingsForm [name="autostart"]');
  if (auto) auto.checked = !!r.autostart;
}

function bindAppSettings() {
  $("#updateNow").addEventListener("click", async () => {
    $("#updateState").textContent = T("update_checking");
    const r = await slow("check_update");
    if (!r.ok) $("#updateState").textContent = T("update_err");
    else if (r.available) { $("#updateState").textContent = T("update_avail", r.version); showUpdate(r); }
    else $("#updateState").textContent = r.none ? T("update_none_yet") : T("update_latest");
  });
  $("#updateLink").addEventListener("click", () => ($("#updateLink").dataset.install ? installUpdate() : api.open_release()));
  $("#reportBtn").addEventListener("click", async () => {
    const btn = $("#reportBtn"); btn.disabled = true;
    try {
      const r = await slow("make_report");
      toast(r.ok ? T("report_done") : T("report_err"), !r.ok);
    } finally { btn.disabled = false; }
  });
}

function bindExtras() {
  bindToolbarExtras();
  bindHash();
  bindReorder();
  bindDrop();
  bindAppSettings();
  syncToolbar();
}
