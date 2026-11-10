// Kami Player muzik modu (B7): sarki sozu paneli (gomulu / yan .lrc / LRCLIB / yapistir), karaoke satir dolgusu,
// kapak rengine gore parlama. player.js plStart sonunda window.plMusicStart(r) cagirir.
"use strict";

const PM = { lines: [], plain: "", idx: -1, raf: 0, token: 0, src: "" };
const pmCfg = () => (typeof PX !== "undefined" && PX.cfg) || {};

function pmParseLrc(text) {
  const out = [];
  let off = 0;
  for (const raw of String(text || "").split(/\r?\n/)) {
    const o = raw.match(/^\s*\[offset:\s*([+-]?\d+)\]/i);
    if (o) { off = +o[1] / 1000; continue; }
    const tags = [...raw.matchAll(/\[(\d{1,3}):(\d{2})(?:[.:](\d{1,3}))?\]/g)];
    if (!tags.length) continue;
    const txt = raw.replace(/\[[^\]]*\]/g, "").replace(/<\d{1,3}:\d{2}(?:[.:]\d{1,3})?>/g, "").trim();
    for (const t of tags) {
      const frac = t[3] ? +t[3] / 10 ** t[3].length : 0;
      out.push({ t: +t[1] * 60 + +t[2] + frac - off, text: txt });
    }
  }
  return out.sort((a, b) => a.t - b.t);
}

function pmEnsureDom() {
  if ($("#plLyr")) return;
  const a = $("#plAudio");
  a.insertAdjacentHTML("afterbegin", `
    <section class="pl-lyr" id="plLyr" hidden>
      <header class="pm-head"><div class="pm-cover" id="pmCover"></div><div class="pm-meta"><b id="pmTitle"></b><span id="pmArtist"></span></div>
        <button class="pl-b pm-edit" id="pmEdit" title="${plL("Sözleri yapıştır / düzenle", "Paste / edit lyrics")}">✎</button></header>
      <div class="pm-list" id="pmList"></div>
      <div class="pm-empty" id="pmEmpty" hidden></div>
    </section>`);
  $("#pmList").addEventListener("click", (e) => {
    const li = e.target.closest(".pm-l[data-t]");
    if (li) plSeek(+li.dataset.t, true);
  });
  $("#pmEdit").onclick = pmPasteBox;
  ["click", "dblclick"].forEach((ev) => $("#plLyr").addEventListener(ev, (e) => e.stopPropagation()));
}

// YouTube/indirme basliklarini temizle: [Official Music Video], (Lyrics), ft. ..., "Sanatci - Sarki"
function pmClean(s) {
  return String(s || "")
    .replace(/\s*[\[(【「][^\])】」]*[\])】」]/g, " ")
    .replace(/\b(official\s+(music\s+|lyric\s+)?(video|audio|visualizer)|music\s+video|lyric\s+video|lyrics?|audio|hd|hq|4k|mv|m\/v)\b/gi, " ")
    .replace(/\s+(ft\.?|feat\.?|featuring)\s+.*$/i, "")
    .replace(/[|｜].*$/, "")
    .replace(/\s{2,}/g, " ").replace(/^[\s\-–—]+|[\s\-–—]+$/g, "").trim();
}
function pmMeta(r) {
  const tg = r.tags || {};
  let artist = String(tg.artist || tg.album_artist || "").replace(/\s*(VEVO|- Topic|Official)\s*$/i, "").trim();
  const raw = tg.title || r.title || "";
  let title = pmClean(raw);
  const m = title.match(/^(.+?)\s+[-–—~]\s+(.+)$/);
  if (m) {   // "Sanatci - Sarki": kanal adi sanatci etiketine yazilmis olabilir, basliktaki sanatci daha guvenilir
    const a = m[1].trim(), t = m[2].trim();
    if (!artist || !t.toLowerCase().includes(artist.toLowerCase())) { artist = a; title = t; }
  }
  return { artist, title, album: tg.album || "" };
}

window.plMusicStart = async (r) => {
  pmEnsureDom();
  cancelAnimationFrame(PM.raf);
  Object.assign(PM, { lines: [], plain: "", idx: -1, src: "", token: PM.token + 1 });
  const tok = PM.token;
  const lyr = $("#plLyr"), au = $("#plAudio");
  pmGlow(r.kind === "audio" ? r.cover : "");
  if (r.kind === "video") pmVideoLyrics(r, tok);
  if (r.kind !== "audio") PM.meta = null;
  if (r.kind !== "audio" || pmCfg().lyrics === false) { lyr.hidden = true; au.classList.remove("has-lyr"); return; }
  const meta = pmMeta(r);
  PM.meta = meta;
  $("#pmTitle").textContent = meta.title || r.title;
  $("#pmArtist").textContent = [meta.artist, meta.album].filter(Boolean).join(" · ");
  $("#pmCover").style.backgroundImage = r.cover ? `url("${r.cover}")` : "";
  $("#pmCover").hidden = !r.cover;
  lyr.hidden = false; au.classList.add("has-lyr");
  $("#pmList").innerHTML = `<p class="pm-wait">${plL("Sözler aranıyor…", "Looking for lyrics…")}</p>`;
  $("#pmEmpty").hidden = true;
  let res;
  try { res = await slow("player_lyrics", r.path || "", meta.artist, meta.title, meta.album, r.duration || 0, pmCfg().lrclib !== false); }
  catch (e) { res = { ok: false, error: String(e) }; }
  if (tok !== PM.token) return;   // bu arada baska sarkiya gecildi
  pmShow(res);
};

function pmShow(res) {
  const list = $("#pmList"), empty = $("#pmEmpty");
  PM.lines = res?.synced ? pmParseLrc(res.synced) : [];
  PM.plain = res?.plain || "";
  PM.src = res?.source || "";
  PM.links = res?.links || {};
  PM.idx = -1;
  if (PM.lines.length) {
    list.innerHTML = PM.lines.map((l, i) => `<p class="pm-l${l.text ? "" : " gap"}" data-i="${i}" data-t="${l.t.toFixed(2)}"><span data-txt="${escapeHtml(l.text || "♪")}">${escapeHtml(l.text || "♪")}</span></p>`).join("")
      + `<p class="pm-src">${pmSrcName(PM.src)}</p>`;
    list.classList.add("synced");
    list.scrollTop = 0;
    pmLoop();
  } else if (PM.plain) {
    list.classList.remove("synced");
    list.innerHTML = PM.plain.split(/\r?\n/).map((x) => `<p class="pm-l plain">${escapeHtml(x) || "&nbsp;"}</p>`).join("") + `<p class="pm-src">${pmSrcName(PM.src)} · ${plL("zamanlama yok", "not synced")}</p>`;
    list.scrollTop = 0;
  } else {
    list.innerHTML = "";
    const L = PM.links;
    empty.innerHTML = `<p>${res?.instrumental ? plL("Enstrümantal parça.", "Instrumental track.") : plL("Söz bulunamadı.", "No lyrics found.")}</p>
      <div class="pm-acts"><button class="pl-b" data-a="paste">${plL("Sözleri yapıştır", "Paste lyrics")}</button>
      ${L.genius ? `<button class="pl-b" data-u="${escapeHtml(L.genius)}">Genius</button>` : ""}${L.azlyrics ? `<button class="pl-b" data-u="${escapeHtml(L.azlyrics)}">AZLyrics</button>` : ""}</div>`;
    empty.hidden = false;
    empty.querySelector("[data-a=paste]").onclick = pmPasteBox;
    empty.querySelectorAll("[data-u]").forEach((b) => b.onclick = () => api.open_link(b.dataset.u));
  }
}
function pmSrcName(s) {
  return { lrc: plL("yan .lrc dosyası", "sidecar .lrc"), txt: plL("yan .txt dosyası", "sidecar .txt"), tag: plL("dosyanın içindeki sözler", "embedded lyrics"), lrclib: "LRCLIB" }[s] || "";
}

function pmPasteBox() {
  const empty = $("#pmEmpty");
  $("#pmList").innerHTML = "";
  empty.hidden = false;
  empty.innerHTML = `<textarea id="pmText" spellcheck="false" placeholder="${plL("Sözleri buraya yapıştır. [01:23.45] zamanlı LRC de olur.", "Paste lyrics here. Timed LRC ([01:23.45]) works too.")}"></textarea>
    <div class="pm-acts"><button class="pl-b pri" data-a="save">${plL("Kaydet", "Save")}</button><button class="pl-b" data-a="cancel">${plL("Vazgeç", "Cancel")}</button></div>
    <p class="pm-hint">${plL("Şarkının yanına .lrc / .txt olarak kaydedilir; bir dahaki sefere oradan okunur.", "Saved next to the song as .lrc / .txt and read from there next time.")}</p>`;
  const ta = $("#pmText");
  ta.value = PM.lines.length ? PM.lines.map((l) => `[${String(Math.floor(l.t / 60)).padStart(2, "0")}:${(l.t % 60).toFixed(2).padStart(5, "0")}]${l.text}`).join("\n") : PM.plain;
  ta.addEventListener("keydown", (e) => e.stopPropagation());
  ta.focus();
  empty.querySelector("[data-a=cancel]").onclick = () => { empty.hidden = true; pmShow({ synced: PM.lines.length ? ta.dataset.orig : "", plain: PM.plain, source: PM.src, links: PM.links }); };
  ta.dataset.orig = ta.value;
  empty.querySelector("[data-a=save]").onclick = async () => {
    const text = ta.value.trim();
    if (!text) return;
    let r = { ok: false };
    if (PL.info?.path) { try { r = await api.player_lyrics_save(PL.info.path, text); } catch { /* asagida */ } }
    if (!r.ok && PL.info?.path) toast(plL("Dosyaya yazılamadı, sadece bu oturumda gösteriliyor", "Couldn't write the file, showing for this session only"), true);
    empty.hidden = true;
    const lrc = /^\s*\[\d{1,3}:\d{2}/m.test(text);
    pmShow({ synced: lrc ? text : "", plain: lrc ? "" : text, source: r.source || (lrc ? "lrc" : "txt"), links: PM.links });
  };
}

// aktif satir + karaoke dolgusu (satir basindan sonraki satira kadar soldan saga dolar)
function pmLoop() {
  cancelAnimationFrame(PM.raf);
  const step = () => {
    if (!PM.lines.length || !PL.open || $("#plLyr")?.hidden) return;
    const t = plNow() + 0.15;   // goz sozu biraz once gorsun
    let i = PM.idx;
    if (i < 0 || t < PM.lines[i].t || (PM.lines[i + 1] && t >= PM.lines[i + 1].t)) {
      i = -1;
      for (let k = 0; k < PM.lines.length; k++) { if (PM.lines[k].t <= t) i = k; else break; }
    }
    const list = $("#pmList");
    if (i !== PM.idx) {
      list.querySelectorAll(".pm-l.on, .pm-l.past").forEach((x) => x.classList.remove("on"));
      const prev = list.querySelector(`.pm-l[data-i="${PM.idx}"]`); if (prev) prev.classList.add("past");
      PM.idx = i;
      const cur = list.querySelector(`.pm-l[data-i="${i}"]`);
      if (cur) {
        cur.classList.add("on"); cur.classList.remove("past");
        list.querySelectorAll(".pm-l").forEach((x) => x.classList.toggle("past", +x.dataset.i < i));
        if (!PM.userScroll) list.scrollTo({ top: cur.offsetTop - list.clientHeight * 0.38, behavior: "smooth" });
      }
    }
    const cur = i >= 0 && list.querySelector(`.pm-l[data-i="${i}"]`);
    if (i !== PM.miniI) { PM.miniI = i; const ml = $("#pmMiniLine"); if (ml) ml.textContent = i >= 0 ? PM.lines[i].text : ""; }
    if (cur) cur.classList.toggle("nok", pmCfg().karaoke === false);
    if (cur && pmCfg().karaoke !== false) {
      const a = PM.lines[i].t, b = PM.lines[i + 1] ? PM.lines[i + 1].t : a + 5;
      const k = Math.max(0, Math.min(1, (t - a) / Math.max(0.4, Math.min(b - a, 12))));
      cur.style.setProperty("--k", (k * 100).toFixed(1) + "%");
    }
    PM.raf = requestAnimationFrame(step);
  };
  PM.raf = requestAnimationFrame(step);
}
// kullanici elle kaydirirsa 4 sn otomatik kaydirma durur
document.addEventListener("wheel", (e) => {
  if (!e.target.closest?.("#pmList")) return;
  PM.userScroll = true; clearTimeout(PM.usT); PM.usT = setTimeout(() => { PM.userScroll = false; }, 4000);
}, { passive: true });
document.addEventListener("play", (e) => { if (e.target.id === "plVideo" && PM.lines.length) pmLoop(); }, true);
document.addEventListener("seeked", () => { PM.idx = -1; }, true);

// kapak rengi: canli (doygun) piksellerin agirlikli ortalamasi -> --pl-glow
function pmGlow(url) {
  const root = $("#player");
  if (!root) return;
  if (!url || pmCfg().glow === false) { root.style.removeProperty("--pl-glow"); root.style.removeProperty("--pl-glow2"); return; }
  const img = new Image();
  img.crossOrigin = "anonymous";
  img.onload = () => {
    try {
      const c = document.createElement("canvas"); c.width = c.height = 40;
      const g = c.getContext("2d", { willReadFrequently: true }); g.drawImage(img, 0, 0, 40, 40);
      const d = g.getImageData(0, 0, 40, 40).data;
      let r = 0, gg = 0, b = 0, w = 0;
      for (let i = 0; i < d.length; i += 4) {
        const mx = Math.max(d[i], d[i + 1], d[i + 2]), mn = Math.min(d[i], d[i + 1], d[i + 2]);
        const sat = mx ? (mx - mn) / mx : 0, val = mx / 255;
        const wt = sat * sat * (val > 0.15 ? val : 0) + 0.002;
        r += d[i] * wt; gg += d[i + 1] * wt; b += d[i + 2] * wt; w += wt;
      }
      let R = r / w, G = gg / w, B = b / w;
      const mx = Math.max(R, G, B) || 1, boost = 220 / mx;   // parlakligi esitle (koyu kapakta da gorunsun)
      R = Math.min(255, R * boost); G = Math.min(255, G * boost); B = Math.min(255, B * boost);
      root.style.setProperty("--pl-glow", `${R | 0}, ${G | 0}, ${B | 0}`);
      root.style.setProperty("--pl-glow2", `${(R * 0.55) | 0}, ${(G * 0.55) | 0}, ${(B * 0.55) | 0}`);
    } catch { root.style.removeProperty("--pl-glow"); }
  };
  img.src = url;
}

// ---------- mini oynatici (B7): YouTube PiP gibi cercevesiz, hep ustte kart; surukle tasi, cift tik / ⤢ / Esc buyut ----------
window.plMini = async (on) => {
  if (!window.KAMI_PLAYER_WINDOW || !PL.open) return;
  on = on == null ? !PL.mini : !!on;
  if (on === !!PL.mini) return;
  const v = $("#plVideo"), isVid = PL.info?.kind === "video";
  if (on && PL.full) { PL.full = false; $("#player").classList.remove("full"); api.player_fullscreen(false); await new Promise((r) => setTimeout(r, 350)); }
  PL.mini = on;
  let bar = $("#plMini");
  if (!bar) {
    $("#player").insertAdjacentHTML("beforeend", `
      <div class="pl-mini" id="plMini"><div class="pmi-cover" id="pmiCover"></div>
        <div class="pmi-txt"><b id="pmiTitle"></b><span id="pmMiniLine"></span></div>
        <div class="pmi-btns"><button data-m="prev" title="${plL("Önceki", "Previous")}">⏮</button><button data-m="toggle" class="pmi-play" id="pmiPlay" title="${plL("Oynat / duraklat", "Play / pause")}">⏸</button><button data-m="next" title="${plL("Sonraki", "Next")}">⏭</button><button data-m="exit" title="${plL("Büyüt (Esc)", "Expand (Esc)")}">⤢</button></div>
        <i class="pmi-prog" id="pmiProg"></i></div>`);
    bar = $("#plMini");
    bar.addEventListener("click", (e) => {
      e.stopPropagation();
      const b = e.target.closest("button[data-m]"); if (!b) return;
      ({ prev: () => window.plQueueStep?.(-1), next: () => window.plQueueStep?.(1), toggle: () => plToggle(), exit: () => window.plMini(false) })[b.dataset.m]();
    });
    v.addEventListener("timeupdate", () => {
      if (!PL.mini) return;
      const p = $("#pmiProg"); if (p && PL.dur) p.style.width = Math.min(100, plNow() / PL.dur * 100).toFixed(2) + "%";
    });
    ["play", "pause"].forEach((ev) => v.addEventListener(ev, () => { const b = $("#pmiPlay"); if (b) b.textContent = v.paused ? "▶" : "⏸"; }));
    pmMiniDrag();
  }
  const r = PL.info || {};
  $("#pmiTitle").textContent = (!isVid && PM.meta && PM.meta.title && (PM.meta.artist ? PM.meta.artist + " — " : "") + PM.meta.title) || r.title || "";
  $("#pmiCover").style.backgroundImage = r.cover ? `url("${r.cover}")` : "";
  $("#pmiCover").hidden = !r.cover || isVid;
  $("#pmiPlay").textContent = v.paused ? "▶" : "⏸";
  PM.miniI = PM.idx;
  $("#pmMiniLine").textContent = PM.lines.length && PM.idx >= 0 ? PM.lines[PM.idx].text : (isVid ? "" : [PM.meta?.artist, PM.meta?.album].filter(Boolean).join(" · "));
  window.plPanelClose?.();
  if ($("#plDict")) $("#plDict").hidden = true;
  $("#player").classList.toggle("mini", on);
  $("#player").classList.toggle("mini-vid", on && isVid);
  let res;
  try { res = await api.player_mini(on, isVid ? "video" : "audio", v.videoWidth && v.videoHeight ? v.videoWidth / v.videoHeight : 0); } catch (e) { res = { ok: false }; }
  if (on && !res?.ok) { PL.mini = false; $("#player").classList.remove("mini", "mini-vid"); toast(plL("Mini oynatıcı açılamadı", "Mini player failed"), true); }
};
// cercevesiz pencerede tasima: fareyle surukle (pencere imlecin altinda kayar, screenX farki kullanilir)
function pmMiniDrag() {
  let drag = null, moved = false, acc = [0, 0], busy = false;
  const flush = async () => {
    if (busy || (!acc[0] && !acc[1])) return;
    busy = true; const [dx, dy] = acc; acc = [0, 0];
    try { await api.player_mini_move(dx, dy); } catch { /* yok */ }
    busy = false; if (acc[0] || acc[1]) flush();
  };
  document.addEventListener("pointerdown", (e) => {
    if (!PL.mini || e.button !== 0 || e.target.closest("button")) return;
    drag = { x: e.screenX, y: e.screenY }; moved = false;
  }, true);
  document.addEventListener("pointermove", (e) => {
    if (!drag) return;
    const dx = e.screenX - drag.x, dy = e.screenY - drag.y;
    if (!moved && Math.abs(dx) + Math.abs(dy) < 4) return;
    moved = true; drag = { x: e.screenX, y: e.screenY };
    acc[0] += dx; acc[1] += dy; flush();
  }, true);
  document.addEventListener("pointerup", () => { drag = null; }, true);
  document.addEventListener("click", (e) => { if (PL.mini && moved) { e.stopPropagation(); e.preventDefault(); moved = false; } }, true);
  document.addEventListener("dblclick", (e) => { if (PL.mini && !e.target.closest("button")) { e.stopPropagation(); e.preventDefault(); window.plMini(false); } }, true);
}

// ---------- sarki gecisi (B7): bosluksuz (siradakini onceden hazirla, bitmeden hemen gec) / crossfade ----------
// Crossfade: biten sarkinin kuyrugu ayri bir <audio> ile sessizlesirken siradaki ana oynaticida yukselir.
const PG = { pre: null, preFor: "", xf: null, advanced: 0 };
function pgNextPath() {
  if (typeof PX === "undefined" || PX.qi < 0 || PX.qi >= PX.queue.length - 1 || PX.nextCancel) return "";
  return PX.queue[PX.qi + 1];
}
const _pgOpen = window.playerOpenPath;
window.playerOpenPath = async (path, queue) => {
  if (PG.pre && PG.pre.path === path && PG.pre.r?.ok) {   // onceden kaydedildi: ffprobe beklemeden basla
    const r = PG.pre.r; PG.pre = null;
    if (queue && queue.length && typeof PX !== "undefined") PX.pending = queue;
    plStart(r); return;
  }
  return _pgOpen(path, queue);
};
document.addEventListener("timeupdate", async (e) => {
  if (e.target.id !== "plVideo" || !PL.open || PL.info?.kind !== "audio") return;
  const v = e.target, left = (PL.dur || v.duration || 0) - plNow();
  if (!isFinite(left) || left <= 0) return;
  const next = pgNextPath();
  if (!next) return;
  if (left < 20 && PG.preFor !== PL.info.path) {   // siradakini hazirla
    PG.preFor = PL.info.path;
    try { const r = await api.player_open_path(next); PG.pre = { path: next, r }; } catch { PG.pre = null; }
  }
  const xf = +pmCfg().xfade || 0;
  if (Date.now() - PG.advanced < 3000) return;
  if (xf > 0 && left <= xf && !v.paused && PL.mode === "direct" && PL.info.direct_url) {
    PG.advanced = Date.now();
    pgCrossfade(v, left);
  } else if (xf === 0 && left <= 0.32 && !v.paused) {
    PG.advanced = Date.now();
    window.plQueueStep?.(1);
  }
}, true);
function pgCrossfade(v, left) {
  const tail = new Audio(PL.info.direct_url);
  tail.crossOrigin = "anonymous";
  const vol0 = Math.min(1, v.muted ? 0 : v.volume * (PL.vol > 1 ? 1 : 1));
  tail.volume = vol0;
  tail.currentTime = plNow();
  tail.play().catch(() => {});
  PG.xf && clearInterval(PG.xf.t);
  const dur = Math.max(1, left) * 1000, t0 = performance.now();
  const target = v.volume;
  window.plQueueStep?.(1);
  const nv = $("#plVideo");
  nv.volume = 0;
  const t = setInterval(() => {
    const k = Math.min(1, (performance.now() - t0) / dur);
    tail.volume = Math.max(0, vol0 * (1 - k));
    nv.volume = Math.min(target, target * k);
    if (k >= 1) { clearInterval(t); tail.pause(); tail.src = ""; nv.volume = target; }
  }, 50);
  PG.xf = { t };
}
const _pgEnded = window.plOnEnded;
window.plOnEnded = () => { if (Date.now() - PG.advanced < 3000) return; _pgEnded?.(); };

// ---------- muzik klipleri (video): sozler altyazi izi olarak (yan .lrc / gomulu / LRCLIB), yapistirilabilir ----------
function pmLrcToVtt(lrc, dur) {
  const L = pmParseLrc(lrc).filter((l) => l.text);
  const ts = (t) => { t = Math.max(0, t); const h = Math.floor(t / 3600), m = Math.floor(t % 3600 / 60), s = (t % 60).toFixed(3).padStart(6, "0"); return `${String(h).padStart(2, "0")}:${String(m).padStart(2, "0")}:${s}`; };
  return "WEBVTT\n\n" + L.map((l, i) => `${ts(l.t)} --> ${ts(Math.min(L[i + 1] ? L[i + 1].t : l.t + 5, l.t + 8, dur || 1e9))}\n${l.text}`).join("\n\n");
}
function pmAddLyricTrack(lrc, src, select) {
  const vtt = pmLrcToVtt(lrc, PL.dur);
  const url = "data:text/vtt;charset=utf-8," + encodeURIComponent(vtt);
  PL.subList = (PL.subList || []).filter((x) => !x.lyrics);
  PL.subList.push({ label: plL("Şarkı sözleri", "Lyrics") + (src ? " · " + src : ""), url, raw: "", lang: "", lyrics: true });
  const sel = $("#plSub");
  sel.innerHTML = `<option value="-1">${plL("Altyazı yok", "No subtitles")}</option>` + PL.subList.map((x, i) => `<option value="${i}">${escapeHtml(x.label)}</option>`).join("");
  sel.hidden = false;
  if (select) { sel.value = String(PL.subList.length - 1); plLoadSub(PL.subList.length - 1); } else sel.value = String(PL.subIdx ?? -1);
}
async function pmVideoLyrics(r, tok) {
  if (pmCfg().lyrics === false || !r.path) return;
  const meta = pmMeta(r);
  const musicish = (r.duration || 0) < 15 * 60 && /\s[-–—]\s/.test(String(r.tags?.title || r.title || ""));
  let res;
  try { res = await slow("player_lyrics", r.path, meta.artist, meta.title, meta.album, r.duration || 0, musicish && pmCfg().lrclib !== false); } catch { return; }
  if (tok !== PM.token || !res?.synced) return;
  pmAddLyricTrack(res.synced, pmSrcName(res.source), !(PL.subIdx >= 0));
}
window.pmPasteVideoLyrics = () => {
  if (!PL.open || !PL.info?.path) return;
  $("#pmVPaste")?.remove();
  const box = document.createElement("div");
  box.id = "pmVPaste"; box.className = "pm-vpaste";
  box.innerHTML = `<b>${plL("Şarkı sözlerini yapıştır", "Paste lyrics")}</b><textarea spellcheck="false" placeholder="${plL("LRCLIB'den kopyaladığın zamanlı sözler ([00:12.34] satır)", "Timed LRC lines from LRCLIB")}"></textarea>
    <div><button class="pl-b pri" data-a="ok">${plL("Kaydet ve göster", "Save & show")}</button><button class="pl-b" data-a="no">${plL("Vazgeç", "Cancel")}</button></div>`;
  ["click", "dblclick", "keydown", "pointerdown"].forEach((ev) => box.addEventListener(ev, (e) => e.stopPropagation()));
  $("#player").appendChild(box);
  const ta = box.querySelector("textarea"); ta.focus();
  box.querySelector("[data-a=no]").onclick = () => box.remove();
  box.querySelector("[data-a=ok]").onclick = async () => {
    const t = ta.value.trim();
    if (!/^\s*\[\d{1,3}:\d{2}/m.test(t)) { toast(plL("Zamanlı satır bulunamadı ([01:23.45] biçimi gerekir)", "No timed lines found"), true); return; }
    try { await api.player_lyrics_save(PL.info.path, t); } catch { /* yalnizca bu oturum */ }
    pmAddLyricTrack(t, plL("yapıştırılan", "pasted"), true);
    box.remove(); toast(plL("Sözler altyazı olarak eklendi", "Lyrics added as subtitles"));
  };
};
