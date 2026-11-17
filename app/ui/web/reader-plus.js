// Kami Reader+ (v1.30): okuma istatistigi, otomatik kaydirma / sayfa cevirme, e-kitap puntosu, seri ve yeni bolum takibi.
"use strict";
(() => {
  const RP = { auto: false, speed: +(localStorage.getItem("kr.autoSpeed") || 60), raf: 0, last: 0, acc: 0, seen: new Set(), active: Date.now() };
  const today = () => new Date().toISOString().slice(0, 10);
  const fmtDur = (s) => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h} ${L("sa", "h")} ${m} ${L("dk", "min")}` : `${m} ${L("dk", "min")}`; };

  const css = document.createElement("style");
  css.textContent = `
  #rpHud{position:fixed;left:50%;bottom:70px;transform:translateX(-50%);background:#110D19ee;border:1px solid var(--line);border-radius:999px;padding:6px 14px;font-size:13px;z-index:30;display:flex;gap:10px;align-items:center}
  #rpHud[hidden]{display:none}#rpHud b{color:var(--em)}
  .rp-panels{display:grid;grid-template-columns:minmax(260px,1fr) minmax(320px,1.4fr);gap:22px;margin:0 0 34px}
  .rp-card{background:var(--panel);border:1px solid var(--line);border-radius:12px;padding:16px 18px}
  .rp-card h4{margin:0 0 10px;font-size:12px;letter-spacing:3px;text-transform:uppercase;color:var(--mute)}
  .rp-nums{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}.rp-nums div{font-size:22px;font-weight:700}.rp-nums small{display:block;font-size:11px;color:var(--mute);font-weight:400}
  .rp-bars{display:flex;gap:4px;align-items:flex-end;height:46px;margin-top:12px}.rp-bars i{flex:1;background:var(--violet);border-radius:3px 3px 0 0;min-height:2px;opacity:.85}
  .rp-bars i.t{background:var(--em)}
  .rp-ser{display:grid;gap:8px;max-height:260px;overflow:auto}.rp-ser .s{display:grid;grid-template-columns:1fr auto;gap:2px 8px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:8px}
  .rp-ser .s small{color:var(--mute);font-size:11px}.rp-ser .s .nw{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}
  .rp-ser .s .nw button{font-size:12px;padding:3px 8px;border:1px solid var(--em);background:transparent;color:var(--em);border-radius:6px;cursor:pointer}
  .rp-ser .s .x{background:none;border:0;color:var(--mute);cursor:pointer}.rp-badge{background:var(--em);color:#000;border-radius:999px;padding:0 7px;font-size:11px;font-weight:700;margin-left:6px}
  .rp-add{display:flex;gap:6px;margin-top:10px}.rp-add input{flex:1;background:#0b0912;border:1px solid var(--line);color:var(--text);border-radius:8px;padding:7px 10px}
  .rp-add button{border:1px solid var(--line);background:var(--royal);color:#fff;border-radius:8px;padding:7px 12px;cursor:pointer}
  @media (max-width: 800px){.rp-panels{grid-template-columns:1fr}}`;
  document.head.appendChild(css);
  const hud = document.createElement("div"); hud.id = "rpHud"; hud.hidden = true; document.body.appendChild(hud);

  // ---------------------------------------------------------------- istatistik (etkin okuma suresi)
  ["mousemove", "keydown", "wheel", "pointerdown"].forEach((e) => document.addEventListener(e, () => { RP.active = Date.now(); }, { passive: true }));
  setInterval(() => {
    if (!RD.doc || document.hidden || !RD.st) return;
    if (Date.now() - RP.active > 120000 && !RP.auto && !(typeof TTS !== "undefined" && TTS.on)) return;   // 2 dk hareketsiz: sayma
    const s = (RD.st.stats ||= { secs: 0, pages: 0, days: {} });
    s.secs += 15; s.days[today()] = (s.days[today()] || 0) + 15;
    const keys = Object.keys(s.days).sort(); if (keys.length > 400) delete s.days[keys[0]];
    dirty();
  }, 15000);
  const _upd = updateUi;
  window.updateUi = updateUi = function () {   // her yeni sayfa bir kez sayilir (oturum basina)
    _upd.apply(this, arguments);
    if (RD.doc && RD.st && !RP.seen.has(RD.page)) { RP.seen.add(RD.page); (RD.st.stats ||= { secs: 0, pages: 0, days: {} }).pages++; }
  };

  // ---------------------------------------------------------------- otomatik kaydirma / cevirme
  function showHud() {
    hud.hidden = !RP.auto;
    if (RP.auto) hud.innerHTML = RD.set.mode === "scroll"
      ? `⏬ ${L("Otomatik kaydırma", "Auto-scroll")} <b>${RP.speed}</b> px/sn · [ ] ${L("hız", "speed")} · A ${L("dur", "stop")}`
      : `⏭ ${L("Otomatik sayfa", "Auto page")} <b>${Math.max(2, Math.round(1200 / RP.speed))}</b> ${L("sn", "s")} · [ ] ${L("hız", "speed")} · A ${L("dur", "stop")}`;
  }
  function tickAuto(t) {
    if (!RP.auto || !RD.doc) { RP.raf = 0; return; }
    const dt = RP.last ? (t - RP.last) / 1000 : 0; RP.last = t;
    if (RD.set.mode === "scroll") {
      RP.acc += RP.speed * dt;
      if (RP.acc >= 1) { const px = Math.floor(RP.acc); RP.acc -= px; $("#rdStage").scrollTop += px; }
      const st = $("#rdStage"); if (st.scrollTop + st.clientHeight >= st.scrollHeight - 2) toggleAuto(false);
    } else {
      RP.acc += dt;
      if (RP.acc >= Math.max(2, 1200 / RP.speed)) { RP.acc = 0; if (RD.page >= RD.doc.count - 1) toggleAuto(false); else step(1); }
    }
    RP.raf = requestAnimationFrame(tickAuto);
  }
  function toggleAuto(on = !RP.auto) {
    RP.auto = on; RP.last = 0; RP.acc = 0; showHud();
    if (on && !RP.raf) RP.raf = requestAnimationFrame(tickAuto);
  }
  ["mousedown", "wheel"].forEach((e) => document.getElementById("rdStage")?.addEventListener(e, () => { if (RP.auto && RD.set.mode !== "scroll") RP.acc = 0; }, { passive: true }));

  // ---------------------------------------------------------------- e-kitap puntosu
  async function epubFont(d) {
    if (!RD.doc?.ebook) return;
    const cur = +(RD.set.epub_font || 11), size = Math.max(7, Math.min(24, cur + d));
    if (size === cur) return;
    toast(L(`Yazı boyutu ${size} — sayfalar yeniden diziliyor…`, `Font ${size} — repaginating…`));
    saveNow();
    const r = await slowR("reader_epub_font", size);
    if (r?.ok) openDoc(RD.doc.path);
  }
  async function slowR(name, ...args) {   // reader.html'de app.js yok: is kuyrugu ile uzun cagri
    const j = await api.job_start(name, args);
    if (!j?.ok) return { ok: false, error: j?.error || "job_failed" };
    for (let w = 80; ; w = Math.min(w * 1.5, 500)) {
      await new Promise((r) => setTimeout(r, w));
      const r = await api.job_result(j.job);
      if (r?.state === "done") return r.result;
      if (r?.state === "lost") return { ok: false, error: "job_lost" };
    }
  }

  document.addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, select") || !RD.doc) return;
    const k = e.key;
    if (k === "a" || k === "A") toggleAuto();
    else if (k === "]") { RP.speed = Math.min(600, Math.round(RP.speed * 1.25)); localStorage.setItem("kr.autoSpeed", RP.speed); showHud(); }
    else if (k === "[") { RP.speed = Math.max(10, Math.round(RP.speed / 1.25)); localStorage.setItem("kr.autoSpeed", RP.speed); showHud(); }
    else if (k === "." && RD.doc.ebook) epubFont(1);
    else if (k === "," && RD.doc.ebook) epubFont(-1);
    else return;
    e.preventDefault();
  });

  const _open = openDoc;
  window.openDoc = openDoc = async function (path) {
    toggleAuto(false); RP.seen = new Set();
    await _open(path);
    if (RD.doc?.ebook) toast(L("E-kitap: , ve . ile yazı boyutu", "E-book: , and . change font size"));
  };
  const _close = closeDoc;
  window.closeDoc = closeDoc = function () { toggleAuto(false); _close(); };

  // ---------------------------------------------------------------- kitaplik: istatistik + seriler
  async function panels() {
    const homeEl = $("#rdHome"); if (!homeEl || homeEl.hidden) return;
    let box = $("#rpPanels");
    if (!box) { box = document.createElement("div"); box.id = "rpPanels"; box.className = "rp-panels"; homeEl.insertBefore(box, $("#rhShelf").previousElementSibling?.tagName === "H3" ? $("#rhShelf").previousElementSibling : $("#rhShelf")); }
    const [st, ser] = await Promise.all([api.reader_stats(), api.reader_series()]);
    const mx = Math.max(60, ...st.days.map((d) => d.s));
    const ns = ser.reduce((a, s) => a + (s.new?.length || 0), 0);
    box.innerHTML = `
      <div class="rp-card"><h4>${L("Okuma", "Reading")}</h4>
        <div class="rp-nums"><div>${fmtDur(st.today)}<small>${L("bugün", "today")}</small></div><div>${fmtDur(st.week)}<small>${L("bu hafta", "this week")}</small></div>
        <div>${st.streak}<small>${L("gün üst üste", "day streak")}</small></div><div>${st.pages}<small>${L("sayfa", "pages")}</small></div>
        <div>${st.finished}<small>${L("bitirilen", "finished")}</small></div><div>${fmtDur(st.total)}<small>${L("toplam", "total")}</small></div></div>
        <div class="rp-bars" title="${L("Son 14 gün", "Last 14 days")}">${st.days.map((d, i) => `<i class="${i === st.days.length - 1 ? "t" : ""}" style="height:${Math.round((d.s / mx) * 100)}%" title="${d.d}: ${fmtDur(d.s)}"></i>`).join("")}</div></div>
      <div class="rp-card"><h4>${L("Seriler", "Series")}${ns ? `<span class="rp-badge">${ns} ${L("yeni", "new")}</span>` : ""}</h4>
        <div class="rp-ser">${ser.map((s) => `<div class="s" data-id="${s.id}"><div><b>${esc(s.title)}</b> <small>${s.kind === "mangadex" ? "MangaDex" : L("klasör", "folder")}${s.last_n >= 0 ? ` · ${L("son", "last")} ${s.last_n}` : ""}${s.error ? ` · ⚠ ${esc(s.error)}` : ""}</small></div>
          <button class="x" data-rm="${s.id}" title="${L("Takibi bırak", "Unfollow")}">✕</button>
          ${s.new?.length ? `<div class="nw">${s.new.slice(-8).map((c, k) => `<button data-ch="${s.id}:${s.new.length - Math.min(8, s.new.length) + k}">${esc(c.name)}</button>`).join("")}<button data-seen="${s.id}">✓ ${L("gördüm", "seen")}</button></div>` : ""}</div>`).join("") ||
          `<small style="color:var(--mute)">${L("Bir manga klasörü ya da mangadex.org/title/… linki ekle; yeni bölüm gelince haber veririm.", "Add a manga folder or a mangadex.org/title/… link; I'll tell you when a new chapter arrives.")}</small>`}</div>
        <div class="rp-add"><input id="rpSrc" placeholder="${L("Klasör yolu ya da mangadex.org/title/… linki", "Folder path or mangadex.org/title/… link")}"><button id="rpPick">📁</button><button id="rpAdd">${L("Takip et", "Follow")}</button><button id="rpChk" title="${L("Şimdi yokla", "Check now")}">⟳</button></div></div>`;
    box.querySelector("#rpPick").onclick = async () => { const p = await api.reader_pick(true); if (p) box.querySelector("#rpSrc").value = p; };
    box.querySelector("#rpAdd").onclick = async () => {
      const v = box.querySelector("#rpSrc").value.trim(); if (!v) return;
      const r = await slowR("reader_series_add", v);
      toast(r?.ok ? L("Takipte: ", "Following: ") + r.series.title : L("Eklenemedi: ", "Failed: ") + (r?.error || "")); panels();
    };
    box.querySelector("#rpChk").onclick = async () => { const r = await slowR("reader_series_check"); toast(r?.found?.length ? L(`${r.found.length} seride yeni bölüm`, `New chapters in ${r.found.length}`) : L("Yeni bölüm yok", "No new chapters")); panels(); };
    box.onclick = async (e) => {
      const rm = e.target.closest("[data-rm]"), seen = e.target.closest("[data-seen]"), ch = e.target.closest("[data-ch]");
      if (rm) { if (confirm(L("Takip bırakılsın mı?", "Unfollow?"))) { await api.reader_series_remove(rm.dataset.rm); panels(); } }
      else if (seen) { await api.reader_series_seen(seen.dataset.seen); panels(); }
      else if (ch) {
        const [sid, k] = ch.dataset.ch.split(":"), s = ser.find((x) => x.id === sid), c = s?.new?.[+k];
        if (c?.path) openDoc(c.path); else if (c?.url) api.open_link(c.url);
      }
    };
  }
  const _home = home;
  window.home = home = async function () { await _home(); panels(); };
  if (!$("#rdHome")?.hidden) setTimeout(panels, 600);
})();
