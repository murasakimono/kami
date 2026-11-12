// Fotograf goruntuleyici: biten gorsellere cift tik / "Goruntule". Yakinlastir (tekerlek), kaydir (surukle),
// dondur (R), ileri/geri (oklar), Donustur'e gonder, arka plani kaldir. Ileride editor + AI araclari buraya.
"use strict";
const VW = { list: [], i: 0, z: 1, x: 0, y: 0, rot: 0, el: null };
const vwL = (tr, en) => (state.lang !== "en" ? tr : en);
const VW_EXT = /\.(jpe?g|png|webp|gif|bmp|avif|jfif|heic|tiff?)$/i;

async function vwOpen(path, lens) {
  if (api.picture_open) { api.picture_open(path, !!lens); return; }   // ayri pencere: Kami Picture
  VW.list = (await api.image_siblings(path)) || [path];
  VW.i = Math.max(0, VW.list.indexOf(path));
  if (!VW.el) vwBuild();
  VW.el.hidden = false;
  vwLoad();
}
function vwBuild() {
  const el = document.createElement("div");
  el.id = "kvw"; el.className = "kvw"; el.hidden = true;
  el.innerHTML = `<div class="kvw-stage" id="kvwStage"><img id="kvwImg" alt=""></div>
    <div class="kvw-top"><b id="kvwName"></b><span id="kvwInfo"></span><span class="sp"></span>
      <button data-v="rot" title="R">⟳ ${vwL("Döndür", "Rotate")}</button><button data-v="fit" title="0">${vwL("Sığdır", "Fit")}</button>
      <button data-v="nobg">✦ ${vwL("Arka planı kaldır", "Remove background")}</button><button data-v="conv">⇄ ${vwL("Dönüştür", "Convert")}</button>
      <button data-v="folder">${vwL("Klasör", "Folder")}</button><button data-v="x" class="x" title="Esc">✕</button></div>
    <button class="kvw-nav l" data-v="prev">‹</button><button class="kvw-nav r" data-v="next">›</button>`;
  document.body.appendChild(el);
  VW.el = el;
  const stage = el.querySelector("#kvwStage");
  stage.addEventListener("wheel", (e) => { e.preventDefault(); const f = e.deltaY < 0 ? 1.15 : 1 / 1.15; VW.z = Math.min(12, Math.max(0.1, VW.z * f)); vwApply(); }, { passive: false });
  let drag = null;
  stage.addEventListener("mousedown", (e) => { drag = { sx: e.clientX - VW.x, sy: e.clientY - VW.y }; stage.classList.add("drag"); });
  addEventListener("mousemove", (e) => { if (drag) { VW.x = e.clientX - drag.sx; VW.y = e.clientY - drag.sy; vwApply(); } });
  addEventListener("mouseup", () => { drag = null; stage.classList.remove("drag"); });
  stage.addEventListener("dblclick", () => { VW.z = VW.z > 1.01 ? 1 : 2.5; VW.x = VW.y = 0; vwApply(); });
  el.addEventListener("click", async (e) => {
    const b = e.target.closest("button[data-v]"); if (!b) return;
    const v = b.dataset.v, p = VW.list[VW.i];
    if (v === "x") vwClose();
    else if (v === "prev") vwStep(-1);
    else if (v === "next") vwStep(1);
    else if (v === "rot") { VW.rot = (VW.rot + 90) % 360; vwApply(); }
    else if (v === "fit") { VW.z = 1; VW.x = VW.y = 0; vwApply(); }
    else if (v === "folder") api.open_path_folder?.(p);
    else if (v === "conv" || v === "nobg") {
      vwClose();
      const got = await api.convert_info([p]); cvOpen(got);
      if (v === "nobg") setTimeout(() => { CV.target = "img:nobg"; cvRender(); }, 60);
    }
  });
  document.addEventListener("keydown", (e) => {
    if (!VW.el || VW.el.hidden) return;
    const k = e.key;
    if (k === "Escape") vwClose(); else if (k === "ArrowRight") vwStep(1); else if (k === "ArrowLeft") vwStep(-1);
    else if (k.toLowerCase() === "r") { VW.rot = (VW.rot + 90) % 360; vwApply(); } else if (k === "0") { VW.z = 1; VW.x = VW.y = 0; vwApply(); }
    else if (k === "+" || k === "=") { VW.z = Math.min(12, VW.z * 1.2); vwApply(); } else if (k === "-") { VW.z = Math.max(0.1, VW.z / 1.2); vwApply(); }
    else return;
    e.preventDefault(); e.stopPropagation();
  }, true);
}
async function vwLoad() {
  const p = VW.list[VW.i]; if (!p) return;
  VW.z = 1; VW.x = VW.y = 0; VW.rot = 0;
  $("#kvwName").textContent = p.split(/[\\/]/).pop();
  $("#kvwInfo").textContent = vwL("yükleniyor…", "loading…");
  const r = await slow("image_data", p);
  if (VW.list[VW.i] !== p) return;
  if (!r?.ok) { $("#kvwInfo").textContent = vwL("Açılamadı", "Can't open"); return; }
  $("#kvwImg").src = r.url;
  const ex = Object.entries(r.exif || {}).map(([k, v]) => `${k}: ${v}`).join(" · ");
  $("#kvwInfo").textContent = `${r.w}×${r.h} · ${fmtBytes(r.size)} · ${VW.i + 1}/${VW.list.length}${ex ? " · " + ex : ""}`;
  vwApply();
}
function vwApply() { const img = $("#kvwImg"); if (img) img.style.transform = `translate(${VW.x}px, ${VW.y}px) scale(${VW.z}) rotate(${VW.rot}deg)`; }
function vwStep(d) { if (VW.list.length < 2) return; VW.i = (VW.i + d + VW.list.length) % VW.list.length; vwLoad(); }
function vwClose() { if (VW.el) { VW.el.hidden = true; $("#kvwImg").src = ""; } }

// kartta cift tik (gorsel) + alt cubukta "Goruntule"
$("#skTrack")?.addEventListener("dblclick", (e) => {
  const b = e.target.closest(".sk-strip"); const d = b && state.items.find((x) => String(x.id) === b.dataset.id);
  if (d && d.status === "complete" && VW_EXT.test(d.filename || "")) vwOpen(d.path);
});
const _vwBar = skRenderBar;
skRenderBar = function (d) {   // eslint-disable-line no-global-assign
  _vwBar(d);
  if (!d || d.status !== "complete" || !VW_EXT.test(d.filename || "") || $("#skBar .sk-rename")) return;
  const b = document.createElement("button");
  b.className = "sk-btn pri";
  b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 16l5-5 4 4 3-3 6 6"/></svg>${vwL("Görüntüle", "View")}`;
  b.onclick = (ev) => { ev.stopPropagation(); vwOpen(d.path); };
  $("#skBar .sk-bar-info")?.after(b);
};
window.KPAL = window.KPAL || [];

window.KPAL.push(() => [{ ic: "◎", t: "Kami Lens: " + vwL("ekrandan alan seçip ara", "search a screen region"), sub: "Ctrl+Shift+L", run: () => api.picture_open("screen", true) }]);

window.KPAL.push(() => [
  { ic: "⏺", t: vwL("Ekran kaydı başlat / durdur", "Start / stop screen recording"), sub: "Alt+F9", run: () => api.rec_toggle() },
  { ic: "⟲", t: vwL("Son anları klip olarak kaydet", "Save last moments as a clip"), sub: "Alt+F10", run: () => api.rec_save_replay() },
  { ic: "📁", t: vwL("Kami Klipler klasörü", "Kami Clips folder"), sub: vwL("kayıtlar", "recordings"), run: () => api.rec_open_folder() },
]);
window.KPAL.push(() => [{ ic: "📖", t: "Kami Reader", sub: vwL("manga, çizgi roman, PDF", "manga, comics, PDF"), run: () => api.reader_show("") }]);
// indirilen manga/PDF: alt cubukta "Oku" -> Kami Reader; cift tikla da acar
const RD_EXT = /\.(pdf|cbz|cbr|cb7|cbt)$/i;
const _rdBar = skRenderBar;
skRenderBar = function (d) {   // eslint-disable-line no-global-assign
  _rdBar(d);
  if (!d || d.status !== "complete" || !RD_EXT.test(d.filename || "") || $("#skBar .sk-rename")) return;
  const b = document.createElement("button");
  b.className = "sk-btn pri";
  b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 5a2 2 0 0 1 2-2h5v18H6a2 2 0 0 1-2-2zM20 5a2 2 0 0 0-2-2h-5v18h5a2 2 0 0 0 2-2z"/></svg>${vwL("Oku", "Read")}`;
  b.onclick = (ev) => { ev.stopPropagation(); api.reader_show(d.path); };
  $("#skBar .sk-bar-info")?.after(b);
};
document.addEventListener("dblclick", (e) => {
  const b = e.target.closest(".sk-strip"); const d = b && state.items.find((x) => String(x.id) === b.dataset.id);
  if (d && d.status === "complete" && RD_EXT.test(d.filename || "")) api.reader_show(d.path);
});
