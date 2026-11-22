"use strict";
(() => {
  const api = () => window.pywebview?.api;
  const $ = (s) => document.querySelector(s);
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));

  let PROJ = null, PRESETS = {}, VSTS = [], AB_MODE = "A", PC_REC = false, BOOTH_TIMER = 0, BOOTH_RUNNING = false;
  const RHYME_COLORS = ["#9D6BFF", "#2EE6A6", "#F59E0B", "#EC4899", "#38BDF8", "#A3E635"];

  const setStatus = (t) => { $("#stMsg").textContent = t; };

  async function waitApi() {
    for (let i = 0; i < 40; i++) {
      if (api()?.beat_list_projects) return true;
      await new Promise((r) => setTimeout(r, 100));
    }
    return false;
  }

  async function init() {
    await waitApi();
    const [pr, vr, lr, dr] = await Promise.all([
      api().beat_presets().catch(() => ({ presets: {} })),
      api().beat_vst_scan().catch(() => ({ plugins: [] })),
      api().beat_list_projects().catch(() => ({ projects: [] })),
      api().booth_devices().catch(() => ({ devices: [] })),
    ]);
    PRESETS = pr?.presets || {};
    VSTS = vr?.plugins || [];
    renderVsts();
    renderMics(dr?.devices || []);

    const list = lr?.projects || [];
    if (list.length) {
      await loadProj(list[0].id);
    } else {
      const cr = await api().beat_create_project("İlk Parça");
      if (cr?.ok) PROJ = cr.project;
    }
    await refreshProjSelect();
    renderProject();
  }

  async function refreshProjSelect() {
    const lr = await api().beat_list_projects().catch(() => ({ projects: [] }));
    const sel = $("#projSelect");
    sel.innerHTML = (lr?.projects || []).map((p) => `<option value="${esc(p.id)}" ${PROJ && p.id === PROJ.id ? "selected" : ""}>${esc(p.name)} (${Math.round(p.bpm || 120)} BPM)</option>`).join("");
  }

  async function loadProj(id) {
    const r = await api().beat_load_project(id);
    if (r?.ok) { PROJ = r.project; renderProject(); }
  }

  function renderVsts() {
    $("#vstCount").textContent = String(VSTS.length);
    $("#vstList").innerHTML = VSTS.length ? VSTS.map((v) => `
      <div style="display:flex;justify-content:space-between;align-items:center;background:#100C18;padding:6px 8px;border-radius:7px;font-size:12px">
        <div><b>${esc(v.name)}</b><div style="color:var(--mut);font-size:11px">${esc(v.category)}</div></div>
        <button class="btn" data-addvst="${esc(v.path)}" data-vstname="${esc(v.name)}">+ Vokale Ekle</button>
      </div>`).join("") : '<div style="color:var(--mut)">VST3 bulunamadı.</div>';
  }

  function renderMics(devs) {
    $("#micSel").innerHTML = devs.length
      ? devs.map((d) => `<option value="${d.id}" ${d.default ? "selected" : ""}>${esc(d.name)}</option>`).join("")
      : '<option value="-1">Varsayılan Mikrofon</option>';
  }

  function renderProject() {
    if (!PROJ) return;
    $("#metaPill").textContent = `${Math.round(PROJ.bpm || 120)} BPM · ${PROJ.key || "—"}`;
    $("#lyrInput").value = PROJ.lyrics || "";
    $("#abToggle").disabled = !PROJ.reference_path;
    analyzeLyricsUI();

    const wrap = $("#tracksWrap");
    wrap.innerHTML = (PROJ.tracks || []).map((tr) => {
      const takes = tr.takes || [];
      const presetOpts = Object.entries(PRESETS).map(([k, v]) => `<option value="${esc(k)}" ${tr.preset === k ? "selected" : ""}>${esc(v.name)}</option>`).join("");
      const takeOpts = takes.map((t) => `<option value="${esc(t.id)}" ${tr.active_take === t.id ? "selected" : ""}>${esc(t.label)}</option>`).join("");
      const fxChips = (tr.fx || []).map((f, idx) => `<span class="kb-fx-chip">${esc(f.name || f.type)}<button data-delfx="${esc(tr.id)}:${idx}" title="Kaldır">✕</button></span>`).join("");
      return `<div class="kb-card" data-tid="${esc(tr.id)}">
        <div class="kb-tr-head">
          <b>${esc(tr.name)}</b>
          <button class="btn" data-pick="${esc(tr.id)}">Dosya Seç</button>
          ${takes.length ? `<select data-take="${esc(tr.id)}" title="Vocal Comping (Take seç)">${takeOpts}</select>` : ""}
          <button class="btn ${tr.mute ? "bad" : ""}" data-mute="${esc(tr.id)}">M</button>
          <button class="btn ${tr.solo ? "ok" : ""}" data-solo="${esc(tr.id)}">S</button>
          ${tr.role === "vocal" ? `<select data-preset="${esc(tr.id)}"><option value="">Şablon Seç…</option>${presetOpts}</select>` : ""}
          <span style="font-size:11px;color:var(--mut);margin-left:auto">${esc((tr.path || "").split(/[\\/]/).pop() || "Boş")}</span>
        </div>
        <div class="kb-wave" data-wave="${esc(tr.id)}"><span style="color:var(--mut);font-size:11px;margin:auto">Dalga formu</span></div>
        <div class="kb-ctrls">
          <label>Ses <input type="range" data-vol="${esc(tr.id)}" min="-24" max="6" step="0.5" value="${tr.volume_db ?? 0}"> <b>${tr.volume_db ?? 0} dB</b></label>
          <label>Pan <input type="range" data-pan="${esc(tr.id)}" min="-1" max="1" step="0.05" value="${tr.pan ?? 0}"></label>
          <label>Gecikme (ms) <input type="number" data-off="${esc(tr.id)}" value="${tr.offset_ms ?? 0}" step="5" style="width:68px"></label>
        </div>
        ${fxChips ? `<div class="kb-fx-list">${fxChips}</div>` : ""}
      </div>`;
    }).join("");

    (PROJ.tracks || []).forEach(async (tr) => {
      if (!tr.path) return;
      const wr = await api().beat_waveform(tr.path, 96).catch(() => null);
      const box = wrap.querySelector(`[data-wave="${tr.id}"]`);
      if (box && wr?.peaks?.length) {
        box.innerHTML = wr.peaks.map((p) => `<i style="height:${Math.max(10, Math.round(p * 100))}%"></i>`).join("");
      }
    });
  }

  async function saveProj() {
    if (PROJ) await api().beat_save_project(PROJ).catch(() => {});
  }

  async function analyzeLyricsUI() {
    const txt = $("#lyrInput").value;
    if (PROJ) PROJ.lyrics = txt;
    const r = await api().beat_lyrics_analyze(txt, PROJ?.bpm || 0).catch(() => null);
    if (!r?.ok) return;
    $("#lyrStats").textContent = `${r.total_lines} satır · ${r.total_syllables} hece · ${r.rhyme_groups} kafiye`;
    $("#lyrBars").innerHTML = (r.lines || []).filter((l) => l.text.trim()).map((l) => {
      const col = l.rhyme_group ? RHYME_COLORS[(l.rhyme_group - 1) % RHYME_COLORS.length] : "transparent";
      return `<div class="kb-lyr-line"><span class="kb-syl">${l.syllables}</span><span class="kb-rhyme" style="background:${col}"></span><span>${esc(l.text)}</span></div>`;
    }).join("");
  }

  // Olaylar
  document.querySelectorAll(".kb-tab").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".kb-tab").forEach((x) => x.classList.toggle("on", x === b));
    const mash = b.dataset.mode === "mashup";
    $("#studioPane").hidden = mash;
    $("#mashupPane").hidden = !mash;
    $("#kbSide").hidden = mash;
    $("#kbBody").classList.toggle("mash", mash);
  });

  document.querySelectorAll(".kb-side-tabs button").forEach((b) => b.onclick = () => {
    document.querySelectorAll(".kb-side-tabs button").forEach((x) => x.classList.toggle("on", x === b));
    ["booth", "lyrics", "vst"].forEach((k) => { $(`#pane-${k}`).hidden = b.dataset.side !== k; });
  });

  $("#projSelect").onchange = (e) => loadProj(e.target.value);
  $("#projNew").onclick = async () => {
    const cr = await api().beat_create_project("Yeni Parça " + new Date().toLocaleTimeString("tr-TR", { hour: "2-digit", minute: "2-digit" }));
    if (cr?.ok) { PROJ = cr.project; await refreshProjSelect(); renderProject(); }
  };

  $("#tracksWrap").addEventListener("click", async (e) => {
    const b = e.target.closest("button"); if (!b || !PROJ) return;
    if (b.dataset.pick) {
      const pr = await api().beat_pick_audio();
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
    } else if (b.dataset.delfx) {
      const [tid, idx] = b.dataset.delfx.split(":");
      const tr = PROJ.tracks.find((x) => x.id === tid);
      if (tr) { tr.fx.splice(+idx, 1); await saveProj(); renderProject(); }
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
      if (tr) { tr.volume_db = +el.value; el.nextElementSibling.textContent = `${tr.volume_db} dB`; saveProj(); }
    } else if (el.dataset.pan) {
      const tr = PROJ.tracks.find((x) => x.id === el.dataset.pan);
      if (tr) { tr.pan = +el.value; saveProj(); }
    }
  });

  $("#vstList").addEventListener("click", async (e) => {
    const b = e.target.closest("[data-addvst]"); if (!b || !PROJ) return;
    const tr = PROJ.tracks.find((x) => x.id === "vocal1") || PROJ.tracks[0];
    if (tr) {
      tr.fx.push({ type: "vst3", name: b.dataset.vstname, path: b.dataset.addvst });
      await saveProj(); renderProject(); setStatus(`${b.dataset.vstname} vokal zincirine eklendi.`);
    }
  });

  $("#vstScanBtn").onclick = async () => {
    const r = await api().beat_vst_scan();
    VSTS = r?.plugins || []; renderVsts();
  };

  $("#aiApplyBtn").onclick = async () => {
    if (!PROJ) return;
    const txt = $("#aiPrompt").value.trim(); if (!txt) return;
    setStatus("AI miks uygulanıyor…");
    const r = await api().beat_ai_mix(PROJ.id, txt, "vocal1");
    if (r?.ok) { PROJ = r.project; renderProject(); setStatus("AI Miks: " + (r.actions || []).join(" · ")); }
  };

  $("#mixdownBtn").onclick = async () => {
    if (!PROJ) return;
    const btn = $("#mixdownBtn");
    btn.disabled = true;
    setStatus("Mixdown alınıyor (-14 LUFS)…");
    try {
      const r = await api().beat_render_mixdown(PROJ.id, "", -14.0);
      if (r?.ok) {
        setStatus("✓ Mixdown hazır: " + r.path);
        $("#lufsMsg").textContent = `LUFS: ${r.lufs ?? "—"} · Peak: ${r.peak_db ?? "—"} dB`;
        api().player_show?.({ path: r.path });
      } else setStatus("Mixdown hatası: " + (r?.error || "?"));
    } finally { btn.disabled = false; }
  };

  $("#toStudioBtn").onclick = async () => {
    if (!PROJ) return;
    setStatus("Kami Studio lirik video hazırlanıyor…");
    const r = await api().beat_export_lyric_video(PROJ.id, PROJ.name);
    setStatus(r?.ok ? "✓ Kami Studio açıldı ve sözler aktarıldı." : ("Hata: " + (r?.error || "?")));
  };

  $("#refPick").onclick = async () => {
    if (!PROJ) return;
    const pr = await api().beat_pick_audio();
    if (pr?.path) {
      PROJ.reference_path = pr.path; await saveProj(); $("#abToggle").disabled = false;
      const lr = await api().beat_measure_lufs(pr.path);
      if (lr?.ok) $("#lufsMsg").textContent = `Referans LUFS: ${lr.lufs} · Peak: ${lr.peak_db} dB`;
    }
  };
  $("#abToggle").onclick = () => {
    if (!PROJ) return;
    AB_MODE = AB_MODE === "A" ? "B" : "A";
    $("#abToggle").textContent = AB_MODE === "A" ? "A/B: Miks (A)" : "A/B: Referans (B)";
    const p = AB_MODE === "B" ? PROJ.reference_path : PROJ.last_mixdown;
    if (p) api().player_show?.({ path: p });
    else setStatus("Önce Mixdown al veya Referans seç.");
  };

  $("#lyrInput").addEventListener("input", () => { analyzeLyricsUI(); saveProj(); });

  $("#pcRecBtn").onclick = async () => {
    if (!PC_REC) {
      const r = await api().booth_rec_start(PROJ?.id || "", "vocal1", +$("#micSel").value);
      if (r?.ok) { PC_REC = true; $("#pcRecBtn").classList.add("bad"); $("#pcRecBtn").textContent = "⏹ Kaydı Durdur"; $("#pcRecSt").textContent = "Kayıt alınıyor…"; }
      else $("#pcRecSt").textContent = "Hata: " + (r?.error || "?");
    } else {
      PC_REC = false; $("#pcRecBtn").classList.remove("bad"); $("#pcRecBtn").textContent = "🎙 Kayda Başla";
      const r = await api().booth_rec_stop($("#micClean").checked);
      if (r?.ok) { $("#pcRecSt").textContent = `✓ Kaydedildi (${r.duration}s)`; if (PROJ) loadProj(PROJ.id); }
      else $("#pcRecSt").textContent = "Hata: " + (r?.error || "?");
    }
  };

  $("#boothSrvBtn").onclick = async () => {
    const btn = $("#boothSrvBtn");
    if (BOOTH_RUNNING) {
      clearInterval(BOOTH_TIMER); BOOTH_TIMER = 0;
      await api().booth_server_stop().catch(() => {});
      BOOTH_RUNNING = false;
      btn.classList.remove("bad"); btn.classList.add("ok");
      btn.textContent = "Kablosuz Booth'u Başlat";
      $("#boothUrl").textContent = "";
      return;
    }
    const r = await api().booth_server_start(PROJ?.id || "", "vocal1");
    if (r?.ok) {
      BOOTH_RUNNING = true;
      btn.classList.remove("ok"); btn.classList.add("bad");
      btn.textContent = "⏹ Booth Sunucusunu Durdur";
      $("#boothUrl").textContent = "iPhone Safari'den aç: " + r.url;
      clearInterval(BOOTH_TIMER);
      let lastTs = r.last_upload?.ts || 0;
      BOOTH_TIMER = setInterval(async () => {
        const st = await api().booth_server_status().catch(() => null);
        if (st?.last_upload?.ts && st.last_upload.ts > lastTs) {
          lastTs = st.last_upload.ts;
          if (PROJ) loadProj(PROJ.id);
          setStatus("✓ iPhone Booth'tan yeni take geldi!");
        }
      }, 2500);
    }
  };

  $("#mVocalPick").onclick = async () => { const r = await api().beat_pick_audio(); if (r?.path) $("#mVocal").value = r.path; };
  $("#mBeatPick").onclick = async () => { const r = await api().beat_pick_audio(); if (r?.path) $("#mBeat").value = r.path; };
  $("#mGo").onclick = async () => {
    const v = $("#mVocal").value.trim(), b = $("#mBeat").value.trim();
    if (!v || !b) return;
    const btn = $("#mGo"); btn.disabled = true;
    $("#mRes").textContent = "BPM/Ton eşleştiriliyor ve mashup işleniyor…";
    try {
      const r = await api().beat_studio_mashup(v, b, "", +$("#mVDb").value, +$("#mBDb").value);
      $("#mRes").textContent = r?.ok ? `✓ Hazır (${r.out || r.path}) — Vokal ${r.vocal_bpm} BPM → Beat ${r.beat_bpm} BPM` : ("Hata: " + (r?.error || "?"));
    } finally { btn.disabled = false; }
  };

  init();
})();
