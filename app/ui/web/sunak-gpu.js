// Kami Faz 17: Sunak PixiJS v8 GPU Sahnesi & Eklemli Kukla Maskot
// Eski DOM/CSS Sunak katmaninin (sk-ring, sk-char, skFx) yerini GPU uzerinde alir.
"use strict";

(function (global) {
  const COSTUME_PRESETS = {
    default: { hue: 0, saturate: 1, sepia: false, brightness: 1 },
    oni: { hue: 310, saturate: 1.45, sepia: false, brightness: 1.02 },
    ice: { hue: 155, saturate: 1.2, sepia: false, brightness: 1.08 },
    gold: { hue: 8, saturate: 1.65, sepia: true, brightness: 1.05 },
    cyber: { hue: 245, saturate: 1.6, sepia: false, brightness: 1.04 },
  };

  function makePaperTexture(PIXI, blurPx) {
    const c = document.createElement("canvas");
    c.width = 70;
    c.height = 150;
    const g = c.getContext("2d");
    if (blurPx) g.filter = `blur(${blurPx}px)`;
    g.translate(35, 75);
    const grd = g.createLinearGradient(0, -60, 0, 60);
    grd.addColorStop(0, "#EDE6FF");
    grd.addColorStop(1, "#B9A6F2");
    g.fillStyle = grd;
    g.beginPath();
    g.moveTo(-20, -62);
    g.lineTo(20, -62);
    g.lineTo(20, 52);
    for (let x = 20; x >= -20; x -= 5) {
      g.lineTo(x, 52 + ((x / 5) % 2 ? 7 : 1));
    }
    g.closePath();
    g.fill();
    g.fillStyle = "#6D28D9";
    g.fillRect(-20, -62, 40, 9);
    g.strokeStyle = "#3B1580";
    g.lineWidth = 2.6;
    g.lineCap = "round";
    g.beginPath();
    g.moveTo(0, -44);
    g.lineTo(0, 30);
    g.moveTo(-10, -30);
    g.quadraticCurveTo(0, -24, 10, -32);
    g.moveTo(-11, -10);
    g.lineTo(9, -4);
    g.moveTo(-8, 10);
    g.quadraticCurveTo(2, 18, 10, 8);
    g.stroke();
    g.fillStyle = "#0FA37A";
    g.beginPath();
    g.arc(0, 38, 6.5, 0, Math.PI * 2);
    g.fill();
    return PIXI.Texture.from(c);
  }

  function makeGlowTexture(PIXI, rgbaTemplate) {
    const c = document.createElement("canvas");
    c.width = 64;
    c.height = 64;
    const g = c.getContext("2d");
    const r = g.createRadialGradient(32, 32, 0, 32, 32, 32);
    r.addColorStop(0, rgbaTemplate.replace("A", "1"));
    r.addColorStop(0.28, rgbaTemplate.replace("A", "0.55"));
    r.addColorStop(1, rgbaTemplate.replace("A", "0"));
    g.fillStyle = r;
    g.fillRect(0, 0, 64, 64);
    return PIXI.Texture.from(c);
  }

  class SunakGpuEngine {
    constructor() {
      this.bgApp = null;
      this.altarApp = null;
      this.bgReady = false;
      this.altarReady = false;
      this.fxOn = (() => {
        try {
          return localStorage.getItem("kami.fx") !== "0";
        } catch {
          return true;
        }
      })();
      this.reduced = !!(
        global.matchMedia &&
        global.matchMedia("(prefers-reduced-motion: reduce)").matches
      );
      this.state = {
        speedFrac: 0,
        isDownloading: false,
        isError: false,
        mood: "idle",
        drop: false,
        mouseX: 0,
        mouseY: 0,
      };
      this.smoothSpeed = 0;
      this.orbitAngle = 0;
      this.swallowT = 0;
      this.costumeFilter = null;
      this.charTextures = {};
      this.curCharSprite = null;
      this.prevCharSprite = null;
      this.puppet = null;
      this.ringFill = null;
      this.ringBase = null;
      this.orbitGroup = null;
      this.auraSprite = null;
      this.ribbons = [];
      this.bgParts = [];
    }

    available() {
      return !!(global.PIXI && global.PIXI.Application);
    }

    async initBg() {
      if (!this.available() || this.bgApp) return false;
      const PIXI = global.PIXI;
      try {
        const app = new PIXI.Application();
        await app.init({
          backgroundAlpha: 0,
          resizeTo: global,
          antialias: true,
          autoDensity: true,
          resolution: Math.min(2, global.devicePixelRatio || 1),
          powerPreference: "high-performance",
        });
        app.canvas.id = "skFxGpu";
        app.canvas.className = "sk-fx-gpu";
        document.body.prepend(app.canvas);
        this.bgApp = app;

        const sprNear = makePaperTexture(PIXI, 0);
        const sprMid = makePaperTexture(PIXI, 1.1);
        const sprFar = makePaperTexture(PIXI, 2.2);
        const texVio = makeGlowTexture(PIXI, "rgba(167,139,250,A)");
        const texEm = makeGlowTexture(PIXI, "rgba(46,230,166,A)");
        const texWisp = makeGlowTexture(PIXI, "rgba(196,181,253,A)");

        const layerTal = new PIXI.Container();
        const layerGlow = new PIXI.Container();
        app.stage.addChild(layerTal, layerGlow);

        const rnd = (a, b) => a + Math.random() * (b - a);
        const LAYERS = [
          [sprFar, 0.35, 0.055, 5],
          [sprMid, 0.55, 0.08, 4],
          [sprNear, 0.8, 0.11, 3],
        ];
        const spawnTal = (L, y) => {
          const [tex, sc, a] = L;
          const sp = new PIXI.Sprite(tex);
          sp.anchor.set(0.5);
          sp.alpha = a;
          layerTal.addChild(sp);
          return {
            kind: "t",
            layer: L,
            sprite: sp,
            sc: sc * rnd(0.85, 1.15),
            x: rnd(0, app.screen.width),
            y: y ?? rnd(0, app.screen.height),
            vy: -rnd(6, 14) * sc,
            sway: rnd(10, 26) * sc,
            ph: rnd(0, Math.PI * 2),
            rot: rnd(-0.4, 0.4),
            spin: rnd(0.4, 1.1),
          };
        };
        for (const L of LAYERS) {
          for (let i = 0; i < L[3]; i++) this.bgParts.push(spawnTal(L));
        }

        let elapsed = 0;
        app.ticker.add((ticker) => {
          const on = this.fxOn && !document.hidden && !this.reduced;
          app.canvas.style.display = on ? "block" : "none";
          if (!on) return;
          const dt = Math.min(0.05, ticker.deltaMS / 1000);
          elapsed += dt;
          const W = app.screen.width;
          const H = app.screen.height;
          const rate = 1.2 + (this.state.speedFrac || 0) * 6;

          if (Math.random() < rate * dt && this.bgParts.length < 52) {
            const isEm = Math.random() < 0.32;
            const sp = new PIXI.Sprite(isEm ? texEm : texVio);
            sp.anchor.set(0.5);
            sp.blendMode = "add";
            const sz = rnd(12, 26);
            sp.width = sz;
            sp.height = sz;
            layerGlow.addChild(sp);
            this.bgParts.push({
              kind: "e",
              sprite: sp,
              x: rnd(0, W),
              y: H + 8,
              vx: rnd(-6, 6),
              vy: -rnd(22, 48),
              life: rnd(5, 10),
              t: 0,
              fl: rnd(0, Math.PI * 2),
            });
          }

          if (
            Math.random() < 0.08 * dt &&
            this.bgParts.filter((p) => p.kind === "w").length < 3
          ) {
            const sp = new PIXI.Sprite(texWisp);
            sp.anchor.set(0.5);
            sp.blendMode = "add";
            const sz = rnd(52, 88);
            sp.width = sz;
            sp.height = sz;
            layerGlow.addChild(sp);
            this.bgParts.push({
              kind: "w",
              sprite: sp,
              x: rnd(W * 0.1, W * 0.9),
              y: rnd(H * 0.25, H * 0.75),
              vx: rnd(-18, 18),
              vy: rnd(-8, 8),
              life: rnd(7, 12),
              t: 0,
              ph: rnd(0, Math.PI * 2),
            });
          }

          this.bgParts = this.bgParts.filter((p) => {
            if (p.kind === "t") {
              p.y += p.vy * dt;
              if (p.y < -95) {
                p.y = H + 95;
                p.x = rnd(0, W);
              }
              p.sprite.x = p.x + Math.sin(elapsed * 0.5 + p.ph) * p.sway;
              p.sprite.y = p.y;
              p.sprite.rotation = p.rot + Math.sin(elapsed * 0.35 + p.ph) * 0.35;
              const fl = Math.cos(elapsed * p.spin * 0.45 + p.ph);
              p.sprite.scale.set(
                p.sc * (Math.sign(fl) || 1) * (0.3 + 0.7 * Math.abs(fl)),
                p.sc
              );
              return true;
            }
            p.t += dt;
            if (p.t >= p.life) {
              p.sprite.destroy();
              return false;
            }
            p.x += p.vx * dt;
            p.y += p.vy * dt;
            const k = p.t / p.life;
            const fade = Math.sin(Math.min(1, k) * Math.PI);
            if (p.kind === "e") {
              const fl = 0.75 + 0.25 * Math.sin(elapsed * 9 + p.fl);
              p.sprite.x = p.x + Math.sin(p.t * 1.7 + p.fl) * 8;
              p.sprite.y = p.y;
              p.sprite.alpha = 0.32 * fade * fl;
            } else {
              p.vx += Math.sin(elapsed + p.ph) * 4 * dt;
              p.vy += Math.cos(elapsed * 0.7 + p.ph) * 4 * dt;
              p.sprite.x = p.x;
              p.sprite.y = p.y;
              p.sprite.alpha = 0.18 * fade;
            }
            return true;
          });
        });

        this.bgReady = true;
        return true;
      } catch (err) {
        console.warn("Sunak GPU arka plan baslatilamadi, 2D yedek aktif:", err);
        return false;
      }
    }

    async initAltar(altarEl, eyeInstance) {
      if (!this.available() || !altarEl || this.altarApp) return false;
      const PIXI = global.PIXI;
      try {
        if (eyeInstance?.ready) {
          await eyeInstance.ready;
          eyeInstance.stop?.();
        }
        const app = new PIXI.Application();
        await app.init({
          width: 300,
          height: 330,
          backgroundAlpha: 0,
          antialias: true,
          autoDensity: true,
          resolution: Math.min(2, global.devicePixelRatio || 1),
          powerPreference: "high-performance",
        });
        app.canvas.id = "skAltarGpu";
        app.canvas.className = "sk-altar-gpu";
        altarEl.prepend(app.canvas);
        this.altarApp = app;

        // 1. Hiz halkasi & yorunge katmani
        const ringLayer = new PIXI.Container();
        ringLayer.position.set(150, 150);
        app.stage.addChild(ringLayer);

        this.ringBase = new PIXI.Graphics();
        this.ringBase.circle(0, 0, 132).stroke({ width: 10, color: 0x1c1228 });
        ringLayer.addChild(this.ringBase);

        this.ringFill = new PIXI.Graphics();
        ringLayer.addChild(this.ringFill);

        this.orbitGroup = new PIXI.Container();
        const orb1 = new PIXI.Graphics().circle(0, -146, 3.2).fill(0xc4b5fd);
        const orb2 = new PIXI.Graphics().circle(0, 146, 2.4).fill(0x2ee6a6);
        this.orbitGroup.addChild(orb1, orb2);
        ringLayer.addChild(this.orbitGroup);

        // 2. Arka ruh aurasi
        const auraTex = makeGlowTexture(PIXI, "rgba(139,92,246,A)");
        this.auraSprite = new PIXI.Sprite(auraTex);
        this.auraSprite.anchor.set(0.5);
        this.auraSprite.position.set(150, 165);
        this.auraSprite.width = 250;
        this.auraSprite.height = 250;
        this.auraSprite.alpha = 0.25;
        this.auraSprite.blendMode = "add";
        app.stage.addChild(this.auraSprite);

        // 3. Eklemli Kukla Maskot (PuppetRig)
        this.puppet = new PIXI.Container();
        this.puppet.position.set(150, 164);
        app.stage.addChild(this.puppet);

        // Eklemli yan kagit kurdeleler (ikincil hareket)
        for (const side of [-1, 1]) {
          const joint = new PIXI.Container();
          joint.position.set(side * 58, -10);
          const rib = new PIXI.Graphics()
            .moveTo(0, 0)
            .lineTo(side * 12, 42)
            .lineTo(side * 4, 78)
            .lineTo(side * -6, 46)
            .closePath()
            .fill({ color: 0x1e142d, alpha: 0.85 })
            .stroke({ width: 1.5, color: 0x6d28d9, alpha: 0.65 });
          joint.addChild(rib);
          this.puppet.addChild(joint);
          this.ribbons.push({ side, joint });
        }

        // Karakter sprite katmanlari (crossfade icin prev + cur)
        const charWrap = new PIXI.Container();
        this.puppet.addChild(charWrap);
        this.costumeFilter = new PIXI.ColorMatrixFilter();
        charWrap.filters = [this.costumeFilter];

        if (eyeInstance?.img) {
          for (const [k, img] of Object.entries(eyeInstance.img)) {
            this.charTextures[k] = PIXI.Texture.from(img);
          }
        }

        this.prevCharSprite = new PIXI.Sprite(
          this.charTextures.idle || PIXI.Texture.EMPTY
        );
        this.curCharSprite = new PIXI.Sprite(
          this.charTextures.idle || PIXI.Texture.EMPTY
        );
        const fitSprite = (sp, tex, flip) => {
          const w = tex && tex !== PIXI.Texture.EMPTY && tex.width > 1 ? tex.width : 403;
          const h = tex && tex !== PIXI.Texture.EMPTY && tex.height > 1 ? tex.height : 614;
          sp.scale.set((flip ? -1 : 1) * (222 / w), 338 / h);
        };
        for (const sp of [this.prevCharSprite, this.curCharSprite]) {
          sp.anchor.set(0.5, 0.5);
          fitSprite(sp, sp.texture, false);
        }
        this.prevCharSprite.alpha = 0;
        charWrap.addChild(this.prevCharSprite, this.curCharSprite);

        this.setCostume(
          global.kamiSfx?.getCostume?.() || "default"
        );

        let lastFrame = "";
        let lastFlip = false;
        let lastRingKey = "";
        let elapsed = 0;

        app.ticker.add((ticker) => {
          const dt = Math.min(0.05, ticker.deltaMS / 1000);
          elapsed += dt;

          // Hiz halkasi interpolasyonu
          const targetSpd = this.state.speedFrac || 0;
          this.smoothSpeed += (targetSpd - this.smoothSpeed) * Math.min(1, dt * 8);

          // Yorunge donusu
          this.orbitAngle =
            (this.orbitAngle + dt * (8 + this.smoothSpeed * 260)) % 360;
          this.orbitGroup.rotation = (this.orbitAngle * Math.PI) / 180;

          // Hiz halkasi cizimi (yalnizca deger degistiginde GPU geometrisi yeniden kurulur)
          const ringKey = `${this.smoothSpeed.toFixed(3)}|${!!this.state.drop}|${!!this.state.isError}`;
          if (ringKey !== lastRingKey) {
            lastRingKey = ringKey;
            this.ringBase.clear();
            this.ringBase
              .circle(0, 0, 132)
              .stroke({ width: 10, color: this.state.drop ? 0x0fa37a : 0x1c1228 });

            this.ringFill.clear();
            if (this.smoothSpeed > 0.002) {
              const startA = -Math.PI / 2;
              const endA = startA + Math.PI * 2 * Math.min(1, this.smoothSpeed);
              const col =
                this.smoothSpeed > 0.92
                  ? 0x2ee6a6
                  : this.state.isError
                  ? 0xff4d6a
                  : 0x8b5cf6;
              this.ringFill
                .arc(0, 0, 132, startA, endA)
                .stroke({ width: 10, color: col, cap: "butt" });
            }
          }

          // Aura rengi ve nabzi
          if (this.state.isError) this.auraSprite.tint = 0xff4d6a;
          else if (this.state.drop || this.smoothSpeed > 0.92)
            this.auraSprite.tint = 0x2ee6a6;
          else this.auraSprite.tint = 0x8b5cf6;
          this.auraSprite.alpha =
            (this.state.drop ? 0.55 : 0.22 + this.smoothSpeed * 0.28) *
            (0.88 + 0.12 * Math.sin(elapsed * 2.4));

          // KamiEye durum makinesini adimla (canvas cizimi olmadan sadece state/mix)
          if (eyeInstance) {
            eyeInstance.step(dt);
            const fName = eyeInstance.cur?.name || "idle";
            const fFlip = !!eyeInstance.cur?.flip;
            if (fName !== lastFrame || fFlip !== lastFlip) {
              if (this.curCharSprite.texture !== PIXI.Texture.EMPTY) {
                this.prevCharSprite.texture = this.curCharSprite.texture;
                fitSprite(this.prevCharSprite, this.prevCharSprite.texture, lastFlip);
              }
              if (this.charTextures[fName]) {
                this.curCharSprite.texture = this.charTextures[fName];
              }
              fitSprite(this.curCharSprite, this.curCharSprite.texture, fFlip);
              lastFrame = fName;
              lastFlip = fFlip;
            }
            const mix = eyeInstance.mix ?? 1;
            this.curCharSprite.alpha = mix;
            this.prevCharSprite.alpha = Math.max(0, 1 - mix);
          }

          // Kukla eklemli hareket: nefes + imlec egimi + yutma tepkisi
          const mx = eyeInstance?.target?.mouseX || 0;
          const my = eyeInstance?.target?.mouseY || 0;
          const breatheY = this.reduced ? 0 : Math.sin(elapsed * 2.1) * 3.5;
          const targetRot = this.reduced ? 0 : mx * 0.065;
          this.puppet.rotation +=
            (targetRot - this.puppet.rotation) * Math.min(1, dt * 10);
          this.puppet.x =
            150 + (this.reduced ? 0 : mx * 5);
          this.puppet.y =
            164 + breatheY + (this.reduced ? 0 : my * 3.5);

          // Yutma / squash-stretch animasyonu
          let sx = 1;
          let sy = 1;
          if (this.swallowT > 0) {
            this.swallowT = Math.max(0, this.swallowT - dt * 1.8);
            const k = Math.sin(this.swallowT * Math.PI);
            sx = 1 + k * 0.08;
            sy = 1 - k * 0.06;
          } else if (eyeInstance?.squash > 0) {
            sx = 1 + eyeInstance.squash * 0.035;
            sy = 1 - eyeInstance.squash * 0.03;
          }
          this.puppet.scale.set(sx, sy);

          // Eklemli kurdele sallanimi
          const windAmp = 0.06 + this.smoothSpeed * 0.18;
          for (const r of this.ribbons) {
            r.joint.rotation =
              r.side * 0.08 +
              Math.sin(elapsed * (2.6 + this.smoothSpeed * 4) + r.side) *
                windAmp -
              this.puppet.rotation * 1.4;
          }
        });

        document.body.classList.add("sunak-gpu");
        this.altarReady = true;
        return true;
      } catch (err) {
        console.warn("Sunak GPU sunak sahnesi baslatilamadi, 2D yedek aktif:", err);
        return false;
      }
    }

    setState(patch) {
      Object.assign(this.state, patch || {});
    }

    setFx(on) {
      this.fxOn = !!on;
    }

    triggerSwallow() {
      this.swallowT = 1;
    }

    setCostume(name) {
      if (!this.costumeFilter) return;
      const p = COSTUME_PRESETS[name] || COSTUME_PRESETS.default;
      this.costumeFilter.reset();
      if (p.sepia) this.costumeFilter.sepia(true);
      if (p.hue) this.costumeFilter.hue(p.hue, true);
      if (p.saturate !== 1) this.costumeFilter.saturate(p.saturate - 1, true);
      if (p.brightness !== 1) this.costumeFilter.brightness(p.brightness, true);
    }
  }

  global.KamiSunakGPU = new SunakGpuEngine();
})(window);
