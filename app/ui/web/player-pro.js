// Faz 12 — Kami Player Pro: libplacebo WebGL2 Shader, AudioWorklet Canli DSP, Kelime Karaoke & 16-Adim DAW
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
      // KrigBilateral benzeri kenar korumali keskinlestirme
      vec3 detail = c - blur;
      float edge = clamp(1.0 - length(detail) * 3.0, 0.2, 1.0);
      c = clamp(c + detail * (0.65 * edge), 0.0, 1.0);
    } else if (u_mode == 2) {
      // SSimSuperRes benzeri lokal kontrast + mikro detay
      vec3 hi = c - blur;
      c = clamp(c + hi * 0.95, 0.0, 1.0);
    } else if (u_mode == 3) {
      // Adaptive Deband + Film Grain
      float g = (hash12(v_uv * u_res + fract(u_time) * 100.0) - 0.5) * 0.035;
      c = clamp(mix(blur, c, 0.85) + g, 0.0, 1.0);
    }
    gl_FragColor = vec4(c, 1.0);
  }`;

  // ---------- 12.2 Inline AudioWorklet Canli DSP ----------
  const WORKLET_CODE = `
  class KamiDspProcessor extends AudioWorkletProcessor {
    static get parameterDescriptors() {
      return [{ name: "pitchRatio", defaultValue: 1.0, minValue: 0.5, maxValue: 2.0 }];
    }
    constructor() {
      super();
      this.buf = new Float32Array(8192);
      this.w = 0;
      this.r = 0.0;
    }
    process(inputs, outputs, parameters) {
      const inp = inputs[0], out = outputs[0];
      if (!inp || !inp[0] || !out || !out[0]) return true;
      const ratio = parameters.pitchRatio[0] || 1.0;
      const src = inp[0];
      const len = this.buf.length;
      if (Math.abs(ratio - 1.0) < 0.01) {
        for (let ch = 0; ch < out.length; ch++) {
          const s = inp[ch] || src;
          out[ch].set(s);
        }
        return true;
      }
      for (let i = 0; i < src.length; i++) {
        this.buf[this.w] = src[i];
        this.w = (this.w + 1) % len;
        const idx = Math.floor(this.r) % len;
        const val = this.buf[idx];
        this.r = (this.r + ratio) % len;
        for (let ch = 0; ch < out.length; ch++) out[ch][i] = val;
      }
      return true;
    }
  }
  registerProcessor("kami-dsp-processor", KamiDspProcessor);`;

  async function ensureAudioDsp() {
    if (typeof PL === "undefined" || !PL.ctx || !PL.gain) return;
    if (!PRO.clarityFilter) {
      PRO.clarityFilter = PL.ctx.createBiquadFilter();
      PRO.clarityFilter.type = "peaking";
      PRO.clarityFilter.frequency.value = 2800;
      PRO.clarityFilter.Q.value = 1.2;
      PRO.clarityFilter.gain.value = 0;
    }
    if (!PRO.rgGain) {
      PRO.rgGain = PL.ctx.createGain();
      PRO.rgGain.gain.value = 1.0;
    }
    if (!PRO.analyser) {
      PRO.analyser = PL.ctx.createAnalyser();
      PRO.analyser.fftSize = 256;
      try {
        PL.gain.connect(PRO.clarityFilter);
        PRO.clarityFilter.connect(PRO.rgGain);
        PRO.rgGain.connect(PRO.analyser);
      } catch { /* zaten bagli */ }
    }
    if (!PRO.workletReady && PL.ctx.audioWorklet) {
      try {
        const blob = new Blob([WORKLET_CODE], { type: "application/javascript" });
        const url = URL.createObjectURL(blob);
        await PL.ctx.audioWorklet.addModule(url);
        URL.revokeObjectURL(url);
        PRO.workletNode = new AudioWorkletNode(PL.ctx, "kami-dsp-processor");
        PRO.workletReady = true;
      } catch { /* Worklet desteklenmiyorsa pas gec */ }
    }
  }

  function setDialogueClarity(on) {
    PRO.dialogueClarity = !!on;
    ensureAudioDsp();
    if (PRO.clarityFilter) PRO.clarityFilter.gain.value = PRO.dialogueClarity ? 6.5 : 0;
  }

  function setPitchSemitones(semi) {
    PRO.pitchSemi = Math.max(-12, Math.min(12, Number(semi) || 0));
    const ratio = Math.pow(2, PRO.pitchSemi / 12);
    if (PRO.workletNode?.parameters) {
      const p = PRO.workletNode.parameters.get("pitchRatio");
      if (p) p.value = ratio;
    }
  }

  async function applyReplayGain(path) {
    if (!PRO.replayGain || !path || typeof api === "undefined" || !api.player_replaygain) return;
    try {
      const r = await api.player_replaygain(path);
      if (r?.ok && PRO.rgGain) PRO.rgGain.gain.value = r.linear_gain || 1.0;
    } catch { /* sessiz */ }
  }

  // ---------- 12.3 WebGL2 Shader Muzik Gorsellestirici ----------
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
    ensureAudioDsp();
    const ac = typeof PL !== "undefined" && PL.ctx ? PL.ctx : new (window.AudioContext || window.webkitAudioContext)();
    if (ac.state === "suspended") ac.resume();
    const now = ac.currentTime;
    const osc = ac.createOscillator();
    const g = ac.createGain();
    if (trackIdx === 0) { // Kick
      osc.type = "sine";
      osc.frequency.setValueAtTime(140, now);
      osc.frequency.exponentialRampToValueAtTime(42, now + 0.14);
      g.gain.setValueAtTime(0.7, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.18);
    } else if (trackIdx === 1) { // Snare
      osc.type = "triangle";
      osc.frequency.setValueAtTime(210, now);
      g.gain.setValueAtTime(0.35, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.11);
    } else if (trackIdx === 2) { // Hat
      osc.type = "square";
      osc.frequency.setValueAtTime(840, now);
      g.gain.setValueAtTime(0.12, now);
      g.gain.exponentialRampToValueAtTime(0.001, now + 0.045);
    } else { // Bass Synth
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
  };
})();
