/* Kami goz motoru v3 (saf Canvas/JS).
 *
 * Katmanlar (alttan uste):
 *  1) base   : karakterin ORIJINAL cizimi (kirpikler, kece, alevler aynen).
 *  2) goz    : goz aki + iris, yalnizca goz yuvasinin ICINDE ve iki kapak kenari ARASINDA
 *              (yuva = cizimden olculen ust/alt goz cizgisi). Iris bu alanin disina asla cikmaz.
 *  3) kapak  : gozun yerine temiz kece cizilmis "closed" resminden, yuva ust cizgisinden kapak
 *              kenarina kadar olan bolge. Kenarda kalin, uclara dogru incelen kirpik cizgisi.
 *              Tam kapali gozde bu cizgi alt goz cizgisine oturur: tek kavisli kapali goz.
 *  4) alt kapak: mutlu/kisik gozde alttan ayni sekilde.
 *
 * new KamiEye(canvas, {assets}) -> .ready, .start(), .set({...}), .lookAt(clientX, clientY)
 * Girdiler: mouseX, mouseY (-1..1), isDownloading, progress (0..1), downloadSpeed (0..1), isError,
 *           playbackState ('idle'|'playing'|'paused'), mood ('idle'|'happy'|'sleep'|'locked'|'alert'),
 *           lid (0..1), levels (ekolayzir 0..1 dizisi)
 */
(function (global) {
  'use strict';
  const META = {"size":1024,"eye":{"x":360,"y":300,"w":230,"h":150},"iris":{"cx":489.5,"cy":387.5,"r":46.5},"contour":{"x0":385,"top":[418.6,418.2,417.3,415.8,413.8,411.2,408.1,406.7,405.4,404.2,402.9,401.8,400.6,399.5,398.5,397.4,396.5,395.5,394.6,393.7,392.8,392.0,391.2,390.4,389.7,389.0,388.3,387.6,387.0,386.4,385.8,385.2,384.7,384.1,383.6,383.1,382.6,382.1,381.7,381.2,380.8,380.4,380.0,379.6,379.2,378.9,378.5,378.1,377.8,377.4,377.1,376.8,376.4,376.1,375.8,375.5,375.2,374.9,374.6,374.3,373.9,373.6,373.3,373.0,372.7,372.4,372.1,371.8,371.5,371.1,370.8,370.5,370.1,369.8,369.5,369.1,368.8,368.4,368.0,367.7,367.3,366.9,366.5,366.1,365.7,365.3,364.9,364.5,364.0,363.6,363.1,362.7,362.2,361.8,361.3,360.8,360.3,359.8,359.3,358.8,358.3,357.7,357.2,356.7,356.1,355.6,355.0,354.4,353.9,353.3,352.7,352.1,351.5,350.9,350.3,349.7,349.1,348.5,347.9,347.3,346.7,346.0,345.4,344.8,344.2,343.6,342.9,342.3,341.7,341.1,340.5,339.9,339.2,338.6,338.0,337.5,336.9,336.3,335.7,335.2,334.6,334.1,333.5,333.0,332.5,332.0,331.5,331.1,330.6,330.2,329.8,329.4,329.0,328.6,328.3,327.9,327.6,327.4,327.1,326.9,326.7,326.5,326.4,326.3,326.2,326.1,326.1,326.1,326.1,326.2,326.3,326.5,326.7,332.5,337.3,341.1,343.8,345.4,345.7],"bot":[418.6,418.8,419.0,419.2,419.4,419.6,419.8,420.0,420.2,420.4,420.6,420.8,421.0,421.2,421.4,421.6,421.8,422.0,422.2,422.4,422.7,422.9,423.1,423.3,423.5,423.7,423.9,424.1,424.3,424.6,424.8,425.0,425.2,425.4,425.6,425.8,426.1,426.3,426.5,426.7,426.9,427.1,427.4,427.6,427.8,428.0,428.2,428.4,428.6,428.9,429.1,429.3,429.5,429.7,429.9,430.1,430.3,430.5,430.7,430.9,431.1,431.3,431.5,431.7,431.9,432.1,432.3,432.5,432.7,432.8,433.0,433.2,433.4,433.5,433.7,433.8,434.0,434.1,434.3,434.4,434.5,434.7,434.8,434.9,435.0,435.1,435.2,435.3,435.3,435.4,435.5,435.5,435.6,435.6,435.6,435.6,435.6,435.6,435.6,435.6,435.5,435.5,435.4,435.3,435.2,435.1,435.0,434.8,434.7,434.5,434.3,434.1,433.9,433.7,433.4,433.1,432.8,432.5,432.2,431.8,431.4,431.0,430.6,430.1,429.6,429.1,428.6,428.1,427.5,426.9,426.2,425.6,424.9,424.1,423.4,422.6,421.8,420.9,420.0,419.1,418.1,417.1,416.1,415.0,413.9,412.8,411.6,410.3,409.0,407.7,406.4,404.9,403.5,402.0,400.4,398.8,397.1,395.4,393.7,391.9,390.0,388.1,386.1,384.1,382.0,379.8,377.6,375.3,372.9,370.5,368.1,365.5,362.9,360.2,357.5,354.6,351.7,348.8,345.7]}};
  const C = META.contour, X0 = C.x0, N = C.top.length;
  const lerp = (a, b, t) => a + (b - a) * t, clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const loadImage = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('yuklenemedi: ' + src)); i.src = src; });

  class KamiEye {
    constructor(canvas, opts = {}) {
      this.canvas = canvas; this.ctx = canvas.getContext('2d');
      this.base = (opts.assets || 'eye/assets/').replace(/\/?$/, '/');
      this.autoBlink = opts.autoBlink !== false; this.breathe = opts.breathe !== false;
      this.reduced = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
      this.target = { mouseX: 0, mouseY: 0, isDownloading: false, progress: 0, downloadSpeed: 0, isError: false,
        playbackState: 'idle', mood: 'idle', lid: 0, levels: null };
      this.s = { dx: 0, dy: 0, upper: 0, lower: 0, red: 0, scale: 1, pupil: 0, ring: 0, cross: 0 };
      this.blink = 0; this.nextBlink = 1.2 + Math.random() * 2; this.blinkT = -1;
      this.sacc = { x: 0, y: 0, next: 0.8 }; this.idle = 0; this.t = 0; this.running = false;
      const E = META.eye; this.off = document.createElement('canvas'); this.off.width = E.w; this.off.height = E.h;
      this.octx = this.off.getContext('2d');
      this.ready = Promise.all(['base.webp', 'closed.webp', 'sclera.png', 'iris.png', 'iris_red.png'].map((n) => loadImage(this.base + n)))
        .then(([base, closed, sclera, iris, irisRed]) => { this.img = { base, closed, sclera, iris, irisRed }; this.draw(); return this; });
    }

    set(v) { Object.assign(this.target, v); return this; }
    start() {
      if (this.running) return this; this.running = true; let last = performance.now();
      const loop = (now) => { if (!this.running) return; const dt = Math.min(0.05, (now - last) / 1000); last = now;
        this.step(dt); this.draw(); this.raf = requestAnimationFrame(loop); };
      this.raf = requestAnimationFrame(loop); return this;
    }
    stop() { this.running = false; cancelAnimationFrame(this.raf); return this; }
    center() { const r = this.canvas.getBoundingClientRect(), k = r.width / META.size; return { x: r.left + META.iris.cx * k, y: r.top + META.iris.cy * k }; }
    lookAt(cx, cy, reach = 420) { const c = this.center();
      this.target.mouseX = clamp((cx - c.x) / reach, -1, 1); this.target.mouseY = clamp((cy - c.y) / (reach * 0.7), -1, 1); this.idle = 0; }

    step(dt) {
      const T = this.target, s = this.s; this.t += dt; this.idle += dt;
      // kucuk bakis kaymalari: goz hic donup kalmaz
      this.sacc.next -= dt;
      if (this.sacc.next <= 0) { const far = this.idle > 2.5; this.sacc.next = (far ? 1.4 : 0.6) + Math.random() * (far ? 2.6 : 1.4);
        this.sacc.x = (Math.random() - 0.5) * (far ? 1.0 : 0.14); this.sacc.y = (Math.random() - 0.5) * (far ? 0.7 : 0.1); }
      let upper = 0.04, lower = 0, lx = T.mouseX + this.sacc.x, ly = T.mouseY + this.sacc.y, pupil = 0, scale = 1, ring = 0, cross = 0;
      const sp = clamp(T.downloadSpeed || 0, 0, 1);
      if (T.isDownloading) { lx *= 0.3; ly = 0.75; upper = 0.22; ring = 1; }
      scale = 1 + 0.07 * sp; if (sp > 0.85) { pupil = (sp - 0.85) / 0.15; upper = 0; }
      if (T.playbackState === 'playing') scale += 0.015 * Math.sin(this.t * 4);
      switch (T.mood) {
        case 'happy': upper = 0.42; lower = 0.58; ring = 0; break;
        case 'sleep': upper = 1; lower = 0; ring = 0; break;
        case 'locked': upper = 0.36; lower = 0.2; cross = 1; break;
        case 'alert': upper = 0; scale = 0.88; break;
      }
      if (T.isError) { upper = 0.28; lower = 0.08; ring = 0; cross = 0; }
      upper = Math.max(upper, clamp(T.lid || 0, 0, 1));
      if (this.autoBlink && T.mood !== 'sleep' && T.mood !== 'happy') {
        this.nextBlink -= dt;
        if (this.nextBlink <= 0 && this.blinkT < 0) { this.blinkT = 0; this.nextBlink = 2.4 + Math.random() * 3.6; if (Math.random() < 0.2) this.nextBlink = 0.32; }
        if (this.blinkT >= 0) { this.blinkT += dt; const p = this.blinkT / 0.18; this.blink = p < 0.4 ? p / 0.4 : Math.max(0, 1 - (p - 0.4) / 0.6); if (p >= 1) { this.blinkT = -1; this.blink = 0; } }
      } else this.blink = 0;
      const k = this.reduced ? 1 : 1 - Math.pow(0.0003, dt), kl = this.reduced ? 1 : 1 - Math.pow(0.00002, dt);
      s.dx = lerp(s.dx, clamp(lx, -1, 1), k); s.dy = lerp(s.dy, clamp(ly, -1, 1), k);
      s.upper = lerp(s.upper, upper, kl); s.lower = lerp(s.lower, lower, kl); s.red = lerp(s.red, T.isError ? 1 : 0, kl);
      s.scale = lerp(s.scale, scale, k); s.pupil = lerp(s.pupil, pupil, k); s.ring = lerp(s.ring, ring, kl); s.cross = lerp(s.cross, cross, kl);
    }

    // kapak kenari: yuva ust/alt cizgisi arasinda. Uclarda (koselerde) yuva kapandigi icin dogal olarak birlesir.
    _upperY(i, u) { return C.top[i] + (C.bot[i] - C.top[i]) * u; }
    _lowerY(i, l) { return C.bot[i] - (C.bot[i] - C.top[i]) * l; }
    _path(c, ox, oy, fa, fb, closeTop) {
      c.beginPath();
      for (let i = 0; i < N; i++) { const y = fa(i); i ? c.lineTo(X0 + i - ox, y - oy) : c.moveTo(X0 + i - ox, y - oy); }
      for (let i = N - 1; i >= 0; i--) c.lineTo(X0 + i - ox, fb(i) - oy);
      c.closePath();
    }
    _line(c, f) { c.beginPath(); for (let i = 0; i < N; i++) { const y = f(i); i ? c.lineTo(X0 + i, y) : c.moveTo(X0 + i, y); } }

    _eyeball(u, l) {
      const c = this.octx, E = META.eye, I = META.iris, s = this.s, img = this.img, T = this.target;
      c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1; c.filter = 'none';
      c.clearRect(0, 0, E.w, E.h);
      c.save();
      this._path(c, E.x, E.y, (i) => this._upperY(i, u), (i) => this._lowerY(i, l)); c.clip();      // tek kirpma: kapaklar arasi
      c.drawImage(img.sclera, 0, 0);
      const jx = s.red > 0.5 && !this.reduced ? (Math.random() - 0.5) * 3 : 0;
      const cx = I.cx - E.x + s.dx * 30 + jx, cy = I.cy - E.y + s.dy * 13, r = I.r * s.scale;
      // iris'in goz akina dusen golgesi
      c.fillStyle = 'rgba(40,20,70,.25)'; c.beginPath(); c.arc(cx + 2, cy + 3, r + 3, 0, Math.PI * 2); c.fill();
      c.drawImage(img.iris, cx - r, cy - r, r * 2, r * 2);
      if (s.red > 0.01) { c.globalAlpha = s.red; c.drawImage(img.irisRed, cx - r, cy - r, r * 2, r * 2); c.globalAlpha = 1; }
      // limbus: koyu ince halka (cizimdeki gibi)
      c.strokeStyle = 'rgba(2,10,8,.85)'; c.lineWidth = 3; c.beginPath(); c.arc(cx, cy, r - 1.5, 0, Math.PI * 2); c.stroke();
      if (s.pupil > 0.01) { c.fillStyle = '#04030A'; c.beginPath(); c.ellipse(cx, cy, lerp(4, r * 0.5, s.pupil), lerp(r * 0.7, r * 0.55, s.pupil), 0, 0, Math.PI * 2); c.fill(); }
      if (s.ring > 0.02) { c.globalAlpha = s.ring * (0.75 + 0.25 * Math.sin(this.t * 5)); c.strokeStyle = '#7CFFD6'; c.lineWidth = 3.5; c.lineCap = 'round';
        c.beginPath(); c.arc(cx, cy, r * 0.8, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * clamp(T.progress || 0, 0.02, 1)); c.stroke(); c.globalAlpha = 1; }
      if (s.cross > 0.02) { c.globalAlpha = s.cross * 0.85; c.strokeStyle = '#7CFFD6'; c.lineWidth = 2;
        c.beginPath(); c.moveTo(cx - r * 1.5, cy); c.lineTo(cx + r * 1.5, cy); c.moveTo(cx, cy - r * 1.1); c.lineTo(cx, cy + r * 1.1); c.stroke(); c.globalAlpha = 1; }
      // isiklar
      c.fillStyle = 'rgba(255,255,255,.96)'; c.beginPath(); c.ellipse(cx + 16 - s.dx * 5, cy - 20, 9, 6.2, -0.3, 0, Math.PI * 2); c.fill();
      c.fillStyle = 'rgba(255,255,255,.5)'; c.beginPath(); c.ellipse(cx - 14, cy + 18, 3.2, 2.7, 0, 0, Math.PI * 2); c.fill();
      // ust kapak golgesi
      c.filter = 'blur(4px)'; c.fillStyle = 'rgba(30,14,55,.55)';
      this._path(c, E.x, E.y, (i) => this._upperY(i, u) - 8, (i) => this._upperY(i, u) + 9); c.fill(); c.filter = 'none';
      c.restore();
    }

    _lids(ctx, u, l) {
      const img = this.img;
      if (u > 0.003) {
        ctx.save(); this._path(ctx, 0, 0, (i) => C.top[i] - 2, (i) => this._upperY(i, u)); ctx.clip();
        ctx.drawImage(img.closed, 0, 0); ctx.restore();
      }
      if (l > 0.003) {
        ctx.save(); this._path(ctx, 0, 0, (i) => this._lowerY(i, l), (i) => C.bot[i] + 2); ctx.clip();
        ctx.drawImage(img.closed, 0, 0); ctx.restore();
      }
      // kirpik cizgisi: kapak kenarinda, uclara dogru incelen kalin cizgi (dis kosede kalin)
      const stroke = (f, wMax, a) => {
        if (a <= 0.01) return;
        ctx.save(); ctx.globalAlpha = a; ctx.fillStyle = '#06040B';
        ctx.beginPath();
        for (let i = 0; i < N; i++) { const t = i / (N - 1), w = wMax * Math.pow(Math.sin(Math.PI * clamp(t * 1.04, 0, 1)), 0.55) * (0.65 + 0.55 * t); ctx[i ? 'lineTo' : 'moveTo'](X0 + i, f(i) - w * 0.35); }
        for (let i = N - 1; i >= 0; i--) { const t = i / (N - 1), w = wMax * Math.pow(Math.sin(Math.PI * clamp(t * 1.04, 0, 1)), 0.55) * (0.65 + 0.55 * t); ctx.lineTo(X0 + i, f(i) + w * 0.65); }
        ctx.closePath(); ctx.fill(); ctx.restore();
      };
      stroke((i) => this._upperY(i, u), lerp(6, 12, u), clamp((u - 0.03) * 8, 0, 1));
      stroke((i) => this._lowerY(i, l), lerp(4, 9, l), clamp((l - 0.03) * 8, 0, 1));
      if (this.target.mood === 'sleep' && u > 0.9) {
        ctx.save(); ctx.globalAlpha = 0.45 + 0.35 * Math.sin(this.t * 1.6); ctx.strokeStyle = '#2EE6A6'; ctx.lineWidth = 2.5; ctx.shadowColor = '#2EE6A6'; ctx.shadowBlur = 10;
        ctx.beginPath(); for (let i = 10; i < N - 10; i++) ctx[i > 10 ? 'lineTo' : 'moveTo'](X0 + i, C.bot[i] + 6); ctx.stroke(); ctx.restore();
      }
    }

    draw() {
      if (!this.img) return;
      const ctx = this.ctx, W = this.canvas.width, k = W / META.size, s = this.s, T = this.target;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, W, this.canvas.height);
      const bob = this.breathe && !this.reduced ? Math.sin(this.t * 1.7) * 6 : 0;
      ctx.setTransform(k, 0, 0, k, 0, bob * k); ctx.imageSmoothingQuality = 'high';
      if (T.levels && T.levels.length) { const n = T.levels.length, cy = META.iris.cy;
        for (let i = 0; i < n; i++) { const v = clamp(T.levels[i], 0, 1), h = 20 + v * 230, off = 300 + i * 26;
          ctx.fillStyle = `rgba(46,230,166,${0.35 + 0.6 * v})`; ctx.fillRect(512 - off - 14, cy - h / 2, 14, h); ctx.fillRect(512 + off, cy - h / 2, 14, h); } }
      ctx.drawImage(this.img.base, 0, 0, META.size, META.size);
      const u = clamp(Math.max(s.upper, this.blink), 0, 1), l = clamp(s.lower, 0, 1 - u);
      if (u + l < 0.995) { this._eyeball(u, l); ctx.drawImage(this.off, META.eye.x, META.eye.y); }
      this._lids(ctx, u, l);
      if (s.red > 0.5 && !this.reduced && Math.random() < 0.3) { const E = META.eye, y = E.y + 30 + Math.random() * (E.h - 60), w = 60 + Math.random() * 110;
        ctx.fillStyle = Math.random() < 0.5 ? 'rgba(255,60,90,.75)' : 'rgba(46,230,166,.6)'; ctx.fillRect(E.x + Math.random() * (E.w - w), y, w, 4); }
    }
  }
  KamiEye.META = META; global.KamiEye = KamiEye;
})(window);
