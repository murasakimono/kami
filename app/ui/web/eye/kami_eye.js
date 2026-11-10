/* Kami goz motoru v4: boyanmis mimik kareleri (sprite) + canli gecisler. Saf Canvas/JS.
 *
 * Neden: karakterin ifadeleri elle boyanmis kalitede kalmali. Goz pikselleri hic bozulmaz;
 * hareket, kareler arasi yumusak gecis (crossfade + hafif ezilme), nefes, kirpma ve bakis
 * yonune gore kare secimiyle verilir.
 *
 * Kareler (assets/*.webp, 352x409): idle, down (indiriyor), speed (tam hiz), done (bitti),
 * error (hata), sleep (uyku/kapali), alert (yana bakis), lock (kilitlendi).
 *
 * new KamiEye(canvas, {assets, eyeY, mirrorFrame}) -> .ready, .start(), .set({...}), .lookAt(clientX, clientY)
 * Girdiler: mouseX, mouseY (-1..1), isDownloading, downloadSpeed (0..1), isError,
 *           playbackState ('idle'|'playing'|'paused'), mood ('idle'|'happy'|'sleep'|'locked'|'alert'),
 *           lid (0..1; 0.5 ustu = gozunu kapatir), levels (ekolayzir 0..1 dizisi)
 */
(function (global) {
  'use strict';
  const FRAMES = ['idle', 'down', 'speed', 'done', 'error', 'sleep', 'alert', 'lock'];
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
  const loadImage = (src) => new Promise((res, rej) => { const i = new Image(); i.onload = () => res(i); i.onerror = () => rej(new Error('yuklenemedi: ' + src)); i.src = src; });

  class KamiEye {
    constructor(canvas, opts = {}) {
      this.canvas = canvas; this.ctx = canvas.getContext('2d');
      this.base = (opts.assets || 'eye/assets/').replace(/\/?$/, '/');
      this.autoBlink = opts.autoBlink !== false; this.breathe = opts.breathe !== false;
      this.fade = opts.fade || 0.18;
      this.reduced = !!(global.matchMedia && global.matchMedia('(prefers-reduced-motion: reduce)').matches);
      this.target = { mouseX: 0, mouseY: 0, isDownloading: false, downloadSpeed: 0, isError: false, playbackState: 'idle', mood: 'idle', lid: 0, levels: null };
      this.cur = { name: 'idle', flip: false }; this.prev = null; this.mix = 1;
      this.blinkT = -1; this.nextBlink = 1.5 + Math.random() * 2; this.glance = { t: 0, side: 0 }; this.t = 0; this.idle = 0; this.squash = 0;
      this.eyeY = opts.eyeY || 0.55;   // goz yuksekligi (kare boyuna oran): ekolayzir ve glitch buraya gelir
      const names = FRAMES.concat(opts.mirrorFrame ? ['alertL'] : []);   // alertL: sola bakis icin ayri kare (tam boy karakterde ayna yerine)
      this.ready = Promise.all(names.map((n) => loadImage(this.base + n + '.webp'))).then((imgs) => {
        this.img = {}; names.forEach((n, i) => { this.img[n] = imgs[i]; });
        this.fw = imgs[0].naturalWidth; this.fh = imgs[0].naturalHeight; this.draw(); return this;
      });
    }
    set(v) { Object.assign(this.target, v); return this; }
    start() {
      if (this.running) return this; this.running = true; let last = performance.now();
      const loop = (now) => { if (!this.running) return; const dt = Math.min(0.05, (now - last) / 1000); last = now; this.step(dt); this.draw(); this.raf = requestAnimationFrame(loop); };
      this.raf = requestAnimationFrame(loop); return this;
    }
    stop() { this.running = false; cancelAnimationFrame(this.raf); return this; }
    lookAt(cx, cy, reach = 360) {
      const r = this.canvas.getBoundingClientRect(), x = r.left + r.width / 2, y = r.top + r.height * this.eyeY;
      this.target.mouseX = clamp((cx - x) / reach, -1, 1); this.target.mouseY = clamp((cy - y) / reach, -1, 1); this.idle = 0;
    }

    _wanted() {
      const T = this.target;
      if (T.lid >= 0.5 || T.mood === 'sleep') return { name: 'sleep', flip: false };
      if (T.mood === 'happy') return { name: 'done', flip: false };   // bitis sevinci hatadan once (kisa surer)
      if (T.isError) return { name: 'error', flip: false };
      if (T.mood === 'locked') return { name: 'lock', flip: false };
      if (T.mood === 'alert') return { name: 'alert', flip: T.mouseX < 0 };
      if ((T.downloadSpeed || 0) > 0.85) return { name: 'speed', flip: false };
      if (T.isDownloading) return { name: 'down', flip: false };
      // bakis: imlec belirgin yana gidince yan bakis karesi (sola bakarken ayna)
      if (Math.abs(T.mouseX) > 0.55) return { name: 'alert', flip: T.mouseX < 0 };
      if (this.glance.t > 0) return { name: 'alert', flip: this.glance.side < 0 };
      return { name: 'idle', flip: false };
    }

    step(dt) {
      this.t += dt; this.idle += dt;
      // bos kalinca ara sira yana bakar (canli dursun)
      if (this.glance.t > 0) this.glance.t -= dt;
      else if (this.idle > 4 && Math.random() < dt * 0.12) { this.glance.t = 0.9 + Math.random() * 0.8; this.glance.side = Math.random() < 0.5 ? -1 : 1; }
      let w = this._wanted();
      // kirpma: acik gozlu karelerde kisa sure kapali kareye gecis
      const openFrame = ['idle', 'down', 'alert', 'alertL', 'lock', 'speed'].includes(w.name);
      if (this.autoBlink && openFrame) {
        this.nextBlink -= dt;
        if (this.nextBlink <= 0 && this.blinkT < 0) { this.blinkT = 0; this.nextBlink = 2.5 + Math.random() * 3.5; if (Math.random() < 0.2) this.nextBlink = 0.35; }
      }
      if (this.blinkT >= 0) { this.blinkT += dt; if (this.blinkT > 0.13) this.blinkT = -1; else if (openFrame) w = { name: 'sleep', flip: false, blink: true }; }
      if (w.flip && this.img && this.img.alertL && w.name === 'alert') w = { name: 'alertL', flip: false, blink: w.blink };
      if (w.name !== this.cur.name || w.flip !== this.cur.flip) {
        this.prev = this.cur; this.cur = w; this.mix = 0;
        this.squash = w.blink || (this.prev && this.prev.blink) ? 0 : 1;
      }
      const fd = this.reduced ? 0.001 : ((this.cur.blink || (this.prev && this.prev.blink)) ? 0.05 : this.fade);
      this.mix = Math.min(1, this.mix + dt / fd);
      this.squash = Math.max(0, this.squash - dt * 6);
    }

    _drawFrame(ctx, f, alpha, k, ox, oy) {
      if (!f || alpha <= 0) return;
      const img = this.img[f.name]; ctx.save(); ctx.globalAlpha = alpha;
      ctx.translate(ox, oy); if (f.flip) { ctx.translate(this.fw * k, 0); ctx.scale(-1, 1); }
      const ih = img.naturalHeight || this.fh, iw = img.naturalWidth || this.fw, cut = Math.ceil(ih * 0.008), sy = this.fh * k / ih;   // resimlerin ust kenarinda koyu bant var
      ctx.drawImage(img, 0, cut, iw, ih - cut, 0, cut * sy, this.fw * k, (ih - cut) * sy); ctx.restore();
    }

    draw() {
      if (!this.img) return;
      const ctx = this.ctx, W = this.canvas.width, H = this.canvas.height, T = this.target;
      ctx.setTransform(1, 0, 0, 1, 0, 0); ctx.clearRect(0, 0, W, H);
      const k = Math.min(W / this.fw, H / this.fh), ox0 = (W - this.fw * k) / 2, oy0 = (H - this.fh * k) / 2;
      const still = this.reduced;
      const breath = this.breathe && !still ? Math.sin(this.t * 1.7) : 0;
      const pulse = T.playbackState === 'playing' && !still ? Math.max(0, Math.sin(this.t * 7.5)) * 0.018 : 0;
      const sq = this.squash * 0.035;
      const sx = 1 + pulse + sq * 0.6, sy = 1 + pulse - sq + breath * 0.006;
      let shake = 0; if (this.cur.name === 'error' && !still) shake = (Math.random() - 0.5) * 4 * k;
      ctx.save();
      ctx.translate(W / 2 + shake, H / 2 + breath * 3 * k); ctx.scale(sx, sy); ctx.translate(-W / 2, -H / 2);
      // ekolayzir: kare arkasinda iki yana cubuklar
      if (T.levels && T.levels.length) {
        const n = T.levels.length, cy = oy0 + this.fh * k * this.eyeY;
        for (let i = 0; i < n; i++) { const v = clamp(T.levels[i], 0, 1), h = (14 + v * 120) * k, off = (this.fw * 0.5 + 8 + i * 13) * k;
          ctx.fillStyle = `rgba(46,230,166,${0.35 + 0.6 * v})`; ctx.fillRect(W / 2 - off - 7 * k, cy - h / 2, 7 * k, h); ctx.fillRect(W / 2 + off, cy - h / 2, 7 * k, h); }
      }
      if (this.mix < 1) this._drawFrame(ctx, this.prev, 1, k, ox0, oy0);
      this._drawFrame(ctx, this.cur, this.mix, k, ox0, oy0);
      ctx.restore();
      if (this.cur.name === 'error' && !still && Math.random() < 0.3) {
        const y = oy0 + this.fh * k * (this.eyeY - 0.1 + Math.random() * 0.2), w = (40 + Math.random() * 90) * k;
        ctx.fillStyle = Math.random() < 0.5 ? 'rgba(255,60,90,.7)' : 'rgba(46,230,166,.55)'; ctx.fillRect(ox0 + Math.random() * (this.fw * k - w), y, w, 3 * k);
      }
    }
  }
  global.KamiEye = KamiEye;
})(window);
