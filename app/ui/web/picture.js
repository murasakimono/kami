// Kami Picture: fotograf goruntuleyici + Kami Lens (gorselle arama, sonuclar burada birlesir).
"use strict";
const $ = (s) => document.querySelector(s);
const PC = { list: [], i: 0, z: 1, x: 0, y: 0, rot: 0, lens: null, lensFor: "" };
let api = null, LANG = "tr";
const L = (tr, en) => (LANG === "en" ? en : tr);
const esc = (t) => String(t ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const fmtB = (n) => (n > 1e6 ? (n / 1e6).toFixed(1) + " MB" : Math.round(n / 1e3) + " KB");
function toast(t) { const el = document.createElement("div"); el.className = "toast"; el.textContent = t; document.body.appendChild(el); setTimeout(() => el.remove(), 2600); }
function i18n() { document.querySelectorAll("[data-tr]").forEach((e) => (e.textContent = L(e.dataset.tr, e.dataset.en))); }

async function open(path, lens) {
  try { const rc = JSON.parse(localStorage.getItem("kami.picRecent") || "[]").filter((x) => x !== path); rc.unshift(path); localStorage.setItem("kami.picRecent", JSON.stringify(rc.slice(0, 8))); } catch { /* depolama yok */ }
  PC.list = (await api.image_siblings(path)) || [path];
  if (!PC.list.includes(path)) PC.list.unshift(path);
  PC.i = PC.list.indexOf(path);
  await load();
  window.kamiPicV138?.syncControls?.(PC);
  if (lens) runLens();
  else if (!$("#pcLens").hidden) runLens();
}
async function load() {
  const p = PC.list[PC.i]; if (!p) return;
  PC.z = 1; PC.x = PC.y = 0; PC.rot = 0;
  $("#pcName").textContent = p.split(/[\\/]/).pop();
  $("#pcInfo").textContent = L("yükleniyor…", "loading…");
  $("#pcEmpty").hidden = true;
  window.kamiPicV138?.syncControls?.(PC);
  const r = await api.image_data(p);
  if (PC.list[PC.i] !== p) return;
  if (!r?.ok) { $("#pcInfo").textContent = L("Açılamadı", "Can't open"); return; }
  $("#pcImg").src = r.url;
  const ex = Object.entries(r.exif || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
  $("#pcInfo").textContent = `${r.w}×${r.h} · ${fmtB(r.size)} · ${PC.i + 1}/${PC.list.length}${ex ? " · " + ex : ""}`;
  document.title = "Kami Picture · " + p.split(/[\\/]/).pop();
  api.pic_set_current?.(p);
  apply();
}
function apply() { $("#pcImg").style.transform = `translate(${PC.x}px, ${PC.y}px) scale(${PC.z}) rotate(${PC.rot}deg)`; }
function step(d) { if (PC.list.length < 2) return; PC.i = (PC.i + d + PC.list.length) % PC.list.length; load().then(() => { if (!$("#pcLens").hidden) runLens(); }); }

// ---------- Perspektif Mockup & AI Kopru Durumu ----------
const MOCK = { on: false, base: "", design: "", s0: null, s1: null, el: null };
function mockStage() { return $("#pcStage"); }
function mockPos(e) { const r = mockStage().getBoundingClientRect(); return [e.clientX - r.left, e.clientY - r.top]; }
function mockImgXY(cx, cy) {   // sahne -> goruntu piksel (zoom/pan etkisini rect uzerinden hesaba katar)
  const img = $("#pcImg");
  const r = img.getBoundingClientRect();
  const W = img.naturalWidth || 1, H = img.naturalHeight || 1;
  return [Math.max(0, Math.min(W, ((cx - r.left) / r.width) * W)), Math.max(0, Math.min(H, ((cy - r.top) / r.height) * H))];
}
function mockDraw(s0, s1) {
  if (!MOCK.el) return;
  const x = Math.min(s0[0], s1[0]), y = Math.min(s0[1], s1[1]);
  MOCK.el.style.left = x + "px"; MOCK.el.style.top = y + "px";
  MOCK.el.style.width = Math.abs(s1[0] - s0[0]) + "px"; MOCK.el.style.height = Math.abs(s1[1] - s0[1]) + "px";
}
function mockCancel() {
  MOCK.on = false; MOCK.s0 = MOCK.s1 = null;
  if (MOCK.el) { MOCK.el.remove(); MOCK.el = null; }
  mockStage().style.cursor = "";
}
async function mockRun() {
  const p = PC.list[PC.i]; if (!p) return;
  const files = (await api.pic_batch_pick()) || [];
  if (!files[0]) return toast(L("Tasarım görseli seçilmedi", "No design image picked"));
  mockCancel();
  MOCK.on = true; MOCK.base = p; MOCK.design = files[0];
  PC.rot = 0; apply();
  MOCK.el = document.createElement("div");
  MOCK.el.style.cssText = "position:absolute;display:none;border:2px solid #2EE6A6;background:rgba(46,230,166,.14);pointer-events:none;z-index:6";
  mockStage().appendChild(MOCK.el);
  mockStage().style.cursor = "crosshair";
  toast(L("Tasarımın yerleşeceği alanı sürükleyerek seç (Esc iptal)", "Drag to select where the design goes (Esc cancels)"));
}
async function mockFinish(s1) {
  const s0 = MOCK.s0; mockCancel();
  if (!s0 || !s1) return;
  const [x1, y1] = mockImgXY(s0[0], s0[1]);
  const [x2, y2] = mockImgXY(s1[0], s1[1]);
  if (Math.abs(x2 - x1) < 4 || Math.abs(y2 - y1) < 4) return toast(L("Alan çok küçük", "Area too small"));
  toast(L("Mockup oluşturuluyor…", "Building mockup…"));
  const r = await api.pic_mockup(MOCK.design, MOCK.base, [[x1, y1], [x2, y1], [x2, y2], [x1, y2]], "");
  if (r?.ok) { toast(L("Mockup hazır: ", "Mockup ready: ") + r.path.split(/[\\/]/).pop()); open(r.path); }
  else toast(L("Mockup olmadı: ", "Mockup failed: ") + (r?.error || ""));
}
async function bridgeStatus() {
  try {
    const r = await api.pic_ai_bridge_status();
    const pre = r?.vram_6gb_preflight || {};
    const snap = pre.snapshot || {};
    const vram = pre.fallback === "cpu"
      ? L("VRAM yetersiz (CPU öneriliyor)", "VRAM low (CPU suggested)")
      : L("VRAM yeterli", "VRAM OK") + (snap.vram_free_mb ? ` · ${snap.vram_free_mb} MB boş` : "");
    toast(`${L("ComfyUI", "ComfyUI")}: ${r?.comfyui_running ? "✓" : "✗"} · ${L("IOPaint", "IOPaint")}: ${r?.iopaint_running ? "✓" : "✗"} · ${vram}`);
  } catch { toast(L("AI köprü durumu alınamadı", "Could not read AI bridge status")); }
}

// ---------- Kami Lens ----------
async function runLens() {
  const p = PC.list[PC.i]; if (!p) return;
  const box = $("#pcLens"); box.hidden = false; $("[data-a=lens]").classList.add("on");
  if (PC.lensFor === p && PC.lens) return drawLens(PC.lens);
  box.innerHTML = `<div class="ln-load"><i></i>${L("Google Lens, Yandex ve TinEye'de aranıyor…", "Searching Google Lens, Yandex and TinEye…")}</div>`;
  PC.lensFor = p; PC.lens = null;
  const r = await api.lens_search(p);
  if (PC.lensFor !== p) return;
  PC.lens = r; drawLens(r);
}
function drawLens(r) {
  const box = $("#pcLens");
  if (!r?.ok) { box.innerHTML = `<p class="ln-err">${L("Arama yapılamadı", "Search failed")}: ${esc(r?.error || Object.keys(r?.errors || {}).join(", "))}</p>`; return; }
  const errs = Object.keys(r.errors || {});
  const big = r.biggest; window.PCSZ = (r.sizes || []).map((x) => x.url);
  box.innerHTML = `
    ${big ? `<h3>${L("En büyük boyut", "Largest size")}</h3><div class="ln-big"><span>${L("Bulunan en büyük", "Biggest found")}: <b>${big.w}×${big.h}</b></span><button class="ln-btn" data-dl="${esc(big.url)}">${L("İndir", "Download")}</button></div>` : ""}
    ${r.tags?.length ? `<h3>${L("Bu ne olabilir", "What it might be")}</h3><div class="ln-tags">${r.tags.map((t) => `<span>${esc(t)}</span>`).join("")}</div>` : ""}
    <h3>${L("Motorlarda aç", "Open in engines")}</h3>
    <div class="ln-links">${Object.entries(r.links || {}).filter(([, u]) => u).map(([k, u]) => `<button class="ln-btn ghost" data-url="${esc(u)}">${esc(k)} ↗</button>`).join("")}</div>
    ${r.sites?.length ? `<h3>${L("Geçtiği sayfalar", "Pages with this image")} · ${r.sites.length}${r.tineye_total > r.sites.length ? ` <small>(TinEye: ${r.tineye_total})</small>` : ""}</h3>
      <div class="ln-sites">${r.sites.map((s) => `<div class="ln-site" data-url="${esc(s.url)}" title="${esc(s.url)}"><img src="${esc(s.thumb || s.img)}" loading="lazy" referrerpolicy="no-referrer" onerror="this.style.visibility='hidden'">
        <div><b>${esc(s.title || s.domain)}</b><small>${esc(s.desc)}</small><small>${esc(s.domain)}${s.w ? ` · ${s.w}×${s.h}` : ""} · <em>${esc(s.engine)}</em></small></div></div>`).join("")}</div>` : `<p class="ln-err">${L("Bu görselin geçtiği sayfa bulunamadı.", "No pages found for this image.")}</p>`}
    ${r.similar?.length ? `<h3>${L("Benzer görseller", "Similar images")}</h3><div class="ln-sim">${r.similar.map((s) => `<img src="${esc(s.thumb)}" title="${esc(s.title)}" data-url="${esc(s.url)}" loading="lazy" referrerpolicy="no-referrer">`).join("")}</div>` : ""}
    ${errs.length ? `<p class="ln-err">${L("Yanıt vermeyen", "Not responding")}: ${esc(errs.join(", "))}</p>` : ""}`;
}

document.addEventListener("click", async (e) => {
  const u = e.target.closest("[data-url]"); if (u) { api.open_web(u.dataset.url); return; }
  const d = e.target.closest("[data-dl]");
  if (d) { d.disabled = true; d.textContent = L("İndiriliyor…", "Downloading…"); const r = await api.lens_download([d.dataset.dl, ...(window.PCSZ || [])], PC.list[PC.i]); d.disabled = false; d.textContent = L("İndir", "Download"); toast(r?.ok ? L("İndirildi: ", "Saved: ") + r.path.split(/[\\/]/).pop() : L("İndirilemedi: ", "Failed: ") + (r?.error || "")); if (r?.ok) { PC.list = await api.image_siblings(r.path); PC.i = PC.list.indexOf(r.path); load(); } return; }
  const b = e.target.closest("button[data-a]"); if (!b) return;
  const a = b.dataset.a, p = PC.list[PC.i];
  if (a === "prev") step(-1); else if (a === "next") step(1);
  else if (a === "grab") window.kamiPicV138?.action?.("grab", p);
  else if (a === "edit") window.kamiEditor.open(p || "");
  else if (a === "new") window.kamiEditor.open("");
  else if (a === "rot") { PC.rot = (PC.rot + 90) % 360; apply(); }
  else if (a === "fit") { PC.z = 1; PC.x = PC.y = 0; apply(); }
  else if (a === "folder" && p) api.open_path_folder(p);
  else if ((a === "conv" || a === "nobg") && p) api.picture_send(p, a === "nobg" ? "img:nobg" : "");
  else if ((a === "beautify" || a === "pin") && p) window.kamiPicV138?.action?.(a, p);
  else if (a === "lens") { if (!$("#pcLens").hidden) { $("#pcLens").hidden = true; b.classList.remove("on"); } else runLens(); }
  else if (a === "mockup") mockRun();
  else if (a === "bridge") bridgeStatus();
});
const stage = $("#pcStage");
stage.addEventListener("wheel", (e) => { e.preventDefault(); PC.z = Math.min(12, Math.max(0.1, PC.z * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); apply(); }, { passive: false });
let drag = null;
stage.addEventListener("mousedown", (e) => {
  if (e.target.closest("button")) return;
  if (MOCK.on) { MOCK.s0 = mockPos(e); MOCK.s1 = MOCK.s0; MOCK.el.style.display = "block"; mockDraw(MOCK.s0, MOCK.s1); return; }
  drag = { sx: e.clientX - PC.x, sy: e.clientY - PC.y }; stage.classList.add("drag");
});
addEventListener("mousemove", (e) => {
  if (MOCK.on && MOCK.s0) { MOCK.s1 = mockPos(e); mockDraw(MOCK.s0, MOCK.s1); return; }
  if (drag) { PC.x = e.clientX - drag.sx; PC.y = e.clientY - drag.sy; apply(); }
});
addEventListener("mouseup", (e) => {
  if (MOCK.on && MOCK.s0) { mockFinish(e ? mockPos(e) : MOCK.s1); }
  drag = null; stage.classList.remove("drag");
});
stage.addEventListener("dblclick", () => { PC.z = PC.z > 1.01 ? 1 : 2.5; PC.x = PC.y = 0; apply(); });
document.addEventListener("keydown", (e) => {
  if (e.target.matches?.("input, textarea") || window.ED?.on || (typeof ED !== "undefined" && ED.on)) return;
  const k = e.key;
  if (k === "Escape" && MOCK.on) { mockCancel(); e.preventDefault(); return; }
  if (k.toLowerCase() === "e" && PC.list[PC.i]) { window.kamiEditor.open(PC.list[PC.i]); e.preventDefault(); return; }
  if (k === "ArrowRight") step(1); else if (k === "ArrowLeft") step(-1);
  else if (k.toLowerCase() === "r") { PC.rot = (PC.rot + 90) % 360; apply(); } else if (k === "0") { PC.z = 1; PC.x = PC.y = 0; apply(); }
  else if (k === "+" || k === "=") { PC.z = Math.min(12, PC.z * 1.2); apply(); } else if (k === "-") { PC.z = Math.max(0.1, PC.z / 1.2); apply(); }
  else if (k.toLowerCase() === "l") $("[data-a=lens]").click();
  else return;
  e.preventDefault();
});

window.addEventListener("pywebviewready", async () => {
  api = window.pywebview.api;
  try { LANG = (await api.get_settings())?.language === "en" ? "en" : "tr"; } catch { /* yok */ }
  i18n();
  const poll = async () => { try { for (const it of (await api.picture_poll()) || []) { if (it.edit) { if (it.path) await open(it.path, false); window.kamiEditor.open(it.path || ""); } else await open(it.path, it.lens); } } catch { /* yok */ } };
  poll();
  window.addEventListener("focus", poll);
  setInterval(() => { if (!document.hidden) poll(); }, 1000);
});

// v1.32.1 bos ekran: ac / yeni tuval / son acilanlar (eskiden tek satir yazi)
async function pcEmptyRender() {
  const box = $("#pcEmpty"); if (!box || box.hidden) return;
  let rc = []; try { rc = JSON.parse(localStorage.getItem("kami.picRecent") || "[]"); } catch { /* yok */ }
  box.innerHTML = `<span class="pce-ic"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="9" cy="10" r="2"/><path d="m21 16-5-5-9 9"/></svg></span>
    <b>${L("Bir görseli buraya bırak", "Drop an image here")}</b><small>${L("JPG, PNG, WebP, HEIC, GIF, AVIF…", "JPG, PNG, WebP, HEIC, GIF, AVIF…")}</small>
    <span class="pce-acts"><button type="button" class="btn primary" data-pce="open">${L("Görsel aç", "Open image")}</button><button type="button" class="btn" data-pce="new">${L("Yeni tuval", "New canvas")}</button></span>
    ${rc.length ? `<span class="pce-rc-h">${L("Son açılanlar", "Recent")}</span><span class="pce-rc">${rc.map((p, i) => `<button type="button" data-pr="${i}" title="${esc(p)}"><img alt=""><i>${esc(p.split(/[\\/]/).pop())}</i></button>`).join("")}</span>` : ""}`;
  box.querySelector('[data-pce="open"]').onclick = async () => { const f = (await api.pic_batch_pick()) || []; if (f[0]) open(f[0]); };
  box.querySelector('[data-pce="new"]').onclick = () => window.kamiEditor?.open("");
  box.querySelectorAll("[data-pr]").forEach(async (b) => {
    const p = rc[+b.dataset.pr];
    b.onclick = () => open(p);
    try { const r = await api.image_data(p); if (r?.ok) b.querySelector("img").src = r.url; else b.remove(); } catch { b.remove(); }
  });
}
(function pceBoot() { if (api) pcEmptyRender(); else setTimeout(pceBoot, 300); })();
