/* Kami goz motoru (saf Canvas/JS, bagimlilik yok).
 *
 * Katman duzeni: govde (temiz goz akiyla) cizilir; goz bolgesi ayri bir tuvalde
 * kurulur (iris, golge, isik, kapaklar, kirpik cizgisi) ve EN SON goz yuvasi maskesiyle
 * kirpilir (destination-in). Maskenin disina tek piksel cikamaz: iris ne kadar
 * kayarsa kaysin kapaklarin arkasinda kalir.
 *
 * Kullanim:
 *   const eye = new KamiEye(canvas, { assets: 'eye/assets/' });
 *   await eye.ready;
 *   eye.set({ mouseX: 0.3, mouseY: -0.2, isDownloading: true, progress: 0.4,
 *             downloadSpeed: 0.8, isError: false, playbackState: 'playing', mood: 'idle' });
 *
 * Girdiler:
 *   mouseX, mouseY   -1..1  bakis yonu
 *   isDownloading    bool   asagi bakar + iris cevresinde ilerleme halkasi (progress 0..1)
 *   downloadSpeed    0..1   iris buyur, gozbebegi acilir
 *   isError          bool   kirmizi iris + titreme
 *   playbackState    'idle' | 'playing' | 'paused'  (oynatici; playing = hafif nabiz)
 *   mood             'idle' | 'happy' | 'sleep' | 'locked' | 'alert'
 *   lid              0..1   elle kapak (uzerine gelince 1)
 *   levels           sayi dizisi 0..1 (ekolayzir; goz cevresinde cubuklar)
 */
(function (global) {
  'use strict';
  const META = {"size":1024,"eye":{"x":330,"y":280,"w":310,"h":190},"iris":{"cx":157,"cy":106,"r":47},"contour":{"x0":57,"step":3,"top":[135.6,132.9,129.7,127.6,123.7,119.6,114.8,112.4,110.3,108.4,106.7,105.0,103.3,101.6,100.0,98.6,97.2,93.8,88.7,82.6,77.8,74.1,71.0,68.1,65.6,63.4,61.8,60.3,59.1,58.2,57.6,57.2,57.0,57.0,57.0,57.0,57.3,57.8,58.6,59.4,60.8,62.3,64.0,65.2,66.0,66.4,66.8,66.9,63.9,60.6,57.0,58.2,59.9,61.9,61.8,61.3,60.7,60.2,60.0],"bot":[138.0,138.0,138.0,138.0,138.1,138.6,139.3,140.3,141.3,142.3,143.2,144.1,144.9,145.8,146.4,147.2,147.8,148.4,148.8,149.3,149.7,150.0,150.0,150.0,150.0,150.0,150.0,150.3,151.0,151.8,152.4,152.8,153.0,153.0,153.0,153.0,152.7,152.2,151.4,150.6,149.2,147.7,145.9,143.7,141.0,138.0,134.8,130.8,126.0,121.2,117.0,113.2,109.2,104.8,99.7,93.4,85.7,75.3,66.9]}};
  const lerp = (a, b, t) => a + (b - a) * t;
  const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));

  function loadImage(src) {
    return new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('yuklenemedi: ' + src)); i.src = src; });
  }

  class KamiEye {
    constructor(canvas, opts = {}) {
      this.canvas = canvas;
      this.ctx = canvas.getContext('2d');
      this.base = (opts.assets || 'eye/assets/').replace(/\/?$/, '/');
      this.autoBlink = opts.autoBlink !== false;
      this.breathe = opts.breathe !== false;
      this.reduced = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
      this.target = { mouseX: 0, mouseY: 0, isDownloading: false, progress: 0, downloadSpeed: 0,
        isError: false, playbackState: 'idle', mood: 'idle', lid: 0, levels: null };
      // yumusatilmis durum
      this.s = { dx: 0, dy: 0, upper: 0, lower: 0, red: 0, scale: 1, pupil: 0, ring: 0, cross: 0 };
      this.blink = 0; this.nextBlink = 1.5 + Math.random() * 2.5; this.blinkT = -1;
      this.t = 0; this.last = 0; this.running = false;
      this.eyeCanvas = document.createElement('canvas');
      this.eyeCanvas.width = META.eye.w; this.eyeCanvas.height = META.eye.h;
      this.ectx = this.eyeCanvas.getContext('2d');
      this.ready = Promise.all(['body.webp', 'mask.png', 'felt.webp', 'iris.png', 'iris_red.png']
        .map((n) => loadImage(this.base + n))).then(([body, mask, felt, iris, irisRed]) => {
        this.img = { body, mask, felt, iris, irisRed };
        this.feltPattern = this.ectx.createPattern(felt, 'repeat');
        this.draw(0);
        return this;
      });
    }

    set(values) { Object.assign(this.target, values); return this; }

    start() {
      if (this.running) return this;
      this.running = true; this.last = performance.now();
      const loop = (now) => {
        if (!this.running) return;
        const dt = Math.min(0.05, (now - this.last) / 1000); this.last = now;
        this.step(dt); this.draw();
        this.raf = requestAnimationFrame(loop);
      };
      this.raf = requestAnimationFrame(loop);
      return this;
    }

    stop() { this.running = false; cancelAnimationFrame(this.raf); return this; }

    /** Goz yuvasinin sayfa koordinatindaki merkezi (fare takibi icin). */
    center() {
      const r = this.canvas.getBoundingClientRect(), k = r.width / META.size;
      return { x: r.left + (META.eye.x + META.iris.cx) * k, y: r.top + (META.eye.y + META.iris.cy) * k };
    }

    /** Fare konumunu -1..1 araligina cevirip hedefe yazar. */
    lookAt(clientX, clientY, reach = 420) {
      const c = this.center();
      this.target.mouseX = clamp((clientX - c.x) / reach, -1, 1);
      this.target.mouseY = clamp((clientY - c.y) / (reach * 0.7), -1, 1);
    }

    step(dt) {
      const T = this.target, s = this.s;
      this.t += dt;
      // hedefler
      let upper = 0.10, lower = 0, lookX = T.mouseX, lookY = T.mouseY, pupil = 0, scale = 1, ring = 0, cross = 0;
      const speed = clamp(T.downloadSpeed || 0, 0, 1);
      if (T.isDownloading) { lookX *= 0.25; lookY = 0.75; upper = 0.16; ring = 1; }
      scale = 1 + 0.10 * speed; pupil = speed > 0.85 ? (speed - 0.85) / 0.15 : 0;
      if (pupil > 0) { upper = 0; }
      if (T.playbackState === 'playing') scale += 0.02 * Math.sin(this.t * 4);
      switch (T.mood) {
        case 'happy': upper = 0.56; lower = 0.44; lookY = 0; ring = 0; break;
        case 'sleep': upper = 1; lower = 0; ring = 0; break;
        case 'locked': upper = 0.30; lower = 0.22; cross = 1; break;
        case 'alert': upper = 0; pupil = 0; scale = 0.9; break;
      }
      if (T.isError) { upper = 0.22; lower = 0.08; ring = 0; cross = 0; }
      upper = Math.max(upper, clamp(T.lid || 0, 0, 1));
      // goz kirpma
      if (this.autoBlink && T.mood !== 'sleep') {
        this.nextBlink -= dt;
        if (this.nextBlink <= 0 && this.blinkT < 0) { this.blinkT = 0; this.nextBlink = 2.6 + Math.random() * 3.4; if (Math.random() < 0.22) this.nextBlink = 0.32; }
        if (this.blinkT >= 0) {
          this.blinkT += dt; const d = 0.16, p = this.blinkT / d;
          this.blink = p < 0.45 ? p / 0.45 : Math.max(0, 1 - (p - 0.45) / 0.55);
          if (p >= 1) { this.blinkT = -1; this.blink = 0; }
        }
      } else { this.blink = 0; }
      const k = this.reduced ? 1 : 1 - Math.pow(0.0005, dt);       // bakis yumusatma
      const kl = this.reduced ? 1 : 1 - Math.pow(0.00002, dt);     // kapaklar daha hizli
      s.dx = lerp(s.dx, lookX, k); s.dy = lerp(s.dy, lookY, k);
      s.upper = lerp(s.upper, upper, kl); s.lower = lerp(s.lower, lower, kl);
      s.red = lerp(s.red, T.isError ? 1 : 0, kl); s.scale = lerp(s.scale, scale, k);
      s.pupil = lerp(s.pupil, pupil, k); s.ring = lerp(s.ring, ring, kl); s.cross = lerp(s.cross, cross, kl);
    }

    _lidPath(c, amountTop, amountBottom, which) {
      // Maskenin ust/alt konturlari arasinda dogrusal ara deger: kapak kenari gozun kendi bicimini izler.
      const { x0, step, top, bot } = META.contour, n = top.length;
      c.beginPath();
      if (which === 'upper') {
        c.moveTo(x0 - 30, -10); c.lineTo(x0 - 30, top[0] + (bot[0] - top[0]) * amountTop);
        for (let i = 0; i < n; i++) c.lineTo(x0 + i * step, top[i] + (bot[i] - top[i]) * amountTop);
        c.lineTo(x0 + n * step + 30, top[n - 1] + (bot[n - 1] - top[n - 1]) * amountTop); c.lineTo(x0 + n * step + 30, -10);
      } else {
        const H = META.eye.h + 10;
        c.moveTo(x0 - 30, H); c.lineTo(x0 - 30, bot[0] - (bot[0] - top[0]) * amountBottom);
        for (let i = 0; i < n; i++) c.lineTo(x0 + i * step, bot[i] - (bot[i] - top[i]) * amountBottom);
        c.lineTo(x0 + n * step + 30, bot[n - 1] - (bot[n - 1] - top[n - 1]) * amountBottom); c.lineTo(x0 + n * step + 30, H);
      }
      c.closePath();
    }

    _edge(c, amount, fromTop) {
      const { x0, step, top, bot } = META.contour, n = top.length;
      c.beginPath();
      for (let i = 0; i < n; i++) {
        const y = fromTop ? top[i] + (bot[i] - top[i]) * amount : bot[i] - (bot[i] - top[i]) * amount;
        if (i === 0) c.moveTo(x0, y); else c.lineTo(x0 + i * step, y);
      }
    }

    _drawEye() {
      const c = this.ectx, E = META.eye, I = META.iris, s = this.s, img = this.img, T = this.target;
      c.setTransform(1, 0, 0, 1, 0, 0); c.globalCompositeOperation = 'source-over'; c.globalAlpha = 1;
      c.clearRect(0, 0, E.w, E.h);
      // 1) goz aki: govde resminin goz bolgesi
      c.drawImage(img.body, E.x, E.y, E.w, E.h, 0, 0, E.w, E.h);
      // 2) iris (titreme: hata)
      const jx = s.red > 0.5 && !this.reduced ? (Math.random() - 0.5) * 3 : 0;
      const cx = I.cx + s.dx * 34 + jx, cy = I.cy + s.dy * 16, r = I.r * s.scale;
      c.drawImage(img.iris, cx - r, cy - r, r * 2, r * 2);
      if (s.red > 0.01) { c.globalAlpha = s.red; c.drawImage(img.irisRed, cx - r, cy - r, r * 2, r * 2); c.globalAlpha = 1; }
      // gozbebegi acilmasi (tam hiz)
      if (s.pupil > 0.01) { c.fillStyle = '#04030A'; c.beginPath(); c.ellipse(cx, cy, lerp(4, r * 0.52, s.pupil), lerp(r * 0.7, r * 0.56, s.pupil), 0, 0, Math.PI * 2); c.fill(); }
      // ilerleme halkasi
      if (s.ring > 0.02) {
        c.globalAlpha = s.ring * (0.75 + 0.25 * Math.sin(this.t * 5));
        c.strokeStyle = '#7CFFD6'; c.lineWidth = 3.5; c.lineCap = 'round';
        c.beginPath(); c.arc(cx, cy, r * 0.82, -Math.PI / 2, -Math.PI / 2 + Math.PI * 2 * clamp(T.progress || 0, 0.02, 1)); c.stroke();
        c.globalAlpha = 1;
      }
      // nisangah
      if (s.cross > 0.02) {
        c.globalAlpha = s.cross * 0.9; c.strokeStyle = '#7CFFD6'; c.lineWidth = 2;
        c.beginPath(); c.moveTo(cx - r * 1.5, cy); c.lineTo(cx + r * 1.5, cy); c.moveTo(cx, cy - r * 1.1); c.lineTo(cx, cy + r * 1.1); c.stroke(); c.globalAlpha = 1;
      }
      // 3) sabit isik yansimasi (iris hareket etse de isik yerinde: canlilik)
      c.fillStyle = 'rgba(255,255,255,.95)';
      c.beginPath(); c.ellipse(I.cx + 20 + s.dx * 20, I.cy - 22 + s.dy * 8, 9, 6.5, -0.35, 0, Math.PI * 2); c.fill();
      c.fillStyle = 'rgba(255,255,255,.55)';
      c.beginPath(); c.ellipse(I.cx - 16 + s.dx * 24, I.cy + 20 + s.dy * 10, 3.5, 3, 0, 0, Math.PI * 2); c.fill();
      // 4) ust kapagin gozun ustune dusurdugu golge
      const upper = clamp(Math.max(s.upper, this.blink), 0, 1), lower = clamp(s.lower, 0, 1 - upper);
      c.save(); this._lidPath(c, Math.min(1, upper + 0.2), 0, 'upper'); c.clip();
      c.fillStyle = 'rgba(20,10,40,.38)'; c.fillRect(0, 0, E.w, E.h); c.restore();
      // 5) kapaklar (kece dokusu) + kirpik cizgisi
      c.fillStyle = this.feltPattern;
      if (upper > 0.005) { this._lidPath(c, upper, 0, 'upper'); c.fill(); }
      if (lower > 0.005) { this._lidPath(c, 0, lower, 'lower'); c.fill(); }
      c.lineJoin = 'round'; c.lineCap = 'round'; c.strokeStyle = '#05030A';
      if (upper > 0.005) { c.lineWidth = lerp(5, 9, upper); this._edge(c, upper, true); c.stroke(); }
      if (lower > 0.005) { c.lineWidth = 4; this._edge(c, lower, false); c.stroke(); }
      // kapali/kisik gozde kirpik cizgisinin altinda ince isik: cizgi koyu kecede kaybolmasin
      if (upper > 0.5) {
        c.save(); c.translate(0, 5); c.globalAlpha = (upper - 0.5) * 0.9; c.strokeStyle = 'rgba(196,181,253,.55)'; c.lineWidth = 1.6;
        this._edge(c, upper, true); c.stroke(); c.restore();
      }
      // uyku: kapak altindan sizan isik
      if (T.mood === 'sleep' && upper > 0.9) {
        c.globalAlpha = 0.55 + 0.35 * Math.sin(this.t * 1.6); c.strokeStyle = '#2EE6A6'; c.lineWidth = 2.5;
        c.shadowColor = '#2EE6A6'; c.shadowBlur = 8; this._edge(c, 0.03, false); c.stroke(); c.shadowBlur = 0; c.globalAlpha = 1;
      }
      // 6) MASKE: goz yuvasinin disinda kalan her sey silinir
      c.globalCompositeOperation = 'destination-in';
      c.drawImage(img.mask, 0, 0);
      c.globalCompositeOperation = 'source-over';
    }

    draw() {
      if (!this.img) return;
      const ctx = this.ctx, W = this.canvas.width, H = this.canvas.height, k = W / META.size, s = this.s, T = this.target;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, W, H);
      const bob = this.breathe && !this.reduced ? Math.sin(this.t * 1.7) * 6 : 0;   // nefes
      ctx.setTransform(k, 0, 0, k, 0, bob * k);
      ctx.imageSmoothingQuality = 'high';
      // ekolayzir: govdenin arkasinda, goz hizasinda iki yana acilan cubuklar
      if (T.levels && T.levels.length) {
        const n = T.levels.length, cy = META.eye.y + META.iris.cy;
        for (let i = 0; i < n; i++) {
          const v = clamp(T.levels[i], 0, 1), h = 20 + v * 230, off = 300 + i * 26;
          ctx.fillStyle = `rgba(46,230,166,${0.35 + 0.6 * v})`;
          ctx.fillRect(512 - off - 14, cy - h / 2, 14, h); ctx.fillRect(512 + off, cy - h / 2, 14, h);
        }
      }
      ctx.drawImage(this.img.body, 0, 0, META.size, META.size);
      this._drawEye();
      ctx.drawImage(this.eyeCanvas, META.eye.x, META.eye.y);
      // hata: renk kaymasi seritleri
      if (s.red > 0.5 && !this.reduced && Math.random() < 0.35) {
        const y = META.eye.y + Math.random() * META.eye.h, w = 60 + Math.random() * 120;
        ctx.fillStyle = Math.random() < 0.5 ? 'rgba(255,60,90,.75)' : 'rgba(46,230,166,.6)';
        ctx.fillRect(META.eye.x + Math.random() * (META.eye.w - w), y, w, 5);
      }
    }
  }

  KamiEye.META = META;
  global.KamiEye = KamiEye;
})(window);
