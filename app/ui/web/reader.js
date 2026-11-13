// Kami Reader: manga / cizgi roman / PDF. Tek-cift sayfa, dikey (webtoon), sagdan sola, gece modu,
// PDF'de secip vurgulama + not, arama, icindekiler, yer imleri, Piper ile sesli okuma.
"use strict";
const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
let api = null, LANG = "tr";
const L = (tr, en) => (LANG === "en" ? en : tr);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
function toast(t) { const el = document.createElement("div"); el.className = "toast"; el.textContent = t; document.body.appendChild(el); setTimeout(() => el.remove(), 2600); }
function i18n() { $$("[data-tr]").forEach((e) => (e.textContent = L(e.dataset.tr, e.dataset.en))); }

const RD = {
  doc: null, page: 0, cache: new Map(), st: null, tab: "hl", dirty: false, ratio: 1.414,
  set: { mode: "single", rtl: false, fit: "height", night: false },
};
const pdf = () => RD.doc?.kind === "pdf";

// ---------------------------------------------------------------- kitaplik
async function home() {
  closeDoc();
  $("#rd").hidden = true; $("#rdHome").hidden = false;
  const list = (await api.reader_recent()) || [];
  const sh = $("#rhShelf");
  if (!list.length) { sh.innerHTML = `<p class="rh-empty">${L("Henüz bir şey okumadın. Bir PDF ya da .cbz dosyasını buraya sürükle.", "Nothing read yet. Drag a PDF or .cbz here.")}</p>`; return; }
  sh.innerHTML = list.map((b, k) => {
    const p = b.count ? Math.round(((b.page + 1) / b.count) * 100) : 0;
    return `<div class="rh-book" data-path="${esc(b.path)}"><div class="rh-cover" id="cv${k}" style="--p:${p}%">${b.hl ? `<i>${b.hl} ✎</i>` : ""}</div>
      <b>${esc(b.title)}</b><small>${b.count ? `${b.page + 1}/${b.count} · %${p}` : ""}</small></div>`;
  }).join("");
  // kapaklar: her belgenin ilk sayfasi (sirayla, arayuzu bogmadan)
  for (let k = 0; k < Math.min(list.length, 24); k++) {
    if (!$("#rd").hidden) break;
    const t = await api.reader_cover(list[k].path);
    const el = $("#cv" + k); if (el && t) el.style.backgroundImage = `url("${t}")`;
  }
}

// ---------------------------------------------------------------- belge
async function openDoc(path) {
  const r = await api.reader_open(path);
  if (!r?.ok) { toast(L("Açılamadı: ", "Could not open: ") + (r?.error || "")); return; }
  stopTts();
  RD.doc = r; RD.cache.clear(); RD.st = r.state || {}; RD.st.hl ||= []; RD.st.marks ||= [];
  RD.set = Object.assign({ mode: "single", rtl: false, fit: "height", night: false }, RD.st.settings || {}); RD.zoom = 1;
  RD.page = Math.min(RD.st.page || 0, r.count - 1);
  document.body.classList.toggle("pdf", pdf()); document.body.classList.toggle("comic", !pdf());
  $("#rdHome").hidden = true; $("#rd").hidden = false;
  $("#rdTitle").textContent = r.title; document.title = r.title + " — Kami Reader";
  $("#rdSlider").max = r.count;
  applySet(); buildRail(); render(); renderTab();
}
function closeDoc() { saveNow(); RD.doc = null; RD.cache.clear(); }

function applySet() {
  const s = RD.set;
  $$("#rdMode button").forEach((b) => b.classList.toggle("on", b.dataset.mode === s.mode));
  $("#rdStage").classList.toggle("scroll", s.mode === "scroll");
  $("#rdStage").classList.toggle("rtl", !!s.rtl && s.mode !== "scroll");
  document.body.classList.toggle("rtl", !!s.rtl);
  document.body.classList.toggle("night", !!s.night);
  $("#rdNight").classList.toggle("on", !!s.night);
  $("#rdDir").textContent = s.rtl ? "⇠ " + L("Sağdan sola", "Right to left") : "⇢ " + L("Soldan sağa", "Left to right");
  $("#rdFit").textContent = s.fit === "width" ? "↔ " + L("Genişliğe sığdır", "Fit width") : "▭ " + L("Sayfaya sığdır", "Fit page");
}
function saveSet() { RD.st.settings = RD.set; dirty(); applySet(); render(); }
function dirty() { RD.dirty = true; clearTimeout(RD._sv); RD._sv = setTimeout(saveNow, 800); }
function saveNow() { if (RD.doc && RD.dirty) { RD.dirty = false; RD.st.page = RD.page; api.reader_save(RD.st); } }

async function pageData(i, width) {
  const key = i + ":" + width;
  if (RD.cache.has(key)) return RD.cache.get(key);
  const p = api.reader_page(i, width, pdf());
  RD.cache.set(key, p);
  if (RD.cache.size > 40) RD.cache.delete(RD.cache.keys().next().value);
  const r = await p;
  if (r?.ok && r.w) RD.ratio = r.h / r.w;
  return r;
}

function spreadPages() {
  const n = RD.doc.count, i = RD.page;
  if (RD.set.mode !== "double") return [i];
  if (i === 0) return [0];                 // kapak tek
  const a = i % 2 === 1 ? i : i - 1;       // 1-2, 3-4, ...
  return a + 1 < n ? [a, a + 1] : [a];
}

function boxSize(pages) {
  const st = $("#rdStage"), W = st.clientWidth - 24, H = st.clientHeight - 28;
  const per = pages.length;
  const z = RD.zoom || 1;
  if (RD.set.mode === "scroll") return { w: Math.round(Math.min(W, pdf() ? 1100 : 900) * z) };
  if (RD.set.fit === "width") return { w: Math.round((Math.floor(W / per) - 2) * z) };
  return { w: Math.round(Math.floor(Math.min(W / per - 2, H / RD.ratio)) * z) };   // sayfanin tamami gorunur
}

async function render() {
  if (!RD.doc) return;
  const sp = $("#rdSpread");
  if (RD.set.mode === "scroll") return renderScroll();
  const pages = spreadPages();
  const { w } = boxSize(pages);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  const tok = (RD._tok = (RD._tok || 0) + 1);
  sp.innerHTML = pages.map((i) => `<div class="rd-page" data-i="${i}" style="width:${w}px;height:${Math.round(w * RD.ratio)}px"><div class="ld">${i + 1}</div></div>`).join("");
  $("#rdStage").scrollTop = 0;
  for (const i of pages) {
    const r = await pageData(i, Math.round(w * dpr));
    if (tok !== RD._tok) return;
    const el = sp.querySelector(`.rd-page[data-i="${i}"]`);
    if (el && r?.ok) fillPage(el, r, w);
  }
  updateUi();
  // onden yukle
  const nx = pages[pages.length - 1] + 1;
  for (const k of [nx, nx + 1]) if (k < RD.doc.count) pageData(k, Math.round(w * dpr));
}

function fillPage(el, r, w) {
  const h = Math.round(w * (r.h / r.w));
  el.style.width = w + "px"; el.style.height = h + "px";
  el.innerHTML = `<img src="${r.src}" alt="" draggable="false">` + (pdf() ? `<div class="rd-hl"></div><div class="rd-text"></div>` : "");
  if (pdf() && r.words) {
    const tl = el.querySelector(".rd-text");
    tl.innerHTML = r.words.map(([t, x0, y0, x1, y1]) => {
      const fh = (y1 - y0) * h;
      return `<span style="left:${(x0 * 100).toFixed(3)}%;top:${(y0 * 100).toFixed(3)}%;font-size:${fh.toFixed(1)}px;height:${fh.toFixed(1)}px" data-w="${((x1 - x0) * w).toFixed(1)}">${esc(t)} </span>`;
    }).join("");
    // her kelimeyi kendi kutusunun genisligine esitle (secim dogru otursun)
    tl.querySelectorAll("span").forEach((s) => { const tw = s.getBoundingClientRect().width; if (tw > 0) s.style.transform = `scaleX(${(+s.dataset.w / tw).toFixed(3)})`; });
    drawHl(el);
  }
}

function drawHl(el) {
  const i = +el.dataset.i, box = el.querySelector(".rd-hl"); if (!box) return;
  const items = RD.st.hl.filter((h) => h.page === i);
  let html = items.map((h) => h.rects.map((r, k) => `<i class="${h.color}${k === h.rects.length - 1 && h.note ? " note" : ""}" data-id="${h.id}" style="left:${r[0] * 100}%;top:${r[1] * 100}%;width:${(r[2] - r[0]) * 100}%;height:${(r[3] - r[1]) * 100}%" title="${esc(h.note || "")}"></i>`).join("")).join("");
  (RD.marks?.[i] || []).forEach((r) => { html += `<i class="${r.cls}" style="left:${r.x0 * 100}%;top:${r.y0 * 100}%;width:${(r.x1 - r.x0) * 100}%;height:${(r.y1 - r.y0) * 100}%"></i>`; });
  box.innerHTML = html;
}
function redrawHl() { $$(".rd-page").forEach(drawHl); }

// dikey (webtoon / uzun PDF): tum sayfalar alt alta, gorunur olanlar yuklenir
function renderScroll() {
  const sp = $("#rdSpread"), { w } = boxSize([0]);
  const dpr = Math.min(2, window.devicePixelRatio || 1);
  sp.innerHTML = Array.from({ length: RD.doc.count }, (_, i) => `<div class="rd-page" data-i="${i}" style="width:${w}px;height:${Math.round(w * RD.ratio)}px"><div class="ld">${i + 1}</div></div>`).join("");
  RD._io?.disconnect();
  RD._io = new IntersectionObserver((ents) => ents.forEach(async (e) => {
    if (!e.isIntersecting || e.target.dataset.done) return;
    e.target.dataset.done = 1;
    const i = +e.target.dataset.i, r = await pageData(i, Math.round(w * dpr));
    if (r?.ok) fillPage(e.target, r, w);
  }), { root: $("#rdStage"), rootMargin: "1200px 0px" });
  sp.querySelectorAll(".rd-page").forEach((p) => RD._io.observe(p));
  requestAnimationFrame(() => { sp.querySelector(`.rd-page[data-i="${RD.page}"]`)?.scrollIntoView(); updateUi(); });
}
$("#rdStage").addEventListener("scroll", () => {
  if (RD.set.mode !== "scroll" || !RD.doc) return;
  const st = $("#rdStage"), mid = st.scrollTop + st.clientHeight / 3;
  const el = [...$$(".rd-page")].find((p) => p.offsetTop + p.offsetHeight > mid);
  if (el && +el.dataset.i !== RD.page) { RD.page = +el.dataset.i; updateUi(); dirty(); }
}, { passive: true });

function go(i) {
  if (!RD.doc) return;
  i = Math.max(0, Math.min(RD.doc.count - 1, i));
  if (RD.set.mode === "scroll") { RD.page = i; $(`.rd-page[data-i="${i}"]`)?.scrollIntoView(); updateUi(); dirty(); return; }
  if (i === RD.page) return;
  RD.page = i; dirty(); render();
}
function step(d) {   // d: +1 ileri / -1 geri (okuma yonune gore)
  if (!RD.doc) return;
  if (RD.set.mode === "scroll") { $("#rdStage").scrollBy({ top: d * $("#rdStage").clientHeight * 0.85, behavior: "smooth" }); return; }
  const pages = spreadPages();
  if (RD.set.mode === "double") go(d > 0 ? pages[pages.length - 1] + 1 : (pages[0] <= 1 ? 0 : pages[0] - 2));
  else {
    const st = $("#rdStage");   // genislige sigdirmada once sayfanin icinde kaydir
    if (RD.set.fit === "width" && d > 0 && st.scrollTop + st.clientHeight < st.scrollHeight - 4) { st.scrollBy({ top: st.clientHeight * 0.85, behavior: "smooth" }); return; }
    if (RD.set.fit === "width" && d < 0 && st.scrollTop > 4) { st.scrollBy({ top: -st.clientHeight * 0.85, behavior: "smooth" }); return; }
    go(RD.page + d);
  }
}

function updateUi() {
  const n = RD.doc.count, i = RD.page;
  $("#rdPg").textContent = `${i + 1} / ${n}`;
  $("#rdSlider").value = i + 1;
  $("#rdPct").textContent = "%" + Math.round(((i + 1) / n) * 100) + (RD.zoom && RD.zoom !== 1 ? ` · ${Math.round(RD.zoom * 100)}% ${L("yakın", "zoom")}` : "");
  $("#rdMarkBtn").textContent = RD.st.marks.includes(i) ? "★" : "☆";
  $$(".rd-rail .th").forEach((t) => t.classList.toggle("on", +t.dataset.i === i));
  $(`.rd-rail .th[data-i="${i}"]`)?.scrollIntoView({ block: "nearest" });
}

// ---------------------------------------------------------------- kucuk resim seridi
function buildRail() {
  const rail = $("#rdRail");
  rail.innerHTML = Array.from({ length: RD.doc.count }, (_, i) => `<div class="th${RD.st.marks.includes(i) ? " mk" : ""}" data-i="${i}"><span>${i + 1}</span></div>`).join("");
  RD._tio?.disconnect();
  RD._tio = new IntersectionObserver((ents) => ents.forEach(async (e) => {
    if (!e.isIntersecting || e.target.dataset.done) return;
    e.target.dataset.done = 1;
    const src = await api.reader_thumb(+e.target.dataset.i);
    if (src) e.target.insertAdjacentHTML("afterbegin", `<img src="${src}" alt="">`);
  }), { root: rail, rootMargin: "400px 0px" });
  rail.querySelectorAll(".th").forEach((t) => RD._tio.observe(t));
}
$("#rdRail").addEventListener("click", (e) => { const t = e.target.closest(".th"); if (t) go(+t.dataset.i); });

// ---------------------------------------------------------------- calisma paneli
function renderTab() {
  if (!RD.doc) return;
  $$(".rd-tabs button").forEach((b) => b.classList.toggle("on", b.dataset.tab === RD.tab));
  const box = $("#rdTab");
  if (RD.tab === "hl") {
    const list = [...RD.st.hl].sort((a, b) => a.page - b.page || a.rects[0][1] - b.rects[0][1]);
    box.innerHTML = (pdf() ? "" : `<p class="rd-hint">${L("Vurgu ve notlar PDF'lerde çalışır. Çizgi romanlarda yer imi kullanabilirsin (B).", "Highlights work in PDFs. Use bookmarks (B) for comics.")}</p>`) +
      (list.length ? `<button class="btn" data-a="export">${L("Notları Markdown olarak dışa aktar", "Export notes as Markdown")}</button>` +
        list.map((h) => `<div class="rd-item ${h.color}" data-go="${h.page}" data-id="${h.id}"><button class="x" data-del="${h.id}" title="Sil">✕</button>
        <small>${L("Sayfa", "Page")} ${h.page + 1}</small><p>${esc(h.text)}</p>${h.note ? `<div class="nt">${esc(h.note)}</div>` : ""}</div>`).join("")
        : pdf() ? `<p class="rd-hint">${L("Metni seç, rengini tıkla. Not eklemek için seçtikten sonra 'Not'a bas. Kısayollar: ← → sayfa, Ctrl+F ara, B yer imi, N gece, T sesli oku, D çift sayfa, R yön.", "Select text and pick a colour. Shortcuts: ← → pages, Ctrl+F search, B bookmark, N night, T read aloud, D double, R direction.")}</p>` : "");
  } else if (RD.tab === "toc") {
    const o = RD.doc.outline || [];
    box.innerHTML = o.length ? o.map((t) => `<div class="rd-toc" data-go="${t.page}" style="padding-left:${8 + t.lvl * 14}px">${esc(t.t)} <small style="color:var(--mute)">${t.page + 1}</small></div>`).join("")
      : `<p class="rd-hint">${L("Bu belgede içindekiler yok.", "No table of contents.")}</p>`;
  } else if (RD.tab === "find") {
    box.innerHTML = `<input type="search" id="rdQ" placeholder="${pdf() ? L("Belgede ara… (Enter)", "Search document… (Enter)") : L("Arama yalnızca PDF'de", "Search works in PDFs")}" ${pdf() ? "" : "disabled"} value="${esc(RD.lastQ || "")}"><div id="rdHits"></div>`;
    setTimeout(() => $("#rdQ")?.focus(), 30);
    if (RD.hits) showHits();
  } else {
    box.innerHTML = RD.st.marks.length ? [...RD.st.marks].sort((a, b) => a - b).map((p) => `<div class="rd-item" data-go="${p}"><button class="x" data-unmark="${p}">✕</button><small>★</small><p>${L("Sayfa", "Page")} ${p + 1}</p></div>`).join("")
      : `<p class="rd-hint">${L("Yer imi yok. B tuşu ya da ☆ ile ekle.", "No bookmarks. Press B or ☆.")}</p>`;
  }
}
async function doSearch(q) {
  RD.lastQ = q; $("#rdHits").innerHTML = `<p class="rd-hint">${L("Aranıyor…", "Searching…")}</p>`;
  RD.hits = (await api.reader_search(q)) || [];
  showHits(); markFind(q);
}
function showHits() {
  const h = $("#rdHits"); if (!h) return;
  h.innerHTML = RD.hits.length ? `<p class="rd-hint">${RD.hits.length} ${L("sonuç", "results")}</p>` + RD.hits.map((x) => `<div class="rd-item" data-go="${x.page}"><small>${L("Sayfa", "Page")} ${x.page + 1}</small><p>${esc(x.ctx)}</p></div>`).join("")
    : `<p class="rd-hint">${L("Bulunamadı.", "Not found.")}</p>`;
}
function markFind(q) {   // gorunen sayfalarda eslesen kelimeleri boya
  RD.marks = {}; q = (q || "").toLowerCase().trim();
  if (q) $$(".rd-text span").forEach((s) => {
    if (!s.textContent.toLowerCase().includes(q.split(/\s+/)[0])) return;
    const pg = s.closest(".rd-page"), i = +pg.dataset.i, R = pg.getBoundingClientRect(), r = s.getBoundingClientRect();
    (RD.marks[i] ||= []).push({ cls: "find", x0: (r.left - R.left) / R.width, y0: (r.top - R.top) / R.height, x1: (r.right - R.left) / R.width, y1: (r.bottom - R.top) / R.height });
  });
  redrawHl();
}

// ---------------------------------------------------------------- secim -> vurgu
function selInfo() {
  const sel = window.getSelection();
  if (!sel || sel.isCollapsed || !sel.rangeCount) return null;
  const range = sel.getRangeAt(0);
  const pg = (range.startContainer.parentElement || range.startContainer).closest?.(".rd-page");
  if (!pg) return null;
  const R = pg.getBoundingClientRect();
  const rects = [...range.getClientRects()].filter((r) => r.width > 1 && r.height > 1).map((r) => [
    +((r.left - R.left) / R.width).toFixed(4), +((r.top - R.top) / R.height).toFixed(4),
    +((r.right - R.left) / R.width).toFixed(4), +((r.bottom - R.top) / R.height).toFixed(4)]);
  // ayni satirdaki kutulari birlestir
  const merged = [];
  rects.sort((a, b) => a[1] - b[1] || a[0] - b[0]).forEach((r) => {
    const m = merged.find((x) => Math.abs(x[1] - r[1]) < 0.006 && r[0] - x[2] < 0.03);
    if (m) { m[0] = Math.min(m[0], r[0]); m[2] = Math.max(m[2], r[2]); m[3] = Math.max(m[3], r[3]); } else merged.push([...r]);
  });
  return { page: +pg.dataset.i, rects: merged, text: sel.toString().replace(/\s+/g, " ").trim(), last: range.getBoundingClientRect() };
}
document.addEventListener("mouseup", (e) => {
  if (e.target.closest(".rd-pop")) return;
  setTimeout(() => {
    const s = pdf() && selInfo();
    const pop = $("#rdPop");
    if (!s || !s.text) { pop.hidden = true; return; }
    RD.sel = s; pop.hidden = false;
    pop.style.left = Math.max(8, Math.min(innerWidth - pop.offsetWidth - 8, s.last.left + s.last.width / 2 - pop.offsetWidth / 2)) + "px";
    pop.style.top = Math.max(8, s.last.top - pop.offsetHeight - 10) + "px";
  }, 10);
});
function addHl(color, note) {
  const s = RD.sel; if (!s) return null;
  const h = { id: Date.now().toString(36), page: s.page, rects: s.rects, text: s.text, color, note: note || "", t: Date.now() };
  RD.st.hl.push(h); dirty(); redrawHl(); window.getSelection().removeAllRanges(); $("#rdPop").hidden = true;
  if (RD.tab === "hl") renderTab();
  return h;
}
function editNote(h) {
  openDrawer("hl");
  const it = $(`.rd-item[data-id="${h.id}"]`); if (!it) return;
  it.scrollIntoView({ block: "center" });
  it.querySelector("textarea")?.remove();
  it.insertAdjacentHTML("beforeend", `<textarea placeholder="${L("Notun… (Ctrl+Enter kaydeder)", "Your note… (Ctrl+Enter saves)")}">${esc(h.note || "")}</textarea>`);
  const ta = it.querySelector("textarea"); ta.focus();
  const save = () => { h.note = ta.value.trim(); dirty(); redrawHl(); renderTab(); };
  ta.addEventListener("keydown", (e) => { if (e.key === "Enter" && e.ctrlKey) save(); if (e.key === "Escape") renderTab(); });
  ta.addEventListener("blur", save);
}
function openDrawer(tab) { if (tab) RD.tab = tab; $("#rdDrawer").hidden = false; renderTab(); setTimeout(render, 0); }

// ---------------------------------------------------------------- sesli okuma (Piper)
const TTS = { on: false, queue: [], k: 0, page: 0, audio: new Audio(), next: null, paused: false };
async function startTts(text) {
  stopTts();
  $("#rdTts").hidden = false; TTS.on = true; TTS.paused = false;
  const st = await api.reader_tts_status();
  const lang = $("#rdTtsLang").value;
  if (!st?.[lang || "tr"]) $("#rdTtsLine").textContent = L("İlk kullanım: Piper ve ses modeli indiriliyor (~70 MB)…", "First use: downloading Piper and the voice (~70 MB)…");
  if (text) { TTS.single = true; TTS.queue = await api.reader_split(text); }
  else { TTS.single = false; TTS.page = RD.page; TTS.queue = await api.reader_split(await api.reader_text(RD.page)); }
  TTS.k = 0; playK();
}
async function synth(k) {
  const t = TTS.queue[k]; if (!t) return null;
  return api.reader_speak(t, $("#rdTtsLang").value, +$("#rdTtsRate").value);
}
async function playK() {
  if (!TTS.on) return;
  if (TTS.k >= TTS.queue.length) {
    if (TTS.single || TTS.page + 1 >= RD.doc.count) { stopTts(); return; }
    TTS.page++; go(TTS.page); TTS.queue = await api.reader_split(await api.reader_text(TTS.page)); TTS.k = 0;
    if (!TTS.queue.length) return playK();
  }
  const line = TTS.queue[TTS.k];
  $("#rdTtsLine").textContent = line; $("#rdTtsPlay").textContent = "⏸";
  const r = await (TTS.next && TTS.nextK === TTS.k ? TTS.next : synth(TTS.k));
  if (!TTS.on) return;
  if (!r?.ok) { $("#rdTtsLine").textContent = L("Sesli okuma olmadı: ", "Read aloud failed: ") + (r?.error || ""); return; }
  TTS.nextK = TTS.k + 1; TTS.next = synth(TTS.k + 1);   // bir sonrakini simdiden hazirla
  sayMark(line);
  TTS.audio.src = r.src; TTS.audio.play().catch(() => {});
  TTS.audio.onended = () => { TTS.k++; playK(); };
}
function sayMark(line) {   // okunan cumlenin ilk kelimelerini sayfada isaretle
  if (!pdf()) return;
  const first = line.split(/\s+/).slice(0, 4).join(" ").toLowerCase();
  RD.marks = {};
  const pg = $(`.rd-page[data-i="${TTS.page}"]`);
  if (pg && !TTS.single) {
    const spans = [...pg.querySelectorAll(".rd-text span")], txt = spans.map((s) => s.textContent.toLowerCase());
    for (let k = 0; k < spans.length; k++) {
      if (!first.startsWith(txt[k].trim().slice(0, 6))) continue;
      const R = pg.getBoundingClientRect();
      spans.slice(k, k + Math.max(4, line.split(/\s+/).length)).forEach((s) => {
        const r = s.getBoundingClientRect();
        (RD.marks[TTS.page] ||= []).push({ cls: "say", x0: (r.left - R.left) / R.width, y0: (r.top - R.top) / R.height, x1: (r.right - R.left) / R.width, y1: (r.bottom - R.top) / R.height });
      });
      break;
    }
  }
  redrawHl();
}
function stopTts() { TTS.on = false; TTS.audio.pause(); TTS.next = null; $("#rdTts").hidden = true; RD.marks = {}; redrawHl(); }

// ---------------------------------------------------------------- olaylar
document.addEventListener("click", async (e) => {
  const g = e.target.closest("[data-go]");
  const del = e.target.closest("[data-del]"), um = e.target.closest("[data-unmark]");
  if (del) { RD.st.hl = RD.st.hl.filter((h) => h.id !== del.dataset.del); dirty(); redrawHl(); renderTab(); return; }
  if (um) { RD.st.marks = RD.st.marks.filter((p) => p !== +um.dataset.unmark); dirty(); buildRail(); renderTab(); updateUi(); return; }
  const it = e.target.closest(".rd-item[data-id]");
  if (it && e.detail === 2) { const h = RD.st.hl.find((x) => x.id === it.dataset.id); if (h) editNote(h); return; }
  if (g && !e.target.closest("textarea")) { go(+g.dataset.go); return; }
  const hi = e.target.closest(".rd-hl i[data-id]");
  if (hi) { const h = RD.st.hl.find((x) => x.id === hi.dataset.id); if (h) editNote(h); return; }
  const book = e.target.closest(".rh-book"); if (book) { openDoc(book.dataset.path); return; }
  const tab = e.target.closest("[data-tab]"); if (tab) { RD.tab = tab.dataset.tab; renderTab(); return; }
  const mode = e.target.closest("[data-mode]"); if (mode) { RD.set.mode = mode.dataset.mode; saveSet(); return; }
  const hl = e.target.closest("[data-hl]"); if (hl) { addHl(hl.dataset.hl); return; }
  const b = e.target.closest("[data-a]"); if (!b) return;
  const a = b.dataset.a;
  if (a === "pick" || a === "pickdir") { const p = await api.reader_pick(a === "pickdir"); if (p) openDoc(p); }
  else if (a === "home") home();
  else if (a === "zl") step(RD.set.rtl ? 1 : -1);
  else if (a === "zr") step(RD.set.rtl ? -1 : 1);
  else if (a === "dir") { RD.set.rtl = !RD.set.rtl; saveSet(); }
  else if (a === "fit") { RD.set.fit = RD.set.fit === "width" ? "height" : "width"; saveSet(); }
  else if (a === "night") { RD.set.night = !RD.set.night; saveSet(); }
  else if (a === "mark") toggleMark();
  else if (a === "drawer") { $("#rdDrawer").hidden = !$("#rdDrawer").hidden; renderTab(); setTimeout(render, 0); }
  else if (a === "export") { const r = await api.reader_export_notes(); toast(r?.ok ? L("Kaydedildi: ", "Saved: ") + r.path.split(/[\\/]/).pop() : L("Olmadı", "Failed")); }
  else if (a === "tts") TTS.on ? stopTts() : startTts();
  else if (a === "ttsstop") stopTts();
  else if (a === "ttsplay") { if (TTS.audio.paused) { TTS.audio.play(); b.textContent = "⏸"; } else { TTS.audio.pause(); b.textContent = "▶"; } }
  else if (a === "ttsnext") { TTS.audio.pause(); TTS.k++; TTS.next = null; playK(); }
  else if (a === "ttsprev") { TTS.audio.pause(); TTS.k = Math.max(0, TTS.k - 1); TTS.next = null; playK(); }
  else if (a === "popnote") { const h = addHl("p"); if (h) editNote(h); }
  else if (a === "popdict") { const t = RD.sel?.text; $("#rdPop").hidden = true; if (t) rdLookupOrTranslate(t); }
  else if (a === "ocrpage") { rdOcrCurrentPage(); }
  else if (a === "exportmd") { rdExportMarkdown(); }
  else if (a === "ocrpdf") { rdMakeSearchablePdf(); }
  else if (a === "popsay") { const t = RD.sel?.text; $("#rdPop").hidden = true; if (t) startTts(t); }
  else if (a === "popcopy") { navigator.clipboard?.writeText(RD.sel?.text || ""); $("#rdPop").hidden = true; toast(L("Kopyalandı", "Copied")); }
});

function rdShowBox(title, body) {
  const b = $("#rdDictBox");
  if (!b) return;
  b.hidden = false;
  b.innerHTML = `<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px"><strong style="color:#c4b5fd">${esc(title)}</strong><button id="rdDictClose" style="background:none;border:0;color:#bbaee0;cursor:pointer">✕</button></div><div style="white-space:pre-wrap">${esc(body)}</div>`;
  b.querySelector("#rdDictClose").onclick = () => { b.hidden = true; };
}

function rdExportMarkdown() {
  if (!RD.doc || !RD.st) return;
  const hls = RD.st.hl || [];
  if (!hls.length) { toast(L("Dışa aktarılacak vurgu yok", "No highlights to export")); return; }
  const lines = [`# ${RD.doc.title || "PDF Notları"}\n`];
  for (const h of hls) {
    lines.push(`- **S.${(h.page || 0) + 1}:** ${h.text || ""}${h.note ? `\n  - *Not:* ${h.note}` : ""}`);
  }
  const blob = new Blob([lines.join("\n")], { type: "text/markdown;charset=utf-8" });
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = `${(RD.doc.title || "notlar").replace(/[^a-zA-Z0-9_-]+/g, "_")}.md`;
  a.click();
  toast(L("Markdown indirildi ✓", "Markdown downloaded ✓"));
}

async function rdMakeSearchablePdf() {
  if (!RD.doc?.path) return;
  toast(L("PDF OCR işi başlatıldı...", "PDF OCR job started..."));
  const r = await api.reader_ocr_pdf?.(RD.doc.path);
  if (r?.ok) toast(L("Aranabilir PDF işi kuyrukta ✓", "Searchable PDF job queued ✓"));
}

async function rdLookupOrTranslate(text) {
  const clean = String(text || "").trim();
  if (!clean) return;
  rdShowBox(clean, L("Aranıyor...", "Looking up..."));
  const single = !/\s/.test(clean) && clean.length <= 40;
  if (single) {
    const d = await api.dict_lookup(clean, "", "", -1).catch(() => null);
    if (d && d.ok && Array.isArray(d.senses) && d.senses.length) {
      const lines = d.senses.slice(0, 5).map((s, i) => `${i + 1}. (${s.pos || ""}) ${s.gloss || ""}`);
      rdShowBox(`${d.word || clean}${d.ipa ? " /" + d.ipa + "/" : ""}`, lines.join("\n"));
      return;
    }
  }
  const tr = await api.ocr_translate(clean, "", "google").catch(() => null);
  if (tr && tr.ok && tr.text) rdShowBox(L("Çeviri", "Translation"), tr.text);
  else rdShowBox(clean, L("Sonuç bulunamadı", "No result"));
}

async function rdOcrCurrentPage() {
  const pg = document.querySelector(`.rd-page[data-i="${RD.page}"]`);
  const srcEl = pg?.querySelector("canvas, img");
  if (!srcEl) { toast(L("OCR için sayfa görseli bulunamadı", "No page image for OCR")); return; }
  rdShowBox("OCR", L("Sayfa okunuyor...", "Scanning page..."));
  const cv = document.createElement("canvas");
  cv.width = srcEl.naturalWidth || srcEl.width;
  cv.height = srcEl.naturalHeight || srcEl.height;
  cv.getContext("2d").drawImage(srcEl, 0, 0, cv.width, cv.height);
  const res = await api.ocr_image(cv.toDataURL("image/png"), "").catch(() => null);
  if (!res || !res.ok || !res.text) {
    rdShowBox("OCR", (res && res.error) || L("Metin bulunamadı", "No text found"));
    return;
  }
  const tr = await api.ocr_translate(res.text, res.lang || "", "google").catch(() => null);
  const out = (tr && tr.ok && tr.text) ? `${tr.text}\n\n---\n${res.text}` : res.text;
  rdShowBox(`OCR (${res.lang || "auto"})`, out);
}
function toggleMark() {
  const i = RD.page, m = RD.st.marks;
  RD.st.marks = m.includes(i) ? m.filter((x) => x !== i) : [...m, i];
  dirty(); updateUi(); $(`.rd-rail .th[data-i="${i}"]`)?.classList.toggle("mk", RD.st.marks.includes(i));
  if (RD.tab === "marks") renderTab();
}
document.addEventListener("keydown", (e) => {
  if (e.target.matches("input, textarea, select")) {
    if (e.target.id === "rdQ" && e.key === "Enter") doSearch(e.target.value);
    return;
  }
  if (!RD.doc) return;
  const k = e.key, rtl = RD.set.rtl && RD.set.mode !== "scroll";
  if (k === "ArrowRight") step(rtl ? -1 : 1);
  else if (k === "ArrowLeft") step(rtl ? 1 : -1);
  else if (k === "PageDown" || k === " " || k === "ArrowDown" && RD.set.mode !== "scroll") { e.preventDefault(); step(1); }
  else if (k === "PageUp" || k === "ArrowUp" && RD.set.mode !== "scroll") { e.preventDefault(); step(-1); }
  else if (k === "Home") go(0);
  else if (k === "End") go(RD.doc.count - 1);
  else if (e.ctrlKey && k.toLowerCase() === "f") { e.preventDefault(); openDrawer("find"); }
  else if (k === "b" || k === "B") toggleMark();
  else if (k === "n" || k === "N") { RD.set.night = !RD.set.night; saveSet(); }
  else if (k === "d" || k === "D") { RD.set.mode = RD.set.mode === "double" ? "single" : "double"; saveSet(); }
  else if (k === "w" || k === "W") { RD.set.mode = RD.set.mode === "scroll" ? "single" : "scroll"; saveSet(); }
  else if (k === "r" || k === "R") { RD.set.rtl = !RD.set.rtl; saveSet(); }
  else if (k === "f" || k === "F") { RD.set.fit = RD.set.fit === "width" ? "height" : "width"; saveSet(); }
  else if ((k === "t" || k === "T") && pdf()) TTS.on ? stopTts() : startTts();
  else if (k === "o" || k === "O") rdOcrCurrentPage();
  else if (k === "+" || k === "=") zoomBy(1.15);
  else if (k === "-") zoomBy(1 / 1.15);
  else if (k === "0") { RD.zoom = 1; RD.cache.clear(); render(); }
  else if (k === "Escape") { $("#rdPop").hidden = true; if (!$("#rdDrawer").hidden) { $("#rdDrawer").hidden = true; setTimeout(render, 0); } }
});
$("#rdSlider").addEventListener("input", (e) => { $("#rdPg").textContent = `${e.target.value} / ${RD.doc.count}`; });
$("#rdSlider").addEventListener("change", (e) => go(+e.target.value - 1));
function zoomBy(f) {
  RD.zoom = Math.max(0.4, Math.min(4, (RD.zoom || 1) * f));
  clearTimeout(RD._zt); RD._zt = setTimeout(() => { RD.cache.clear(); render(); }, 120);
  updateUi();
}
$("#rdStage").addEventListener("wheel", (e) => {   // tek/cift sayfada tekerlek: sayfa sonunda bir sonrakine gec; Ctrl+tekerlek: yakinlastir
  if (RD.doc && e.ctrlKey) { e.preventDefault(); zoomBy(e.deltaY < 0 ? 1.12 : 1 / 1.12); return; }
  if (!RD.doc || RD.set.mode === "scroll") return;
  const st = $("#rdStage"), atEnd = st.scrollTop + st.clientHeight >= st.scrollHeight - 2, atTop = st.scrollTop <= 1;
  if ((e.deltaY > 0 && atEnd) || (e.deltaY < 0 && atTop)) {
    e.preventDefault();
    if (Date.now() - (RD._wh || 0) < 350) return;
    RD._wh = Date.now(); step(e.deltaY > 0 ? 1 : -1);
  }
}, { passive: false });
let rsz; window.addEventListener("resize", () => { clearTimeout(rsz); rsz = setTimeout(() => { RD.cache.clear(); render(); }, 200); });
// hareketsizken ust/alt cubuklar kaybolur (yalniz cizgi romanda; PDF'de calisirken sabit)
let idleT; document.addEventListener("mousemove", (e) => {
  document.body.classList.remove("idle"); clearTimeout(idleT);
  if (RD.doc && !pdf() && e.clientY > 80 && e.clientY < innerHeight - 70) idleT = setTimeout(() => document.body.classList.add("idle"), 2200);
});
let dd = 0;
document.addEventListener("dragenter", (e) => { e.preventDefault(); dd++; $("#rdDrop").hidden = false; });
document.addEventListener("dragleave", () => { if (--dd <= 0) { dd = 0; $("#rdDrop").hidden = true; } });
document.addEventListener("dragover", (e) => e.preventDefault());
document.addEventListener("drop", (e) => { e.preventDefault(); dd = 0; $("#rdDrop").hidden = true; });   // yol Python'dan gelir (reader_poll)
window.addEventListener("beforeunload", saveNow);

async function init() {
  api = window.pywebview.api;
  try { const s = await api.get_settings(); LANG = s?.language || "tr"; } catch { /* tr */ }
  i18n();
  const q = (await api.reader_poll()) || [];
  if (q.length) openDoc(q[q.length - 1]); else home();
  setInterval(async () => { const q2 = (await api.reader_poll()) || []; if (q2.length) openDoc(q2[q2.length - 1]); }, 700);
}
if (window.pywebview?.api) init(); else window.addEventListener("pywebviewready", init);
