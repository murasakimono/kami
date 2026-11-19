// Kamify v1.38.0 — 4-layer Cover WebGL Mesh Shader, Word Karaoke, A-B Loop, Stop-After-Track, Type-to-Search & Dinamik Ada Toggle
"use strict";
(() => {
  const callApi = () => (typeof api === "function" ? api() : window.pywebview?.api);
  const $id = (s) => document.getElementById(s);
  const css = document.createElement("style");
  css.textContent = `
    #kfMeshCanvas{position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;opacity:0;transition:opacity .7s ease}
    #kfMeshCanvas.on{opacity:.52}
    .kf-ab-wrap{position:relative;display:flex;align-items:center;flex:1}
    .kf-ab-wrap input[type=range]{width:100%}
    .kf-ab-band{position:absolute;top:50%;transform:translateY(-50%);height:6px;border-radius:4px;background:rgba(46,230,166,.35);border:1px solid rgba(46,230,166,.75);pointer-events:none;z-index:1}
    .kf-mini-btn{height:24px;min-width:24px;padding:0 7px;border-radius:7px;border:1px solid var(--line);background:#151022;color:var(--mut);font:700 11px "Chakra Petch",sans-serif;cursor:pointer;transition:all .14s}
    .kf-mini-btn:hover{border-color:var(--ac);color:#fff}
    .kf-mini-btn.on{border-color:var(--em);color:var(--em);background:rgba(46,230,166,.12)}
    .kf-word{display:inline-block;margin-right:4px;transition:transform .22s cubic-bezier(.22,1,.36,1),filter .22s ease,opacity .22s ease,color .22s ease}
    .kf-word.sung{color:#2EE6A6;opacity:1;filter:none}
    .kf-word.cur{color:#fff;transform:scale(1.07);opacity:1;filter:none;text-shadow:0 0 12px rgba(46,230,166,.55)}
    .kf-word.next{opacity:.56;filter:blur(.6px)}
    .kf-breather{display:flex;gap:5px;padding:6px 12px;opacity:.72}
    .kf-breather i{width:6px;height:6px;border-radius:50%;background:var(--em);animation:kfBeat 1.2s ease-in-out infinite}
    .kf-breather i:nth-child(2){animation-delay:.2s}.kf-breather i:nth-child(3){animation-delay:.4s}
    @keyframes kfBeat{0%,100%{transform:scale(.7);opacity:.4}50%{transform:scale(1.25);opacity:1}}
    #kfTypeFilter{position:fixed;right:20px;bottom:104px;z-index:45;background:rgba(16,12,26,.96);border:1px solid var(--ac);border-radius:10px;padding:6px 10px;display:flex;align-items:center;gap:8px;box-shadow:0 12px 30px rgba(0,0,0,.6);font:600 12px "Chakra Petch",sans-serif}
    #kfTypeFilter b{color:var(--em)}#kfTypeFilter button{border:0;background:none;color:var(--mut);cursor:pointer}
  `;
  document.head.appendChild(css);

  // ---- 1. Dinamik Ada quick toggle ----
  const dynBtn = $id("kfDynAdaBtn");
  if (dynBtn) {
    let dynOn = true;
    const syncDyn = () => {
      dynBtn.classList.toggle("pri", dynOn);
      dynBtn.textContent = dynOn ? "Dinamik Ada: Açık" : "Dinamik Ada: Kapalı";
    };
    const initDyn = async () => {
      try {
        const s = await callApi()?.get_settings?.();
        if (s && "island_music_expand" in s) dynOn = s.island_music_expand !== false;
        syncDyn();
      } catch {}
    };
    dynBtn.onclick = async () => {
      dynOn = !dynOn;
      syncDyn();
      await callApi()?.set_setting?.("island_music_expand", dynOn);
      if (typeof mToast === "function") mToast(dynOn ? "✓ Mini-Ada hover'da kapak rengiyle genişler" : "Mini-Ada sabit kompakt modda kalır");
    };
    window.addEventListener("pywebviewready", initDyn);
    setTimeout(initDyn, 400);
  }

  // ---- 2. 4-Layer Twisted Cover WebGL Ambient Mesh ----
  const mainEl = document.querySelector(".main");
  const cv = document.createElement("canvas");
  cv.id = "kfMeshCanvas";
  if (mainEl) mainEl.prepend(cv);
  const gl = cv.getContext("webgl", { alpha: true, antialias: false, powerPreference: "low-power" });
  let prog = null, curPalette = [
    [0.48, 0.22, 0.92], [0.18, 0.90, 0.65], [0.22, 0.10, 0.45], [0.10, 0.08, 0.16],
  ], tgtPalette = curPalette.map((c) => [...c]);

  if (gl) {
    const vs = `attribute vec2 p; varying vec2 uv; void main(){ uv=p*0.5+0.5; gl_Position=vec4(p,0.,1.); }`;
    const fs = `
      precision mediump float;
      varying vec2 uv;
      uniform float t;
      uniform vec3 c0, c1, c2, c3;
      void main() {
        vec2 q = uv;
        float w1 = sin(q.x * 2.7 + t * 0.45) * cos(q.y * 2.1 - t * 0.35);
        float w2 = sin((q.x + q.y) * 3.1 - t * 0.28) * 0.5;
        vec2 p = q + 0.18 * vec2(w1, w2);
        vec3 col = mix(c2, c0, smoothstep(0.1, 0.85, p.x + 0.2 * w1));
        col = mix(col, c1, 0.58 * smoothstep(0.25, 0.95, 1.0 - p.y + 0.22 * w2));
        col = mix(col, c3, 0.42 * length(q - vec2(0.5)));
        gl_FragColor = vec4(col, 0.72);
      }
    `;
    const mk = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
    const vsh = mk(gl.VERTEX_SHADER, vs), fsh = mk(gl.FRAGMENT_SHADER, fs);
    if (vsh && fsh) {
      prog = gl.createProgram();
      gl.attachShader(prog, vsh); gl.attachShader(prog, fsh); gl.linkProgram(prog);
      const b = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, b);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1,-1, 1,-1, -1,1, 1,1]), gl.STATIC_DRAW);
      gl.useProgram(prog);
      const loc = gl.getAttribLocation(prog, "p");
      gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    }
  }

  let sampledCov = "";
  function sampleMeshPalette(url) {
    if (!url || url === sampledCov) return;
    sampledCov = url;
    const im = new Image(); im.crossOrigin = "anonymous";
    im.onload = () => {
      try {
        const c = document.createElement("canvas"); c.width = 4; c.height = 4;
        const g = c.getContext("2d"); g.drawImage(im, 0, 0, 4, 4);
        const d = g.getImageData(0, 0, 4, 4).data;
        const pts = [0, 3, 12, 15].map((i) => [d[i*4]/255, d[i*4+1]/255, d[i*4+2]/255]);
        tgtPalette = pts.map(([r, gr, b]) => (r + gr + b > 0.25) ? [r, gr, b] : [0.38, 0.2, 0.72]);
      } catch {}
    };
    im.src = url;
  }

  let meshT = 0, meshRaf = 0;
  function tickMesh() {
    meshRaf = 0;
    const playing = typeof SP_PLAYING !== "undefined" && SP_PLAYING;
    const ambOn = typeof AMB_ON === "undefined" || AMB_ON;
    const covUrl = typeof CUR_TRACK !== "undefined" ? CUR_TRACK?.cover : "";
    if (covUrl) sampleMeshPalette(covUrl);
    cv.classList.toggle("on", Boolean(prog && ambOn && playing && !document.hidden));
    if (!prog || !ambOn || !playing || document.hidden) return;
    if (cv.width !== Math.max(200, Math.floor(cv.clientWidth / 2)) || cv.height !== Math.max(200, Math.floor(cv.clientHeight / 2))) {
      cv.width = Math.max(200, Math.floor(cv.clientWidth / 2));
      cv.height = Math.max(200, Math.floor(cv.clientHeight / 2));
    }
    meshT += 0.016;
    for (let k = 0; k < 4; k++) for (let c = 0; c < 3; c++) curPalette[k][c] += (tgtPalette[k][c] - curPalette[k][c]) * 0.03;
    gl.viewport(0, 0, cv.width, cv.height);
    gl.useProgram(prog);
    gl.uniform1f(gl.getUniformLocation(prog, "t"), meshT);
    ["c0", "c1", "c2", "c3"].forEach((nm, i) => gl.uniform3f(gl.getUniformLocation(prog, nm), curPalette[i][0], curPalette[i][1], curPalette[i][2]));
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    meshRaf = requestAnimationFrame(tickMesh);
  }
  setInterval(() => {
    if (!meshRaf && typeof SP_PLAYING !== "undefined" && SP_PLAYING && !document.hidden && (typeof AMB_ON === "undefined" || AMB_ON)) {
      meshRaf = requestAnimationFrame(tickMesh);
    }
  }, 500);
  document.addEventListener("visibilitychange", () => { if (!document.hidden && !meshRaf) meshRaf = requestAnimationFrame(tickMesh); });

  // ---- 3. Word-by-Word Karaoke + Breather ----
  let lyrEstStart = Date.now(), lyrBaseMs = 0, lyrTrackSig = "";
  setInterval(() => {
    const pop = $id("spLyr");
    if (!pop || pop.hidden || typeof CUR_TRACK === "undefined" || !CUR_TRACK || typeof LYRICS === "undefined" || !LYRICS.length) return;
    const sig = `${CUR_TRACK.title}|${CUR_TRACK.progress_ms}`;
    if (sig !== lyrTrackSig) { lyrTrackSig = sig; lyrBaseMs = CUR_TRACK.progress_ms || 0; lyrEstStart = Date.now(); }
    const sec = (lyrBaseMs + (SP_PLAYING ? (Date.now() - lyrEstStart) : 0)) / 1000;
    let activeIdx = -1;
    LYRICS.forEach((ln, idx) => { if (ln.t >= 0 && ln.t <= sec + 0.15) activeIdx = idx; });
    const rows = pop.querySelectorAll(".lyr-ln");
    const row = activeIdx >= 0 ? rows[activeIdx] : null;
    const ln = activeIdx >= 0 ? LYRICS[activeIdx] : null;
    if (row && ln) {
      let words = Array.isArray(ln.words) && ln.words.length ? ln.words : null;
      if (!words && ln.t >= 0) {
        const nextT = (LYRICS[activeIdx + 1]?.t > ln.t) ? LYRICS[activeIdx + 1].t : ln.t + 3.5;
        const toks = String(ln.text || "").split(/\s+/).filter(Boolean);
        const span = Math.max(0.8, Math.min(8.0, nextT - ln.t));
        words = toks.map((w, i) => ({ w, t: ln.t + (i / toks.length) * span, end: ln.t + ((i + 1) / toks.length) * span }));
      }
      if (words) {
        row.innerHTML = words.map((wd) => {
          const cls = sec < wd.t ? "next" : (sec <= wd.end + 0.12 ? "cur" : "sung");
          return `<span class="kf-word ${cls}">${wd.w.replace(/</g, "&lt;")}</span>`;
        }).join(" ");
      }
      if (activeIdx + 1 < LYRICS.length && LYRICS[activeIdx + 1].t - ln.t > 7 && sec > ln.t + 3.5) {
        if (!pop.querySelector(".kf-breather")) row.insertAdjacentHTML("afterend", '<div class="kf-breather"><i></i><i></i><i></i></div>');
      } else pop.querySelectorAll(".kf-breather").forEach((b) => b.remove());
    }
  }, 110);

  // ---- 4. Tauon A-B Loop & Stop After Track ----
  let loopA = null, loopB = null, stopAfter = false, lastAbSeek = 0, lastStopTrack = "";
  const ctl = document.querySelector(".sp-ctl");
  const seekEl = $id("spSeek");
  let abBand = null;
  if (seekEl && seekEl.parentElement) {
    const wrap = document.createElement("div");
    wrap.className = "kf-ab-wrap";
    seekEl.parentNode.insertBefore(wrap, seekEl);
    wrap.appendChild(seekEl);
    abBand = document.createElement("div");
    abBand.className = "kf-ab-band";
    abBand.hidden = true;
    wrap.appendChild(abBand);
  }
  function syncAbBand() {
    if (!abBand) return;
    const dur = (typeof CUR_TRACK !== "undefined" && CUR_TRACK?.duration_ms) || 0;
    if (loopA != null && loopB != null && loopB > loopA && dur > 0) {
      const l = Math.max(0, Math.min(100, (loopA / dur) * 100));
      const w = Math.max(1, Math.min(100 - l, ((loopB - loopA) / dur) * 100));
      abBand.style.left = l + "%";
      abBand.style.width = w + "%";
      abBand.hidden = false;
    } else abBand.hidden = true;
  }
  if (ctl) {
    const bA = document.createElement("button"); bA.className = "kf-mini-btn"; bA.textContent = "A"; bA.title = "A-B Döngü Başlangıcı";
    const bB = document.createElement("button"); bB.className = "kf-mini-btn"; bB.textContent = "B"; bB.title = "A-B Döngü Bitişi (Sağ tık: temizle)";
    const bStp = document.createElement("button"); bStp.className = "kf-mini-btn"; bStp.textContent = "Parça Sonu ⏹"; bStp.title = "Bu parçadan sonra durdur";
    bA.onclick = () => {
      if (loopA != null && loopB != null) { loopA = loopB = null; bA.classList.remove("on"); bB.classList.remove("on"); syncAbBand(); return; }
      loopA = (typeof CUR_TRACK !== "undefined" && CUR_TRACK?.progress_ms) || 0;
      bA.classList.add("on");
      syncAbBand();
    };
    bB.onclick = () => {
      if (loopA == null) loopA = 0;
      const cur = (typeof CUR_TRACK !== "undefined" && CUR_TRACK?.progress_ms) || 0;
      if (loopB != null || cur <= loopA) { loopA = loopB = null; bA.classList.remove("on"); bB.classList.remove("on"); }
      else { loopB = cur; bB.classList.add("on"); }
      syncAbBand();
    };
    bB.oncontextmenu = (e) => { e.preventDefault(); loopA = loopB = null; bA.classList.remove("on"); bB.classList.remove("on"); syncAbBand(); };
    bStp.onclick = () => {
      stopAfter = !stopAfter;
      bStp.classList.toggle("on", stopAfter);
      lastStopTrack = (typeof CUR_TRACK !== "undefined" && (CUR_TRACK?.id || CUR_TRACK?.title)) || "";
      if (typeof mToast === "function") mToast(stopAfter ? "✓ Bu şarkı bitince otomatik durdurulacak" : "Parça sonu durdurma iptal");
    };
    ctl.append(bA, bB, bStp);
    setInterval(async () => {
      if (typeof CUR_TRACK === "undefined" || !CUR_TRACK) return;
      syncAbBand();
      const tid = CUR_TRACK.id || CUR_TRACK.title || "";
      if (stopAfter && lastStopTrack && tid && tid !== lastStopTrack) {
        stopAfter = false; bStp.classList.remove("on");
        await callApi()?.music_spotify_control?.("pause")?.catch?.(() => {});
        if (typeof mToast === "function") mToast("⏹ Parça sonu: çalma durduruldu");
      }
      if (SP_PLAYING && loopA != null && loopB != null && loopB > loopA && CUR_TRACK.progress_ms >= loopB && Date.now() - lastAbSeek > 1000) {
        lastAbSeek = Date.now();
        await callApi()?.music_spotify_seek?.(loopA)?.catch?.(() => {});
      }
    }, 450);
  }

  // ---- 5. Global Type-to-Search Filter (Tauon) ----
  let typeQuery = "", filterBox = null, typeTimer = 0;
  function applyTypeFilter() {
    if (!filterBox && !typeQuery) return;
    if (!filterBox) {
      filterBox = document.createElement("div"); filterBox.id = "kfTypeFilter";
      filterBox.innerHTML = '<span>Süzgeç:</span><b id="kfTfQ"></b><button id="kfTfX">✕</button>';
      document.body.appendChild(filterBox);
      filterBox.querySelector("#kfTfX").onclick = () => { typeQuery = ""; applyTypeFilter(); };
    }
    filterBox.hidden = !typeQuery;
    filterBox.querySelector("#kfTfQ").textContent = typeQuery;
    const low = typeQuery.toLocaleLowerCase("tr");
    document.querySelectorAll("#list .row, #list .acard").forEach((el) => {
      el.hidden = low ? !el.textContent.toLocaleLowerCase("tr").includes(low) : false;
    });
  }
  document.addEventListener("keydown", (e) => {
    if (e.target.matches?.("input, textarea, select") || e.ctrlKey || e.metaKey || e.altKey) return;
    if (e.key === "Escape" && typeQuery) { typeQuery = ""; applyTypeFilter(); return; }
    if (e.key === "Backspace" && typeQuery) { typeQuery = typeQuery.slice(0, -1); applyTypeFilter(); e.preventDefault(); return; }
    if (e.key.length === 1 && /[\p{L}\p{N} ]/u.test(e.key)) {
      if (typeQuery.length < 30) { typeQuery += e.key; applyTypeFilter(); }
      clearTimeout(typeTimer); typeTimer = setTimeout(() => { if (filterBox && !typeQuery) filterBox.hidden = true; }, 4000);
    }
  });

  // ---- 6. Kami 2.0: MP3 Whisper Guclu Sarki Modu + Canli LRC Editoru + B8 Dinleme Gunlugu ----
  const lrcCss = document.createElement("style");
  lrcCss.textContent = `
    .kf-lrc-ov { position:fixed; inset:0; z-index:88; background:rgba(5,4,10,.84); backdrop-filter:blur(8px); display:grid; place-items:center; padding:18px; }
    .kf-lrc-box { width:min(760px,95vw); max-height:90vh; background:#120E1D; border:1px solid var(--ac); border-radius:14px; padding:16px 18px; display:flex; flex-direction:column; gap:10px; color:#EDE9F6; }
    .kf-lrc-rows { flex:1; overflow-y:auto; max-height:46vh; display:flex; flex-direction:column; gap:5px; padding-right:4px; }
    .kf-lrc-row { display:grid; grid-template-columns:82px 74px 1fr 28px; gap:7px; align-items:center; background:#181226; border:1px solid var(--line); border-radius:8px; padding:5px 8px; }
    .kf-lrc-row.cur { border-color:var(--em); background:rgba(46,230,166,.08); }
    .kf-lrc-row input { background:#0B0812; border:1px solid var(--line); border-radius:6px; color:#fff; padding:5px 8px; font:inherit; width:100%; }
  `;
  document.head.appendChild(lrcCss);

  function fmtLrcSec(sec) {
    if (sec == null || sec < 0 || !Number.isFinite(sec)) return "--:--.--";
    const m = Math.floor(sec / 60), s = (sec % 60).toFixed(2).padStart(5, "0");
    return `${String(m).padStart(2, "0")}:${s}`;
  }
  function parseLrcSec(str) {
    const m = String(str || "").trim().match(/^(\d+):(\d+(?:\.\d+)?)$/);
    return m ? (parseInt(m[1], 10) * 60 + parseFloat(m[2])) : -1;
  }

  async function openLrcEditor(path, titleHint = "") {
    if (!path) return;
    const r = await callApi()?.music_lrc_read?.(path).catch(() => null);
    let rows = (r?.lines && r.lines.length)
      ? r.lines.map((x) => ({ t: Number(x.t ?? -1), text: String(x.text || "") }))
      : [{ t: 0, text: "" }];
    let activeRow = 0;

    const ov = document.createElement("div");
    ov.className = "kf-lrc-ov";
    ov.innerHTML = `
      <div class="kf-lrc-box">
        <div style="display:flex;align-items:center;justify-content:space-between;gap:8px">
          <b>🎤 Canlı LRC & Zaman Damgası Editörü · <span style="color:var(--em)">${(titleHint || path.split(/[\\/]/).pop()).replace(/</g, "&lt;")}</span></b>
          <button class="btn" id="kfLrcX">✕</button>
        </div>
        <div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap;background:#0B0812;padding:8px 10px;border-radius:10px;border:1px solid var(--line)">
          <audio id="kfLrcAudio" controls style="flex:1;height:32px"></audio>
          <label style="font-size:11.5px;display:flex;align-items:center;gap:5px"><input type="checkbox" id="kfStrongChk" checked> <b>Güçlü Mod</b> (UVR5 Vokal Ayır + Tam Rap Algılama)</label>
          <button class="btn pri" id="kfRunWhisper">🎙 Whisper ile Söz Çıkar</button>
          <button class="btn" id="kfRunOllama" title="Yerel Ollama (qwen2.5:3b) ile yazım hatalarını düzelt">✨ Ollama ile Düzelt</button>
        </div>
        <div style="font-size:11.5px;color:var(--mut);display:flex;justify-content:space-between;align-items:center">
          <span>İpucu: Şarkı çalarken <b>[Damgala (F8)]</b> tuşuyla aktif satıra anlık zaman damgası vurup alt satıra geçebilirsin.</span>
          <div style="display:flex;gap:6px">
            <button class="btn" id="kfAddRow">+ Satır Ekle</button>
            <button class="btn" id="kfRawToggle">Ham .LRC Metni</button>
          </div>
        </div>
        <div class="kf-lrc-rows" id="kfLrcRows"></div>
        <textarea id="kfLrcRaw" rows="10" hidden style="width:100%;background:#09070F;border:1px solid var(--line);border-radius:8px;color:#EDE9F6;padding:10px;font:12.5px Consolas,monospace"></textarea>
        <div style="display:flex;justify-content:space-between;align-items:center">
          <span id="kfLrcSt" style="font-size:12px;color:var(--em)"></span>
          <div style="display:flex;gap:8px">
            <button class="btn" id="kfStampNext">⏱ Aktif Satırı Damgala & İlerle (F8)</button>
            <button class="btn pri" id="kfSaveLrc">💾 .LRC + MP3 İçine Kaydet</button>
          </div>
        </div>
      </div>
    `;
    document.body.appendChild(ov);

    const aud = ov.querySelector("#kfLrcAudio");
    callApi()?.player_open_path?.(path).then((m) => { if (m?.url) aud.src = m.url; }).catch(() => {});

    const rowsBox = ov.querySelector("#kfLrcRows");
    const rawBox = ov.querySelector("#kfLrcRaw");
    const stEl = ov.querySelector("#kfLrcSt");

    function rowsToRaw() {
      return rows.filter((x) => x.text.trim()).map((x) => (x.t >= 0 ? `[${fmtLrcSec(x.t)}]${x.text.trim()}` : x.text.trim())).join("\n");
    }
    function rawToRows(txt) {
      const out = [];
      for (const ln of String(txt || "").split(/\r?\n/)) {
        const s = ln.trim();
        if (!s) continue;
        const m = s.match(/^\[(\d+:\d+(?:\.\d+)?)\]\s*(.*)$/);
        if (m) out.push({ t: parseLrcSec(m[1]), text: m[2] });
        else if (!s.startsWith("[")) out.push({ t: -1, text: s });
      }
      return out.length ? out : [{ t: 0, text: "" }];
    }

    function drawRows() {
      rowsBox.innerHTML = rows.map((r, i) => `
        <div class="kf-lrc-row${i === activeRow ? " cur" : ""}" data-idx="${i}">
          <input class="ts-in" value="${fmtLrcSec(r.t)}" data-tsi="${i}" title="Zaman (dd:ss.ms)">
          <button class="btn" data-stamp="${i}" style="padding:4px 6px;font-size:11px">⏱ Damgala</button>
          <input class="tx-in" value="${r.text.replace(/"/g, "&quot;")}" data-txi="${i}" placeholder="Şarkı sözü satırı…">
          <button class="btn" data-del="${i}" style="padding:3px 6px;color:#FB7185">✕</button>
        </div>
      `).join("");
      rowsBox.querySelectorAll(".ts-in").forEach((inp) => {
        inp.onchange = () => { rows[+inp.dataset.tsi].t = parseLrcSec(inp.value); };
      });
      rowsBox.querySelectorAll(".tx-in").forEach((inp) => {
        inp.onfocus = () => { activeRow = +inp.dataset.txi; };
        inp.oninput = () => { rows[+inp.dataset.txi].text = inp.value; };
      });
      rowsBox.querySelectorAll("[data-stamp]").forEach((b) => {
        b.onclick = () => {
          const idx = +b.dataset.stamp;
          rows[idx].t = Number(aud.currentTime || 0);
          activeRow = Math.min(rows.length - 1, idx + 1);
          drawRows();
        };
      });
      rowsBox.querySelectorAll("[data-del]").forEach((b) => {
        b.onclick = () => {
          rows.splice(+b.dataset.del, 1);
          if (!rows.length) rows.push({ t: 0, text: "" });
          drawRows();
        };
      });
    }
    drawRows();

    ov.querySelector("#kfAddRow").onclick = () => {
      rows.push({ t: Number(aud.currentTime || 0), text: "" });
      activeRow = rows.length - 1;
      drawRows();
    };
    ov.querySelector("#kfRawToggle").onclick = () => {
      if (rawBox.hidden) {
        rawBox.value = rowsToRaw();
        rawBox.hidden = false;
        rowsBox.hidden = true;
      } else {
        rows = rawToRows(rawBox.value);
        rawBox.hidden = true;
        rowsBox.hidden = false;
        drawRows();
      }
    };
    const stampAndAdvance = () => {
      if (!rawBox.hidden) rows = rawToRows(rawBox.value);
      if (rows[activeRow]) {
        rows[activeRow].t = Number(aud.currentTime || 0);
        activeRow = Math.min(rows.length - 1, activeRow + 1);
        drawRows();
        rowsBox.querySelector(`.kf-lrc-row[data-idx="${activeRow}"]`)?.scrollIntoView({ block: "nearest" });
      }
    };
    ov.querySelector("#kfStampNext").onclick = stampAndAdvance;
    const onKey = (e) => {
      if (e.key === "F8") { e.preventDefault(); stampAndAdvance(); }
      else if (e.key === "Escape") { closeOv(); }
    };
    document.addEventListener("keydown", onKey);
    function closeOv() {
      document.removeEventListener("keydown", onKey);
      try { aud.pause(); } catch {}
      ov.remove();
    }
    ov.querySelector("#kfLrcX").onclick = closeOv;

    ov.querySelector("#kfRunWhisper").onclick = async () => {
      const strong = ov.querySelector("#kfStrongChk").checked;
      stEl.textContent = strong
        ? "🎙 UVR5 ile vokal ayrılıyor + Whisper Güçlü Mod ile tüm satırlar çıkarılıyor…"
        : "🎙 Whisper ile zaman damgalı söz çıkarılıyor…";
      const res = await callApi()?.music_whisper_lrc?.(path, "tr", strong).catch((e) => ({ ok: false, error: String(e) }));
      if (res?.ok) {
        rows = (res.lines && res.lines.length)
          ? res.lines.map((x) => ({ t: Number(x.t ?? 0), text: String(x.text || "") }))
          : rawToRows(res.lrc_text || "");
        rawBox.value = rowsToRaw();
        drawRows();
        stEl.textContent = `✓ ${rows.length} satır çıkarıldı ve .lrc olarak kaydedildi (${res.uvr_used ? "UVR5 Vokal + " : ""}Güçlü Mod)`;
      } else {
        stEl.textContent = "✕ Hata: " + (res?.error === "tool_missing" ? "Önce Kami AI'dan Whisper aracını kur" : (res?.error || "çıkarılamadı"));
      }
    };

    ov.querySelector("#kfRunOllama").onclick = async () => {
      const curRaw = rawBox.hidden ? rowsToRaw() : rawBox.value;
      if (!curRaw.trim()) { stEl.textContent = "Önce söz çıkar veya yapıştır."; return; }
      stEl.textContent = "✨ Yerel Ollama (qwen2.5:3b) ile yazım düzeltiliyor…";
      const res = await callApi()?.music_lrc_polish_ollama?.(curRaw, titleHint, "").catch(() => null);
      if (res?.ok && res.text) {
        rows = rawToRows(res.text);
        rawBox.value = res.text;
        drawRows();
        stEl.textContent = `✓ Ollama (${res.model}) ile düzeltildi`;
      } else {
        stEl.textContent = "✕ Ollama yanıt vermedi (" + (res?.error || "kapalı") + ")";
      }
    };

    ov.querySelector("#kfSaveLrc").onclick = async () => {
      const payload = rawBox.hidden ? rows : rawBox.value;
      const res = await callApi()?.music_lrc_save?.(path, payload, "", titleHint).catch(() => null);
      stEl.textContent = res?.ok ? "✓ .LRC dosyasına ve MP3 USLT etiketine kaydedildi!" : ("✕ " + (res?.error || "Kaydedilemedi"));
    };
  }

  window.openKamiLrcEditor = openLrcEditor;

  document.addEventListener("click", async (e) => {
    const wb = e.target.closest("[data-locwhisper]");
    if (wb) {
      e.stopPropagation();
      openLrcEditor(wb.dataset.locwhisper, "");
      setTimeout(() => document.getElementById("kfRunWhisper")?.click(), 180);
      return;
    }
    const eb = e.target.closest("[data-loclrcedit]");
    if (eb) {
      e.stopPropagation();
      openLrcEditor(eb.dataset.loclrcedit, eb.dataset.loctitle || "");
      return;
    }
    const nb = e.target.closest('.nav-b[data-nav="scrobble"]');
    if (nb) {
      document.querySelectorAll(".nav-b[data-nav]").forEach((b) => b.classList.toggle("on", b === nb));
      const vt = document.getElementById("viewTitle");
      if (vt) vt.textContent = "Sistem Sesi Dinleme Günlüğü (Ctrl+Shift+G)";
      const sb = document.getElementById("subBar");
      const listEl = document.getElementById("list");
      if (sb) {
        sb.hidden = false;
        sb.innerHTML = `<button class="btn pri" id="kfScrobNow">🎧 Şimdi Sistem Sesini Tanı & Günlüğe Ekle (Ctrl+Shift+G)</button><small style="color:var(--mut)">10 sn'lik hızlı tanımlama kısayolundan (Ctrl+Shift+S) bağımsız çalışır ve geçmişi kaydeder.</small>`;
        sb.querySelector("#kfScrobNow").onclick = async (ev) => {
          ev.target.disabled = true; ev.target.textContent = "Dinleniyor…";
          const r = await callApi()?.scrobbler_recognize_now?.().catch(() => null);
          ev.target.disabled = false; ev.target.textContent = "🎧 Şimdi Sistem Sesini Tanı & Günlüğe Ekle (Ctrl+Shift+G)";
          if (typeof mToast === "function") mToast(r?.ok ? `✓ Tanındı: ${r.song?.artist} — ${r.song?.title}` : (r?.error || "Şarkı algılanamadı"), !r?.ok);
          nb.click();
        };
      }
      if (listEl) {
        const hist = await callApi()?.scrobbler_history?.().catch(() => []) || [];
        listEl.innerHTML = hist.length ? hist.map((h) => `
          <div class="row">
            <div class="meta"><b>${(h.title || "Bilinmeyen").replace(/</g, "&lt;")}</b><small>${(h.artist || "").replace(/</g, "&lt;")} · ${new Date((h.ts || 0) * 1000).toLocaleString("tr-TR")}</small></div>
            <button class="btn" onclick="document.getElementById('q').value='${(h.artist + " " + h.title).replace(/'/g, "")}';document.getElementById('go').click()">Ara</button>
          </div>
        `).join("") : `<div style="color:var(--mut);padding:14px">Henüz günlük kaydı yok. Yukarıdaki düğmeye veya <b>Ctrl+Shift+G</b> kısayoluna basarak çalan parçaları günlüğe kaydedebilirsin.</div>`;
      }
    }
  });
})();
