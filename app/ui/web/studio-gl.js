"use strict";
// Kami Studio GPU onizleme gecisi (WebGL2): chroma key + renk tekerlekleri + 3D LUT.
// Matematik studio.py grade_pixel() ile birebir; disa aktarimda ayni ayarlar 33'luk LUT'a pisirilir.
const SGL = (() => {
  const cv = document.createElement("canvas");
  const gl = cv.getContext("webgl2", { premultipliedAlpha: false, preserveDrawingBuffer: true });
  if (!gl) return { ok: false, process: () => null, setLut: () => {} };
  const VS = `#version 300 es
  in vec2 p; out vec2 uv; void main(){ uv = vec2(p.x*.5+.5, .5-p.y*.5); gl_Position = vec4(p,0.,1.); }`;
  const FS = `#version 300 es
  precision highp float; precision highp sampler3D;
  in vec2 uv; out vec4 o;
  uniform sampler2D img; uniform sampler3D lut;
  uniform float exp_, con, sat, temp, tint, lutMix, useLut, lutN;
  uniform vec3 lift, gam, gain;
  uniform float keyOn, keySim, keySmooth, keySpill; uniform vec3 keyCol;
  vec2 uvOf(vec3 c){ return vec2(-0.1146*c.r-0.3854*c.g+0.5*c.b, 0.5*c.r-0.4542*c.g-0.0458*c.b); }
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
    if (useLut > .5) { vec3 l = texture(lut, c*(lutN-1.)/lutN + .5/lutN).rgb; c = mix(c, clamp(l,0.,1.), lutMix); }
    o = vec4(c, a);
  }`;
  function sh(t, src) { const s = gl.createShader(t); gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) console.warn(gl.getShaderInfoLog(s)); return s; }
  const pr = gl.createProgram(); gl.attachShader(pr, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(pr, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(pr); gl.useProgram(pr);
  const buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-1, -1, 1, -1, -1, 1, 1, 1]), gl.STATIC_DRAW);
  const loc = gl.getAttribLocation(pr, "p"); gl.enableVertexAttribArray(loc); gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
  const U = n => gl.getUniformLocation(pr, n);
  const tex = gl.createTexture(); gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, tex);
  for (const [k, v] of [[gl.TEXTURE_MIN_FILTER, gl.LINEAR], [gl.TEXTURE_MAG_FILTER, gl.LINEAR], [gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE], [gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE]]) gl.texParameteri(gl.TEXTURE_2D, k, v);
  gl.uniform1i(U("img"), 0); gl.uniform1i(U("lut"), 1);
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
  return { ok: true, process, setLut, active, has: n => !!luts[n] };
})();
