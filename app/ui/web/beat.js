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
  // 1c: sonuk kafiye paleti (koyu temada goz yormaz); beat_studio.RHYME_PALETTE_SIZE ile ayni uzunluk
  const RHYME_COLORS = ["#B39DF0", "#73C9A2", "#D9B26A", "#D98BB0", "#7FB8D9", "#AFC97C", "#D99C80", "#9CA6DE"];

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
    loadGlobalLat();   // R2: kalici genel gecikme ayari
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
  // 1c: bolum haritasi, soz zamanlari ve analizden gelen BPM/ton da geri al kapsaminda
  const snap = () => JSON.stringify({ tracks: PROJ?.tracks || [], latency_ms: PROJ?.latency_ms || 0,
    sections: PROJ?.sections || [], lyric_times: PROJ?.lyric_times || null, bpm: PROJ?.bpm, key: PROJ?.key });
  function restore(s) {
    const d = JSON.parse(s);
    PROJ.tracks = d.tracks;
    PROJ.latency_ms = d.latency_ms;
    if (Array.isArray(d.sections)) PROJ.sections = d.sections;
    if (d.lyric_times) PROJ.lyric_times = d.lyric_times;
    if (d.bpm != null) PROJ.bpm = d.bpm;
    if (d.key != null) PROJ.key = d.key;
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
  /** R1: ard arda ok tusu kaydirmalari tek geri al adimi (900 ms icinde ayni secim). */
  let NUDGE = { t: 0, key: "", base: null };
  function commitNudge(label, before) {
    if (!PROJ || snap() === before) return;
    const key = [...(TL?.selection() || [])].sort().join(",");
    const now = Date.now();
    if (NUDGE.base !== null && NUDGE.key === key && now - NUDGE.t < 900 && UNDO[UNDO.length - 1] === NUDGE.base) {
      NUDGE.t = now;            // yigin ustu zaten ilk kaydirmadan onceki hal: yeni adim ekleme
      REDO.length = 0;
      afterChange(label);
      return;
    }
    NUDGE = { t: now, key, base: before };
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
    syncLatUi();

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
    renderLyrics();
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
      el: { scroll: $("#tlScroll"), content: $("#tlContent"), ruler: $("#tlRuler"), heads: $("#tlHeads"), secs: $("#tlSections") },
      getProj: () => PROJ,
      selTid: () => SEL_TID,
      edit,
      commitFrom,
      snap,
      onStatus: setStatus,
      onTime: (t) => { if (aud().paused) $("#lcdTime").textContent = fmtTime(t); prUpdate(t); },
      onPlayState: (on) => {
        if (on && !aud().paused) aud().pause();
        syncTransport();
      },
      onZoom: (pps) => { $("#tlZoomLbl").textContent = `${pps < 10 ? pps.toFixed(1) : Math.round(pps)} px/s`; syncGridLabel(); },
      commitNudge,
      lyricFlag: () => lyricFlagT(),
      onLyricStart: (t, commit) => setLyricStart(t, commit),
      onSelectTrack: (tid) => selectTrack(tid),
      onPickForTrack: (tid, t) => pickAudioFor(tid, t),
      follow: () => $("#tlFollow").checked,
      keepRolling: () => PC_REC,
      onLoopChange: () => { syncLoopUi(); scheduleSave(); },
      onSectionClick: (sec) => sectionToLoop(sec),
    });
    TL.setSnap(gridMode());
    syncGridLabel();
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
    else if (r?.ok && PROJ.tracks.find((x) => x.id === tid)?.role === "beat" && !(PROJ.sections || []).length) analyzeSections(true);
  }

  $("#tlUndo").onclick = undo;
  $("#tlRedo").onclick = redo;
  $("#tlSplit").onclick = () => TL?.splitSelected();
  $("#tlDup").onclick = () => TL?.duplicateSelected();
  $("#tlDel").onclick = () => TL?.deleteSelected();
  $("#tlZoomIn").onclick = () => TL?.zoomBy(1.5);
  $("#tlZoomOut").onclick = () => TL?.zoomBy(1 / 1.5);
  $("#tlFit").onclick = () => TL?.fit();
  // R1: izgara secimi kalici (localStorage); Otomatik'te etkin bolum secicide yazar
  const GRID_LBL = { 1: "1 bar", 2: "1/2", 4: "1/4", 8: "1/8", 16: "1/16", 32: "1/32" };
  function gridMode() { const v = $("#tlSnap").value; return v === "auto" ? "auto" : +v; }
  function syncGridLabel() {
    const o = $("#tlSnap").querySelector('option[value="auto"]');
    if (o && TL) o.textContent = `Otomatik (${GRID_LBL[TL.effGrid()] || "—"})`;
  }
  try {
    const g = localStorage.getItem("kb.grid");
    if (g !== null && $("#tlSnap").querySelector(`option[value="${CSS.escape(g)}"]`)) $("#tlSnap").value = g;
  } catch {}
  $("#tlSnap").onchange = (e) => {
    try { localStorage.setItem("kb.grid", e.target.value); } catch {}
    TL?.setSnap(gridMode()); syncGridLabel(); e.target.blur();
  };
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
      else if ((k0 === "n" || k0 === "N") && !(e.ctrlKey || e.metaKey)) { e.preventDefault(); prSyncNow(); }
      return;
    }
    if (EAR && !(t && /^(INPUT|TEXTAREA)$/.test(t.tagName) && t.type !== "checkbox")) {   // R2: kulakla ayar modu
      const k1 = e.key;
      if (k1 === "ArrowLeft" || k1 === "ArrowRight") { e.preventDefault(); earAdjust((k1 === "ArrowRight" ? 1 : -1) * (e.shiftKey ? 10 : 1)); return; }
      if (k1 === "Enter") { e.preventDefault(); earSave(); return; }
      if (k1 === "Escape") { e.preventDefault(); earCancel(); return; }
      if (k1 === " ") { e.preventDefault(); if (t && t.tagName === "BUTTON") t.blur(); if (TL.isPlaying()) TL.stop(); else TL.play(EAR.loop.a, { loop: EAR.loop }); return; }
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
    else if (k === "Escape" && (TL.selection().size || TL.loopSelected())) { TL.clearSel(); TL.clearLoopSel(); setStatus("Seçim bırakıldı — ok tuşları artık çalma çizgisini kaydırır"); }
    else if (k === "ArrowLeft" || k === "ArrowRight") {
      // R1: secili klip(ler) > secili dongu > calma cizgisi. Sol/Sag = bir izgara, Shift = 10 ms, Ctrl+Shift = 1 ms
      e.preventDefault();
      const dir = k === "ArrowRight" ? 1 : -1;
      const mode = e.shiftKey && ctrl ? "1ms" : e.shiftKey ? "10ms" : "grid";
      const stepTxt = mode === "grid" ? `ızgara ${GRID_LBL[TL.effGrid()] || "10 ms"}` : mode.replace("ms", " ms");
      // oncelik: cetvelde az once tutulan dongu > secili klip(ler) > calma cizgisi (Esc: secimleri birak)
      if (TL.loopSelected()) {
        const t = TL.nudgeLoop(dir, mode);
        if (t !== null) { const p = TL.formatPos(t); setStatus(`Döngü ${TL.loopSelected() === "le" ? "sonu" : TL.loopSelected() === "ls" ? "başı" : "(taşı) başı"} ${p.time} · ${p.bbt} (${stepTxt})`); }
      } else if (TL.selection().size) {
        const t = TL.nudgeSelected(dir, mode);
        if (t !== null) { const p = TL.formatPos(t); setStatus(`Klip başı ${p.time} · ${p.bbt} (${stepTxt})`); }
      } else {
        const t = TL.nudgePlayhead(dir, mode);
        const p = TL.formatPos(t); setStatus(`Çalma ${p.time} · ${p.bbt} (${stepTxt})`);
      }
    }
    else if (!ctrl && !e.altKey && (k === "r" || k === "R")) { e.preventDefault(); recStart(); }
    else if (!ctrl && !e.altKey && (k === "l" || k === "L")) { e.preventDefault(); toggleLoopUi(); }
    else if (!ctrl && !e.altKey && (k === "m" || k === "M")) { e.preventDefault(); toggleMetro(); }
    else if (!ctrl && !e.altKey && (k === "c" || k === "C")) { e.preventDefault(); toggleCount(); }
    else if (!ctrl && !e.altKey && (k === "n" || k === "N") && PR.on) { e.preventDefault(); prSyncNow(); }
  });

  // ---------------- 1c: Soz paneli (baslik -> bolum, hece, kafiye rengi, satir zamani) ----------------
  // Kural: soz METNINE hicbir otomatik dokunus yok; yalniz analiz ve gosterim.
  let LYR_PY = { text: null, res: null };   // Python hece/kafiye sonucu (metin anahtarli onbellek)
  let LYR_REQ = 0;
  async function analyzeLyricsUI() {
    const txt = $("#lyrInput").value;
    if (PROJ) PROJ.lyrics = txt;
    const my = ++LYR_REQ;
    const r = await api()?.beat_lyrics_analyze?.(txt, PROJ?.bpm || 0).catch(() => null);
    if (my !== LYR_REQ) return;
    LYR_PY = { text: txt, res: r?.ok ? r : null };
    renderLyrics();
  }
  function lyricTimes() {
    if (!PROJ || !window.BeatLyrics) return [];
    const lt = PROJ.lyric_times || {};
    return BeatLyrics.lineTimes(PROJ.lyrics || "", PROJ.sections || [], PROJ.bpm || 120, lt.bars_per_line || 1, lt.anchors || [], 4,
      BeatLyrics.lyricStart(lt.start));
  }
  // ---- R3: "Sozler buradan baslar" isareti (lyric_times.start) ----
  /** Cetveldeki bayragin yeri: elle konduysa o, yoksa ilk satirin tahmini zamani. Soz yoksa null (bayrak yok). */
  function lyricFlagT() {
    if (!PROJ || !window.BeatLyrics || !String(PROJ.lyrics || "").trim()) return null;
    const st = BeatLyrics.lyricStart(PROJ.lyric_times?.start);
    if (st !== null) return st;
    // cetvel her karede cizilir: ilk satir zamanini girdiler degismedikce onbellekten ver
    const key = `${PROJ.lyrics.length}|${PROJ.bpm}|${JSON.stringify(PROJ.sections || [])}|${JSON.stringify(PROJ.lyric_times || {})}|${PROJ.lyrics.slice(0, 200)}`;
    if (FLAG_CACHE.key !== key) {
      const tm = lyricTimes();
      FLAG_CACHE = { key, t: tm.length ? Math.max(0, Number(tm.find((x) => x.n === 0)?.t ?? tm[0].t) || 0) : null };
    }
    return FLAG_CACHE.t;
  }
  let FLAG_CACHE = { key: "", t: null };
  let LS_BEFORE = null;   // surukleme basindaki anlik goruntu (tek geri al adimi)
  function setLyricStart(t, commit) {
    if (!PROJ || t === null || t === undefined) return;
    const v = BeatClips.r6(Math.max(0, Number(t) || 0));
    if (!commit) {                                  // surukleme: canli onizleme, geri al yiginina girmez
      if (LS_BEFORE === null) LS_BEFORE = snap();
      ensureLyricTimes().start = v;
      if (PR.on) { prCompute(); prUpdate(TL?.getPlayhead() || 0, true); }
      syncLyricStartUi();
      return;
    }
    const before = LS_BEFORE ?? snap();
    LS_BEFORE = null;
    ensureLyricTimes().start = v;
    if (snap() !== before) { pushUndo(before); scheduleSave(); }
    renderLyrics();
    TL?.drawRuler();
    const p = TL?.formatPos(v);
    const anc0 = (PROJ.lyric_times.anchors || []).some((a) => Math.trunc(Number(a.line)) === 0);
    setStatus(`Sözler ${p ? `${p.time} · ${p.bbt}` : fmtTime(v)}'den başlar${anc0 ? " — 1. satır elle sabit (⏱), o satırın senkronunu kaldırırsan bayrağa uyar" : ""}`);
  }
  function syncLyricStartUi() {
    const st = BeatLyrics?.lyricStart(PROJ?.lyric_times?.start);
    const p = st !== null && st !== undefined && TL ? TL.formatPos(st) : null;
    $("#lyrStartLbl").textContent = p ? `Başlangıç: ${p.time} · bar ${p.bbt}` : "Başlangıç: bölüm haritası / en baştan";
    $("#lyrStartClear").disabled = !p;
    const ft = lyricFlagT();
    $("#prStartHint").innerHTML = ft === null ? "Söz yok"
      : `Sözler <b>${esc(fmtTime(ft))}</b>'den başlar — ilk satırı sürükle (cetveldeki pembe <b>SÖZ</b> bayrağı) veya N ile o anı sabitle`;
  }
  function rhymeTail(text, col) {
    const m = /([0-9A-Za-zÇĞİÖŞÜçğıöşü]+)([^0-9A-Za-zÇĞİÖŞÜçğıöşü]*)$/.exec(text);
    if (!m || col == null) return esc(text);
    const i = m.index;
    return `${esc(text.slice(0, i))}<b class="kb-rhy" style="color:${col}">${esc(m[1])}</b>${esc(m[2])}`;
  }
  function renderLyrics() {
    if (!PROJ || !window.BeatLyrics) return;
    const txt = PROJ.lyrics || "";
    if (LYR_PY.text !== txt) { analyzeLyricsUI(); if (LYR_PY.text === null) return; }
    const py = LYR_PY.text === txt ? LYR_PY.res : null;
    const pyByN = new Map(((py && py.lines) || []).filter((l) => l.n >= 0).map((l) => [l.n, l]));
    const parsed = BeatLyrics.parseLyrics(txt);
    const secs = PROJ.sections || [];
    const owner = BeatLyrics.assignBlocks(parsed.blocks, secs);
    const times = lyricTimes();
    const tByN = new Map(times.map((x) => [x.n, x]));
    const barSec = 240 / (Number(PROJ.bpm) || 120);
    const lt = PROJ.lyric_times || {};
    $("#lyrBpl").value = String(lt.bars_per_line || 1);
    if (py) $("#lyrStats").textContent = `${py.total_lines} satır · ${py.total_syllables} hece · ${py.rhyme_groups} kafiye`;
    const rows = [];
    for (const ln of parsed.lines) {
      if (ln.kind === "header") {
        const k = owner[ln.block];
        const sc = k >= 0 ? secs[k] : null;
        const bplOpts = [["0", "genel"], ["0.5", "½ bar"], ["1", "1 bar"], ["2", "2 bar"], ["4", "4 bar"]]
          .map(([v, l]) => `<option value="${v}" ${String(sc?.bars_per_line || 0) === v ? "selected" : ""}>${l}</option>`).join("");
        rows.push(`<div class="kb-lyr-head ${sc ? "" : "none"}">
          <b>[${esc(ln.header || "?")}]</b>
          <span class="kb-lyr-map">${sc ? `→ ${esc(sc.name)} · ${Math.round(Number(sc.start) / barSec) + 1}. bar` : "→ eşleşen bölüm yok (önceki bloğun ardından akar)"}</span>
          ${sc ? `<select class="kb-sel" data-secbpl="${esc(sc.id)}" title="Bu bölümde satır başına bar">${bplOpts}</select>` : ""}
        </div>`);
      } else if (ln.kind === "line") {
        const p = pyByN.get(ln.n);
        const tm = tByN.get(ln.n);
        const col = p && p.color >= 0 ? RHYME_COLORS[p.color % RHYME_COLORS.length] : null;
        const barN = tm ? Math.floor(tm.t / barSec + 1e-6) + 1 : 0;
        rows.push(`<div class="kb-lyr-line" data-n="${ln.n}" title="${tm ? `${fmtTime(tm.t)} · tıkla: buraya git` : ""}">
          <span class="kb-syl" title="Hece">${p ? p.syllables : "·"}</span>
          <span class="kb-rhyme" style="background:${col || "rgba(157,107,255,.15)"}"></span>
          <span class="kb-lyr-bar kb-num ${tm?.anchored ? "anc" : ""}" title="${tm?.anchored ? "Elle sabitlendi" : "Tahmini bar"}">${barN ? barN + "." : "—"}</span>
          <span class="kb-lyr-txt">${rhymeTail(ln.text, col)}</span>
          <button type="button" class="kb-lyr-sync ${tm?.anchored ? "on" : ""}" data-sync="${ln.n}" title="${tm?.anchored ? "Senkronu kaldır" : "Bu satırı çalma konumuna sabitle (şimdi)"}">${tm?.anchored ? "×" : "⏱"}</button>
        </div>`);
      }
    }
    $("#lyrBars").innerHTML = rows.join("") || `<div class="kb-mut kb-lyr-empty">Sözler burada satır satır görünür: hece, bar konumu ve kafiye rengiyle.</div>`;
    if (PR.on) { prCompute(); prUpdate(TL?.getPlayhead() || 0, true); }
    syncLyricStartUi();
    TL?.drawRuler();
  }
  /** Gecikmesiz duzenleme (calmayi yeniden baslatmaz): soz zamanlari ve bolum ayarlari icin. Geri alinabilir. */
  function quietEdit(label, fn) {
    if (!PROJ) return;
    const before = snap();
    fn();
    if (snap() === before) return;
    pushUndo(before);
    scheduleSave();
    renderLyrics();
    TL?.render();
    if (label) setStatus(label);
  }
  function ensureLyricTimes() {
    if (!PROJ.lyric_times || typeof PROJ.lyric_times !== "object") PROJ.lyric_times = { bars_per_line: 1, anchors: [] };
    if (!Array.isArray(PROJ.lyric_times.anchors)) PROJ.lyric_times.anchors = [];
    return PROJ.lyric_times;
  }
  function sungTexts() {
    return BeatLyrics.parseLyrics(PROJ?.lyrics || "").lines.filter((x) => x.kind === "line").map((x) => x.text);
  }
  function syncLineAt(n, t) {
    const texts = sungTexts();
    if (!(n >= 0 && n < texts.length)) return;
    quietEdit(`Satır ${n + 1} → ${fmtTime(t)} (sonrakiler kaydı)`, () => {
      const lt = ensureLyricTimes();
      lt.anchors = BeatLyrics.syncLine(lt.anchors, n, t, texts[n]);
    });
  }
  $("#lyrBars").addEventListener("click", (e) => {
    if (!PROJ) return;
    const sb = e.target.closest("[data-sync]");
    if (sb) {
      const n = +sb.dataset.sync;
      if (sb.classList.contains("on")) quietEdit(`Satır ${n + 1} senkronu kaldırıldı`, () => { const lt = ensureLyricTimes(); lt.anchors = BeatLyrics.unsyncLine(lt.anchors, n); });
      else syncLineAt(n, TL ? TL.getPlayhead() : 0);
      return;
    }
    const row = e.target.closest(".kb-lyr-line[data-n]");
    if (row && TL) {
      const tm = lyricTimes().find((x) => x.n === +row.dataset.n);
      if (tm) { TL.setPlayhead(tm.t); TL.ensureVisible(tm.t); PR.sel = -1; }
    }
  });
  $("#lyrBars").addEventListener("change", (e) => {
    const el = e.target;
    if (!el.dataset.secbpl || !PROJ) return;
    const v = +el.value || 0;
    quietEdit(v ? `Bölüm satır başına ${v} bar` : "Bölüm genel satır ayarını kullanıyor", () => {
      const sc = (PROJ.sections || []).find((x) => x.id === el.dataset.secbpl);
      if (!sc) return;
      if (v > 0) sc.bars_per_line = v; else delete sc.bars_per_line;
    });
    el.blur();
  });
  $("#lyrBpl").onchange = (e) => {
    const v = +e.target.value || 1;
    quietEdit(`Satır başına ${v} bar`, () => { ensureLyricTimes().bars_per_line = v; });
    e.target.blur();
  };
  $("#lyrStartHere").onclick = (e) => { e.currentTarget.blur(); if (TL) setLyricStart(TL.getPlayhead(), true); };
  $("#lyrStartClear").onclick = (e) => {
    e.currentTarget.blur();
    if (!PROJ?.lyric_times || PROJ.lyric_times.start == null) return;
    quietEdit("Söz başlangıç işareti kaldırıldı (bölüm haritası / en baştan)", () => { delete ensureLyricTimes().start; });
  };
  $("#lyrFind").onclick = async (e) => {
    const btn = e.currentTarget;
    btn.blur();
    if (!PROJ) return;
    btn.disabled = true;
    setStatus("Vokalde ilk sesli an aranıyor…");
    try {
      await flushSave();
      const r = await runJob("beat_find_lyric_start", [PROJ.id]);
      if (r?.ok) {
        setLyricStart(r.start, true);
        setStatus(r.source === "vocal" ? `Sözler vokalin ilk sesli anından başlıyor: ${fmtTime(r.start)}`
          : `Vokal bulunamadı — beat'in ilk Verse bölümüne kondu: ${fmtTime(r.start)}`);
        TL?.ensureVisible(r.start);
      } else setStatus("Vokal kaydı da Verse bölümü de yok — bayrağı cetvelde elle sürükle (veya \"Analiz et\" ile bölüm haritası çıkar).");
    } finally { btn.disabled = false; }
  };
  $("#lyrResetSync").onclick = () => {
    if (!PROJ || !(PROJ.lyric_times?.anchors || []).length) { setStatus("Elle senkron yok."); return; }
    quietEdit("Söz senkronları sıfırlandı (tahmini zamanlar)", () => { ensureLyricTimes().anchors = []; });
  };

  // ---------------- 1c: Teleprompter ----------------
  const PR = { on: false, manual: false, sel: -1, last: null, times: [], texts: [] };
  function prCompute() {
    if (!PROJ || !window.BeatLyrics) return;
    PR.times = lyricTimes();
    PR.texts = sungTexts();
    PR.last = null;
  }
  function prShow(on) {
    PR.on = !!on && !!window.BeatLyrics;
    $("#prompter").hidden = !PR.on;
    $("#prompter").classList.toggle("rec", !!RECST);
    $("#lyrPrompt").classList.toggle("on", PR.manual);
    if (PR.on) { prCompute(); prUpdate(TL ? TL.getPlayhead() : 0, true); }
  }
  function prUpdate(t, force) {
    if (!PR.on) return;
    const a = BeatLyrics.activeLine(PR.times, t);
    const key = `${a}|${PR.sel}`;
    if (key === PR.last && !force) return;
    PR.last = key;
    const N = PR.texts.length;
    if (!N) {
      $("#prLines").innerHTML = `<div class="kb-pr-l cur kb-pr-empty">Söz yok — "Söz &amp; Kafiye" sekmesine yaz ya da yapıştır.</div>`;
      return;
    }
    const tByN = new Map(PR.times.map((x) => [x.n, x.t]));
    const rows = [[a - 1, "prev"], [a, "cur"], [a + 1, "next"], [a + 2, "next2"]];
    $("#prLines").innerHTML = rows.map(([n, cls]) => {
      if (n < 0 || n >= N) return `<div class="kb-pr-l ${cls} blank">${cls === "cur" && a < 0 ? "…" : "&nbsp;"}</div>`;
      const anc = PR.times.find((x) => x.n === n)?.anchored;
      return `<div class="kb-pr-l ${cls} ${n === PR.sel ? "sel" : ""}" data-n="${n}" title="${fmtTime(tByN.get(n) || 0)}${anc ? " · elle sabit" : ""} — tıkla: seç">${esc(PR.texts[n])}${anc ? `<i class="kb-pr-anc">⏱</i>` : ""}</div>`;
    }).join("");
  }
  function prSyncNow() {
    if (!PROJ || !TL) return;
    if (!PR.times.length) prCompute();
    const t = TL.getPlayhead();
    const a = BeatLyrics.activeLine(PR.times, t);
    // secili satir yoksa: siradaki satir "simdi" basliyor (sarkici ona girdi)
    const n = PR.sel >= 0 ? PR.sel : Math.min(PR.texts.length - 1, a + 1);
    if (n < 0) return;
    PR.sel = -1;
    syncLineAt(n, t);
  }
  $("#prLines").addEventListener("click", (e) => {
    const row = e.target.closest(".kb-pr-l[data-n]");
    if (!row) return;
    const n = +row.dataset.n;
    PR.sel = PR.sel === n ? -1 : n;
    prUpdate(TL ? TL.getPlayhead() : 0, true);
  });
  $("#prNow").onclick = (e) => { e.currentTarget.blur(); prSyncNow(); };
  $("#prClose").onclick = () => { PR.manual = false; prShow(false); };
  $("#lyrPrompt").onclick = (e) => { e.currentTarget.blur(); PR.manual = !PR.manual; prShow(PR.manual || !!RECST); };

  // ---------------- 1c: Beat analizi + bolum haritasi ----------------
  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
  async function runJob(name, args, onTick) {
    const A = api();
    if (!A?.job_start) return A?.[name] ? A[name](...args) : { ok: false, error: "no_api" };
    const j = await A.job_start(name, args).catch(() => null);
    if (!j?.ok) return { ok: false, error: j?.error || "job_start" };
    for (;;) {
      await sleep(350);
      try { await onTick?.(); } catch {}
      const r = await A.job_result(j.job).catch(() => null);
      if (r?.state === "done") return r.result;
      if (!r || r.state === "lost") return { ok: false, error: "lost" };
    }
  }
  let ANALYZING = false;
  function secProg(on, txt, pct) {
    $("#secProg").hidden = !on;
    $("#secAnalyze").disabled = !!on;
    if (on) { $("#secProgTxt").textContent = txt || "Analiz ediliyor…"; $("#secProgBar").style.width = Math.max(4, Math.min(100, pct || 0)) + "%"; }
  }
  async function analyzeSections(auto = false) {
    if (!PROJ || ANALYZING) return;
    const beatTr = (PROJ.tracks || []).find((t) => t.role === "beat");
    if (!beatTr || !(beatTr.clips || []).length) { if (!auto) setStatus("Önce Beat kanalına bir ses ekle (📂 Ses)."); return; }
    ANALYZING = true;
    secProg(true, "Beat okunuyor…", 3);
    const pid = PROJ.id;
    try {
      await flushSave();
      const r = await runJob("beat_analyze_sections", [pid], async () => {
        const p = await api()?.beat_analysis_progress?.().catch(() => null);
        if (p && p.pid === pid && p.running) secProg(true, `${p.stage}…`, p.pct);
      });
      if (!PROJ || PROJ.id !== pid) return;
      if (!r?.ok) {
        const msg = { no_beat: "Beat kanalında duyulan klip yok.", file_missing: "Beat dosyası bulunamadı.", too_short: "Beat bölüm çıkaramayacak kadar kısa." }[r?.error]
          || ("Analiz hatası: " + (r?.error || "?"));
        setStatus(msg);
        return;
      }
      const secs = (r.sections || []).map((x) => ({ id: x.id, name: x.name, start: x.start, end: x.end }));
      edit(`✓ Analiz: ${r.bpm > 0 ? r.bpm + " BPM · " : ""}${r.key || "ton ?"} · ${secs.length} bölüm (tahmini — çift tıkla adlandır)`, () => {
        if (r.bpm > 0) PROJ.bpm = r.bpm;
        if (r.key) PROJ.key = r.key;
        PROJ.sections = secs;
      });
    } finally {
      ANALYZING = false;
      secProg(false);
    }
  }
  function sectionToLoop(sec) {
    if (!sec || !TL || RECST) return;
    TL.setLoop({ start: Number(sec.start), end: Number(sec.end), on: true });
    TL.setPlayhead(Number(sec.start), true);
    TL.ensureVisible(Number(sec.start));
    setStatus(`Döngü: ${sec.name} (${fmtTime(Number(sec.start))} → ${fmtTime(Number(sec.end))}) — L ile kapat`);
  }
  $("#secAnalyze").onclick = (e) => { e.currentTarget.blur(); analyzeSections(false); };

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
  let LVL_TIMER = 0, LVL_BUSY = false, LVL_PEAK = 0, CLIP_UNTIL = 0;
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
    // 1c: kayit modunda teleprompter kendiliginden acilir (soz varsa)
    if (String(PROJ?.lyrics || "").trim()) { PR.sel = -1; prShow(true); }
    CLIP_UNTIL = 0; $("#hudWarn").hidden = true;
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
    $("#hudWarn").hidden = true;
    prShow(PR.manual);
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
      // 1c: canli patlama uyarisi (tepe -1 dBFS ustu) 2 sn ekranda kalir
      if (db > -1 || st.clip) CLIP_UNTIL = Date.now() + 2000;
      $("#hudWarn").hidden = Date.now() >= CLIP_UNTIL;
      $("#micVuFill").style.width = pct + "%";
    } finally { LVL_BUSY = false; }
  }

  async function recStart(kind = "auto") {
    if (RECST || !PROJ || !TL) return;
    if (MICTEST) { setStatus("Mikrofon testi sürüyor — bitince kayda başlayabilirsin."); return; }
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

  // ---- 1c: Mikrofon asistani + mikrofon yeri asistani ----
  let MICTEST = false;
  const RATE_CLS = { "iyi": "ok", "kuru": "ok", "orta": "mid", "kısık": "mid", "kötü": "bad", "patlıyor": "bad", "yankılı": "bad" };
  const chip = (t) => `<span class="kb-chip ${RATE_CLS[t] || ""}">${esc(t)}</span>`;
  const dbs = (v) => `${Number(v).toFixed(1)} dBFS`;
  function renderMicCard(r) {
    const card = $("#micCard");
    if (!r?.ok) { card.hidden = true; return; }
    const m = r.metrics || {}, rv = r.reverb || {};
    const tips = [...(m.tips || []), ...(r.placement || [])];
    const when = r.t ? new Date(r.t * 1000).toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }) : "";
    card.innerHTML = `
      <div class="kb-mic-row"><span>Gürültü tabanı</span><b class="kb-num">${dbs(m.noise_db)}</b>${chip(m.noise_rating)}</div>
      <div class="kb-mic-row"><span>Tepe</span><b class="kb-num">${dbs(m.peak_db)}</b>${chip(m.clipping ? "patlıyor" : "iyi")}</div>
      <div class="kb-mic-row"><span>Ortalama</span><b class="kb-num">${dbs(m.avg_db)}</b>${chip(m.too_quiet ? "kısık" : "iyi")}</div>
      <div class="kb-mic-row"><span>Sinyal / gürültü</span><b class="kb-num">${Number(m.snr_db).toFixed(1)} dB</b>${chip(m.snr_rating)}</div>
      <div class="kb-mic-row"><span>Yankılılık <i>(tahmini)</i></span><b class="kb-num">${rv.ok ? `≈${Number(rv.rt60).toFixed(2)} sn · ${rv.score}/100` : "—"}</b>${rv.ok ? chip(rv.label) : ""}</div>
      <div class="kb-mic-tips"><b>Öneriler</b><ul>${tips.map((t) => `<li>${esc(t)}</li>`).join("")}</ul></div>
      <small class="kb-mut">${when ? when + " · " : ""}Ölçümler kabadır (oda yankısı özellikle tahmin); kesin değer değildir.</small>`;
    card.hidden = false;
  }
  try { renderMicCard(JSON.parse(localStorage.getItem("kb.mictest") || "null")); } catch {}
  $("#micTestBtn").onclick = async () => {
    if (MICTEST || RECST) return;
    MICTEST = true;
    const btn = $("#micTestBtn");
    btn.disabled = true;
    TL?.stop();
    $("#micTestRun").hidden = false;
    $("#micTestPhase").textContent = "1/2 · Sessiz kal — ortam gürültüsü ölçülüyor…";
    const sample = sungTexts().slice(0, 2).join(" / ") || "Gece çöker şehrin üstüne, sokak lambaları şahit her sözüme";
    try {
      const r = await runJob("beat_mic_test", [+$("#micSel").value], async () => {
        const st = await api()?.beat_mic_test_status?.().catch(() => null);
        if (!st?.running) return;
        const left = Math.ceil(Number(st.remaining) || 0);
        const speak = st.phase === "speech";
        $("#micTestPhase").textContent = speak ? `2/2 · Şimdi normal sesinle oku (${left})` : `1/2 · Sessiz kal — ortam gürültüsü (${left})`;
        $("#micTestPhase").classList.toggle("speak", speak);
        $("#micTestRead").hidden = !speak;
        $("#micTestRead").textContent = speak ? `“${sample}”` : "";
        $("#micTestVu").style.width = Math.max(0, Math.min(100, ((Number(st.level_db) + 60) / 60) * 100)) + "%";
      });
      if (r?.ok) {
        renderMicCard(r);
        try { localStorage.setItem("kb.mictest", JSON.stringify(r)); } catch {}
        setStatus("Mikrofon testi tamam — sonuç kartı Kabin sekmesinde.");
      } else {
        const msg = { sounddevice_missing: "Ses aygıtı kütüphanesi (sounddevice) yok.", busy: "Mikrofon meşgul (kayıt ya da başka test sürüyor).",
          too_short: "Test kaydı çok kısa kaldı." }[r?.error] || ("Mikrofon testi hatası: " + (r?.error || "?"));
        setStatus(msg);
      }
    } finally {
      MICTEST = false;
      btn.disabled = false;
      $("#micTestRun").hidden = true;
      $("#micTestPhase").classList.remove("speak");
      $("#micTestVu").style.width = "0%";
    }
  };

  // ---- Revize R2: kalici kayit gecikmesi (genel ayar; proje degeri ayrica girilmisse o) ----
  let GLOBAL_LAT = 0;
  const clampLat = (v) => Math.max(-500, Math.min(500, Math.round((Number(v) || 0) * 10) / 10));
  function latEffective() { return BeatTransport.effectiveLatencyMs(PROJ?.latency_ms, GLOBAL_LAT); }
  function syncLatUi() {
    const e = latEffective();
    const proj = e.source === "project";
    $("#latCur").textContent = `${Math.round(e.ms * 10) / 10} ms · ${proj ? "proje" : "genel"}`;
    if (document.activeElement !== $("#latInput")) $("#latInput").value = String(e.ms);
    $("#latProjOnly").checked = proj;
    $("#latSource").textContent = proj
      ? `Bu projeye özel değer etkin (genel ayar ${GLOBAL_LAT} ms bu projede kullanılmıyor). Her yeni kayda uygulanır.`
      : "Genel ayar etkin — her kayda uygulanır, uygulama yeniden açılınca da durur.";
  }
  async function loadGlobalLat() {
    const r = await api()?.beat_latency_get?.().catch(() => null);
    if (r?.ok) GLOBAL_LAT = Number(r.global_ms) || 0;
    syncLatUi();
  }
  let LAT_SAVE_T = 0;
  /** Etkin gecikmeyi ayarlar: proje ozel ise proje (geri alinabilir), degilse genel ayar (kalici, 300 ms sonra yazilir). */
  function setLatency(v, why) {
    v = clampLat(v);
    if (latEffective().source === "project") {
      if (v === 0) { setStatus("Projeye özel değer 0 olamaz (0 = genel ayar) — kutuyu kaldır."); syncLatUi(); return; }
      edit(`Proje kayıt gecikmesi: ${v} ms${why ? " · " + why : ""}`, () => { PROJ.latency_ms = v; });
    } else {
      GLOBAL_LAT = v;
      clearTimeout(LAT_SAVE_T);
      LAT_SAVE_T = setTimeout(async () => {
        const r = await api()?.beat_latency_set?.(v).catch(() => null);
        if (r?.ok) { GLOBAL_LAT = Number(r.global_ms) || 0; setStatus(`Kayıt gecikmesi ${GLOBAL_LAT} ms (genel ayar, kalıcı)${why ? " · " + why : ""}`); }
        else setStatus("⚠ Gecikme ayarı yazılamadı: " + (r?.error || "?"));
        syncLatUi();
      }, 300);
    }
    syncLatUi();
  }
  $("#latInput").addEventListener("change", (e) => { setLatency(e.target.value); e.target.blur(); });
  $("#latInput").addEventListener("keydown", (e) => { if (e.key === "Enter") e.target.blur(); });
  for (const [id, d] of [["latMinus10", -10], ["latMinus1", -1], ["latPlus1", 1], ["latPlus10", 10]]) {
    $("#" + id).onclick = (e) => { e.currentTarget.blur(); setLatency(latEffective().ms + d); };
  }
  $("#latProjOnly").onchange = (e) => {
    e.target.blur();
    if (!PROJ) return;
    if (e.target.checked) {
      const v = clampLat(GLOBAL_LAT) || 1;     // 0 "genel" demek: ozel deger en az 1 ms
      edit(`Bu proje kendi gecikmesini kullanıyor: ${v} ms`, () => { PROJ.latency_ms = v; });
    } else edit(`Bu proje genel gecikme ayarını kullanıyor (${GLOBAL_LAT} ms)`, () => { PROJ.latency_ms = 0; });
    syncLatUi();
  };

  // ---- Tik olcumu: tik ARAYUZDEN (kullanicinin duydugu cikis, Web Audio) calar, Python yalniz kaydeder ----
  function probeBuffer(ac, P) {
    const sr = ac.sampleRate;
    const n = Math.round(P.dur * sr), r = Math.max(1, Math.round(P.ramp * sr));
    const total = Math.round(((P.count - 1) * P.spacing + P.dur + 0.05) * sr);
    const buf = ac.createBuffer(1, total, sr);
    const d = buf.getChannelData(0);
    const k = (P.f1 - P.f0) / P.dur;
    for (let i = 0; i < n; i++) {
      const t = i / sr;
      let w = 1;
      if (i < r) w = 0.5 - 0.5 * Math.cos(Math.PI * i / r);
      else if (i >= n - r) w = 0.5 - 0.5 * Math.cos(Math.PI * (n - 1 - i) / r);
      const v = Math.sin(2 * Math.PI * (P.f0 * t + 0.5 * k * t * t)) * w * P.amp;
      for (let c = 0; c < P.count; c++) { const j = Math.round(c * P.spacing * sr) + i; if (j < total) d[j] = v; }
    }
    return buf;
  }
  async function measureLatencyWeb() {
    const A = api();
    if (!A?.beat_latency_listen_start || !TL) return { ok: false, error: "no_api" };
    const P = await A.beat_latency_probe().catch(() => null);
    if (!P?.ok) return { ok: false, error: "no_api" };
    const st = await A.beat_latency_listen_start(+$("#micSel").value).catch((e) => ({ ok: false, error: String(e) }));
    if (!st?.ok) return st || { ok: false, error: "mic" };
    try {
      for (let i = 0; i < 20; i++) { const r = await A.beat_latency_listen_ready().catch(() => null); if (r?.ready) break; await sleep(100); }
      const ac = TL.audioCtx();
      if (ac.state !== "running") await ac.resume();
      const src = ac.createBufferSource();
      src.buffer = probeBuffer(ac, P);
      src.connect(ac.destination);
      await sleep(300);                                 // mikrofon akisi otursun
      const when = ac.currentTime + 0.25;
      const wall = Date.now() + (when - ac.currentTime) * 1000;   // 1b kayit capasiyla ayni saat eslemesi
      src.start(when);
      await sleep(250 + src.buffer.duration * 1000 + 600);
      return await A.beat_latency_listen_stop(wall / 1000);
    } catch (e) {
      await A.beat_latency_listen_stop(0).catch(() => {});
      return { ok: false, error: String(e?.message || e).slice(0, 120) };
    }
  }
  function latErrorText(r) {
    const tail = " Olmazsa yukarıdaki sayıyı elle gir ya da 🎧 Kulakla ayarla'yı kullan.";
    if (r?.error === "no_signal") {
      if (r.reason === "silent_device") return "Mikrofondan hiç veri gelmedi — aygıt başka bir uygulamada açık olabilir ya da Windows mikrofon izni kapalı (Ayarlar › Gizlilik › Mikrofon › masaüstü uygulamaları)." + tail;
      if (r.reason === "quiet" || (r.peak != null && r.peak < 0.01))
        return `Mikrofon neredeyse hiç ses almadı (tepe ${Math.round((r.peak || 0) * 1000) / 10}%). Dene: 1) üstteki listeden doğru mikrofonu seç, 2) Windows giriş seviyesini yükselt, 3) kulaklığı kulağından çıkarıp hoparlörünü mikrofona daya ve sistem sesini %50+ yap.` + tail;
      return `Ses geldi ama 5 tık seçilemedi (güven düşük, oran ${r.ratio ?? "?"}). Ortamı sessizleştir, kulaklık hoparlörünü mikrofona tam daya; tıkları hiç duymadıysan Kami'nin sesi başka çıkıştan gidiyor olabilir — Windows ses çıkışını kulaklık yap ya da aşağıdaki "Windows varsayılan çıkışıyla dene"ye bas.` + tail;
    }
    return ({ sounddevice_missing: "Ses aygıtı kütüphanesi (sounddevice) yok.", already_recording: "Kayıt sürerken ölçülemez — önce kaydı bitir.",
      clock: "Saat eşlemesi tutmadı (mikrofon geç açıldı) — bir kez daha dene.", no_api: "Arayüz köprüsü hazır değil." }[r?.error]
      || ("Hata: " + (r?.error || "?"))) + tail;
  }
  function showLatResult(r) {
    $("#latMeasurePy").hidden = !!r?.ok;
    if (r?.ok) {
      LAT_RESULT = Number(r.latency_ms) || 0;
      const conf = Math.round((Number(r.confidence) || 0) * 100);
      $("#latRes").textContent = `Ölçüm: ${LAT_RESULT.toFixed(1)} ms · güven %${conf}${r.spread_ms != null ? ` · sapma ${r.spread_ms} ms` : ""} — "Uygula" ile kaydet`;
      $("#latApply").disabled = false;
    } else $("#latRes").textContent = latErrorText(r);
  }
  $("#latMeasure").onclick = async () => {
    const btn = $("#latMeasure");
    btn.disabled = true;
    $("#latRes").textContent = "Ölçülüyor… 5 tık çalınacak (kulaklık hoparlörü mikrofona dayalı olsun)";
    LAT_RESULT = null; $("#latApply").disabled = true;
    try { TL?.stop(); showLatResult(await measureLatencyWeb()); } finally { btn.disabled = false; }
  };
  $("#latMeasurePy").onclick = async () => {
    const btn = $("#latMeasurePy");
    btn.disabled = true;
    $("#latRes").textContent = "Ölçülüyor… (Windows varsayılan çıkışı, 2 deneme)";
    try { TL?.stop(); const r = await api()?.beat_measure_latency?.(+$("#micSel").value, -1); showLatResult(r); if (!r?.ok) $("#latMeasurePy").hidden = false; }
    finally { btn.disabled = false; }
  };
  $("#latApply").onclick = () => {
    if (LAT_RESULT == null) return;
    setLatency(LAT_RESULT, "ölçümden");
    $("#latApply").disabled = true;
  };

  // ---- Kulakla ayarla: son kayit beat'le dongude; +-ms anlik duyulur, Kaydet genel ayara yazar ----
  let EAR = null;
  const isRecPath = (p) => /(^|[\\/])(clean_)?pc_mic_/i.test(String(p || ""));
  function lastRecordedClip() {
    let best = null;
    for (const tr of PROJ?.tracks || []) {
      if (tr.role === "beat") continue;
      const created = new Map((tr.takes || []).map((t) => [t.id, Number(t.created_at) || 0]));
      for (const c of BeatClips.stackView(tr.clips || [])) {
        if (!isRecPath(c.path) || c.muted) continue;
        const ts = created.get(c.take_id) || 0;
        if (!best || ts > best.ts || (ts === best.ts && Number(c.start) > Number(best.clip.start))) best = { tr, clip: c, ts };
      }
    }
    if (!best && TL) {   // kayit yolu taninmadiysa: secili klip
      const h = [...TL.selection()].map((id) => TL.findClip(id)).find(Boolean);
      if (h && h.tr.role !== "beat") best = { tr: h.tr, clip: h.clip, ts: 0 };
    }
    return best;
  }
  function earMembers() {
    const tr = (PROJ.tracks || []).find((t) => t.id === EAR.trId);
    if (!tr) return [];
    const c = (tr.clips || []).find((x) => x.id === EAR.clipId);
    if (!c) return [];
    return c.stack_id ? (tr.clips || []).filter((x) => x.stack_id === c.stack_id) : [c];
  }
  function earApplyPreview() {
    for (const c of earMembers()) c.start = BeatClips.r6(Math.max(0, (EAR.orig.get(c.id) ?? c.start) - EAR.delta / 1000));
    const lat = clampLat(EAR.base + EAR.delta);
    $("#earVal").textContent = `${lat} ms`;
    $("#earInfo").textContent = `${EAR.delta > 0 ? "+" : ""}${Math.round(EAR.delta * 10) / 10} ms fark · klip ${EAR.delta >= 0 ? "erkene" : "geçe"} kaydı`;
    TL.render();
    if (TL.isPlaying()) TL.play(TL.getPlayhead(), { loop: EAR.loop });
  }
  function earAdjust(d) { if (!EAR) return; EAR.delta = clampLat(EAR.base + EAR.delta + d) - EAR.base; earApplyPreview(); }
  function earRestore() { for (const c of earMembers()) if (EAR.orig.has(c.id)) c.start = EAR.orig.get(c.id); }
  function earEnd() {
    TL?.stop();
    $("#earBar").hidden = true;
    $("#latEar").disabled = false;
    SAVE_LOCK = Math.max(0, SAVE_LOCK - 1);
    EAR = null;
    TL?.render();
  }
  $("#latEar").onclick = async (e) => {
    e.currentTarget.blur();
    if (!PROJ || !TL || EAR || RECST) return;
    const h = lastRecordedClip();
    if (!h) { setStatus("Önce bir kayıt al (ya da vokal kanalında bir klip seç) — kulakla ayar son kaydın üstünde yapılır."); return; }
    const [s0, e0] = BeatClips.clipBounds(h.clip);
    const bar = 240 / (Number(PROJ.bpm) || 120);
    EAR = { trId: h.tr.id, clipId: h.clip.id, base: latEffective().ms, delta: 0, orig: new Map(), loop: { a: s0, b: Math.min(e0, s0 + 4 * bar) } };
    for (const c of earMembers()) EAR.orig.set(c.id, c.start);
    if (EAR.loop.b - EAR.loop.a < 0.5) EAR.loop.b = EAR.loop.a + Math.min(4 * bar, Math.max(0.5, e0 - s0));
    SAVE_LOCK++;
    $("#earBar").hidden = false;
    $("#latEar").disabled = true;
    earApplyPreview();
    TL.ensureVisible(EAR.loop.a);
    const ok = await TL.play(EAR.loop.a, { loop: EAR.loop });
    if (ok === false) setStatus("Ses motoru açılamadı — Boşluk ile tekrar dene.");
    else setStatus("🎧 Dinle: ses vuruşun gerisinde kalıyorsa + , önündeyse − ; ←/→ (Shift: 10 ms), Enter: kaydet, Esc: vazgeç");
  };
  $("#earBar").addEventListener("click", (e) => { const b = e.target.closest("[data-ear]"); if (b) { b.blur(); earAdjust(+b.dataset.ear); } });
  async function earSave() {
    if (!EAR) return;
    const d = EAR.delta, lat = clampLat(EAR.base + d), fixAll = $("#earFixAll").checked;
    const projOwn = latEffective().source === "project";
    earRestore();
    const before = snap();
    if (fixAll && Math.abs(d) > 1e-9) {
      for (const tr of PROJ.tracks || []) {
        if (tr.role === "beat") continue;
        for (const c of tr.clips || []) {
          if (isRecPath(c.path) || EAR.orig.has(c.id)) c.start = BeatClips.r6(Math.max(0, Number(c.start) - d / 1000));
        }
      }
    }
    if (projOwn) PROJ.latency_ms = lat || 1;
    earEnd();
    commitFrom(fixAll && d ? `Gecikme ${lat} ms · kayıt klipleri ${Math.abs(d)} ms ${d > 0 ? "erkene" : "geçe"} kaydı` : `Gecikme ${lat} ms`, before);
    const r = await api()?.beat_latency_set?.(lat).catch(() => null);
    if (r?.ok) GLOBAL_LAT = Number(r.global_ms) || 0;
    syncLatUi();
    setStatus(`✓ Kayıt gecikmesi ${lat} ms kaydedildi (genel ayar${projOwn ? " + bu proje" : ""}) — yeni kayıtlara uygulanır${fixAll && d ? "; mevcut kayıt klipleri düzeltildi (Ctrl+Z ile geri al)" : ""}`);
  }
  function earCancel() { if (!EAR) return; earRestore(); earEnd(); setStatus("Kulakla ayar iptal — hiçbir şey değişmedi."); }
  $("#earSave").onclick = (e) => { e.currentTarget.blur(); earSave(); };
  $("#earCancel").onclick = (e) => { e.currentTarget.blur(); earCancel(); };

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
