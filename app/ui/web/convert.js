// Donusturucu: dosya sec / surukle-birak / Gezgin sag tik / indirilenlerden -> format sec -> donustur.
"use strict";

const CV = { files: [], target: "", quality: "normal", height: 0, maxw: 0, strip: true, timer: null, office: null };
const cvL = (tr, en) => (state.lang !== "en" ? tr : en);
const CV_LABEL = {
  "pdf:compress": () => cvL("PDF küçült", "Compress PDF"), "pdf:split": () => cvL("Sayfalara böl", "Split pages"),
  "pdf:merge": () => cvL("Tek PDF'te birleştir", "Merge into one PDF"), "pdf:images": () => cvL("Tek PDF yap", "Make one PDF"),
  "meta:strip": () => cvL("Metadata temizle", "Strip metadata"),
};
const CV_KIND = { image: ["Görsel", "Image"], audio: ["Ses", "Audio"], video: ["Video", "Video"], pdf: ["PDF", "PDF"], office: ["Belge", "Document"], other: ["Diğer", "Other"] };
const CV_OFFICE_T = new Set(["docx", "odt", "rtf", "html", "xlsx", "ods", "csv", "pptx", "odp"]);
const cvLabel = (t) => (CV_LABEL[t] ? CV_LABEL[t]() : t.toUpperCase());

function cvTargets() {
  if (!CV.files.length) return [];
  let t = CV.files[0].targets.slice();
  for (const f of CV.files.slice(1)) t = t.filter((x) => f.targets.includes(x));
  const kinds = new Set(CV.files.map((f) => f.kind));
  if (CV.files.length > 1 && kinds.size === 1 && kinds.has("image")) t.unshift("pdf:images");
  if (CV.files.length > 1 && kinds.size === 1 && kinds.has("pdf")) t = t.filter((x) => x !== "pdf:merge").concat("pdf:merge");
  else t = t.filter((x) => x !== "pdf:merge");
  return t;
}

function cvSeg(key, opts, cur) {
  return `<div class="cv-seg" data-k="${key}">${opts.map(([v, l]) => `<button type="button" data-v="${v}" class="${String(cur) === String(v) ? "on" : ""}">${l}</button>`).join("")}</div>`;
}

function cvRender() {
  const root = $("#convertView"); if (!root) return;
  const ts = cvTargets();
  if (CV.target && !ts.includes(CV.target)) CV.target = "";
  const kinds = new Set(CV.files.map((f) => f.kind));
  const needsOffice = CV.target && (CV_OFFICE_T.has(CV.target) || kinds.has("office") || (kinds.has("pdf") && CV.target === "docx"));
  root.innerHTML = `
    <div class="rd-head"><h2>${cvL("Dönüştürücü", "Converter")}</h2><span class="hint">${cvL("Reklamsız, internetsiz. Çıktı dosyanın yanına kaydedilir; aslına dokunulmaz.", "No ads, offline. Output is saved next to the file; the original is untouched.")}</span></div>
    <div class="cv-drop" id="cvDrop">
      ${CV.files.length ? `<ul class="cv-files">${CV.files.map((f, i) => `<li><b>${cvL(...CV_KIND[f.kind])}</b><span title="${escapeHtml(f.path)}">${escapeHtml(f.name)}</span><small>${fmtBytes(f.size)}</small><button type="button" class="cv-x" data-i="${i}" aria-label="${cvL("çıkar", "remove")}">✕</button></li>`).join("")}</ul>` : `<p class="cv-empty">${cvL("Dosyaları buraya bırak", "Drop files here")}<br><small>${cvL("ya da Gezgin'de sağ tık → Kami ile dönüştür", "or right-click in Explorer → Kami ile dönüştür")}</small></p>`}
      <div class="cv-drop-btns"><button type="button" class="btn ghost" id="cvPick">${cvL("Dosya seç", "Choose files")}</button>${CV.files.length ? `<button type="button" class="btn ghost" id="cvClearFiles">${cvL("Listeyi temizle", "Clear list")}</button>` : ""}</div>
    </div>
    ${CV.files.length ? (ts.length ? `<h3 class="cv-h">${cvL("Neye dönüşsün?", "Convert to")}</h3>
      <div class="cv-targets">${ts.map((t) => `<button type="button" class="cv-t ${t === CV.target ? "on" : ""} ${t.includes(":") ? "tool" : ""}" data-t="${t}">${cvLabel(t)}</button>`).join("")}</div>`
      : `<p class="hint">${cvL("Seçili dosyaların ortak bir çıktı formatı yok; aynı türden dosyaları birlikte seç.", "The selected files share no output format; select files of the same kind.")}</p>`) : ""}
    ${CV.target ? `<div class="cv-opts">
      ${CV.target !== "meta:strip" && CV.target !== "pdf:split" && CV.target !== "pdf:merge" ? `<label>${cvL("Kalite", "Quality")}</label>${cvSeg("quality", [["high", cvL("Yüksek", "High")], ["normal", "Normal"], ["small", cvL("Küçük dosya", "Small file")]], CV.quality)}` : ""}
      ${kinds.has("video") && !["mp3", "flac", "wav", "m4a", "opus", "ogg", "meta:strip"].includes(CV.target) ? `<label>${cvL("Çözünürlük", "Resolution")}</label>${cvSeg("height", [[0, cvL("Aynı", "Same")], [1080, "1080p"], [720, "720p"], [480, "480p"]], CV.height)}` : ""}
      ${kinds.has("image") && !["meta:strip", "pdf:images"].includes(CV.target) ? `<label>${cvL("En fazla genişlik", "Max width")}</label>${cvSeg("maxw", [[0, cvL("Aynı", "Same")], [3840, "4K"], [1920, "1920"], [1280, "1280"], [800, "800"]], CV.maxw)}
        <label>${cvL("Konum / kamera bilgisi", "Location / camera info")}</label>${cvSeg("strip", [[1, cvL("Sil", "Remove")], [0, cvL("Koru", "Keep")]], CV.strip ? 1 : 0)}` : ""}
    </div>
    ${needsOffice && CV.office === false ? `<div class="cv-warn">${cvL("Bu dönüşüm için LibreOffice gerekiyor (ücretsiz, ~350 MB).", "This needs LibreOffice (free, ~350 MB).")} <button type="button" class="btn ghost" id="cvOffice">${cvL("LibreOffice'i kur", "Install LibreOffice")}</button></div>` : ""}
    <div class="cv-go"><button type="button" class="btn primary" id="cvGo">${cvL("Dönüştür", "Convert")} · ${CV.files.length} ${cvL("dosya", "file(s)")} → ${cvLabel(CV.target)}</button></div>` : ""}
    <div id="cvJobs"></div>`;
}

function cvRenderJobs(jobs) {
  const box = $("#cvJobs"); if (!box) return;
  if (!jobs.length) { box.innerHTML = ""; return; }
  const run = jobs.some((j) => j.state === "running" || j.state === "queued");
  const err = (e) => ({ cancelled: cvL("iptal edildi", "cancelled"), libreoffice_yok: cvL("LibreOffice kurulu değil", "LibreOffice missing"), zaten_kucuk: cvL("zaten olabildiğince küçük", "already as small as it gets"), desteklenmiyor: cvL("bu dönüşüm desteklenmiyor", "unsupported") }[e] || e);
  box.innerHTML = `<div class="rd-head"><h3 class="cv-h">${cvL("İşler", "Jobs")}</h3><span class="spacer"></span>
      ${run ? `<button type="button" class="btn ghost danger" id="cvCancel">${cvL("Hepsini iptal et", "Cancel all")}</button>` : `<button type="button" class="btn ghost" id="cvClearJobs">${cvL("Temizle", "Clear")}</button>`}</div>
    <ul class="cv-jobs">${jobs.map((j) => `<li class="${j.state}"><span class="cv-jn">${escapeHtml(j.name)} → ${cvLabel(j.target)}</span>
      ${j.state === "done" ? `<button type="button" class="btn ghost cv-show" data-id="${j.id}">${cvL("Göster", "Show")}</button>` : j.state === "error" ? `<em>${escapeHtml(err(j.error))}</em>` : `<span class="cv-bar"><i style="width:${Math.round(j.p * 100)}%"></i></span><small>${j.state === "queued" ? cvL("sırada", "queued") : Math.round(j.p * 100) + "%"}</small>`}</li>`).join("")}</ul>`;
}

async function cvPoll() {
  clearTimeout(CV.timer);
  let jobs = [];
  try { jobs = await api.convert_status(); } catch { /* yok */ }
  cvRenderJobs(jobs || []);
  if ((jobs || []).some((j) => j.state === "running" || j.state === "queued")) CV.timer = setTimeout(cvPoll, 700);
}

function cvAdd(list) {
  for (const f of list || []) if (!CV.files.some((x) => x.path === f.path)) CV.files.push(f);
  cvRender();
}

async function cvOpen(withFiles) {
  if (!$(".main").dataset.view || $(".main").dataset.view !== "convert") skDock("convert");
  if (withFiles) cvAdd(withFiles);
}

VIEW_OPEN.convert = async () => {
  api.convert_view(true);
  if (CV.office === null) { try { CV.office = !!(await api.convert_tools()).libreoffice; } catch { CV.office = false; } }
  cvRender(); cvPoll();
};
const _cvShowView = showView;
showView = function (name) {   // eslint-disable-line no-global-assign
  if (name !== "convert") api.convert_view(false);
  return _cvShowView(name);
};
const _cvClose = skCloseDrawer;
skCloseDrawer = function () { api.convert_view(false); return _cvClose(); };   // eslint-disable-line no-global-assign

document.addEventListener("click", async (e) => {
  if (!e.target.closest?.("#convertView")) return;
  const b = e.target.closest("button"); if (!b) return;
  if (b.id === "cvPick") { cvAdd(await api.convert_pick()); return; }
  if (b.id === "cvClearFiles") { CV.files = []; CV.target = ""; cvRender(); return; }
  if (b.classList.contains("cv-x")) { CV.files.splice(+b.dataset.i, 1); cvRender(); return; }
  if (b.classList.contains("cv-t")) { CV.target = b.dataset.t; cvRender(); return; }
  const seg = b.closest(".cv-seg");
  if (seg) { const k = seg.dataset.k, v = b.dataset.v; CV[k] = k === "quality" ? v : k === "strip" ? v === "1" : +v; cvRender(); return; }
  if (b.id === "cvOffice") { await api.convert_install_office(); toast(cvL("Kurulum penceresi açıldı; bitince tekrar dene", "Installer opened; try again when done")); CV.office = null; return; }
  if (b.id === "cvGo") {
    if (CV_OFFICE_T.has(CV.target) || CV.files.some((f) => f.kind === "office")) { try { CV.office = !!(await api.convert_tools()).libreoffice; } catch { /* yok */ } }
    const r = await api.convert_start(CV.files.map((f) => f.path), CV.target, { quality: CV.quality, height: CV.height, max_width: CV.maxw, strip: CV.strip });
    if (!r?.ok) { toast(cvL("Başlatılamadı: ", "Could not start: ") + (r?.error || "?"), true); return; }
    cvPoll(); return;
  }
  if (b.id === "cvCancel") { await api.convert_cancel(); setTimeout(cvPoll, 400); return; }
  if (b.id === "cvClearJobs") { await api.convert_clear(); cvPoll(); return; }
  if (b.classList.contains("cv-show")) { api.convert_reveal(b.dataset.id); }
});

// Gezgin sag tik / surukle-birak (Python tam yolu kuyruga koyar): her 1.5 sn bak
setInterval(async () => {
  let got = [];
  try { got = await api.convert_inbox(); } catch { return; }
  if (got && got.length) cvOpen(got);
}, 1500);

// indirilenler: biten dosyada "Donustur"
const _cvBar = skRenderBar;
skRenderBar = function (d) {   // eslint-disable-line no-global-assign
  _cvBar(d);
  if (!d || d.status !== "complete" || !d.path) return;
  const rm = $('#skBar [data-act="remove"]');
  const btn = document.createElement("button");
  btn.className = "sk-btn"; btn.dataset.cv = "1";
  btn.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 8h13l-3-3M20 16H7l3 3"/></svg>${cvL("Dönüştür", "Convert")}`;
  btn.onclick = async (ev) => { ev.stopPropagation(); cvOpen(await api.convert_info([d.path])); };
  rm ? rm.before(btn) : $("#skBar").appendChild(btn);
};

// Ctrl+K paleti: indirilen dosyalar + ozellikler
window.KPAL = window.KPAL || [];
window.KPAL.push(() => {
  const its = (typeof skItems === "function" ? skItems() : state.items || []).slice(0, 400);
  const kind = { video: "🎬", music: "🎵", program: "⚙", archive: "🗜", document: "📄" };
  const out = [];
  for (const d of its) {
    const name = d.filename || d.url;
    out.push({ ic: kind[d.category] || "📁", t: name, sub: cvL("indirme · seç", "download · select"), run: () => { skCloseDrawer?.(); SK.sel = d.id; SK.multi?.clear(); skRender(); } });
    if (d.status === "complete" && ["video", "music"].includes(d.category)) out.push({ ic: "▶", t: cvL("Oynat: ", "Play: ") + name, sub: "Kami Player", run: () => playerOpen(d.id) });
  }
  const feat = [["⇄", cvL("Dönüştürücü", "Converter"), "convert"], ["⚡", "Real-Debrid", "rd"], ["👁", cvL("Takip", "Follow"), "follow"], ["🕘", cvL("Geçmiş", "History"), "history"], ["▦", cvL("Toplu indirme", "Batch download"), "batch"], ["📚", cvL("Kütüphane (Kami Player)", "Library (Kami Player)"), "library"], ["✦", cvL("AI altyazı / vokal ayır", "AI subtitles / vocals"), "ai"], ["⚙", cvL("Ayarlar", "Settings"), "settings"]];
  return feat.map(([ic, t, k]) => ({ ic, t, sub: cvL("özellik", "feature"), run: () => skDock(k) })).concat(out);
});

// guncelleme: Sunak ust satirinda gorunur hap (eski #updateLink Sunak'ta gizli kaliyordu)
const _cvShowUpdate = typeof showUpdate === "function" ? showUpdate : null;
showUpdate = function (u) {   // eslint-disable-line no-global-assign
  _cvShowUpdate?.(u);
  if (!u || !u.version) return;
  const st = $("#sunak .sk-status"); if (!st || $("#skUpd")) return;
  const b = document.createElement("button");
  b.id = "skUpd"; b.className = "sk-upd";
  b.innerHTML = `${cvL("Yeni sürüm", "New version")} <b>${escapeHtml(u.version)}</b> · ${u.asset ? cvL("Kur", "Install") : cvL("Gör", "View")}`;
  b.onclick = () => (u.asset ? installUpdate() : api.open_release());
  st.prepend(b);
};
