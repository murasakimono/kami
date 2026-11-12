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
  PC.list = (await api.image_siblings(path)) || [path];
  if (!PC.list.includes(path)) PC.list.unshift(path);
  PC.i = PC.list.indexOf(path);
  await load();
  if (lens) runLens();
  else if (!$("#pcLens").hidden) runLens();
}
async function load() {
  const p = PC.list[PC.i]; if (!p) return;
  PC.z = 1; PC.x = PC.y = 0; PC.rot = 0;
  $("#pcName").textContent = p.split(/[\\/]/).pop();
  $("#pcInfo").textContent = L("yükleniyor…", "loading…");
  $("#pcEmpty").hidden = true;
  const r = await api.image_data(p);
  if (PC.list[PC.i] !== p) return;
  if (!r?.ok) { $("#pcInfo").textContent = L("Açılamadı", "Can't open"); return; }
  $("#pcImg").src = r.url;
  const ex = Object.entries(r.exif || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
  $("#pcInfo").textContent = `${r.w}×${r.h} · ${fmtB(r.size)} · ${PC.i + 1}/${PC.list.length}${ex ? " · " + ex : ""}`;
  document.title = "Kami Picture · " + p.split(/[\\/]/).pop();
  apply();
}
function apply() { $("#pcImg").style.transform = `translate(${PC.x}px, ${PC.y}px) scale(${PC.z}) rotate(${PC.rot}deg)`; }
function step(d) { if (PC.list.length < 2) return; PC.i = (PC.i + d + PC.list.length) % PC.list.length; load().then(() => { if (!$("#pcLens").hidden) runLens(); }); }

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
  else if (a === "rot") { PC.rot = (PC.rot + 90) % 360; apply(); }
  else if (a === "fit") { PC.z = 1; PC.x = PC.y = 0; apply(); }
  else if (a === "folder" && p) api.open_path_folder(p);
  else if ((a === "conv" || a === "nobg") && p) api.picture_send(p, a === "nobg" ? "img:nobg" : "");
  else if (a === "lens") { if (!$("#pcLens").hidden) { $("#pcLens").hidden = true; b.classList.remove("on"); } else runLens(); }
});
const stage = $("#pcStage");
stage.addEventListener("wheel", (e) => { e.preventDefault(); PC.z = Math.min(12, Math.max(0.1, PC.z * (e.deltaY < 0 ? 1.15 : 1 / 1.15))); apply(); }, { passive: false });
let drag = null;
stage.addEventListener("mousedown", (e) => { if (e.target.closest("button")) return; drag = { sx: e.clientX - PC.x, sy: e.clientY - PC.y }; stage.classList.add("drag"); });
addEventListener("mousemove", (e) => { if (drag) { PC.x = e.clientX - drag.sx; PC.y = e.clientY - drag.sy; apply(); } });
addEventListener("mouseup", () => { drag = null; stage.classList.remove("drag"); });
stage.addEventListener("dblclick", () => { PC.z = PC.z > 1.01 ? 1 : 2.5; PC.x = PC.y = 0; apply(); });
document.addEventListener("keydown", (e) => {
  if (e.target.matches?.("input, textarea")) return;
  const k = e.key;
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
  const poll = async () => { try { for (const it of (await api.picture_poll()) || []) await open(it.path, it.lens); } catch { /* yok */ } };
  poll(); setInterval(poll, 700);
});
