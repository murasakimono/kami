// Kami Studio v1.38.0 — 2-Tier Smart Menu, #tlOverview Dual Timeline, Fixed Playhead, Cursor Zoom, Middle-Click Pan & Hex Label Sync
"use strict";
(() => {
  const $id = (s) => document.getElementById(s);
  const callApi = () => window.pywebview?.api;

  // ---- 1. Akilli Araclar Dropdown (position:fixed ile #tl overflow:hidden tarafindan kesilmez) ----
  const smBtn = $id("smartMenuBtn");
  const smMenu = $id("smartMenu");
  if (smBtn && smMenu) {
    smBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      const willOpen = smMenu.hidden;
      smMenu.hidden = !willOpen;
      smBtn.classList.toggle("on", willOpen);
      if (willOpen) {
        const r = smBtn.getBoundingClientRect();
        smMenu.classList.add("km-pop-origin");
        smMenu.style.setProperty("--km-ox", "left");
        smMenu.style.left = Math.max(8, Math.min(window.innerWidth - 260, r.left)) + "px";
        if (r.top > 360) {
          smMenu.style.setProperty("--km-oy", "bottom");
          smMenu.style.bottom = (window.innerHeight - r.top + 6) + "px";
          smMenu.style.top = "auto";
        } else {
          smMenu.style.setProperty("--km-oy", "top");
          smMenu.style.top = (r.bottom + 6) + "px";
          smMenu.style.bottom = "auto";
        }
      }
    });
    document.addEventListener("click", (e) => {
      if (!e.target.closest?.("#smartMenuWrap")) {
        smMenu.hidden = true;
        smBtn.classList.remove("on");
      }
    });
    smMenu.addEventListener("click", async (e) => {
      const btn = e.target.closest("button");
      if (!btn) return;
      smMenu.hidden = true;
      smBtn.classList.remove("on");
      const act = btn.dataset.smart;
      if (!act || !window.ST?.p) return;
      if (act === "chapters") {
        const markers = (ST.p.markers || []).map((m, i) => ({ t: m.t, title: m.note || m.label || `Bölüm ${i + 1}` }));
        if (!markers.length) { window.toast?.("Önce zaman çizelgesinde M ile işaretler ekle"); return; }
        const r = await callApi()?.studio_export_chapters_meta?.(markers, window.projEnd?.() || 0, ST.p.name || "proje");
        window.toast?.(r?.ok ? "Bölüm dosyası oluşturuldu: " + r.path.split(/[\\/]/).pop() : "Oluşturulamadı");
      } else if (act === "proxy") {
        const c = window.selClips?.()?.[0] || ST.p.clips.find((x) => ST.p.assets?.[x.asset]?.kind === "video");
        const asset = c ? ST.p.assets?.[c.asset] : Object.values(ST.p.assets || {}).find((a) => a.kind === "video");
        if (!asset?.path) { window.toast?.("Proje içinde video bulunamadı"); return; }
        window.busy?.("720p Önizleme Proxy hazırlanıyor…");
        const r = await (window.job ? window.job("studio_build_preview", asset.path) : callApi()?.studio_build_preview?.(asset.path));
        window.busy?.(null);
        window.toast?.(r?.ok ? (r.cached ? "Önizleme proxy hazır (önbellek)" : "720p Önizleme Proxy oluşturuldu ✓") : (r?.error || "Proxy başarısız"));
      } else if (act === "silences") {
        const c = window.selClips?.()?.[0] || ST.p.clips.find((x) => ST.p.assets?.[x.asset]?.kind === "video" || ST.p.assets?.[x.asset]?.kind === "audio");
        const asset = c ? ST.p.assets?.[c.asset] : null;
        if (!asset?.path || !c) { window.toast?.("Lütfen önce bir video veya ses klibi seç"); return; }
        window.busy?.("Sessiz aralıklar taranıyor…");
        const gaps = await callApi()?.studio_detect_silences?.(asset.path, -35, 0.45).catch(() => []);
        window.busy?.(null);
        if (!gaps?.length) { window.toast?.("Sessiz boşluk bulunamadı"); return; }
        window.snap?.();
        ST.p.markers ||= [];
        for (const [s, en] of gaps) {
          const tlT = c.start + Math.max(0, s - (c.in || 0));
          if (tlT >= c.start && tlT <= c.start + c.dur) ST.p.markers.push({ t: tlT, note: `Sessizlik (${(en - s).toFixed(1)}s)` });
        }
        window.changed?.(false);
        window.toast?.(`${gaps.length} sessiz aralık işaretlendi ✓`);
      }
    });
  }

  // ---- 2. #tlOverview Dual Timeline Canvas ----
  const ov = $id("tlOverview");
  const scroller = $id("tlScroll");
  const KIND_COL = { video: "#6D4AFF", image: "#3B82F6", audio: "#10B981", text: "#EC4899", fx: "#F59E0B" };
  function drawOverview() {
    if (!ov || !window.ST?.p) return;
    const w = ov.clientWidth || 800;
    if (ov.width !== w) ov.width = w;
    const h = ov.height || 22;
    const g = ov.getContext("2d");
    g.clearRect(0, 0, w, h);
    const total = Math.max(5, window.projEnd ? window.projEnd() : 10);
    const trkMap = new Map((ST.p.tracks || []).map((t, i) => [t.id, { i, kind: t.kind }]));
    const rows = Math.max(1, (ST.p.tracks || []).length);
    const rh = Math.max(2, (h - 4) / rows);
    for (const c of ST.p.clips || []) {
      const ti = trkMap.get(c.track);
      const y = 2 + (ti ? ti.i : 0) * rh;
      const x = (c.start / total) * w;
      const cw = Math.max(2, (c.dur / total) * w);
      g.fillStyle = KIND_COL[ti?.kind] || "#7C3AED";
      g.globalAlpha = ST.sel?.has?.(c.id) ? 1 : 0.72;
      g.fillRect(x, y, cw, Math.max(2, rh - 1));
    }
    g.globalAlpha = 1;
    if (scroller && ST.px) {
      const vx = ((scroller.scrollLeft / ST.px) / total) * w;
      const vw = Math.max(12, ((scroller.clientWidth / ST.px) / total) * w);
      g.strokeStyle = "rgba(46,230,166,.85)";
      g.fillStyle = "rgba(46,230,166,.12)";
      g.lineWidth = 1.2;
      g.fillRect(vx, 0.5, vw, h - 1);
      g.strokeRect(vx, 0.5, vw, h - 1);
    }
    const px = ((ST.t || 0) / total) * w;
    g.fillStyle = "#fff";
    g.fillRect(px - 0.5, 0, 1.5, h);
  }
  if (ov) {
    let ovDrag = false;
    const scrubOv = (clientX) => {
      if (!window.ST?.p || !scroller) return;
      const r = ov.getBoundingClientRect();
      const ratio = Math.max(0, Math.min(1, (clientX - r.left) / Math.max(1, r.width)));
      const total = Math.max(5, window.projEnd ? window.projEnd() : 10);
      const targetT = ratio * total;
      scroller.scrollLeft = Math.max(0, targetT * ST.px - scroller.clientWidth * 0.4);
      window.seek?.(targetT);
      drawOverview();
    };
    ov.addEventListener("pointerdown", (e) => { ovDrag = true; ov.setPointerCapture?.(e.pointerId); scrubOv(e.clientX); });
    window.addEventListener("pointermove", (e) => { if (ovDrag) scrubOv(e.clientX); });
    window.addEventListener("pointerup", () => { ovDrag = false; });
    scroller?.addEventListener("scroll", drawOverview, { passive: true });
    let _lastOvSig = "";
    setInterval(() => {
      if (document.hidden || !document.hasFocus()) return;
      const sig = `${window.ST?.t?.toFixed?.(2) || 0}|${window.ST?.p?.clips?.length || 0}|${window.ST?.px || 0}|${scroller?.scrollLeft || 0}`;
      if (sig === _lastOvSig) return;
      _lastOvSig = sig;
      drawOverview();
    }, 300);
  }

  // ---- 3. Sabit Kafa & Cursor Zoom & Middle-Click Pan ----
  let lockHead = false;
  let zoomCursor = true;
  const lockBtn = $id("stLockHeadBtn");
  const zoomBtn = $id("stZoomModeBtn");
  lockBtn?.addEventListener("click", () => {
    lockHead = !lockHead;
    lockBtn.classList.toggle("on", lockHead);
  });
  zoomBtn?.addEventListener("click", () => {
    zoomCursor = !zoomCursor;
    zoomBtn.textContent = zoomCursor ? "Zoom: İmleç" : "Zoom: Kafa";
    zoomBtn.classList.toggle("on", !zoomCursor);
  });

  if (scroller) {
    // Sabit kafa oynatim sirasinda kafayi ortada tutar
    setInterval(() => {
      if (!lockHead || !window.ST || !document.body.classList.contains("playing")) return;
      const x = ST.t * ST.px;
      scroller.scrollLeft = Math.max(0, x - scroller.clientWidth * 0.5);
    }, 60);

    // Ctrl + Tekerlek -> imlec/kafa odakli hassas zoom
    scroller.addEventListener("wheel", (e) => {
      if (!e.ctrlKey || !window.ST || typeof setZoom !== "function") return;
      e.preventDefault();
      e.stopPropagation();
      const r = scroller.getBoundingClientRect();
      const offsetX = zoomCursor ? (e.clientX - r.left) : Math.max(0, Math.min(r.width, ST.t * ST.px - scroller.scrollLeft));
      const tPivot = (scroller.scrollLeft + offsetX) / Math.max(1, ST.px);
      const factor = e.deltaY < 0 ? 1.25 : 1 / 1.25;
      setZoom(ST.px * factor);
      scroller.scrollLeft = Math.max(0, tPivot * ST.px - offsetX);
      drawOverview();
    }, { capture: true, passive: false });

    // Orta tus basili tutarak yatay/dikey kaydirma (Middle-click pan)
    let panState = null;
    scroller.addEventListener("pointerdown", (e) => {
      if (e.button !== 1) return;
      e.preventDefault();
      panState = { x: e.clientX, y: e.clientY, sl: scroller.scrollLeft, st: scroller.scrollTop };
      scroller.style.cursor = "grabbing";
    });
    window.addEventListener("pointermove", (e) => {
      if (!panState) return;
      scroller.scrollLeft = panState.sl - (e.clientX - panState.x);
      scroller.scrollTop = panState.st - (e.clientY - panState.y);
    });
    window.addEventListener("pointerup", () => {
      if (panState) { panState = null; scroller.style.cursor = ""; }
    });
  }

  // ---- 4. Live Hex Label Update on Color Swatch Input ----
  document.addEventListener("input", (e) => {
    if (e.target.matches?.('#insp input[type="color"]')) {
      const lbl = e.target.parentElement?.querySelector(".st-hex-lbl");
      if (lbl) lbl.textContent = String(e.target.value || "").toUpperCase();
    }
  });

  // ---- 5. Kami 2.0 B7: Sosyal Medya Guvenli Alan Maskesi (Ayar Olarak Acilip Kapatilabilir) ----
  const safeStyle = document.createElement("style");
  safeStyle.textContent = `
    #stSafeMask { position:absolute; inset:0; pointer-events:none; z-index:18; display:none; font:600 10px "Chakra Petch",sans-serif; color:rgba(255,255,255,.78); }
    #stSafeMask.on { display:block; }
    #stSafeMask .sf-top { position:absolute; top:0; left:0; right:0; height:12%; background:rgba(244,114,182,.14); border-bottom:1px dashed rgba(244,114,182,.65); display:flex; align-items:center; justify-content:center; }
    #stSafeMask .sf-right { position:absolute; top:28%; right:0; width:17%; bottom:20%; background:rgba(56,189,248,.14); border-left:1px dashed rgba(56,189,248,.65); display:flex; align-items:center; justify-content:center; writing-mode:vertical-rl; }
    #stSafeMask .sf-bot { position:absolute; left:0; right:0; bottom:0; height:20%; background:rgba(251,191,36,.14); border-top:1px dashed rgba(251,191,36,.65); display:flex; align-items:center; justify-content:center; }
    .st-desc-ov { position:fixed; inset:0; z-index:92; background:rgba(5,4,10,.84); backdrop-filter:blur(8px); display:grid; place-items:center; padding:20px; }
    .st-desc-box { width:min(740px,94vw); max-height:86vh; background:#120E1D; border:1px solid #38BDF8; border-radius:14px; padding:16px 18px; display:flex; flex-direction:column; gap:10px; color:#EDE9F6; }
    .st-desc-words { flex:1; overflow-y:auto; max-height:48vh; background:#0A0810; border:1px solid rgba(157,107,255,.25); border-radius:10px; padding:12px; display:flex; flex-wrap:wrap; gap:5px; line-height:1.8; }
    .st-dw { padding:2px 7px; border-radius:6px; background:#1A142B; border:1px solid rgba(157,107,255,.28); cursor:pointer; font-size:13px; user-select:none; transition:all .12s; }
    .st-dw:hover { border-color:#38BDF8; }
    .st-dw.cut { background:rgba(251,113,133,.18); border-color:#FB7185; color:#FB7185; text-decoration:line-through; opacity:.65; }
  `;
  document.head.appendChild(safeStyle);

  const viewWrap = $id("viewWrap");
  let safeMask = null;
  if (viewWrap) {
    safeMask = document.createElement("div");
    safeMask.id = "stSafeMask";
    safeMask.innerHTML = `
      <div class="sf-top">ÜST BAR GÜVENLİ ALAN Dışı (TikTok / Reels Arama &amp; Saat)</div>
      <div class="sf-right">SAĞ İKONLAR (Beğeni / Yorum / Paylaş)</div>
      <div class="sf-bot">ALT AÇIKLAMA &amp; MÜZİK ŞERİDİ (Altyazıyı Buraya Koyma)</div>
    `;
    viewWrap.appendChild(safeMask);
  }
  const safeBtn = document.querySelector('[data-a="safe"]');
  let safeZoneOn = false;
  function applySafeZone(on, persist = true) {
    safeZoneOn = Boolean(on);
    safeMask?.classList.toggle("on", safeZoneOn);
    safeBtn?.classList.toggle("on", safeZoneOn);
    if (persist) callApi()?.set_setting?.("studio_safe_zone", safeZoneOn)?.catch?.(() => {});
  }
  if (safeBtn) {
    safeBtn.title = "TikTok / Reels / Shorts Güvenli Alan Maskesi (Ayar olarak kaydedilir)";
    safeBtn.addEventListener("click", (e) => {
      e.stopImmediatePropagation();
      applySafeZone(!safeZoneOn, true);
    }, true);
  }
  setTimeout(async () => {
    try {
      const s = await callApi()?.get_settings?.();
      if (s && "studio_safe_zone" in s) applySafeZone(Boolean(s.studio_safe_zone), false);
    } catch {}
  }, 350);

  // ---- 6. Kami 2.0 B6: Descript Tarzi "Metin Siler Gibi Video Kurgu" + B5 Auto-Cursor Zoom ----
  if (smMenu && !smMenu.querySelector('[data-smart="descript"]')) {
    smMenu.insertAdjacentHTML("beforeend", `
      <button type="button" data-smart="descript">📝 Metin Siler Gibi Video Kurgu (Descript)</button>
      <button type="button" data-smart="cursorzoom">🔍 Otomatik Tıklama Zoom'u (Screen Studio)</button>
    `);
  }

  async function openDescriptEditor() {
    const c = window.selClips?.()?.[0] || window.ST?.p?.clips?.find((x) => ST.p.assets?.[x.asset]?.kind === "video");
    const asset = c ? window.ST?.p?.assets?.[c.asset] : null;
    if (!c || !asset) { window.toast?.("Lütfen önce zaman çizelgesinde bir video klibi seç"); return; }

    let segments = [];
    // Varsa altyazi veya isaretlerden, yoksa klibi esit konusma bloklarina bolerek kelime/cumle kartlari olustur
    const subs = (window.ST?.p?.clips || []).filter((x) => x.text || x.kind === "text");
    if (subs.length) {
      segments = subs.map((s, i) => ({ id: i, start: s.start, end: s.start + (s.dur || 2), text: s.text || `Bölüm ${i + 1}`, cut: false }));
    } else {
      const dur = Math.max(2, Number(c.dur || 10));
      const step = Math.max(1.5, Math.min(4.0, dur / 8));
      let idx = 0;
      for (let t = 0; t < dur - 0.2; t += step) {
        const s0 = c.start + t, s1 = Math.min(c.start + dur, c.start + t + step);
        segments.push({ id: idx++, start: Number(s0.toFixed(2)), end: Number(s1.toFixed(2)), text: `[${s0.toFixed(1)}s–${s1.toFixed(1)}s Konuşma Bloğu #${idx}]`, cut: false });
      }
    }

    const ov = document.createElement("div");
    ov.className = "st-desc-ov";
    ov.innerHTML = `
      <div class="st-desc-box">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <b>📝 Descript Tarzı Metin Siler Gibi Video Kurgu · <span style="color:#38BDF8">${(asset.name || "Klip").replace(/</g, "&lt;")}</span></b>
          <button class="tb" id="stDescX">✕</button>
        </div>
        <small style="color:#A39BB5">Üstünü çizdiğin (tıkladığın) kelime veya cümle blokları, <b>[Seçili Kısımları Videodan Kes &amp; Birleştir]</b> dediğinde zaman çizelgesinden otomatik kesilip Ripple ile boşluksuz birleştirilir.</small>
        <div class="st-desc-words" id="stDescWords"></div>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span id="stDescInfo" style="font-size:12px;color:#2EE6A6">0 blok silmek üzere seçildi</span>
          <div style="display:flex;gap:8px">
            <button class="tb" id="stDescWhisper">🎙 Whisper ile Kelimeleri Çıkar</button>
            <button class="tb pri" id="stDescApply">✂ Seçili Metinleri Videodan Kes &amp; Birleştir</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(ov);
    const box = ov.querySelector("#stDescWords");
    const info = ov.querySelector("#stDescInfo");
    const drawWords = () => {
      box.innerHTML = segments.map((sg, i) => `<span class="st-dw${sg.cut ? " cut" : ""}" data-i="${i}" title="${sg.start}s - ${sg.end}s">${sg.text.replace(/</g, "&lt;")}</span>`).join("");
      const cutN = segments.filter((x) => x.cut).length;
      info.textContent = `${cutN} konuşma bloğu videodan kesilecek`;
      box.querySelectorAll(".st-dw").forEach((el) => {
        el.onclick = () => {
          const item = segments[+el.dataset.i];
          item.cut = !item.cut;
          window.seek?.(item.start);
          drawWords();
        };
      });
    };
    drawWords();
    ov.querySelector("#stDescX").onclick = () => ov.remove();
    ov.querySelector("#stDescWhisper").onclick = async () => {
      if (!asset.path) return;
      info.textContent = "🎙 Whisper kelime zamanlamaları çıkarılıyor…";
      const r = await callApi()?.studio_transcribe_words?.(asset.path).catch(() => null);
      if (r?.words?.length) {
        segments = r.words.map((w, i) => ({ id: i, start: c.start + Number(w.start || 0), end: c.start + Number(w.end || (w.start + 0.4)), text: String(w.word || w.text || ""), cut: false }));
        drawWords();
        info.textContent = `✓ ${segments.length} kelime zaman damgasıyla yüklendi`;
      } else {
        info.textContent = "Not: Kelime bazlı Whisper bulunamadı, zaman bloklarıyla kesim yapabilirsin.";
      }
    };
    ov.querySelector("#stDescApply").onclick = () => {
      const kept = segments.filter((x) => !x.cut);
      if (!kept.length) { window.toast?.("Tüm blokları silemezsin"); return; }
      window.snap?.();
      // Bitisik korunan bloklari tek klip diliminde birlestir ve Ripple ile sirala
      const merged = [];
      for (const sg of kept) {
        const last = merged[merged.length - 1];
        if (last && Math.abs(sg.start - last.end) < 0.15) last.end = sg.end;
        else merged.push({ start: sg.start, end: sg.end });
      }
      const idx = ST.p.clips.indexOf(c);
      if (idx >= 0) {
        const baseIn = Number(c.in || 0);
        const baseStart = Number(c.start || 0);
        let cursor = baseStart;
        const newClips = merged.map((m, mi) => {
          const offset = Math.max(0, m.start - baseStart);
          const dur = Math.max(0.2, m.end - m.start);
          const nc = JSON.parse(JSON.stringify(c));
          nc.id = c.id + (mi ? "_d" + mi : "");
          nc.in = baseIn + offset;
          nc.start = cursor;
          nc.dur = dur;
          cursor += dur;
          return nc;
        });
        ST.p.clips.splice(idx, 1, ...newClips);
        window.changed?.(true);
      }
      ov.remove();
      window.toast?.(`✓ Seçilen metin aralıkları videodan kesildi ve Ripple ile birleştirildi`);
    };
  }

  smMenu?.addEventListener("click", async (e) => {
    const btn = e.target.closest("button");
    if (!btn) return;
    if (btn.dataset.smart === "descript") {
      openDescriptEditor();
    } else if (btn.dataset.smart === "cursorzoom") {
      const s = await callApi()?.get_settings?.().catch(() => ({}));
      const cur = s?.rec_cursor_zoom !== false;
      const c = window.selClips?.()?.[0] || window.ST?.p?.clips?.[0];
      if (c) {
        window.snap?.();
        c.zoomKeyframes = [
          { t: 0, scale: 1.0, x: 0.5, y: 0.5 },
          { t: Math.min(1.2, (c.dur || 4) * 0.3), scale: 1.38, x: 0.52, y: 0.48, spring: true },
          { t: Math.min(2.8, (c.dur || 4) * 0.75), scale: 1.0, x: 0.5, y: 0.5, spring: true },
        ];
        window.changed?.(false);
      }
      await callApi()?.set_setting?.("rec_cursor_zoom", !cur)?.catch?.(() => {});
      window.toast?.(`✓ Screen Studio Yaylı İmleç Zoom: ${!cur ? "AÇIK" : "KAPALI"} (Klibe yaylı zoom eğrisi eklendi)`);
    }
  });
})();
