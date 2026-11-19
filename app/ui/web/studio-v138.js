// Kami Studio v1.38.0 — 2-Tier Smart Menu, #tlOverview Dual Timeline, Fixed Playhead, Cursor Zoom, Middle-Click Pan & Hex Label Sync
"use strict";
(() => {
  const $id = (s) => document.getElementById(s);
  const callApi = () => window.pywebview?.api;

  // ---- 1. Akilli Araclar Dropdown ----
  const smBtn = $id("smartMenuBtn");
  const smMenu = $id("smartMenu");
  if (smBtn && smMenu) {
    smBtn.addEventListener("click", (e) => {
      e.stopPropagation();
      smMenu.hidden = !smMenu.hidden;
      smBtn.classList.toggle("on", !smMenu.hidden);
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
    setInterval(() => { if (!document.hidden) drawOverview(); }, 250);
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
})();
