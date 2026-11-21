// Asama 6a arayuzu: hiz siniri dugmesi, esZamanli indirme, surukle-sirala, surukle-birak, SHA256,
// guncelleme bildirimi, Ayarlar > Uygulama/Zamanlayici/Guvenlik/Hakkinda. app.js ve rd.js'ten sonra yuklenir.
"use strict";

// ---------- arac cubugu: hiz siniri + esZamanli indirme ----------
function syncToolbar() {
  const s = state.settings;
  const lim = Number(s.speed_limit_kib || 0);
  const btn = $("#speedToggle");
  const lbl = lim === 512 ? "Hafif · " : (lim === 2048 ? "Orta · " : "");
  btn.textContent = lim ? lbl + fmtBytes(lim * 1024) + "/s" : T("speed_off");
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
    const steps = [0, 512, 2048];   // Sınırsız -> Hafif -> Orta
    const i = steps.indexOf(lim);
    const next = steps[(i < 0 ? 1 : i + 1) % steps.length];
    await setSetting("speed_limit_kib", next);
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

// Fikir 14: suruklenen medya dosyasi icin onizleme karti (oynat / duzenle / AI)
function showDropPreview(files) {
  const existing = document.getElementById("kmDropPreview");
  if (existing) existing.remove();
  const box = document.createElement("div");
  box.id = "kmDropPreview";
  box.style.cssText = "position:fixed;right:18px;bottom:18px;z-index:70;width:340px;max-height:320px;overflow:auto;background:rgba(16,12,26,.97);border:1px solid var(--ac,#9D6BFF);border-radius:14px;padding:12px;box-shadow:0 16px 40px rgba(0,0,0,.65);font:500 12.5px 'Chakra Petch',sans-serif;color:#EDE9F6";
  const esc = (s) => String(s || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  box.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><b>Dosya Önizleme</b><button data-x type="button" style="border:0;background:none;color:var(--mut,#A39BB5);cursor:pointer;font-size:14px">✕</button></div>` +
    files.map((m, i) => {
      const name = (m.path || "").split(/[\\/]/).pop() || m.path || m.name;
      const isImg = m.kind === "image";
      const isAud = /\.(mp3|flac|wav|m4a|ogg|opus|aac|wma)$/i.test(name);
      return `<div style="display:flex;justify-content:space-between;align-items:center;gap:8px;padding:6px 0;border-top:1px solid rgba(157,107,255,.15)"><span style="overflow:hidden;text-overflow:ellipsis;white-space:nowrap" title="${esc(m.path)}">${esc(name)}</span><span style="display:flex;gap:6px;flex:none">` +
        `<button data-a="play" data-i="${i}" style="border:1px solid var(--ac,#9D6BFF);background:rgba(157,107,255,.15);color:#EDE9F6;border-radius:6px;padding:4px 8px;cursor:pointer">${isImg ? "Görüntüle" : "Oynat"}</button>` +
        `<button data-a="edit" data-i="${i}" style="border:1px solid rgba(157,107,255,.35);background:transparent;color:#EDE9F6;border-radius:6px;padding:4px 8px;cursor:pointer">Düzenle</button>` +
        (isAud ? `<button data-a="ai" data-i="${i}" style="border:1px solid rgba(46,230,166,.5);background:rgba(46,230,166,.12);color:#D1FAE5;border-radius:6px;padding:4px 8px;cursor:pointer">AI Altyazı-Vokal</button>` : "") +
        `</span></div>`;
    }).join("");
  document.body.appendChild(box);
  box.querySelector("[data-x]").onclick = () => box.remove();
  box.onclick = (e) => {
    const b = e.target.closest("button[data-a]");
    if (!b) return;
    const m = files[+b.dataset.i]; const a = b.dataset.a;
    if (a === "play") { api.player_open_path?.(m.path); }
    else if (a === "edit") { api.picture_open?.(m.path, false, true); }
    else if (a === "ai") { api.player_open_path?.(m.path); toast("AI araçları (altyazı/vokal) Player'da erişilebilir"); }
    box.remove();
  };
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
      const mediaFiles = [];
      for (const f of files) {
        const p = f.path || "";
        if (/\.(jpe?g|png|webp|gif|bmp|avif|jfif|heic|tiff?)$/i.test(f.name)) { mediaFiles.push({ path: p || f.name, kind: "image" }); continue; }
        if (/\.(mkv|mp4|m4v|webm|avi|mov|ts|m2ts|wmv|flv|mpg|mpeg|3gp|ogv|mp3|flac|wav|ogg|oga|opus|m4a|aac|wma|ape|aiff|mka|wv)$/i.test(f.name)) { mediaFiles.push({ path: p || f.name, kind: "media" }); continue; }
        if (!/\.torrent$/i.test(f.name) || f.size > 10 * 1024 * 1024) { toast(T("drop_only_torrent"), true); continue; }
        const r = await api.drop_torrent(await fileToB64(f));
        dispatchAdd(r, f.name, {});
      }
      if (mediaFiles.length) showDropPreview(mediaFiles);
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
  if (!await kAsk(T("update_confirm"))) return;
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
  $("#backupExportBtn")?.addEventListener("click", async () => {
    const btn = $("#backupExportBtn"); btn.disabled = true;
    try {
      const r = await slow("backup_export");
      if (r?.cancelled) return;
      toast(r?.ok ? `Yedek alındı (${r.count} öğe)` : `Yedek hatası: ${r?.error || "?"}`, !r?.ok);
    } finally { btn.disabled = false; }
  });
  $("#backupImportBtn")?.addEventListener("click", async () => {
    const btn = $("#backupImportBtn"); btn.disabled = true;
    try {
      const r = await slow("backup_import");
      if (r?.cancelled) return;
      if (!r?.ok) {
        const msg = r?.error === "newer_version"
          ? `Bu yedek daha yeni bir Kami sürümünden (${r.backup_version}). Mevcut (${r.current_version}) açamaz.`
          : `Geri yüklenemedi: ${r?.error || "?"}`;
        await (typeof kAlert === "function" ? kAlert(msg) : toast(msg));
        return;
      }
      const keys = (r.reenter_keys || []).length
        ? `\n\nGüvenlik nedeniyle şu anahtarları yeniden gir:\n- ${r.reenter_keys.join("\n- ")}`
        : "";
      const doneMsg = `Yedek geri yükleme için hazırlandı (${(r.restored || []).length} dosya).\nVeritabanı ve ayarların bozulmadan uygulanması için Kami'yi şimdi kapatıp yeniden aç.${keys}`;
      await (typeof kAlert === "function" ? kAlert(doneMsg) : toast(doneMsg));
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
