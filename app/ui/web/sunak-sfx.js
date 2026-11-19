"use strict";
(() => {
  const SFX_KEY = "kami.sfx";
  const COSTUME_KEY = "kami.costume";
  let ctx = null;

  function isMediaActive() {
    if (window.kamiMediaPlaying) return true;
    try {
      for (const el of document.querySelectorAll("audio, video")) {
        if (!el.paused && !el.muted && el.volume > 0) return true;
      }
    } catch {}
    return false;
  }

  function playTone(freqs, dur = 0.09, type = "sine", vol = 0.05) {
    if (localStorage.getItem(SFX_KEY) === "0" || isMediaActive()) return;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === "suspended") ctx.resume();
      const now = ctx.currentTime;
      freqs.forEach((f, i) => {
        const osc = ctx.createOscillator();
        const gain = ctx.createGain();
        osc.type = type;
        osc.frequency.setValueAtTime(f, now + i * 0.055);
        gain.gain.setValueAtTime(vol, now + i * 0.055);
        gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.055 + dur);
        osc.connect(gain);
        gain.connect(ctx.destination);
        osc.start(now + i * 0.055);
        osc.stop(now + i * 0.055 + dur + 0.01);
      });
    } catch { /* ses yok */ }
  }

  function sfxPageRustle() {
    if (localStorage.getItem(SFX_KEY) === "0" || isMediaActive()) return;
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      if (ctx.state === "suspended") ctx.resume();
      const len = Math.floor(ctx.sampleRate * 0.09);
      const buf = ctx.createBuffer(1, len, ctx.sampleRate);
      const ch = buf.getChannelData(0);
      for (let i = 0; i < len; i++) ch[i] = (Math.random() * 2 - 1) * (1 - i / len);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      const flt = ctx.createBiquadFilter();
      flt.type = "bandpass";
      flt.frequency.value = 1850;
      flt.Q.value = 1.4;
      const g = ctx.createGain();
      const now = ctx.currentTime;
      g.gain.setValueAtTime(0.032, now);
      g.gain.exponentialRampToValueAtTime(0.0005, now + 0.09);
      src.connect(flt);
      flt.connect(g);
      g.connect(ctx.destination);
      src.start(now);
    } catch {}
  }

  const COSTUMES = {
    default: "",
    oni: "hue-rotate(310deg) saturate(1.45) contrast(1.08)",
    ice: "hue-rotate(155deg) saturate(1.2) brightness(1.08)",
    gold: "sepia(0.55) hue-rotate(8deg) saturate(1.7) brightness(1.05)",
    cyber: "hue-rotate(245deg) saturate(1.6) contrast(1.12)",
  };

  function applyCostume(name) {
    const id = name && name in COSTUMES ? name : (localStorage.getItem(COSTUME_KEY) || "default");
    localStorage.setItem(COSTUME_KEY, id);
    const el = document.querySelector("#skEye, #sunak .sk-char");
    if (el) el.style.filter = COSTUMES[id] || "";
    window.KamiSunakGPU?.setCostume?.(id);
    return id;
  }

  window.kamiSfx = {
    play: (kind) => {
      if (kind === "page") sfxPageRustle();
      else if (kind === "start") playTone([523.25, 659.25], 0.08, "triangle", 0.045);
      else if (kind === "done") playTone([523.25, 659.25, 783.99, 880], 0.11, "sine", 0.05);
      else if (kind === "error") playTone([293.66, 220], 0.12, "triangle", 0.045);
      else playTone([587.33], 0.038, "sine", 0.025);
    },
    isOn: () => localStorage.getItem(SFX_KEY) !== "0",
    setOn: (v) => localStorage.setItem(SFX_KEY, v ? "1" : "0"),
    costumes: Object.keys(COSTUMES),
    getCostume: () => localStorage.getItem(COSTUME_KEY) || "default",
    setCostume: (id) => applyCostume(id),
  };

  window.addEventListener("pywebviewready", () => {
    setTimeout(() => applyCostume(), 500);
  });
  document.addEventListener("click", (e) => {
    if (e.target.closest?.(".eco-btn, .sk-room")) window.kamiSfx.play("click");
  }, true);
})();
