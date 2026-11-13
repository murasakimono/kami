"use strict";
// Kami Studio GPU onizleme gecisi (WebGL2): chroma key + renk tekerlekleri + 3D LUT.
// Matematik studio.py grade_pixel() ile birebir; disa aktarimda ayni ayarlar 33'luk LUT'a pisirilir.
const SGL = (() => {
  const cv = document.createElement("canvas");
  const gl = cv.getContext("webgl2", { premultipliedAlpha: false, preserveDrawingBuffer: true });
  if (!gl) return { ok: false, process: () => null, processToFbo: () => null, disposeFbo: () => {}, fboStats: () => ({ count: 0, keys: [] }), setLut: () => {} };
  const VS = `#version 300 es
  in vec2 p; out vec2 uv; void main(){ uv = vec2(p.x*.5+.5, .5-p.y*.5); gl_Position = vec4(p,0.,1.); }`;
  const FS = `#version 300 es
  precision highp float; precision highp sampler3D;
  in vec2 uv; out vec4 o;
  uniform sampler2D img; uniform sampler3D lut; uniform sampler2D curveTex;
  uniform float exp_, con, sat, temp, tint, lutMix, useLut, lutN;
  uniform float vig, grain, halation, timeSeed, useCurve;
  uniform vec3 lift, gam, gain;
  uniform float keyOn, keySim, keySmooth, keySpill; uniform vec3 keyCol;
  vec2 uvOf(vec3 c){ return vec2(-0.1146*c.r-0.3854*c.g+0.5*c.b, 0.5*c.r-0.4542*c.g-0.0458*c.b); }
  float hash12(vec2 p){ return fract(sin(dot(p, vec2(12.9898, 78.233))) * 43758.5453); }
  void main(){
    vec4 s = texture(img, uv); vec3 c = s.rgb; float a = s.a;
    if (keyOn > .5) {
      float d = distance(uvOf(c), uvOf(keyCol)) * 1.6;
      float k = keySmooth > 0.001 ? clamp((d - keySim) / keySmooth, 0., 1.) : step(keySim, d);
      a *= k;
      if (keySpill > .5) { if (keyCol.g >= keyCol.b) c.g = min(c.g, max(c.r, c.b)); else c.b = min(c.b, max(c.r, c.g)); }
    }
    c *= exp2(exp_);
    c.r *= 1. + .12*temp; c.b *= 1. - .12*temp; c.g *= 1. - .10*tint;
    c = clamp(c*(1.+gain) + lift*(1.-c), 0., 1.);
    c = pow(c, 1. / max(vec3(.05), 1. + gam));
    c = (c - .5) * (1. + con) + .5;
    float y = dot(c, vec3(.2126, .7152, .0722));
    c = clamp(vec3(y) + (c - vec3(y)) * sat, 0., 1.);
    if (useCurve > .5) {
      c.r = texture(curveTex, vec2(c.r, .5)).r;
      c.g = texture(curveTex, vec2(c.g, .5)).g;
      c.b = texture(curveTex, vec2(c.b, .5)).b;
    }
    if (useLut > .5) { vec3 l = texture(lut, c*(lutN-1.)/lutN + .5/lutN).rgb; c = mix(c, clamp(l,0.,1.), lutMix); }
    if (halation > .005) {
      vec3 b1 = (texture(img, uv + vec2(.006, 0.)).rgb + texture(img, uv - vec2(.006, 0.)).rgb + texture(img, uv + vec2(0., .008)).rgb + texture(img, uv - vec2(0., .008)).rgb) * .25;
      float hi = max(0., dot(b1, vec3(.3,.6,.1)) - .68);
      vec3 glow = vec3(1., .36, .14) * hi * 2.6 * halation;
      c = clamp(1. - (1. - c) * (1. - clamp(glow, 0., .85)), 0., 1.);
    }
    if (vig > .005) {
      float rd = length((uv - .5) * vec2(1.18, 1.));
      c *= clamp(1. - vig * 1.15 * pow(rd * 1.35, 2.2), .10, 1.);
    }
    if (grain > .005) {
      float n = (hash12(uv * vec2(960., 540.) + vec2(timeSeed * 19.7, timeSeed * 7.3)) - .5) * grain * .22;
      c = clamp(c + vec3(n), 0., 1.);
    }
    o = vec4(c, a);
  }`;
  function sh(t, src) { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s)); return s; }
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = n => gl.getUniformLocation(pr, n);
  const tex = gl.createTexture(); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  gl.uniform1i(U("img"), 0); gl.uniform1i(U("lut"), 1); gl.uniform1i(U("curveTex"), 2);
  const cTex = gl.createTexture(); gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, cTex);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  const cBuf = new Uint8Array(256 * 4);
  let lastCurveKey = "";
  function evalCurvePts(pts, x) {
    if (!pts || pts.length < 2) return x;
    const s = [...pts].filter(p => p && p.length >= 2).map(p => [+p[0], +p[1]]).sort((a, b) => a[0] - b[0]);
    if (s.length < 2) return x;
    if (x <= s[0][0]) return Math.max(0, Math.min(1, s[0][1]));
    for (let i = 0; i < s.length - 1; i++) {
      const [x0, y0] = s[i], [x1, y1] = s[i + 1];
      if (x <= x1) return Math.max(0, Math.min(1, y0 + (y1 - y0) * ((x - x0) / Math.max(1e-6, x1 - x0))));
    }
    return Math.max(0, Math.min(1, s[s.length - 1][1]));
  }
  function syncCurves(crv) {
    const has = crv && ["luma", "r", "g", "b"].some(ch => Array.isArray(crv[ch]) && crv[ch].length >= 2);
    if (!has) return false;
    const key = JSON.stringify(crv);
    if (key !== lastCurveKey) {
      lastCurveKey = key;
      for (let i = 0; i < 256; i++) {
        const x = i / 255;
        const lu = crv.luma ? evalCurvePts(crv.luma, x) : x;
        cBuf[i * 4] = Math.round(evalCurvePts(crv.r, lu) * 255);
        cBuf[i * 4 + 1] = Math.round(evalCurvePts(crv.g, lu) * 255);
        cBuf[i * 4 + 2] = Math.round(evalCurvePts(crv.b, lu) * 255);
        cBuf[i * 4 + 3] = 255;
      }
      gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, cTex);
      gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, 256, 1, 0, gl.RGBA, gl.UNSIGNED_BYTE, cBuf);
      gl.activeTexture(gl.TEXTURE0);
    }
    return true;
  }
  const luts = {};   // ad -> 3D doku
  function setLut(name, n, data) {
    gl.activeTexture(gl.TEXTURE1);
    const t = gl.createTexture(); gl.bindTexture(gl.TEXTURE_3D, t);
    gl.texImage3D(gl.TEXTURE_3D, 0, gl.RGB16F, n, n, n, 0, gl.RGB, gl.FLOAT, new Float32Array(data));
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_R, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_3D, k, v);
    luts[name] = { t, n }; gl.activeTexture(gl.TEXTURE0);
  }
  const hex = h => { h = (h || "#00ff00").replace("#", ""); return [0, 2, 4].map(i => parseInt(h.substr(i, 2), 16) / 255); };
  const v3 = a => (a && a.length === 3 ? a.map(Number) : [0, 0, 0]);
  function active(c) {
    const g = c.grade || {}, k = c.key || {};
    if (k.on) return true;
    if (g.lut && (g.lutMix ?? 1) > 0) return true;
    if ((g.vignette || 0) > 0.005 || (g.grain || 0) > 0.005 || (g.halation || 0) > 0.005) return true;
    if (g.curves && ["luma", "r", "g", "b"].some(ch => Array.isArray(g.curves[ch]) && g.curves[ch].length >= 2)) return true;
    if (["exp", "con", "temp", "tint"].some(x => Math.abs(g[x] || 0) > 1e-4) || Math.abs((g.sat ?? 1) - 1) > 1e-4) return true;
    return ["lift", "gamma", "gain"].some(w => (g[w] || []).some(v => Math.abs(v) > 1e-4));
  }
  // kaynak tuvali isle, sonuc tuvalini don (bekleyen LUT yuklenmemisse LUT'suz)
  function process(src, w, h, c) {
    if (cv.width !== w || cv.height !== h) { cv.width = w; cv.height = h; }
    gl.viewport(0, 0, w, h);
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, src);
    const g = c.grade || {}, k = c.key || {};
    gl.uniform1f(U("exp_"), +g.exp || 0); gl.uniform1f(U("con"), +g.con || 0); gl.uniform1f(U("sat"), g.sat ?? 1);
    gl.uniform1f(U("temp"), +g.temp || 0); gl.uniform1f(U("tint"), +g.tint || 0);
    gl.uniform1f(U("vig"), +g.vignette || 0); gl.uniform1f(U("grain"), +g.grain || 0); gl.uniform1f(U("halation"), +g.halation || 0);
    gl.uniform1f(U("timeSeed"), (performance.now() * 0.001) % 100);
    const hasC = syncCurves(g.curves);
    gl.uniform1f(U("useCurve"), hasC ? 1 : 0);
    if (hasC) { gl.activeTexture(gl.TEXTURE2); gl.bindTexture(gl.TEXTURE_2D, cTex); gl.activeTexture(gl.TEXTURE0); }
    gl.uniform3fv(U("lift"), v3(g.lift)); gl.uniform3fv(U("gam"), v3(g.gamma)); gl.uniform3fv(U("gain"), v3(g.gain));
    const lt = g.lut && luts[g.lut];
    gl.uniform1f(U("useLut"), lt ? 1 : 0); gl.uniform1f(U("lutMix"), g.lutMix ?? 1);
    if (lt) { gl.activeTexture(gl.TEXTURE1); gl.bindTexture(gl.TEXTURE_3D, lt.t); gl.activeTexture(gl.TEXTURE0); gl.uniform1f(U("lutN"), lt.n); }
    gl.uniform1f(U("keyOn"), k.on ? 1 : 0); gl.uniform1f(U("keySim"), k.sim ?? .15); gl.uniform1f(U("keySmooth"), k.smooth ?? .08);
    gl.uniform1f(U("keySpill"), k.spill === false ? 0 : 1); gl.uniform3fv(U("keyCol"), hex(k.color));
    gl.clearColor(0, 0, 0, 0); gl.clear(gl.COLOR_BUFFER_BIT);
    gl.drawArrays(gl.TRIANGLE_STRIP, 0, 4);
    return cv;
  }
  // Faz 7.3: WebGL2 FBO ping-pong havuzu (coklu gecis shader onbellekleme ve VRAM dostu temizlik)
  const fboPool = new Map();
  function ensureFbo(key, w, h) {
    let entry = fboPool.get(key);
    if (entry && entry.w === w && entry.h === h) return entry;
    if (entry) {
      gl.deleteFramebuffer(entry.fb);
      gl.deleteTexture(entry.tex);
    }
    const t = gl.createTexture();
    gl.bindTexture(gl.TEXTURE_2D, t);
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, w, h, 0, gl.RGBA, gl.UNSIGNED_BYTE, null);
    for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) {
      gl.texParameteri(gl.TEXTURE_2D, k, v);
    }
    const fb = gl.createFramebuffer();
    gl.bindFramebuffer(gl.FRAMEBUFFER, fb);
    gl.framebufferTexture2D(gl.FRAMEBUFFER, gl.COLOR_ATTACHMENT0, gl.TEXTURE_2D, t, 0);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    entry = { fb, tex: t, w, h };
    fboPool.set(key, entry);
    return entry;
  }
  function processToFbo(key, src, w, h, c) {
    const target = ensureFbo(key, w, h);
    gl.bindFramebuffer(gl.FRAMEBUFFER, target.fb);
    process(src, w, h, c);
    gl.bindFramebuffer(gl.FRAMEBUFFER, null);
    return target;
  }
  function disposeFbo(key) {
    if (key) {
      const e = fboPool.get(key);
      if (e) { gl.deleteFramebuffer(e.fb); gl.deleteTexture(e.tex); fboPool.delete(key); }
      return;
    }
    for (const e of fboPool.values()) { gl.deleteFramebuffer(e.fb); gl.deleteTexture(e.tex); }
    fboPool.clear();
  }
  function fboStats() { return { count: fboPool.size, keys: [...fboPool.keys()] }; }
  return { ok: true, process, processToFbo, ensureFbo, disposeFbo, fboStats, setLut, active, has: n => !!luts[n] };
})();
