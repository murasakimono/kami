"use strict";
// Kami Studio sol paneller: medya, ses/meme, metin, altyazi, efekt, gecis, zoom, abone, akilli araclar, eklentiler.
const PANELS = {
  media: "Proje", sound: "Ses & Meme", text: "Metin", graphics: "Grafik", captions: "Altyazı", fx: "Efektler", trans: "Geçişler",
  zoom: "Zoom", subscribe: "Abone ol", templates: "Şablonlar", ai: "Akıllı araçlar", plugins: "Eklentiler & Claude",
};
const PANEL_IC = { media: "▦", sound: "♪", text: "T", graphics: "◆", captions: "≡", fx: "✦", trans: "⇋", zoom: "⊕", subscribe: "🔔", templates: "❖", ai: "✧", plugins: "⧉" };
$("#libtabs").innerHTML = Object.entries(PANELS).map(([k, v]) => `<button data-panel="${k}" title="${v}"><i>${PANEL_IC[k]}</i>${v.split(" ")[0]}</button>`).join("");
let panel = "media";
const pb = $("#panelBody");

function renderPanel(name) {
  if (name) panel = name;
  $$("#libtabs button").forEach(b => b.classList.toggle("on", b.dataset.panel === panel));
  $("#panelTitle").textContent = PANELS[panel];
  $("#panelTools").innerHTML = "";
  (P[panel] || (() => ""))();
}
$("#libtabs").addEventListener("click", e => {
  const b = e.target.closest("[data-panel]"); if (!b) return;
  renderPanel(b.dataset.panel);
});
const sec = t => `<div class="sec">${t}</div>`;
const firstSel = () => selClips()[0];
function needSel(kinds) {
  const c = firstSel();
  if (c && (!kinds || kinds.includes(clipKind(c)))) return c;
  const fb = ST.p.clips.find(x => (!kinds || kinds.includes(clipKind(x))) && ST.t >= x.start && ST.t < x.start + x.dur);
  if (fb) return fb;
  toast("Önce zaman çizelgesinde bir klip seç"); return null;
}

// ---------------------------------------------------------------- medya
const P = {};
P.media = async () => {
  $("#panelTools").innerHTML = `<button class="tb" id="impBtn">＋ İçe aktar</button>`;
  $("#impBtn").onclick = async () => { const ps = await api.studio_pick_media(); if (ps?.length) importPaths(ps); };
  const as = Object.entries(ST.p.assets);
  let h = as.length ? "" : `<div class="hint">Dosyaları pencereye sürükle-bırak ya da “İçe aktar”. Video, ses, resim ve GIF olur.<br>İlk eklenenler zaman çizelgesine kendiliğinden dizilir.</div>`;
  h += `<div class="bin">${as.map(([id, a]) => {
    const m = ST.media[a.path], bg = a.kind === "image" || a.gif ? `background-image:url('${a.url}')` : m?.thumbs?.sprite ? `background-image:url(${m.thumbs.sprite});background-size:${(m.thumbs.count || 16) * 100}% 100%;background-position:${100 / ((m.thumbs.count || 16) - 1) * 2}% 0` : "";
    return `<div class="asset ${a.kind}${a.missing ? " missing" : ""}${ST.binSel.has(id) ? " sel" : ""}" draggable="true" data-aid="${id}" style="${bg}" title="${esc(a.path)}">
      <button class="ad" data-add="${id}" title="Oynatma kafasına ekle">＋</button>${a.kind !== "image" || a.gif ? `<span class="du">${fmt(a.dur, false)}</span>` : ""}<span class="nm">${esc(a.name)}</span></div>`;
  }).join("")}</div>`;
  const rec = await api.studio_recent();
  if (rec.length) h += sec("Son projeler") + rec.slice(0, 8).map(r => `<div class="snd" data-open="${esc(r.path)}"><b>${esc(r.name || r.path.split(/[\\/]/).pop())}</b><button title="Aç">↗</button></div>`).join("");
  pb.innerHTML = h;
};
pb.addEventListener("dragstart", e => {
  const a = e.target.closest("[data-aid]"); if (a) { e.dataTransfer.setData("text/kami-asset", a.dataset.aid); e.dataTransfer.effectAllowed = "copy"; return; }
  const it = e.target.closest("[data-item]"); if (it) { e.dataTransfer.setData("text/kami-item", it.dataset.item); e.dataTransfer.effectAllowed = "copy"; }
});
pb.addEventListener("click", async e => {
  const add = e.target.closest("[data-add]");
  if (add) { e.stopPropagation(); const aid = add.dataset.add, a = ST.p.assets[aid]; dropAsset(aid, ST.t, null); return; }
  const as = e.target.closest("[data-aid]");
  if (as) { const id = as.dataset.aid; e.ctrlKey || e.shiftKey ? (ST.binSel.has(id) ? ST.binSel.delete(id) : ST.binSel.add(id)) : (ST.binSel = new Set([id])); renderPanel(); return; }
  const op = e.target.closest("[data-open]"); if (op) { openProject(op.dataset.open); return; }
});
pb.addEventListener("dblclick", e => { const as = e.target.closest("[data-aid]"); if (as) dropAsset(as.dataset.aid, ST.t, null); });

// ---------------------------------------------------------------- ses & meme
let sndTab = "kami", sndCache = {}, sndAudio = null;
const slots = (() => { try { return JSON.parse(localStorage.kstSlots || "{}"); } catch { return {}; } })();
const saveSlots = () => { try { localStorage.kstSlots = JSON.stringify(slots); } catch { } };
P.sound = async () => {
  $("#panelTools").innerHTML = `<button class="tb" id="sndDir" title="Klasörü aç">📁</button>`;
  $("#sndDir").onclick = () => api.studio_open_folder(sndTab === "Memeler" ? "Memeler" : "Sesler");
  const tabs = [["kami", "Kami SFX"], ["Sesler", "Seslerim"], ["Memeler", "Memelerim"], ["myinstants", "Myinstants"], ["freesound", "Freesound"], ["pack", "Paketler"]];
  let h = `<div class="tabs">${tabs.map(([k, l]) => `<button data-tab="${k}" class="${sndTab === k ? "on" : ""}">${l}</button>`).join("")}</div>`;
  const sl = Object.entries(slots);
  if (sl.length) h += sec("Hızlı (1-9 tuşu)") + `<div class="chips">${sl.sort().map(([k, s]) => `<span class="chip">${k} · ${esc(s.name.slice(0, 18))}<button data-unslot="${k}">✕</button></span>`).join("")}</div>`;
  if (sndTab === "kami") {
    pb.innerHTML = h + `<div class="hint">Kami'nin kendi ürettiği telifsiz efektler (tık, whoosh, boom, zil, riser…). Sürükle ya da ＋.</div><div id="sndList" class="hint">Hazırlanıyor…</div>`;
    const items = await job("studio_sfx", []);
    sndRender(items.map(i => ({ ...i, local: true })));
  } else if (sndTab === "Sesler" || sndTab === "Memeler") {
    h += `<div class="hint">${sndTab === "Sesler" ? "Videolar\\Kami Studio\\Sesler" : "Videolar\\Kami Studio\\Memeler"} klasörüne attığın her şey burada. İnternetten seçtiklerin de buraya iner.</div><input class="in" id="sndQ" placeholder="Ara…">`;
    pb.innerHTML = h + `<div id="sndList" class="hint">Yükleniyor…</div>`;
    const items = sndCache[sndTab] = await api.studio_library(sndTab);
    sndRender(items.map(i => ({ ...i, local: true })));
    $("#sndQ").oninput = e => sndRender(items.filter(i => i.name.toLowerCase().includes(e.target.value.toLowerCase())).map(i => ({ ...i, local: true })));
  } else if (sndTab === "myinstants" || sndTab === "freesound") {
    const fsNeed = sndTab === "freesound" && !ST.cat.freesound;
    h += fsNeed ? `<div class="hint">Freesound için ücretsiz API anahtarı gerekir: freesound.org → hesabın → API (“Apply for API key”). Anahtar Windows'ta şifreli saklanır.</div><div class="row"><input class="in" id="fsKey" placeholder="API anahtarı"><button class="tb" id="fsSave">Kaydet</button></div>`
      : `<div class="row"><input class="in" id="sndQ" placeholder="${sndTab === "myinstants" ? "ör. bruh, vine boom, ayy, oof" : "ör. whoosh, impact, horror"}" style="flex:1"><button class="tb" id="sndGo" style="flex:none">Ara</button></div>`;
    pb.innerHTML = h + `<div id="sndList"></div>`;
    if (fsNeed) { $("#fsSave").onclick = async () => { await api.studio_freesound_key($("#fsKey").value); ST.cat.freesound = true; renderPanel(); }; return; }
    const go = async () => {
      const q = $("#sndQ").value.trim() || (sndTab === "myinstants" ? "meme" : "whoosh");
      $("#sndList").innerHTML = '<div class="hint">Aranıyor…</div>';
      const r = await job(sndTab === "myinstants" ? "studio_myinstants" : "studio_freesound", [q]);
      if (r[0]?.error) { $("#sndList").innerHTML = `<div class="hint">Olmadı: ${esc(r[0].error)}</div>`; return; }
      sndCache[sndTab] = r; sndRender(r.map(i => ({ ...i, kind: "audio" })));
    };
    $("#sndGo").onclick = go; $("#sndQ").onkeydown = e => { if (e.key === "Enter") go(); };
    if (sndCache[sndTab]) sndRender(sndCache[sndTab].map(i => ({ ...i, kind: "audio" })));
  } else {
    const items = await api.studio_pack_sounds();
    pb.innerHTML = h + (items.length ? `<div id="sndList"></div>` : `<div class="hint">Eklenti paketlerinden gelen sesler burada. Eklenti panelinden paket ekle.</div>`);
    if (items.length) sndRender(items.map(i => ({ ...i, kind: "audio" })));
  }
};
function sndRender(items) {
  const box = $("#sndList"); if (!box) return;
  box.className = "";
  box.innerHTML = items.length ? items.slice(0, 200).map(i => {
    const d = JSON.stringify({ type: "sound", path: i.path || "", url: i.url, name: i.name, kind: i.kind, local: !!i.local });
    return `<div class="snd" draggable="true" data-item='${esc(d)}'><button data-prev="${esc(i.url)}" title="Dinle">${i.kind === "audio" ? "▶" : "👁"}</button><b title="${esc(i.name)}">${esc(i.name)}</b>` +
      `<button data-star title="Hızlı tuşa ata">★</button><button data-put title="Oynatma kafasına ekle">＋</button></div>`;
  }).join("") : '<div class="hint">Bir şey yok.</div>';
}
pb.addEventListener("click", async e => {
  const t = e.target.closest("[data-tab]"); if (t) { sndTab = t.dataset.tab; renderPanel(); return; }
  const us = e.target.closest("[data-unslot]"); if (us) { delete slots[us.dataset.unslot]; saveSlots(); renderPanel(); return; }
  const pv = e.target.closest("[data-prev]");
  if (pv) {
    const row = pv.closest("[data-item]"), it = JSON.parse(row.dataset.item);
    if (it.kind !== "audio") { modal(`<h3>${esc(it.name)}</h3>${it.kind === "video" ? `<video src="${esc(it.url)}" autoplay loop controls style="width:100%"></video>` : `<img src="${esc(it.url)}" style="max-width:100%">`}<div class="row"><button class="tb pri" data-v="ok">Kapat</button></div>`); return; }
    if (sndAudio && !sndAudio.paused && sndAudio.dataset.u === pv.dataset.prev) { sndAudio.pause(); return; }
    sndAudio?.pause(); sndAudio = new Audio(pv.dataset.prev); sndAudio.dataset.u = pv.dataset.prev; sndAudio.play().catch(() => toast("Çalınamadı")); return;
  }
  const put = e.target.closest("[data-put]"); if (put) { dropItem(JSON.parse(put.closest("[data-item]").dataset.item), ST.t); return; }
  const st = e.target.closest("[data-star]");
  if (st) {
    const it = JSON.parse(st.closest("[data-item]").dataset.item);
    const k = await modal(`<h3>Hızlı tuş: ${esc(it.name)}</h3><div class="hint">Zaman çizelgesindeyken bu tuşa basınca oynatma kafasına eklenir.</div><div class="grid3">${[1, 2, 3, 4, 5, 6, 7, 8, 9].map(n => `<button class="tb" data-v="${n}">${n}${slots[n] ? " · " + esc(slots[n].name.slice(0, 8)) : ""}</button>`).join("")}</div>`);
    if (k) { slots[k] = it; saveSlots(); renderPanel(); toast(`${k} tuşu: ${it.name}`); }
  }
});
async function soundAsset(it) {
  let path = it.path;
  if (!it.local || !path) {
    busy("İndiriliyor: " + it.name);
    const r = await job("studio_fetch_sound", [it.url, it.name, sndTab === "freesound" ? "Freesound" : sndTab === "pack" ? "Paket" : "Myinstants"]);
    busy(null);
    if (!r?.ok) { toast("İndirilemedi: " + r?.error); return null; }
    path = r.path; sndCache.Sesler = null;
  }
  const ids = await importPaths([path]);
  return ids[0];
}
async function dropItem(it, t, tid) {
  if (it.type === "sound") {
    const aid = await soundAsset(it); if (!aid) return;
    const a = ST.p.assets[aid]; snap();
    let c;
    if (a.kind === "audio") c = placeAt({ asset: aid, dur: a.dur, in: 0 }, "audio", t);
    else c = placeAt({ asset: aid, dur: a.kind === "image" && !a.gif ? 2.5 : a.dur, in: 0, fit: "contain", scale: .55 }, "video", t);
    if (tid && ST.p.tracks.find(x => x.id === tid)?.kind === trackOf(c).kind) { c.track = tid; resolveOverlap(c); }
    ST.sel = new Set([c.id]); changed();
  } else if (it.type === "text") addText(it.preset, t);
  else if (it.type === "fx") addFxClip(it.id, t);
  else if (it.type === "sub") addSub(it.kind, t);
  else if (it.type === "gfx") addGfx(it.kind, t);
}
window.dropItem = dropItem;
window.quickSlot = n => { const s = slots[n]; if (s) dropItem(s, ST.t); else toast(`${n} tuşu boş — Ses panelinde ★ ile ata`); };

// ---------------------------------------------------------------- metin
const TEXT_PRESETS = [
  { n: "Başlık", s: { font: "Chakra Petch", size: 9, anim: "pop", pos: "center", outline: 6 } },
  { n: "Alt başlık", s: { font: "Chakra Petch", size: 5, anim: "slide", pos: "bottom", outline: 4 } },
  { n: "Meme üst", s: { font: "Impact", size: 9, anim: "none", pos: "top", outline: 9, bold: false }, up: true },
  { n: "Meme alt", s: { font: "Impact", size: 9, anim: "none", pos: "bottom", outline: 9, bold: false }, up: true },
  { n: "Neon", s: { font: "Chakra Petch", size: 8, anim: "fade", pos: "center", color: "#2EE6A6", glow: true, glowColor: "#2EE6A6", outline: 1, outlineColor: "#0b3d2c" } },
  { n: "Glitch", s: { font: "Rubik Glitch", size: 9, anim: "glitch", pos: "center", color: "#ffffff", outline: 3, outlineColor: "#ff2e88" } },
  { n: "Daktilo", s: { font: "Consolas", size: 5, anim: "type", pos: "bottom", outline: 3 } },
  { n: "Korku", s: { font: "Damnation", size: 10, anim: "shake", pos: "center", color: "#d10000", glow: true, glowColor: "#ff0000", outline: 2 } },
  { n: "RAGE", s: { font: "Impact", size: 13, anim: "shake", pos: "center", color: "#ff2a2a", outline: 8, bold: false }, up: true },
  { n: "Zıpla", s: { font: "Arial Black", size: 8, anim: "bounce", pos: "center", color: "#FFE600", outline: 7 } },
  { n: "Sinematik", s: { font: "Georgia", size: 4.2, anim: "fade", pos: "center", spacing: 14, outline: 0, shadow: 3, bold: false, italic: true } },
  { n: "Kutulu", s: { font: "Segoe UI", size: 5, anim: "pop", pos: "bottom", box: true, boxColor: "#000000", outline: 0 } },
  { n: "Büyüyen", s: { font: "Chakra Petch", size: 10, anim: "zoom", pos: "center", outline: 6 } },
  { n: "Yorum", s: { font: "Comic Sans MS", size: 5.5, anim: "pop", pos: "custom", x: .72, y: .25, color: "#000000", box: true, boxColor: "#ffffff", outline: 0, rot: -6 } },
];
P.text = () => {
  pb.innerHTML = `<div class="hint">Tıkla: oynatma kafasına ekler. Sürükle: istediğin yere. Ayrıntılar sağdaki panelde.</div>` +
    `<div class="grid2">${TEXT_PRESETS.map((p, i) => `<div class="card" draggable="true" data-item='${esc(JSON.stringify({ type: "text", preset: i }))}' data-tp="${i}" style="font-family:'${p.s.font}';color:${p.s.color || "#fff"};${p.s.glow ? `text-shadow:0 0 8px ${p.s.glowColor}` : ""};${p.s.box ? `background:${p.s.boxColor};` : ""}font-size:15px;text-align:center">${esc(p.up ? p.n.toUpperCase() : p.n)}</div>`).join("")}</div>`;
};
pb.addEventListener("click", e => { const tp = e.target.closest("[data-tp]"); if (tp && panel === "text") addText(+tp.dataset.tp, ST.t); });
function addText(i, t) {
  const p = TEXT_PRESETS[i]; snap();
  const c = placeAt({ text: p.up ? "ÜST YAZI" : p.n === "RAGE" ? "AAAAAA!" : "Yazını yaz", dur: 3, style: { ...p.s } }, "text", t);
  ST.sel = new Set([c.id]); changed(); setTimeout(() => $("#insp textarea")?.select(), 50);
}

// ---------------------------------------------------------------- grafik
P.graphics = () => {
  pb.innerHTML = `<div class="hint">Hareketli grafikler (vektör, her çözünürlükte keskin). Tıkla: oynatma kafasına ekler; yazıları sağdan değiştir.</div>` +
    `<div class="grid2">${Object.entries(ST.cat.graphics || {}).map(([k, v]) => `<div class="card" data-gfx="${k}" draggable="true" data-item='${esc(JSON.stringify({ type: "gfx", kind: k }))}'><b>${esc(v)}</b></div>`).join("")}</div>`;
};
pb.addEventListener("click", e => { const g = e.target.closest("[data-gfx]"); if (g && panel === "graphics") addGfx(g.dataset.gfx, ST.t); });
const GFX_DEF = { lower: { title: "İsim Soyisim", sub: "Unvan", x: .07, y: .8 }, "lower-min": { title: "İsim", sub: "Unvan", x: .07, y: .82 }, location: { title: "İstanbul, Türkiye", x: .06, y: .1 },
  chapter: { num: "01", title: "BÖLÜM", x: .5, y: .5 }, endscreen: {}, callout: { title: "Burası!", x: .5, y: .45 }, progress: {}, highlight: { title: "ÖNEMLİ", x: .5, y: .5 },
  counter: { from: 0, to: 1000, x: .5, y: .5 }, quote: { title: "Alıntı", sub: "Kişi", x: .5, y: .5 } };
function addGfx(kind, t) { snap(); const c = placeAt({ graphic: kind, dur: kind === "endscreen" ? 20 : kind === "progress" ? Math.max(5, projEnd() - t) : 4, style: { ...(GFX_DEF[kind] || {}) } }, "text", t); ST.sel = new Set([c.id]); changed(); }

// ---------------------------------------------------------------- sablonlar
P.templates = () => {
  let groups = {};
  for (const t of ST.cat.templates || []) (groups[t.group] ||= []).push(t);
  const ft = (ST.cat.templates || []).filter(t => isFav("tpl", t.id));
  if (ft.length) groups = { "★ Favoriler": ft, ...groups };
  pb.innerHTML = `<div class="hint">Tek tıkla hazır kurgu parçaları (yazı + efekt + ses). Oynatma kafasına eklenir, hepsi düzenlenebilir. ❄ olanlar seçili video klibe uygulanır.</div>` +
    Object.entries(groups).map(([g, items]) => sec(g) + `<div class="grid2">${items.map(t => `<div class="card" data-tpl="${t.id}"><b>${t.needs ? "❄ " : ""}${esc(t.name)}</b>${favStar("tpl", t.id)}</div>`).join("")}</div>`).join("");
};
async function applyTemplate(id, t = ST.t) {
  const c = selClips()[0];
  busy("Şablon ekleniyor…");
  const p = clone(ST.p);
  const r = await job("studio_template", [p, id, t, c?.id || ""]); busy(null);
  if (!r.ok) { toast(r.error || "olmadı", 3500); return; }
  snap(); ST.p = r.project; for (const a of Object.values(ST.p.assets)) prepAsset(a);
  ST.sel = new Set(r.added.slice(0, 1)); changed();
}
window.applyTemplate = applyTemplate;
pb.addEventListener("click", e => { const t = e.target.closest("[data-tpl]"); if (t && panel === "templates") applyTemplate(t.dataset.tpl); });

// ---------------------------------------------------------------- altyazi
P.captions = () => {
  const c = firstSel();
  pb.innerHTML = `<div class="hint">Konuşmayı Whisper ile kelime kelime yazıya döker; her kelime söylendiği anda belirir. Önce konuşmanın olduğu klibi seç.</div>` +
    `<label class="fld w2"><span>Dil</span><select class="in" id="capLang"><option value="auto">Otomatik</option><option value="tr">Türkçe</option><option value="en">İngilizce</option></select></label>` +
    sec("Stil") + `<div class="grid2">${Object.entries(ST.cat.captions).map(([k, v]) => `<div class="card${k === (localStorage.kstCap || "hormozi") ? " on" : ""}" data-cap="${k}"><b>${esc(v)}</b></div>`).join("")}</div>` +
    `<div class="row" style="margin-top:12px"><button class="tb pri" id="capGo">≡ ${c ? "Seçili klibe altyazı" : "Altyazı oluştur"}</button></div>` +
    `<div class="hint">Yazım hatalarını sağ paneldeki “Kelimeler” kutusundan düzeltebilirsin.</div>`;
  $("#capGo").onclick = () => aiAction("captions", firstSel());
};
pb.addEventListener("click", e => {
  const cp = e.target.closest("[data-cap]"); if (!cp) return;
  try { localStorage.kstCap = cp.dataset.cap; } catch { }
  const c = firstSel(); if (c?.words) { snap(); c.style = { ...(c.style || {}), caption: cp.dataset.cap }; changed(); }
  renderPanel();
});

// ---------------------------------------------------------------- efektler
let fxThumb = "";
P.fx = () => {
  try { const cv = document.createElement("canvas"); cv.width = 160; cv.height = 90; cv.getContext("2d").drawImage($("#view"), 0, 0, 160, 90); fxThumb = cv.toDataURL("image/jpeg", .7); } catch { fxThumb = ""; }
  const packs = {};
  for (const [id, f] of Object.entries(ST.cat.fx)) (packs[f.pack] ||= []).push([id, f]);
  const c = firstSel(), on = new Set(c?.fx || []);
  const q = (P.fx.q || "").toLowerCase();
  const card = ([id, f]) => `<div class="card${on.has(id) ? " on" : ""}" data-fx="${id}" draggable="true" data-item='${esc(JSON.stringify({ type: "fx", id }))}'><div class="sw" style="${fxThumb ? `background-image:url(${fxThumb});` : ""}filter:${f.css || "none"}"></div><b>${esc(f.name)}</b>${favStar("fx", id)}</div>`;
  const all = Object.entries(ST.cat.fx).filter(([id, f]) => !q || f.name.toLowerCase().includes(q) || f.pack.toLowerCase().includes(q));
  const favs = all.filter(([id]) => isFav("fx", id));
  pb.innerHTML = `<div class="hint">${c && ["video", "image"].includes(clipKind(c)) ? "Tıkla: seçili klibe uygula / kaldır. Sağ panelden Tümü / Giriş / Çıkış seç." : "Klip seçili değil: tıklayınca efekt izine (tüm görüntüye) 3 sn eklenir."} Sürükle: efekt izine istediğin yere. ★: favori.</div>` +
    `<input class="in" id="fxQ" placeholder="${Object.keys(ST.cat.fx).length} efekt içinde ara…" value="${esc(P.fx.q || "")}" style="width:100%;margin-bottom:6px">` +
    (favs.length ? sec("★ Favoriler") + `<div class="grid2">${favs.map(card).join("")}</div>` : "") +
    Object.entries(packs).map(([pk, items]) => { const it = items.filter(x => all.includes(x) || all.some(y => y[0] === x[0])); return it.length ? sec(pk) + `<div class="grid2">${it.map(card).join("")}</div>` : ""; }).join("");
  const qi = $("#fxQ"); qi.oninput = () => { P.fx.q = qi.value; clearTimeout(P.fx.t); P.fx.t = setTimeout(() => { P.fx(); const n = $("#fxQ"); n.focus(); n.setSelectionRange(n.value.length, n.value.length); }, 180); };
};
pb.addEventListener("click", e => {
  const f = e.target.closest("[data-fx]"); if (!f || panel !== "fx") return;
  const id = f.dataset.fx, c = firstSel();
  snap();
  if (c && ["video", "image"].includes(clipKind(c))) {
    for (const x of selClips().filter(x => ["video", "image"].includes(clipKind(x)))) {
      const s = new Set(x.fx || []); s.has(id) ? s.delete(id) : s.add(id); x.fx = [...s]; if (!x.fx.length) delete x.fx;
    }
    changed(); renderPanel();
  } else addFxClip(id, ST.t, true);
});
function addFxClip(id, t, snapped) {
  if (!snapped) snap();
  const c = placeAt({ mode: id, dur: 3 }, "fx", t); ST.sel = new Set([c.id]); changed();
}

// ---------------------------------------------------------------- gecisler
P.trans = () => {
  pb.innerHTML = `<div class="hint">Seçili klibin girişine uygulanır (önceki klipten bu klibe geçerken). Süreyi sağ panelden ayarla.</div><div class="grid2">${Object.entries(ST.cat.trans).map(([k, v]) => `<div class="card" data-tr="${k}"><b>${esc(v)}</b></div>`).join("")}</div>` +
    `<div class="row" style="margin-top:10px"><button class="tb" id="trAll">Seçili tüm kesimlere uygula</button></div>`;
  $("#trAll").onclick = () => toast("Önce klipleri seç (Shift+tık), sonra geçişe tıkla");
};
pb.addEventListener("click", e => {
  const t = e.target.closest("[data-tr]"); if (!t) return;
  const cs = selClips().filter(c => ["video", "image"].includes(clipKind(c)));
  if (!cs.length) { toast("Önce bir video klibi seç"); return; }
  snap(); for (const c of cs) { if (t.dataset.tr === "none") delete c.trans; else c.trans = { in: t.dataset.tr, dur: c.trans?.dur || .35 }; } changed();
});

// ---------------------------------------------------------------- zoom
P.zoom = () => {
  pb.innerHTML = `<div class="hint">Seçili klibe uygular. Kendi zoom'unu sağ panelde kare kare yap, “Şablon kaydet” ile buraya ekle; sonra başka videolara tek tıkla uygula.</div>` +
    sec("Hazır") + `<div class="grid2">${ST.cat.zoom.filter(z => !z.user).map(z => `<div class="card" data-zm="${z.id}"><b>${esc(z.name)}</b><small>${z.kf.length} kare</small></div>`).join("")}</div>` +
    sec("Benim şablonlarım") + (ST.cat.zoom.some(z => z.user) ? `<div class="grid2">${ST.cat.zoom.filter(z => z.user).map(z => `<div class="card" data-zm="${z.id}"><b>${esc(z.name)}</b><small>${z.kf.length} kare · <a href="#" data-zdel="${z.id}" style="color:var(--red)">sil</a></small></div>`).join("")}</div>` : '<div class="hint">Henüz yok.</div>') +
    sec("Vuruşa zoom") + `<div class="hint">İşaretli her vuruşta seçili klibe kısa “vuruş zoom” kareleri ekler.</div><div class="row"><button class="tb" id="zBeat">⊕ Vuruşlarda zoom</button></div>`;
  $("#zBeat").onclick = () => aiAction("beatzoom", firstSel());
};
pb.addEventListener("click", async e => {
  const d = e.target.closest("[data-zdel]");
  if (d) { e.preventDefault(); e.stopPropagation(); const left = await api.studio_template_delete(d.dataset.zdel); ST.cat.zoom = [...ST.cat.zoom.filter(z => !z.user), ...left]; renderPanel(); return; }
  const z = e.target.closest("[data-zm]"); if (!z) return;
  const tpl = ST.cat.zoom.find(x => x.id === z.dataset.zm);
  const cs = selClips().filter(c => ["video", "image"].includes(clipKind(c)));
  if (!cs.length) { toast("Önce bir video klibi seç"); return; }
  snap(); for (const c of cs) c.zoom = clone(tpl.kf); changed();
});

// ---------------------------------------------------------------- abone ol
P.subscribe = () => {
  pb.innerHTML = `<div class="hint">Tıkla: oynatma kafasına 4 sn ekler. Yazıyı, rengi ve konumu sağdan değiştir (ör. “ABONE OL” yerine “SUBSCRIBE”). Önizlemede ekrandaki yeşil kutuyla taşıyabilirsin.</div>` +
    `<div class="grid2">${Object.entries(ST.cat.subscribe).sort((a, b) => isFav("sub", b[0]) - isFav("sub", a[0])).map(([k, v]) => `<div class="card" data-sub="${k}" draggable="true" data-item='${esc(JSON.stringify({ type: "sub", kind: k }))}'><b>${isFav("sub", k) ? "★ " : ""}${esc(v)}</b>${favStar("sub", k)}</div>`).join("")}</div>` +
    `<div class="hint" style="margin-top:10px">Tık ve zil sesleri için “YouTube” şablonlarına bak (Şablonlar sekmesi). Hazır yeşil perde animasyonları: Medya sayfası → Stok → “subscribe green screen”, sonra Perdeyi sil.</div>`;
};
pb.addEventListener("click", e => { const s = e.target.closest("[data-sub]"); if (s && panel === "subscribe") addSub(s.dataset.sub, ST.t); });
function addSub(kind, t) {
  snap(); const pro = kind.startsWith("yt") || ["play-morph", "channel", "folding", "3d", "wave", "meme", "social", "lss"].includes(kind);
  const c = placeAt({ subscribe: kind, dur: pro ? 3.6 : 4, style: { y: kind === "social" ? .5 : .8, x: .5, ...(pro && (kind.startsWith("yt") || kind === "channel") ? { label: "Abone ol", done: "Abone olundu" } : {}) } }, "text", t);
  ST.sel = new Set([c.id]); changed();
}

// ---------------------------------------------------------------- akilli araclar
const AI_TOOLS = [
  ["silence", "Sessizlikleri kırp", "Konuşma arasındaki boşlukları siler, sonrakileri kaydırır (jump cut)."],
  ["freeze", "Boş/donuk sahneleri kırp", "Görüntünün değişmediği bölümleri çıkarır (bekleme ekranı, donmuş kare)."],
  ["scenes", "Sahne değişiminde böl", "Kamera/kurgu geçişlerini bulup klibi oradan böler."],
  ["beats", "Vuruşları bul", "Müzik klibindeki vuruşlara işaret koyar; mıknatıs bunlara yapışır."],
  ["cutbeats", "Vuruşa göre kes", "Seçili video klibini işaretli vuruşlarda böler."],
  ["montage", "Vuruşa montaj", "Medya kutusunda seçtiğin videolardan müziğin vuruşlarına oturan bir edit dizer (AMV/edit)."],
  ["beatzoom", "Vuruşlarda zoom", "Her vuruşta klibe kısa zoom darbesi ekler."],
  ["captions", "Otomatik altyazı", "Whisper ile kelime zamanlı altyazı (kinetik stiller)."],
  ["matte", "Arka planı sil (video)", "Yeşil perde olmadan kişiyi keser (kare kare BiRefNet, ekran kartı). Sonuç şeffaf yeni klip olur."],
  ["splitscreen", "Yan yana (podcast/tepki)", "Seçili iki video klibini ekranı bölerek yan yana (dikeyde üst-alt) dizer."],
  ["reframe", "Dikey çerçeve (yüz takibi)", "Videoyu 9:16 yapar, konuşan yüzü kadrajda tutar."],
];
P.ai = () => {
  pb.innerHTML = `<div class="hint">Önce zaman çizelgesinde klibi seç. Hepsi geri alınabilir (Ctrl+Z).</div>` +
    AI_TOOLS.map(([k, n, d]) => `<div class="card" data-ai="${k}" style="margin-bottom:7px"><b>${n}</b><small>${d}</small></div>`).join("");
};
pb.addEventListener("click", e => { const a = e.target.closest("[data-ai]"); if (a) aiAction(a.dataset.ai, firstSel()); });

async function needTool(r) {
  if (r?.error !== "need_tool") return false;
  const big = r.tool === "whisper" ? "Whisper (~3 GB, model ilk kullanımda iner)" : "IOPaint ortamı (Kami Picture ile ortak, ~4 GB)";
  if (await ask("Araç kurulsun mu?", `Bunun için ${big} gerekli. Şimdi kurulsun mu? Bir kez kurulur.`, "Kur")) {
    const j = await api.studio_ai_install(r.tool);
    try { await waitStudioJob(j.job, "Kuruluyor"); toast("Kuruldu, tekrar dene"); } catch (e) { toast("Kurulamadı: " + e.message, 5000); }
  }
  return true;
}
async function aiAction(kind, c) {
  if (kind === "unreframe") { snap(); delete c.reframe; changed(); return; }
  if (kind === "montage") return montage();
  if (kind === "splitscreen") return splitScreen();
  if (kind === "matte") return selClips().filter(x => clipKind(x) === "video").length > 1 ? window.matteSel() : matte(c);
  if (kind === "beatzoom") return beatZoom(c);
  if (["silence", "freeze", "scenes", "beats", "captions", "reframe", "cutbeats"].includes(kind)) {
    const want = kind === "beats" || kind === "silence" || kind === "captions" ? ["video", "audio"] : ["video"];
    c = c && want.includes(clipKind(c)) ? c : needSel(want); if (!c) return;
  }
  const a = assetOf(c), sp = c.speed || 1, src0 = c.in || 0, srcDur = c.dur * sp;
  try {
    if (kind === "silence") {
      const o = await modal(`<h3>Sessizlikleri kırp</h3><div class="hint">Eşik: bu seviyenin altı sessiz sayılır. Gürültülü kayıtta yükselt (-30), temiz kayıtta düşür (-40).</div>
        <label class="fld"><span>Eşik (dB)</span><input type="range" id="sdb" min="-55" max="-20" value="-35" oninput="sdbn.value=this.value"><input class="num" id="sdbn" value="-35" readonly></label>
        <label class="fld"><span>En kısa (sn)</span><input type="range" id="sml" min="0.2" max="2" step="0.05" value="0.45" oninput="smln.value=this.value"><input class="num" id="smln" value="0.45" readonly></label>
        <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb pri" data-v="ok">Kırp</button></div>`, { collect: () => [+$("#sdb").value, +$("#sml").value] });
      if (!o) return;
      busy("Sessizlikler aranıyor…");
      const rng = await job("studio_silences", [a.path, src0, srcDur, o[0], o[1]]); busy(null);
      if (!rng.length) { toast("Sessizlik bulunamadı"); return; }
      snap(); const n = removeRanges(c, rng); changed(); toast(`${n} sessiz bölüm kırpıldı`);
    } else if (kind === "freeze") {
      busy("Donuk sahneler aranıyor (biraz sürebilir)…");
      const rng = await job("studio_freezes", [a.path, src0, srcDur, 1.0]); busy(null);
      if (!rng.length) { toast("Donuk sahne yok"); return; }
      snap(); const n = removeRanges(c, rng, 0); changed(); toast(`${n} donuk bölüm kırpıldı`);
    } else if (kind === "scenes") {
      busy("Sahne geçişleri aranıyor…");
      const ts = await job("studio_scenes", [a.path, src0, srcDur, .35]); busy(null);
      if (!ts.length) { toast("Sahne değişimi bulunamadı"); return; }
      snap(); let cur = c, n = 0;
      for (const s of ts) { const t = c.start + (s - src0) / sp; const r = splitClip(cur, t); if (r) { cur = r; n++; } }
      changed(); toast(`${n} yerden bölündü`);
    } else if (kind === "beats") {
      busy("Vuruşlar analiz ediliyor…");
      const b = await job("studio_beats", [a.path]); busy(null);
      const mode = await modal(`<h3>Vuruşlar · ${b.bpm} BPM</h3><div class="hint">Izgara: tempoya göre düzenli vuruşlar (${b.beats.length}). Güçlü: davul/bas darbeleri (${b.onsets.length}) — düzensiz parçalar için.</div>
        <div class="row"><button class="tb" data-v="no">Vazgeç</button><button class="tb" data-v="onsets">Güçlü vuruşlar</button><button class="tb pri" data-v="beats">Tempo ızgarası</button></div>`);
      if (!mode) return;
      const ts = b[mode].map(t => +(c.start + (t - src0) / sp).toFixed(3)).filter(t => t >= c.start && t <= c.start + c.dur);
      snap(); ST.p.markers = [...(ST.p.markers || []).filter(m => m.kind !== "beat"), ...ts.map(t => ({ t, kind: "beat" }))]; changed();
      toast(`${ts.length} vuruş işaretlendi (mıknatıs bunlara yapışır)`);
    } else if (kind === "cutbeats") {
      const beats = (ST.p.markers || []).filter(m => m.kind === "beat").map(m => m.t).sort((x, y) => x - y);
      if (!beats.length) { toast("Önce müzik klibinde “Vuruşları bul”"); return; }
      const ev = await modal(`<h3>Vuruşa göre kes</h3><div class="row">${[1, 2, 4, 8].map(n => `<button class="tb" data-v="${n}">Her ${n} vuruşta</button>`).join("")}</div>`);
      if (!ev) return;
      snap(); let cur = c, n = 0;
      for (const t of beats.filter((_, i) => i % +ev === 0)) { const r = splitClip(cur, t); if (r) { cur = r; n++; } }
      changed(); toast(`${n} kesim`);
    } else if (kind === "captions") {
      const lang = $("#capLang")?.value || "auto";
      const r = await api.studio_ai("captions", a.path, src0, srcDur, { lang });
      if (await needTool(r)) return;
      if (!r.ok) { toast("Başlatılamadı: " + r.error); return; }
      const j = await waitStudioJob(r.job, "Altyazı çıkarılıyor (Whisper)");
      const words = (j.result?.words || []).map(w => ({ ...w, s: +(w.s / sp).toFixed(3), e: +(w.e / sp).toFixed(3) }));
      if (!words.length) { toast("Konuşma bulunamadı"); return; }
      snap();
      const t = placeAt({ words, dur: c.dur, style: { caption: localStorage.kstCap || "hormozi" } }, "text", c.start);
      ST.sel = new Set([t.id]); changed(); toast(`${words.length} kelime eklendi`);
    } else if (kind === "reframe") {
      if (ST.p.w > ST.p.h && await ask("Dikey yapılsın mı?", "Proje 9:16 (1080×1920) yapılacak, sonra yüz takibi uygulanacak.", "Dikey yap")) { snap(); ST.p.w = 1080; ST.p.h = 1920; afterLoadPub(); }
      const r = await api.studio_ai("reframe", a.path, src0, srcDur, { ratio: ST.p.w / ST.p.h });
      if (await needTool(r)) return;
      if (!r.ok) { toast("Başlatılamadı: " + r.error); return; }
      const j = await waitStudioJob(r.job, "Yüz takip ediliyor");
      const kf = j.result?.kf || [];
      if (!kf.length) { toast("Yüz/hareket bulunamadı"); return; }
      snap();
      for (const x of ST.p.clips.filter(x => x.asset === c.asset)) { x.reframe = kf; x.fit = "cover"; }
      changed(); toast("Kadraj yüzü takip ediyor");
    }
  } catch (e) { busy(null); toast("Olmadı: " + e.message, 5000); }
}
window.aiAction = aiAction;
async function matte(c, model) {
  c = c && clipKind(c) === "video" ? c : needSel(["video"]); if (!c) return;
  const a = assetOf(c), sp = c.speed || 1, len = c.dur * sp;
  const m = model || await modal(`<h3>Arka planı sil</h3><div class="hint">Yalnız <b>seçili klibin</b> zaman çizelgesinde görünen kısmı işlenir: ${fmt(len)} (kaynakta ${fmt(c.in || 0)} – ${fmt((c.in || 0) + len)}). Videonun geri kalanına dokunulmaz; önce klibi istediğin yerden böl (S), sonra sil.<br>Kare kare ekran kartında işlenir (~${Math.max(1, Math.round(len * 30 * .5 / 60))} dk). Sonuç şeffaf bir kopya olarak klibin yerine geçer, ses korunur, orijinal dosya değişmez.</div>
    <div class="row"><button class="tb" data-v="">Vazgeç</button><button class="tb" data-v="birefnet-general-lite">Hızlı</button><button class="tb pri" data-v="birefnet-general">En iyi kalite</button></div>`);
  if (!m || m === "no") return;
  const r = await api.studio_matte(a.path, c.in || 0, len, m);
  if (await needTool(r)) return;
  if (!r.ok) { toast(r.error || "olmadı"); return; }
  try {
    const j = await waitStudioJob(r.job, "Arka plan siliniyor");
    const i = j.result; snap();
    let aid = "a1", n = 1; while (ST.p.assets[aid]) aid = "a" + (++n);
    ST.p.assets[aid] = { path: i.path, kind: "video", dur: i.dur, w: i.w, h: i.h, audio: i.audio, name: i.name, alpha: true, url: i.url };
    prepAsset(ST.p.assets[aid]);
    c.asset = aid; c.in = 0; delete c.speed; changed(); toast("Arka plan silindi — altına istediğin videoyu/görseli koy");
  } catch (e) { toast("Olmadı: " + e.message, 5000); }
}
function splitScreen() {
  const cs = selClips().filter(c => clipKind(c) === "video");
  if (cs.length !== 2) { toast("Zaman çizelgesinde iki video klibi seç (Shift+tık)"); return; }
  snap(); const vert = ST.p.h > ST.p.w;
  cs.forEach((c, i) => { c.fit = "cover"; c.scale = .5; if (vert) { c.x = 0; c.y = i ? .25 : -.25; c.scale = 1; c.crop = "half-h"; } else { c.x = i ? .25 : -.25; c.y = 0; c.scale = 1; c.crop = "half-w"; } });
  cs[1].start = cs[0].start; if (cs[1].track === cs[0].track) { cs[1].track = addTrack("video"); }
  changed(); toast("Yan yana dizildi");
}
function afterLoadPub() { $("#ratio").value = `${ST.p.w}x${ST.p.h}`; layoutView(); }
async function montage() {
  const music = ST.p.clips.find(c => ST.sel.has(c.id) && clipKind(c) === "audio") || ST.p.clips.find(c => clipKind(c) === "audio");
  let beats = (ST.p.markers || []).filter(m => m.kind === "beat").map(m => m.t).sort((a, b) => a - b);
  const vids = [...ST.binSel].filter(id => ["video", "image"].includes(ST.p.assets[id]?.kind));
  if (!music) { toast("Önce bir müzik ekle"); return; }
  if (!vids.length) { toast("Medya kutusunda videoları seç (Ctrl+tık)"); renderPanel("media"); return; }
  if (!beats.length) {
    busy("Vuruşlar analiz ediliyor…");
    const a = assetOf(music), b = await job("studio_beats", [a.path]); busy(null);
    beats = b.beats.map(t => +(music.start + (t - (music.in || 0)) / (music.speed || 1)).toFixed(3)).filter(t => t >= music.start && t <= music.start + music.dur);
    ST.p.markers = [...(ST.p.markers || []).filter(m => m.kind !== "beat"), ...beats.map(t => ({ t, kind: "beat" }))];
  }
  const ev = await modal(`<h3>Vuruşa montaj</h3><div class="hint">${vids.length} kaynak, ${beats.length} vuruş. Her parça kaynaktan rastgele bir yerden alınır; Ana video izine dizilir.</div>
    <div class="row">${[1, 2, 4].map(n => `<button class="tb${n === 2 ? " pri" : ""}" data-v="${n}">Her ${n} vuruşta kes</button>`).join("")}</div>`);
  if (!ev) return;
  snap();
  const tr = ST.p.tracks.find(t => t.id === "v1")?.id || trackFor("video");
  const pts = beats.filter((_, i) => i % +ev === 0);
  if (pts[0] > music.start + .05) pts.unshift(music.start);
  pts.push(music.start + music.dur);
  ST.p.clips = ST.p.clips.filter(c => !(c.track === tr && c.start < pts.at(-1) && c.start + c.dur > pts[0]));
  let k = 0;
  for (let i = 0; i < pts.length - 1; i++) {
    const d = pts[i + 1] - pts[i]; if (d < .08) continue;
    const aid = vids[k++ % vids.length], a = ST.p.assets[aid];
    const maxIn = Math.max(0, (a.kind === "image" ? 0 : a.dur) - d);
    addClip({ asset: aid, track: tr, start: +pts[i].toFixed(3), dur: +d.toFixed(3), in: +(Math.random() * maxIn).toFixed(2), ...(i % 4 === 0 ? { trans: { in: "flash", dur: .2 } } : {}) });
  }
  changed(); toast("Montaj hazır — beğenmezsen Ctrl+Z");
}
function beatZoom(c) {
  c = c && ["video", "image"].includes(clipKind(c)) ? c : needSel(["video", "image"]); if (!c) return;
  const beats = (ST.p.markers || []).filter(m => m.kind === "beat").map(m => m.t - c.start).filter(t => t >= 0 && t < c.dur);
  if (!beats.length) { toast("Önce müzikte “Vuruşları bul”"); return; }
  snap();
  const kf = [{ t: 0, z: 1 }];
  for (const b of beats) { kf.push({ t: +b.toFixed(3), z: 1 }, { t: +(b + .06).toFixed(3), z: 1.12, e: "out" }, { t: +(b + .3).toFixed(3), z: 1.0, e: "inout" }); }
  c.zoom = kf.filter((k, i, arr) => i === 0 || k.t > arr[i - 1].t + .005); changed(); toast(`${beats.length} vuruşa zoom eklendi`);
}

// ---------------------------------------------------------------- eklentiler & Claude
P.plugins = async () => {
  const mcp = await api.studio_mcp_info();
  pb.innerHTML = sec("Claude ile düzenle (MCP)") +
    `<div class="hint">Claude masaüstü uygulamasına Kami Studio'yu bağlar. Sonra Claude'a “açık projede sessizlikleri kırp, Hormozi altyazı ekle, 12. saniyeye abone animasyonu koy” diyebilirsin; değişiklikler burada anında görünür, render_frame ile sonucu kendisi de görür.</div>` +
    `<div class="row"><button class="tb ${mcp.installed ? "on" : "pri"}" id="mcpIn">${mcp.installed ? "✓ Bağlı — yeniden yaz" : "Claude'a bağla"}</button></div>` +
    `<div class="hint">Bağladıktan sonra Claude uygulamasını kapatıp aç. Yapılandırma: <code>${esc(mcp.config)}</code></div>` +
    `<details><summary class="hint" style="cursor:pointer">Elle eklemek için</summary><pre class="code">${esc(JSON.stringify({ mcpServers: { "kami-studio": mcp.server } }, null, 2))}</pre></details>` +
    sec("Eklenti paketleri") +
    `<div class="hint">GitHub ya da doğrudan bir JSON adresi: efekt modları (ffmpeg + önizleme), ses listeleri, zoom şablonları. Güvenlik için dosya okuyan ffmpeg filtreleri reddedilir.</div>` +
    `<div class="row"><input class="in" id="pkUrl" placeholder="https://github.com/kullanici/paket" style="flex:1"><button class="tb" id="pkAdd" style="flex:none">Ekle</button></div>` +
    (ST.cat.packs.length ? ST.cat.packs.map(p => `<div class="snd"><b>${esc(p.name)}</b><small class="hint">${p.fx} efekt · ${p.sounds} ses</small><button data-pkdel="${esc(p.id)}" title="Kaldır">✕</button></div>`).join("") : '<div class="hint">Yüklü paket yok.</div>') +
    `<details><summary class="hint" style="cursor:pointer">Paket biçimi</summary><pre class="code">${esc(JSON.stringify({ name: "Benim paketim", fx: { neonpunk: { name: "Neon punk", pack: "Benim", ff: "eq=saturation=1.8,hue=h=20", css: "saturate(1.8) hue-rotate(20deg)", ov: ["grain"] } }, sounds: [{ name: "boom", url: "https://…/boom.mp3" }], zoom: [{ name: "Sert vuruş", kf: [{ t: 0, z: 1 }, { t: .1, z: 1.4, e: "out" }] }] }, null, 1))}</pre></details>`;
  $("#mcpIn").onclick = async () => { const r = await api.studio_mcp_install(); toast(r.ok ? "Eklendi — Claude uygulamasını yeniden başlat" : r.error, 4500); renderPanel(); };
  $("#pkAdd").onclick = async () => {
    busy("Paket indiriliyor…"); const r = await job("studio_pack_add", [$("#pkUrl").value]); busy(null);
    if (!r.ok) { toast("Eklenemedi: " + r.error, 5000); return; }
    ST.cat = await api.studio_catalog(); toast(`${r.name}: ${r.fx} efekt, ${r.sounds} ses`); renderPanel();
  };
};
pb.addEventListener("click", async e => {
  const d = e.target.closest("[data-pkdel]"); if (!d) return;
  await api.studio_pack_remove(d.dataset.pkdel); ST.cat = await api.studio_catalog(); renderPanel();
});
window.renderPanel = renderPanel;
window.onThumbs = () => { if (panel === "media") renderPanel(); };
