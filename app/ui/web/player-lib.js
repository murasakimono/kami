// Kami Player eklentileri: siradakiler + kutuphane + oynatma listeleri (sag cekmece), ayarlar paneli
// (altyazi gorunumu, goruntu: oran/kirpma/zoom/renk, ses: normallestirme / gece modu), siradaki bolum geri sayimi.
"use strict";

const PX = {
  queue: [], qi: -1, pending: null, nextShown: false, nextCancel: false, lib: null, libTab: "queue", libSeries: null,
  cfg: { langs: "tr,en", trEngine: "nllb", dialog: false, delay: 0, xfade: 0, assStyle: "orig", ocrLang: "auto", dictClick: true, lyrics: true, lrclib: true, karaoke: true, glow: true, sub: { size: "m", color: "#ffffff", bg: "semi", pos: 0 }, vid: { aspect: "auto", zoom: 100, bright: 100, contrast: 100, sat: 100, rot: 0, flip: false }, audio: "off" },
};
const pxBase = (p) => String(p).split(/[\\/]/).pop().replace(/\.[^.]+$/, "");
const pxSave = () => { try { localStorage.setItem("kami.player", JSON.stringify(PX.cfg)); } catch { /* yok */ } };
try { const c = JSON.parse(localStorage.getItem("kami.player") || "null"); if (c) PX.cfg = { ...PX.cfg, ...c, sub: { ...PX.cfg.sub, ...c.sub }, vid: { ...PX.cfg.vid, ...c.vid } }; } catch { /* varsayilan */ }

// ---------- kurulum (player.js plBuild sonunda cagirir) ----------
window.plOnBuild = () => {
  const p = $("#player");
  p.insertAdjacentHTML("beforeend", `
    <div class="pl-panel" id="plPanel" hidden></div>
    <div class="pl-next" id="plNextCard" hidden><span>${plL("Sıradaki", "Up next")}</span><b id="plNextName"></b>
      <div><button class="pl-b pri" id="plNextNow">${plL("Şimdi oynat", "Play now")} <i id="plNextSec"></i></button><button class="pl-b" id="plNextNo">${plL("İptal", "Cancel")}</button></div></div>`);
  $("#plNextNow").onclick = () => { $("#plNextCard").hidden = true; plQueueStep(1); };
  $("#plNextNo").onclick = () => { PX.nextCancel = true; $("#plNextCard").hidden = true; };
  $("#plVideo").addEventListener("timeupdate", pxNextWatch);
  $("#plAud").addEventListener("change", (e) => pxPrefSave({ a: plLang(PL.info.audio[+e.target.value]?.lang) }));
  $("#plRate").addEventListener("change", (e) => pxPrefSave({ rate: +e.target.value }));
  window.addEventListener("resize", pxApplyVideo);
  pxApplyAll();
};

// ---------- dil + klasor/dizi basina tercih (ses dili, altyazi, 2. altyazi, hiz) ----------
const pxDir = (p) => String(p || "").replace(/[\\/][^\\/]*$/, "");
const pxPrefs = () => { try { return JSON.parse(localStorage.getItem("kami.prefs") || "{}"); } catch { return {}; } };
function pxPrefSave(patch) {
  if (!PL.info?.path) return;
  const all = pxPrefs(), k = pxDir(PL.info.path);
  all[k] = { ...(all[k] || {}), ...patch };
  try { localStorage.setItem("kami.prefs", JSON.stringify(all)); } catch { /* yok */ }
}
window.plPickTracks = (r) => {
  const pref = pxPrefs()[pxDir(r.path)] || {};
  PX.applying = true;
  // ses izi: tercih edilen dil
  if (pref.a && r.audio.length > 1) {
    const ai = r.audio.findIndex((a) => plLang(a.lang) === pref.a);
    if (ai > 0) { $("#plAud").value = String(ai); plAudio(ai); }
  }
  // altyazi: klasor tercihi > dil sirasi (Ayarlar) > dosyanin varsayilan izi
  const order = pref.s ? [pref.s] : PX.cfg.langs.split(",").map((x) => x.trim()).filter(Boolean);
  let si = -1;
  if (pref.s !== "off") {
    for (const L of order) { si = PL.subList.findIndex((x) => x.lang === L && !x.forced); if (si >= 0) break; }
    if (si < 0) si = PL.subList.findIndex((x) => x.def);
    if (si < 0 && PL.subList.length && !pref.s) si = 0;
  }
  $("#plSub").value = String(si); plLoadSub(si);
  if (pref.s2 && pref.s2 !== "off") { const s2 = PL.subList.findIndex((x, i) => x.lang === pref.s2 && i !== si); if (s2 >= 0) plLoadSub(s2, 2); }
  if (pref.rate) { $("#plVideo").playbackRate = pref.rate; $("#plRate").value = String(pref.rate); }
  PX.applying = false;
  if (r.kind === "video") pxOfferTranslate();
};
// Turkce altyazi yoksa ama baska metin altyazi varsa: kucuk teklif cipi (dil sirasinin basi tr ise)
function pxOfferTranslate() {
  if (!PL.subList.length || PX.cfg.langs.split(",")[0] !== "tr" || PL.subList.some((x) => x.lang === "tr")) return;
  const chip = document.createElement("button");
  chip.className = "pl-chip"; chip.textContent = plL("Türkçe altyazı yok · çevir", "No Turkish subtitles · translate");
  chip.onclick = () => { chip.remove(); pxTranslate(); };
  $("#player").appendChild(chip); setTimeout(() => chip.remove(), 8000);
}
// kaymis altyaziyi sese hizala (ffsubsync): secili altyazinin yerine hizali olani koyar
async function pxSync() {
  const it = PL.subList[PL.subIdx];
  if (!it) { toast(plL("Önce bir altyazı seç", "Select a subtitle first"), true); return; }
  if ($("#plPanel")) $("#plPanel").hidden = true;
  toast(plL("Altyazı sese hizalanıyor…", "Syncing subtitles to audio…"));
  let r;
  try { r = await slow("subtitle_sync", PL.info.path, await (await fetch(it.url)).text(), it.lang || ""); }
  catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) { toast(plL("Hizalanamadı: ", "Sync failed: ") + (r?.error || "?"), true); return; }
  it.url = URL.createObjectURL(new Blob([r.vtt], { type: "text/vtt" }));
  it.raw = "";   // hizali surum duz metin
  PL.subShift = 0; window.plOnShift?.();
  await plLoadSub(PL.subIdx);
  toast(plL("Altyazı hizalandı, dosyanın yanına kaydedildi", "Subtitles synced and saved next to the file"));
}

async function pxTranslate() {
  const it = PL.subList[PL.subIdx >= 0 ? PL.subIdx : PL.subList.findIndex((x) => x.lang === "en")] || PL.subList[0];
  if (!it) { toast(plL("Çevrilecek altyazı yok", "No subtitle to translate"), true); return; }
  if ($("#plPanel")) $("#plPanel").hidden = true;
  toast(plL(`Altyazı çevriliyor (${PX.cfg.trEngine === "google" ? "Google" : "NLLB"})…`, "Translating subtitles…"));
  let r;
  try {
    const text = await (await fetch(it.url)).text();
    r = await slow("subtitle_translate", PL.info.path, text, it.lang || "en", PX.cfg.trEngine);
  } catch (e) { r = { ok: false, error: String(e) }; }
  if (!r || !r.ok) {
    toast(plL("Çeviri başarısız: ", "Translation failed: ") + ({ tool_missing: plL("önce Whisper aracını kur (Ayarlar)", "install the Whisper tool first") }[r?.error] || r?.error || "?"), true);
    return;
  }
  const url = URL.createObjectURL(new Blob([r.vtt], { type: "text/vtt" }));
  PL.subList.push({ label: plL("Türkçe (çeviri)", "Turkish (translated)"), url, raw: "", lang: "tr" });
  const i = PL.subList.length - 1;
  $("#plSub").insertAdjacentHTML("beforeend", `<option value="${i}">${escapeHtml(PL.subList[i].label)}</option>`);
  $("#plSub").hidden = false; $("#plSub").value = String(i);
  const prev = PL.subIdx;
  await plLoadSub(i);
  if (prev >= 0 && PX.cfg.dualOnTranslate !== false) plLoadSub(prev, 2);   // orijinal ustte kalsin (DUAL)
  toast(plL("Türkçe altyazı hazır, dosyanın yanına kaydedildi", "Turkish subtitles ready, saved next to the file"));
}

window.plOnSubChange = () => { if (!PX.applying && PL.open) pxPrefSave({ s: PL.subIdx < 0 ? "off" : PL.subList[PL.subIdx]?.lang || "" }); };
window.plOnShift = () => { if ($("#pxShift")) $("#pxShift").textContent = (PL.subShift > 0 ? "+" : "") + PL.subShift.toFixed(1) + " sn"; };

// ---------- siradakiler ----------
window.plPlayQueue = (paths, i = 0) => {
  PX.pending = paths.slice(); playerOpenPath(paths[i]);
  if ($("#plDrawer")) $("#plDrawer").hidden = true;   // secilen oynasin, cekmece kapansin
};
window.plOnStart = async (r) => {
  PX.nextShown = false; PX.nextCancel = false; $("#plNextCard").hidden = true;
  if (!r.path) { PX.queue = []; PX.qi = -1; $("#plPrev").disabled = $("#plNext").disabled = true; pxApplyAll(); return; }   // uzak akis
  if (PX.pending && PX.pending.includes(r.path)) { PX.queue = PX.pending; PX.pending = null; }
  else if (!PX.queue.includes(r.path)) {
    try { PX.queue = await api.player_siblings(r.path); } catch { PX.queue = [r.path]; }
  }
  PX.qi = PX.queue.indexOf(r.path);
  $("#plPrev").disabled = PX.qi <= 0; $("#plNext").disabled = PX.qi < 0 || PX.qi >= PX.queue.length - 1;
  pxApplyAll();
  const dr = $("#plDrawer");
  if (dr && !dr.hidden && PX.libTab === "queue") pxDrawerRender();
};
window.plQueueStep = (d) => {
  const i = PX.qi + d;
  if (i < 0 || i >= PX.queue.length) return;
  PX.pending = PX.queue; playerOpenPath(PX.queue[i]);
};
function pxNextWatch() {   // son 10 sn: siradaki bolum karti + geri sayim
  if (!PL.open || PL.info.kind !== "video" || PX.nextCancel || PX.qi < 0 || PX.qi >= PX.queue.length - 1 || !PL.dur) return;
  const left = PL.dur - plNow();
  if (left <= 10 && left > 0) {
    if (!PX.nextShown) { PX.nextShown = true; $("#plNextName").textContent = pxBase(PX.queue[PX.qi + 1]); $("#plNextCard").hidden = false; }
    $("#plNextSec").textContent = `(${Math.ceil(left)})`;
  }
}
window.plOnEnded = () => {
  if (PX.qi >= 0 && PX.qi < PX.queue.length - 1 && !PX.nextCancel) { $("#plNextCard").hidden = true; plQueueStep(1); }
};

// ---------- sag cekmece: siradakiler / kutuphane / listeler ----------
window.plDrawer = (tab) => {
  let d = $("#plDrawer");
  if (!d) {
    d = document.createElement("aside"); d.id = "plDrawer"; d.hidden = true;
    d.innerHTML = `<div class="px-tabs">
        <button data-tab="queue">${plL("Sıradakiler", "Queue")}</button><button data-tab="lib">${plL("Kütüphane", "Library")}</button><button data-tab="albums">${plL("Albümler", "Albums")}</button><button data-tab="lists">${plL("Listeler", "Playlists")}</button>
        <button class="px-x" data-tab="close">✕</button></div><div class="px-body" id="pxBody"></div>`;
    document.body.appendChild(d);
    d.addEventListener("click", pxDrawerClick);
  }
  if ($("#plPanel")) $("#plPanel").hidden = true;
  if (tab) PX.libTab = tab;
  else if (!d.hidden) { d.hidden = true; return; }
  d.hidden = false;
  if (!PL.open && PX.libTab === "queue") PX.libTab = "lib";
  pxDrawerRender();
};
window.plPanelClose = () => {
  const d = $("#plDrawer"), p = $("#plPanel");
  if (d && !d.hidden) { d.hidden = true; return true; }
  if (p && !p.hidden) { p.hidden = true; return true; }
  return false;
};
async function pxDrawerRender() {
  const body = $("#pxBody");
  $$("#plDrawer .px-tabs [data-tab]").forEach((b) => b.classList.toggle("on", b.dataset.tab === PX.libTab));
  const row = (path, i, cur, extra = "") => `<button class="px-row ${cur ? "cur" : ""}" data-play="${i}">${extra}<span>${escapeHtml(pxBase(path))}</span></button>`;
  if (PX.libTab === "queue") {
    body.innerHTML = PX.queue.length
      ? `<div class="px-list">${PX.queue.map((p, i) => row(p, i, i === PX.qi, `<i>${i + 1}</i>`)).join("")}</div>
         <div class="px-save"><input id="pxName" placeholder="${plL("Liste adı", "Playlist name")}"><button class="pl-b" data-act="saveq">${plL("Listeye kaydet", "Save as playlist")}</button></div>`
      : `<p class="px-empty">${plL("Sırada bir şey yok.", "Nothing queued.")}</p>`;
    PX.view = PX.queue;
    return;
  }
  if (PX.libTab === "lists") {
    const lists = await api.playlist_get();
    const names = Object.keys(lists);
    body.innerHTML = names.length ? names.map((n) => `<div class="px-card"><button class="px-row" data-list="${escapeHtml(n)}"><span>${escapeHtml(n)}</span><small>${lists[n].length}</small></button><button class="pl-b" data-del="${escapeHtml(n)}">✕</button></div>`).join("")
      : `<p class="px-empty">${plL("Henüz liste yok. Sıradakiler sekmesinden kaydedebilirsin.", "No playlists yet. Save one from the Queue tab.")}</p>`;
    body.insertAdjacentHTML("beforeend", `<button class="pl-b" data-act="addfolder" style="margin-top:12px">📁 ${plL("Klasörü liste olarak ekle", "Add a folder as playlist")}</button>
      <p class="px-hint">${plL("Klasör listesi her açılışta klasörün güncel içeriğini çalar; klasöre eklediğin yeni dosyalar da gelir.", "Folder playlists always play the folder's current contents.")}</p>`);
    PX.lists = lists;
    return;
  }
  if (PX.libTab === "albums") { pxAlbums(body); return; }
  // kutuphane
  if (!PX.lib) { body.innerHTML = `<p class="px-empty">${plL("Taranıyor…", "Scanning…")}</p>`; try { PX.lib = typeof slow === "function" ? await slow("library_get") : await api.library_get(); } catch (e) { body.innerHTML = `<p class="px-empty">${escapeHtml(String(e))}</p>`; return; } }
  const L = PX.lib;
  if (PX.libSeries) {
    const s = L.series.find((x) => x.name === PX.libSeries);
    if (s) {
      body.innerHTML = `<button class="px-back" data-act="back">‹ ${escapeHtml(s.name)}</button><div class="px-list">${s.paths.map((p, i) => row(p, i, PL.open && PL.info.path === p, `<i>${i + 1}</i>`)).join("")}</div>`;
      PX.view = s.paths;
      return;
    }
    PX.libSeries = null;
  }
  const recent = L.items.filter((x) => !x.series).sort((a, b) => b.mtime - a.mtime).slice(0, 40);
  PX.view = recent.map((x) => x.path);
  body.innerHTML = `
    ${L.series.length ? `<h4>${plL("Diziler", "Series")}</h4><div class="px-grid">${L.series.map((s) => `<button class="px-series" data-series="${escapeHtml(s.name)}"><b>${escapeHtml(s.name)}</b><small>${s.count} ${plL("bölüm", "eps")}${s.seasons.length > 1 ? " · " + s.seasons.length + plL(" sezon", " seasons") : ""}</small></button>`).join("")}</div>` : ""}
    <h4>${plL("Son eklenenler", "Recently added")}</h4>
    <div class="px-list">${recent.map((x, i) => row(x.path, i, false, `<i class="k-${x.kind}">${x.kind === "audio" ? "♪" : "▶"}</i>`)).join("") || `<p class="px-empty">${plL("Medya bulunamadı.", "No media found.")}</p>`}</div>
    <h4>${plL("Klasörler", "Folders")}</h4>
    <div class="px-dirs">${L.dirs.map((d) => `<div><span title="${escapeHtml(d)}">${escapeHtml(d)}</span>${d === L.base ? `<small>${plL("indirme", "downloads")}</small>` : `<button class="pl-b" data-rmdir="${escapeHtml(d)}">✕</button>`}</div>`).join("")}
      <button class="pl-b" data-act="adddir">+ ${plL("Klasör ekle", "Add folder")}</button><button class="pl-b" data-act="rescan">${plL("Yeniden tara", "Rescan")}</button></div>`;
}
// ---------- albumler (B7): kapak izgarasi -> album sayfasi ----------
async function pxAlbums(body) {
  if (!PX.albums) {
    body.innerHTML = `<p class="px-empty">${plL("Müzik taranıyor… (ilk sefer biraz sürebilir)", "Scanning music… (first time can take a while)")}</p>`;
    let r;
    try { r = await slow("library_albums"); } catch (e) { r = { ok: false, error: String(e) }; }
    if (!r?.ok) { body.innerHTML = `<p class="px-empty">${escapeHtml(r?.error || "?")}</p>`; return; }
    PX.albums = r.albums;
    if (PX.libTab !== "albums") return;
  }
  const A = PX.albums;
  const cover = (a, cls) => `<div class="${cls}" style="${a.cover ? `background-image:url('${a.cover}')` : ""}">${a.cover ? "" : "♪"}</div>`;
  const name = (a) => a.single ? plL("Tekli parçalar", "Singles") : a.album;
  if (PX.album != null && A[PX.album]) {
    const a = A[PX.album];
    PX.view = a.tracks.map((x) => x.path);
    body.innerHTML = `<button class="px-back" data-act="aback">‹ ${plL("Albümler", "Albums")}</button>
      <div class="px-ahead">${cover(a, "px-acover big")}<div><b>${escapeHtml(name(a))}</b><span>${escapeHtml(a.artist || "")}</span><small>${a.count} ${plL("parça", "tracks")}</small>
        <div class="px-aacts"><button class="pl-b pri" data-act="aplay">▶ ${plL("Oynat", "Play")}</button><button class="pl-b" data-act="ashuf">⤮ ${plL("Karıştır", "Shuffle")}</button></div></div></div>
      <div class="px-list">${a.tracks.map((x, i) => `<button class="px-row ${PL.open && PL.info?.path === x.path ? "cur" : ""}" data-play="${i}"><i>${x.track || i + 1}</i><span>${escapeHtml(x.title)}${a.single || (x.artist && x.artist !== a.artist) ? `<small> · ${escapeHtml(x.artist || "")}</small>` : ""}</span></button>`).join("")}</div>`;
    return;
  }
  PX.album = null;
  body.innerHTML = A.length ? `<div class="px-agrid">${A.map((a, i) => `<button class="px-acard" data-album="${i}">${cover(a, "px-acover")}<b>${escapeHtml(name(a))}</b><small>${escapeHtml(a.artist || "")} · ${a.count}</small></button>`).join("")}</div>
      <button class="pl-b" data-act="rescan" style="margin-top:12px">${plL("Yeniden tara", "Rescan")}</button>`
    : `<p class="px-empty">${plL("Kütüphane klasörlerinde müzik bulunamadı. Kütüphane sekmesinden klasör ekleyebilirsin.", "No music found. Add folders from the Library tab.")}</p>`;
}

async function pxDrawerClick(e) {
  const t = e.target.closest("button"); if (!t) return;
  if (t.dataset.tab) { if (t.dataset.tab === "close") $("#plDrawer").hidden = true; else { PX.libTab = t.dataset.tab; PX.libSeries = null; PX.album = null; pxDrawerRender(); } return; }
  if (t.dataset.play != null) { plPlayQueue(PX.view, +t.dataset.play); return; }
  if (t.dataset.album != null) { PX.album = +t.dataset.album; pxDrawerRender(); $("#pxBody").scrollTop = 0; return; }
  if (t.dataset.series) { PX.libSeries = t.dataset.series; pxDrawerRender(); return; }
  if (t.dataset.list) { const l = PX.lists[t.dataset.list]; if (l?.length) plPlayQueue(l, 0); return; }
  if (t.dataset.del) { await api.playlist_delete(t.dataset.del); pxDrawerRender(); return; }
  if (t.dataset.rmdir) { await api.library_remove_dir(t.dataset.rmdir); PX.lib = null; pxDrawerRender(); return; }
  const act = t.dataset.act;
  if (act === "back") { PX.libSeries = null; pxDrawerRender(); }
  if (act === "adddir") { const r = await api.library_add_dir(); if (r.ok) { PX.lib = null; pxDrawerRender(); } }
  if (act === "rescan") { PX.lib = null; PX.albums = null; pxDrawerRender(); }
  if (act === "aback") { PX.album = null; pxDrawerRender(); }
  if (act === "addfolder") { const r = await api.playlist_add_folder(); if (r?.ok) { toast(plL("Liste eklendi: ", "Playlist added: ") + r.name); pxDrawerRender(); } }
  if (act === "aplay" || act === "ashuf") {
    const a = PX.albums?.[PX.album]; if (!a) return;
    let paths = a.tracks.map((x) => x.path);
    if (act === "ashuf") paths = paths.map((p) => [Math.random(), p]).sort((x, y) => x[0] - y[0]).map((x) => x[1]);
    plPlayQueue(paths, 0);
  }
  if (act === "saveq") {
    const name = $("#pxName").value.trim(); if (!name) { $("#pxName").focus(); return; }
    await api.playlist_save(name, PX.queue); toast(plL("Liste kaydedildi", "Playlist saved")); PX.libTab = "lists"; pxDrawerRender();
  }
}

// ---------- ayarlar paneli ----------
window.plSettings = () => {
  const p = $("#plPanel");
  if (!p.hidden) { p.hidden = true; return; }
  if ($("#plDrawer")) $("#plDrawer").hidden = true;
  const c = PX.cfg;
  const seg = (group, key, opts) => `<div class="px-seg" data-g="${group}" data-k="${key}">${opts.map(([v, l]) => `<button data-v="${v}" class="${String(c[group][key]) === String(v) ? "on" : ""}">${l}</button>`).join("")}</div>`;
  const rng = (key, min, max, label) => `<label class="px-rng"><span>${label}</span><input type="range" data-vk="${key}" min="${min}" max="${max}" value="${c.vid[key]}"><b>${c.vid[key]}%</b></label>`;
  p.innerHTML = `
    <h4>${plL("Altyazı", "Subtitles")}</h4>
    <div class="px-shift"><span>${plL("ASS altyazı", "ASS subtitles")}</span><div class="px-seg" data-g="ass" style="margin:0">${[["orig", plL("Orijinal stil", "Original style")], ["kami", plL("Kami stili", "Kami style")]].map(([v, l]) => `<button data-v="${v}" class="${c.assStyle === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
    <p class="px-hint">${plL("Orijinal stilde renk, boyut ve konum dosyadan gelir; aşağıdaki ayarlar Kami stilinde ve düz altyazılarda geçerli.", "Original style keeps the file's look; settings below apply to Kami style and plain subtitles.")}</p>
    ${seg("sub", "size", [["s", "S"], ["m", "M"], ["l", "L"], ["xl", "XL"]])}
    ${seg("sub", "color", [["#ffffff", plL("Beyaz", "White")], ["#ffe066", plL("Sarı", "Yellow")], ["#2EE6A6", plL("Zümrüt", "Emerald")], ["#C4B5FD", plL("Lavanta", "Lavender")]])}
    ${seg("sub", "bg", [["none", plL("Gölge", "Shadow")], ["semi", plL("Yarı saydam", "Semi")], ["solid", plL("Koyu", "Solid")]])}
    ${seg("sub", "pos", [[0, plL("Alt", "Bottom")], [60, plL("Biraz yukarı", "Raised")], [140, plL("Yukarı", "High")]])}
    <label class="px-rng"><span>${plL("2. altyazı (DUAL)", "2nd subtitle (DUAL)")}</span><select class="pl-sel" id="pxSub2" style="grid-column: span 2"><option value="-1">${plL("Kapalı", "Off")}</option>${(PL.subList || []).map((x, i) => `<option value="${i}" ${i === PL.sub2Idx ? "selected" : ""}>${escapeHtml(x.label)}</option>`).join("")}</select></label>
    <div class="px-shift"><span>${plL("Kaydır (G / H)", "Offset (G / H)")}</span><button class="pl-b" data-act="sh-">−0.5</button><b id="pxShift">${(PL.subShift > 0 ? "+" : "") + (PL.subShift || 0).toFixed(1)} sn</b><button class="pl-b" data-act="sh+">+0.5</button><button class="pl-b" data-act="sh0">0</button></div>
    <div class="px-shift"><span>${plL("Müzik klibi: şarkı sözlerini altyazı yap", "Music video: lyrics as subtitles")}</span><button class="pl-b" onclick="window.pmPasteVideoLyrics?.(); document.getElementById('plPanel').hidden = true;">${plL("Yapıştır", "Paste")}</button></div>
    <div class="px-shift"><span>${plL("Kaymış altyazıyı sese hizala", "Auto-sync subtitles to audio")}</span><button class="pl-b" data-act="sync">${plL("Hizala", "Sync")}</button></div>
    <div class="px-shift"><span>${plL("Türkçeye çevir", "Translate to Turkish")}</span>
      <div class="px-seg" data-g="tr" style="margin:0">${[["nllb", "NLLB"], ["google", "Google"]].map(([v, l]) => `<button data-v="${v}" class="${c.trEngine === v ? "on" : ""}">${l}</button>`).join("")}</div>
      <button class="pl-b" data-act="translate">${plL("Çevir", "Translate")}</button></div>
    <p class="px-hint">${plL("NLLB: bilgisayarında çalışır, tutarlı (ilk kullanımda ~1.4 GB iner). Google: hızlı, internet ister.", "NLLB: runs locally, consistent (~1.4 GB first time). Google: fast, needs internet.")}</p>
    <label class="px-rng"><span>${plL("Dil sırası", "Language order")}</span><input class="px-in" id="pxLangs" value="${escapeHtml(c.langs)}" placeholder="tr,en,ja" style="grid-column: span 2"></label>
    ${pxBool("dictClick", plL("Kelimeye tıkla → sözlük", "Click a word → dictionary"))}
    <p class="px-hint">${plL("Açıkken altyazıdaki kelimeye tıklayınca video durur ve anlamı açılır.", "When on, clicking a subtitle word pauses and shows its meaning.")}</p>
    <div class="px-shift"><span>${plL("Ekran yazısı dili (O)", "On-screen text language (O)")}</span></div>
    <div class="px-seg" data-g="ocr">${[["auto", plL("Otomatik", "Auto")], ["en", "English"], ["tr", "Türkçe"], ["ja", "日本語"]].map(([v, l]) => `<button data-v="${v}" class="${c.ocrLang === v ? "on" : ""}">${l}</button>`).join("")}</div>
    <h4>${plL("Görüntü", "Picture")}</h4>
    ${seg("vid", "aspect", [["auto", plL("Otomatik", "Auto")], ["16/9", "16:9"], ["4/3", "4:3"], ["21/9", "21:9"], ["fill", plL("Doldur", "Fill")]])}
    ${rng("zoom", 100, 160, plL("Yakınlaştır / kırp", "Zoom / crop"))}${rng("bright", 50, 150, plL("Parlaklık", "Brightness"))}${rng("contrast", 50, 150, plL("Kontrast", "Contrast"))}${rng("sat", 0, 200, plL("Doygunluk", "Saturation"))}
    ${window.pxExtraVideoHtml?.() || ""}
    <button class="pl-b" data-act="vreset">${plL("Görüntüyü sıfırla", "Reset picture")}</button>
    <h4>${plL("Ses", "Audio")}</h4>
    <div class="px-seg" data-g="audio">${[["off", plL("Kapalı", "Off")], ["norm", plL("Normalleştir", "Normalize")], ["night", plL("Gece modu", "Night mode")]].map(([v, l]) => `<button data-v="${v}" class="${c.audio === v ? "on" : ""}">${l}</button>`).join("")}</div>
    <p class="px-hint">${plL("Gece modu patlamaları kısar, fısıltıları yükseltir. Ses kaydırıcısı %200'e kadar çıkar.", "Night mode tames explosions and lifts whispers. Volume goes up to 200%.")}</p>
    <div class="px-shift"><span>${plL("5.1 → kulaklık (diyalog öne)", "5.1 → headphones (dialogue first)")}</span><div class="px-seg" data-g="dialog" style="margin:0">${[["0", plL("Kapalı", "Off")], ["1", plL("Açık", "On")]].map(([v, l]) => `<button data-v="${v}" class="${(c.dialog ? "1" : "0") === v ? "on" : ""}">${l}</button>`).join("")}</div></div>
    <label class="px-rng"><span>${plL("Sesi geciktir", "Delay audio")}</span><input type="range" data-ak="delay" min="0" max="1000" step="10" value="${c.delay}"><b>${c.delay} ms</b></label>
    ${window.pxExtraAudioHtml?.() || ""}
    <h4>${plL("Müzik", "Music")}</h4>
    ${pxBool("lyrics", plL("Şarkı sözü paneli", "Lyrics panel"))}
    ${pxBool("lrclib", plL("Sözleri internette ara (LRCLIB)", "Search lyrics online (LRCLIB)"))}
    ${pxBool("karaoke", plL("Karaoke dolgusu", "Karaoke fill"))}
    ${pxBool("glow", plL("Kapak rengiyle parla", "Glow with cover color"))}
    <div class="px-shift"><span>${plL("Şarkı geçişi", "Track transition")}</span></div>
    <div class="px-seg" data-g="xfade">${[[0, plL("Boşluksuz", "Gapless")], [3, "Crossfade 3 sn"], [6, "6 sn"], [10, "10 sn"]].map(([v, l]) => `<button data-v="${v}" class="${+c.xfade === v ? "on" : ""}">${l}</button>`).join("")}</div>
    <p class="px-hint">${plL("Sıra: şarkının yanındaki .lrc / .txt → dosyanın içindeki sözler → LRCLIB. Bulunamazsa ✎ ile yapıştırabilirsin.", "Order: sidecar .lrc / .txt → embedded lyrics → LRCLIB. Otherwise paste with ✎.")}</p>
    <h4>${plL("Kısayollar", "Shortcuts")}</h4>
    <div class="px-keys">${pxKeysHtml()}</div>
    <button class="pl-b" data-act="keyreset">${plL("Varsayılana dön", "Reset to defaults")}</button>
    <h4>${plL("Genel", "General")}</h4>
    <button class="pl-b" data-act="default">${plL("Varsayılan oynatıcı yap (Windows ayarları)", "Make default player (Windows settings)")}</button>
    ${window.pxExtraToolsHtml?.() || ""}`;
  pxTabify(p);
  p.hidden = false;
  p.onclick = async (e) => {
    const b = e.target.closest("button"); if (!b) return;
    const segEl = b.closest(".px-seg");
    if (segEl) {
      const g = segEl.dataset.g, v = b.dataset.v;
      if (segEl.dataset.b) { c[segEl.dataset.b] = v === "1"; pxSave(); pxBoolApply(segEl.dataset.b); segEl.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b)); return; }
      if (g === "audio") c.audio = v; else if (g === "tr") c.trEngine = v; else if (g === "ocr") c.ocrLang = v; else if (g === "xfade") c.xfade = +v;
      else if (g === "ass") { c.assStyle = v; pxSave(); if (PL.open && PL.subIdx >= 0) plLoadSub(PL.subIdx); }
      else if (g === "dialog") { c.dialog = v === "1"; pxSave(); if (PL.open) { if (PL.mode === "direct" && plDialogMix()) PL.mode = "remux"; plModeUi(); plSeek(plNow(), !$("#plVideo").paused); } } else c[g][segEl.dataset.k] = segEl.dataset.k === "pos" ? +v : v;
      segEl.querySelectorAll("button").forEach((x) => x.classList.toggle("on", x === b));
      pxSave(); pxApplyAll();
    }
    if (b.dataset.act === "translate") pxTranslate();
    if (b.dataset.key) pxCaptureKey(b);
    if (b.dataset.act === "keyreset") { try { localStorage.removeItem("kami.keys"); } catch { /* yok */ } $(".px-keys").innerHTML = pxKeysHtml(); }
    if (b.dataset.act === "sync") pxSync();
    if (b.dataset.act === "sh-") plShift(-0.5);
    if (b.dataset.act === "sh+") plShift(0.5);
    if (b.dataset.act === "sh0") plShift(0);
    if (b.dataset.act === "vreset") { Object.assign(c.vid, { aspect: "auto", zoom: 100, bright: 100, contrast: 100, sat: 100, rot: 0, flip: false }); pxSave(); pxApplyAll(); p.hidden = true; plSettings(); }
    if (b.dataset.act === "default") { const ok = await api.player_default_apps(); if (!ok) toast(plL("Windows ayarları açılamadı", "Couldn't open Windows settings"), true); }
  };
  p.onchange = (e) => {
    if (e.target.id === "pxSub2") { const i = +e.target.value; plLoadSub(i, 2); pxPrefSave({ s2: i < 0 ? "off" : PL.subList[i]?.lang || "" }); }
    if (e.target.id === "pxLangs") { c.langs = e.target.value.toLowerCase().replace(/\s+/g, ""); pxSave(); }
  };
  p.oninput = (e) => {
    if (e.target.dataset.ak === "delay") {
      c.delay = +e.target.value; e.target.nextElementSibling.textContent = c.delay + " ms"; pxSave(); window.plApplyAudio(); return;
    }
    const k = e.target.dataset.vk; if (!k) return;
    c.vid[k] = +e.target.value; e.target.nextElementSibling.textContent = c.vid[k] + "%";
    pxSave(); pxApplyVideo();
  };
};

function pxBool(key, label) {
  const on = PX.cfg[key] !== false;
  return `<div class="px-shift"><span>${label}</span><div class="px-seg" data-b="${key}" style="margin:0">${[["0", plL("Kapalı", "Off")], ["1", plL("Açık", "On")]].map(([v, l]) => `<button data-v="${v}" class="${(on ? "1" : "0") === v ? "on" : ""}">${l}</button>`).join("")}</div></div>`;
}
function pxBoolApply(key) {
  if (key === "dictClick") { const b = $("#plSubs"); if (b) b.dataset.h = ""; }
  if (["lyrics", "lrclib", "glow"].includes(key) && PL.open && PL.info) window.plMusicStart?.(PL.info);
}
// h4 basliklarini sekmelere cevir (Altyazi | Goruntu | Ses | Muzik | Kisayollar | Genel); son sekme hatirlanir
function pxTabify(p) {
  const kids = [...p.children];
  const tabs = [];
  let sec = null;
  for (const el of kids) {
    if (el.tagName === "H4") {
      sec = document.createElement("section"); sec.className = "px-sec"; sec.dataset.t = String(tabs.length);
      tabs.push(el.textContent); el.replaceWith(sec);
    } else if (sec) sec.appendChild(el);
  }
  const bar = document.createElement("nav");
  bar.className = "px-ptabs";
  bar.innerHTML = tabs.map((t, i) => `<button data-tab="${i}">${escapeHtml(t)}</button>`).join("");
  p.prepend(bar);
  const show = (i) => {
    i = Math.max(0, Math.min(tabs.length - 1, +i || 0));
    PX.tab = i; try { localStorage.setItem("kami.ptab", String(i)); } catch { /* yok */ }
    bar.querySelectorAll("button").forEach((b) => b.classList.toggle("on", +b.dataset.tab === i));
    p.querySelectorAll(".px-sec").forEach((s) => { s.hidden = +s.dataset.t !== i; });
  };
  bar.addEventListener("click", (e) => { const b = e.target.closest("button[data-tab]"); if (b) { e.stopPropagation(); show(b.dataset.tab); } });
  let last = PX.tab;
  if (last == null) { try { last = +localStorage.getItem("kami.ptab") || 0; } catch { last = 0; } }
  show(last);
}

function pxApplyAll() { pxApplySub(); pxApplyVideo(); window.plApplyAudio(); }
function pxApplySub() {
  const el = $("#player"); if (!el) return;
  const s = PX.cfg.sub;
  el.style.setProperty("--sub-size", { s: "0.8", m: "1", l: "1.25", xl: "1.55" }[s.size] || "1");
  el.style.setProperty("--sub-color", s.color);
  el.style.setProperty("--sub-bg", { none: "transparent", semi: "rgba(8,7,12,.62)", solid: "rgba(8,7,12,.92)" }[s.bg] || "rgba(8,7,12,.62)");
  el.style.setProperty("--sub-pos", s.pos + "px");
}
function pxApplyVideo() {
  const v = $("#plVideo"); if (!v) return;
  const c = PX.cfg.vid;
  v.style.filter = `brightness(${c.bright}%) contrast(${c.contrast}%) saturate(${c.sat}%)`;
  v.style.transform = c.zoom !== 100 ? `scale(${c.zoom / 100})` : "";
  if (c.aspect === "auto" || c.aspect === "fill") {
    Object.assign(v.style, { width: "", height: "", left: "", top: "", objectFit: c.aspect === "fill" ? "cover" : "contain" });
  } else {   // zorla oran: kutu o oranda, goruntu kutuya gerilir
    const [a, b] = c.aspect.split("/").map(Number), W = innerWidth, H = innerHeight;
    const w = Math.min(W, H * a / b), h = w * b / a;
    Object.assign(v.style, { width: w + "px", height: h + "px", left: (W - w) / 2 + "px", top: (H - h) / 2 + "px", objectFit: "fill" });
  }
}
window.plDialogMix = () => !!(PX.cfg.dialog && PL.info && PL.info.kind === "video" && (PL.info.audio[PL.audio]?.channels || 0) >= 6);
// kisayol listesi: her eylem icin atanmis tus(lar); tiklayinca yeni tus beklenir
function pxKeyName(k) { return ({ " ": plL("Boşluk", "Space"), arrowleft: "←", arrowright: "→", arrowup: "↑", arrowdown: "↓", escape: "Esc" })[k] || k.toUpperCase(); }
function pxKeysHtml() {
  const km = plKeymap();
  return Object.entries(PL_ACTIONS).map(([act, [tr, en]]) => {
    const keys = Object.keys(km).filter((k) => km[k] === act);
    return `<div><span>${plL(tr, en)}</span><button class="pl-b" data-key="${act}">${keys.map(pxKeyName).join(" / ") || "—"}</button></div>`;
  }).join("");
}
function pxCaptureKey(btn) {
  btn.textContent = plL("Bir tuşa bas…", "Press a key…"); PL.capture = true;
  const on = (e) => {
    e.preventDefault(); e.stopPropagation();
    document.removeEventListener("keydown", on, true); PL.capture = false;
    const key = e.key.toLowerCase();
    if (key !== "escape" || btn.dataset.key === "close") {
      let user = {}; try { user = JSON.parse(localStorage.getItem("kami.keys") || "{}"); } catch { /* bos */ }
      const km = plKeymap();
      for (const k of Object.keys(km)) if (km[k] === btn.dataset.key && k !== key) user[k] = "";   // eski tusu bosalt
      user[key] = btn.dataset.key;
      try { localStorage.setItem("kami.keys", JSON.stringify(user)); } catch { /* yok */ }
    }
    $(".px-keys").innerHTML = pxKeysHtml();
  };
  document.addEventListener("keydown", on, true);
}
window.plApplyAudio = () => {
  if (PL.delay) PL.delay.delayTime.setTargetAtTime((PX.cfg.delay || 0) / 1000, PL.ctx.currentTime, 0.02);
  if (!PL.comp) return;
  const m = PX.cfg.audio, C = PL.comp, t = PL.ctx.currentTime;
  const set = (th, knee, ratio, att, rel, g) => {
    C.threshold.setValueAtTime(th, t); C.knee.setValueAtTime(knee, t); C.ratio.setValueAtTime(ratio, t);
    C.attack.setValueAtTime(att, t); C.release.setValueAtTime(rel, t); PL.gain.gain.setTargetAtTime(g, t, 0.05);
  };
  if (m === "night") set(-42, 12, 12, 0.003, 0.25, 2.6);
  else if (m === "norm") set(-26, 20, 4, 0.01, 0.3, 1.6);
  else set(0, 0, 1, 0.01, 0.25, 1);
};

// Sunak'tan kutuphane: doka dugme
if (typeof SK !== "undefined") {
  const dock = $("#skDock");
  dock?.insertAdjacentHTML("afterbegin", `<button data-sk="library" title="${plL("Kütüphane (Kami Player)", "Library (Kami Player)")}"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h4v16H4zM10 4h4v16h-4zM16 5l4 1-3 14-4-1z"/></svg></button>`);
  dock?.addEventListener("click", (e) => { if (e.target.closest('[data-sk="library"]')) { e.stopImmediatePropagation(); if (!$("#player")) plBuild(); plDrawer("lib"); } }, true);
}
