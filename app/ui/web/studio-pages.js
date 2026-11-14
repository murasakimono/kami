"use strict";
// Kami Studio sayfalari: Medya (tarayici: proje/stok/yapay zeka/animasyon/font), Renk, Ses, Teslim + sayfa doku.
let page = "edit";
function setPage(p) {
  page = p; document.body.dataset.page = p;
  $$("#dock .dk-pages button").forEach(b => b.classList.toggle("on", b.dataset.page === p));
  try { localStorage.kstPage = p; } catch { }
  ({ media: renderBrowser, color: renderColor, audio: renderMixer, deliver: renderDeliver, edit: () => renderPanel?.() })[p]?.();
  setTimeout(() => { layoutView(); renderTimeline(); }, 30);
}
window.setPage = setPage;
$("#dock .dk-pages").addEventListener("click", e => { const b = e.target.closest("[data-page]"); if (b) setPage(b.dataset.page); });
document.addEventListener("keydown", e => {
  const tag = document.activeElement?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT" || !$("#modal").hidden) return;
  if (e.shiftKey && /^Digit[1-5]$/.test(e.code)) { e.preventDefault(); setPage(["media", "edit", "color", "audio", "deliver"][+e.code.slice(5) - 1]); }
  else if (!e.ctrlKey && e.shiftKey && e.key.toLowerCase() === "f") { e.preventDefault(); freezeFrame(); }
});
document.addEventListener("click", e => { const b = e.target.closest('[data-a="freeze"]'); if (b) freezeFrame(); });
function freezeFrame() {
  const c = selClips().find(x => clipKind(x) === "video" && ST.t > x.start && ST.t < x.start + x.dur) ||
    ST.p.clips.find(x => clipKind(x) === "video" && ST.t > x.start && ST.t < x.start + x.dur && !trackOf(x).hide);
  if (!c) { toast("Oynatma kafası bir video klibin üstünde olmalı"); return; }
  ST.sel = new Set([c.id]); applyTemplate("freeze", ST.t);
}
// renk sayfasinda kapsamlar
let scopeT = 0;
setInterval(() => { if (page === "color" && Date.now() - scopeT > 110) { scopeT = Date.now(); drawScopes(); } }, 120);

// ---------------------------------------------------------------- yardimci: kartlar
const keyLinks = { pexels: "https://www.pexels.com/api/new/", pixabay: "https://pixabay.com/api/docs/", unsplash: "https://unsplash.com/oauth/applications/new", gemini: "https://aistudio.google.com/app/apikey" };
const keyNames = { pexels: "Pexels", pixabay: "Pixabay", unsplash: "Unsplash", gemini: "Gemini" };
function keyBox(name, why) {
  return `<div class="keybox"><b>${keyNames[name]} anahtarı gerekli</b><div class="hint">${why} Ücretsiz; bir kez girersin, Windows'ta şifreli saklanır.</div>
    <div class="row"><button class="tb" data-open="${keyLinks[name]}">Anahtar al ↗</button><input class="in" id="key_${name}" placeholder="anahtarı yapıştır" style="flex:1"><button class="tb pri" data-savekey="${name}" style="flex:none">Kaydet</button></div></div>`;
}
document.addEventListener("click", async e => {
  const o = e.target.closest("[data-open]"); if (o && o.closest("#browser, #modal, #deliver, #color")) { api.studio_open_url(o.dataset.open); return; }
  const k = e.target.closest("[data-savekey]");
  if (k) { const n = k.dataset.savekey, v = $("#key_" + n)?.value.trim(); if (!v) return; const r = await api.studio_key_set(n, v); ST.cat.keys = r.keys; toast(keyNames[n] + " kaydedildi"); renderBrowser(); }
});

// ================================================================= MEDYA SAYFASI
const BR = { src: "project", stockSrc: "pexels", kind: "video", q: "", items: [], page: 1, aiKind: "image", models: null, watch: 0, found: [] };
const SOURCES = [["project", "▦", "Proje medyası"], ["stock", "⌕", "Stok foto & video"], ["ai", "✧", "Yapay zeka üret"], ["anim", "◈", "Animasyon & perde"], ["fonts", "Aa", "Fontlar"]];
function renderBrowser() {
  const b = $("#browser");
  b.innerHTML = `<div class="brw"><nav class="brsrc">${SOURCES.map(([k, i, n]) => `<button data-src="${k}" class="${BR.src === k ? "on" : ""}"><i>${i}</i><span>${n}</span></button>`).join("")}
      <div class="sp"></div><div class="hint" style="padding:8px">Sürükle-bırak: dosyaları pencereye at.</div></nav><div class="brmain" id="brmain"></div></div>`;
  ({ project: brProject, stock: brStock, ai: brAI, anim: brAnim, fonts: brFonts })[BR.src]();
}
$("#browser").addEventListener("click", e => { const s = e.target.closest("[data-src]"); if (s) { BR.src = s.dataset.src; renderBrowser(); } });
function brProject() {
  const m = $("#brmain"), as = Object.entries(ST.p.assets);
  m.innerHTML = `<div class="brhead"><h2>Proje medyası</h2><span class="sp"></span><button class="tb" id="brImp">＋ İçe aktar</button><button class="tb" data-open-dir="Stok">Stok klasörü</button></div>` +
    (as.length ? `<div class="bgrid">${as.map(([id, a]) => {
      const mm = ST.media[a.path], bg = a.kind === "image" || a.gif ? `background-image:url('${a.url}')` : mm?.thumbs?.sprite ? `background-image:url(${mm.thumbs.sprite});background-size:${(mm.thumbs.count || 16) * 100}% 100%;background-position:12% 0` : "";
      return `<div class="bitem ${a.kind}${a.missing ? " missing" : ""}" draggable="true" data-aid="${id}" style="${bg}"><span class="du">${a.kind === "image" && !a.gif ? "görsel" : fmt(a.dur, false)}</span>${a.alpha ? '<span class="tag2">şeffaf</span>' : ""}<span class="nm">${esc(a.name)}</span><button class="ad" data-add="${id}" title="Oynatma kafasına ekle">＋</button></div>`;
    }).join("")}</div>` : `<div class="empty"><b>Henüz medya yok</b><span>Dosyaları sürükle, “İçe aktar”a bas ya da soldan stok/yapay zeka ile bul.</span></div>`);
  $("#brImp").onclick = async () => { const ps = await api.studio_pick_media(); if (ps?.length) { await importPaths(ps); brProject(); } };
}
$("#browser").addEventListener("click", e => {
  const d = e.target.closest("[data-open-dir]"); if (d) { api.studio_open_folder(d.dataset.openDir); return; }
  const add = e.target.closest("[data-add]"); if (add) { e.stopPropagation(); dropAsset(add.dataset.add, ST.t, null); toast("Eklendi"); }
});
$("#browser").addEventListener("dragstart", e => {
  const a = e.target.closest("[data-aid]"); if (a) { e.dataTransfer.setData("text/kami-asset", a.dataset.aid); return; }
});
// ---- stok
const STOCK = { pexels: ["photo", "video"], pixabay: ["photo", "video"], unsplash: ["photo"], openverse: ["photo", "audio"] };
const STOCK_N = { pexels: "Pexels", pixabay: "Pixabay", unsplash: "Unsplash", openverse: "Openverse (CC, anahtarsız)" };
const QUICK = ["subscribe green screen", "explosion", "smoke", "city night", "nature drone", "business", "technology", "transition", "light leak", "film burn", "rain", "fire"];
function brStock() {
  const m = $("#brmain"), src = BR.stockSrc;
  if (!STOCK[src].includes(BR.kind)) BR.kind = STOCK[src][0];
  const needKey = src !== "openverse" && !ST.cat.keys?.[src];
  m.innerHTML = `<div class="brhead"><h2>Stok</h2><div class="seg">${Object.keys(STOCK).map(k => `<button data-ss="${k}" class="${src === k ? "on" : ""}">${STOCK_N[k]}</button>`).join("")}</div></div>` +
    (needKey ? keyBox(src, `${STOCK_N[src]} araması için.`) :
      `<div class="row"><input class="in big" id="stQ" placeholder="Ne arıyorsun? (İngilizce daha çok sonuç verir)" value="${esc(BR.q)}" style="flex:1">
       <div class="seg">${STOCK[src].map(k => `<button data-sk="${k}" class="${BR.kind === k ? "on" : ""}">${{ photo: "Foto", video: "Video", audio: "Ses" }[k]}</button>`).join("")}</div><button class="tb pri" id="stGo" style="flex:none">Ara</button></div>
       <div class="chips">${QUICK.map(q => `<button class="tb" data-q="${q}" style="font-size:11px;padding:3px 8px">${q}</button>`).join("")}</div>
       <div class="bgrid" id="stGrid"></div><div class="row" id="stMore"></div>
       <div class="hint">İndirilenler “Videolar\\Kami Studio\\Stok” altına iner; atıflar “atiflar.txt” dosyasında. Pexels/Pixabay/Unsplash ücretsiz ticari kullanıma izin verir; Openverse'te lisansı kontrol et.</div>`);
  if (needKey) return;
  const go = async (more = false) => {
    BR.q = $("#stQ").value.trim(); if (!BR.q) return;
    BR.page = more ? BR.page + 1 : 1;
    if (!more) $("#stGrid").innerHTML = '<div class="hint">Aranıyor…</div>';
    const r = await job("studio_stock", [src, BR.q, BR.kind, BR.page]);
    if (r.error) { $("#stGrid").innerHTML = `<div class="hint">Olmadı: ${esc(r.error === "no_key" ? "anahtar yok" : r.error)}</div>`; return; }
    BR.items = more ? BR.items.concat(r.items) : r.items; stockGrid();
    $("#stMore").innerHTML = r.items.length >= 20 ? `<button class="tb" id="stMoreB">Daha fazla</button>` : "";
    $("#stMoreB") && ($("#stMoreB").onclick = () => go(true));
  };
  $("#stGo").onclick = () => go(); $("#stQ").onkeydown = e => { if (e.key === "Enter") go(); };
  if (BR.items.length) stockGrid();
}
function stockGrid() {
  const g = $("#stGrid"); if (!g) return;
  g.innerHTML = BR.items.map((it, i) => `<div class="bitem ${it.kind}" data-si="${i}" style="background-image:url('${esc(it.thumb || "")}')">
    ${it.kind === "video" ? `<span class="du">${fmt(it.dur || 0, false)}</span>` : ""}${it.kind === "audio" ? `<span class="du">${fmt(it.dur || 0, false)}</span>` : ""}
    <span class="nm">${esc(it.by ? "© " + it.by : it.name)}</span><button class="ad" data-sget="${i}" title="İndir ve oynatma kafasına ekle">＋</button></div>`).join("") || '<div class="hint">Sonuç yok.</div>';
}
$("#browser").addEventListener("click", async e => {
  const ss = e.target.closest("[data-ss]"); if (ss) { BR.stockSrc = ss.dataset.ss; BR.items = []; brStock(); return; }
  const sk = e.target.closest("[data-sk]"); if (sk) { BR.kind = sk.dataset.sk; BR.items = []; brStock(); $("#stGo")?.click(); return; }
  const q = e.target.closest("[data-q]"); if (q) { $("#stQ").value = q.dataset.q; if (q.dataset.q.includes("green") && BR.stockSrc !== "openverse") { BR.kind = "video"; } $("#stGo").click(); return; }
  const g = e.target.closest("[data-sget]"); if (g) { e.stopPropagation(); stockGet(BR.items[+g.dataset.sget], true); return; }
  const si = e.target.closest("[data-si]");
  if (si) {
    const it = BR.items[+si.dataset.si];
    const v = await modal(`<h3>${esc(it.name || "")}</h3>${it.kind === "video" ? `<video src="${esc(it.preview || it.url)}" autoplay loop muted controls style="width:100%;border-radius:8px"></video>` : it.kind === "audio" ? `<audio src="${esc(it.url)}" controls autoplay style="width:100%"></audio>` : `<img src="${esc(it.thumb)}" style="width:100%;border-radius:8px">`}
      <div class="hint">${esc(it.by ? "© " + it.by + " · " : "")}${esc(it.license || "")} · ${it.w || "?"}×${it.h || "?"}</div>
      <div class="row"><button class="tb" data-v="no">Kapat</button><button class="tb" data-v="bin">Projeye ekle</button><button class="tb pri" data-v="tl">Zaman çizelgesine ekle</button></div>`);
    if (v === "bin" || v === "tl") stockGet(it, v === "tl");
  }
});
async function stockGet(it, toTimeline) {
  busy("İndiriliyor: " + (it.name || ""));
  const r = await job("studio_stock_get", [BR.stockSrc, it]); busy(null);
  if (!r.ok) { toast("İndirilemedi: " + (r.error || ""), 4000); return; }
  const ids = await importPaths([r.path]);
  if (toTimeline && ids[0]) { const a = ST.p.assets[ids[0]]; snap(); const c = placeAt({ asset: ids[0], dur: a.kind === "image" ? 4 : a.dur, in: 0, ...(a.kind !== "audio" ? { fit: "cover" } : {}) }, a.kind === "audio" ? "audio" : "video"); ST.sel = new Set([c.id]); changed(); toast("Zaman çizelgesine eklendi"); }
  else toast("Projeye eklendi");
}
// ---- yapay zeka
async function brAI() {
  const m = $("#brmain");
  const liveKeys = (await api.studio_keys_status?.().catch(() => null)) || ST.cat.keys || {};
  const hasKey = liveKeys.gemini;
  const keyPills = Object.entries(liveKeys).map(([k, ok]) => `<span class="hint" style="padding:2px 6px;border-radius:6px;border:1px solid var(--line);color:${ok ? "var(--em)" : "var(--mute)"}">${esc(k)}: ${ok ? "hazır" : "yok"}</span>`).join(" ");
  const bank = BR.trBank || (BR.trBank = await api.studio_tr_meme_bank().catch(() => ({ aiPrompts: [] })));
  const prompts = bank?.aiPrompts || [];
  const promptChips = prompts.length ? `<div class="hint" style="margin-top:6px">🐛 Slow-Mo AI Böcek & TR Meme Promptları (tıkla ${hasKey ? "doldur + " : ""}kopyala):</div><div class="catpills" id="aiMemeChips">${prompts.map((p, i) => `<button data-aiprompt="${i}">${esc(p.title)}</button>`).join("")}</div>` : "";
  m.innerHTML = `<div class="brhead"><h2>Yapay zeka ile üret</h2><span class="sp"></span>${keyPills}</div>
    <div class="aigrid">
      <div class="aicard"><h3>Gemini (API)</h3>${hasKey ? `
        <div class="seg"><button data-aik="image" class="${BR.aiKind === "image" ? "on" : ""}">Görsel</button><button data-aik="video" class="${BR.aiKind === "video" ? "on" : ""}">Video</button></div>
        <textarea class="in" id="aiP" placeholder="Ne üretilsin? Ör: neon ışıklı yağmurlu İstanbul sokağı, sinematik, 35mm" style="min-height:90px"></textarea>
        ${promptChips}
        <div class="row"><select class="in" id="aiM" style="flex:1"><option>modeller yükleniyor…</option></select>
          <select class="in" id="aiA" style="flex:none;width:110px">${["16:9", "9:16", "1:1", "4:5"].map(r => `<option${r === aspectOf() ? " selected" : ""}>${r}</option>`).join("")}</select></div>
        ${BR.aiKind === "image" ? `<label class="fld w2"><span>Referans</span><select class="in" id="aiR"><option value="">yok</option>${Object.values(ST.p.assets).filter(a => a.kind === "image").map(a => `<option value="${esc(a.path)}">${esc(a.name)}</option>`).join("")}</select></label>` : ""}
        <div class="row"><button class="tb pri" id="aiGo">✧ Üret</button></div>
        <div class="hint">${BR.aiKind === "video" ? "Video üretimi ücretlidir (Google faturalandırması gerekir, ~0,10 $/sn). Pahalı gelirse sağdaki Flow'u kullan (Gemini Pro aboneliğine dahil)." : "Görsel başına birkaç sent; sonuç “Videolar\\Kami Studio\\Yapay Zeka”ya kaydedilip projeye eklenir."}</div>`
      : keyBox("gemini", "Gemini ile görsel (Nano Banana) ve video üretmek için. Faturalandırma açık değilse yalnız ücretsiz modeller çalışır.")}</div>
      <div class="aicard"><h3>Google Flow / Gemini uygulaması</h3>
        <div class="hint">Aboneliğinle Flow'da (Veo) ya da Gemini'de üret, indir; Kami indirilenler klasörünü izler ve yeni dosyayı tek tıkla projeye ekler.</div>
        <div class="row"><button class="tb pri" data-flow="https://labs.google/fx/tools/flow">Flow'u aç ↗</button><button class="tb" data-flow="https://gemini.google.com/app">Gemini'yi aç ↗</button></div>
        ${hasKey ? "" : promptChips}
        <div id="watchBox" class="hint">${BR.watch ? "İndirilenler izleniyor…" : "Açınca izleme başlar."}</div><div id="foundList"></div></div>
    </div>`;
  if ($("#aiMemeChips")) $("#aiMemeChips").onclick = e => {
    const b = e.target.closest("[data-aiprompt]"); if (!b) return;
    const item = prompts[+b.dataset.aiprompt]; if (!item) return;
    if ($("#aiP")) $("#aiP").value = item.prompt;
    try { navigator.clipboard?.writeText(item.prompt); } catch { }
    toast("Prompt kopyalandı: " + item.title);
  };
  if (!hasKey) return;
  const r = BR.models || await job("studio_gemini_models", []);
  if (r.error) { $("#aiM").innerHTML = `<option>${esc(r.error)}</option>`; return; }
  BR.models = r;
  const list = BR.aiKind === "image" ? r.image : r.video;
  $("#aiM").innerHTML = list.length ? list.map(x => `<option value="${esc(x.id)}">${esc(x.name)}</option>`).join("") : "<option value=''>Bu anahtarla kullanılabilir model yok</option>";
  $("#aiGo").onclick = async () => {
    const prompt = $("#aiP").value.trim(), model = $("#aiM").value; if (!prompt || !model) return;
    const rr = await api.studio_gemini(BR.aiKind, prompt, model, $("#aiA").value, $("#aiR")?.value || "");
    if (!rr.ok) { toast(rr.error || "olmadı"); return; }
    try { const j = await waitStudioJob(rr.job, "Üretiliyor (" + model + ")"); const ids = await importPaths(j.result.paths); toast(`${ids.length} dosya projeye eklendi`); }
    catch (e) { modal(`<h3>Üretilemedi</h3><pre class="code">${esc(e.message)}</pre><div class="hint">Model ücretliyse ya da kota dolduysa Flow'u kullan.</div><div class="row"><button class="tb" data-flow="https://labs.google/fx/tools/flow">Flow'u aç ↗</button><button class="tb pri" data-v="ok">Tamam</button></div>`); }
  };
}
function aspectOf() { const r = ST.p.w / ST.p.h; return r > 1.5 ? "16:9" : r < .7 ? "9:16" : r < .9 ? "4:5" : "1:1"; }
$("#browser").addEventListener("click", e => { const a = e.target.closest("[data-aik]"); if (a) { BR.aiKind = a.dataset.aik; brAI(); } });
document.addEventListener("click", e => {
  const f = e.target.closest("[data-flow]"); if (!f) return;
  api.studio_open_url(f.dataset.flow); if (!$("#modal").hidden && f.closest("#modal")) { $("#modal").hidden = true; }
  BR.watch = Date.now() / 1000 - 5; BR.found = []; watchDownloads(); toast("Tarayıcıda açıldı — indirdiklerin burada görünecek");
});
async function watchDownloads() {
  if (!BR.watch || Date.now() / 1000 - BR.watch > 3600) { BR.watch = 0; return; }
  const got = await api.studio_downloads_since(BR.watch);
  const known = new Set(Object.values(ST.p.assets).map(a => a.path));
  BR.found = got.filter(g => !known.has(g.path));
  const box = $("#foundList");
  if (box) box.innerHTML = BR.found.map(f => `<div class="snd"><b>${esc(f.name)}</b><button data-imp="${esc(f.path)}" title="Projeye ekle">＋</button></div>`).join("");
  if (BR.found.length && page !== "media") toast(`İndirilenlere yeni dosya geldi: ${BR.found[0].name} — Medya > Yapay zeka`, 4000);
  setTimeout(watchDownloads, 4000);
}
document.addEventListener("click", async e => { const b = e.target.closest("[data-imp]"); if (b) { await importPaths([b.dataset.imp]); b.closest(".snd")?.remove(); toast("Eklendi"); } });
// ---- animasyon
function brAnim() {
  const m = $("#brmain");
  m.innerHTML = `<div class="brhead"><h2>Animasyon & yeşil perde</h2></div>
    <div class="aigrid">
      <div class="aicard"><h3>Lottie</h3><div class="hint">LottieFiles'tan bir animasyonun sayfa adresini ya da .json/.lottie bağlantısını yapıştır (ya da dosya seç). Şeffaf videoya çevrilip projeye eklenir.</div>
        <div class="row"><input class="in" id="ltU" placeholder="https://lottiefiles.com/... ya da https://lottie.host/....json" style="flex:1"><button class="tb pri" id="ltGo" style="flex:none">Ekle</button></div>
        <div class="row"><button class="tb" id="ltF">Dosya seç…</button><button class="tb" data-open="https://lottiefiles.com/free-animations/subscribe">LottieFiles: subscribe ↗</button><button class="tb" data-open="https://lottiefiles.com/free-animations/arrow">ok ↗</button><button class="tb" data-open="https://lottiefiles.com/free-animations/emoji">emoji ↗</button></div></div>
      <div class="aicard"><h3>Yeşil perde animasyonları</h3><div class="hint">Hazır abone/beğen/patlama/geçiş animasyonları. İndirip zaman çizelgesine koy, klibin denetçisinde “Perdeyi sil”i aç (pipetle rengi seç).</div>
        <div class="chips">${["subscribe button green screen", "like button green screen", "bell icon green screen", "explosion green screen", "smoke green screen", "transition green screen", "glitch overlay", "light leak overlay"].map(q => `<button class="tb" data-gs="${q}" style="font-size:11px;padding:4px 8px">${q.replace(" green screen", "").replace(" overlay", " (kaplama)")}</button>`).join("")}</div>
        <div class="hint">Arama Pexels/Pixabay video sekmesinde açılır.</div></div>
    </div>`;
  const go = async src => { busy("Lottie dönüştürülüyor…"); const r = await job("studio_lottie", [src]); busy(null); if (!r.ok) { toast("Olmadı: " + r.error, 5000); return; } await importPaths([r.info.path]); toast("Animasyon projeye eklendi (şeffaf)"); };
  $("#ltGo").onclick = () => { const u = $("#ltU").value.trim(); if (u) go(u); };
  $("#ltF").onclick = async () => { const p = await api.studio_pick_lottie(); if (p) go(p); };
}
$("#browser").addEventListener("click", e => { const g = e.target.closest("[data-gs]"); if (g) { BR.src = "stock"; BR.stockSrc = ST.cat.keys?.pixabay ? "pixabay" : "pexels"; BR.kind = "video"; BR.q = g.dataset.gs; renderBrowser(); setTimeout(() => $("#stGo")?.click(), 50); } });
// ---- fontlar
async function brFonts() {
  const m = $("#brmain");
  m.innerHTML = `<div class="brhead"><h2>Fontlar</h2><span class="sp"></span><button class="tb" id="fnG">Google font paketini indir (${(ST.googleFonts || []).length})</button><button class="tb" data-open-dir="Fontlar">Fontlar klasörü</button><button class="tb" id="fnR">Yenile</button></div>
    <div class="hint">Bilgisayarındaki bütün fontlar + “Videolar\\Kami Studio\\Fontlar” klasörüne attıkların. Metin ve altyazı denetçisinde font kutusuna yazarak seç.</div>
    <input class="in" id="fnQ" placeholder="Font ara…"><div class="fgrid" id="fnList"></div>`;
  const list = () => {
    const q = $("#fnQ").value.toLowerCase(), fs = (ST.cat.fonts || []).filter(f => f.toLowerCase().includes(q)).slice(0, 240);
    $("#fnList").innerHTML = fs.map(f => `<div class="font" data-font="${esc(f)}"><span class="fprev" style="font-family:'kf_${esc(f)}',sans-serif">Abone Ol 123</span><small>${esc(f)}</small></div>`).join("");
    for (const el of $$(".font", $("#fnList"))) loadFontFace(el.dataset.font);
  };
  $("#fnQ").oninput = list; list();
  $("#fnG").onclick = async () => { busy("Fontlar indiriliyor…"); const r = await job("studio_fonts_download", []); busy(null); await loadFonts(); toast(`${r.fonts.length} font hazır`); brFonts(); };
  $("#fnR").onclick = async () => { await loadFonts(true); brFonts(); };
}
const loadedFaces = new Set();
function loadFontFace(f) {
  if (loadedFaces.has(f) || !ST.fontMap?.[f]) return; loadedFaces.add(f);
  try { const ff = new FontFace("kf_" + f, `url("${ST.fontMap[f]}")`); ff.load().then(x => document.fonts.add(x)).catch(() => {}); } catch { }
}
async function loadFonts() {
  const r = await job("studio_catalog_fonts", []);
  ST.fontMap = r.map; ST.googleFonts = r.google; ST.cat.fonts = r.fonts;
  let dl = $("#fontList"); if (!dl) { dl = document.createElement("datalist"); dl.id = "fontList"; document.body.appendChild(dl); }
  dl.innerHTML = r.fonts.map(f => `<option value="${esc(f)}">`).join("");
  if (window.jasReloadFonts) window.jasReloadFonts();
}
window.loadFonts = loadFonts;

// ================================================================= RENK SAYFASI
const LOOKS = {
  "Sinematik teal & orange": { exp: 0, con: .18, sat: 1.1, temp: .15, lift: [-.03, .01, .05], gamma: [0, 0, 0], gain: [.06, .02, -.06] },
  "Sıcak gün batımı": { exp: .1, con: .1, sat: 1.2, temp: .5, tint: -.05, lift: [.03, 0, -.03], gamma: [.04, 0, -.05], gain: [.05, .02, -.05] },
  "Soğuk gece": { exp: -.2, con: .15, sat: .8, temp: -.5, lift: [-.02, 0, .06], gamma: [-.03, 0, .06], gain: [-.03, 0, .04] },
  "Solgun film": { exp: .05, con: -.15, sat: .7, lift: [.08, .07, .06], gamma: [0, 0, 0], gain: [-.06, -.06, -.08] },
  "Yüksek kontrast S/B": { con: .45, sat: 0, lift: [-.04, -.04, -.04], gamma: [0, 0, 0], gain: [.08, .08, .08] },
  "Canlı vlog": { exp: .15, con: .12, sat: 1.35, temp: .1, lift: [0, 0, 0], gamma: [.05, .05, .05], gain: [.04, .04, .04] },
  "Karanlık / moody": { exp: -.3, con: .25, sat: .75, temp: -.1, lift: [-.05, -.04, -.02], gamma: [-.06, -.05, -.03], gain: [0, 0, 0] },
  "Pastel": { exp: .2, con: -.2, sat: .85, tint: .08, lift: [.07, .05, .08], gamma: [.05, .04, .06], gain: [0, 0, 0] },
  "Matrix yeşil": { con: .2, sat: .8, tint: -.4, lift: [-.03, .03, -.03], gamma: [-.05, .06, -.05], gain: [-.04, .05, -.06] },
};
const WHEELS = [["lift", "Gölgeler", .25], ["gamma", "Orta tonlar", .5], ["gain", "Parlak", .5]];
const WPH = [0, 2 * Math.PI / 3, 4 * Math.PI / 3];
function gradeClip() { const c = selClips()[0]; return c && ["video", "image"].includes(clipKind(c)) ? c : null; }
function renderStrip() {
  const vs = ST.p.clips.filter(c => ["video", "image"].includes(clipKind(c))).sort((a, b) => a.start - b.start);
  $("#strip").innerHTML = vs.map((c, i) => {
    const a = assetOf(c), m = a ? ST.media[a.path] : null;
    const bg = a?.kind === "image" ? `background-image:url('${a.url}')` : m?.thumbs?.sprite ? `background-image:url(${m.thumbs.sprite});background-size:${(m.thumbs.count || 16) * 100}% 100%;background-position:${Math.min(100, ((c.in || 0) / (a.dur || 1)) * 100)}% 0` : "";
    return `<div class="sclip${ST.sel.has(c.id) ? " on" : ""}" data-sc="${c.id}" style="${bg}"><b>${String(i + 1).padStart(2, "0")}</b>${SGL.active(c) ? "<i>◐</i>" : ""}<span>${fmt(c.start, false)}</span></div>`;
  }).join("") || '<div class="hint">Zaman çizelgesinde video yok.</div>';
}
$("#strip").addEventListener("click", e => { const s = e.target.closest("[data-sc]"); if (!s) return; const c = ST.p.clips.find(x => x.id === s.dataset.sc); ST.sel = new Set([c.id]); seek(c.start + Math.min(.5, c.dur / 2)); renderColor(); });
let CURVE_CH = "luma";
function evalCurvePts(pts, x) {
  if (!pts || pts.length < 2) return x;
  const s = [...pts].filter(p => p && p.length >= 2).map(p => [+p[0], +p[1]]).sort((a, b) => a[0] - b[0]);
  if (s.length < 2) return x;
  if (x <= s[0][0]) return clamp(s[0][1], 0, 1);
  for (let i = 0; i < s.length - 1; i++) {
    const [x0, y0] = s[i], [x1, y1] = s[i + 1];
    if (x <= x1) return clamp(y0 + (y1 - y0) * ((x - x0) / Math.max(1e-6, x1 - x0)), 0, 1);
  }
  return clamp(s[s.length - 1][1], 0, 1);
}
function drawCurveCv(cv, c) {
  if (!cv) return;
  const g = cv.getContext("2d"), W = cv.width, H = cv.height, pad = 10, uw = W - 2 * pad, uh = H - 2 * pad;
  const X = u => pad + u * uw, Y = v => H - pad - v * uh;
  g.clearRect(0, 0, W, H); g.fillStyle = "#0B0912"; g.fillRect(0, 0, W, H);
  g.strokeStyle = "rgba(255,255,255,.08)"; g.lineWidth = 1;
  for (let i = 0; i <= 4; i++) { const t = i / 4; g.beginPath(); g.moveTo(X(t), Y(0)); g.lineTo(X(t), Y(1)); g.moveTo(X(0), Y(t)); g.lineTo(X(1), Y(t)); g.stroke(); }
  const crv = c.grade?.curves || {};
  const cols = { luma: "#EAE4FF", r: "#FB7185", g: "#34D399", b: "#60A5FA" };
  for (const ch of ["luma", "r", "g", "b"]) {
    const pts = crv[ch] || [[0, 0], [1, 1]];
    g.strokeStyle = cols[ch]; g.globalAlpha = ch === CURVE_CH ? 1 : .3; g.lineWidth = ch === CURVE_CH ? 2.2 : 1.1;
    g.beginPath();
    for (let i = 0; i <= 64; i++) { const x = i / 64, y = evalCurvePts(pts, x); i ? g.lineTo(X(x), Y(y)) : g.moveTo(X(x), Y(y)); }
    g.stroke();
  }
  g.globalAlpha = 1;
  const apts = crv[CURVE_CH] || [[0, 0], [1, 1]];
  g.fillStyle = cols[CURVE_CH];
  for (const [px, py] of apts) { g.beginPath(); g.arc(X(px), Y(py), 4.5, 0, 7); g.fill(); }
}
function bindCurveCv(cv, c) {
  if (!cv) return;
  drawCurveCv(cv, c);
  const W = cv.width, H = cv.height, pad = 10, uw = W - 2 * pad, uh = H - 2 * pad;
  const pos = e => { const r = cv.getBoundingClientRect(); return [(e.clientX - r.left) * W / r.width, (e.clientY - r.top) * H / r.height]; };
  cv.oncontextmenu = e => {
    e.preventDefault();
    const [mx, my] = pos(e), crv = ((c.grade ||= {}).curves ||= {}), pts = [...(crv[CURVE_CH] || [[0, 0], [1, 1]])];
    const i = pts.findIndex(([px, py], idx) => idx > 0 && idx < pts.length - 1 && Math.hypot(pad + px * uw - mx, H - pad - py * uh - my) < 10);
    if (i > 0) { snap(); pts.splice(i, 1); crv[CURVE_CH] = pts; drawCurveCv(cv, c); changed(false); renderStrip(); }
  };
  cv.onpointerdown = e => {
    const [mx, my] = pos(e), crv = ((c.grade ||= {}).curves ||= {});
    let pts = (crv[CURVE_CH] || [[0, 0], [1, 1]]).map(p => [...p]);
    let i = pts.findIndex(([px, py]) => Math.hypot(pad + px * uw - mx, H - pad - py * uh - my) < 11);
    snap();
    if (i < 0) {
      const nx = +clamp((mx - pad) / uw, .02, .98).toFixed(3), ny = +clamp((H - pad - my) / uh, 0, 1).toFixed(3);
      pts.push([nx, ny]); pts.sort((a, b) => a[0] - b[0]); i = pts.findIndex(p => p[0] === nx && p[1] === ny);
    }
    crv[CURVE_CH] = pts; drawCurveCv(cv, c); draw();
    cv.setPointerCapture(e.pointerId);
    cv.onpointermove = ev => {
      const [x2, y2] = pos(ev);
      const xmin = i === 0 ? 0 : i === pts.length - 1 ? 1 : pts[i - 1][0] + .02;
      const xmax = i === 0 ? 0 : i === pts.length - 1 ? 1 : pts[i + 1][0] - .02;
      pts[i][0] = +clamp((x2 - pad) / uw, xmin, xmax).toFixed(3);
      pts[i][1] = +clamp((H - pad - y2) / uh, 0, 1).toFixed(3);
      crv[CURVE_CH] = pts; drawCurveCv(cv, c); draw();
    };
    cv.onpointerup = () => { cv.onpointermove = null; changed(false); renderStrip(); };
  };
}
async function renderColor() {
  renderStrip();
  const c = gradeClip(), box = $("#color");
  if (!c) { box.innerHTML = `<div class="ph"><b>Renk</b></div><div class="hint">Üstteki şeritten bir klip seç.</div>`; return; }
  const g = c.grade || {};
  const _rawLuts = await api.studio_luts();
  const luts = Array.isArray(_rawLuts) ? _rawLuts : [];
  box.innerHTML = `<div class="ph"><b>Renk</b><span class="sp"></span><span class="hint">${esc(assetOf(c)?.name || "")}</span></div>
    <div class="wheels">${WHEELS.map(([k, n]) => `<div class="wheel"><canvas data-wheel="${k}" width="112" height="112"></canvas><small>${n}</small>
      <input type="range" data-wm="${k}" min="-1" max="1" step="0.01" value="${(g._w?.[k]?.m ?? 0)}" title="Parlaklık"></div>`).join("")}</div>
    ${fld("Pozlama", "grade.exp", -2, 2, .01, g.exp || 0)}${fld("Kontrast", "grade.con", -.6, .8, .01, g.con || 0)}${fld("Doygunluk", "grade.sat", 0, 2, .01, g.sat ?? 1)}
    ${fld("Sıcaklık", "grade.temp", -1, 1, .01, g.temp || 0)}${fld("Ton (yeşil/mor)", "grade.tint", -1, 1, .01, g.tint || 0)}
    <div class="sec">Film / Optik</div>
    ${fld("Vinyet", "grade.vignette", 0, 1, .02, g.vignette || 0)}${fld("Film Greni", "grade.grain", 0, 1, .02, g.grain || 0)}${fld("Halation Glow", "grade.halation", 0, 1, .02, g.halation || 0)}
    <div class="sec">Ton Eğrisi (Curves)</div>
    <div class="catpills">${[["luma", "Tümü"], ["r", "Kırmızı"], ["g", "Yeşil"], ["b", "Mavi"]].map(([k, n]) => `<button type="button" class="${CURVE_CH === k ? "on" : ""}" data-cch="${k}">${n}</button>`).join("")}<button type="button" id="curveReset">Sıfırla</button></div>
    <canvas id="curveCv" class="curve-cv" width="260" height="165" title="Tıkla/sürükle: nokta ekle/taşı · Sağ tık: sil"></canvas>
    <div class="sec">LUT</div>
    <label class="fld w2"><span>LUT</span><select class="in" data-k="grade.lut"><option value="">yok</option>${luts.map(l => `<option value="${esc(l.name)}"${l.name === g.lut ? " selected" : ""}>${esc(l.title)}</option>`).join("")}</select></label>
    ${fld("Yoğunluk", "grade.lutMix", 0, 1, .01, g.lutMix ?? 1)}
    <div class="row"><button class="tb" id="lutImp">.cube içe aktar</button><button class="tb" data-open-dir2="LUT">LUT klasörü</button></div>
    <div class="sec">Hazır görünümler</div><div class="grid2">${Object.keys(LOOKS).map(n => `<button class="tb" data-look="${esc(n)}">${esc(n)}</button>`).join("")}</div>
    <div class="row" style="margin-top:10px"><button class="tb" id="grCopy">Tüm videolara uygula</button><button class="tb" id="grReset">Sıfırla</button></div>
    <div class="hint">Önizleme ekran kartında; dışa aktarımda aynı ayarlar tek bir 3D LUT'a pişirilir (birebir aynı sonuç).</div>`;
  for (const cv of $$("[data-wheel]", box)) drawWheel(cv, c);
  bindCurveCv($("#curveCv", box), c);
  $("#lutImp").onclick = async () => { const got = await api.studio_lut_import(); if (got.length) { toast(`${got.length} LUT eklendi`); renderColor(); } };
}
function wheelState(c, k) { const w = ((c.grade ||= {})._w ||= {}); return (w[k] ||= { x: 0, y: 0, m: 0 }); }
function wheelApply(c, k, amt) {
  const s = wheelState(c, k);
  c.grade[k] = WPH.map(ph => +(s.m * amt * .5 + amt * (s.x * Math.cos(ph) + s.y * Math.sin(ph))).toFixed(4));
}
function drawWheel(cv, c) {
  const g = cv.getContext("2d"), R = 52, cx = 56, cy = 56, k = cv.dataset.wheel, s = wheelState(c, k);
  g.clearRect(0, 0, 112, 112);
  for (let a = 0; a < 360; a += 3) { g.beginPath(); g.moveTo(cx, cy); g.arc(cx, cy, R, (a - 92) * Math.PI / 180 * -1, (a - 88) * Math.PI / 180 * -1, true); g.fillStyle = `hsla(${a},70%,45%,.75)`; g.fill(); }
  const grd = g.createRadialGradient(cx, cy, 0, cx, cy, R); grd.addColorStop(0, "rgba(20,15,30,1)"); grd.addColorStop(1, "rgba(20,15,30,0)"); g.fillStyle = grd; g.beginPath(); g.arc(cx, cy, R, 0, 7); g.fill();
  g.strokeStyle = "rgba(255,255,255,.15)"; g.beginPath(); g.arc(cx, cy, R, 0, 7); g.stroke(); g.beginPath(); g.moveTo(cx - 6, cy); g.lineTo(cx + 6, cy); g.moveTo(cx, cy - 6); g.lineTo(cx, cy + 6); g.stroke();
  g.fillStyle = "#fff"; g.strokeStyle = "#000"; g.lineWidth = 2; g.beginPath(); g.arc(cx + s.x * R, cy - s.y * R, 6, 0, 7); g.fill(); g.stroke();
}
$("#color").addEventListener("pointerdown", e => {
  const cv = e.target.closest("[data-wheel]"); if (!cv) return;
  const c = gradeClip(); if (!c) return;
  const k = cv.dataset.wheel, amt = WHEELS.find(w => w[0] === k)[2]; snap();
  const mv = ev => { const r = cv.getBoundingClientRect(); let x = ((ev.clientX - r.left) - r.width / 2) / (r.width / 2 - 4), y = -(((ev.clientY - r.top) - r.height / 2) / (r.height / 2 - 4)); const l = Math.hypot(x, y); if (l > 1) { x /= l; y /= l; }
    const s = wheelState(c, k); s.x = +x.toFixed(3); s.y = +y.toFixed(3); wheelApply(c, k, amt); drawWheel(cv, c); draw(); };
  mv(e); cv.setPointerCapture(e.pointerId); cv.onpointermove = mv; cv.onpointerup = () => { cv.onpointermove = null; changed(false); renderStrip(); };
});
$("#color").addEventListener("dblclick", e => { const cv = e.target.closest("[data-wheel]"); if (!cv) return; const c = gradeClip(); snap(); const s = wheelState(c, cv.dataset.wheel); s.x = s.y = 0; wheelApply(c, cv.dataset.wheel, WHEELS.find(w => w[0] === cv.dataset.wheel)[2]); drawWheel(cv, c); changed(false); });
$("#color").addEventListener("input", e => {
  const c = gradeClip(); if (!c) return; const el = e.target;
  if (el.dataset.wm) { if (!inspSnapC) { snap(); inspSnapC = true; } const s = wheelState(c, el.dataset.wm); s.m = +el.value; wheelApply(c, el.dataset.wm, WHEELS.find(w => w[0] === el.dataset.wm)[2]); draw(); return; }
  const k = el.dataset.k; if (!k) return;
  if (!inspSnapC) { snap(); inspSnapC = true; }
  const v = el.tagName === "SELECT" ? el.value : +el.value;
  c.grade ||= {}; setKGrade(c, k, v);
  if (el.type === "range") { const n = el.parentElement.querySelector(`input.num[data-k="${k}"]`); if (n) n.value = (+v).toFixed(2); }
  draw();
});
let inspSnapC = false;
$("#color").addEventListener("change", e => { inspSnapC = false; changed(false); renderStrip(); });
function setKGrade(c, k, v) { const key = k.split(".")[1]; if (v === "" || v == null) delete c.grade[key]; else c.grade[key] = v; }
$("#color").addEventListener("click", e => {
  const c = gradeClip(); if (!c) return;
  const ch = e.target.closest("[data-cch]"); if (ch) { CURVE_CH = ch.dataset.cch; renderColor(); return; }
  if (e.target.id === "curveReset") { snap(); if (c.grade?.curves) delete c.grade.curves[CURVE_CH]; changed(false); renderColor(); return; }
  const l = e.target.closest("[data-look]"); if (l) { snap(); c.grade = { ...clone(LOOKS[l.dataset.look]), lut: c.grade?.lut, lutMix: c.grade?.lutMix }; changed(false); renderColor(); return; }
  const d = e.target.closest("[data-open-dir2]"); if (d) { api.studio_open_folder(d.dataset.openDir2); return; }
  if (e.target.id === "grReset") { snap(); delete c.grade; changed(false); renderColor(); }
  if (e.target.id === "grCopy") { snap(); for (const x of ST.p.clips) if (x !== c && clipKind(x) === "video") x.grade = clone(c.grade || {}); changed(false); renderStrip(); toast("Tüm video kliplerine uygulandı"); }
});
// kapsamlar
function drawScopes() {
  const W = 256, H = Math.max(2, Math.round(256 * view.height / view.width));
  const tmp = drawScopes.c ||= document.createElement("canvas"); tmp.width = W; tmp.height = H;
  const tg = tmp.getContext("2d", { willReadFrequently: true }); tg.drawImage(view, 0, 0, W, H);
  const d = tg.getImageData(0, 0, W, H).data;
  const prep = (id, w, h) => { const cv = $("#" + id); const r = cv.getBoundingClientRect(); cv.width = Math.max(2, r.width | 0); cv.height = Math.max(2, r.height | 0); const g = cv.getContext("2d"); g.fillStyle = "#050308"; g.fillRect(0, 0, cv.width, cv.height); return [g, cv.width, cv.height]; };
  // dalga formu (luma)
  let [g, cw, chh] = prep("scWave");
  let img = g.createImageData(cw, chh);
  const plot = (im, x, y, r, gg, b) => { if (x < 0 || y < 0 || x >= im.width || y >= im.height) return; const i = (y * im.width + x) * 4; im.data[i] = Math.min(255, im.data[i] + r); im.data[i + 1] = Math.min(255, im.data[i + 1] + gg); im.data[i + 2] = Math.min(255, im.data[i + 2] + b); im.data[i + 3] = 255; };
  for (let y = 0; y < H; y += 1) for (let x = 0; x < W; x++) { const i = (y * W + x) * 4, L = .2126 * d[i] + .7152 * d[i + 1] + .0722 * d[i + 2]; plot(img, (x * cw / W) | 0, (chh - 1 - L / 255 * (chh - 1)) | 0, 18, 40, 22); }
  g.putImageData(img, 0, 0); label(g, "Dalga");
  // RGB parade
  [g, cw, chh] = prep("scParade"); img = g.createImageData(cw, chh);
  for (let y = 0; y < H; y += 1) for (let x = 0; x < W; x++) { const i = (y * W + x) * 4, px = (x * cw / W / 3) | 0;
    plot(img, px, (chh - 1 - d[i] / 255 * (chh - 1)) | 0, 50, 8, 8); plot(img, px + ((cw / 3) | 0), (chh - 1 - d[i + 1] / 255 * (chh - 1)) | 0, 8, 50, 8); plot(img, px + ((2 * cw / 3) | 0), (chh - 1 - d[i + 2] / 255 * (chh - 1)) | 0, 10, 14, 55); }
  g.putImageData(img, 0, 0); label(g, "RGB");
  // vektorskop
  [g, cw, chh] = prep("scVec"); img = g.createImageData(cw, chh); const R = Math.min(cw, chh) / 2 - 4, ox = cw / 2, oy = chh / 2;
  for (let i = 0; i < d.length; i += 8) { const r = d[i] / 255, gg = d[i + 1] / 255, b = d[i + 2] / 255; const u = -.1146 * r - .3854 * gg + .5 * b, v = .5 * r - .4542 * gg - .0458 * b;
    plot(img, (ox + u * 2 * R) | 0, (oy - v * 2 * R) | 0, d[i] / 5 + 10, d[i + 1] / 5 + 10, d[i + 2] / 5 + 10); }
  g.putImageData(img, 0, 0); g.strokeStyle = "rgba(255,255,255,.15)"; g.beginPath(); g.arc(ox, oy, R, 0, 7); g.stroke();
  g.strokeStyle = "rgba(255,181,71,.4)"; g.beginPath(); g.moveTo(ox, oy); g.lineTo(ox - R * .55 * Math.cos(.98), oy - R * .55 * Math.sin(.98) * -1 - 0); g.stroke(); label(g, "Vektör (cilt çizgisi)");
  // histogram
  [g, cw, chh] = prep("scHist"); const hs = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
  for (let i = 0; i < d.length; i += 4) { hs[0][d[i]]++; hs[1][d[i + 1]]++; hs[2][d[i + 2]]++; }
  const mx = Math.max(1, ...hs.map(h => Math.max(...h.slice(2, 254)))); g.globalCompositeOperation = "lighter";
  [["rgba(255,60,60,.7)", 0], ["rgba(60,255,90,.7)", 1], ["rgba(70,110,255,.8)", 2]].forEach(([col, ci]) => { g.fillStyle = col; g.beginPath(); g.moveTo(0, chh); for (let x = 0; x < 256; x++) g.lineTo(x * cw / 255, chh - Math.min(1, hs[ci][x] / mx) * (chh - 6)); g.lineTo(cw, chh); g.fill(); });
  g.globalCompositeOperation = "source-over"; label(g, "Histogram");
}
function label(g, t) { g.fillStyle = "rgba(196,181,253,.8)"; g.font = "10px Chakra Petch"; g.fillText(t, 6, 13); }

// ================================================================= SES SAYFASI
function _vuLevel(analyser, fallback) {
  if (!analyser || !ST.playing) return fallback;
  const buf = _vuLevel.b ||= new Uint8Array(analyser.fftSize);
  analyser.getByteTimeDomainData(buf);
  let peak = 0;
  for (let i = 0; i < buf.length; i++) { const v = Math.abs(buf[i] - 128) / 128; if (v > peak) peak = v; }
  return Math.min(1, peak * 1.45);
}
let vuTimer = 0;
function startVuLoop() {
  clearInterval(vuTimer);
  vuTimer = setInterval(() => {
    if (page !== "audio") { clearInterval(vuTimer); return; }
    for (const el of $$("[data-vu]", $("#mixer"))) {
      const tid = el.dataset.vu;
      let lvl = 0;
      if (tid === "_master") {
        const fb = ST.playing ? Math.min(1, ST.p.clips.filter(c => ST.t >= c.start && ST.t < c.start + c.dur).reduce((m, c) => Math.max(m, clipVol?.(c, ST.t) || 0), 0) * .7) : 0;
        lvl = _vuLevel(ST.acMaster, fb);
      } else {
        const fb = ST.playing ? ST.p.clips.filter(c => c.track === tid && ST.t >= c.start && ST.t < c.start + c.dur).reduce((m, c) => Math.max(m, clipVol?.(c, ST.t) || 0), 0) * .7 : 0;
        lvl = _vuLevel(ST.acTr?.[tid]?.analyser, fb);
      }
      el.style.height = Math.round(Math.min(1, Math.max(0, lvl)) * 100) + "%";
    }
  }, 60);
}
function renderMixer() {
  const m = $("#mixer"), ms = ST.p.master || {};
  const tracks = ST.p.tracks.filter(t => t.kind === "audio" || t.kind === "video");
  m.innerHTML = `<div class="ph"><b>Ses mikseri & 10-Bant EQ</b><span class="sp"></span><div class="vu master-vu" title="Ana Çıkış VU"><i data-vu="_master"></i></div></div>
    <div class="mixwrap"><div class="strips">${tracks.map(t => `<div class="chan${t.mute ? " muted" : ""}" data-tr="${t.id}">
        <b title="${esc(t.name)}">${esc(t.name)}</b><small>${t.kind === "video" ? "video sesi" : "ses"}</small>
        <div class="fader-vu"><input type="range" class="fader" orient="vertical" min="0" max="2" step="0.01" value="${t.vol ?? 1}" data-tvol="${t.id}"><div class="vu"><i data-vu="${t.id}"></i></div></div>
        <span class="db">${dbOf(t.vol ?? 1)}</span>
        <div class="cbtn"><button class="tb${t.mute ? " on" : ""}" data-tm="${t.id}" title="Sessiz">M</button><button class="tb${t.solo ? " on" : ""}" data-ts="${t.id}" title="Solo (Sadece bu iz)">S</button><button class="tb${t.duck ? " on" : ""}" data-td="${t.id}" title="Konuşma olunca bu izi kıs (müzik için)">Kıs</button></div>
        <button class="tb" data-tfix="${t.id}" title="Bu izdeki tüm kliplere ses düzeltme">Düzelt…</button></div>`).join("")}</div>
      <div class="master"><h3>Ana çıkış</h3>
        <label class="fld w2"><span>Ses yüksekliği</span><select class="in" id="mxL">${[["", "Dokunma"], ["-14", "YouTube (-14 LUFS)"], ["-16", "Podcast (-16)"], ["-11", "TikTok/Reels (-11)"], ["-9", "Çok yüksek (-9)"]].map(([v, n]) => `<option value="${v}"${String(ms.lufs ?? "") === v ? " selected" : ""}>${n}</option>`).join("")}</select></label>
        <div class="fld"><span>Kısma miktarı</span><input type="range" id="mxD" min="0" max="1" step="0.05" value="${ms.duck ?? .6}"><input class="num" readonly value="${Math.round((ms.duck ?? .6) * 100)}%"></div>
        <div class="row" style="margin:6px 0"><button class="tb" id="mxDuckFile" title="Müzik dosyasını konuşma klibine göre otomatik kıs ve içe aktar">🦆 Müzik Dosyasını Sesle Kıs</button></div>
        <div class="hint">“Kıs” açık izler (müzik), diğer izlerde konuşma varken otomatik kısılır (dışa aktarımda sidechain kompresör).</div>
        <div class="sec">Seçili klip · 10-Bant EQ & Pan</div><div id="mxClip" class="hint">Zaman çizelgesinde bir ses/video klibi seç.</div></div></div>`;
  const c = selClips()[0];
  if (c && (clipKind(c) === "audio" || assetOf(c)?.audio)) {
    const bands = window.EQ_BANDS_HZ || [31, 62, 125, 250, 500, 1000, 2000, 4000, 8000, 16000];
    const eq = c.eq || bands.map(() => 0);
    const eqPre = ST.cat.eqPresets || { flat: ["Düz", bands.map(() => 0)], podcast: ["Podcast", [-6,-4,-2,-1,1,2,4,5,3,1]], bass: ["Bas", [6,5,4,2,0,-1,0,1,1,0]], bright: ["Tiz", [-1,-1,0,0,1,2,3,5,6,5]], radio: ["Radyo", [-12,-10,-6,2,5,6,4,-4,-9,-12]], cinema: ["Sinema", [3,2,1,0,-1,1,2,2,3,2]] };
    $("#mxClip").innerHTML = `<b>${esc(assetOf(c)?.name || "")}</b>` +
      `<div class="fld"><span>Stereo Pan</span><input type="range" id="mxPan" min="-1" max="1" step="0.05" value="${c.pan || 0}"><input class="num" readonly value="${((c.pan || 0) * 100).toFixed(0)}%"></div>` +
      `<div class="catpills">${Object.entries(eqPre).map(([id, [nm]]) => `<button type="button" data-meqp="${id}">${esc(nm)}</button>`).join("")}</div>` +
      `<div class="eq10">${bands.map((f, i) => `<div class="eqb"><span class="eqv">${(+(eq[i] || 0)).toFixed(0)}</span><input type="range" orient="vertical" min="-12" max="12" step="0.5" value="${eq[i] || 0}" data-eqi="${i}"><small>${f >= 1000 ? (f / 1000) + "k" : f}</small></div>`).join("")}</div>` +
      `<div class="chips" style="margin-top:6px">${Object.entries(ST.cat.afx || {}).map(([id, n]) => `<button class="tb${(c.afx || []).includes(id) ? " on" : ""}" data-mafx="${id}" style="font-size:11px;padding:4px 8px">${esc(n)}</button>`).join("")}</div>`;
  }
  startVuLoop();
}
function dbOf(v) { return v <= 0 ? "-∞" : (20 * Math.log10(v)).toFixed(1) + " dB"; }
$("#mixer").addEventListener("input", e => {
  const f = e.target.closest("[data-tvol]"); if (f) { const t = ST.p.tracks.find(x => x.id === f.dataset.tvol); t.vol = +f.value; f.closest(".chan").querySelector(".db").textContent = dbOf(t.vol); ST.dirty = true; window.syncMedia?.(ST.t, false); scheduleSaveP(); return; }
  if (e.target.id === "mxD") { (ST.p.master ||= {}).duck = +e.target.value; e.target.nextElementSibling.value = Math.round(e.target.value * 100) + "%"; scheduleSaveP(); return; }
  if (e.target.id === "mxPan") { const c = selClips()[0]; if (!c) return; c.pan = +e.target.value; e.target.nextElementSibling.value = Math.round(c.pan * 100) + "%"; window.syncMedia?.(ST.t, false); ST.dirty = true; scheduleSaveP(); return; }
  if (e.target.dataset.eqi != null) { const c = selClips()[0]; if (!c) return; c.eq ||= new Array(10).fill(0); c.eq[+e.target.dataset.eqi] = +e.target.value; e.target.previousElementSibling.textContent = (+e.target.value).toFixed(0); window.syncMedia?.(ST.t, false); ST.dirty = true; scheduleSaveP(); }
});
function scheduleSaveP() { changed(false); }
$("#mixer").addEventListener("change", e => { if (e.target.id === "mxL") { snap(); (ST.p.master ||= {}).lufs = e.target.value ? +e.target.value : null; changed(false); } });
$("#mixer").addEventListener("click", async e => {
  const mu = e.target.closest("[data-tm]"), so = e.target.closest("[data-ts]"), du = e.target.closest("[data-td]"), fx = e.target.closest("[data-tfix]"), ma = e.target.closest("[data-mafx]"), ep = e.target.closest("[data-meqp]");
  if (e.target.id === "mxDuckFile") {
    const duckC = ST.p.clips.find(x => trackOf(x).duck && assetOf(x)?.path);
    const voiceC = ST.p.clips.find(x => !trackOf(x).duck && (trackOf(x).kind === "audio" || assetOf(x)?.audio) && assetOf(x)?.path);
    if (!duckC || !voiceC) return toast("Bir izde 'Kıs' açıp diğer izde konuşma klibi seç");
    busy("Müzik ses altına kısılıyor…");
    const r = await api.studio_audio_duck(assetOf(duckC).path, assetOf(voiceC).path, "");
    busy(null);
    if (r?.ok && r.path) { await importPaths([r.path]); toast("Kısılmış müzik Medya'ya eklendi"); }
    else toast(r?.error || "Sidechain duck başarısız");
    return;
  }
  if (mu) { snap(); const t = ST.p.tracks.find(x => x.id === mu.dataset.tm); t.mute = !t.mute; changed(); renderMixer(); }
  if (so) { snap(); const t = ST.p.tracks.find(x => x.id === so.dataset.ts); t.solo = !t.solo; changed(); renderMixer(); }
  if (du) { snap(); const t = ST.p.tracks.find(x => x.id === du.dataset.td); t.duck = !t.duck; changed(false); renderMixer(); }
  if (ep) { const c = selClips()[0], pre = ST.cat.eqPresets?.[ep.dataset.meqp]?.[1]; if (c && pre) { snap(); c.eq = [...pre]; window.syncMedia?.(ST.t, false); changed(false); renderMixer(); } }
  if (ma) { const c = selClips()[0]; snap(); const s = new Set(c.afx || []); s.has(ma.dataset.mafx) ? s.delete(ma.dataset.mafx) : s.add(ma.dataset.mafx); c.afx = [...s]; changed(false); renderMixer(); }
  if (fx) {
    const v = await modal(`<h3>İzdeki tüm kliplere</h3><div class="grid2">${[["voice", "Konuşma: netleştir + gürültü"], ["music", "Müzik: dokunma"], ["clean", "Sadece gürültü azalt"], ["off", "Hepsini kaldır"]].map(([k, n]) => `<button class="tb" data-v="${k}">${n}</button>`).join("")}</div>`);
    if (!v) return; snap();
    for (const c of ST.p.clips.filter(c => c.track === fx.dataset.tfix)) c.afx = { voice: ["nr1", "voice"], clean: ["nr2"], music: [], off: [] }[v];
    changed(false); toast("Uygulandı");
  }
});

// ================================================================= TESLIM SAYFASI
const DV = { preset: "youtube", quality: "high", size: "", range: "all", queue: [] };
const SIZES = { "": "Proje boyutu", "1280x720": "720p", "1920x1080": "1080p", "2560x1440": "1440p", "3840x2160": "4K", "1080x1920": "1080×1920 (dikey)", "720x1280": "720×1280 (dikey)" };
function renderDeliver() {
  const d = $("#deliver"), pre = ST.cat.deliver || {};
  d.innerHTML = `<div class="ph"><b>Teslim</b><span class="sp"></span><span class="hint">${ST.p.w}×${ST.p.h} · ${ST.p.fps} fps · ${fmt(projEnd())}</span></div>
    <div class="presets">${Object.entries(pre).map(([k, n]) => `<button class="preset${DV.preset === k ? " on" : ""}" data-pre="${k}"><i>${{ youtube: "▶", shorts: "▯", hevc: "H5", prores: "PR", gif: "GIF", webm: "W", mp3: "♪", wav: "≋" }[k] || "⬇"}</i><span>${esc(n)}</span></button>`).join("")}</div>
    <label class="fld w2"><span>Kalite</span><select class="in" id="dvQ"><option value="high"${DV.quality === "high" ? " selected" : ""}>Yüksek</option><option value="medium"${DV.quality === "medium" ? " selected" : ""}>Orta (küçük dosya)</option></select></label>
    <label class="fld w2"><span>Çözünürlük</span><select class="in" id="dvS">${Object.entries(SIZES).map(([k, n]) => `<option value="${k}"${DV.size === k ? " selected" : ""}>${n}</option>`).join("")}</select></label>
    <label class="fld w2"><span>Aralık</span><select class="in" id="dvR"><option value="all">Tüm video</option><option value="loop">Döngü I–O</option><option value="sel">Seçili klipler</option><option value="mk">İlk–son işaret</option><option value="ph">Oynatma kafasından sona</option></select></label>
    <div class="row" style="flex-wrap:wrap;gap:6px"><button class="tb pri" id="dvGo">⬇ Sıraya ekle ve başlat</button><button class="tb" id="dvGif">🎞️ Hızlı GIF / WebP</button><button class="tb" id="dvProIo" title="Wildcard çıktı adı öner">🏷️ Pro IO Yol</button><button class="tb" id="dvThumb">Kapak karesi (PNG)</button></div>
    <div class="hint" id="proIoHint" style="margin-top:4px"></div>
    <div class="sec">Kuyruk</div><div id="dvQueue">${DV.queue.length ? "" : '<div class="hint">Boş.</div>'}</div>
    <div class="hint">Dışa aktarım her zaman asıl dosyalardan, ekran kartıyla (NVENC) yapılır. Stok kullandıysan atıflar: Videolar\\Kami Studio\\Stok\\atiflar.txt</div>`;
  $("#dvR").value = DV.range; renderQueue();
  $("#dvGo").onclick = enqueue;
  $("#dvProIo").onclick = async () => {
    const ext = { mp3: "mp3", wav: "wav", gif: "gif", prores: "mov", webm: "webm" }[DV.preset] || "mp4";
    const p = window.rootProjectClone ? window.rootProjectClone() : clone(ST.p);
    const r = await api.studio_pro_io_path(p, "{name}_v{ver}_{w}x{h}_{date}", ext, "", ST.path || "");
    if (r?.ok) { $("#proIoHint").textContent = "Pro IO Öneri: " + r.path; toast("Yol önerisi: " + r.filename); }
  };
  $("#dvGif").onclick = async () => {
    if (!ST.p.clips.length) { toast("Zaman çizelgesi boş"); return; }
    const fmt = await modal(`<h3>Hızlı GIF / WebP Dışa Aktar</h3><div class="hint">AEJuice / Spunkram tarzı 2 geçişli yüksek kalite palet çıktısı.</div><div class="row"><button class="tb pri" data-v="gif">🎞️ GIF (720p, 15fps)</button><button class="tb" data-v="webp">✨ Animasyonlu WebP</button><button class="tb" data-v="">Vazgeç</button></div>`);
    if (!fmt) return;
    const p = window.rootProjectClone ? window.rootProjectClone() : clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
    busy(fmt.toUpperCase() + " hazırlanıyor…");
    const r = await job("studio_export_gif", [p, "", fmt, 15, 720]);
    busy(null);
    if (r?.ok) { toast("Hazır: " + r.path.split(/[\\/]/).pop()); api.open_path_folder(r.path); } else toast(r?.error || "olmadı", 4500);
  };
  $("#dvThumb").onclick = async () => { busy("Kare hazırlanıyor…"); const p = window.rootProjectClone ? window.rootProjectClone() : clone(ST.p); for (const a of Object.values(p.assets)) delete a.url; const r = await api.studio_frame_png(p, ST.t, ""); busy(null); if (r.ok) { toast("Kaydedildi: " + r.path.split(/[\\/]/).pop()); api.open_path_folder(r.path); } else toast(r.error); };
}
$("#deliver").addEventListener("click", e => { const p = e.target.closest("[data-pre]"); if (p) { DV.preset = p.dataset.pre; renderDeliver(); } });
$("#deliver").addEventListener("change", e => { if (e.target.id === "dvQ") DV.quality = e.target.value; if (e.target.id === "dvS") DV.size = e.target.value; if (e.target.id === "dvR") DV.range = e.target.value; });
async function enqueue() {
  if (!ST.p.clips.length) { toast("Zaman çizelgesi boş"); return; }
  const ext = { mp3: ".mp3", wav: ".wav", gif: ".gif", prores: ".mov", webm: ".webm" }[DV.preset] || ".mp4";
  const out = await api.studio_pick_save_ext(ST.p.name, ext); if (!out) return;
  const o = { preset: DV.preset, quality: DV.quality };
  const sel = selClips();
  if (DV.range === "loop" && ST.loopIn != null && ST.loopOut > ST.loopIn) o.range = [ST.loopIn, ST.loopOut];
  if (DV.range === "sel" && sel.length) o.range = [Math.min(...sel.map(c => c.start)), Math.max(...sel.map(c => c.start + c.dur))];
  if (DV.range === "mk" && ST.p.markers?.length > 1) { const ts = ST.p.markers.map(m => m.t).sort((a, b) => a - b); o.range = [ts[0], ts.at(-1)]; }
  if (DV.range === "ph") o.range = [ST.t, projEnd()];
  if (DV.size) o.size = DV.size.split("x").map(Number);
  await save();
  const p = window.rootProjectClone ? window.rootProjectClone() : clone(ST.p); for (const a of Object.values(p.assets)) delete a.url;
  const r = await api.studio_export(p, out, o);
  if (!r?.ok) { toast("Başlatılamadı: " + r?.error); return; }
  DV.queue.unshift({ job: r.job, out, state: "running", p: 0, t0: Date.now(), preset: DV.preset });
  renderQueue(); pollQueue();
}
window.enqueueExport = enqueue;
let qTimer = 0;
async function pollQueue() {
  clearTimeout(qTimer);
  let running = false;
  for (const q of DV.queue.filter(q => q.state === "running")) { const j = await api.studio_job(q.job); Object.assign(q, { state: j.state || "error", p: j.p || 0, secs: j.secs, enc: j.encoder, error: j.error }); if (q.state === "running") running = true; else if (q.state === "done") toast("Hazır: " + q.out.split(/[\\/]/).pop()); }
  renderQueue(); if (running) qTimer = setTimeout(pollQueue, 700);
}
function renderQueue() {
  const b = $("#dvQueue"); if (!b) return;
  if (!DV.queue.length) { b.innerHTML = '<div class="hint">Boş.</div>'; return; }
  b.innerHTML = DV.queue.map((q, i) => `<div class="qitem ${q.state}"><b>${esc(q.out.split(/[\\/]/).pop())}</b>
    <div class="bar"><i style="width:${(q.p * 100).toFixed(1)}%"></i></div>
    <small>${q.state === "running" ? `%${Math.round(q.p * 100)}` + (q.p > .03 ? ` · kalan ~${Math.max(0, ((Date.now() - q.t0) / 1000) / q.p * (1 - q.p)).toFixed(0)} sn` : "") : q.state === "done" ? `✓ ${q.secs} sn · ${q.enc === "h264_nvenc" ? "NVENC" : q.enc || ""}` : q.state === "error" ? "✕ " + esc((q.error || "").slice(-140)) : q.state}</small>
    <span class="qb">${q.state === "running" ? `<button class="tb" data-qc="${i}">İptal</button>` : q.state === "done" ? `<button class="tb" data-qo="${i}">Klasör</button><button class="tb" data-qp="${i}">Oynat</button>` : ""}</span></div>`).join("");
}
$("#deliver").addEventListener("click", e => {
  const c = e.target.closest("[data-qc]"), o = e.target.closest("[data-qo]"), p = e.target.closest("[data-qp]");
  if (c) api.studio_cancel(DV.queue[+c.dataset.qc].job);
  if (o) api.open_path_folder(DV.queue[+o.dataset.qo].out);
  if (p) api.open_path(DV.queue[+p.dataset.qp].out);
});

// ================================================================= acilis
window.addEventListener("pywebviewready", async () => {
  await new Promise(r => setTimeout(r, 400));
  loadFonts().catch(() => {});
  let p0 = "edit"; try { p0 = localStorage.kstPage || "edit"; } catch { }
  setPage(p0);
});
