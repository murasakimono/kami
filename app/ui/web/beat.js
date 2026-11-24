"use strict";
(() => {
  const api = () => window.pywebview?.api;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  let PROJ = null;
  let PRESETS = {};
  let VSTS = [];
  let AB_MODE = "A";
  let PC_REC = false;
  let BOOTH_TIMER = 0;
  let BOOTH_RUNNING = false;
  let SEL_TID = "vocal1";
  let ACTIVE_AUDIO_PATH = "";
  let LAST_MASH_OUT = "";
  // ---- Asama 1a: geri al / otomatik kayit / zaman cizelgesi ----
  const UNDO = [], REDO = [];
  const UNDO_MAX = 200;
  let SAVE_TIMER = 0;
  let SAVE_LOCK = 0;          // sunucu tarafli degisiklik (take ekleme, kayit, AI miks) surerken otomatik kayit bekler
  let SAVE_DIRTY = false;
  let LAT_RESULT = null;
  let TL = null;
  const RHYME_COLORS = ["#9D6BFF", "#14F195", "#F59E0B", "#EC4899", "#38BDF8", "#A3E635"];

  const setStatus = (t) => { $("#stMsg").textContent = t; };
  const aud = () => $("#audPreview");

  function fmtTime(sec) {
    const s = Math.max(0, Number(sec) || 0);
    const m = Math.floor(s / 60);
    const rem = s % 60;
    return `${String(m).padStart(2, "0")}:${rem < 10 ? "0" : ""}${rem.toFixed(1)}`;
  }

  function fxLabel(fx) {
    if (fx?.name) return fx.name;
    const map = {
      highpass: "Highpass", lowpass: "Lowpass", peak: "Parametric EQ",
      compressor: "Compressor", deesser: "De-Esser", distortion: "Saturator",
      delay: "Delay", reverb: "Reverb", limiter: "Limiter", noisegate: "Noise Gate", gain: "Gain",
    };
    return map[String(fx?.type || "").toLowerCase()] || (fx?.type || "FX");
  }

  function fxParamSummary(fx) {
    if (!fx) return "";
    const p = [];
    if (fx.cutoff_hz != null) p.push(`${Math.round(fx.cutoff_hz)} Hz`);
    if (fx.freq_hz != null) p.push(`${Math.round(fx.freq_hz)} Hz`);
    if (fx.threshold_db != null) p.push(`${fx.threshold_db} dB`);
    if (fx.ratio != null) p.push(`${fx.ratio}:1`);
    if (fx.gain_db != null) p.push(`${fx.gain_db > 0 ? "+" : ""}${fx.gain_db} dB`);
    if (fx.drive_db != null) p.push(`+${fx.drive_db} dB`);
    if (fx.room_size != null) p.push(`Oda ${Math.round(fx.room_size * 100)}%`);
    if (fx.mix != null) p.push(`Mix ${Math.round(fx.mix * 100)}%`);
    return p.slice(0, 2).join(" · ") || (fx.type === "vst3" ? "VST3 Plugin" : "Aktif");
  }

  async function waitApi() {
    for (let i = 0; i < 40; i++) {
      if (api()?.beat_list_projects) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    return false;
  }

  function drawWaveform(canvas, peaks, color, fillFade) {
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    const w = Math.max(120, canvas.clientWidth || 640);
    const h = Math.max(48, canvas.clientHeight || 96);
    canvas.width = Math.round(w * dpr);
    canvas.height = Math.round(h * dpr);
    const ctx = canvas.getContext("2d");
    ctx.scale(dpr, dpr);
    ctx.clearRect(0, 0, w, h);

    // Center line
    ctx.strokeStyle = "rgba(157, 107, 255, .18)";
    ctx.lineWidth = 1;
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    if (!peaks?.length) return;
    const n = peaks.length;
    const step = w / n;
    const barW = Math.max(1.5, step * 0.68);
    const mid = h / 2;

    const grad = ctx.createLinearGradient(0, 4, 0, h - 4);
    grad.addColorStop(0, color);
    grad.addColorStop(0.5, fillFade || color);
    grad.addColorStop(1, color);
    ctx.fillStyle = grad;

    for (let i = 0; i < n; i++) {
      const amp = Math.max(0.06, Math.min(1, Number(peaks[i]) || 0));
      const bh = amp * (h * 0.82);
      const x = i * step + (step - barW) / 2;
      ctx.fillRect(x, mid - bh / 2, barW, Math.max(2, bh));
    }
  }

  async function init() {
    initTimeline();
    await waitApi();
    const [pr, vr, lr, dr] = await Promise.all([
      api()?.beat_presets?.().catch(() => ({ presets: {} })) || { presets: {} },
      api()?.beat_vst_scan?.().catch(() => ({ plugins: [] })) || { plugins: [] },
      api()?.beat_list_projects?.().catch(() => ({ projects: [] })) || { projects: [] },
      api()?.booth_devices?.().catch(() => ({ devices: [] })) || { devices: [] },
    ]);
    PRESETS = pr?.presets || {};
    VSTS = vr?.plugins || [];
    renderVsts();
    renderMics(dr?.devices || []);

    const list = lr?.projects || [];
    if (list.length) {
      await loadProj(list[0].id);
    } else if (api()?.beat_create_project) {
      const cr = await api().beat_create_project("İlk Parça").catch(() => null);
      if (cr?.ok) PROJ = cr.project;
    } else {
      PROJ = {
        id: "demo",
        name: "Önizleme Oturumu",
        bpm: 124,
        key: "Am",
        lyrics: "Gece çöker şehrin üstüne\nSokak lambaları şahit her sözüme",
        tracks: [
          { id: "beat", name: "Beat / Altyapı", role: "beat", path: "", volume_db: -1.5, pan: 0, offset_ms: 0, fx: [] },
          { id: "vocal1", name: "Ana Vokal", role: "vocal", path: "", volume_db: 0, pan: 0, offset_ms: 0, preset: "clean_rap", fx: [
            { type: "highpass", cutoff_hz: 90 },
            { type: "compressor", threshold_db: -18, ratio: 4 },
            { type: "deesser", freq_hz: 6800, gain_db: -4 },
            { type: "reverb", room_size: 0.18, wet_level: 0.08 },
          ] },
        ],
      };
    }
    await refreshProjSelect();
    renderProject();
  }

  async function refreshProjSelect() {
    const lr = await api()?.beat_list_projects?.().catch(() => ({ projects: [] })) || { projects: [] };
    const sel = $("#projSelect");
    const items = lr?.projects?.length ? lr.projects : (PROJ ? [PROJ] : []);
    sel.innerHTML = items.map((p) => `<option value="${esc(p.id)}" ${PROJ && p.id === PROJ.id ? "selected" : ""}>${esc(p.name)} (${Math.round(p.bpm || 120)} BPM)</option>`).join("");
  }

  async function loadProj(id, opts = {}) {
    await flushSave();
    const r = await api()?.beat_load_project?.(id).catch(() => null);
    if (!r?.ok) { setStatus("Proje açılamadı: " + (r?.error || "?")); return false; }
    TL?.stop();
    PROJ = r.project;
    if (!opts.keepHistory) { UNDO.length = 0; REDO.length = 0; TL?.clearSel(); }
    renderProject();
    if (!opts.keepView) { TL?.setPlayhead(0, false); TL?.fit(); }
    if (r.recovered) setStatus("⚠ Proje dosyası bozuktu — son otomatik kayıttan kurtarıldı.");
    return true;
  }

  function selTrack() {
    const tracks = PROJ?.tracks || [];
    return tracks.find((x) => x.id === SEL_TID) || tracks.find((x) => x.role === "vocal") || tracks[0] || null;
  }

  // ---------------- Geri al / yinele + otomatik kayit ----------------
  const snap = () => JSON.stringify({ tracks: PROJ?.tracks || [], latency_ms: PROJ?.latency_ms || 0 });
  function restore(s) {
    const d = JSON.parse(s);
    PROJ.tracks = d.tracks;
    PROJ.latency_ms = d.latency_ms;
    TL?.pruneSelection();
  }
  function pushUndo(before) {
    UNDO.push(before);
    if (UNDO.length > UNDO_MAX) UNDO.shift();
    REDO.length = 0;
    updateUndoUi();
  }
  function updateUndoUi() {
    $("#tlUndo").disabled = !UNDO.length;
    $("#tlRedo").disabled = !REDO.length;
  }
  /** Proje durumunu degistiren her islem buradan gecer: anlik goruntu -> geri al yigini -> cizim -> 800 ms sonra kayit. */
  function edit(label, fn) {
    if (!PROJ) return;
    const before = snap();
    fn();
    commitFrom(label, before);
  }
  function commitFrom(label, before) {
    if (!PROJ || snap() === before) return;
    pushUndo(before);
    afterChange(label);
  }
  function afterChange(label) {
    renderProject();
    scheduleSave();
    TL?.restartIfPlaying();
    if (label) setStatus(label);
  }
  function undo() {
    if (!UNDO.length || !PROJ) return;
    REDO.push(snap());
    restore(UNDO.pop());
    updateUndoUi();
    afterChange(`Geri alındı (${UNDO.length} adım kaldı)`);
  }
  function redo() {
    if (!REDO.length || !PROJ) return;
    UNDO.push(snap());
    restore(REDO.pop());
    updateUndoUi();
    afterChange("Yinelendi");
  }
  function scheduleSave() {
    SAVE_DIRTY = true;
    clearTimeout(SAVE_TIMER);
    SAVE_TIMER = setTimeout(() => { flushSave(); }, 800);
  }
  async function flushSave() {
    clearTimeout(SAVE_TIMER);
    SAVE_TIMER = 0;
    if (!SAVE_DIRTY || !PROJ || !api()?.beat_save_project) return;
    if (SAVE_LOCK) { SAVE_TIMER = setTimeout(flushSave, 400); return; }
    if (BOOTH_RUNNING) {   // iPhone'dan yeni take geldiyse once birlestir (yoksa eski proje onu ezerdi)
      SAVE_LOCK++;
      try { await checkBoothUpload(); } finally { SAVE_LOCK--; }
    }
    SAVE_DIRTY = false;
    const r = await api().beat_save_project(PROJ).catch(() => null);
    if (!r?.ok) { SAVE_DIRTY = true; setStatus("⚠ Otomatik kayıt başarısız: " + (r?.error || "?")); }
  }
  async function saveProj() { scheduleSave(); await flushSave(); }
  /** Python tarafinin projeyi degistirdigi islemler (take ekleme, kayit durdurma, AI miks): once bekleyen kaydi yaz,
      islem bitene kadar otomatik kaydi kilitle, sonra projeyi yeniden yukle ve tek geri al adimi olarak isle. */
  async function serverMutate(label, fn) {
    if (!PROJ) return null;
    await flushSave();
    SAVE_LOCK++;
    const before = snap();
    try {
      const r = await fn();
      if (r?.ok) {
        if (r.project) PROJ = r.project;
        else {
          const lr = await api()?.beat_load_project?.(PROJ.id).catch(() => null);
          if (lr?.ok) PROJ = lr.project;
        }
        if (snap() !== before) pushUndo(before);
        renderProject();
        if (label) setStatus(label);
      }
      return r;
    } finally {
      SAVE_LOCK--;
    }
  }
  window.addEventListener("beforeunload", () => { if (SAVE_DIRTY && PROJ) api()?.beat_save_project?.(PROJ); });

  function renderVsts() {

    $("#vstCount").textContent = String(VSTS.length);
    $("#vstList").innerHTML = VSTS.length ? VSTS.map((v) => `
      <div class="kb-vst-row">
        <div><b>${esc(v.name)}</b><small>${esc(v.category)}</small></div>
        <button type="button" class="btn" data-addvst="${esc(v.path)}" data-vstname="${esc(v.name)}">+ Ekle</button>
      </div>`).join("") : '<div class="kb-mut">Sistemde VST3 bulunamadı (Common Files\\VST3 taranır).</div>';
  }

  function renderMics(devs) {
    $("#micSel").innerHTML = devs.length
      ? devs.map((d) => `<option value="${d.id}" ${d.default ? "selected" : ""}>${esc(d.name)}</option>`).join("")
      : '<option value="-1">Varsayılan Mikrofon</option>';
  }

  function renderFxRack() {
    const tr = selTrack();
    $("#fxTargetName").textContent = tr ? tr.name : "—";
    $("#selTrackHint").textContent = tr ? `${tr.name} seçili` : "";
    $("#vstTargetInfo").textContent = `Hedef kanal: ${tr ? tr.name : "Ana Vokal"}`;
    const fx = tr?.fx || [];
    if (!fx.length) {
      $("#fxRack").innerHTML = `<div class="kb-mut" style="display:grid;place-items:center;padding:8px">Bu kanalda FX yok — sağdaki VST3 sekmesinden ekle veya kanaldan şablon seç.</div>`;
      return;
    }
    $("#fxRack").innerHTML = fx.map((f, idx) => `
      <div class="kb-fx-mod ${f.bypass ? "off" : ""}" data-togglefx="${esc(tr.id)}:${idx}" title="Bypass aç/kapat">
        <div class="kb-fx-top">
          <span class="kb-fx-led"></span>
          <span class="kb-fx-name">${esc(fxLabel(f))}</span>
          <button type="button" class="kb-fx-del" data-delfx="${esc(tr.id)}:${idx}" title="Kaldır">✕</button>
        </div>
        <div class="kb-fx-param">${esc(fxParamSummary(f))}</div>
      </div>`).join("");
  }

  function renderProject() {
    if (!PROJ) return;
    syncLoopUi();
    $("#metaPill").textContent = `${Math.round(PROJ.bpm || 120)} BPM · ${PROJ.key || "—"}`;
    if (document.activeElement !== $("#lyrInput")) $("#lyrInput").value = PROJ.lyrics || "";
    $("#abToggle").disabled = !PROJ.reference_path;
    $("#latCur").textContent = `${Math.round(Number(PROJ.latency_ms) || 0)} ms`;

    const tracks = PROJ.tracks || [];
    tracks.forEach((tr) => { if (!Array.isArray(tr.clips)) tr.clips = []; });
    if (!tracks.some((t) => t.id === SEL_TID) && tracks.length) SEL_TID = tracks[0].id;

    let vocalIdx = 0;
    $("#tlHeads").innerHTML = tracks.map((tr) => {
      const col = BeatTimeline.trackColor(tr, tr.role === "beat" ? 0 : vocalIdx++);
      const takes = tr.takes || [];
      const presetOpts = Object.entries(PRESETS).map(([k, v]) => `<option value="${esc(k)}" ${tr.preset === k ? "selected" : ""}>${esc(v.name)}</option>`).join("");
      const takeOpts = takes.map((t) => `<option value="${esc(t.id)}" ${tr.active_take === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("");
      return `
        <div class="kb-head ${tr.id === SEL_TID ? "sel" : ""}" data-tid="${esc(tr.id)}" style="--tc:${col}">
          <div class="kb-ch">
            <span class="kb-role-bar"></span>
            <div class="kb-ch-top">
              <b>${esc(tr.name)}</b>
              <button type="button" class="kb-ms ${tr.mute ? "m-on" : ""}" data-mute="${esc(tr.id)}" title="Sessize Al (Mute)">M</button>
              <button type="button" class="kb-ms ${tr.solo ? "s-on" : ""}" data-solo="${esc(tr.id)}" title="Tek Çal (Solo)">S</button>
            </div>
            <div class="kb-ch-mid">
              <button type="button" class="btn" data-pick="${esc(tr.id)}" title="Ses dosyası ekle (kanal boşsa başa, değilse son klibin arkasına; belirli yere eklemek için şeride çift tıkla)">📂 Ses</button>
              ${takes.length ? `<select class="kb-sel" data-take="${esc(tr.id)}" title="Take Comping: seçili (yoksa aktif take'teki) klipleri bu take ile değiştir">${takeOpts}</select>` : ""}
              ${tr.role === "vocal" ? `<select class="kb-sel" data-preset="${esc(tr.id)}" title="Vokal Şablonu"><option value="">Şablon…</option>${presetOpts}</select>` : ""}
            </div>
            <div class="kb-ch-bot">
              <span>Ses</span>
              <input type="range" data-vol="${esc(tr.id)}" min="-24" max="6" step="0.5" value="${tr.volume_db ?? 0}">
              <span class="kb-db-val">${(tr.volume_db ?? 0) > 0 ? "+" : ""}${tr.volume_db ?? 0} dB</span>
              <input type="range" data-pan="${esc(tr.id)}" min="-1" max="1" step="0.05" value="${tr.pan ?? 0}" style="max-width:46px" title="Pan (L/R)">
              <input type="number" data-lat="${esc(tr.id)}" value="${tr.latency_ms ?? 0}" step="1" title="Kanal kayıt gecikmesi (ms) — bu kanala yeni kayıt klipleri bu kadar sola kaydırılır (proje gecikmesine eklenir)">
            </div>
          </div>
        </div>`;
    }).join("");

    renderFxRack();
    TL?.render();
    updateUndoUi();
  }

  async function playPath(path, label = "", frac = 0) {
    if (!path) {
      setStatus("Bu kanalda henüz ses dosyası yok.");
      return false;
    }
    TL?.stop();
    const a = aud();
    if (ACTIVE_AUDIO_PATH === path && a.src) {
      if (frac > 0 && a.duration > 0) a.currentTime = a.duration * frac;
      if (a.paused) a.play().catch(() => {});
      else if (!frac) a.pause();
      return true;
    }
    if (!api()?.beat_media_url) {
      if (api()?.player_show) { api().player_show({ path }); return true; }
      setStatus("Önizleme yalnızca uygulama penceresinde çalışır.");
      return false;
    }
    const r = await api().beat_media_url(path).catch(() => null);
    if (!r?.ok || !r.url) {
      if (api()?.player_show) { api().player_show({ path }); return true; }
      setStatus("Ses açılamadı: " + (r?.error || "?"));
      return false;
    }
    ACTIVE_AUDIO_PATH = path;
    a.src = r.url;
    $("#nowPlayingLbl").textContent = label || path.split(/[\\/]/).pop();
    a.onloadedmetadata = () => {
      if (frac > 0 && a.duration > 0) a.currentTime = a.duration * frac;
      a.play().catch(() => {});
    };
    a.play().catch(() => {});
    return true;
  }

  // <audio> yalniz Mixdown/Referans/A-B/Mashup dinlemesi icin; zaman cizelgesi Web Audio ile calar.
  function syncPlayheadUI() {
    const a = aud();
    const on = !a.paused && !!a.src;
    if (on) $("#lcdTime").textContent = fmtTime(a.currentTime || 0);
    $("#nowPlayingLbl").classList.toggle("on", on);
    syncTransport();
  }
  function syncTransport() {
    const a = aud();
    const on = (TL?.isPlaying()) || (!a.paused && !!a.src);
    $("#trPlay").classList.toggle("on", !!on);
    $("#trPlay").textContent = on ? "⏸" : "▶";
  }

  aud().addEventListener("timeupdate", syncPlayheadUI);
  aud().addEventListener("play", syncPlayheadUI);
  aud().addEventListener("pause", syncPlayheadUI);
  aud().addEventListener("ended", syncPlayheadUI);

  $("#trPlay").onclick = () => {
    const a = aud();
    if (!a.paused && a.src) { a.pause(); return; }
    TL?.toggle();
  };
  $("#trStop").onclick = () => {
    const a = aud();
    a.pause();
    TL?.stop();
    TL?.setPlayhead(0, false);
    syncTransport();
  };
  $("#trRew").onclick = () => {
    TL?.setPlayhead(0);
    TL?.ensureVisible(0);
  };
  $("#trRec").onclick = () => $("#pcRecBtn")?.click();

  // ---------------- Zaman cizelgesi ----------------
  function initTimeline() {
    if (!window.BeatTimeline || !window.BeatClips) return;
    TL = BeatTimeline.create({
      api,
      el: { scroll: $("#tlScroll"), content: $("#tlContent"), ruler: $("#tlRuler"), heads: $("#tlHeads") },
      getProj: () => PROJ,
      selTid: () => SEL_TID,
      edit,
      commitFrom,
      snap,
      onStatus: setStatus,
      onTime: (t) => { if (aud().paused) $("#lcdTime").textContent = fmtTime(t); },
      onPlayState: (on) => {
        if (on && !aud().paused) aud().pause();
        syncTransport();
      },
      onZoom: (pps) => { $("#tlZoomLbl").textContent = `${pps < 10 ? pps.toFixed(1) : Math.round(pps)} px/s`; },
      onSelectTrack: (tid) => selectTrack(tid),
      onPickForTrack: (tid, t) => pickAudioFor(tid, t),
      follow: () => $("#tlFollow").checked,
      keepRolling: () => PC_REC,
      onLoopChange: () => { syncLoopUi(); scheduleSave(); },
    });
    TL.setSnap(+$("#tlSnap").value);
    applyRecSetUi();
  }

  function selectTrack(tid) {
    if (!tid || tid === SEL_TID) return;
    SEL_TID = tid;
    document.querySelectorAll(".kb-head").forEach((x) => x.classList.toggle("sel", x.dataset.tid === SEL_TID));
    document.querySelectorAll(".kb-tl-lane").forEach((x) => x.classList.toggle("sel", x.dataset.lane === SEL_TID));
    renderFxRack();
  }

  async function pickAudioFor(tid, startSec) {
    if (!PROJ) return;
    const pick = await api()?.beat_pick_audio?.();
    if (!pick?.path) return;
    // startSec yoksa (📂 Ses): Python varsayilani -> kanal bossa 0, degilse son klibin sonu
    const st = startSec == null ? -1 : startSec;
    const r = await serverMutate("Ses kanala eklendi.", () => api().beat_add_take(PROJ.id, tid, pick.path, "", st));
    if (r && !r.ok) setStatus("Eklenemedi: " + (r.error || "?"));
    else if (r?.ok && !r.clip) setStatus("Take eklendi ama süresi okunamadı (dosya bozuk olabilir).");
  }

  $("#tlUndo").onclick = undo;
  $("#tlRedo").onclick = redo;
  $("#tlSplit").onclick = () => TL?.splitSelected();
  $("#tlDup").onclick = () => TL?.duplicateSelected();
  $("#tlDel").onclick = () => TL?.deleteSelected();
  $("#tlZoomIn").onclick = () => TL?.zoomBy(1.5);
  $("#tlZoomOut").onclick = () => TL?.zoomBy(1 / 1.5);
  $("#tlFit").onclick = () => TL?.fit();
  $("#tlSnap").onchange = (e) => { TL?.setSnap(+e.target.value); e.target.blur(); };
  // secim kutusu degisince odagi birak: kisayollar (Bosluk, S, Delete) hemen calissin
  $("#tlHeads").addEventListener("change", (e) => { if (e.target.tagName === "SELECT") setTimeout(() => e.target.blur(), 0); });

  // Kisayollar (metin alanina yazarken calismaz)
  document.addEventListener("keydown", (e) => {
    const t = e.target;
    if (RECST) {   // kayit modu: yalniz bitir / iptal / metronom
      const k0 = e.key;
      if (k0 === "Escape") { e.preventDefault(); recCancel(); }
      else if (k0 === "r" || k0 === "R" || k0 === " ") { e.preventDefault(); if (t && t.tagName === "BUTTON") t.blur(); recStop(); }
      else if ((k0 === "m" || k0 === "M") && !(e.ctrlKey || e.metaKey)) { e.preventDefault(); toggleMetro(); }
      return;
    }
    if (t && (t.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(t.tagName))) {
      if (t.type !== "range") return;   // surgu odaktaysa kisayollar yine calissin
      if (/^(Arrow|Page|Home|End)/.test(e.key)) return;
    }
    if (t && t.tagName === "BUTTON" && e.key === " ") t.blur();   // bosluk odakli dugmeyi ikinci kez tetiklemesin
    if ($("#studioPane").hidden || !TL) return;
    const k = e.key;
    const ctrl = e.ctrlKey || e.metaKey;
    if (k === " ") { e.preventDefault(); $("#trPlay").click(); }
    else if (ctrl && (k === "z" || k === "Z") && !e.shiftKey) { e.preventDefault(); undo(); }
    else if (ctrl && (k === "y" || k === "Y" || ((k === "z" || k === "Z") && e.shiftKey))) { e.preventDefault(); redo(); }
    else if (ctrl && (k === "d" || k === "D")) { e.preventDefault(); TL.duplicateSelected(); }
    else if (!ctrl && (k === "s" || k === "S")) { e.preventDefault(); TL.splitSelected(); }
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); TL.deleteSelected(); }
    else if (!ctrl && (k === "+" || k === "=" || e.code === "NumpadAdd")) { e.preventDefault(); TL.zoomBy(1.5); }
    else if (!ctrl && (k === "-" || k === "_" || e.code === "NumpadSubtract")) { e.preventDefault(); TL.zoomBy(1 / 1.5); }
    else if (k === "Home") { e.preventDefault(); TL.setPlayhead(0); TL.ensureVisible(0); }
    else if (!ctrl && !e.altKey && (k === "r" || k === "R")) { e.preventDefault(); recStart(); }
    else if (!ctrl && !e.altKey && (k === "l" || k === "L")) { e.preventDefault(); toggleLoopUi(); }
    else if (!ctrl && !e.altKey && (k === "m" || k === "M")) { e.preventDefault(); toggleMetro(); }
    else if (!ctrl && !e.altKey && (k === "c" || k === "C")) { e.preventDefault(); toggleCount(); }
  });

  async function analyzeLyricsUI() {
    const txt = $("#lyrInput").value;
    if (PROJ) PROJ.lyrics = txt;
    const r = await api()?.beat_lyrics_analyze?.(txt, PROJ?.bpm || 0).catch(() => null);
    if (!r?.ok) return;
    $("#lyrStats").textContent = `${r.total_lines} satır · ${r.total_syllables} hece · ${r.rhyme_groups} kafiye`;
    $("#lyrBars").innerHTML = (r.lines || []).filter((l) => l.text.trim()).map((l) => {
      const col = l.rhyme_group ? RHYME_COLORS[(l.rhyme_group - 1) % RHYME_COLORS.length] : "rgba(157,107,255,.15)";
      return `<div class="kb-lyr-line"><span class="kb-syl">${l.syllables}</span><span class="kb-rhyme" style="background:${col}"></span><span>${esc(l.text)}</span></div>`;
    }).join("");
  }

  // ---- Mode & Side Tabs ----
  document.querySelectorAll(".kb-tab").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".kb-tab").forEach((x) => x.classList.toggle("on", x === b));
      const mash = b.dataset.mode === "mashup";
      if (mash) TL?.stop();
      $("#studioPane").hidden = mash;
      $("#mashupPane").hidden = !mash;
      $("#kbSide").hidden = mash;
      $("#kbBody").classList.toggle("mash", mash);
      if (!mash) TL?.render();
    };
  });

  document.querySelectorAll(".kb-side-tabs button").forEach((b) => {
    b.onclick = () => {
      document.querySelectorAll(".kb-side-tabs button").forEach((x) => x.classList.toggle("on", x === b));
      ["booth", "lyrics", "vst"].forEach((k) => { $(`#pane-${k}`).hidden = b.dataset.side !== k; });
    };
  });

  $("#projSelect").onchange = (e) => loadProj(e.target.value);
  $("#projNew").onclick = async () => {
    await flushSave();
    const cr = await api()?.beat_create_project?.("Yeni Parça " + new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }));
    if (cr?.ok) {
      TL?.stop();
      PROJ = cr.project; UNDO.length = 0; REDO.length = 0;
      await refreshProjSelect(); renderProject(); TL?.setPlayhead(0, false); TL?.fit();
    }
  };

  // ---- Kanal basliklari ----
  $("#tlHeads").addEventListener("click", async (e) => {
    const head = e.target.closest(".kb-head[data-tid]");
    if (head) selectTrack(head.dataset.tid);
    const b = e.target.closest("button");
    if (!b || !PROJ) return;
    if (b.dataset.pick) {
      await pickAudioFor(b.dataset.pick);
    } else if (b.dataset.mute) {
      edit("Mute", () => { const tr = PROJ.tracks.find((x) => x.id === b.dataset.mute); if (tr) tr.mute = !tr.mute; });
    } else if (b.dataset.solo) {
      edit("Solo", () => { const tr = PROJ.tracks.find((x) => x.id === b.dataset.solo); if (tr) tr.solo = !tr.solo; });
    }
  });

  $("#tlHeads").addEventListener("change", (e) => {
    if (!PROJ) return;
    const el = e.target;
    if (el.dataset.preset) {
      const p = PRESETS[el.value];
      if (!p) return;
      SEL_TID = el.dataset.preset;
      edit(`${p.name} uygulandı.`, () => {
        const tr = PROJ.tracks.find((x) => x.id === el.dataset.preset);
        if (tr) { tr.preset = el.value; tr.denoise = !!p.denoise; tr.fx = JSON.parse(JSON.stringify(p.fx)); }
      });
    } else if (el.dataset.take) {
      // Take comping: secili klipler (yoksa aktif take'ten gelen klipler) ayni zamanlamayla yeni take'e gecer
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.take);
      const tk = tr?.takes?.find((t) => t.id === el.value);
      if (!tr || !tk) return;
      // 1b: take bir destenin uyesiyse (dongu/punch take'i) comping yerine desteyi o take'e cevir
      const inStack = tr.clips.find((c) => c.take_id === tk.id && c.stack_id);
      if (inStack) {
        edit(`Aktif take: ${tk.label}`, () => {
          tr.active_take = tk.id;
          tr.clips = BeatClips.stackSetActive(tr.clips, inStack.stack_id, inStack.id);
        });
        TL?.animateTakeIn([inStack.id]);
        return;
      }
      const sel = TL ? TL.selection() : new Set();
      const mine = tr.clips.filter((c) => sel.has(c.id));
      const targets = new Set((mine.length ? mine : tr.clips.filter((c) => c.take_id === tr.active_take)).map((c) => c.id));
      edit(`Take: ${tk.label}`, () => {
        tr.active_take = tk.id;
        tr.path = tk.path;
        tr.clips = tr.clips.map((c) => {
          if (!targets.has(c.id)) return c;
          const n = Object.assign({}, c, { take_id: tk.id, path: tk.path });
          delete n.src_len;   // yeni kaynagin suresi dalga formu gelince ogrenilir
          return BeatClips.normalize(n);
        });
      });
    } else if (el.dataset.lat) {
      edit("Kanal gecikmesi", () => { const tr = PROJ.tracks.find((x) => x.id === el.dataset.lat); if (tr) tr.latency_ms = +el.value || 0; });
    } else if (el.dataset.vol || el.dataset.pan) {
      const before = el.dataset.before;
      if (before) { delete el.dataset.before; commitFrom(el.dataset.vol ? "Ses seviyesi" : "Pan", before); }
    }
  });

  // Surgu suruklenirken canli; birakinca tek geri al adimi (change olayinda commitFrom)
  $("#tlHeads").addEventListener("input", (e) => {
    if (!PROJ) return;
    const el = e.target;
    const tid = el.dataset.vol || el.dataset.pan;
    if (!tid) return;
    if (!el.dataset.before) el.dataset.before = snap();
    const tr = PROJ.tracks.find((x) => x.id === tid);
    if (!tr) return;
    if (el.dataset.vol) {
      tr.volume_db = +el.value;
      el.nextElementSibling.textContent = `${tr.volume_db > 0 ? "+" : ""}${tr.volume_db} dB`;
    } else tr.pan = +el.value;
  });

  // ---- Bottom FX Rack Interactions ----
  $("#fxRack").addEventListener("click", async (e) => {
    if (!PROJ) return;
    const delBtn = e.target.closest("[data-delfx]");
    if (delBtn) {
      e.stopPropagation();
      const [tid, idx] = delBtn.dataset.delfx.split(":");
      edit("FX kaldırıldı", () => { const tr = PROJ.tracks.find((x) => x.id === tid); if (tr) tr.fx.splice(+idx, 1); });
      return;
    }
    const mod = e.target.closest("[data-togglefx]");
    if (mod) {
      const [tid, idx] = mod.dataset.togglefx.split(":");
      edit("FX bypass", () => { const fx = PROJ.tracks.find((x) => x.id === tid)?.fx?.[+idx]; if (fx) fx.bypass = !fx.bypass; });
    }
  });

  $("#vstList").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-addvst]"); if (!b || !PROJ) return;
    const tr = selTrack();
    if (tr) edit(`${b.dataset.vstname} → ${tr.name} zincirine eklendi.`, () => {
      tr.fx.push({ type: "vst3", name: b.dataset.vstname, path: b.dataset.addvst });
    });
  });

  $("#vstScanBtn").onclick = async () => {
    const r = await api()?.beat_vst_scan?.();
    VSTS = r?.plugins || []; renderVsts();
  };

  $("#aiApplyBtn").onclick = async () => {
    if (!PROJ) return;
    const txt = $("#aiPrompt").value.trim(); if (!txt) return;
    const targetId = selTrack()?.id || "vocal1";
    setStatus("AI miks uygulanıyor…");
    const r = await serverMutate("", () => api()?.beat_ai_mix?.(PROJ.id, txt, targetId));
    if (r?.ok) { setStatus("AI Miks: " + (r.actions || []).join(" · ")); TL?.restartIfPlaying(); }
  };

  $("#mixdownBtn").onclick = async () => {
    if (!PROJ) return;
    const btn = $("#mixdownBtn");
    btn.disabled = true;
    setStatus("Bounce alınıyor (klipler + efektler, -14 LUFS)…");
    try {
      await flushSave();
      TL?.stop();
      const A = api();
      const r = A?.beat_bounce ? await A.beat_bounce(PROJ.id, "", -14.0) : await A?.beat_render_mixdown?.(PROJ.id, "", -14.0);
      if (r?.ok) {
        PROJ.last_mixdown = r.path;
        setStatus("✓ Bounce hazır: " + r.path);
        $("#lufsMsg").textContent = `LUFS: ${r.lufs ?? "—"} · Peak: ${r.peak_db ?? "—"} dB`;
        await playPath(r.path, `${PROJ.name} (Mixdown)`);
      } else setStatus("Bounce hatası: " + (r?.error || "?"));
    } finally { btn.disabled = false; }
  };

  $("#toStudioBtn").onclick = async () => {
    if (!PROJ) return;
    setStatus("Kami Studio lirik video hazırlanıyor…");
    await flushSave();
    const r = await api()?.beat_export_lyric_video?.(PROJ.id, PROJ.name);
    setStatus(r?.ok ? "✓ Kami Studio açıldı ve sözler aktarıldı." : ("Hata: " + (r?.error || "?")));
  };

  $("#refPick").onclick = async () => {
    if (!PROJ) return;
    const pr = await api()?.beat_pick_audio?.();
    if (pr?.path) {
      PROJ.reference_path = pr.path; scheduleSave(); $("#abToggle").disabled = false;
      const lr = await api()?.beat_measure_lufs?.(pr.path);
      if (lr?.ok) $("#lufsMsg").textContent = `Referans LUFS: ${lr.lufs} · Peak: ${lr.peak_db} dB`;
    }
  };
  $("#abToggle").onclick = async () => {
    if (!PROJ) return;
    AB_MODE = AB_MODE === "A" ? "B" : "A";
    $("#abToggle").textContent = AB_MODE === "A" ? "A/B: Miks (A)" : "A/B: Referans (B)";
    const p = AB_MODE === "B" ? PROJ.reference_path : PROJ.last_mixdown;
    if (p) await playPath(p, AB_MODE === "B" ? "Referans (B)" : "Miks (A)");
    else setStatus("Önce Mixdown al veya Referans seç.");
  };

  $("#lyrInput").addEventListener("input", () => { analyzeLyricsUI(); scheduleSave(); });

  // ---- Booth PC Mic + iPhone Wireless ----
  // iPhone Booth yuklemesi Python tarafinda projeye take+klip ekler; yerel (henuz kaydedilmemis) duzenlemeleri
  // kaybetmemek icin sunucudaki YENI take/klipler yerel projeye eklenir (birlestirme), proje yeniden yuklenmez.
  let BOOTH_LAST_TS = 0;
  async function checkBoothUpload() {
    if (!BOOTH_RUNNING || !PROJ) return false;
    const st = await api()?.booth_server_status?.().catch(() => null);
    if (!(st?.last_upload?.ts > BOOTH_LAST_TS)) return false;
    BOOTH_LAST_TS = st.last_upload.ts;
    const lr = await api()?.beat_load_project?.(PROJ.id).catch(() => null);
    if (!lr?.ok) return false;
    edit("✓ iPhone Booth'tan yeni take geldi!", () => {
      for (const st2 of lr.project.tracks || []) {
        const loc = PROJ.tracks.find((t) => t.id === st2.id);
        if (!loc) continue;
        const haveT = new Set((loc.takes || []).map((t) => t.id));
        const newTakes = (st2.takes || []).filter((t) => !haveT.has(t.id));
        if (!newTakes.length) continue;
        loc.takes = (loc.takes || []).concat(newTakes);
        const haveC = new Set((loc.clips || []).map((c) => c.id));
        const newIds = new Set(newTakes.map((t) => t.id));
        loc.clips = (loc.clips || []).concat((st2.clips || []).filter((c) => !haveC.has(c.id) && newIds.has(c.take_id)));
        loc.active_take = st2.active_take; loc.path = st2.path;
      }
    });
    await flushSave();
    return true;
  }

  // ---------------- 1b: kayit akisi (metronom, sayim, dongu + take destesi, punch-in, kayit modu) ----------------
  const RECSET = Object.assign({ metro: false, vol: 0.6, count: 1, lastCount: 1, preroll: 2 },
    (() => { try { return JSON.parse(localStorage.getItem("kb.rec") || "{}"); } catch { return {}; } })());
  let RECST = null;        // aktif kayit plani
  let LVL_TIMER = 0, LVL_BUSY = false, LVL_PEAK = 0;
  const saveRecSet = () => { try { localStorage.setItem("kb.rec", JSON.stringify(RECSET)); } catch {} };
  const fmtSigned = (x) => (x < 0 ? "−" : "") + fmtTime(Math.abs(x));

  function applyRecSetUi() {
    $("#tlMetro").classList.toggle("on", !!RECSET.metro);
    $("#tlMetroVol").value = String(Math.round(RECSET.vol * 100));
    $("#tlCount").value = String(RECSET.count);
    $("#tlPreroll").value = String(RECSET.preroll);
    TL?.setMetronome({ on: !!RECSET.metro, vol: RECSET.vol });
  }
  function syncLoopUi() { const L = PROJ?.loop; $("#tlLoop").classList.toggle("on", !!(L && L.on)); }
  function toggleMetro() {
    RECSET.metro = !RECSET.metro; saveRecSet(); applyRecSetUi();
    setStatus(RECSET.metro ? "Metronom açık (yalnız kulaklık)" : "Metronom kapalı");
  }
  function toggleCount() {
    if (RECSET.count) { RECSET.lastCount = RECSET.count; RECSET.count = 0; } else RECSET.count = RECSET.lastCount || 1;
    saveRecSet(); applyRecSetUi();
    setStatus(RECSET.count ? `Sayarak giriş: ${RECSET.count} bar` : "Sayarak giriş kapalı");
  }
  function toggleLoopUi() {
    const L = TL?.toggleLoop();
    syncLoopUi();
    if (L) setStatus(L.on ? `Döngü açık: ${fmtTime(L.start)} → ${fmtTime(L.end)}` : "Döngü kapalı");
  }
  $("#tlMetro").onclick = toggleMetro;
  $("#tlLoop").onclick = toggleLoopUi;
  $("#tlMetroVol").addEventListener("input", (e) => { RECSET.vol = (+e.target.value || 0) / 100; TL?.setMetronome({ vol: RECSET.vol }); });
  $("#tlMetroVol").addEventListener("change", (e) => { saveRecSet(); e.target.blur(); });
  $("#tlCount").onchange = (e) => { RECSET.count = +e.target.value || 0; if (RECSET.count) RECSET.lastCount = RECSET.count; saveRecSet(); e.target.blur(); };
  $("#tlPreroll").onchange = (e) => { RECSET.preroll = Math.max(0, Math.min(10, +e.target.value || 0)); e.target.value = RECSET.preroll; saveRecSet(); };
  $("#tlPunch").onclick = () => (RECST ? recStop() : recStart("punch"));

  function hudCount(n) {
    const c = $("#hudCount");
    if (n > 0) {
      c.hidden = false;
      c.textContent = String(n);
      c.classList.remove("beat"); void c.offsetWidth; c.classList.add("beat");
      $("#hudMode").textContent = "SAYIM";
    } else {
      c.hidden = true;
      if (RECST) $("#hudMode").textContent = { loop: "DÖNGÜ KAYDI", punch: "PUNCH", linear: "KAYIT" }[RECST.mode];
    }
  }
  function hudLap(n) { $("#hudLap").textContent = RECST?.mode === "loop" ? `Tur ${n + 1}${n ? ` · ${n} take` : ""}` : ""; }

  function enterRecUi(plan) {
    document.body.classList.add("kb-recmode");
    $("#recHud").hidden = false;
    $("#hudMode").textContent = plan.countIn ? "SAYIM" : plan.mode === "punch" ? "ÖN-ÇALMA" : plan.mode === "loop" ? "DÖNGÜ KAYDI" : "KAYIT";
    $("#hudTime").textContent = "0:00.0";
    $("#hudTrack").textContent = "→ " + ((PROJ?.tracks || []).find((x) => x.id === plan.tid)?.name || plan.tid);
    hudLap(0);
    $("#pcRecBtn").classList.add("bad"); $("#pcRecBtn").classList.remove("pri"); $("#pcRecBtn").textContent = "⏹ Kaydı Durdur";
    $("#trRec").classList.add("on");
    $("#tlPunch").classList.toggle("on", plan.mode === "punch");
    $("#pcRecSt").textContent = `Kayıt alınıyor → ${$("#hudTrack").textContent.slice(2)} @ ${fmtTime(plan.keep_from)}`;
    TL?.setRecLive({ trId: plan.tid, mode: plan.mode, from: plan.keep_from, a: plan.a, b: plan.b, t0: plan.t0, t1: plan.t1, laps: 0 });
    LVL_PEAK = 0;
    clearInterval(LVL_TIMER);
    LVL_TIMER = setInterval(pollLevel, 90);
  }
  function exitRecUi() {
    document.body.classList.remove("kb-recmode");
    $("#recHud").hidden = true;
    $("#hudCount").hidden = true;
    clearInterval(LVL_TIMER); LVL_TIMER = 0;
    $("#micVuFill").style.width = "0%";
    $("#pcRecBtn").classList.remove("bad"); $("#pcRecBtn").classList.add("pri"); $("#pcRecBtn").textContent = "🎙 Kayda Başla";
    $("#trRec").classList.remove("on");
    $("#tlPunch").classList.remove("on");
    TL?.setRecLive(null);
  }
  async function pollLevel() {
    const u = TL?.uNow();
    if (RECST && u != null) {
      const rel = u - RECST.keep_from;
      $("#hudTime").textContent = fmtSigned(rel);
      if (RECST.mode === "punch") $("#hudMode").textContent = rel < 0 ? "ÖN-ÇALMA" : "PUNCH";
    }
    if (LVL_BUSY) return;
    LVL_BUSY = true;
    try {
      const st = await api()?.booth_rec_status?.().catch(() => null);
      if (!st?.ok || !RECST) return;
      const db = Number(st.level_db);
      const pct = Math.max(0, Math.min(100, ((db + 60) / 60) * 100));
      LVL_PEAK = Math.max(pct, LVL_PEAK - 1.2);
      $("#hudLvl").style.width = pct + "%";
      $("#hudPeak").style.left = LVL_PEAK + "%";
      $("#hudLvl").classList.toggle("hot", db > -6);
      $("#hudDb").textContent = db <= -119 ? "−∞ dB" : `${db.toFixed(1)} dB${st.clip ? " · CLIP!" : ""}`;
      $("#micVuFill").style.width = pct + "%";
    } finally { LVL_BUSY = false; }
  }

  async function recStart(kind = "auto") {
    if (RECST || !PROJ || !TL) return;
    const bpmv = Number(PROJ.bpm) || 120;
    let plan;
    if (kind === "punch") {
      const sel = [...TL.selection()].map((id) => TL.findClip(id)).filter(Boolean);
      if (sel.length !== 1) { setStatus("Punch için önce tek bir klip seç."); return; }
      const L = PROJ.loop;
      if (!L || !(L.end - L.start >= 0.05)) { setStatus("Punch aralığı yok: cetvelde sürükleyerek bölge çiz (döngü kapalı da olabilir)."); return; }
      const [s, e] = BeatClips.clipBounds(sel[0].clip);
      const t0 = Math.max(s, L.start), t1 = Math.min(e, L.end);
      if (t1 - t0 < 0.05) { setStatus("Punch aralığı seçili klibin üstünde değil."); return; }
      const pre = Math.max(0, Number(RECSET.preroll) || 0);
      plan = { mode: "punch", tid: sel[0].tr.id, clipId: sel[0].clip.id, t0, t1, ustart: t0 - pre, keep_from: t0,
        loop: null, countIn: null, stopAtU: t1 + 0.3 };
    } else {
      const L = TL.loopRegion();
      const tid = recTrackId();
      const cnt = BeatTransport.countInPlan(L ? L.a : TL.getPlayhead(), bpmv, RECSET.count);
      plan = { mode: L ? "loop" : "linear", tid, a: L?.a, b: L?.b, ustart: cnt.transport_start, keep_from: cnt.rec_from,
        loop: L || null, countIn: cnt.beats ? { origin: cnt.rec_from, ticks: cnt.ticks } : null, stopAtU: null };
    }
    TL.stop();
    await flushSave();
    const r = await api()?.booth_rec_start?.(PROJ.id, plan.tid, +$("#micSel").value, -1);
    if (!r?.ok) { setStatus("Kayıt başlamadı: " + (r?.error || "mikrofon açılamadı")); $("#pcRecSt").textContent = "Hata: " + (r?.error || "?"); return; }
    RECST = plan;
    PC_REC = true;
    SAVE_LOCK++;   // kayit bitip Python klibi ekleyene kadar eski projeyi diske yazma
    enterRecUi(plan);
    const ok = await TL.play(plan.ustart, {
      loop: plan.loop, countIn: plan.countIn, rec: true, force: true, stopAtU: plan.stopAtU,
      onCount: hudCount,
      onLap: (n) => { if (RECST !== plan) return; plan.laps = n; TL.recLap(n); hudLap(n); if (n) setStatus(`Take ${n} tamam — tur ${n + 1} kaydediliyor`); },
      onAutoStop: () => { if (RECST === plan) recStop(); },
    });
    if (!ok && RECST === plan) { await recCancel(true); setStatus("Kayıt başlatılamadı (ses motoru açılamadı)."); }
  }

  async function recStop() {
    if (!RECST) return;
    const plan = RECST;
    RECST = null;
    const anchor = TL?.anchor();
    TL?.stop();
    PC_REC = false;
    exitRecUi();
    SAVE_LOCK = Math.max(0, SAVE_LOCK - 1);
    const p = {
      mode: plan.mode, track_id: plan.tid, keep_from: plan.keep_from,
      anchor_u: anchor ? anchor.u : plan.ustart, anchor_wall: (anchor ? anchor.wall : Date.now()) / 1000,
      loop_a: plan.a ?? null, loop_b: plan.b ?? null, clip_id: plan.clipId || "", t0: plan.t0 ?? null, t1: plan.t1 ?? null, xfade: 0.01,
    };
    setStatus("Kayıt işleniyor…");
    $("#pcRecSt").textContent = "Kayıt işleniyor…";
    const r = await serverMutate("", () => api()?.booth_rec_stop?.($("#micClean").checked, p));
    if (r?.ok) {
      const ids = r.new_clip_ids || [];
      const msg = r.mode === "loop" ? `✓ ${ids.length} take tek destede — son tur aktif (rozete tıkla: take seç)`
        : r.mode === "punch" ? "✓ Punch tamam — yeni take aralığın destesinde aktif"
          : `✓ Kaydedildi (${r.duration}s) — klip zaman çizelgesinde`;
      setStatus(msg);
      $("#pcRecSt").textContent = msg;
      const top = ids[ids.length - 1];
      if (top && TL.findClip(top)) TL.select(top, false);
      TL.animateTakeIn([top]);
      TL.setPlayhead(plan.mode === "punch" ? plan.t0 : plan.keep_from, false);
    } else {
      const err = { no_complete_lap: "Tam tur tamamlanmadı — take oluşmadı (ham kayıt klasörde duruyor).",
        punch_too_short: "Punch kaydı çok kısa kaldı.", punch_clip_not_found: "Punch klibi bulunamadı (silinmiş olabilir).",
        empty_recording: "Kayıt boş." }[r?.error] || ("Kayıt hatası: " + (r?.error || "?"));
      setStatus(err);
      $("#pcRecSt").textContent = err;
    }
  }

  async function recCancel(silent) {
    if (!RECST) return;
    RECST = null;
    TL?.stop();
    PC_REC = false;
    exitRecUi();
    SAVE_LOCK = Math.max(0, SAVE_LOCK - 1);
    const r = await api()?.booth_rec_cancel?.().catch(() => null);
    if (silent) return;
    const msg = r?.ok ? `Kayıt iptal edildi — take eklenmedi, ham ses saklandı: ${String(r.path || "").split(/[\\/]/).pop()}`
      : "İptal: " + (r?.error || "?");
    setStatus(msg);
    $("#pcRecSt").textContent = msg;
  }

  function recTrackId() {
    const tr = selTrack();
    return tr && tr.role !== "beat" ? tr.id : ((PROJ?.tracks || []).find((x) => x.role === "vocal")?.id || "vocal1");
  }
  $("#pcRecBtn").onclick = () => (RECST ? recStop() : recStart());

  // ---- Gecikme (alkis) testi ----
  $("#latMeasure").onclick = async () => {
    const btn = $("#latMeasure");
    btn.disabled = true;
    $("#latRes").textContent = "Ölçülüyor… (3 tık)";
    LAT_RESULT = null; $("#latApply").disabled = true;
    try {
      TL?.stop();
      const r = await api()?.beat_measure_latency?.(+$("#micSel").value);
      if (r?.ok) {
        LAT_RESULT = Number(r.latency_ms) || 0;
        const conf = Math.round((Number(r.confidence) || 0) * 100);
        $("#latRes").textContent = `${LAT_RESULT.toFixed(1)} ms · güven %${conf}${r.spread_ms != null ? ` · sapma ${r.spread_ms} ms` : ""}`;
        $("#latApply").disabled = false;
      } else {
        const msg = { no_signal: "Tık duyulmadı — sesi aç, kulaklığı mikrofona yaklaştır ve tekrar dene.",
          sounddevice_missing: "Ses aygıtı kütüphanesi (sounddevice) yok." }[r?.error] || ("Hata: " + (r?.error || "?"));
        $("#latRes").textContent = msg;
      }
    } finally { btn.disabled = false; }
  };
  $("#latApply").onclick = () => {
    if (LAT_RESULT == null || !PROJ) return;
    const v = Math.round(LAT_RESULT * 10) / 10;
    edit(`Proje kayıt gecikmesi: ${v} ms`, () => { PROJ.latency_ms = v; });
    $("#latApply").disabled = true;
  };

  $("#boothSrvBtn").onclick = async () => {
    const btn = $("#boothSrvBtn");
    if (BOOTH_RUNNING) {
      clearInterval(BOOTH_TIMER); BOOTH_TIMER = 0;
      await api()?.booth_server_stop?.().catch(() => {});
      BOOTH_RUNNING = false;
      btn.classList.remove("bad"); btn.classList.add("ok");
      btn.textContent = "Kablosuz Booth'u Başlat";
      $("#boothQrBox").hidden = true;
      $("#boothUrl").textContent = "";
      return;
    }
    await flushSave();
    const r = await api()?.booth_server_start?.(PROJ?.id || "", recTrackId());
    if (r?.ok) {
      BOOTH_RUNNING = true;
      btn.classList.remove("ok"); btn.classList.add("bad");
      btn.textContent = "⏹ Booth Sunucusunu Durdur";
      $("#boothUrl").textContent = r.url;
      $("#boothQrBox").hidden = false;
      const qr = await api()?.beat_qr_svg?.(r.url).catch(() => null);
      if (qr?.ok && qr.data_url) { $("#boothQrImg").src = qr.data_url; $("#boothQrImg").hidden = false; }
      else { $("#boothQrImg").hidden = true; }
      clearInterval(BOOTH_TIMER);
      BOOTH_LAST_TS = r.last_upload?.ts || 0;
      BOOTH_TIMER = setInterval(() => { checkBoothUpload(); }, 2500);
    }
  };
  $("#boothCopyBtn")?.addEventListener("click", () => {
    const u = $("#boothUrl").textContent.trim();
    if (u) navigator.clipboard?.writeText(u).then(() => setStatus("Booth linki kopyalandı."));
  });

  // ---- Dual-Deck Mashup ----
  async function loadDeckWave(path, cvsId, color) {
    if (!path || !api()?.beat_waveform) return;
    const wr = await api().beat_waveform(path, 160).catch(() => null);
    drawWaveform($(cvsId), wr?.peaks || [], color);
  }
  $("#mVocalPick").onclick = async () => {
    const r = await api()?.beat_pick_audio?.();
    if (r?.path) {
      $("#mVocal").value = r.path;
      $("#mVocalPlay").disabled = false;
      loadDeckWave(r.path, "#mVocalWave", "#9D6BFF");
    }
  };
  $("#mBeatPick").onclick = async () => {
    const r = await api()?.beat_pick_audio?.();
    if (r?.path) {
      $("#mBeat").value = r.path;
      $("#mBeatPlay").disabled = false;
      loadDeckWave(r.path, "#mBeatWave", "#14F195");
    }
  };
  $("#mVocalPlay").onclick = () => playPath($("#mVocal").value.trim(), "Deck A (Vokal)");
  $("#mBeatPlay").onclick = () => playPath($("#mBeat").value.trim(), "Deck B (Beat)");
  $("#mVDb").oninput = () => { const v = +$("#mVDb").value; $("#mVDbVal").textContent = `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`; };
  $("#mBDb").oninput = () => { const v = +$("#mBDb").value; $("#mBDbVal").textContent = `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`; };
  $("#mPlayOut").onclick = () => { if (LAST_MASH_OUT) playPath(LAST_MASH_OUT, "Mashup Çıktısı"); };

  $("#mGo").onclick = async () => {
    const v = $("#mVocal").value.trim(), b = $("#mBeat").value.trim();
    if (!v || !b) return;
    const btn = $("#mGo"); btn.disabled = true;
    $("#mRes").textContent = "BPM/Ton eşleştiriliyor ve mashup işleniyor…";
    try {
      const r = await api()?.beat_studio_mashup?.(v, b, "", +$("#mVDb").value, +$("#mBDb").value);
      if (r?.ok) {
        LAST_MASH_OUT = r.out || r.path || "";
        $("#mRes").textContent = `✓ Hazır (${LAST_MASH_OUT}) — Vokal ${r.vocal_bpm} BPM → Beat ${r.beat_bpm} BPM`;
        $("#mPlayOut").hidden = !LAST_MASH_OUT;
      } else {
        $("#mRes").textContent = "Hata: " + (r?.error || "?");
      }
    } finally { btn.disabled = false; }
  };

  init();
})();
