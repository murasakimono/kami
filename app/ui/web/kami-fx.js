// KamiFX: WebGL GLSL Akan Obsidian arka plani, View Transitions API ve enerji kivilcimi.
// 30 fps sinirli, blur/hidden/reduced-motion duyarli, webglcontextlost kurtarmali, Klasik Parcacik yedekli.
"use strict";
(() => {
  const REDUCED = (() => {
    try { return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false; } catch { return false; }
  })();
  const ST = {
    mode: "obsidian", transitions: true, speed: 0,
    gl: null, canvas: null, raf: 0, t0: performance.now(), last: 0,
    pulse: 0, focused: true, altarX: 0.24, altarY: 0.72,
    tint: [0.0, 0.0, 0.0],
  };

  const VS = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
  const FS = `
    precision mediump float;
    uniform vec2 u_res;
    uniform vec2 u_altar;
    uniform float u_time;
    uniform float u_speed;
    uniform float u_pulse;
    uniform vec3 u_tint;
    float hash(vec2 p){return fract(sin(dot(p,vec2(127.1,311.7)))*43758.5453);}
    float noise(vec2 p){
      vec2 i=floor(p), f=fract(p);
      f=f*f*(3.0-2.0*f);
      return mix(mix(hash(i),hash(i+vec2(1,0)),f.x),mix(hash(i+vec2(0,1)),hash(i+vec2(1,1)),f.x),f.y);
    }
    float fbm(vec2 p){
      float v=0.0, a=0.5;
      for(int i=0;i<4;i++){v+=a*noise(p);p*=2.03;a*=0.5;}
      return v;
    }
    void main(){
      vec2 uv=gl_FragCoord.xy/u_res;
      float asp=u_res.x/max(1.0,u_res.y);
      vec2 p=(uv-0.5)*vec2(asp,1.0);
      vec2 ap=(u_altar-0.5)*vec2(asp,1.0);
      float t=u_time*(0.12+u_speed*0.32);
      vec2 q=vec2(fbm(p*2.1+vec2(t*0.42,-t*0.32)), fbm(p*2.1+vec2(-t*0.36,t*0.44)+5.2));
      float n=fbm(p*2.4+q*1.6+t*0.16);
      float vein=smoothstep(0.34,0.50,abs(n-0.50));
      float glow=(1.0-vein)*(0.36+0.62*u_speed+0.48*u_pulse);
      vec3 base=vec3(0.036,0.020,0.062);
      vec3 vio=vec3(0.32,0.08,0.48)*n*0.82;   // gercek Kami moru (lacivert degil)
      vec3 em=vec3(0.14,0.86,0.62)*glow*0.34;   // zumrut enerji damarlari
      float distA=length(p-ap);
      float aura=exp(-distA*2.2)*(0.24+0.36*u_speed+0.38*u_pulse);
      vec3 altarGlow=mix(vec3(0.36,0.12,0.58),u_tint,0.52)*aura;
      float vig=smoothstep(1.35,0.12,distA);
      vec3 col=(base+vio+em+altarGlow)*vig;
      col=1.0-exp(-col*1.15);
      gl_FragColor=vec4(col, 1.0);
    }`;

  function initWebGL(c) {
    const gl = c.getContext("webgl", { alpha: false, antialias: false, powerPreference: "low-power" });
    if (!gl) return null;
    const sh = (type, src) => { const s = gl.createShader(type); gl.shaderSource(s, src); gl.compileShader(s); return gl.getShaderParameter(s, gl.COMPILE_STATUS) ? s : null; };
    const vs = sh(gl.VERTEX_SHADER, VS), fs = sh(gl.FRAGMENT_SHADER, FS);
    if (!vs || !fs) return null;
    const prog = gl.createProgram();
    gl.attachShader(prog, vs); gl.attachShader(prog, fs); gl.linkProgram(prog);
    if (!gl.getProgramParameter(prog, gl.LINK_STATUS)) return null;
    gl.useProgram(prog);
    const buf = gl.createBuffer();
    gl.bindBuffer(gl.ARRAY_BUFFER, buf);
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
    const loc = gl.getAttribLocation(prog, "p");
    gl.enableVertexAttribArray(loc);
    gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
    return {
      gl,
      uRes: gl.getUniformLocation(prog, "u_res"),
      uAltar: gl.getUniformLocation(prog, "u_altar"),
      uTime: gl.getUniformLocation(prog, "u_time"),
      uSpeed: gl.getUniformLocation(prog, "u_speed"),
      uPulse: gl.getUniformLocation(prog, "u_pulse"),
      uTint: gl.getUniformLocation(prog, "u_tint"),
    };
  }

  function updateAltarCenter() {
    const el = document.getElementById("skAltar");
    if (!el) return;
    const r = el.getBoundingClientRect();
    if (r.width > 0 && innerWidth > 0 && innerHeight > 0) {
      ST.altarX = (r.left + r.width * 0.5) / innerWidth;
      ST.altarY = 1.0 - (r.top + r.height * 0.5) / innerHeight;
    }
  }

  function ensureCanvas() {
    if (ST.canvas) return ST.canvas;
    const c = document.createElement("canvas");
    c.id = "skObsidian";
    c.style.cssText = "position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;opacity:0;transition:opacity .35s ease";
    document.body.prepend(c);
    ST.canvas = c;
    c.addEventListener("webglcontextlost", (e) => {
      e.preventDefault();
      if (ST.raf) { cancelAnimationFrame(ST.raf); ST.raf = 0; }
      ST.gl = null;
      if (ST.mode === "obsidian" && typeof window.fxApplyMode === "function") window.fxApplyMode("particles");
    });
    c.addEventListener("webglcontextrestored", () => {
      ST.gl = initWebGL(c);
      if (ST.gl && ST.mode === "obsidian") {
        c.style.opacity = "1";
        if (typeof window.fxApplyMode === "function") window.fxApplyMode("obsidian");
        startLoop();
      }
    });
    ST.gl = initWebGL(c);
    if (!ST.gl) return null;
    const resize = () => {
      const dpr = Math.min(1.5, window.devicePixelRatio || 1);
      c.width = Math.max(1, Math.floor(innerWidth * 0.5 * dpr));
      c.height = Math.max(1, Math.floor(innerHeight * 0.5 * dpr));
      ST.gl?.gl.viewport(0, 0, c.width, c.height);
      updateAltarCenter();
    };
    resize();
    window.addEventListener("resize", resize);
    return c;
  }

  function startLoop() {
    if (!ST.raf && ST.mode === "obsidian" && ST.gl && !document.hidden && ST.focused && !REDUCED) {
      ST.raf = requestAnimationFrame(frame);
    }
  }

  function frame(now) {
    ST.raf = 0;
    if (ST.mode !== "obsidian" || document.hidden || !ST.focused || !ST.gl) return;
    if (now - ST.last < 33) { ST.raf = requestAnimationFrame(frame); return; } // 30 fps siniri
    ST.last = now;
    const { gl, uRes, uAltar, uTime, uSpeed, uPulse, uTint } = ST.gl;
    ST.pulse = Math.max(0, ST.pulse * 0.92);
    gl.uniform2f(uRes, ST.canvas.width, ST.canvas.height);
    gl.uniform2f(uAltar, ST.altarX, ST.altarY);
    gl.uniform1f(uTime, (now - ST.t0) / 1000);
    gl.uniform1f(uSpeed, ST.speed);
    gl.uniform1f(uPulse, ST.pulse);
    gl.uniform3f(uTint, ST.tint[0], ST.tint[1], ST.tint[2]);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (!REDUCED) ST.raf = requestAnimationFrame(frame);
  }

  function setMode(mode) {
    const m = (mode === "particles" || mode === "off") ? mode : "obsidian";
    ST.mode = m;
    document.body.dataset.bgMode = m;
    if (m === "obsidian") {
      const c = ensureCanvas();
      if (c && ST.gl) {
        c.style.opacity = "1";
        if (REDUCED) frame(performance.now());
        else startLoop();
      } else {
        // WebGL yoksa otomatik Klasik Parcacik yedegine dus
        ST.mode = "particles";
        document.body.dataset.bgMode = "particles";
        if (typeof window.fxApplyMode === "function") window.fxApplyMode("particles");
      }
    } else if (ST.canvas) {
      ST.canvas.style.opacity = "0";
      if (ST.raf) { cancelAnimationFrame(ST.raf); ST.raf = 0; }
    }
  }

  function vt(fn) {
    if (REDUCED || !ST.transitions || typeof document.startViewTransition !== "function") return fn();
    try { return document.startViewTransition(fn); } catch { return fn(); }
  }

  function sparkFrom(fromEl, toEl) {
    if (REDUCED || !ST.transitions || !fromEl || !toEl) return;
    const a = fromEl.getBoundingClientRect(), b = toEl.getBoundingClientRect();
    if (!a.width || !b.width) return;
    const dot = document.createElement("div");
    dot.style.cssText = `position:fixed;left:${a.left + a.width * 0.5}px;top:${a.top + a.height * 0.5}px;width:12px;height:12px;margin:-6px 0 0 -6px;border-radius:50%;background:#2EE6A6;box-shadow:0 0 18px 4px rgba(46,230,166,.85);z-index:9500;pointer-events:none;transition:transform .48s cubic-bezier(.22,1,.36,1),opacity .48s ease`;
    document.body.appendChild(dot);
    requestAnimationFrame(() => {
      const dx = (b.left + b.width * 0.5) - (a.left + a.width * 0.5);
      const dy = (b.top + b.height * 0.5) - (a.top + a.height * 0.5);
      dot.style.transform = `translate(${dx}px, ${dy}px) scale(0.4)`;
      dot.style.opacity = "0";
    });
    setTimeout(() => { dot.remove(); ST.pulse = 1.0; }, 500);
  }

  document.addEventListener("visibilitychange", () => { if (!document.hidden && ST.focused) startLoop(); });
  window.addEventListener("blur", () => { ST.focused = false; if (ST.raf) { cancelAnimationFrame(ST.raf); ST.raf = 0; } });
  window.addEventListener("focus", () => { ST.focused = true; startLoop(); });

  window.KamiFX = {
    applySettings(s) {
      if (!s) return;
      ST.transitions = s.ui_transitions !== false;
      const mode = s.sunak_bg_mode || "obsidian";
      setMode(mode);
      if (typeof window.fxApplyMode === "function") window.fxApplyMode(ST.mode);
    },
    setMode,
    setSpeed(v) { ST.speed = Math.max(0, Math.min(1, Number(v) || 0)); },
    setTint(r, g, b) { ST.tint = [r / 255, g / 255, b / 255]; },
    pulse() { ST.pulse = 1.0; },
    vt,
    sparkFrom,
  };
})();
