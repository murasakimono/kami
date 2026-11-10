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

function pmMeta(r) {
  const tg = r.tags || {};
  let artist = tg.artist || tg.album_artist || "", title = tg.title || "";
  if (!title) {   // "Sanatci - Sarki" dosya adi
    const base = String(r.title || "").replace(/\s*[\[(].*?[\])]\s*/g, " ").trim();
    const m = base.match(/^(.+?)\s+[-–—]\s+(.+)$/);
    if (m) { artist = artist || m[1].trim(); title = m[2].trim(); } else title = base;
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

// ---------- mini oynatici (B7): kucuk, hep ustte; kapak + baslik + o anki soz satiri + kontroller ----------
window.plMini = (on) => {
  if (!window.KAMI_PLAYER_WINDOW || !PL.open) return;
  on = on == null ? !PL.mini : !!on;
  PL.mini = on;
  let bar = $("#plMini");
  if (!bar) {
    $("#player").insertAdjacentHTML("beforeend", `
      <div class="pl-mini" id="plMini"><div class="pmi-cover" id="pmiCover"></div>
        <div class="pmi-txt"><b id="pmiTitle"></b><span id="pmMiniLine"></span></div>
        <div class="pmi-btns"><button data-m="prev" title="${plL("Önceki", "Previous")}">⏮</button><button data-m="toggle" class="pmi-play" title="${plL("Oynat / duraklat", "Play / pause")}">⏯</button><button data-m="next" title="${plL("Sonraki", "Next")}">⏭</button><button data-m="exit" title="${plL("Büyüt (Esc)", "Expand (Esc)")}">⤢</button></div>
        <i class="pmi-prog" id="pmiProg"></i></div>`);
    bar = $("#plMini");
    ["click", "dblclick"].forEach((ev) => bar.addEventListener(ev, (e) => e.stopPropagation()));
    bar.addEventListener("click", (e) => {
      const b = e.target.closest("button[data-m]"); if (!b) return;
      ({ prev: () => window.plQueueStep?.(-1), next: () => window.plQueueStep?.(1), toggle: () => plToggle(), exit: () => window.plMini(false) })[b.dataset.m]();
    });
    bar.addEventListener("dblclick", () => window.plMini(false));
    $("#plVideo").addEventListener("timeupdate", () => {
      if (!PL.mini) return;
      const p = $("#pmiProg"); if (p && PL.dur) p.style.width = Math.min(100, plNow() / PL.dur * 100).toFixed(2) + "%";
    });
  }
  const r = PL.info || {};
  $("#pmiTitle").textContent = (PM.meta && (PM.meta.artist ? PM.meta.artist + " — " : "") + PM.meta.title) || r.title || "";
  $("#pmiCover").style.backgroundImage = r.cover ? `url("${r.cover}")` : "";
  $("#pmiCover").hidden = !r.cover || r.kind !== "audio";
  if (!PM.lines.length) $("#pmMiniLine").textContent = "";
  $("#player").classList.toggle("mini", on);
  window.plPanelClose?.();
  if ($("#plDict")) $("#plDict").hidden = true;
  api.player_mini(on);
};
