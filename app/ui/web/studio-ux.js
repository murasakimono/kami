"use strict";
// Kami Studio kullanim katmani: favoriler, Giris/Cikis/Dongu animasyon secici, efekt yerlesimi, sag tik menuleri,
// isaretler (surukle/sil/atla), iz silme, sesi ayirma, kisayollar.

// ---------------------------------------------------------------- favoriler
const FAV = (() => { try { return JSON.parse(localStorage.kstFav || "{}"); } catch { return {}; } })();
const favSave = () => { try { localStorage.kstFav = JSON.stringify(FAV); } catch { } };
const isFav = (kind, id) => (FAV[kind] || []).includes(id);
function favToggle(kind, id) {
  const s = new Set(FAV[kind] || []); s.has(id) ? s.delete(id) : s.add(id); FAV[kind] = [...s]; favSave();
  toast(s.has(id) ? "★ Favorilere eklendi" : "Favorilerden çıkarıldı", 1400);
}
window.FAV = FAV; window.isFav = isFav; window.favToggle = favToggle;
const star = (kind, id) => `<button class="fav${isFav(kind, id) ? " on" : ""}" data-fav="${kind}|${id}" title="Favori">★</button>`;
window.favStar = star;

// ---------------------------------------------------------------- animasyon secici (Giris / Cikis / Dongu)
let animTab = { clip: "in", text: "in" };
const LEGACY_TEXT = { pop: ["pop", "none"], fade: ["fade", "fade"], slide: ["slide-u", "fade"], bounce: ["bounce", "none"], zoom: ["zoom", "fade"], glitch: ["glitch", "none"], type: ["type", "none"], shake: ["none", "none"], none: ["none", "none"] };
function animVal(c, scope, slot) {
  if (scope === "clip") return c.anim?.[slot] || "";
  const st = c.style || {};
  if (["animIn", "animOut", "animLoop"].some(k => k in st)) return st["anim" + slot[0].toUpperCase() + slot.slice(1)] || "none";
  const lg = LEGACY_TEXT[st.anim || "pop"] || ["none", "none"];
  return slot === "in" ? lg[0] : slot === "out" ? lg[1] : st.anim === "shake" ? "shake" : "none";
}
function animBox(c, scope) {
  const cat = scope === "clip" ? ST.cat.canim : ST.cat.tanim; if (!cat) return "";
  const tab = animTab[scope], items = cat[tab] || {}, cur = animVal(c, scope, tab), fk = `${scope}-${tab}`;
  const name = v => typeof v === "string" ? v : v.name;
  const ids = Object.keys(items).filter(id => id !== "none");
  const favs = ids.filter(id => isFav(fk, id)), rest = ids.filter(id => !isFav(fk, id));
  const chip = id => `<span class="ach${cur === id ? " on" : ""}"><button data-anim="${scope}|${tab}|${id}">${esc(name(items[id]))}</button>${star(fk, id)}</span>`;
  const lab = { in: "Giriş", out: "Çıkış", loop: "Döngü" };
  const sum = ["in", "out", "loop"].map(s => { const v = animVal(c, scope, s); return v && v !== "none" ? `<b>${lab[s]}:</b> ${esc(name(cat[s][v] || v))}` : ""; }).filter(Boolean).join(" · ");
  let h = `<div class="sec">Animasyon</div><div class="atabs">${["in", "out", "loop"].map(s => `<button data-atab="${scope}|${s}" class="${tab === s ? "on" : ""}">${lab[s]}${animVal(c, scope, s) && animVal(c, scope, s) !== "none" ? " •" : ""}</button>`).join("")}</div>` +
    (sum ? `<div class="hint">${sum}</div>` : `<div class="hint">Giriş: klibin başında, Çıkış: sonunda, Döngü: tüm süre boyunca.</div>`) +
    `<div class="achips"><span class="ach${!cur || cur === "none" ? " on" : ""}"><button data-anim="${scope}|${tab}|none">Yok</button></span>${favs.map(chip).join("")}${favs.length && rest.length ? '<i class="abr"></i>' : ""}${rest.map(chip).join("")}</div>`;
  const P = scope === "clip" ? "anim." : "style.";
  if (tab === "in" && cur && cur !== "none") h += fld("Giriş süresi", P + "inDur", .05, 3, .05, (scope === "clip" ? c.anim?.inDur : c.style?.inDur) ?? (scope === "clip" ? .5 : .45), " sn") + (scope === "clip" ? sel("Eğri", "anim.inEase", { "": "Varsayılan", ...cat.ease }, c.anim?.inEase || "") : "");
  if (tab === "out" && cur && cur !== "none") h += fld("Çıkış süresi", P + "outDur", .05, 3, .05, (scope === "clip" ? c.anim?.outDur : c.style?.outDur) ?? (scope === "clip" ? .5 : .4), " sn") + (scope === "clip" ? sel("Eğri", "anim.outEase", { "": "Varsayılan", ...cat.ease }, c.anim?.outEase || "") : "");
  if (tab === "loop" && cur && cur !== "none" && scope === "clip") h += fld("Şiddet", "anim.loopAmt", .1, 4, .05, c.anim?.loopAmt ?? 1) + fld("Hız", "anim.loopSpeed", .1, 4, .05, c.anim?.loopSpeed ?? 1);
  return h;
}
window.animBox = animBox;
function setAnim(c, scope, slot, id) {
  if (scope === "clip") {
    c.anim = { ...(c.anim || {}) };
    if (id === "none") delete c.anim[slot]; else c.anim[slot] = id;
    if (!c.anim.in && !c.anim.out && !c.anim.loop) delete c.anim;
    return;
  }
  const st = c.style = { ...(c.style || {}) };
  if (!["animIn", "animOut", "animLoop"].some(k => k in st)) {   // eski tek animasyonu yeni uca cevir
    const lg = LEGACY_TEXT[st.anim || "pop"] || ["none", "none"];
    st.animIn = lg[0]; st.animOut = lg[1]; st.animLoop = st.anim === "shake" ? "shake" : "none";
  }
  delete st.anim;
  st["anim" + slot[0].toUpperCase() + slot.slice(1)] = id;
}

// ---------------------------------------------------------------- efekt yerlesimi
function fxRows(c) {
  if (!c.fx?.length) return '<div class="hint">Soldaki Efekt panelinden tıkla. Her efekt tüm klipte, yalnız başta ya da yalnız sonda olabilir.</div>';
  return c.fx.map(id => {
    const p = c.fxAt?.[id] || {}, at = p.at || "all";
    return `<div class="fxrow"><b title="${esc(ST.cat.fx[id]?.pack || "")}">${esc(ST.cat.fx[id]?.name || id)}</b>` +
      `<div class="seg mini">${[["all", "Tümü"], ["in", "Giriş"], ["out", "Çıkış"]].map(([v, l]) => `<button data-fxat="${id}|${v}" class="${at === v ? "on" : ""}">${l}</button>`).join("")}</div>` +
      (at !== "all" ? `<input type="number" class="num" data-fxd="${id}" min="0.1" max="10" step="0.1" value="${p.d ?? 1}" title="saniye">` : "<span></span>") +
      `<button data-unfx="${id}" title="Kaldır">✕</button></div>`;
  }).join("");
}
window.fxRows = fxRows;

$("#insp").addEventListener("click", e => {
  const c = selClips()[0];
  const fv = e.target.closest("[data-fav]");
  if (fv) { e.stopPropagation(); const [k, id] = fv.dataset.fav.split("|"); favToggle(k, id); renderInsp(); return; }
  const at = e.target.closest("[data-atab]");
  if (at) { const [sc, s] = at.dataset.atab.split("|"); animTab[sc] = s; renderInsp(); return; }
  const an = e.target.closest("[data-anim]");
  if (an && c) {
    const [sc, slot, id] = an.dataset.anim.split("|"); snap();
    for (const x of selClips()) if (sc === "clip" ? ["video", "image"].includes(clipKind(x)) : clipKind(x) === "text" && !x.subscribe && !x.graphic && !x.words) setAnim(x, sc, slot, id);
    if (sc === "text") assDirty?.();
    changed(false); renderInsp();
    if (id !== "none") {   // goster: animasyonun oldugu bolgeye git ve oynat
      const d = sc === "clip" ? (c.anim?.[slot + "Dur"] ?? .5) : (c.style?.[slot + "Dur"] ?? .45);
      const t0 = slot === "out" ? c.start + c.dur - d - .25 : c.start;
      seek(Math.max(0, t0)); if (!ST.playing) play();
      clearTimeout(window._animStop); window._animStop = setTimeout(() => { if (ST.playing) play(); }, (slot === "loop" ? 2200 : (d + .6) * 1000));
    }
    return;
  }
  const fa = e.target.closest("[data-fxat]");
  if (fa && c) { const [id, v] = fa.dataset.fxat.split("|"); snap(); c.fxAt = { ...(c.fxAt || {}) }; if (v === "all") delete c.fxAt[id]; else c.fxAt[id] = { ...(c.fxAt[id] || { d: 1 }), at: v }; if (!Object.keys(c.fxAt).length) delete c.fxAt; changed(false); renderInsp(); }
});
$("#insp").addEventListener("change", e => {
  const el = e.target.closest("[data-fxd]"); if (!el) return;
  const c = selClips()[0]; if (!c) return; snap();
  c.fxAt = { ...(c.fxAt || {}) }; c.fxAt[el.dataset.fxd] = { ...(c.fxAt[el.dataset.fxd] || { at: "in" }), d: clamp(+el.value || 1, .1, Math.max(.1, c.dur)) }; changed(false);
});
// panellerdeki ★
$("#panelBody").addEventListener("click", e => {
  const fv = e.target.closest("[data-fav]"); if (!fv) return;
  e.stopPropagation(); e.preventDefault();
  const [k, id] = fv.dataset.fav.split("|"); favToggle(k, id); renderPanel();
}, true);

// ---------------------------------------------------------------- sag tik menusu
const ctx = document.createElement("div"); ctx.id = "ctxMenu"; ctx.hidden = true; document.body.appendChild(ctx);
function ctxClose() { ctx.hidden = true; ctx.innerHTML = ""; }
function ctxOpen(x, y, items) {
  ctx.innerHTML = items.map((it, i) => it === "-" ? '<hr>' : `<button data-i="${i}"${it.dis ? " disabled" : ""}${it.red ? ' class="red"' : ""}><span>${it.ic || ""}</span>${esc(it.l)}${it.k ? `<kbd>${it.k}</kbd>` : ""}</button>`).join("");
  ctx.hidden = false;
  const r = ctx.getBoundingClientRect();
  ctx.style.left = Math.min(x, innerWidth - r.width - 6) + "px"; ctx.style.top = Math.min(y, innerHeight - r.height - 6) + "px";
  ctx.onclick = ev => { const b = ev.target.closest("[data-i]"); if (!b) return; const it = items[+b.dataset.i]; ctxClose(); it.f?.(); };
}
document.addEventListener("pointerdown", e => { if (!ctx.hidden && !ctx.contains(e.target)) ctxClose(); }, true);
document.addEventListener("keydown", e => { if (e.key === "Escape" && !ctx.hidden) { ctxClose(); e.stopPropagation(); } }, true);
window.addEventListener("blur", ctxClose);

function clipMenu(c, e) {
  if (!ST.sel.has(c.id)) { ST.sel = new Set([c.id]); renderTimeline(); renderInsp(); renderHandles(); }
  const k = clipKind(c), a = assetOf(c), n = ST.sel.size;
  const vis = ["video", "image"].includes(k);
  const items = [
    { ic: "✂", l: "Oynatma kafasında böl", k: "S", f: splitAtPlayhead, dis: !(ST.t > c.start && ST.t < c.start + c.dur) },
    { ic: "⧉", l: "Çoğalt", k: "Ctrl+D", f: dupSel }, { ic: "⎘", l: "Kopyala", k: "Ctrl+C", f: copySel },
    "-",
  ];
  if (k === "video" && a?.audio) items.push({ ic: "♪", l: c.detached ? "Ses zaten ayrı" : "Sesi ayrı ize ayır", f: () => detachAudio(), dis: !!c.detached || (c.vol === 0) });
  if (k === "video") items.push({ ic: "❄", l: "Kareyi dondur", k: "Shift+F", f: () => freezeFrame?.() }, { ic: "✂", l: n > 1 ? `Arka planı sil (${n} klip)` : "Arka planı sil (bu klip)", f: () => matteSel() });
  if (vis) items.push({ ic: "✦", l: "Animasyon ekle…", f: () => { animTab.clip = "in"; renderInsp(); $("#insp .atabs")?.scrollIntoView({ block: "center" }); } },
    { ic: "◐", l: "Renk sayfasında düzenle", f: () => setPage("color") });
  if (k === "text" && !c.subscribe && !c.graphic) items.push({ ic: "T", l: "Animasyon seç…", f: () => { animTab.text = "in"; renderInsp(); $("#insp .atabs")?.scrollIntoView({ block: "center" }); } });
  items.push({ ic: "⇤", l: "Klibin başına git", f: () => seek(c.start) }, { ic: "⇥", l: "Klibin sonuna git", f: () => seek(c.start + c.dur) }, "-",
    { ic: "🗑", l: n > 1 ? `${n} klibi sil` : "Sil", k: "Del", red: true, f: () => deleteSel(false) },
    { ic: "⇠", l: "Sil ve boşluğu kapat", k: "Shift+Del", red: true, f: () => deleteSel(true) });
  ctxOpen(e.clientX, e.clientY, items);
}
function laneMenu(tid, t, e) {
  const tk = ST.p.tracks.find(x => x.id === tid);
  const items = [
    { ic: "▸", l: "Oynatma kafasını buraya al", f: () => seek(t) },
    { ic: "⎀", l: "Yapıştır", k: "Ctrl+V", f: () => { seek(t); paste(); } },
    { ic: "◆", l: "Buraya işaret koy", k: "M", f: () => addMarker(t) },
  ];
  if (tk?.kind === "text") items.push({ ic: "T", l: "Buraya metin ekle", f: () => { setPanelSafe("text"); window.dropItem?.({ type: "text", preset: 0 }, t, tid); } });
  if (tk?.kind === "fx") items.push({ ic: "✦", l: "Efekt ekle…", f: () => setPanelSafe("fx") });
  items.push("-", ...trackItems(tk));
  ctxOpen(e.clientX, e.clientY, items);
}
function setPanelSafe(p) { if (document.body.dataset.page !== "edit") setPage("edit"); renderPanel(p); }
function trackItems(tk) {
  if (!tk) return [];
  const n = ST.p.clips.filter(c => c.track === tk.id).length;
  return [
    { ic: "✎", l: "İzi yeniden adlandır", f: async () => { const v = await askText("İz adı", tk.name); if (v) { snap(); tk.name = v; changed(false); } } },
    { ic: tk.lock ? "🔓" : "🔒", l: tk.lock ? "Kilidi aç" : "Kilitle", f: () => { snap(); tk.lock = !tk.lock; changed(false); } },
    { ic: "◌", l: tk.hide ? "Göster" : "Gizle", f: () => { snap(); tk.hide = !tk.hide; changed(false); } },
    ...(tk.kind === "video" || tk.kind === "audio" ? [{ ic: "🔇", l: tk.mute ? "Sesi aç" : "Sessize al", f: () => { snap(); tk.mute = !tk.mute; changed(false); } }] : []),
    { ic: "＋", l: "Aynı türden iz ekle", f: () => { snap(); addTrack(tk.kind); changed(false); } },
    { ic: "↑", l: "Yukarı taşı", f: () => moveTrack(tk, -1) }, { ic: "↓", l: "Aşağı taşı", f: () => moveTrack(tk, 1) },
    "-",
    { ic: "🗑", l: n ? `İzi sil (${n} klip de silinir)` : "İzi sil", red: true, f: () => deleteTrack(tk) },
  ];
}
async function askText(title, val) {
  return modal(`<h3>${esc(title)}</h3><input class="in" id="mIn" value="${esc(val || "")}" style="width:100%"><div class="row"><button class="tb" data-v="">Vazgeç</button><button class="tb pri" data-v="ok">Tamam</button></div>`,
    { init: m => { const i = $("#mIn", m); i.focus(); i.select(); i.onkeydown = ev => { if (ev.key === "Enter") m.querySelector('[data-v="ok"]').click(); }; }, collect: () => $("#mIn").value.trim() });
}
function moveTrack(tk, dir) {
  const ts = ST.p.tracks, i = ts.indexOf(tk), j = i + dir;
  if (j < 0 || j >= ts.length) return;
  snap(); [ts[i], ts[j]] = [ts[j], ts[i]]; changed(false);
}
async function deleteTrack(tk) {
  const same = ST.p.tracks.filter(t => t.kind === tk.kind);
  const n = ST.p.clips.filter(c => c.track === tk.id).length;
  if (n && !await modal(`<h3>“${esc(tk.name)}” izi silinsin mi?</h3><div class="hint">İçindeki ${n} klip de silinir. Geri al (Ctrl+Z) ile dönebilirsin.</div><div class="row"><button class="tb" data-v="">Vazgeç</button><button class="tb pri red" data-v="ok">Sil</button></div>`)) return;
  snap();
  ST.p.clips = ST.p.clips.filter(c => c.track !== tk.id);
  ST.p.tracks = ST.p.tracks.filter(t => t !== tk);
  if (tk.id === "v1" && same.length > 1) { const nv = ST.p.tracks.find(t => t.kind === "video"); if (nv) { for (const c of ST.p.clips) if (c.track === nv.id) c.track = "v1"; nv.id = "v1"; } }
  for (const id of [...ST.sel]) if (!ST.p.clips.some(c => c.id === id)) ST.sel.delete(id);
  changed(); toast(`“${tk.name}” silindi`);
}
function headMenu(tid, e) { const tk = ST.p.tracks.find(x => x.id === tid); ctxOpen(e.clientX, e.clientY, trackItems(tk)); }

function assetMenu(aid, e) {
  const a = ST.p.assets[aid]; if (!a) return;
  const used = ST.p.clips.filter(c => c.asset === aid).length;
  ctxOpen(e.clientX, e.clientY, [
    { ic: "＋", l: "Oynatma kafasına ekle", f: () => dropAsset(aid, ST.t, null) },
    { ic: "⇥", l: "Sona ekle", f: () => appendAsset(aid) },
    { ic: "📁", l: "Klasörde göster", f: () => api.studio_reveal?.(a.path) },
    "-",
    { ic: "🗑", l: used ? `Projeden kaldır (${used} klip de silinir)` : "Projeden kaldır", red: true, f: () => { snap(); ST.p.clips = ST.p.clips.filter(c => c.asset !== aid); delete ST.p.assets[aid]; ST.binSel?.delete(aid); changed(); renderPanel(); } },
  ]);
}
function viewMenu(e) {
  const c = ST.p.clips.find(x => ST.sel.has(x.id));
  ctxOpen(e.clientX, e.clientY, [
    { ic: ST.playing ? "❚❚" : "▶", l: ST.playing ? "Durdur" : "Oynat", k: "Boşluk", f: play },
    { ic: "📷", l: "Bu kareyi PNG kaydet", f: () => $('[data-a="snapshot"]')?.click() },
    { ic: "▣", l: "Güvenli alan çizgileri", f: () => document.body.classList.toggle("safe") },
    { ic: "⛶", l: "Tam ekran", k: "F", f: () => $('[data-a="full"]')?.click() },
    ...(c ? ["-", { ic: "⟲", l: "Konum / ölçeği sıfırla", f: () => { snap(); delete c.x; delete c.y; delete c.scale; delete c.rot; changed(); } }] : []),
  ]);
}
document.addEventListener("contextmenu", e => {
  const tag = e.target.tagName;
  if (tag === "INPUT" || tag === "TEXTAREA") return;   // metin kutularinda kes/kopyala menusu kalsin
  e.preventDefault();
  if (!ST.p) return;
  const mk = e.target.closest(".mkh"); if (mk) { markerMenu(+mk.dataset.i, e); return; }
  const cl = e.target.closest(".clip[data-cid]"); if (cl) { const c = ST.p.clips.find(x => x.id === cl.dataset.cid); if (c) clipMenu(c, e); return; }
  const th = e.target.closest(".th[data-tid]"); if (th) { headMenu(th.dataset.tid, e); return; }
  const ln = e.target.closest(".lane[data-tid]"); if (ln) { laneMenu(ln.dataset.tid, tAt(e.clientX), e); return; }
  if (e.target.closest("#ruler")) { const t = tAt(e.clientX); ctxOpen(e.clientX, e.clientY, [{ ic: "◆", l: "Buraya işaret koy", f: () => addMarker(t) }, { ic: "▸", l: "Buraya git", f: () => seek(t) }, ...(ST.p.markers?.length ? [{ ic: "🗑", l: "Tüm işaretleri sil", red: true, f: () => { snap(); ST.p.markers = []; changed(false); } }] : [])]); return; }
  const as = e.target.closest("[data-aid]"); if (as) { assetMenu(as.dataset.aid, e); return; }
  if (e.target.closest("#viewArea, #stage")) { viewMenu(e); return; }
});

// ---------------------------------------------------------------- isaretler
const MK_COL = { note: "#FFB547", red: "#FF4F6D", green: "#2EE6A6", blue: "#5AA8FF", violet: "#A78BFA" };
function addMarker(t, label) {
  snap(); (ST.p.markers ||= []).push({ t: +(+t).toFixed(3), kind: "note", ...(label ? { label } : {}) });
  ST.p.markers.sort((a, b) => a.t - b.t); changed(false);
}
window.addMarker = addMarker;
function renderMarkers() {
  const host = $("#ruler"); if (!host || !ST.p) return;
  $$(".mkh", host).forEach(m => m.remove());
  (ST.p.markers || []).forEach((m, i) => {
    const d = document.createElement("div"); d.className = "mkh"; d.dataset.i = i;
    d.style.left = (m.t * ST.px) + "px"; d.style.setProperty("--mc", MK_COL[m.kind] || MK_COL.note);
    d.title = `${m.label ? m.label + " · " : ""}${fmt(m.t)} — sürükle: taşı · çift tık: ad · sağ tık: menü · Alt+tık: sil`;
    if (m.label) d.innerHTML = `<span>${esc(m.label)}</span>`;
    host.appendChild(d);
  });
}
function markerMenu(i, e) {
  const m = ST.p.markers[i]; if (!m) return;
  ctxOpen(e.clientX, e.clientY, [
    { ic: "▸", l: "Bu işarete git", f: () => seek(m.t) },
    { ic: "✎", l: m.label ? "Adı değiştir" : "Ad ver", f: async () => { const v = await askText("İşaret adı", m.label || ""); if (v != null) { snap(); if (v) m.label = v; else delete m.label; changed(false); } } },
    { ic: "●", l: "Renk: turuncu", f: () => mkColor(m, "note") }, { ic: "●", l: "Renk: kırmızı", f: () => mkColor(m, "red") },
    { ic: "●", l: "Renk: yeşil", f: () => mkColor(m, "green") }, { ic: "●", l: "Renk: mavi", f: () => mkColor(m, "blue") },
    "-",
    { ic: "🗑", l: "İşareti sil", red: true, f: () => { snap(); ST.p.markers.splice(i, 1); changed(false); } },
  ]);
}
function mkColor(m, k) { snap(); m.kind = k; changed(false); }
$("#ruler").addEventListener("pointerdown", e => {
  const h = e.target.closest(".mkh"); if (!h || e.button !== 0) return;
  e.stopPropagation(); e.preventDefault();
  const i = +h.dataset.i, m = ST.p.markers[i]; if (!m) return;
  if (e.altKey) { snap(); ST.p.markers.splice(i, 1); changed(false); return; }
  const x0 = e.clientX, t0 = m.t; let moved = false;
  h.setPointerCapture(e.pointerId);
  h.onpointermove = ev => {
    if (!moved && Math.abs(ev.clientX - x0) < 3) return;
    if (!moved) { snap(); moved = true; }
    let t = Math.max(0, t0 + (ev.clientX - x0) / ST.px);
    if (ST.snap && !ev.shiftKey) { const ex = new Set(); t = snapT(t, snapTargets(ex).filter(v => Math.abs(v - t0) > 1e-6))[0]; }
    m.t = +t.toFixed(3); h.style.left = (m.t * ST.px) + "px";
  };
  h.onpointerup = () => { h.onpointermove = null; if (moved) { ST.p.markers.sort((a, b) => a.t - b.t); changed(false); } else seek(m.t); };
}, true);
$("#ruler").addEventListener("dblclick", async e => {
  const h = e.target.closest(".mkh"); if (!h) return;
  e.stopPropagation();
  const m = ST.p.markers[+h.dataset.i]; const v = await askText("İşaret adı", m.label || "");
  if (v != null) { snap(); if (v) m.label = v; else delete m.label; changed(false); }
}, true);

// zaman cizelgesi her cizildiginde isaret tutamaclarini da ciz + izlere silme dugmesi
const _rt = window.renderTimeline || renderTimeline;
renderTimeline = function () {
  _rt.apply(this, arguments);
  renderMarkers();
  for (const th of $$("#tlHeads .th")) if (!th.querySelector("[data-thdel]")) th.insertAdjacentHTML("beforeend", `<button data-thdel class="thdel" title="İzi sil">✕</button>`);
};
$("#tlHeads").addEventListener("click", e => {
  const b = e.target.closest("[data-thdel]"); if (!b) return;
  e.stopPropagation();
  const tk = ST.p.tracks.find(t => t.id === b.closest(".th").dataset.tid); if (tk) deleteTrack(tk);
}, true);

// ---------------------------------------------------------------- gezinme: isaretler ve kesim noktalari
function editPoints() {
  const s = new Set([0]);
  for (const c of ST.p.clips) { s.add(+c.start.toFixed(3)); s.add(+(c.start + c.dur).toFixed(3)); }
  return [...s].sort((a, b) => a - b);
}
function jump(list, dir) {
  const eps = 1 / (ST.p.fps * 2);
  const t = dir > 0 ? list.find(v => v > ST.t + eps) : [...list].reverse().find(v => v < ST.t - eps);
  if (t != null) seek(t); else toast(dir > 0 ? "Sonrası yok" : "Öncesi yok", 900);
}
document.addEventListener("keydown", e => {
  if (!ST.p || !$("#modal").hidden) return;
  const tag = document.activeElement?.tagName; if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return;
  const k = e.key;
  const mks = () => (ST.p.markers || []).map(m => m.t).sort((a, b) => a - b);
  if ((e.ctrlKey || e.altKey) && (k === "ArrowLeft" || k === "ArrowRight")) { e.preventDefault(); e.stopImmediatePropagation(); jump(mks(), k === "ArrowRight" ? 1 : -1); }
  else if (k === "ArrowUp" || k === "ArrowDown") { e.preventDefault(); jump(editPoints(), k === "ArrowDown" ? 1 : -1); }
  else if (k === "[" || k === "]") { e.preventDefault(); jump(mks(), k === "]" ? 1 : -1); }
  else if (k.toLowerCase() === "b" && !e.ctrlKey) { e.preventDefault(); splitAtPlayhead(); }
}, true);

// ---------------------------------------------------------------- sesi ayir
function detachAudio() {
  const vs = selClips().filter(c => clipKind(c) === "video" && assetOf(c)?.audio && !c.detached);
  if (!vs.length) { toast("Sesi olan bir video klip seç"); return; }
  snap();
  const nw = [];
  for (const c of vs) {
    let tk = ST.p.tracks.find(t => t.kind === "audio" && !ST.p.clips.some(o => o.track === t.id && o.start < c.start + c.dur && o.start + o.dur > c.start));
    if (!tk) { const id = addTrack("audio", "Ayrılan ses"); tk = ST.p.tracks.find(t => t.id === id); }
    const a = addClip({ asset: c.asset, track: tk.id, start: c.start, dur: c.dur, in: c.in || 0, speed: c.speed, vol: c.vol ?? 1, fadeIn: c.fadeIn, fadeOut: c.fadeOut, afx: c.afx, link: c.id });
    for (const k of Object.keys(a)) if (a[k] === undefined) delete a[k];
    c.vol = 0; c.detached = a.id; delete c.afx;
    nw.push(a.id);
  }
  ST.sel = new Set(nw); changed(); toast(vs.length > 1 ? `${vs.length} klibin sesi ayrıldı` : "Ses ayrı ize alındı");
}
window.detachAudio = detachAudio;

// ---------------------------------------------------------------- arka plan silme: secili klip(ler)
async function matteSel() {
  const vs = selClips().filter(c => clipKind(c) === "video");
  if (!vs.length) { toast("Önce bir video klip seç"); return; }
  if (vs.length === 1) return window.matte?.(vs[0]);
  const tot = vs.reduce((s, c) => s + c.dur * (c.speed || 1), 0);
  const m = await modal(`<h3>Arka planı sil (${vs.length} klip)</h3><div class="hint">Yalnız seçili kliplerin zaman çizelgesinde görünen kısımları işlenir (toplam ${tot.toFixed(1)} sn); videonun geri kalanına dokunulmaz. Sonuçlar şeffaf kopyalar olarak kliplerin yerine geçer.</div><div class="row"><button class="tb" data-v="">Vazgeç</button><button class="tb" data-v="birefnet-general-lite">Hızlı</button><button class="tb pri" data-v="birefnet-general">En iyi kalite</button></div>`);
  if (!m) return;
  for (const c of vs) { ST.sel = new Set([c.id]); await window.matte?.(c, m); }
}
window.matteSel = matteSel;

// ---------------------------------------------------------------- kisayol listesi
const KEYS = [
  ["Oynatma", [["Boşluk", "Oynat / durdur"], ["← →", "1 kare (Shift: 1 sn)"], ["↑ ↓", "Önceki / sonraki kesim noktası"], ["Ctrl+← →  ya da  [ ]", "Önceki / sonraki işaret"], ["Home / End", "Başa / sona"], ["F", "Tam ekran önizleme"]]],
  ["Kurgu", [["S  ya da  B", "Oynatma kafasında böl (✂)"], ["Q / W", "Oynatma kafasının solunu / sağını sil"], ["Del", "Sil"], ["Shift+Del", "Sil ve boşluğu kapat"], ["Shift+F", "Kareyi dondur"], ["Ctrl+C / V / D", "Kopyala / yapıştır / çoğalt"], ["Ctrl+A", "Tümünü seç"], ["Ctrl+L", "Bağlı video/ses kilidini aç/kapa"], ["Esc", "Seçimi kaldır"], ["Sağ tık", "Klip / iz / işaret menüsü"]]],
  ["İşaretler", [["M", "İşaret koy"], ["Sürükle", "İşareti taşı (cetvelde)"], ["Çift tık", "İşarete ad ver"], ["Alt+tık", "İşareti sil"]]],
  ["Proje", [["Ctrl+Z / Y", "Geri al / yinele"], ["Ctrl+S", "Kaydet (Shift: farklı kaydet)"], ["Ctrl+E", "Dışa aktar"], ["Ctrl+O", "Aç"], ["+ / −", "Zaman ölçeği (Ctrl+tekerlek)"], ["1-9", "Hızlı ses (Ses panelinde ★ ile ata)"], ["Shift+1…5", "Sayfalar: Medya, Kurgu, Renk, Ses, Teslim"]]],
];
document.addEventListener("click", e => {
  const b = e.target.closest('[data-a="keys"]'); if (!b) return;
  e.stopImmediatePropagation();
  modal(`<h3>Kısayollar</h3><div class="keygrid">${KEYS.map(([g, ks]) => `<div><div class="sec">${g}</div><div class="keys">${ks.map(([k, v]) => `<kbd>${k}</kbd><span>${v}</span>`).join("")}</div></div>`).join("")}</div><div class="row"><button class="tb pri" data-v="ok">Tamam</button></div>`);
}, true);
// dugmelere kisayol ipucu
for (const [a, tip] of [["split", "Böl (S / B)"], ["del", "Sil (Del)"], ["undo", "Geri al (Ctrl+Z)"], ["redo", "Yinele (Ctrl+Y)"], ["marker", "İşaret koy (M) · sağ tık: menü"], ["dup", "Çoğalt (Ctrl+D)"]]) {
  const b = document.querySelector(`[data-a="${a}"]`); if (b) b.title = tip;
}
