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
})();
