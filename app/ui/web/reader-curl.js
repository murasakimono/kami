// Kami Reader — Gercek WebGL 3D Fiziksel Sayfa Kivrimi (Conical/Cylindrical Curl Shader + Pointer Drag)
"use strict";
(() => {
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));

  class KamiPageCurl {
    constructor() {
      this.canvas = null;
      this.gl = null;
      this.prog = null;
      this.buf = null;
      this.idx = null;
      this.count = 0;
      this.texA = null;
      this.texB = null;
      this.raf = 0;
      this.turning = false;
    }

    ensureCanvas(stage) {
      if (!this.canvas) {
        const cv = document.createElement("canvas");
        cv.id = "rdCurlCanvas";
        cv.style.cssText = "position:fixed;pointer-events:none;z-index:25;display:none;";
        document.body.appendChild(cv);
        this.canvas = cv;
        this._initGL();
      }
      return this.canvas;
    }

    _initGL() {
      if (this.gl || !this.canvas) return;
      const gl = this.canvas.getContext("webgl", { alpha: true, antialias: true, premultipliedAlpha: true });
      if (!gl) return;
      this.gl = gl;

      const vs = `
        attribute vec2 aPos;
        varying vec2 vUv;
        varying float vShade;
        varying float vDrop;
        uniform float uProg;
        uniform float uDir;
        uniform float uR;
        uniform float uCorner;
        void main() {
          vUv = aPos;
          // Normalize coordinate along curl direction (0 = spine, 1 = leading outer edge)
          float u = uDir > 0.0 ? aPos.x : (1.0 - aPos.x);
          float v = mix(0.0, aPos.y - 0.5, uCorner);
          // Curl line starts at u = 1.0 and sweeps across to u = -0.35
          float line = mix(1.06, -0.36, uProg) + v * 0.22;
          float d = u - line;
          vec3 p = vec3(aPos.x * 2.0 - 1.0, 1.0 - aPos.y * 2.0, 0.0);
          vShade = 1.0;
          vDrop = 0.0;
          if (d > 0.0) {
            float arc = clamp(d / max(0.02, uR), 0.0, 3.14159265);
            float rolled = sin(arc) * uR;
            float z = (1.0 - cos(arc)) * uR;
            float flatTail = max(0.0, d - 3.14159265 * uR);
            float nx = (arc < 3.14159265) ? (line + rolled) : (line - flatTail);
            float worldX = uDir > 0.0 ? (nx * 2.0 - 1.0) : ((1.0 - nx) * 2.0 - 1.0);
            p.x = worldX;
            p.z = min(0.75, z * 1.45);
            // Gentle cylindrical crest & backface lift lighting
            vShade = (arc > 1.57) ? (0.86 + 0.14 * cos(arc)) : (1.0 - 0.18 * sin(arc));
          } else {
            vDrop = exp(d * 14.0) * 0.35 * sin(uProg * 3.14159);
          }
          float persp = 1.0 + p.z * 0.42;
          gl_Position = vec4(p.xy * (1.0 + p.z * 0.14), p.z * 0.3, persp);
        }
      `;

      const fs = `
        precision mediump float;
        varying vec2 vUv;
        varying float vShade;
        varying float vDrop;
        uniform sampler2D uTex;
        uniform float uBack;
        uniform float uAlpha;
        void main() {
          vec4 c = texture2D(uTex, vUv);
          if (!gl_FrontFacing) {
            // Back side of curved paper: slight paper warmth & attenuated ink bleed
            vec3 backCol = mix(vec3(0.95, 0.93, 0.90), c.rgb, 0.38);
            c.rgb = backCol * (0.82 * vShade);
          } else {
            c.rgb *= (vShade - vDrop);
          }
          // Subtle spine shadow near hinge
          float spine = smoothstep(0.0, 0.045, uBack > 0.5 ? vUv.x : (1.0 - vUv.x));
          c.rgb *= (0.88 + 0.12 * spine);
          gl_FragColor = vec4(c.rgb * uAlpha, c.a * uAlpha);
        }
      `;

      const compile = (type, src) => {
        const s = gl.createShader(type);
        gl.shaderSource(s, src);
        gl.compileShader(s);
        if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) return null;
        return s;
      };
      const vsh = compile(gl.VERTEX_SHADER, vs);
      const fsh = compile(gl.FRAGMENT_SHADER, fs);
      if (!vsh || !fsh) { this.gl = null; return; }
      const pr = gl.createProgram();
      gl.attachShader(pr, vsh);
      gl.attachShader(pr, fsh);
      gl.linkProgram(pr);
      if (!gl.getProgramParameter(pr, gl.LINK_STATUS)) { this.gl = null; return; }
      this.prog = pr;

      // 36x48 mesh
      const nx = 36, ny = 48;
      const verts = [];
      const indices = [];
      for (let iy = 0; iy <= ny; iy++) {
        for (let ix = 0; ix <= nx; ix++) {
          verts.push(ix / nx, iy / ny);
        }
      }
      for (let iy = 0; iy < ny; iy++) {
        for (let ix = 0; ix < nx; ix++) {
          const i0 = iy * (nx + 1) + ix;
          const i1 = i0 + 1;
          const i2 = i0 + (nx + 1);
          const i3 = i2 + 1;
          indices.push(i0, i1, i2, i1, i3, i2);
        }
      }
      this.buf = gl.createBuffer();
      gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
      gl.bufferData(gl.ARRAY_BUFFER, new Float32Array(verts), gl.STATIC_DRAW);
      this.idx = gl.createBuffer();
      gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.idx);
      gl.bufferData(gl.ELEMENT_ARRAY_BUFFER, new Uint16Array(indices), gl.STATIC_DRAW);
      this.count = indices.length;
      this.texA = this._makeTex(gl);
      this.texB = this._makeTex(gl);
    }

    _makeTex(gl) {
      const t = gl.createTexture();
      gl.bindTexture(gl.TEXTURE_2D, t);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR);
      gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR);
      return t;
    }

    _uploadImg(img, tex) {
      const gl = this.gl;
      if (!gl || !img) return false;
      try {
        gl.bindTexture(gl.TEXTURE_2D, tex);
        gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, gl.RGBA, gl.UNSIGNED_BYTE, img);
        return true;
      } catch {
        return false;
      }
    }

    _loadImage(src) {
      return new Promise((resolve) => {
        if (!src) return resolve(null);
        const im = new Image();
        im.crossOrigin = "anonymous";
        im.onload = () => resolve(im);
        im.onerror = () => resolve(null);
        im.src = src;
      });
    }

    cancel() {
      if (this.raf) cancelAnimationFrame(this.raf);
      this.raf = 0;
      this.turning = false;
      if (this.canvas) this.canvas.style.display = "none";
    }

    _drawFrame(rect, imgA, imgB, progress, dir) {
      const cv = this.canvas;
      const dpr = Math.min(2, window.devicePixelRatio || 1);
      const pw = Math.max(1, Math.round(rect.width * dpr));
      const ph = Math.max(1, Math.round(rect.height * dpr));
      if (cv.width !== pw || cv.height !== ph) { cv.width = pw; cv.height = ph; }
      cv.style.left = rect.left + "px";
      cv.style.top = rect.top + "px";
      cv.style.width = rect.width + "px";
      cv.style.height = rect.height + "px";
      cv.style.display = "block";

      if (this.gl && this.prog) {
        const gl = this.gl;
        gl.viewport(0, 0, pw, ph);
        gl.clearColor(0, 0, 0, 0);
        gl.clear(gl.COLOR_BUFFER_BIT | gl.DEPTH_BUFFER_BIT);
        gl.enable(gl.BLEND);
        gl.blendFunc(gl.SRC_ALPHA, gl.ONE_MINUS_SRC_ALPHA);
        gl.useProgram(this.prog);
        gl.bindBuffer(gl.ARRAY_BUFFER, this.buf);
        const loc = gl.getAttribLocation(this.prog, "aPos");
        gl.enableVertexAttribArray(loc);
        gl.vertexAttribPointer(loc, 2, gl.FLOAT, false, 0, 0);
        gl.bindBuffer(gl.ELEMENT_ARRAY_BUFFER, this.idx);

        // 1. Flat under-page (target B)
        if (imgB && this._texReadyB) {
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, this.texB);
          gl.uniform1i(gl.getUniformLocation(this.prog, "uTex"), 0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uProg"), 0.0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uDir"), dir);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uR"), 0.085);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uCorner"), 0.0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uBack"), 1.0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uAlpha"), 1.0);
          gl.drawElements(gl.TRIANGLES, this.count, gl.UNSIGNED_SHORT, 0);
        }
        // 2. Curling front page (A)
        if (imgA && this._texReadyA) {
          gl.activeTexture(gl.TEXTURE0);
          gl.bindTexture(gl.TEXTURE_2D, this.texA);
          gl.uniform1i(gl.getUniformLocation(this.prog, "uTex"), 0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uProg"), clamp(progress, 0, 1));
          gl.uniform1f(gl.getUniformLocation(this.prog, "uDir"), dir);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uR"), 0.09);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uCorner"), 0.65);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uBack"), 0.0);
          gl.uniform1f(gl.getUniformLocation(this.prog, "uAlpha"), clamp(1.0 - Math.max(0, (progress - 0.86) / 0.14), 0, 1));
          gl.drawElements(gl.TRIANGLES, this.count, gl.UNSIGNED_SHORT, 0);
        }
        return;
      }

      // 2D Canvas shaded fold fallback
      const ctx = cv.getContext("2d");
      if (!ctx) return;
      ctx.clearRect(0, 0, pw, ph);
      if (imgB) ctx.drawImage(imgB, 0, 0, pw, ph);
      const foldX = dir > 0 ? pw * (1 - progress) : pw * progress;
      ctx.save();
      ctx.beginPath();
      if (dir > 0) ctx.rect(0, 0, foldX, ph);
      else ctx.rect(foldX, 0, pw - foldX, ph);
      ctx.clip();
      if (imgA) ctx.drawImage(imgA, 0, 0, pw, ph);
      ctx.restore();
      const g = ctx.createLinearGradient(foldX - 28 * dpr, 0, foldX + 28 * dpr, 0);
      g.addColorStop(0, "rgba(0,0,0,0)");
      g.addColorStop(0.5, "rgba(0,0,0,0.42)");
      g.addColorStop(1, "rgba(255,255,255,0.22)");
      ctx.fillStyle = g;
      ctx.fillRect(foldX - 28 * dpr, 0, 56 * dpr, ph);
    }

    async turn(stageEl, rect, fromSrc, toSrc, dir = 1, startProg = 0.02) {
      this.cancel();
      if (!fromSrc || !rect || rect.width < 20 || rect.height < 20) return;
      this.ensureCanvas(stageEl);
      const [imgA, imgB] = await Promise.all([this._loadImage(fromSrc), this._loadImage(toSrc)]);
      if (!imgA) return;
      if (this.gl) {
        this._texReadyA = this._uploadImg(imgA, this.texA);
        this._texReadyB = imgB ? this._uploadImg(imgB, this.texB) : false;
      }
      this.turning = true;
      const t0 = performance.now();
      const dur = 360 * (1 - clamp(startProg, 0, 0.85));
      return new Promise((resolve) => {
        const tick = (now) => {
          if (!this.turning) { resolve(); return; }
          const k = clamp((now - t0) / Math.max(80, dur), 0, 1);
          const ease = 1 - Math.pow(1 - k, 3);
          const p = startProg + (1 - startProg) * ease;
          this._drawFrame(rect, imgA, imgB, p, dir);
          if (k < 1) this.raf = requestAnimationFrame(tick);
          else { this.cancel(); resolve(); }
        };
        this.raf = requestAnimationFrame(tick);
      });
    }
  }

  window.KamiPageCurl = new KamiPageCurl();
})();
