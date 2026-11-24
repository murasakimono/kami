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
  // ---- Revize 4: efekt duzenleme seviyesi + parametre paneli + efektli onizleme ----
  let FX_LEVEL = "track";     // "track" | "clip"
  let FX_OPEN = null;         // acik parametre paneli: { level, tid, cid, idx }
  let PREV = null;            // BeatFx.createPreview
  let CLEAN = null;           // 2b: BeatClean (Temizle paneli)
  // ---- Asama 1d/1e ----
  let LIB = null;             // BeatLibrary (beat rafi + fikirler)
  let ALIGN = null;           // bekleyen hizalama onerisi { tid, cid, clips, before, label }
  const PROTECTED_TRACKS = new Set(["beat", "vocal1"]);
  const LAYER_LBL = { double: "Double", adlib: "Adlib", chant: "Chant" };
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
    if (window.BeatFx && Object.keys(BeatFx.schema()).length) return BeatFx.label(fx);
    if (fx?.name) return fx.name;
    const map = {
      highpass: "Highpass", lowpass: "Lowpass", peak: "Parametric EQ",
      compressor: "Compressor", deesser: "De-Esser", distortion: "Saturator",
      delay: "Delay", reverb: "Reverb", limiter: "Limiter", noisegate: "Noise Gate", gain: "Gain",
    };
    return map[String(fx?.type || "").toLowerCase()] || (fx?.type || "FX");
  }

  function fxParamSummary(fx) {
    if (window.BeatFx && Object.keys(BeatFx.schema()).length) return BeatFx.summary(fx);
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
    const fs = await api()?.beat_fx_schema?.().catch(() => null);
    if (fs?.ok && window.BeatFx) BeatFx.setSchema(fs);
    fillFxSelects();
    initListen();
    loadStyles();
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
    initLibrary();
  }

  /** 1e: beat rafi + fikir rafi paneli. */
  function initLibrary() {
    if (!window.BeatLibrary || LIB) return;
    LIB = BeatLibrary.init({
      api, $, esc, getProj: () => PROJ, serverMutate, setStatus, playPath, drawWaveform, runJob,
      playhead: () => (TL ? TL.getPlayhead() : 0),
      selTrackId: () => recTrackId(),
      micId: () => +$("#micSel").value,
      isRecording: () => !!RECST,
      lyricLines: () => (window.BeatLyrics ? BeatLyrics.parseLyrics(PROJ?.lyrics || "").lines.filter((l) => l.kind === "line").map((l) => ({ n: l.n, text: l.text })) : []),
      onLinksChanged: () => renderLyrics(),
      onBeatAdded: () => { if (!(PROJ?.sections || []).length) analyzeSections(true); },
    });
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
    syncReference();
    refreshAutoBuses();
    if (!opts.keepView) { TL?.setPlayhead(0, false); TL?.fit(); }
    if (r.recovered) setStatus("⚠ Proje dosyası bozuktu — son otomatik kayıttan kurtarıldı.");
    hideAlign();
    LIB?.refreshIdeas();
    return true;
  }

  /** 2b: varsayilan bus'lar ilk kez kurulu eklentilere gore (Supermassive / MDelay) yenilenir; ses/mute korunur. */
  async function refreshAutoBuses() {
    if (!PROJ?.buses_auto || !api()?.beat_buses_default) return;
    const pid = PROJ.id;
    const r = await api().beat_buses_default(Number(PROJ.bpm) || 120).catch(() => null);
    if (!r?.ok || !PROJ || PROJ.id !== pid) return;
    const old = new Map((PROJ.buses || []).map((b) => [b.id, b]));
    PROJ.buses = r.buses.map((b) => Object.assign(b, old.has(b.id) ? { volume_db: old.get(b.id).volume_db ?? 0, mute: !!old.get(b.id).mute } : {}));
    delete PROJ.buses_auto;
    renderProject();
    scheduleSave();
  }

  function selTrack() {
    const tracks = PROJ?.tracks || [];
    return tracks.find((x) => x.id === SEL_TID) || tracks.find((x) => x.role === "vocal") || tracks[0] || null;
  }

  // ---------------- Geri al / yinele + otomatik kayit ----------------
  // 1c: bolum haritasi, soz zamanlari ve analizden gelen BPM/ton da geri al kapsaminda
  const snap = () => JSON.stringify({ tracks: PROJ?.tracks || [], latency_ms: PROJ?.latency_ms || 0,
    sections: PROJ?.sections || [], lyric_times: PROJ?.lyric_times || null, bpm: PROJ?.bpm, key: PROJ?.key,
    buses: PROJ?.buses || null });                       // 2b: bus ses/mute geri alinabilir
  function restore(s) {
    const d = JSON.parse(s);
    PROJ.tracks = d.tracks;
    PROJ.latency_ms = d.latency_ms;
    if (Array.isArray(d.sections)) PROJ.sections = d.sections;
    if (d.lyric_times) PROJ.lyric_times = d.lyric_times;
    if (d.bpm != null) PROJ.bpm = d.bpm;
    if (d.key != null) PROJ.key = d.key;
    if (Array.isArray(d.buses)) PROJ.buses = d.buses;
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
    PREV?.refresh();
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

  // ---------------- R4: FX rafi (kanal / klip seviyesi, parametre paneli, surukle-birak) ----------------
  /** Secili kanalda tek secili klip ({tr, clip}) ya da null. */
  function selClipHit() {
    const sel = [...(TL?.selection() || [])];
    if (sel.length !== 1) return null;
    const h = TL.findClip(sel[0]);
    return h && h.tr.id === selTrack()?.id ? h : null;
  }
  /** Duzenlenen zincir: { tr, clip, level, chain, owner } — owner.fx zincirin sahibi (kanal ya da klip). */
  function fxCtx() {
    const tr = selTrack();
    const h = selClipHit();
    const level = FX_LEVEL === "clip" && h ? "clip" : "track";
    const owner = level === "clip" ? h.clip : tr;
    return { tr, clip: h?.clip || null, level, owner, chain: owner?.fx || [] };
  }
  function clipName(tr, c) {
    const tk = (tr.takes || []).find((t) => t.id === c.take_id);
    const [s, e] = BeatClips.clipBounds(c);
    return `${tk?.label || (c.path || "").split(/[\\/]/).pop() || "Klip"} (${s.toFixed(1)}–${e.toFixed(1)} sn)`;
  }
  /** Kanal zinciri degisince: onayar korunur ama "Ozel" olur (preset_base = cikis noktasi). */
  function markCustom(tr) {
    if (!tr || !tr.preset || tr.preset === "custom") return;
    const p = PRESETS[tr.preset];
    if (p && window.BeatFx && BeatFx.chainEquals(p.fx, tr.fx)) return;
    tr.preset_base = tr.preset;
    tr.preset = "custom";
  }
  /** Efekt duzenlemesi: geri al adimi + kayit, calmayi YENIDEN BASLATMADAN (efektli onizleme kendisi gecer). */
  function fxCommit(label, before) {
    if (!PROJ || snap() === before) return;
    const c = fxCtx();
    if (c.level === "track") markCustom(c.tr);
    pushUndo(before);
    renderProject();
    scheduleSave();
    PREV?.refresh();
    if (label) setStatus(label);
  }
  function fxEdit(label, fn) {
    if (!PROJ) return;
    const before = snap();
    fn(fxCtx());
    fxCommit(label, before);
  }
  function ownerChain(c) { if (!Array.isArray(c.owner.fx)) c.owner.fx = []; return c.owner.fx; }

  function fillFxSelects() {
    const sc = window.BeatFx ? BeatFx.schema() : {};
    const groups = {};
    for (const [k, v] of Object.entries(sc)) (groups[v.group] = groups[v.group] || []).push([k, v.label]);
    $("#fxAddSel").innerHTML = '<option value="">+ Efekt…</option>' + Object.entries(groups).map(([g, items]) =>
      `<optgroup label="${esc(g)}">${items.map(([k, l]) => `<option value="${esc(k)}">${esc(l)}</option>`).join("")}</optgroup>`).join("")
      + '<option value="__vst">VST3 eklentisi… (sağ panel)</option>';
    $("#fxPresetSel").innerHTML = '<option value="">Şablon…</option>' + Object.entries(PRESETS)
      .map(([k, v]) => `<option value="${esc(k)}">${esc(v.name)}</option>`).join("");
  }

  function renderFxRack() {
    const c = fxCtx();
    const tr = c.tr;
    $("#fxTargetName").textContent = tr ? tr.name : "—";
    $("#selTrackHint").textContent = tr ? `${tr.name} seçili` : "";
    $("#vstTargetInfo").textContent = c.level === "clip" ? `Hedef: Klip · ${clipName(tr, c.clip)}` : `Hedef kanal: ${tr ? tr.name : "Ana Vokal"}`;
    // seviye sekmeleri: Kanal / Klip
    const h = selClipHit();
    $("#fxLevelTabs").innerHTML = `<button type="button" class="kb-fx-lv ${c.level === "track" ? "on" : ""}" data-lv="track" role="tab" title="Kanalın efekt zinciri (tüm kliplere, klip efektlerinden sonra)">Kanal: ${esc(tr?.name || "—")}</button>`
      + (h ? `<button type="button" class="kb-fx-lv ${c.level === "clip" ? "on" : ""}" data-lv="clip" role="tab" title="Yalnız bu klibin efektleri (kanal zincirinden ÖNCE uygulanır)">Klip: ${esc(clipName(h.tr, h.clip))}${BeatClips.hasClipFx(h.clip) ? " ●" : ""}</button>` : "");
    $("#fxClipOpts").hidden = c.level !== "clip";
    if (c.level === "clip") {
      $("#fxSkipTrack").checked = !!c.clip.skip_track_fx;
      $("#fxStackAll").hidden = !c.clip.stack_id;
      $("#fxClipInfo").textContent = c.clip.stack_id ? "Destede efekt aktif take'e ait" : "";
    }
    const fx = c.chain;
    const scope = c.level === "clip" ? `${esc(tr.id)}:${esc(c.clip.id)}` : esc(tr?.id || "");
    if (!fx.length) {
      $("#fxRack").innerHTML = `<div class="kb-mut" style="display:grid;place-items:center;padding:8px">${c.level === "clip"
        ? "Bu klipte efekt yok — “+ Efekt…” ile ekle (kanal zincirinden önce uygulanır)."
        : "Bu kanalda FX yok — “+ Efekt…”, sağdaki VST3 sekmesi veya şablon ile ekle."}</div>`;
    } else {
      $("#fxRack").innerHTML = fx.map((f, idx) => `
        <div class="kb-fx-mod ${f.bypass ? "off" : ""} ${FX_OPEN && FX_OPEN.idx === idx && FX_OPEN.level === c.level ? "open" : ""}" data-fxi="${idx}" draggable="true" title="Tıkla: parametreler · sürükle: sırala">
          <div class="kb-fx-top">
            <button type="button" class="kb-fx-led" data-fxbyp="${idx}" title="Bypass aç/kapat"></button>
            <span class="kb-fx-name">${esc(fxLabel(f))}</span>
            <button type="button" class="kb-fx-del" data-fxcopy="${idx}" title="Kopyala">⧉</button>
            <button type="button" class="kb-fx-del" data-delfx="${scope}:${idx}" data-fxdel="${idx}" title="Kaldır">✕</button>
          </div>
          <div class="kb-fx-param">${esc(fxParamSummary(f))}</div>
        </div>`).join("");
    }
    syncFxPanel(c);
    renderStyle(c);
    renderAdlibQuick(c);
    renderMixRow(c);
  }

  /** Acik paneli (varsa) gecerli zincirdeki module yeniden baglar; modul yoksa kapatir. */
  function syncFxPanel(c) {
    c = c || fxCtx();
    const P = $("#fxPanel");
    if (!FX_OPEN || !window.BeatFx) { if (!P.hidden) BeatFx?.closePanel(P); return; }
    const sameOwner = FX_OPEN.level === c.level && FX_OPEN.tid === c.tr?.id && (c.level === "track" || FX_OPEN.cid === c.clip?.id);
    const fx = sameOwner ? c.chain[FX_OPEN.idx] : null;
    if (!fx) { FX_OPEN = null; BeatFx.closePanel(P); return; }
    if (P.__fx === fx && !P.hidden) return;      // ayni nesne: surgu suruklenirken yeniden kurma
    openFxPanel(FX_OPEN.idx);
  }
  function openFxPanel(idx) {
    const c = fxCtx();
    const fx = c.chain[idx];
    if (!fx || !window.BeatFx) return;
    FX_OPEN = { level: c.level, tid: c.tr.id, cid: c.clip?.id || "", idx };
    const P = $("#fxPanel");
    P.__fx = fx;
    BeatFx.openPanel({
      el: P, fx, api, runJob,
      title: `${fxLabel(fx)} · ${c.level === "clip" ? "Klip" : c.tr.name}`,
      snap,
      onInput: () => {
        const card = $(`#fxRack [data-fxi="${idx}"] .kb-fx-param`);
        if (card) card.textContent = fxParamSummary(fx);
        PREV?.refresh();
      },
      onCommit: (label, before) => fxCommit(label, before),
      onStatus: setStatus,
      onClose: () => { FX_OPEN = null; renderFxRack(); },
      reopen: () => { P.__fx = null; syncFxPanel(); },
    });
    document.querySelectorAll("#fxRack .kb-fx-mod").forEach((m) => m.classList.toggle("open", +m.dataset.fxi === idx));
  }

  // ---------------- 2b: otomasyon serit basligi + bus seritleri + send / vokale yer ac ----------------
  function autoHeadHtml(tr, col) {
    if (!tr.auto_lane || !window.BeatAuto) return "";
    const p = tr.auto_lane === "pan" ? "pan" : "volume";
    const n = (tr.automation?.[p] || []).length;
    return `<div class="kb-auto-head" data-autohead="${esc(tr.id)}" style="--tc:${col}">
      <select class="kb-sel" data-autoparam="${esc(tr.id)}" title="Otomasyon parametresi">
        <option value="volume" ${p === "volume" ? "selected" : ""} title="Kanal sürgüsüne eklenir">Ses (dB)</option>
        <option value="pan" ${p === "pan" ? "selected" : ""} title="Noktası varsa pan düğmesinin yerine geçer">Pan</option>
      </select>
      <span class="kb-mut">${n} nokta</span>
      <button type="button" class="btn ic" data-autoclear="${esc(tr.id)}" title="Bu şeridin tüm noktalarını sil" ${n ? "" : "disabled"}>⌫</button>
    </div>`;
  }
  function busStripsHtml() {
    return (PROJ?.buses || []).map((b) => {
      const v = Number(b.volume_db) || 0;
      const eng = (b.fx || []).map((f) => f.name || f.type).join(" → ");
      return `<div class="kb-bus-strip ${b.mute ? "muted" : ""}" data-bus="${esc(b.id)}" title="${esc(b.name)} bus'ı: ${esc(eng || "efekt yok")}">
        <b>${esc(b.name)}</b><span class="kb-mut">BUS</span>
        <input type="range" data-busvol="${esc(b.id)}" min="-24" max="6" step="0.5" value="${v}" title="Bus ses seviyesi">
        <span class="kb-db-val">${v > 0 ? "+" : ""}${v} dB</span>
        <button type="button" class="kb-ms ${b.mute ? "m-on" : ""}" data-busmute="${esc(b.id)}" title="Bus'ı sessize al">M</button>
      </div>`;
    }).join("");
  }
  const SEND_MIN = -60;
  function renderMixRow(c) {
    const tr = c?.tr;
    const box = $("#sendBox");
    if (!tr) { box.innerHTML = ""; $("#roomBox").hidden = true; return; }
    const sends = tr.sends || {};
    box.innerHTML = (PROJ?.buses || []).map((b) => {
      const v = sends[b.id] ?? SEND_MIN;
      const off = !(v > SEND_MIN);
      return `<label class="kb-send ${off ? "off" : ""} ${b.mute ? "bmute" : ""}" title="${esc(b.name)} send (post-fader)${b.mute ? " — bus sessizde" : ""}">
        <span>${esc(b.name)}</span><input type="range" data-send="${esc(b.id)}" min="${SEND_MIN}" max="6" step="0.5" value="${v}">
        <b class="kb-num">${off ? "kapalı" : `${v > 0 ? "+" : ""}${v} dB`}</b></label>`;
    }).join("") || '<span class="kb-mut">Bus yok</span>';
    const rb = $("#roomBox");
    rb.hidden = tr.role === "vocal";
    if (!rb.hidden) {
      const m = Object.assign({ on: false, mode: "band", center_hz: 2000, width_oct: 2, depth_db: 3 }, tr.make_room || {});
      rb.innerHTML = `<label class="kb-chk" title="Vokal kanalları ses verdiğinde bu kanalın orta frekanslarını birkaç dB geri çeker (bounce'ta da)"><input type="checkbox" data-room="on" ${m.on ? "checked" : ""}><span>Vokale yer aç</span></label>
        <select class="kb-sel" data-room="mode" title="Bant: yalnız orta frekanslar · Geniş: tüm beat (basit ducking)">
          <option value="band" ${m.mode !== "wide" ? "selected" : ""}>Orta bant</option><option value="wide" ${m.mode === "wide" ? "selected" : ""}>Geniş (ducking)</option></select>
        <label title="Merkez frekans"><span>Merkez</span><input type="range" data-room="center_hz" min="500" max="6000" step="50" value="${m.center_hz}" ${m.mode === "wide" ? "disabled" : ""}><b class="kb-num">${(m.center_hz / 1000).toFixed(1)} kHz</b></label>
        <label title="Bant genişliği (oktav)"><span>Genişlik</span><input type="range" data-room="width_oct" min="0.5" max="4" step="0.25" value="${m.width_oct}" ${m.mode === "wide" ? "disabled" : ""}><b class="kb-num">${Number(m.width_oct).toFixed(2)} okt</b></label>
        <label title="Azaltma miktarı (bant: 0-6 dB, geniş: 0-3 dB)"><span>Şiddet</span><input type="range" data-room="depth_db" min="0" max="${m.mode === "wide" ? 3 : 6}" step="0.5" value="${Math.min(m.depth_db, m.mode === "wide" ? 3 : 6)}"><b class="kb-num">${m.depth_db} dB</b></label>`;
    }
    $("#cleanOpen").hidden = !(tr.clips || []).length;
  }

  function renderProject() {
    if (!PROJ) return;
    syncLoopUi();
    $("#metaPill").textContent = `${Math.round(PROJ.bpm || 120)} BPM · ${PROJ.key || "—"}`;
    if (document.activeElement !== $("#lyrInput")) $("#lyrInput").value = PROJ.lyrics || "";
    $("#abToggle").disabled = !refOf();
    syncLatUi();

    const tracks = PROJ.tracks || [];
    tracks.forEach((tr) => { if (!Array.isArray(tr.clips)) tr.clips = []; });
    if (!tracks.some((t) => t.id === SEL_TID) && tracks.length) SEL_TID = tracks[0].id;

    let vocalIdx = 0;
    $("#tlHeads").innerHTML = tracks.map((tr) => {
      const col = BeatTimeline.trackColor(tr, tr.role === "beat" ? 0 : vocalIdx++);
      const lay = tr.layer && LAYER_LBL[tr.layer] ? `<span class="kb-layer-tag" title="${esc(LAYER_LBL[tr.layer])} katmanı → ${esc((tracks.find((x) => x.id === tr.layer_of) || {}).name || tr.layer_of || "")}${tr.chant_dev ? ` · ${tr.chant_dev.delay_ms} ms / ${tr.chant_dev.cents} cent` : ""}">${esc(LAYER_LBL[tr.layer][0])}</span>` : "";
      const takes = tr.takes || [];
      const presetOpts = (tr.preset === "custom" ? `<option value="custom" selected>Özel${PRESETS[tr.preset_base] ? ` (${esc(PRESETS[tr.preset_base].name)})` : ""}</option>` : "")
        + Object.entries(PRESETS).map(([k, v]) => `<option value="${esc(k)}" ${tr.preset === k ? "selected" : ""}>${esc(v.name)}</option>`).join("");
      const takeOpts = takes.map((t) => `<option value="${esc(t.id)}" ${tr.active_take === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("");
      return `
        <div class="kb-head ${tr.id === SEL_TID ? "sel" : ""}" data-tid="${esc(tr.id)}" style="--tc:${col}" title="Boş yerinden sürükle: kanal sırası">
          <div class="kb-ch">
            <span class="kb-role-bar"></span>
            <div class="kb-ch-top">
              ${lay}<b data-rename="${esc(tr.id)}" title="Çift tık: yeniden adlandır">${esc(tr.name)}</b>
              <button type="button" class="kb-ms ${tr.mute ? "m-on" : ""}" data-mute="${esc(tr.id)}" title="Sessize Al (Mute)">M</button>
              <button type="button" class="kb-ms ${tr.solo ? "s-on" : ""}" data-solo="${esc(tr.id)}" title="Tek Çal (Solo)">S</button>
              <button type="button" class="kb-ms ${tr.auto_lane ? "a-on" : ""} ${window.BeatAuto?.hasAuto(tr) ? "a-has" : ""}" data-autotog="${esc(tr.id)}" title="Otomasyon şeridi (ses / pan)">A</button>
              ${PROTECTED_TRACKS.has(tr.id) ? "" : `<button type="button" class="kb-del" data-deltrack="${esc(tr.id)}" title="Kanalı sil (geri alınabilir)">×</button>`}
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
        </div>${autoHeadHtml(tr, col)}`;
    }).join("") + busStripsHtml();

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
      // R4
      onSelection: () => { if (FX_OPEN?.level === "clip") FX_OPEN = null; autoClipLevel(); renderFxRack(); },
      onClipFx: (tid, cid) => clipFx(tid, cid),
      onRegionFx: (tid, cid, a, b) => regionFx(tid, cid, a, b),
      onThrow: (tid, cid, a, b, kind, note) => throwFx(tid, cid, a, b, kind, note),
      onPlayStart: () => PREV?.refresh(true),
      // 2b
      onBreathToggle: (tid, cid, i) => CLEAN?.toggleBreath(tid, cid, i),
      onCleanOpen: (tid, cid) => openClean(tid, cid),
      breathSuggest: (c) => CLEAN?.breathSuggest(c),
    });
    TL.setSnap(gridMode());
    initPreview();
    initClean();
    syncGridLabel();
    applyRecSetUi();
  }

  /** 2b: Temizle paneli. */
  function initClean() {
    if (!window.BeatClean) return;
    CLEAN = BeatClean.create({
      el: $("#cleanPanel"), api, runJob, getProj: () => PROJ, edit, onStatus: setStatus, tl: () => TL,
      onApplied: () => { TL?.restartIfPlaying(); PREV?.refresh(true); },
    });
  }
  function openClean(tid, cid) {
    if (!CLEAN || !PROJ) return;
    if (tid) selectTrack(tid);
    const h = cid ? null : selClipHit();
    CLEAN.open(tid || SEL_TID, cid || (FX_LEVEL === "clip" && h ? h.clip.id : ""));
  }
  // 2b: send seviyeleri + vokale yer ac (surgu canli; birakinca tek geri al adimi)
  let MIX_BEFORE = null;
  function mixField(el) {
    const tr = selTrack();
    if (!tr) return null;
    if (el.dataset.send) {
      const v = +el.value;
      tr.sends = Object.assign({}, tr.sends || {});
      if (v > SEND_MIN) tr.sends[el.dataset.send] = v; else delete tr.sends[el.dataset.send];
      const lbl = el.nextElementSibling;
      if (lbl) lbl.textContent = v > SEND_MIN ? `${v > 0 ? "+" : ""}${v} dB` : "kapalı";
      el.closest(".kb-send")?.classList.toggle("off", !(v > SEND_MIN));
      return "Send";
    }
    if (el.dataset.room) {
      const k = el.dataset.room;
      tr.make_room = Object.assign({ on: false, mode: "band", center_hz: 2000, width_oct: 2, depth_db: 3 }, tr.make_room || {});
      tr.make_room[k] = el.type === "checkbox" ? el.checked : (el.tagName === "SELECT" ? el.value : +el.value);
      if (k === "mode" && el.value === "wide") tr.make_room.depth_db = Math.min(3, tr.make_room.depth_db);
      const lbl = el.nextElementSibling;
      if (lbl && el.type === "range") lbl.textContent = k === "center_hz" ? `${(+el.value / 1000).toFixed(1)} kHz` : k === "width_oct" ? `${(+el.value).toFixed(2)} okt` : `${el.value} dB`;
      return "Vokale yer aç";
    }
    return null;
  }
  $("#mixRow").addEventListener("input", (e) => {
    if (!PROJ || e.target.type !== "range") return;
    if (MIX_BEFORE === null) MIX_BEFORE = snap();
    mixField(e.target);
  });
  $("#mixRow").addEventListener("change", (e) => {
    if (!PROJ) return;
    const before = MIX_BEFORE ?? snap();
    MIX_BEFORE = null;
    const label = mixField(e.target);
    if (e.target.tagName === "SELECT") e.target.blur();
    if (label) commitFrom(label, before);
  });

  $("#cleanOpen").onclick = (e) => { e.currentTarget.blur(); if (CLEAN?.isOpen()) CLEAN.close(); else openClean(); };

  /** Efektli onizleme yoneticisi + arac cubugu denetimleri. */
  function initPreview() {
    if (!window.BeatFx || !TL) return;
    PREV = BeatFx.createPreview({
      api, tl: () => TL, getProj: () => PROJ, selTid: () => SEL_TID,
      onState: (s) => {
        const n = $("#fxPreviewNote");
        n.textContent = s.text;
        n.title = s.title || "";
        n.dataset.kind = s.kind || "";
        $("#fxPreviewToggle").classList.toggle("on", s.enabled);
        $("#fxPreviewToggle").textContent = s.enabled ? "FX ▶" : "FX ✕";
        $("#fxPreviewScope").disabled = !s.enabled;
        $("#fxPreviewScope").value = s.scope;
      },
    });
    $("#fxPreviewToggle").onclick = (e) => { e.currentTarget.blur(); PREV.setEnabled(!PREV.state().enabled); };
    $("#fxPreviewScope").onchange = (e) => PREV.setScope(e.target.value);
    PREV.syncState();
  }
  /** Kendi efekti olan tek klip secilince raf klip seviyesine gecer; secim kalkinca kanala doner. */
  function autoClipLevel() {
    const h = selClipHit();
    if (!h) { FX_LEVEL = "track"; return; }
    if (BeatClips.hasClipFx(h.clip)) FX_LEVEL = "clip";
  }

  function selectTrack(tid) {
    if (!tid || tid === SEL_TID) return;
    SEL_TID = tid;
    document.querySelectorAll(".kb-head").forEach((x) => x.classList.toggle("sel", x.dataset.tid === SEL_TID));
    document.querySelectorAll(".kb-tl-lane").forEach((x) => x.classList.toggle("sel", x.dataset.lane === SEL_TID));
    FX_OPEN = null;
    renderFxRack();
    PREV?.refresh(true);
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
    else if (k === "Delete" || k === "Backspace") { e.preventDefault(); if (!TL.autoDeleteSelected()) TL.deleteSelected(); }
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
    else if (!ctrl && !e.altKey && (k === "b" || k === "B")) { e.preventDefault(); toggleAB(); }
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
          ${(LIB?.lineIdeas(ln.n) || []).map((it) => `<button type="button" class="kb-lyr-idea" data-ideaplay="${esc(it.file)}" data-ideaname="${esc(it.name)}" title="💡 ${esc(it.name)} — tıkla: çal">🎙</button>`).join("")}
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
    const ib = e.target.closest("[data-ideaplay]");
    if (ib) { playPath(ib.dataset.ideaplay, `💡 ${ib.dataset.ideaname || ""}`); return; }
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
      ["booth", "lyrics", "vst", "shelf", "ideas"].forEach((k) => { $(`#pane-${k}`).hidden = b.dataset.side !== k; });
      if (b.dataset.side === "shelf") LIB?.refreshShelf();
      if (b.dataset.side === "ideas") LIB?.refreshIdeas();
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
    } else if (b.dataset.autotog) {           // 2b: otomasyon seridi ac/kapa (gorunum durumu, geri al adimi degil)
      const tr = PROJ.tracks.find((x) => x.id === b.dataset.autotog);
      if (tr) { if (tr.auto_lane) delete tr.auto_lane; else tr.auto_lane = "volume"; TL?.clearAutoSel(); renderProject(); scheduleSave(); }
    } else if (b.dataset.autoclear) {
      const tr = PROJ.tracks.find((x) => x.id === b.dataset.autoclear);
      const p = tr?.auto_lane === "pan" ? "pan" : "volume";
      if (tr?.automation?.[p]?.length) edit(`${p === "pan" ? "Pan" : "Ses"} otomasyonu temizlendi`, () => { tr.automation[p] = []; });
    } else if (b.dataset.busmute) {
      edit("Bus mute", () => { const bb = (PROJ.buses || []).find((x) => x.id === b.dataset.busmute); if (bb) bb.mute = !bb.mute; });
    } else if (b.dataset.deltrack) {
      const tr = PROJ.tracks.find((x) => x.id === b.dataset.deltrack);
      if (!tr) return;
      const nClips = (tr.clips || []).length;
      if (nClips && !confirm(`“${tr.name}” kanalı ${nClips} klibiyle silinsin mi? (Ctrl+Z ile geri alınır; ham dosyalar silinmez)`)) return;
      tracksOp("remove", { id: tr.id }, `Kanal silindi: ${tr.name} (Ctrl+Z geri alır)`);
    }
  });

  // ---- 1d: kanal ekle / sil / sirala / yeniden adlandir (mantik Python'da: beat_tracks_op) ----
  async function tracksOp(op, args, label) {
    if (!PROJ) return null;
    const r = await api()?.beat_tracks_op?.(PROJ.tracks, op, args).catch(() => null);
    if (!r?.ok) {
      setStatus({ protected_track: "Beat ve Ana Vokal kanalları silinemez.", too_many_tracks: "En fazla 24 kanal." }[r?.error] || ("Kanal işlemi başarısız: " + (r?.error || "?")));
      return r;
    }
    edit(label, () => { PROJ.tracks = r.tracks; });
    if (r.track_id) selectTrack(r.track_id);
    return r;
  }
  $("#tlAddTrack").onclick = (e) => {
    e.currentTarget.blur();
    const pop = $("#addTrackPop");
    pop.hidden = !pop.hidden;
    if (!pop.hidden) {
      const pal = ["#38BDF8", "#EC4899", "#A3E635", "#F97316", "#2DD4BF", "#E879F9", "#F59E0B", "#9D6BFF"];
      const used = new Set((PROJ?.tracks || []).map((t) => String(t.color || "").toUpperCase()));
      $("#atColor").value = pal.find((c) => !used.has(c.toUpperCase())) || pal[0];
      $("#atName").value = "";
      $("#atName").focus();
    }
  };
  $("#atCancel").onclick = () => { $("#addTrackPop").hidden = true; };
  async function addTrackFromPop() {
    $("#addTrackPop").hidden = true;
    const role = $("#atRole").value;
    const r = await tracksOp("add", { role, name: $("#atName").value.trim(), color: $("#atColor").value }, "");
    if (r?.ok) setStatus(`Kanal eklendi: ${(PROJ.tracks.find((t) => t.id === r.track_id) || {}).name || ""} — başlığı sürükleyerek sırala`);
  }
  $("#atOk").onclick = addTrackFromPop;
  $("#atName").addEventListener("keydown", (e) => { if (e.key === "Enter") addTrackFromPop(); else if (e.key === "Escape") $("#addTrackPop").hidden = true; e.stopPropagation(); });
  $("#tlHeads").addEventListener("dblclick", (e) => {
    const b = e.target.closest("b[data-rename]");
    if (!b || !PROJ) return;
    const tid = b.dataset.rename;
    const tr = PROJ.tracks.find((x) => x.id === tid);
    const inp = document.createElement("input");
    inp.className = "kb-rename"; inp.value = tr?.name || ""; inp.maxLength = 40;
    b.replaceWith(inp); inp.focus(); inp.select();
    let done = false;
    const finish = (save) => {
      if (done) return; done = true;
      const nm = inp.value.trim();
      if (save && nm && nm !== tr?.name) tracksOp("rename", { id: tid, name: nm }, `Kanal adı: ${nm}`);
      else renderProject();
    };
    inp.addEventListener("keydown", (ev) => { ev.stopPropagation(); if (ev.key === "Enter") finish(true); else if (ev.key === "Escape") finish(false); });
    inp.addEventListener("blur", () => finish(true));
  });
  // surukle-birak siralama
  let HEAD_DRAG = "";
  // yalniz bos yerden basilinca suruklenebilir (surgu / metin kutusu / dugmeler normal calissin)
  $("#tlHeads").addEventListener("mousedown", (e) => {
    const h = e.target.closest(".kb-head[data-tid]");
    if (h) h.draggable = !e.target.closest("input,select,button,textarea");
  });
  const clearDropMarks = () => document.querySelectorAll(".kb-head.kb-drop-above,.kb-head.kb-drop-below").forEach((x) => x.classList.remove("kb-drop-above", "kb-drop-below"));
  $("#tlHeads").addEventListener("dragstart", (e) => {
    const h = e.target.closest(".kb-head[data-tid]");
    if (!h || e.target.closest("input,select,button")) { if (h) e.preventDefault(); return; }
    HEAD_DRAG = h.dataset.tid;
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", "kami-track:" + HEAD_DRAG); } catch {}
  });
  $("#tlHeads").addEventListener("dragover", (e) => {
    if (!HEAD_DRAG) return;
    const h = e.target.closest(".kb-head[data-tid]");
    if (!h) return;
    e.preventDefault();
    clearDropMarks();
    const r = h.getBoundingClientRect();
    h.classList.add(e.clientY < r.top + r.height / 2 ? "kb-drop-above" : "kb-drop-below");
  });
  $("#tlHeads").addEventListener("dragleave", (e) => { if (!e.relatedTarget || !$("#tlHeads").contains(e.relatedTarget)) clearDropMarks(); });
  $("#tlHeads").addEventListener("drop", (e) => {
    const src = HEAD_DRAG;
    HEAD_DRAG = "";
    const h = e.target.closest(".kb-head[data-tid]");
    clearDropMarks();
    if (!src || !h || !PROJ) return;
    e.preventDefault();
    const ids = PROJ.tracks.map((t) => t.id).filter((x) => x !== src);
    const r = h.getBoundingClientRect();
    let idx = ids.indexOf(h.dataset.tid);
    if (idx < 0) return;
    if (e.clientY >= r.top + r.height / 2) idx += 1;
    ids.splice(idx, 0, src);
    if (ids.join() === PROJ.tracks.map((t) => t.id).join()) return;
    tracksOp("reorder", { ids }, "Kanal sırası değişti");
  });
  $("#tlHeads").addEventListener("dragend", () => { HEAD_DRAG = ""; clearDropMarks(); });

  $("#tlHeads").addEventListener("change", (e) => {
    if (!PROJ) return;
    const el = e.target;
    if (el.dataset.preset) {
      const p = PRESETS[el.value];
      if (!p) return;
      SEL_TID = el.dataset.preset;
      FX_OPEN = null;
      edit(`${p.name} uygulandı.`, () => {
        const tr = PROJ.tracks.find((x) => x.id === el.dataset.preset);
        if (tr) { tr.preset = el.value; tr.denoise = !!p.denoise; tr.fx = JSON.parse(JSON.stringify(p.fx)); delete tr.preset_base; }
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
    } else if (el.dataset.autoparam) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.autoparam);
      if (tr) { tr.auto_lane = el.value === "pan" ? "pan" : "volume"; TL?.clearAutoSel(); renderProject(); scheduleSave(); }
    } else if (el.dataset.busvol) {
      const before = el.dataset.before;
      if (before) { delete el.dataset.before; commitFrom("Bus ses seviyesi", before); }
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
    if (el.dataset.busvol) {                  // 2b: bus ses seviyesi (birakinca tek geri al adimi)
      if (!el.dataset.before) el.dataset.before = snap();
      const bb = (PROJ.buses || []).find((x) => x.id === el.dataset.busvol);
      if (bb) { bb.volume_db = +el.value; el.nextElementSibling.textContent = `${bb.volume_db > 0 ? "+" : ""}${bb.volume_db} dB`; }
      return;
    }
    const tid = el.dataset.vol || el.dataset.pan;
    if (!tid) return;
    if (!el.dataset.before) el.dataset.before = snap();
    const tr = PROJ.tracks.find((x) => x.id === tid);
    if (!tr) return;
    if (tr.layer) tr.auto_place = false;   // 1d: elle ayarlanan katman otomatik yerlesimden cikar
    if (el.dataset.vol) {
      tr.volume_db = +el.value;
      el.nextElementSibling.textContent = `${tr.volume_db > 0 ? "+" : ""}${tr.volume_db} dB`;
    } else tr.pan = +el.value;
  });

  // ---- Bottom FX Rack Interactions (R4: tikla = parametre paneli, LED = bypass, surukle = sirala) ----
  $("#fxRack").addEventListener("click", (e) => {
    if (!PROJ) return;
    const del = e.target.closest("[data-fxdel]");
    const cp = e.target.closest("[data-fxcopy]");
    const byp = e.target.closest("[data-fxbyp]");
    if (del || cp || byp) {
      e.stopPropagation();
      const i = +(del || cp || byp).dataset[del ? "fxdel" : cp ? "fxcopy" : "fxbyp"];
      if (del) {
        if (FX_OPEN?.idx === i) FX_OPEN = null;
        else if (FX_OPEN && FX_OPEN.idx > i) FX_OPEN.idx--;
        fxEdit("FX kaldırıldı", (c) => ownerChain(c).splice(i, 1));
      } else if (cp) fxEdit("FX kopyalandı", (c) => { const ch = ownerChain(c); ch.splice(i + 1, 0, JSON.parse(JSON.stringify(ch[i]))); });
      else fxEdit("FX bypass", (c) => { const f = ownerChain(c)[i]; if (f) f.bypass = !f.bypass; });
      return;
    }
    const mod = e.target.closest("[data-fxi]");
    if (!mod) return;
    const i = +mod.dataset.fxi;
    if (FX_OPEN && FX_OPEN.idx === i && !$("#fxPanel").hidden) { FX_OPEN = null; BeatFx.closePanel($("#fxPanel")); renderFxRack(); return; }
    openFxPanel(i);
  });
  $("#fxRack").addEventListener("dblclick", (e) => { const m = e.target.closest("[data-fxi]"); if (m && !e.target.closest("button")) openFxPanel(+m.dataset.fxi); });
  // surukle-birak ile siralama
  let FX_DRAG = -1;
  $("#fxRack").addEventListener("dragstart", (e) => {
    const m = e.target.closest("[data-fxi]");
    if (!m) return;
    FX_DRAG = +m.dataset.fxi;
    e.dataTransfer.effectAllowed = "move";
    try { e.dataTransfer.setData("text/plain", String(FX_DRAG)); } catch {}
    m.classList.add("drag");
  });
  $("#fxRack").addEventListener("dragover", (e) => {
    if (FX_DRAG < 0) return;
    e.preventDefault();
    const m = e.target.closest("[data-fxi]");
    document.querySelectorAll("#fxRack .kb-fx-mod").forEach((x) => x.classList.toggle("drop", x === m && +x.dataset.fxi !== FX_DRAG));
  });
  $("#fxRack").addEventListener("dragend", () => { FX_DRAG = -1; document.querySelectorAll("#fxRack .kb-fx-mod").forEach((x) => x.classList.remove("drag", "drop")); });
  $("#fxRack").addEventListener("drop", (e) => {
    if (FX_DRAG < 0) return;
    e.preventDefault();
    const m = e.target.closest("[data-fxi]");
    const from = FX_DRAG;
    FX_DRAG = -1;
    const c0 = fxCtx();
    const to = m ? +m.dataset.fxi : c0.chain.length - 1;
    if (to === from) { renderFxRack(); return; }
    const openFx = FX_OPEN ? c0.chain[FX_OPEN.idx] : null;
    fxEdit("FX sırası değişti", (c) => { const ch = ownerChain(c); const [x] = ch.splice(from, 1); ch.splice(to, 0, x); });
    if (openFx) { const i = fxCtx().chain.indexOf(openFx); if (i >= 0) { FX_OPEN.idx = i; renderFxRack(); } }
  });
  $("#fxLevelTabs").addEventListener("click", (e) => {
    const b = e.target.closest("[data-lv]");
    if (!b) return;
    FX_LEVEL = b.dataset.lv;
    FX_OPEN = null;
    renderFxRack();
  });
  $("#fxAddSel").addEventListener("change", (e) => {
    const v = e.target.value;
    e.target.value = "";
    if (!v || !PROJ) return;
    if (v === "__vst") { document.querySelector('.kb-side-tabs [data-side="vst"]')?.click(); return; }
    const f = BeatFx.defaultFx(v);
    if (!f) return;
    let at = -1;
    fxEdit(`${BeatFx.label(f)} eklendi`, (c) => { const ch = ownerChain(c); ch.push(f); at = ch.length - 1; });
    if (at >= 0) openFxPanel(at);
  });
  $("#fxPresetSel").addEventListener("change", (e) => {
    const k = e.target.value;
    e.target.value = "";
    const p = PRESETS[k];
    if (!p || !PROJ) return;
    FX_OPEN = null;
    fxEdit(`${p.name} uygulandı.`, (c) => {
      c.owner.fx = JSON.parse(JSON.stringify(p.fx));
      if (c.level === "track") { c.tr.preset = k; c.tr.denoise = !!p.denoise; delete c.tr.preset_base; delete c.tr.style; }
    });
  });
  $("#fxSkipTrack").addEventListener("change", (e) => {
    const on = e.target.checked;
    fxEdit(on ? "Klip kanal efektini atlıyor" : "Klip kanal efektinden geçiyor", (c) => { if (c.clip) c.clip.skip_track_fx = on; });
  });
  $("#fxStackAll").addEventListener("click", () => {
    const c = fxCtx();
    if (!c.clip?.stack_id) return;
    const n = BeatClips.stackMembers(c.tr.clips, c.clip.stack_id).length;
    fxEdit(`Klip efekti destedeki ${n} take'e uygulandı`, (cc) => { cc.tr.clips = BeatClips.applyFxToStack(cc.tr.clips, cc.clip.id); });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && FX_OPEN && !$("#fxPanel").hidden && !RECST) { FX_OPEN = null; BeatFx.closePanel($("#fxPanel")); renderFxRack(); }
  });

  /** R4: 'Bu bolgeye efekt' -> klip aralikta bolunur (10 ms capraz gecis), ortadaki parca kendi zincirini alir. */
  function regionFx(tid, cid, t0, t1) {
    const tr = PROJ?.tracks.find((x) => x.id === tid);
    if (!tr) return;
    let mid = "";
    edit(`Bölgeye efekt: ${t0.toFixed(2)}–${t1.toFixed(2)} sn (klip bölündü)`, () => {
      const r = BeatClips.regionSplit(tr.clips, cid, t0, t1, BeatClips.XFADE, null, []);
      tr.clips = r.clips;
      mid = r.mid_id;
    });
    if (!mid) { setStatus("Bölge çok kısa ya da klibin dışında."); return; }
    SEL_TID = tid;
    TL?.select(mid, false);
    FX_LEVEL = "clip";
    FX_OPEN = null;
    renderProject();
    setStatus("Bölge ayrı klip oldu — “+ Efekt…” veya şablonla bu bölgeye efekt ekle (kanal zincirinden önce).");
  }
  function clipFx(tid, cid) {
    if (tid !== SEL_TID) selectTrack(tid);
    TL?.select(cid, false);
    FX_LEVEL = "clip";
    FX_OPEN = null;
    renderFxRack();
  }


  // ================= Asama 2a: tarz onayarlari =================
  const STY = { presets: [], open: localStorage.getItem("kb_sty_open") !== "0", notes: new Map(), live: { before: null, timer: 0, seq: 0, commit: false } };
  const fxSig = (fx) => JSON.stringify((fx || []).map((f) => { const o = Object.assign({}, f); delete o.name; return o; }));
  const styCustom = (tr) => !!tr?.style && fxSig(tr.fx) !== tr.style.fx_sig;
  async function loadStyles() {
    const r = await api()?.beat_style_presets?.().catch(() => null);
    STY.presets = r?.presets || [];
    renderStyle();
  }
  function resolveStyle(id, intensity) {
    return api()?.beat_style_resolve?.(id, intensity, $("#styVst").checked, Number(PROJ?.bpm) || 0, useSends()).catch((e) => ({ ok: false, error: String(e) }));
  }
  /** 2b: onayarin reverb/delay'i bus send'ine (varsayilan acik; bus yoksa kanal sonunda kalir). */
  function useSends() { return !!$("#stySends")?.checked && (PROJ?.buses || []).length > 0; }
  function applySends(tr, r) {
    if (!r?.use_sends) return;
    tr.sends = Object.assign({}, tr.sends || {}, r.sends || {});
    for (const b of ["reverb", "delay"]) if (!(r.sends || {})[b] && tr.style_sends?.includes(b)) delete tr.sends[b];
    tr.style_sends = Object.keys(r.sends || {});
  }
  function renderStyle(c) {
    c = c || fxCtx();
    const tr = c.tr;
    const bar = $("#styBar");
    if (!bar) return;
    $("#styFold").textContent = `${STY.open ? "▾" : "▸"} TARZ ÖNAYARLARI`;
    $("#styGrid").hidden = !STY.open;
    $("#styInfo").hidden = !STY.open;
    const st = c.level === "track" ? tr?.style : null;
    const kind = tr?.layer === "adlib" || /adlib/i.test(tr?.name || "") ? "adlib" : "vocal";
    $("#styGrid").innerHTML = STY.presets.length ? BeatStyle.cardsHtml(STY.presets, st ? { id: st.id, custom: styCustom(tr) } : null, kind)
      : '<div class="kb-mut">Önayar listesi yükleniyor…</div>';
    $("#styCur").textContent = st ? `${st.name}${styCustom(tr) ? " · Özel" : ""}` : (c.level === "clip" ? "Klip seviyesi: kart zinciri bu klibe uygulanır" : "");
    const v = st ? Math.round(st.intensity ?? 50) : 50;
    if (document.activeElement !== $("#styInt")) { $("#styInt").value = v; $("#styIntVal").textContent = String(v); }
    $("#styInt").disabled = !st;
    $("#styInt").title = st ? "Önayar yoğunluğu (50 = tasarlanan). Sürgü önayarı yeniden uygular; özel değişiklikler geri al ile döner." : "Önce bir önayar kartı seç";
    $("#stySave").disabled = !(c.chain || []).length;
    const n = tr ? STY.notes.get(tr.id) : null;
    $("#styInfo").innerHTML = n && st && n.id === st.id ? styInfoHtml(n) : (STY.open ? "Kart seç: zincir tek adımda kurulur (tek geri al), efektli önizleme ~1-2 sn'de yenilenir. Kartın üstünde bekle: açıklama + neden." : "");
  }
  function styInfoHtml(r) {
    const used = (r.steps || []).map((s) => `<span class="kb-sty-step ${s.engine}" title="${esc(s.note || "")}">${esc(s.plugin || s.label)}${s.engine === "skip" ? " ✕" : ""}</span>`).join("");
    const notes = (r.notes || []).filter((t) => /incelt|atlandı|seç/.test(t));
    return `<div class="kb-sty-steps">${used}</div>${notes.length ? `<div class="kb-sty-notes">⚠ ${notes.map(esc).join(" · ")}</div>` : ""}`;
  }
  async function applyStyle(id) {
    const c0 = fxCtx();
    if (!PROJ || !c0.tr) return;
    const inten = c0.level === "track" ? (c0.tr.style?.intensity ?? 50) : 50;
    setStatus("Önayar hazırlanıyor…");
    const r = await resolveStyle(id, inten);
    if (!r?.ok) { setStatus("Önayar uygulanamadı: " + (r?.error || "?")); return; }
    FX_OPEN = null;
    let tid = "";
    fxEdit(`${r.name} uygulandı (${r.fx.length} modül${r.vst_total ? ` · eklenti ${r.vst_installed}/${r.vst_total}` : ""})`, (c) => {
      c.owner.fx = JSON.parse(JSON.stringify(r.fx));
      if (c.level === "track") {
        tid = c.tr.id;
        c.tr.style = { id, name: r.name, intensity: inten, use_vst: !!r.use_vst, fx_sig: fxSig(c.owner.fx) };
        c.tr.preset = ""; delete c.tr.preset_base;
        c.tr.denoise = !!r.denoise;
        applySends(c.tr, r);
      }
    });
    if (tid) { STY.notes.set(tid, r); renderStyle(); suggestLayers(tid, id); }
  }
  // ---- yogunluk surgusu (canli; birakinca tek geri al adimi) ----
  async function liveIntensity(v) {
    const tr = selTrack();
    if (!tr?.style || fxCtx().level !== "track") { STY.live.before = null; STY.live.commit = false; return; }
    const my = ++STY.live.seq;
    const r = await resolveStyle(tr.style.id, v);
    if (my !== STY.live.seq) return;
    if (r?.ok) {
      tr.fx = r.fx; tr.style.intensity = v; tr.style.fx_sig = fxSig(tr.fx);
      applySends(tr, r);
      STY.notes.set(tr.id, r);
      FX_OPEN = null;
      renderFxRack();
      PREV?.refresh();
    }
    if (STY.live.commit) {
      const b = STY.live.before;
      STY.live.before = null; STY.live.commit = false;
      if (b) fxCommit(`Önayar yoğunluğu ${v}`, b);
    }
  }
  $("#styInt").addEventListener("input", (e) => {
    $("#styIntVal").textContent = e.target.value;
    if (!selTrack()?.style) return;
    if (STY.live.before === null) STY.live.before = snap();
    clearTimeout(STY.live.timer);
    STY.live.timer = setTimeout(() => liveIntensity(+e.target.value), 120);
  });
  $("#styInt").addEventListener("change", (e) => {
    if (!selTrack()?.style) return;
    if (STY.live.before === null) STY.live.before = snap();
    STY.live.commit = true;
    clearTimeout(STY.live.timer);
    liveIntensity(+e.target.value);
    e.target.blur();
  });
  $("#styFold").onclick = () => { STY.open = !STY.open; localStorage.setItem("kb_sty_open", STY.open ? "1" : "0"); renderStyle(); };
  $("#styGrid").addEventListener("click", async (e) => {
    const del = e.target.closest("[data-stydel]");
    if (del) {
      e.stopPropagation();
      const r = await api()?.beat_user_preset_delete?.(del.dataset.stydel).catch(() => null);
      setStatus(r?.ok ? "Önayar silindi." : "Silinemedi: " + (r?.error || "?"));
      loadStyles();
      return;
    }
    const card = e.target.closest("[data-sty]");
    if (card) applyStyle(card.dataset.sty);
  });
  $("#stySave").onclick = () => {
    const tr = selTrack();
    $("#stySaveBox").hidden = !$("#stySaveBox").hidden;
    if (!$("#stySaveBox").hidden) { $("#stySaveName").value = tr?.style ? `${tr.style.name} (benim)` : `${tr?.name || "Vokal"} zinciri`; $("#stySaveName").select(); $("#stySaveName").focus(); }
  };
  async function saveUserPreset() {
    const c = fxCtx();
    const name = $("#stySaveName").value.trim();
    if (!name) return;
    const kind = c.tr?.layer === "adlib" ? "adlib" : "vocal";
    const r = await api()?.beat_user_preset_save?.(name, JSON.parse(JSON.stringify(c.chain || [])),
      c.tr?.style ? `${c.tr.style.name} tabanlı` : "", "Kendi", !!c.tr?.denoise, kind).catch(() => null);
    $("#stySaveBox").hidden = true;
    if (!r?.ok) { setStatus("Önayar kaydedilemedi: " + (r?.error || "?")); return; }
    setStatus(`“${r.preset.name}” önayar olarak kaydedildi — listenin başında.`);
    await loadStyles();
  }
  $("#stySaveOk").onclick = saveUserPreset;
  $("#stySaveName").addEventListener("keydown", (e) => { e.stopPropagation(); if (e.key === "Enter") saveUserPreset(); else if (e.key === "Escape") $("#stySaveBox").hidden = true; });
  $("#styVst").addEventListener("change", (e) => { e.target.blur(); const tr = selTrack(); if (tr?.style && fxCtx().level === "track") applyStyle(tr.style.id); });
  // ---- katman esleniği onerisi ----
  async function suggestLayers(tid, id) {
    const r = await api()?.beat_style_suggest?.(PROJ.tracks, tid, id).catch(() => null);
    const list = r?.suggestions || [];
    const box = $("#stySuggest");
    if (!list.length) { box.hidden = true; return; }
    box.hidden = false;
    box.innerHTML = `<span>Katmanlara eşlenik önayar:</span>${list.map((x) => `<b title="${esc(x.track_name)} kanalına">${esc(LAYER_LBL[x.kind] || x.kind)} → ${esc(x.name)}</b>`).join("")}
      <button type="button" class="btn ok" id="styLayerApply">Uygula</button><button type="button" class="btn ic" id="styLayerClose" title="Kapat">✕</button>`;
    $("#styLayerClose").onclick = () => { box.hidden = true; };
    $("#styLayerApply").onclick = async () => {
      box.hidden = true;
      const res = await Promise.all(list.map((x) => resolveStyle(x.preset_id, PROJ.tracks.find((t) => t.id === tid)?.style?.intensity ?? 50)));
      edit(`Katmanlara eşlenik önayar uygulandı (${list.length} kanal)`, () => {
        list.forEach((x, i) => {
          const r2 = res[i];
          const t = PROJ.tracks.find((y) => y.id === x.track_id);
          if (!t || !r2?.ok) return;
          t.fx = JSON.parse(JSON.stringify(r2.fx));
          t.style = { id: x.preset_id, name: r2.name, intensity: r2.intensity, use_vst: !!r2.use_vst, fx_sig: fxSig(t.fx) };
          t.preset = ""; delete t.preset_base;
          applySends(t, r2);
          STY.notes.set(t.id, r2);
        });
      });
    };
  }

  // ================= Asama 2a: adlib hizli efektleri + efekt atmalari =================
  function isAdlibTrack(tr) { return !!tr && (tr.layer === "adlib" || (tr.role === "vocal" && /adlib/i.test(tr.name || ""))); }
  function renderAdlibQuick(c) {
    c = c || fxCtx();
    $("#adlibQuick").hidden = !isAdlibTrack(c.tr) || !(c.tr.clips || []).length;
  }
  $("#adlibQuick").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-adlib]");
    if (!b || !PROJ) return;
    b.blur();
    const tr = selTrack();
    if (!isAdlibTrack(tr)) return;
    const recipe = await api()?.beat_quick_fx?.(b.dataset.adlib, Number(PROJ.bpm) || 0, $("#adlibNote").value).catch(() => null);
    if (!recipe?.ok) { setStatus("Efekt hazırlanamadı: " + (recipe?.error || "?")); return; }
    const own = new Set((tr.clips || []).map((x) => x.id));
    let ids = [...(TL?.selection() || [])].filter((id) => own.has(id));
    const scope = ids.length ? `${ids.length} klip` : "tüm klipler";
    if (!ids.length) ids = (recipe.mode === "echo_tail" ? BeatClips.stackView(tr.clips) : tr.clips).map((x) => x.id);
    let made = [];
    edit(`Adlib: ${recipe.label} (${scope})`, () => {
      const r = BeatStyle.applyAdlib(tr.clips, ids, recipe);
      tr.clips = r.clips;
      made = r.ids;
    });
    if (made.length === 1 && recipe.mode !== "autopan") { TL?.select(made[0], false); FX_LEVEL = "clip"; FX_OPEN = null; renderFxRack(); }
  });
  /** Bolgeye efekt atma (Ctrl+surukle menusu): bolge ayri klip olur, ortaya efekt + kuyruk; tek geri al. */
  async function throwFx(tid, cid, t0, t1, kind, note) {
    const tr = PROJ?.tracks.find((x) => x.id === tid);
    if (!tr) return;
    const recipe = await api()?.beat_quick_fx?.(kind, Number(PROJ.bpm) || 0, note || "1/8").catch(() => null);
    if (!recipe?.ok) { setStatus("Efekt hazırlanamadı: " + (recipe?.error || "?")); return; }
    let mid = "";
    edit(`${recipe.label}: ${t0.toFixed(2)}–${t1.toFixed(2)} sn${recipe.tail_sec ? ` (kuyruk ${recipe.tail_sec.toFixed(1)} sn)` : ""}`, () => {
      const r = BeatStyle.applyThrow(tr.clips, cid, t0, t1, recipe);
      tr.clips = r.clips;
      mid = r.mid_id;
    });
    if (!mid) { setStatus("Bölge çok kısa ya da klibin dışında."); return; }
    if (tid !== SEL_TID) { SEL_TID = tid; renderProject(); }
    TL?.select(mid, false);
    FX_LEVEL = "clip";
    FX_OPEN = null;
    renderFxRack();
  }

  // ================= Asama 2a: dinleme simulatoru =================
  function initListen() {
    if (!window.BeatSim) { $("#listenSel").hidden = true; return; }
    $("#listenSel").innerHTML = BeatSim.list().map((p) => `<option value="${esc(p.id)}">Dinleme: ${esc(p.label)}</option>`).join("");
    $("#listenSel").onchange = (e) => {
      const id = TL?.setListen(e.target.value) || "normal";
      const p = BeatSim.profile(id);
      $("#listenBadge").hidden = id === "normal";
      $("#listenBadge").textContent = p.badge;
      document.body.classList.toggle("kb-sim-on", id !== "normal");
      setStatus(id === "normal" ? "Dinleme: Normal" : `${p.badge} — yalnız dinleme; bounce etkilenmez.`);
      e.target.blur();
    };
  }

  // ================= Asama 2a: referans A/B =================
  function refOf() {
    const r = PROJ?.reference;
    if (r && r.path) return r;
    return PROJ?.reference_path ? { path: PROJ.reference_path, gain_db: 0, start: 0 } : null;
  }
  async function syncReference() {
    const r = refOf();
    $("#abToggle").disabled = !r;
    renderRefBox();
    if (!TL) return;
    if (!r) { TL.setReference(null); setAB("A", true); return; }
    const ok = await TL.setReference({ path: r.path, gain_db: Number(r.gain_db) || 0, start: Number(r.start) || 0 });
    if (!ok) setStatus("Referans açılamadı (dosya taşınmış olabilir).");
  }
  function renderRefBox() {
    const r = refOf();
    $("#refName").textContent = r ? r.path.split(/[\\/]/).pop() : "Referans seçilmedi";
    $("#refName").title = r?.path || "";
    $("#refRemove").hidden = !r;
    $("#refStart").value = r ? String(Number(r.start) || 0) : "0";
    const g = r ? Number(r.gain_db) || 0 : 0;
    $("#refGain").value = String(g);
    $("#refGainVal").textContent = `${g > 0 ? "+" : ""}${g.toFixed(1)} dB`;
    const an = r?.analysis;
    $("#refMatch").textContent = an ? `${an.match_text}${an.ref_lufs != null ? ` · Referans ${an.ref_lufs} LUFS` : ""}${an.mix_lufs != null ? ` · Miks ${an.mix_lufs.toFixed(1)} LUFS` : ""}` : (r ? "Ölçülmedi — “Yeniden ölç”." : "");
    $("#refNotes").innerHTML = (an?.notes || []).map((t) => `<li>${esc(t)}</li>`).join("");
  }
  function ensureRef() {
    if (!PROJ.reference || typeof PROJ.reference !== "object") PROJ.reference = { path: "", gain_db: 0, start: 0 };
    if (!PROJ.reference.path && PROJ.reference_path) PROJ.reference.path = PROJ.reference_path;
    return PROJ.reference;
  }
  async function measureRef() {
    const r = refOf();
    if (!PROJ || !r) return;
    await flushSave();
    setStatus("Referans ve miks ölçülüyor (LUFS + spektrum)…");
    $("#refMatch").textContent = "Ölçülüyor…";
    const res = await runJob("beat_reference_analyze", [PROJ.id, r.path, Number(r.start) || 0]);
    if (!res?.ok) { setStatus("Referans ölçülemedi: " + (res?.error || "?")); renderRefBox(); return; }
    const ref = ensureRef();
    if (res.match?.ok) ref.gain_db = res.match.gain_db;
    ref.analysis = { ref_lufs: res.ref_lufs, mix_lufs: res.mix_lufs, match_text: res.warning || res.match?.text || "",
      notes: (res.notes || []).map((n) => n.text), at: Date.now() };
    scheduleSave();
    TL?.setRefGain(ref.gain_db);
    renderRefBox();
    setStatus(res.warning || res.match?.text || "Referans ölçüldü.");
  }
  function setAB(mode, quiet) {
    if (!TL) return;
    if (mode === "B" && !TL.hasReference()) { if (!quiet) setStatus(refOf() ? "Referans yükleniyor…" : "Önce “Referans…” ile bir şarkı seç."); mode = "A"; }
    const m = TL.setAB(mode);
    AB_MODE = m;
    $("#abToggle").textContent = m === "B" ? "A/B: Referans" : "A/B: Miks";
    $("#abToggle").classList.toggle("on", m === "B");
    if (!quiet) {
      const g = Number(refOf()?.gain_db) || 0;
      setStatus(m === "B" ? `B: Referans (seviye eşitli ${g > 0 ? "+" : ""}${g.toFixed(1)} dB)${TL.isPlaying() ? "" : " — Boşluk ile çal"}` : "A: Miks");
    }
  }
  function toggleAB() { setAB(AB_MODE === "B" ? "A" : "B"); }
  $("#abToggle").onclick = (e) => { e.currentTarget.blur(); toggleAB(); };
  $("#refPick").onclick = (e) => {
    e.currentTarget.blur();
    const box = $("#refBox");
    box.hidden = !box.hidden;
    if (!box.hidden) { const rc = $("#refPick").getBoundingClientRect(); box.style.top = `${rc.bottom + 6}px`; box.style.left = `${Math.max(8, Math.min(rc.left, window.innerWidth - 380))}px`; renderRefBox(); }
  };
  $("#refClose").onclick = () => { $("#refBox").hidden = true; };
  $("#refChoose").onclick = async () => {
    if (!PROJ) return;
    const pr = await api()?.beat_pick_audio?.();
    if (!pr?.path) return;
    const ref = ensureRef();
    Object.assign(ref, { path: pr.path, gain_db: 0, start: 0 });
    delete ref.analysis;
    PROJ.reference_path = pr.path;
    scheduleSave();
    await syncReference();
    measureRef();
  };
  $("#refRemove").onclick = () => {
    if (!PROJ) return;
    PROJ.reference = { path: "", gain_db: 0, start: 0 };
    PROJ.reference_path = "";
    scheduleSave();
    syncReference();
    setStatus("Referans kaldırıldı.");
  };
  $("#refMeasure").onclick = () => measureRef();
  $("#refGain").addEventListener("input", (e) => {
    if (!refOf()) return;
    const g = Number(e.target.value) || 0;
    ensureRef().gain_db = g;
    $("#refGainVal").textContent = `${g > 0 ? "+" : ""}${g.toFixed(1)} dB`;
    TL?.setRefGain(g);
    scheduleSave();
  });
  $("#refStart").addEventListener("change", (e) => {
    if (!refOf()) return;
    ensureRef().start = Math.max(0, Number(e.target.value) || 0);
    scheduleSave();
    syncReference();
  });
  $("#refStart").addEventListener("keydown", (e) => e.stopPropagation());

  $("#vstList").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-addvst]"); if (!b || !PROJ) return;
    const c = fxCtx();
    if (!c.tr) return;
    let at = -1;
    fxEdit(`${b.dataset.vstname} → ${c.level === "clip" ? "klip" : c.tr.name} zincirine eklendi.`, (cc) => {
      const ch = ownerChain(cc);
      ch.push({ type: "vst3", name: b.dataset.vstname, path: b.dataset.addvst });
      at = ch.length - 1;
    });
    if (at >= 0) openFxPanel(at);
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
        showRelease(r.release_warnings);
      } else setStatus("Bounce hatası: " + (r?.error || "?"));
    } finally { btn.disabled = false; }
  };

  $("#toStudioBtn").onclick = async () => {
    if (!PROJ) return;
    await flushSave();
    const rc = await api()?.beat_release_check?.(PROJ.id).catch(() => null);   // 1e: disa aktarma oncesi lisans uyarisi
    if (rc?.ok) showRelease(rc.warnings);
    setStatus("Kami Studio lirik video hazırlanıyor…");
    await flushSave();
    const r = await api()?.beat_export_lyric_video?.(PROJ.id, PROJ.name);
    setStatus(r?.ok ? "✓ Kami Studio açıldı ve sözler aktarıldı." : ("Hata: " + (r?.error || "?")));
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
    if (st.last_upload.target === "idea") { LIB?.ideasChanged(st.last_upload.idea); return true; }   // 1e-2: fikir rafina geldi
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
    $("#hudTrack").textContent = "→ " + ((PROJ?.tracks || []).find((x) => x.id === plan.tid)?.name || plan.tid)
      + (plan.layer ? ` · ${LAYER_LBL[plan.layer.kind]} (ana vokal kulaklıkta)` : "");
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
    if (AB_MODE === "B") setAB("A", true);      // 2a: kayitta beat duyulsun (referans degil)
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
    } else if ($("#tlLayer").value !== "main") {
      if (REC_PREP) return;
      REC_PREP = true;
      try { plan = await layerPlan($("#tlLayer").value, bpmv); } finally { REC_PREP = false; }
      if (!plan || RECST) return;
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

  // ---------------- 1d: Double / Adlib / Chant katman kaydi ----------------
  let REC_PREP = false;
  /** Katman kaydinin plani: hedef kanal Python'da secilir/olusturulur (beat_layer_prepare), ana vokal kulaklikta calar.
      Double/Chant: secili ana vokal klibi (ya da dongu bolgesi) uzerine; klip sonunda otomatik durur. */
  async function layerPlan(kind, bpmv) {
    const sel = [...TL.selection()].map((id) => TL.findClip(id)).filter(Boolean);
    const selTr = selTrack();
    let main = sel.length === 1 && sel[0].tr.role === "vocal" && !sel[0].tr.layer ? sel[0].tr
      : selTr && selTr.role === "vocal" ? (selTr.layer ? PROJ.tracks.find((t) => t.id === selTr.layer_of) : selTr) : null;
    main = main || PROJ.tracks.find((t) => t.id === "vocal1") || PROJ.tracks.find((t) => t.role === "vocal" && !t.layer);
    if (!main) { setStatus("Ana vokal kanalı yok."); return null; }
    const L = TL.loopRegion();
    const mainClip = sel.length === 1 && sel[0].tr.id === main.id ? sel[0].clip : null;
    let t0, t1;
    if (L) { t0 = L.a; t1 = L.b; }
    else if (mainClip) [t0, t1] = BeatClips.clipBounds(mainClip);
    else if (kind === "adlib") { t0 = TL.getPlayhead(); t1 = t0 + 1; }
    else { setStatus(`${LAYER_LBL[kind]} için önce ana vokal klibini seç (ya da cetvelde döngü bölgesi çiz).`); return null; }
    const r = await api()?.beat_layer_prepare?.(PROJ.tracks, kind, main.id, t0, t1, PROJ.id).catch(() => null);
    if (!r?.ok) { setStatus("Katman kanalı hazırlanamadı: " + ({ too_many_tracks: "en fazla 24 kanal" }[r?.error] || r?.error || "?")); return null; }
    if (r.created) edit(`${LAYER_LBL[kind]} kanalı oluşturuldu: ${(r.tracks.find((t) => t.id === r.track_id) || {}).name || ""}`, () => { PROJ.tracks = r.tracks; });
    if (main.mute) setStatus("Uyarı: ana vokal sessizde (M) — kulaklıkta duyulmaz.");
    const layer = { kind, main: main.id };
    const tid = r.track_id;
    if (L) {
      const cnt = BeatTransport.countInPlan(L.a, bpmv, RECSET.count);
      return { mode: "loop", tid, a: L.a, b: L.b, ustart: cnt.transport_start, keep_from: cnt.rec_from, loop: L,
        countIn: cnt.beats ? { origin: cnt.rec_from, ticks: cnt.ticks } : null, stopAtU: null, layer };
    }
    if (mainClip) {
      const pre = Math.max(0, Number(RECSET.preroll) || 0);
      const cnt = BeatTransport.countInPlan(t0, bpmv, RECSET.count);
      const keep = Math.max(0, t0 - 0.5);   // yarim saniyelik nefes / giris payi kayda girer (hizalayiciya baglam)
      return { mode: "linear", tid, ustart: Math.min(cnt.transport_start, t0 - pre), keep_from: keep, loop: null,
        countIn: cnt.beats ? { origin: cnt.rec_from, ticks: cnt.ticks } : null, stopAtU: t1 + 0.3, layer };
    }
    const cnt = BeatTransport.countInPlan(t0, bpmv, RECSET.count);
    return { mode: "linear", tid, ustart: cnt.transport_start, keep_from: cnt.rec_from, loop: null,
      countIn: cnt.beats ? { origin: cnt.rec_from, ticks: cnt.ticks } : null, stopAtU: null, layer };
  }

  /** Katman kaydi bitti: yerlesim (pan/ses, chant sapmasi) + Double/Chant icin hizalama onerisi. */
  async function afterLayerRecording(plan, ids) {
    const kind = plan.layer.kind, mainId = plan.layer.main;
    const tr = PROJ?.tracks.find((t) => t.id === plan.tid);
    if (!tr || !ids.length) return;
    const lr = await api()?.beat_layer_layout?.(PROJ.tracks, mainId, PROJ.id).catch(() => null);
    const delay = kind === "chant" ? Number(((lr?.tracks || []).find((t) => t.id === plan.tid) || tr).chant_dev?.delay_ms || 0) : 0;
    edit(`${LAYER_LBL[kind]} yerleştirildi${delay ? ` (+${delay} ms chant sapması)` : ""}`, () => {
      if (lr?.ok) PROJ.tracks = lr.tracks;
      if (delay) {
        const t2 = PROJ.tracks.find((t) => t.id === plan.tid);
        if (t2) t2.clips = t2.clips.map((c) => (ids.includes(c.id) ? BeatClips.normalize(Object.assign({}, c, { start: Math.max(0, c.start + delay / 1000) })) : c));
      }
    });
    if (kind === "adlib") return;
    const cid = ids[ids.length - 1];
    const t3 = PROJ.tracks.find((t) => t.id === plan.tid);
    const base = JSON.stringify(t3?.clips || []);
    setStatus(`${LAYER_LBL[kind]} kaydedildi — ana vokale hizalanıyor…`);
    const r = await runJob("beat_layer_align", [PROJ.id, plan.tid, cid, mainId, delay, PROJ]);
    if (!r?.ok) {
      setStatus(`${LAYER_LBL[kind]} hizalanamadı: ` + ({ no_signal: "sinyal yok", too_short: "kayıt çok kısa", no_main_vocal: "altında ana vokal yok" }[r?.error] || r?.error || "?"));
      return;
    }
    showAlign(r, kind, base);
  }

  let ALIGN_DONE = -1, ALIGN_T = 0;
  function hideAlign() { $("#alignBar").hidden = true; ALIGN = null; ALIGN_DONE = -1; clearTimeout(ALIGN_T); }
  function showAlign(r, kind, base) {
    const tr = PROJ?.tracks.find((t) => t.id === r.track_id);
    if (!tr) return;
    clearTimeout(ALIGN_T);
    const off = Number(r.offset_ms) || 0;
    const sh = (ms) => `${ms > 0 ? "−" : "+"}${Math.abs(ms).toFixed(1)} ms`;
    const txt = r.split ? `${r.segments.length} parçaya bölünüp ayrı kaydırılır (${r.segments.map((x) => sh(x.offset_ms)).join(" / ")})`
      : Math.abs(off) < 1 ? "zaten hizalı (±1 ms)" : `${sh(off)} kaydırılır`;
    ALIGN = { tid: r.track_id, clips: r.clips, base, kind };
    ALIGN_DONE = -1;
    $("#alignTxt").innerHTML = `<b>${esc(LAYER_LBL[kind] || "Katman")} hizalama önerisi:</b> ${esc(txt)} · güven ${Math.round((r.confidence || 0) * 100)}%`;
    $("#alignApply").textContent = "Uygula";
    $("#alignApply").hidden = !r.split && Math.abs(off) < 1;
    $("#alignDismiss").textContent = "Vazgeç";
    $("#alignBar").hidden = false;
    setStatus(`${LAYER_LBL[kind]} hizalama önerisi hazır — Uygula ya da Vazgeç`);
  }
  $("#alignApply").onclick = () => {
    if (!PROJ) return;
    if (!ALIGN) {   // uygulandiktan sonra: Geri al
      if (ALIGN_DONE >= 0 && UNDO.length === ALIGN_DONE) undo();
      hideAlign();
      return;
    }
    const tr = PROJ.tracks.find((t) => t.id === ALIGN.tid);
    if (!tr || JSON.stringify(tr.clips) !== ALIGN.base) { setStatus("Kanal o arada değişti — hizalama önerisi geçersiz, yeniden kaydet ya da elle kaydır."); hideAlign(); return; }
    const kind = ALIGN.kind, clips = ALIGN.clips;
    edit(`✓ ${LAYER_LBL[kind] || "Katman"} hizalandı (tek geri al)`, () => { tr.clips = clips; });
    ALIGN = null;
    ALIGN_DONE = UNDO.length;
    $("#alignTxt").innerHTML = `<b>✓ Hizalama uygulandı</b>`;
    $("#alignApply").textContent = "Geri al";
    $("#alignApply").hidden = false;
    $("#alignDismiss").textContent = "Kapat";
    ALIGN_T = setTimeout(hideAlign, 8000);
  };
  $("#alignDismiss").onclick = () => { if (ALIGN) setStatus("Hizalama önerisi uygulanmadı."); hideAlign(); };
  $("#tlLayer").onchange = (e) => {
    e.target.classList.toggle("on", e.target.value !== "main");
    e.target.blur();
    const v = e.target.value;
    setStatus(v === "main" ? "Katman: Ana — normal kayıt" : v === "adlib" ? "Katman: Adlib — çalma çizgisinden, dönüşümlü sol/sağ adlib kanalına"
      : `Katman: ${LAYER_LBL[v]} — ana vokal klibini seç (ya da döngü çiz), kayda bas`);
  };

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
      if (plan.layer) afterLayerRecording(plan, ids);
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
    const r = await api()?.booth_server_start?.(PROJ?.id || "", recTrackId(), $("#boothTarget").value);
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

  // ---- 1e-2: iPhone Booth hedefi (proje kanali / fikir rafi) ----
  try { const bt = localStorage.getItem("kb.boothTarget"); if (bt === "idea" || bt === "track") $("#boothTarget").value = bt; } catch {}
  $("#boothTarget").onchange = async (e) => {
    const v = e.target.value;
    try { localStorage.setItem("kb.boothTarget", v); } catch {}
    if (BOOTH_RUNNING) await api()?.booth_server_target?.(PROJ?.id || "", recTrackId(), v).catch(() => null);
    setStatus(v === "idea" ? "iPhone kayıtları fikir rafına gidecek." : "iPhone kayıtları seçili vokal kanalına gidecek.");
  };

  // ---- 1e-1: yayin oncesi lisans uyarisi ----
  function showRelease(list) {
    const items = (list || []).filter(Boolean);
    if (!items.length) return;
    if (!items.some((w) => w.level === "block" || w.level === "warn")) {   // yalniz bilgi: durum cubugunda
      setStatus("ℹ " + items.map((w) => w.message).join(" · "));
      return;
    }
    $("#releaseList").innerHTML = items.map((w) => `<div class="kb-rel-item ${esc(w.level)}"><b>${esc(w.title)}</b><br>${esc(w.message)}${w.credit_text ? `<br><code>${esc(w.credit_text)}</code>` : ""}</div>`).join("");
    const cred = (items.find((w) => w.credit_text) || {}).credit_text || "";
    $("#releaseCopy").hidden = !cred;
    $("#releaseCopy").dataset.txt = cred;
    $("#releaseCopy").textContent = `“${cred}” kopyala`;
    $("#releaseBox").hidden = false;
    $("#releaseOk").focus();
  }
  $("#releaseOk").onclick = () => { $("#releaseBox").hidden = true; };
  $("#releaseCopy").onclick = (e) => {
    const t = e.currentTarget.dataset.txt || "";
    if (LIB) LIB.copyText(t); else navigator.clipboard?.writeText(t).then(() => setStatus("Kopyalandı: " + t));
  };

  // ---- 1e: raftan / fikirlerden zaman cizelgesine surukle-birak ----
  $("#tlScroll").addEventListener("dragover", (e) => {
    if (LIB?.dragKind(e)) { e.preventDefault(); e.dataTransfer.dropEffect = "copy"; }
  });
  $("#tlScroll").addEventListener("drop", (e) => {
    if (!LIB?.dragKind(e) || !TL?.dropAt) return;
    e.preventDefault();
    LIB.dropOnTimeline(e, TL.dropAt(e));
  });

  // ---- 1d-2: kulaklikta efektli dinleme (varsayilan KAPALI; kayda ham ses) ----
  const MONSET = Object.assign({ room: true, tune: false, block: 128 },
    (() => { try { return JSON.parse(localStorage.getItem("kb.mon") || "{}"); } catch { return {}; } })());
  $("#monRoom").checked = !!MONSET.room;
  $("#monTune").checked = !!MONSET.tune;
  $("#monBlock").value = String(MONSET.block === 256 ? 256 : 128);
  const MON_ERR = { sounddevice_missing: "Ses akışı kurulamadı: sounddevice kurulu değil — özellik pasif.",
    stream_failed: "Ses akışı kurulamadı", already_running: "Zaten açık." };
  function syncMon(st, err) {
    const on = !!st?.running;
    $("#monOn").checked = on;
    const lat = $("#monLat"), msg = $("#monSt");
    lat.hidden = !on;
    msg.classList.remove("warn", "bad");
    if (err) { msg.textContent = err; msg.classList.add("bad"); return; }
    if (!on) { msg.textContent = "Kapalı — kuru dinleme."; return; }
    lat.textContent = `${Math.round(st.latency_ms)} ms`;
    lat.classList.toggle("warn", !!st.warn);
    const extra = [];
    if (st.engine === "numpy") extra.push("pedalboard yok: basit oda havası");
    if (st.engine === "dry") extra.push("efektsiz");
    if ((st.notes || []).includes("tune_unavailable")) extra.push("ton düzeltme eklentisi bulunamadı (VST3: Graillon / MAutoPitch / Auto-Tune)");
    msg.textContent = st.message + (extra.length ? ` · ${extra.join(" · ")}` : "");
    if (st.warn) msg.classList.add("warn");
  }
  async function monStart() {
    const r = await api()?.beat_monitor_start?.(+$("#micSel").value, -1, $("#monRoom").checked, $("#monTune").checked, +$("#monBlock").value).catch(() => null);
    if (!r?.ok) {
      syncMon(null, (MON_ERR[r?.error] || "Efektli dinleme açılamadı") + (r?.detail && r?.error !== "sounddevice_missing" ? `: ${r.detail}` : ""));
      return false;
    }
    syncMon(r);
    setStatus(r.message + (r.warn ? "" : " — kayda ham ses girer"));
    return true;
  }
  async function monStop() {
    const r = await api()?.beat_monitor_stop?.().catch(() => null);
    if (r && !r.ok && r.error === "recording_active") { $("#monOn").checked = true; setStatus("Kayıt sürerken efektli dinleme kapatılamaz — önce kaydı durdur."); return false; }
    syncMon(null);
    return true;
  }
  $("#monOn").onchange = (e) => { if (e.target.checked) monStart(); else monStop(); };
  async function monRestart() {
    MONSET.room = $("#monRoom").checked; MONSET.tune = $("#monTune").checked; MONSET.block = +$("#monBlock").value;
    try { localStorage.setItem("kb.mon", JSON.stringify(MONSET)); } catch {}
    if (!$("#monOn").checked) return;
    if (RECST) { setStatus("Ayar kayıttan sonra uygulanır."); return; }
    if (await monStop()) monStart();
  }
  $("#monRoom").onchange = monRestart;
  $("#monTune").onchange = monRestart;
  $("#monBlock").onchange = monRestart;
  $("#micSel").addEventListener("change", () => { if ($("#monOn").checked && !RECST) monRestart(); });

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
