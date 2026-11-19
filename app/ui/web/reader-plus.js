// Kami Reader+ (v1.30): okuma istatistigi, otomatik kaydirma / sayfa cevirme, e-kitap puntosu, seri ve yeni bolum takibi.
"use strict";
(() => {
  const RP = { auto: false, speed: +(localStorage.getItem("kr.autoSpeed") || 60), raf: 0, last: 0, acc: 0, seen: new Set(), active: Date.now() };
  const today = () => new Date().toISOString().slice(0, 10);
  const fmtDur = (s) => { s = Math.round(s || 0); const h = Math.floor(s / 3600), m = Math.round((s % 3600) / 60); return h ? `${h} ${L("sa", "h")} ${m} ${L("dk", "min")}` : `${m} ${L("dk", "min")}`; };

  const css = document.createElement("style");
  css.textContent = `
  #rpHud{position:fixed;left:50%;bottom:24px;transform:translateX(-50%);background:rgba(17,13,25,.94);border:1px solid rgba(157,107,255,.4);border-radius:999px;padding:6px 14px;font-size:12.5px;z-index:30;display:flex;gap:10px;align-items:center;box-shadow:0 10px 30px rgba(0,0,0,.5)}
  #rpHud[hidden]{display:none}#rpHud b{color:var(--em)}
  #rpHud button{background:rgba(157,107,255,.18);border:1px solid rgba(157,107,255,.35);color:#EDE9F6;border-radius:6px;padding:2px 8px;font:600 12px inherit;cursor:pointer}
  #rpHud button:hover{background:var(--violet);color:#fff}
  #rpHud .rp-spd{width:54px;height:5px;background:#241B33;border-radius:3px;overflow:hidden;display:inline-block}
  #rpHud .rp-spd i{display:block;height:100%;background:linear-gradient(90deg,#9D6BFF,#2EE6A6)}
  .rp-panels{display:grid;grid-template-columns:minmax(260px,1fr) minmax(320px,1.4fr);gap:22px;margin:0 0 34px}
  .rp-card{background:linear-gradient(180deg,rgba(28,21,42,.95),var(--panel));border:1px solid var(--line);border-radius:14px;padding:18px 20px;box-shadow:0 8px 28px rgba(0,0,0,.28)}
  .rp-card h4{margin:0 0 12px;font-size:12px;letter-spacing:3px;text-transform:uppercase;color:var(--mute);display:flex;align-items:center;gap:8px}
  .rp-hero{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:12px;padding-bottom:10px;border-bottom:1px solid rgba(255,255,255,.06)}
  .rp-hero strong{font-size:28px;font-weight:700;color:#EDE9F6}.rp-hero small{display:block;font-size:11px;color:var(--mute)}
  .rp-streak{display:inline-flex;align-items:center;gap:6px;padding:4px 10px;border-radius:999px;background:rgba(46,230,166,.12);border:1px solid rgba(46,230,166,.35);color:var(--em);font-size:12px;font-weight:600}
  .rp-ico{width:14px;height:14px;flex:none;display:block}
  .rp-nums{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}.rp-nums div{font-size:16px;font-weight:700}.rp-nums small{display:block;font-size:10.5px;color:var(--mute);font-weight:400}
  .rp-bars{display:flex;gap:4px;align-items:flex-end;height:48px;margin-top:14px}.rp-bars i{flex:1;background:var(--violet);border-radius:3px 3px 0 0;min-height:3px;opacity:.82;transition:opacity .15s}
  .rp-bars i:hover{opacity:1}.rp-bars i.t{background:var(--em);box-shadow:0 0 8px rgba(46,230,166,.4)}
  .rp-ser{display:grid;gap:8px;max-height:260px;overflow:auto}.rp-ser .s{display:grid;grid-template-columns:1fr auto;gap:2px 8px;align-items:center;padding:8px 10px;border:1px solid var(--line);border-radius:8px}
  .rp-ser .s small{color:var(--mute);font-size:11px}.rp-ser .s .nw{grid-column:1/-1;display:flex;flex-wrap:wrap;gap:6px}
  .rp-ser .s .nw button{font-size:12px;padding:3px 8px;border:1px solid var(--em);background:transparent;color:var(--em);border-radius:6px;cursor:pointer}
  .rp-ser .s .x{background:none;border:0;color:var(--mute);cursor:pointer}.rp-badge{background:var(--em);color:#000;border-radius:999px;padding:0 7px;font-size:11px;font-weight:700;margin-left:6px}
  .rp-add{display:flex;gap:8px;margin-top:12px;align-items:center}.rp-add input{flex:1;min-width:0;background:#0b0912;border:1px solid var(--line);color:var(--text);border-radius:9px;padding:8px 12px;font:inherit;outline:none;transition:border-color .15s}.rp-add input:focus{border-color:var(--violet)}
  .rp-add button{display:inline-flex;align-items:center;justify-content:center;gap:6px;border:1px solid var(--line);background:#1b132b;color:#EDE9F6;border-radius:9px;padding:8px 12px;font:600 12.5px inherit;cursor:pointer;transition:all .15s;white-space:nowrap}
  .rp-add button:hover{border-color:var(--violet);background:#251a3a}
  .rp-add #rpAdd{background:linear-gradient(135deg,#7C3AED,#5B21B6);border-color:rgba(167,139,250,.45);color:#fff}
  .rp-add #rpAdd:hover{filter:brightness(1.1)}
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
    const isEbook = Boolean(RD.doc?.ebook);
    hud.hidden = !RP.auto && !isEbook;
    if (hud.hidden) return;
    const pct = Math.min(100, Math.round((RP.speed / 300) * 100));
    const autoPart = RP.auto ? (RD.set.mode === "scroll"
      ? `⏬ <b>${RP.speed}</b> px/s <span class="rp-spd"><i style="width:${pct}%"></i></span> <button type="button" data-rph="stop">A</button>`
      : `⏭ <b>${Math.max(2, Math.round(1200 / RP.speed))}</b>s <span class="rp-spd"><i style="width:${pct}%"></i></span> <button type="button" data-rph="stop">A</button>`) : "";
    const ebPart = isEbook ? `<button type="button" data-rph="fm" title="${L("Yazıyı küçült (,)", "Smaller text (,)")}">A−</button><button type="button" data-rph="fp" title="${L("Yazıyı büyüt (.)", "Larger text (.)")}">A+</button>` : "";
    hud.innerHTML = [autoPart, ebPart].filter(Boolean).join("<span>·</span>");
  }
  hud.addEventListener("click", (e) => {
    const b = e.target.closest("[data-rph]"); if (!b) return;
    if (b.dataset.rph === "stop") toggleAuto(false);
    else if (b.dataset.rph === "fm") epubFont(-1);
    else if (b.dataset.rph === "fp") epubFont(1);
  });
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
    showHud();
    if (RD.doc?.ebook) toast(L("E-kitap: , ve . ile yazı boyutu", "E-book: , and . change font size"));
  };
  const _close = closeDoc;
  window.closeDoc = closeDoc = function () { toggleAuto(false); _close(); };

  // ---------------------------------------------------------------- kitaplik: istatistik + seriler
  async function panels() {
    if (!api) return;
    const homeEl = $("#rdHome"); if (!homeEl || homeEl.hidden) return;
    let box = $("#rpPanels");
    if (!box) { box = document.createElement("div"); box.id = "rpPanels"; box.className = "rp-panels"; homeEl.insertBefore(box, $("#rhShelf").previousElementSibling?.tagName === "H3" ? $("#rhShelf").previousElementSibling : $("#rhShelf")); }
    const [st, ser] = await Promise.all([api.reader_stats(), api.reader_series()]);
    const mx = Math.max(60, ...st.days.map((d) => d.s));
    const ns = ser.reduce((a, s) => a + (s.new?.length || 0), 0);
    box.innerHTML = `
      <div class="rp-card"><h4>${L("Okuma", "Reading")}</h4>
        <div class="rp-hero"><div><strong>${fmtDur(st.today)}</strong><small>${L("bugün okunan", "read today")}</small></div><span class="rp-streak"><svg class="rp-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 2c.5 3.5-2 5.5-2 8.5a4 4 0 0 0 8 0c0-3-2-5-2-7.5 2.5 1.5 4 4.5 4 8a8 8 0 1 1-16 0c0-3.5 2-6.5 5-8 .5 1.5 1.5 2.5 3 2.5z"/></svg>${st.streak} ${L("gün seri", "day streak")}</span></div>
        <div class="rp-nums"><div>${fmtDur(st.week)}<small>${L("bu hafta", "this week")}</small></div>
        <div>${st.pages}<small>${L("sayfa", "pages")}</small></div>
        <div>${st.finished}<small>${L("bitirilen", "finished")}</small></div><div>${fmtDur(st.total)}<small>${L("toplam", "total")}</small></div></div>
        <div class="rp-bars" title="${L("Son 14 gün", "Last 14 days")}">${st.days.map((d, i) => `<i class="${i === st.days.length - 1 ? "t" : ""}" style="height:${Math.round((d.s / mx) * 100)}%" title="${d.d}: ${fmtDur(d.s)}"></i>`).join("")}</div></div>
      <div class="rp-card"><h4>${L("Seriler", "Series")}${ns ? `<span class="rp-badge">${ns} ${L("yeni", "new")}</span>` : ""}</h4>
        <div class="rp-ser">${ser.map((s) => `<div class="s" data-id="${s.id}"><div><b>${esc(s.title)}</b> <small>${s.kind === "mangadex" ? "MangaDex" : L("klasör", "folder")}${s.last_n >= 0 ? ` · ${L("son", "last")} ${s.last_n}` : ""}${s.error ? ` · ! ${esc(s.error)}` : ""}</small></div>
          <button class="x" data-rm="${s.id}" title="${L("Takibi bırak", "Unfollow")}">✕</button>
          ${s.new?.length ? `<div class="nw">${s.new.slice(-8).map((c, k) => `<button data-ch="${s.id}:${s.new.length - Math.min(8, s.new.length) + k}">${esc(c.name)}</button>`).join("")}<button data-seen="${s.id}">✓ ${L("gördüm", "seen")}</button></div>` : ""}</div>`).join("") ||
          `<small style="color:var(--mute)">${L("Bir manga klasörü ya da mangadex.org/title/… linki ekle; yeni bölüm gelince haber veririm.", "Add a manga folder or a mangadex.org/title/… link; I'll tell you when a new chapter arrives.")}</small>`}</div>
        <div class="rp-add"><input id="rpSrc" placeholder="${L("Klasör yolu ya da mangadex.org/title/… linki", "Folder path or mangadex.org/title/… link")}"><button id="rpPick" title="${L("Klasör seç", "Choose folder")}"><svg class="rp-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/></svg></button><button id="rpAdd">${L("Takip et", "Follow")}</button><button id="rpChk" title="${L("Şimdi yokla", "Check now")}"><svg class="rp-ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-2.64-6.36"/><polyline points="21 3 21 9 15 9"/></svg></button></div></div>`;
    box.querySelector("#rpPick").onclick = async () => { const p = await api.reader_pick(true); if (p) box.querySelector("#rpSrc").value = p; };
    box.querySelector("#rpAdd").onclick = async () => {
      const v = box.querySelector("#rpSrc").value.trim(); if (!v) return;
      const r = await slowR("reader_series_add", v);
      toast(r?.ok ? L("Takipte: ", "Following: ") + r.series.title : L("Eklenemedi: ", "Failed: ") + (r?.error || "")); panels();
    };
    box.querySelector("#rpChk").onclick = async () => { const r = await slowR("reader_series_check"); toast(r?.found?.length ? L(`${r.found.length} seride yeni bölüm`, `New chapters in ${r.found.length}`) : L("Yeni bölüm yok", "No new chapters")); panels(); };
    let resBox = $("#rpResurface");
    if (!resBox) { resBox = document.createElement("div"); resBox.id = "rpResurface"; box.after(resBox); }
    if (st.sample_hl?.text) {
      resBox.className = "rp-hl-resurface";
      const hlTitle = st.sample_hl.title || st.sample_hl.book || L("Belge", "Document");
      resBox.innerHTML = `<div><small style="color:var(--em);letter-spacing:2px;text-transform:uppercase;font-size:10.5px">${L("Günün Vurgusu · ", "Daily Highlight · ")}${esc(hlTitle)} (S.${(st.sample_hl.page || 0) + 1})</small><blockquote>“${esc(st.sample_hl.text)}”</blockquote></div><button type="button" class="btn" id="rpGoHl" style="background:#2A1650;border:1px solid rgba(157,107,255,.45);color:#EDE9F6;padding:8px 14px;clip-path:polygon(8px 0,100% 0,100% calc(100% - 8px),calc(100% - 8px) 100%,0 100%,0 8px);white-space:nowrap;flex:none">${L("Belgeye Git", "Jump to Doc")}</button>`;
      resBox.querySelector("#rpGoHl").onclick = async () => { await openDoc(st.sample_hl.path); go(st.sample_hl.page); };
    } else {
      resBox.className = "";
      resBox.innerHTML = "";
    }
    box.onclick = async (e) => {
      const rm = e.target.closest("[data-rm]"), seen = e.target.closest("[data-seen]"), ch = e.target.closest("[data-ch]");
      if (rm) {
        if (rm.dataset.arm !== "1") {
          rm.dataset.arm = "1"; rm.textContent = L("Emin?", "Sure?");
          setTimeout(() => { if (rm.isConnected && rm.dataset.arm === "1") { rm.dataset.arm = ""; rm.textContent = "✕"; } }, 2400);
          return;
        }
        await api.reader_series_remove(rm.dataset.rm); panels();
      }
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

  // ---- Kami 2.0 D13: LiquidText Alinti & Diyagram Panosu + Recall (Bulanik Hatirlama) Sinav Modu + Panel-to-Panel ----
  const d13Style = document.createElement("style");
  d13Style.textContent = `
    body.rd-recall-on .rd-hl, body.rd-recall-on mark {
      filter: blur(5.5px) !important;
      transition: filter .18s ease !important;
      cursor: help !important;
    }
    body.rd-recall-on .rd-hl:hover, body.rd-recall-on mark:hover, body.rd-recall-on .rd-hl.revealed {
      filter: none !important;
    }
    #rdBoardModal { position:fixed; inset:0; z-index:88; background:rgba(6,4,12,.86); backdrop-filter:blur(8px); display:grid; place-items:center; padding:18px; }
    #rdBoardModal[hidden] { display:none !important; }
    .rdb-box { width:min(920px,95vw); height:min(640px,88vh); background:#110D1C; border:1px solid #FBBF24; border-radius:14px; display:flex; flex-direction:column; overflow:hidden; color:#EDE9F6; }
    .rdb-hd { display:flex; align-items:center; justify-content:space-between; padding:12px 16px; border-bottom:1px solid rgba(255,255,255,.1); background:#161124; }
    .rdb-canvas { flex:1; position:relative; overflow:auto; background:radial-gradient(rgba(157,107,255,.18) 1px, transparent 1px); background-size:20px 20px; padding:18px; }
    .rdb-card { position:absolute; width:235px; background:#1B142C; border:1px solid #9D6BFF; border-radius:10px; padding:10px 12px; cursor:move; box-shadow:0 10px 26px rgba(0,0,0,.55); font-size:12px; line-height:1.45; }
    .rdb-card small { color:#2EE6A6; display:block; margin-bottom:4px; font-weight:700; }
    .rdb-card.blur-q p { filter:blur(5px); transition:filter .18s; }
    .rdb-card.blur-q:hover p { filter:none; }
    .rd-tools-wrap { position:relative; display:inline-flex; }
    #rdToolsMenu {
      position:fixed; right:52px; top:48px; z-index:95;
      width:265px; background:#140F20; border:1px solid rgba(157,107,255,.45);
      border-radius:12px; padding:8px; box-shadow:0 16px 42px rgba(0,0,0,.72);
      display:flex; flex-direction:column; gap:5px;
    }
    #rdToolsMenu[hidden] { display:none !important; }
    #rdToolsMenu button, #rdToolsMenu select {
      width:100% !important; text-align:left !important; justify-content:flex-start !important;
      display:flex !important; align-items:center !important; gap:8px !important;
      padding:7px 10px !important; border-radius:8px !important;
      background:#1B142C !important; border:1px solid rgba(255,255,255,.07) !important;
      color:#EDE9F6 !important; font:600 12px "Chakra Petch",system-ui,sans-serif !important;
    }
    #rdToolsMenu button:hover, #rdToolsMenu button.on { border-color:#2EE6A6 !important; color:#2EE6A6 !important; }
  `;
  document.head.appendChild(d13Style);

  function mountReader20Buttons() {
    const top = document.querySelector(".rd-top");
    if (!top || document.getElementById("rdToolsWrap")) return;
    const drawerBtn = top.querySelector('[data-a="drawer"]');

    const wrap = document.createElement("div");
    wrap.id = "rdToolsWrap";
    wrap.className = "rd-tools-wrap";
    const tBtn = document.createElement("button");
    tBtn.type = "button";
    tBtn.id = "rdToolsBtn";
    tBtn.title = "Görünüm, OCR, Sesli Okuma, Pano ve Sınav Araçları";
    tBtn.textContent = "Araçlar ▾";
    const menu = document.createElement("div");
    menu.id = "rdToolsMenu";
    menu.className = "km-pop-origin";
    menu.style.setProperty("--km-ox", "right");
    menu.style.setProperty("--km-oy", "top");
    menu.hidden = true;
    wrap.append(tBtn, menu);
    top.insertBefore(wrap, drawerBtn || null);

    tBtn.onclick = (e) => {
      e.stopPropagation();
      menu.hidden = !menu.hidden;
      tBtn.classList.toggle("on", !menu.hidden);
    };
    document.addEventListener("click", (e) => {
      if (!e.target.closest?.("#rdToolsWrap")) {
        menu.hidden = true;
        tBtn.classList.remove("on");
      }
    });

    const btnRecall = document.createElement("button");
    btnRecall.id = "rdRecallBtn";
    btnRecall.textContent = "🧠 Sınav Modu (Vurguları Bulanıklaştır)";
    const btnBoard = document.createElement("button");
    btnBoard.id = "rdBoardBtn";
    btnBoard.textContent = "📌 Alıntı & Diyagram Panosu";
    const btnPanel = document.createElement("button");
    btnPanel.id = "rdPanelZoomBtn";
    btnPanel.textContent = "▣ Manga Kare Yakınlaştır";

    // Ust bardaki ikincil butonlari Araclar ▾ menusu icine tasi (ust bar ferah kalsin)
    const moveSelectors = [
      ["#rdAnimMode", null],
      ["#rdNight", "🌙 Gece / Ters Renk Modu"],
      ["#rdFltBtn", "◐ Tarama Filtreleri (Kontrast/Gama)"],
      ["#rdPeekBtn", "⊞ Görsel & Tablo Özeti"],
      ["#rdTtsBtn", "🔊 Sesli Oku (TTS)"],
      ["#rdOcrBtn", "🔍 Sayfayı OCR Çevir"],
      ['[data-a="exportmd"]', "📝 Vurguları Markdown (.md) İndir"],
      ['[data-a="ocrpdf"]', "📄 Taranmış PDF'i Aranabilir Yap"],
    ];
    for (const [sel, lbl] of moveSelectors) {
      const el = top.querySelector(sel);
      if (el) {
        if (lbl) el.textContent = lbl;
        menu.appendChild(el);
      }
    }
    menu.append(btnPanel, btnBoard, btnRecall);

    let recallOn = false;
    btnRecall.onclick = () => {
      recallOn = !recallOn;
      document.body.classList.toggle("rd-recall-on", recallOn);
      btnRecall.classList.toggle("on", recallOn);
      toast(recallOn ? "🧠 Sınav (Recall) Modu Açık: Vurgular bulanıklaştırıldı (üstüne gelince görünür)" : "Sınav Modu Kapatıldı");
    };

    let panelStep = 0;
    const QUADS = [
      "scale(1)",
      "scale(1.65) translate(18%, 18%)",
      "scale(1.65) translate(-18%, 18%)",
      "scale(1.65) translate(18%, -18%)",
      "scale(1.65) translate(-18%, -18%)",
    ];
    btnPanel.onclick = () => {
      panelStep = (panelStep + 1) % QUADS.length;
      const sp = document.getElementById("rdSpread");
      if (sp) {
        sp.style.transition = "transform .26s cubic-bezier(.22,1,.36,1)";
        sp.style.transform = QUADS[panelStep];
      }
      btnPanel.classList.toggle("on", panelStep > 0);
    };

    btnBoard.onclick = () => openLiquidBoard();
  }

  function openLiquidBoard() {
    let mdl = document.getElementById("rdBoardModal");
    if (!mdl) {
      mdl = document.createElement("div");
      mdl.id = "rdBoardModal";
      document.body.appendChild(mdl);
    }
    mdl.hidden = false;
    const hls = (window.RD?.st?.hl || []).slice(0, 30);
    mdl.innerHTML = `
      <div class="rdb-box">
        <div class="rdb-hd">
          <b>📌 LiquidText / MarginNote Alıntı &amp; Diyagram Panosu (${hls.length} Kart)</b>
          <div style="display:flex;gap:8px">
            <button class="btn" id="rdbQuizToggle">🧠 Kartları Bulanıklaştır (Active Recall)</button>
            <button class="btn" id="rdbAddNote">+ Serbest Not Kartı</button>
            <button class="btn" id="rdbClose">Kapat (Esc)</button>
          </div>
        </div>
        <div class="rdb-canvas" id="rdbCanvas"></div>
      </div>
    `;
    const cvs = mdl.querySelector("#rdbCanvas");
    const items = hls.length
      ? hls.map((h, i) => ({ page: (h.page || 0) + 1, text: h.text || h.note || "Alıntı", x: 24 + (i % 3) * 265, y: 24 + Math.floor(i / 3) * 145 }))
      : [{ page: (window.RD?.page || 0) + 1, text: "Belgedeki vurguların ve çalışma notların burada sürüklenebilir kartlar olarak toplanır.", x: 40, y: 40 }];

    let blurCards = false;
    function renderCards() {
      cvs.innerHTML = items.map((it, idx) => `
        <div class="rdb-card${blurCards ? " blur-q" : ""}" data-cidx="${idx}" style="left:${it.x}px;top:${it.y}px">
          <small data-jump="${it.page - 1}" style="cursor:pointer">Sayfa ${it.page} ↗</small>
          <p style="margin:0">${esc(it.text)}</p>
        </div>
      `).join("");
      cvs.querySelectorAll("[data-jump]").forEach((el) => {
        el.onclick = (e) => {
          e.stopPropagation();
          mdl.hidden = true;
          if (typeof go === "function") go(+el.dataset.jump);
        };
      });
      cvs.querySelectorAll(".rdb-card").forEach((card) => {
        card.onpointerdown = (e) => {
          if (e.target.dataset?.jump != null) return;
          const idx = +card.dataset.cidx;
          const sx = e.clientX - items[idx].x, sy = e.clientY - items[idx].y;
          card.setPointerCapture?.(e.pointerId);
          card.onpointermove = (ev) => {
            items[idx].x = Math.max(8, ev.clientX - sx);
            items[idx].y = Math.max(8, ev.clientY - sy);
            card.style.left = items[idx].x + "px";
            card.style.top = items[idx].y + "px";
          };
          card.onpointerup = () => { card.onpointermove = null; };
        };
      });
    }
    renderCards();
    mdl.querySelector("#rdbQuizToggle").onclick = () => { blurCards = !blurCards; renderCards(); };
    mdl.querySelector("#rdbAddNote").onclick = () => {
      const t = prompt("Yeni kavram / vaka notu:");
      if (t) { items.push({ page: (window.RD?.page || 0) + 1, text: t, x: 60 + items.length * 20, y: 60 + items.length * 15 }); renderCards(); }
    };
    mdl.querySelector("#rdbClose").onclick = () => { mdl.hidden = true; };
  }

  setTimeout(mountReader20Buttons, 350);
  document.addEventListener("DOMContentLoaded", mountReader20Buttons);
})();
