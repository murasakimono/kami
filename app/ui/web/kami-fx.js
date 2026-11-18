// KamiFX: WebGL GLSL Akan Obsidian arka plani, View Transitions API ve enerji kivilcimi.
// Tum efektler ayarlardan acilip kapatilabilir; eski Klasik Parcacik moduyla gecislidir.
"use strict";
(() => {
  const ST = { mode: "obsidian", transitions: true, speed: 0, gl: null, canvas: null, raf: 0, t0: performance.now(), pulse: 0 };

  const VS = `attribute vec2 p;void main(){gl_Position=vec4(p,0.,1.);}`;
  const FS = `
    precision mediump float;
    uniform vec2 u_res;
    uniform float u_time;
    uniform float u_speed;
    uniform float u_pulse;
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
      vec2 uv=(gl_FragCoord.xy/u_res)-0.5;
      uv.x*=u_res.x/max(1.0,u_res.y);
      float t=u_time*(0.11+u_speed*0.18);
      vec2 q=vec2(fbm(uv*2.1+vec2(t*0.4,-t*0.3)), fbm(uv*2.1+vec2(-t*0.35,t*0.45)+5.2));
      float n=fbm(uv*2.4+q*1.6+t*0.15);
      float vein=smoothstep(0.46,0.52,abs(n-0.52));
      float glow=(1.0-vein)*(0.25+0.55*u_speed+0.6*u_pulse);
      vec3 base=vec3(0.031,0.022,0.055);
      vec3 vio=vec3(0.18,0.09,0.34)*n*0.75;
      vec3 em=vec3(0.11,0.78,0.56)*glow*0.42;
      float vig=smoothstep(1.05,0.15,length(uv));
      gl_FragColor=vec4((base+vio+em)*vig, 1.0);
    }`;

  function ensureCanvas() {
    if (ST.canvas) return ST.canvas;
    const c = document.createElement("canvas");
    c.id = "skObsidian";
    c.style.cssText = "position:fixed;inset:0;width:100%;height:100%;z-index:0;pointer-events:none;opacity:0;transition:opacity .35s ease";
    document.body.prepend(c);
    ST.canvas = c;
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
    ST.gl = {
      gl,
      uRes: gl.getUniformLocation(prog, "u_res"),
      uTime: gl.getUniformLocation(prog, "u_time"),
      uSpeed: gl.getUniformLocation(prog, "u_speed"),
      uPulse: gl.getUniformLocation(prog, "u_pulse"),
    };
    const resize = () => {
      const dpr = Math.min(1.5, window.devicePixelRatio || 1);
      c.width = Math.max(1, Math.floor(innerWidth * 0.5 * dpr));
      c.height = Math.max(1, Math.floor(innerHeight * 0.5 * dpr));
      gl.viewport(0, 0, c.width, c.height);
    };
    resize();
    window.addEventListener("resize", resize);
    return c;
  }

  function frame(now) {
    ST.raf = 0;
    if (ST.mode !== "obsidian" || document.hidden || !ST.gl) return;
    const { gl, uRes, uTime, uSpeed, uPulse } = ST.gl;
    ST.pulse = Math.max(0, ST.pulse * 0.94);
    gl.uniform2f(uRes, ST.canvas.width, ST.canvas.height);
    gl.uniform1f(uTime, (now - ST.t0) / 1000);
    gl.uniform1f(uSpeed, ST.speed);
    gl.uniform1f(uPulse, ST.pulse);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    ST.raf = requestAnimationFrame(frame);
  }

  function setMode(mode) {
    const m = (mode === "particles" || mode === "off") ? mode : "obsidian";
    ST.mode = m;
    document.body.dataset.bgMode = m;
    if (m === "obsidian") {
      const c = ensureCanvas();
      if (c && ST.gl) {
        c.style.opacity = "1";
        if (!ST.raf && !document.hidden) ST.raf = requestAnimationFrame(frame);
      }
    } else if (ST.canvas) {
      ST.canvas.style.opacity = "0";
      if (ST.raf) { cancelAnimationFrame(ST.raf); ST.raf = 0; }
    }
  }

  function vt(fn) {
    if (!ST.transitions || typeof document.startViewTransition !== "function") return fn();
    try { return document.startViewTransition(fn); } catch { return fn(); }
  }

  function sparkFrom(fromEl, toEl) {
    if (!ST.transitions || !fromEl || !toEl) return;
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

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden && ST.mode === "obsidian" && ST.gl && !ST.raf) ST.raf = requestAnimationFrame(frame);
  });

  window.KamiFX = {
    applySettings(s) {
      if (!s) return;
      ST.transitions = s.ui_transitions !== false;
      const mode = s.sunak_bg_mode || "obsidian";
      setMode(mode);
      if (typeof window.fxApplyMode === "function") window.fxApplyMode(mode);
    },
    setMode,
    setSpeed(v) { ST.speed = Math.max(0, Math.min(1, Number(v) || 0)); },
    pulse() { ST.pulse = 1.0; },
    vt,
    sparkFrom,
  };
})();
