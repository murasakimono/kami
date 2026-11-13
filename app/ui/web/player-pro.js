// Faz 12 — Kami Player Pro: libplacebo WebGL2 Shader, AudioWorklet Canli DSP (stereo + hoparlor baglantili) & 16-Adim DAW
"use strict";
(() => {
  const PRO = {
    shader: "off", // off | krig | ssim | grain
    dialogueClarity: false,
    replayGain: true,
    pitchSemi: 0,
    workletReady: false,
    workletNode: null,
    clarityFilter: null,
    rgGain: null,
    analyser: null,
    wired: false,
    vizRaf: 0,
    scenes: [],
    dawSteps: Array.from({ length: 4 }, () => Array(16).fill(false)),
    dawTimer: null,
    dawStep: 0,
  };

  // ---------- 12.1 libplacebo Sinifi WebGL2 Shader Profilleri ----------
  const PRO_FS = `
  precision highp float;
  uniform sampler2D u_tex;
  uniform vec2 u_res;
  uniform int u_mode; // 1=KrigBilateral, 2=SSimSuperRes, 3=Deband+Grain
  uniform float u_time;
  varying vec2 v_uv;

  float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
  }

  void main() {
    vec2 px = 1.0 / max(u_res, vec2(1.0));
    vec3 c = texture2D(u_tex, v_uv).rgb;
    vec3 n = texture2D(u_tex, v_uv + vec2(0.0, px.y)).rgb;
    vec3 s = texture2D(u_tex, v_uv - vec2(0.0, px.y)).rgb;
    vec3 e = texture2D(u_tex, v_uv + vec2(px.x, 0.0)).rgb;
    vec3 w = texture2D(u_tex, v_uv - vec2(px.x, 0.0)).rgb;
    vec3 blur = (n + s + e + w) * 0.25;

    if (u_mode == 1) {
      vec3 detail = c - blur;
      float edge = clamp(1.0 - length(detail) * 3.0, 0.2, 1.0);
      c = clamp(c + detail * (0.65 * edge), 0.0, 1.0);
    } else if (u_mode == 2) {
      vec3 hi = c - blur;
      c = clamp(c + hi * 0.95, 0.0, 1.0);
    } else if (u_mode == 3) {
      float g = (hash12(v_uv * u_res + fract(u_time) * 100.0) - 0.5) * 0.035;
      c = clamp(mix(blur, c, 0.85) + g, 0.0, 1.0);
    }
    gl_FragColor = vec4(c, 1.0);
  }`;

  // ---------- 12.2 Stereo AudioWorklet Canli DSP (lineer interpolasyon + overlap crossfade) ----------
  const WORKLET_CODE = `
  class KamiDspProcessor extends AudioWorkletProcessor {
    static get parameterDescriptors() {
      return [{ name: "pitchRatio", defaultValue: 1.0, minValue: 0.5, maxValue: 2.0 }];
    }
    constructor() {
      super();
      this.len = 4096;
      this.bufs = [new Float32Array(this.len), new Float32Array(this.len)];
      this.w = 0;
      this.phase = 0.0;
    }
    process(inputs, outputs, parameters) {
      const inp = inputs[0], out = outputs[0];
      if (!inp || !inp[0] || !out || !out[0]) return true;
      const ratio = parameters.pitchRatio[0] || 1.0;
      const nCh = Math.min(out.length, 2);
      const frames = out[0].length;
      if (Math.abs(ratio - 1.0) < 0.005) {
        for (let ch = 0; ch < nCh; ch++) {
          out[ch].set(inp[ch] || inp[0]);
        }
        return true;
      }
      const len = this.len;
      const half = len >> 1;
      for (let i = 0; i < frames; i++) {
        for (let ch = 0; ch < nCh; ch++) {
          const s = (inp[ch] || inp[0])[i];
          this.bufs[ch][this.w] = s;
        }
        // Iki okuma ucu arasinda faz farki ile tikirtisiz crossfade
        const r1 = (this.w - this.phase + len) % len;
        const r2 = (r1 + half) % len;
        const idx1 = Math.floor(r1);
        const f1 = r1 - idx1;
        const idx2 = Math.floor(r2);
        const f2 = r2 - idx2;
        const mix = Math.abs((this.phase / half) - 1.0); // 0..1..0 ucgen pencere
        for (let ch = 0; ch < nCh; ch++) {
          const b = this.bufs[ch];
          const v1 = b[idx1] * (1.0 - f1) + b[(idx1 + 1) % len] * f1;
          const v2 = b[idx2] * (1.0 - f2) + b[(idx2 + 1) % len] * f2;
          out[ch][i] = v1 * mix + v2 * (1.0 - mix);
        }
        this.w = (this.w + 1) % len;
        this.phase = (this.phase + (1.0 - ratio) + len) % len;
      }
      return true;
    }
  }
  registerProcessor("kami-dsp-processor", KamiDspProcessor);`;

  function wireChain() {
    if (typeof PL === "undefined" || !PL.ctx || !PL.gain || !PL.boost) return;
    if (!PRO.clarityFilter || !PRO.rgGain) return;
    try { PL.gain.disconnect(); } catch { /* ilk baglanti */ }
    try { PRO.clarityFilter.disconnect(); } catch { /* */ }
    try { PRO.rgGain.disconnect(); } catch { /* */ }
    if (PRO.workletNode) {
      try { PRO.workletNode.disconnect(); } catch { /* */ }
    }
    // PL.gain -> PRO.clarityFilter -> PRO.rgGain -> (PRO.workletNode) -> PL.boost (-> PL.delay -> PL.an -> destination)
    PL.gain.connect(PRO.clarityFilter);
    PRO.clarityFilter.connect(PRO.rgGain);
    if (PRO.workletNode && Math.abs(PRO.pitchSemi) > 0.05) {
      PRO.rgGain.connect(PRO.workletNode);
      PRO.workletNode.connect(PL.boost);
    } else {
      PRO.rgGain.connect(PL.boost);
    }
    PRO.wired = true;
  }

  async function ensureAudioDsp() {
    if (typeof PL === "undefined" || !PL.ctx || !PL.gain || !PL.boost) return;
    if (!PRO.clarityFilter) {
      PRO.clarityFilter = PL.ctx.createBiquadFilter();
      PRO.clarityFilter.type = "peaking";
      PRO.clarityFilter.frequency.value = 2800;
      PRO.clarityFilter.Q.value = 1.2;
      PRO.clarityFilter.gain.value = PRO.dialogueClarity ? 6.5 : 0;
    }
    if (!PRO.rgGain) {
      PRO.rgGain = PL.ctx.createGain();
      PRO.rgGain.gain.value = 1.0;
    }
    if (!PRO.analyser) {
      PRO.analyser = PL.an || PL.ctx.createAnalyser();
      if (!PL.an) {
        PRO.analyser.fftSize = 256;
        PL.boost.connect(PRO.analyser);
      }
    }
    if (!PRO.workletReady && PL.ctx.audioWorklet) {
      try {
        const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        await PL.ctx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        PRO.workletNode = new AudioWorkletNode(PL.ctx, "kami-dsp-processor", {
          numberOfInputs: 1,
          numberOfOutputs: 1,
          outputChannelCount: [2],
        });
        PRO.workletReady = true;
      } catch { /* Worklet desteklenmiyorsa pas gec */ }
    }
    wireChain();
  }

  async function setDialogueClarity(on) {
    PRO.dialogueClarity = !!on;
    await ensureAudioDsp();
    if (PRO.clarityFilter) PRO.clarityFilter.gain.value = PRO.dialogueClarity ? 6.5 : 0;
  }

  async function setPitchSemitones(semi) {
    PRO.pitchSemi = Math.max(-12, Math.min(12, Number(semi) || 0));
    await ensureAudioDsp();
    const ratio = Math.pow(2, PRO.pitchSemi / 12);
    if (PRO.workletNode?.parameters) {
      const p = PRO.workletNode.parameters.get("pitchRatio");
      if (p) p.value = ratio;
    }
    wireChain();
  }

  async function applyReplayGain(path) {
    if (!PRO.replayGain || !path || typeof api === "undefined" || !api.player_replaygain) return;
    try {
      await ensureAudioDsp();
      const r = await api.player_replaygain(path);
      if (r?.ok && PRO.rgGain) PRO.rgGain.gain.value = r.linear_gain || 1.0;
    } catch { /* sessiz */ }
  }

  // ---------- 12.3 Muzik Gorsellestirici ----------
  function startAudioVisualizer(canvas) {
    if (!canvas) return;
    ensureAudioDsp();
    const ctx2d = canvas.getContext("2d");
    if (!ctx2d) return;
    cancelAnimationFrame(PRO.vizRaf);
    const data = new Uint8Array(PRO.analyser ? PRO.analyser.frequencyBinCount : 128);
    const draw = () => {
      PRO.vizRaf = requestAnimationFrame(draw);
      const w = canvas.width, h = canvas.height;
      ctx2d.clearRect(0, 0, w, h);
      if (PRO.analyser) PRO.analyser.getByteFrequencyData(data);
      const bars = 48;
      const bw = w / bars;
      for (let i = 0; i < bars; i++) {
        const v = (data[i] || 0) / 255;
        const bh = Math.max(2, v * h * 0.9);
        ctx2d.fillStyle = `hsl(${265 + i * 2.2}, 85%, ${45 + v * 30}%)`;
        ctx2d.fillRect(i * bw + 1, h - bh, Math.max(1, bw - 2), bh);
      }
    };
    draw();
  }

  // ---------- 12.4 16-Adimli Tarayici DAW (Davul Makinesi) ----------
  function triggerDrum(trackIdx) {
    const ac = typeof PL !== "undefined" && PL.ctx ? PL.ctx : new (window.AudioContext || window.webkitAudioContext)();
    if (ac.state === "suspended") ac.resume();
    const now = ac.currentTime;
    const osc = ac.createOscillator();
    const g = ac.createGain();
    if (trackIdx === 0) {
      osc.type = "sine";
      osc.frequency.setValueAtTime(140, now);
      osc.frequency.exponentialRampToValueAtTime(42, now + 0.14);
      g.gain.setValueAtTime(0.7, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
    } else if (trackIdx === 1) {
      osc.type = "triangle";
      osc.frequency.setValueAtTime(210, now);
      g.gain.setValueAtTime(0.35, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
    } else if (trackIdx === 2) {
      osc.type = "square";
      osc.frequency.setValueAtTime(840, now);
      g.gain.setValueAtTime(0.12, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.045);
    } else {
      osc.type = "sawtooth";
      osc.frequency.setValueAtTime(65.4, now);
      g.gain.setValueAtTime(0.22, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.16);
    }
    osc.connect(g);
    g.connect(ac.destination);
    osc.start(now);
    osc.stop(now + 0.2);
  }

  function startDaw(bpm = 120) {
    stopDaw();
    const stepMs = (60 / Math.max(50, Math.min(220, bpm)) / 4) * 1000;
    PRO.dawStep = 0;
    PRO.dawTimer = setInterval(() => {
      for (let t = 0; t < PRO.dawSteps.length; t++) {
        if (PRO.dawSteps[t][PRO.dawStep]) triggerDrum(t);
      }
      PRO.dawStep = (PRO.dawStep + 1) % 16;
    }, stepMs);
  }

  function stopDaw() {
    if (PRO.dawTimer) { clearInterval(PRO.dawTimer); PRO.dawTimer = null; }
  }

  // ---------- Oynatici Arayuz Baglantisi ----------
  function mountProPanel() {
    const host = document.getElementById("player");
    if (!host || document.getElementById("kamiProBtn")) return;
    const btn = document.createElement("button");
    btn.id = "kamiProBtn";
    btn.textContent = "PRO DSP";
    btn.style.cssText = "position:fixed;right:14px;top:54px;z-index:60;background:#1C1528;color:#C4B5FD;border:1px solid #6D28D9;padding:4px 9px;font:600 11px 'Chakra Petch',sans-serif;cursor:pointer;";
    const panel = document.createElement("div");
    panel.id = "kamiProPanel";
    panel.hidden = true;
    panel.style.cssText = "position:fixed;right:14px;top:86px;z-index:61;width:240px;background:#120E1C;border:1px solid #6D28D9;padding:10px;color:#EDE9F6;font:12px 'Chakra Petch',sans-serif;display:grid;gap:8px;";
    panel.innerHTML = `
      <label style="display:flex;justify-content:space-between;align-items:center">
        <span>Diyalog Netligi</span><input id="kpClarity" type="checkbox">
      </label>
      <label style="display:flex;justify-content:space-between;align-items:center">
        <span>ReplayGain 2.0</span><input id="kpRg" type="checkbox" checked>
      </label>
      <label style="display:grid;gap:3px">
        <span>Perde (Yarim Ton): <b id="kpPitchVal">0</b></span>
        <input id="kpPitch" type="range" min="-12" max="12" step="1" value="0">
      </label>
      <button id="kpDaw" style="background:#2A1F42;color:#EDE9F6;border:1px solid #7C3AED;padding:5px;cursor:pointer">16-Adim Beat Testi</button>
    `;
    panel.style.display = "none";
    btn.onclick = () => {
      const open = panel.style.display === "none";
      panel.style.display = open ? "grid" : "none";
      ensureAudioDsp();
    };
    host.appendChild(btn);
    host.appendChild(panel);
    document.getElementById("kpClarity")?.addEventListener("change", (e) => setDialogueClarity(e.target.checked));
    document.getElementById("kpRg")?.addEventListener("change", (e) => { PRO.replayGain = e.target.checked; });
    document.getElementById("kpPitch")?.addEventListener("input", (e) => {
      const v = Number(e.target.value) || 0;
      const lbl = document.getElementById("kpPitchVal");
      if (lbl) lbl.textContent = String(v);
      setPitchSemitones(v);
    });
    document.getElementById("kpDaw")?.addEventListener("click", () => {
      if (PRO.dawTimer) { stopDaw(); } else {
        PRO.dawSteps[0][0] = PRO.dawSteps[0][8] = true;
        PRO.dawSteps[1][4] = PRO.dawSteps[1][12] = true;
        startDaw(120);
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", mountProPanel);
  } else {
    mountProPanel();
  }

  window.KamiPlayerPro = {
    state: PRO,
    shaderSource: PRO_FS,
    ensureAudioDsp,
    setDialogueClarity,
    setPitchSemitones,
    applyReplayGain,
    startAudioVisualizer,
    triggerDrum,
    startDaw,
    stopDaw,
    mountProPanel,
  };
})();
