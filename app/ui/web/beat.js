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
  let VU_TIMER = 0;
  let LAST_MASH_OUT = "";
  const PEAKS_CACHE = new Map();
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

  function buildRuler() {
    const box = $("#rulerTicks");
    if (!box) return;
    box.innerHTML = Array.from({ length: 16 }, (_, i) => `<span class="kb-tick">${i * 4 + 1}</span>`).join("");
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
    buildRuler();
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

  async function loadProj(id) {
    const r = await api()?.beat_load_project?.(id).catch(() => null);
    if (r?.ok) { PROJ = r.project; renderProject(); }
  }

  function selTrack() {
    const tracks = PROJ?.tracks || [];
    return tracks.find((x) => x.id === SEL_TID) || tracks.find((x) => x.role === "vocal") || tracks[0] || null;
  }

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
    $("#metaPill").textContent = `${Math.round(PROJ.bpm || 120)} BPM · ${PROJ.key || "—"}`;
    $("#lyrInput").value = PROJ.lyrics || "";
    $("#abToggle").disabled = !PROJ.reference_path;
    analyzeLyricsUI();

    const tracks = PROJ.tracks || [];
    if (!tracks.some((t) => t.id === SEL_TID) && tracks.length) SEL_TID = tracks[0].id;

    const wrap = $("#tracksWrap");
    wrap.innerHTML = tracks.map((tr) => {
      const takes = tr.takes || [];
      const presetOpts = Object.entries(PRESETS).map(([k, v]) => `<option value="${esc(k)}" ${tr.preset === k ? "selected" : ""}>${esc(v.name)}</option>`).join("");
      const takeOpts = takes.map((t) => `<option value="${esc(t.id)}" ${tr.active_take === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("");
      const fileBase = (tr.path || "").split(/[\\/]/).pop();
      const selCls = tr.id === SEL_TID ? "sel" : "";
      const roleAttr = tr.role === "beat" ? "beat" : (tr.role === "vocal" ? "vocal" : "other");
      return `
        <div class="kb-lane ${selCls}" data-tid="${esc(tr.id)}" data-role="${roleAttr}">
          <div class="kb-ch">
            <span class="kb-role-bar"></span>
            <div class="kb-ch-top">
              <b>${esc(tr.name)}</b>
              <button type="button" class="kb-ms ${tr.mute ? "m-on" : ""}" data-mute="${esc(tr.id)}" title="Sessize Al (Mute)">M</button>
              <button type="button" class="kb-ms ${tr.solo ? "s-on" : ""}" data-solo="${esc(tr.id)}" title="Tek Çal (Solo)">S</button>
            </div>
            <div class="kb-ch-mid">
              <button type="button" class="btn" data-pick="${esc(tr.id)}">📂 Ses</button>
              ${takes.length ? `<select class="kb-sel" data-take="${esc(tr.id)}" title="Take Comping">${takeOpts}</select>` : ""}
              ${tr.role === "vocal" ? `<select class="kb-sel" data-preset="${esc(tr.id)}" title="Vokal Şablonu"><option value="">Şablon…</option>${presetOpts}</select>` : ""}
            </div>
            <div class="kb-ch-bot">
              <span>Ses</span>
              <input type="range" data-vol="${esc(tr.id)}" min="-24" max="6" step="0.5" value="${tr.volume_db ?? 0}">
              <span class="kb-db-val">${(tr.volume_db ?? 0) > 0 ? "+" : ""}${tr.volume_db ?? 0} dB</span>
              <input type="range" data-pan="${esc(tr.id)}" min="-1" max="1" step="0.05" value="${tr.pan ?? 0}" style="max-width:46px" title="Pan (L/R)">
              <input type="number" data-off="${esc(tr.id)}" value="${tr.offset_ms ?? 0}" step="5" title="Gecikme (ms)">
            </div>
          </div>
          <div class="kb-wf-wrap" data-wfwrap="${esc(tr.id)}">
            <canvas class="kb-wf-canvas" data-wave="${esc(tr.id)}"></canvas>
            <div class="kb-lane-playhead" data-ph="${esc(tr.id)}"></div>
            ${fileBase
              ? `<span class="kb-wf-meta">▶ ${esc(fileBase)}</span>`
              : `<div class="kb-wf-empty">Ses eklemek için "📂 Ses" seçin veya dosyayı buraya sürükleyin</div>`}
          </div>
        </div>`;
    }).join("");

    renderFxRack();

    tracks.forEach(async (tr) => {
      const cvs = wrap.querySelector(`canvas[data-wave="${tr.id}"]`);
      if (!cvs) return;
      if (!tr.path) {
        drawWaveform(cvs, [], "#9D6BFF");
        return;
      }
      let peaks = PEAKS_CACHE.get(tr.path);
      if (!peaks && api()?.beat_waveform) {
        const wr = await api().beat_waveform(tr.path, 220).catch(() => null);
        peaks = wr?.peaks || [];
        if (peaks.length) PEAKS_CACHE.set(tr.path, peaks);
      }
      const color = tr.role === "beat" ? "#14F195" : "#9D6BFF";
      const mid = tr.role === "beat" ? "#7CF9C4" : "#C4B5FD";
      drawWaveform(cvs, peaks || [], color, mid);
    });
  }

  async function playPath(path, label = "", frac = 0) {
    if (!path) {
      setStatus("Bu kanalda henüz ses dosyası yok.");
      return false;
    }
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

  function syncPlayheadUI() {
    const a = aud();
    const dur = a.duration || 0;
    const cur = a.currentTime || 0;
    const pct = dur > 0 ? Math.min(100, Math.max(0, (cur / dur) * 100)) : 0;
    $("#lcdTime").textContent = fmtTime(cur);
    $("#masterProg").style.width = pct + "%";
    $("#trPlay").classList.toggle("on", !a.paused && !!a.src);
    $("#trPlay").textContent = (!a.paused && !!a.src) ? "⏸" : "▶";
    document.querySelectorAll(".kb-lane-playhead").forEach((ph) => {
      const tr = (PROJ?.tracks || []).find((x) => x.id === ph.dataset.ph);
      const match = tr?.path && tr.path === ACTIVE_AUDIO_PATH && dur > 0;
      ph.style.display = match ? "block" : "none";
      if (match) ph.style.left = pct + "%";
    });
  }

  aud().addEventListener("timeupdate", syncPlayheadUI);
  aud().addEventListener("play", syncPlayheadUI);
  aud().addEventListener("pause", syncPlayheadUI);
  aud().addEventListener("ended", syncPlayheadUI);

  $("#kbRuler").onclick = (e) => {
    const a = aud();
    if (!a.duration) return;
    const rc = e.currentTarget.getBoundingClientRect();
    const frac = Math.min(1, Math.max(0, (e.clientX - rc.left) / rc.width));
    a.currentTime = a.duration * frac;
    syncPlayheadUI();
  };

  $("#trPlay").onclick = async () => {
    const a = aud();
    if (a.src) {
      if (a.paused) a.play().catch(() => {});
      else a.pause();
      return;
    }
    const tr = selTrack();
    const targetPath = PROJ?.last_mixdown || tr?.path || (PROJ?.tracks || []).find((x) => x.path)?.path || "";
    if (targetPath) await playPath(targetPath, tr?.name || "Önizleme");
    else setStatus("Oynatmak için kanala ses ekle veya Mixdown al.");
  };
  $("#trStop").onclick = () => {
    const a = aud();
    a.pause();
    try { a.currentTime = 0; } catch {}
    syncPlayheadUI();
  };
  $("#trRew").onclick = () => {
    const a = aud();
    try { a.currentTime = 0; } catch {}
    syncPlayheadUI();
  };
  $("#trRec").onclick = () => $("#pcRecBtn")?.click();

  async function saveProj() {
    if (PROJ && api()?.beat_save_project) await api().beat_save_project(PROJ).catch(() => {});
  }

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
      $("#studioPane").hidden = mash;
      $("#mashupPane").hidden = !mash;
      $("#kbSide").hidden = mash;
      $("#kbBody").classList.toggle("mash", mash);
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
    const cr = await api()?.beat_create_project?.("Yeni Parça " + new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }));
    if (cr?.ok) { PROJ = cr.project; await refreshProjSelect(); renderProject(); }
  };

  // ---- Track Lane Interactions ----
  $("#tracksWrap").addEventListener("click", async (e) => {
    const lane = e.target.closest(".kb-lane[data-tid]");
    if (lane && lane.dataset.tid !== SEL_TID) {
      SEL_TID = lane.dataset.tid;
      document.querySelectorAll(".kb-lane").forEach((x) => x.classList.toggle("sel", x.dataset.tid === SEL_TID));
      renderFxRack();
    }

    const wfWrap = e.target.closest(".kb-wf-wrap[data-wfwrap]");
    if (wfWrap && PROJ) {
      const tr = PROJ.tracks.find((x) => x.id === wfWrap.dataset.wfwrap);
      if (tr?.path) {
        const rc = wfWrap.getBoundingClientRect();
        const frac = Math.min(0.98, Math.max(0, (e.clientX - rc.left) / rc.width));
        await playPath(tr.path, tr.name, frac);
      } else {
        const pick = await api()?.beat_pick_audio?.();
        if (pick?.path) {
          const ar = await api().beat_add_take(PROJ.id, tr.id, pick.path);
          if (ar?.ok) { PROJ = ar.project; renderProject(); setStatus("Ses kanala eklendi."); }
        }
      }
      return;
    }

    const b = e.target.closest("button");
    if (!b || !PROJ) return;
    if (b.dataset.pick) {
      const pr = await api()?.beat_pick_audio?.();
      if (pr?.path) {
        const ar = await api().beat_add_take(PROJ.id, b.dataset.pick, pr.path);
        if (ar?.ok) { PROJ = ar.project; renderProject(); setStatus("Ses kanala eklendi."); }
      }
    } else if (b.dataset.mute) {
      const tr = PROJ.tracks.find((x) => x.id === b.dataset.mute);
      if (tr) { tr.mute = !tr.mute; await saveProj(); renderProject(); }
    } else if (b.dataset.solo) {
      const tr = PROJ.tracks.find((x) => x.id === b.dataset.solo);
      if (tr) { tr.solo = !tr.solo; await saveProj(); renderProject(); }
    }
  });

  $("#tracksWrap").addEventListener("change", async (e) => {
    if (!PROJ) return;
    const el = e.target;
    if (el.dataset.preset) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.preset);
      const p = PRESETS[el.value];
      if (tr && p) {
        tr.preset = el.value; tr.denoise = !!p.denoise; tr.fx = JSON.parse(JSON.stringify(p.fx));
        SEL_TID = tr.id;
        await saveProj(); renderProject(); setStatus(`${p.name} uygulandı.`);
      }
    } else if (el.dataset.take) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.take);
      const tk = tr?.takes?.find((t) => t.id === el.value);
      if (tr && tk) { tr.active_take = tk.id; tr.path = tk.path; await saveProj(); renderProject(); }
    } else if (el.dataset.off) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.off);
      if (tr) { tr.offset_ms = +el.value || 0; await saveProj(); }
    }
  });

  $("#tracksWrap").addEventListener("input", (e) => {
    if (!PROJ) return;
    const el = e.target;
    if (el.dataset.vol) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.vol);
      if (tr) {
        tr.volume_db = +el.value;
        el.nextElementSibling.textContent = `${tr.volume_db > 0 ? "+" : ""}${tr.volume_db} dB`;
        saveProj();
      }
    } else if (el.dataset.pan) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.pan);
      if (tr) { tr.pan = +el.value; saveProj(); }
    }
  });

  // ---- Bottom FX Rack Interactions ----
  $("#fxRack").addEventListener("click", async (e) => {
    if (!PROJ) return;
    const delBtn = e.target.closest("[data-delfx]");
    if (delBtn) {
      e.stopPropagation();
      const [tid, idx] = delBtn.dataset.delfx.split(":");
      const tr = PROJ.tracks.find((x) => x.id === tid);
      if (tr) { tr.fx.splice(+idx, 1); await saveProj(); renderFxRack(); }
      return;
    }
    const mod = e.target.closest("[data-togglefx]");
    if (mod) {
      const [tid, idx] = mod.dataset.togglefx.split(":");
      const tr = PROJ.tracks.find((x) => x.id === tid);
      const fx = tr?.fx?.[+idx];
      if (fx) { fx.bypass = !fx.bypass; await saveProj(); renderFxRack(); }
    }
  });

  $("#vstList").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-addvst]"); if (!b || !PROJ) return;
    const tr = selTrack();
    if (tr) {
      tr.fx.push({ type: "vst3", name: b.dataset.vstname, path: b.dataset.addvst });
      await saveProj(); renderFxRack(); setStatus(`${b.dataset.vstname} → ${tr.name} zincirine eklendi.`);
    }
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
    const r = await api()?.beat_ai_mix?.(PROJ.id, txt, targetId);
    if (r?.ok) { PROJ = r.project; renderProject(); setStatus("AI Miks: " + (r.actions || []).join(" · ")); }
  };

  $("#mixdownBtn").onclick = async () => {
    if (!PROJ) return;
    const btn = $("#mixdownBtn");
    btn.disabled = true;
    setStatus("Mixdown alınıyor (-14 LUFS)…");
    try {
      const r = await api()?.beat_render_mixdown?.(PROJ.id, "", -14.0);
      if (r?.ok) {
        PROJ.last_mixdown = r.path;
        setStatus("✓ Mixdown hazır: " + r.path);
        $("#lufsMsg").textContent = `LUFS: ${r.lufs ?? "—"} · Peak: ${r.peak_db ?? "—"} dB`;
        await playPath(r.path, `${PROJ.name} (Mixdown)`);
      } else setStatus("Mixdown hatası: " + (r?.error || "?"));
    } finally { btn.disabled = false; }
  };

  $("#toStudioBtn").onclick = async () => {
    if (!PROJ) return;
    setStatus("Kami Studio lirik video hazırlanıyor…");
    const r = await api()?.beat_export_lyric_video?.(PROJ.id, PROJ.name);
    setStatus(r?.ok ? "✓ Kami Studio açıldı ve sözler aktarıldı." : ("Hata: " + (r?.error || "?")));
  };

  $("#refPick").onclick = async () => {
    if (!PROJ) return;
    const pr = await api()?.beat_pick_audio?.();
    if (pr?.path) {
      PROJ.reference_path = pr.path; await saveProj(); $("#abToggle").disabled = false;
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

  $("#lyrInput").addEventListener("input", () => { analyzeLyricsUI(); saveProj(); });

  // ---- Booth PC Mic + iPhone Wireless ----
  $("#pcRecBtn").onclick = async () => {
    const recBtn = $("#pcRecBtn"), trRec = $("#trRec");
    if (!PC_REC) {
      const r = await api()?.booth_rec_start?.(PROJ?.id || "", "vocal1", +$("#micSel").value);
      if (r?.ok) {
        PC_REC = true;
        recBtn.classList.add("bad"); recBtn.classList.remove("pri"); recBtn.textContent = "⏹ Kaydı Durdur";
        trRec.classList.add("on");
        $("#pcRecSt").textContent = "Kayıt alınıyor…";
        clearInterval(VU_TIMER);
        VU_TIMER = setInterval(() => {
          $("#micVuFill").style.width = `${30 + Math.round(Math.random() * 62)}%`;
        }, 120);
      } else $("#pcRecSt").textContent = "Hata: " + (r?.error || "?");
    } else {
      PC_REC = false;
      clearInterval(VU_TIMER); VU_TIMER = 0; $("#micVuFill").style.width = "0%";
      recBtn.classList.remove("bad"); recBtn.classList.add("pri"); recBtn.textContent = "🎙 Kayda Başla";
      trRec.classList.remove("on");
      const r = await api()?.booth_rec_stop?.($("#micClean").checked);
      if (r?.ok) { $("#pcRecSt").textContent = `✓ Kaydedildi (${r.duration}s)`; if (PROJ) loadProj(PROJ.id); }
      else $("#pcRecSt").textContent = "Hata: " + (r?.error || "?");
    }
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
    const r = await api()?.booth_server_start?.(PROJ?.id || "", "vocal1");
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
      let lastTs = r.last_upload?.ts || 0;
      BOOTH_TIMER = setInterval(async () => {
        const st = await api()?.booth_server_status?.().catch(() => null);
        if (st?.last_upload?.ts && st.last_upload.ts > lastTs) {
          lastTs = st.last_upload.ts;
          if (PROJ) loadProj(PROJ.id);
          setStatus("✓ iPhone Booth'tan yeni take geldi!");
        }
      }, 2500);
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

  window.addEventListener("resize", () => {
    (PROJ?.tracks || []).forEach((tr) => {
      if (!tr.path) return;
      const peaks = PEAKS_CACHE.get(tr.path);
      const cvs = document.querySelector(`canvas[data-wave="${tr.id}"]`);
      if (cvs && peaks) drawWaveform(cvs, peaks, tr.role === "beat" ? "#14F195" : "#9D6BFF");
    });
  });

  init();
})();
