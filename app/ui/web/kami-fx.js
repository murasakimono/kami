// KamiFX: WebGL GLSL Akan Obsidian arka plani, View Transitions API ve enerji kivilcimi.
// 30 fps sinirli, blur/hidden/reduced-motion duyarli, webglcontextlost kurtarmali, Klasik Parcacik yedekli.
"use strict";
(() => {
  const REDUCED = (() => {
    try { return window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches || false; } catch { return false; }
  })();
  const ST = {
    mode: "obsidian", transitions: true, speed: 0,
    gl: null, canvas: null, raf: 0, t0: performance.now(), last: 0, phase: 0,
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
    uniform float u_mode;
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
      float distA=length(p-ap);
      float vig=smoothstep(1.45,0.18,distA);
      if(u_mode > 0.5){
        // Ruh Atesi: maskotun altindaki zumrut alevden yukselen keskin duman/ates telleri + kozler
        vec2 fp=p-(ap+vec2(0.0,-0.20));
        float rise=u_time*0.75;
        float sway=sin(fp.y*7.0-rise*1.6)*0.045*(0.4+abs(fp.y)*2.5);
        float w1=fbm(vec2((fp.x+sway)*7.5, fp.y*3.6-rise));
        float w2=fbm(vec2((fp.x-sway*0.7)*13.0, fp.y*6.0-rise*1.45)+3.1);
        float envX=exp(-abs(fp.x)*(4.8-1.6*u_speed));
        float envY=smoothstep(-0.14,0.03,fp.y)*smoothstep(0.82+u_speed*0.42,-0.06,fp.y);
        float tongue=smoothstep(0.36,0.74,w1*0.65+w2*0.35)*envX*envY;
        float core=smoothstep(0.45,0.85,w2)*exp(-length(fp*vec2(3.6,2.4))*3.2)*smoothstep(-0.10,0.02,fp.y);
        // kucuk yukselen koz noktaları
        vec2 ep=vec2(fp.x*18.0, fp.y*10.0-rise*2.2);
        vec2 eid=floor(ep);
        vec2 ef=fract(ep)-0.5;
        float er=hash(eid);
        float ember=step(0.92,er)*smoothstep(0.24,0.02,length(ef-vec2(sin(er*20.0+u_time)*0.15,0.0)))*envX*envY;
        vec3 base=vec3(0.024,0.015,0.042);
        vec3 vioAura=vec3(0.26,0.07,0.44)*envX*envY*0.42;
        vec3 fire=mix(vec3(0.06,0.62,0.46),vec3(0.32,0.98,0.74),clamp(core*1.4,0.0,1.0))*(tongue*0.72+core*0.85+ember*1.2)*(0.65+0.65*u_speed+0.7*u_pulse);
        vec3 flare=mix(vec3(0.18,0.92,0.66),u_tint,0.4)*u_pulse*exp(-distA*3.0)*0.45;
        vec3 col=(base+vioAura+fire+flare)*vig;
        gl_FragColor=vec4(1.0-exp(-col*1.15),1.0);
        return;
      }
      // Akan Obsidian: koyu cilali volkanik cam + cok ince zarif mor/zumrut kilcal damarlar
      float t=u_time;
      vec2 q=vec2(fbm(p*2.6+vec2(t*0.30,-t*0.22)), fbm(p*2.6+vec2(-t*0.24,t*0.31)+4.7));
      float n=fbm(p*3.4+q*1.45+t*0.12);
      float fil=pow(clamp(1.0-abs(n-0.50)*9.5,0.0,1.0),3.2);
      vec3 base=vec3(0.028,0.016,0.048);
      vec3 vio=vec3(0.20,0.06,0.34)*smoothstep(0.36,0.82,n)*0.45;
      vec3 em=mix(vec3(0.45,0.22,0.85),vec3(0.14,0.86,0.62),smoothstep(0.15,0.85,u_speed+u_pulse))*fil*(0.28+0.55*u_speed+0.65*u_pulse);
      float aura=exp(-distA*2.4)*(0.18+0.26*u_speed+0.32*u_pulse);
      vec3 altarGlow=mix(vec3(0.28,0.10,0.48),u_tint,0.45)*aura;
      vec3 col=(base+vio+em+altarGlow)*vig;
      gl_FragColor=vec4(1.0-exp(-col*1.12),1.0);
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
      uMode: gl.getUniformLocation(prog, "u_mode"),
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
      const dpr = Math.min(1.25, window.devicePixelRatio || 1);
      c.width = Math.max(1, Math.floor(innerWidth * dpr));
      c.height = Math.max(1, Math.floor(innerHeight * dpr));
      ST.gl?.gl.viewport(0, 0, c.width, c.height);
      updateAltarCenter();
    };
    resize();
    window.addEventListener("resize", resize);
    return c;
  }

  const isGlMode = (m) => m === "obsidian" || m === "spirit_fire";

  function startLoop() {
    if (!ST.raf && isGlMode(ST.mode) && ST.gl && !document.hidden && ST.focused && !REDUCED) {
      ST.raf = requestAnimationFrame(frame);
    }
  }

  function frame(now) {
    ST.raf = 0;
    if (!isGlMode(ST.mode) || document.hidden || !ST.focused || !ST.gl) return;
    if (now - ST.last < 33) { ST.raf = requestAnimationFrame(frame); return; } // 30 fps siniri
    const dt = ST.last ? Math.min(0.1, (now - ST.last) / 1000) : 0.033;
    ST.last = now;
    ST.phase += dt * (0.10 + ST.speed * 0.35);
    const { gl, uRes, uAltar, uTime, uSpeed, uPulse, uTint, uMode } = ST.gl;
    ST.pulse = Math.max(0, ST.pulse * 0.92);
    gl.uniform2f(uRes, ST.canvas.width, ST.canvas.height);
    gl.uniform2f(uAltar, ST.altarX, ST.altarY);
    gl.uniform1f(uTime, ST.phase);
    gl.uniform1f(uSpeed, ST.speed);
    gl.uniform1f(uPulse, ST.pulse);
    gl.uniform3f(uTint, ST.tint[0], ST.tint[1], ST.tint[2]);
    gl.uniform1f(uMode, ST.mode === "spirit_fire" ? 1.0 : 0.0);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    if (!REDUCED) ST.raf = requestAnimationFrame(frame);
  }

  function setMode(mode) {
    const m = (mode === "particles" || mode === "off" || mode === "spirit_fire") ? mode : "obsidian";
    ST.mode = m;
    document.body.dataset.bgMode = m;
    if (isGlMode(m)) {
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
