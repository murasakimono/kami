"use strict";
/* Kami Beat Asama 1a: klip tabanli zaman cizelgesi + Web Audio onizleme motoru (window.BeatTimeline).
   - Kanal basliklari beat.js'te (DOM, #tlHeads); burasi cetvel, seritler, klip kartlari, secim, surukleme,
     zoom, calma cizgisi ve oynatmayi yonetir.
   - Klip karti DOM, icindeki dalga formu yalniz GORUNEN parca kadar canvas (1 saatlik beat'te de hafif).
   - Dalga formu karolari: api.beat_waveform_tile(path, rate, index) -> path|rate|index anahtariyla onbellek.
   - Tum klip matematigi window.BeatClips (beat-clips.js) ile; duzenleme opts.edit(label, fn) uzerinden
     yapilir (geri al yigini + otomatik kayit beat.js'te). */
(function (root) {
  const BC = root.BeatClips;
  const TILE = 2048;                 // karo basina tepe
  const MAX_RATE = 256;              // Python PEAK_RATE
  const EDGE_PX = 7;                 // kirpma tutamaci genisligi
  const FADE_PX = 12;                // fade ucgeni
  const LONG_SRC_SEC = 600;          // bundan uzun kaynaklar Web Audio'ya cozulmez, <audio> akisiyla calinir
  const MIN_PPS = 1, MAX_PPS = 800;

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const baseName = (p) => String(p || "").split(/[\\/]/).pop();
  const dbToGain = (db) => Math.pow(10, (Number(db) || 0) / 20);

  function trackColor(tr, idx) {
    if (tr.role === "beat") return "#14F195";
    const vocals = ["#9D6BFF", "#F59E0B", "#38BDF8", "#EC4899", "#A3E635"];
    return vocals[idx % vocals.length];
  }

  function create(opts) {
    const api = opts.api;
    const el = opts.el;            // { scroll, content, ruler, heads, playhead }
    const S = {
      pps: 40,                     // piksel / saniye
      playhead: 0,
      sel: new Set(),
      snapDiv: 4,                  // 0 = kapali
      drag: null,
      tiles: new Map(),            // key -> peaks dizisi
      pending: new Set(),
      dur: new Map(),              // path -> kaynak suresi
      frame: 0,
      laneOrder: [],
    };

    const proj = () => opts.getProj();
    const tracks = () => proj()?.tracks || [];
    const bpm = () => Number(proj()?.bpm) || 120;
    const t2x = (t) => t * S.pps;
    const x2t = (x) => x / S.pps;

    function projectEnd() {
      let end = 0;
      for (const tr of tracks()) end = Math.max(end, BC.trackEnd(tr.clips || []));
      return end;
    }
    function contentWidth() {
      const end = projectEnd();
      const viewW = el.scroll.clientWidth || 800;
      return Math.max(viewW, Math.ceil(t2x(Math.max(60, end + Math.max(20, end * 0.25)))));
    }
    function findClip(id) {
      for (const tr of tracks()) {
        const c = (tr.clips || []).find((x) => x.id === id);
        if (c) return { tr, clip: c };
      }
      return null;
    }
    function snapOn(ev) { return S.snapDiv > 0 && !(ev && ev.altKey); }
    function snapT(t, ev) { return snapOn(ev) ? BC.snapTime(t, bpm(), S.snapDiv) : BC.r6(Math.max(0, t)); }

    // ---------------- Cizim ----------------
    function render() {
      const trs = tracks();
      el.content.style.width = contentWidth() + "px";
      const barPx = t2x(240 / bpm());
      el.content.style.setProperty("--bar-px", barPx + "px");
      el.content.style.setProperty("--beat-px", (barPx / 4) + "px");
      S.laneOrder = trs.map((t) => t.id);
      const lanes = trs.map((tr, ti) => {
        const col = trackColor(tr, trs.filter((x, i) => i < ti && x.role !== "beat").length);
        const clips = (tr.clips || []).map((c) => clipHtml(tr, c, col)).join("");
        const empty = !(tr.clips || []).length
          ? `<div class="kb-lane-empty">Boş kanal — "📂 Ses" ile ekle veya buraya çift tıkla</div>` : "";
        return `<div class="kb-tl-lane ${tr.id === opts.selTid() ? "sel" : ""} ${tr.mute ? "muted" : ""}" data-lane="${esc(tr.id)}" style="--tc:${col}">${empty}${clips}</div>`;
      }).join("");
      el.content.innerHTML = lanes + `<div class="kb-playhead" id="tlPlayhead"></div>`;
      el.playhead = el.content.querySelector("#tlPlayhead");
      drawPlayhead();
      drawRuler();
      scheduleWaves();
    }

    function clipHtml(tr, c, col) {
      const [s, e] = BC.clipBounds(c);
      const take = (tr.takes || []).find((t) => t.id === c.take_id);
      const label = take?.label || baseName(c.path) || "Klip";
      const cls = ["kb-clip", S.sel.has(c.id) ? "sel" : "", c.muted ? "muted" : ""].join(" ");
      const gain = Number(c.gain_db) || 0;
      return `<div class="${cls}" data-clip="${esc(c.id)}" style="left:${t2x(s)}px;width:${Math.max(2, t2x(e - s))}px;--tc:${col}">
        <canvas class="kb-clip-wf"></canvas>
        <span class="kb-clip-lbl">${esc(label)}${gain ? ` · ${gain > 0 ? "+" : ""}${gain.toFixed(1)} dB` : ""}${c.muted ? " · sessiz" : ""}</span>
        <i class="kb-fade-h l" data-h="fi" title="Fade in (sürükle)"></i><i class="kb-fade-h r" data-h="fo" title="Fade out (sürükle)"></i>
        <i class="kb-edge l" data-h="ts"></i><i class="kb-edge r" data-h="te"></i>
      </div>`;
    }

    function drawRuler() {
      const cv = el.ruler;
      if (!cv) return;
      const dpr = window.devicePixelRatio || 1;
      const w = cv.clientWidth || 600, h = cv.clientHeight || 28;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      }
      const g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const sl = el.scroll.scrollLeft;
      const barSec = 240 / bpm();
      const barPx = t2x(barSec);
      let every = 1;
      while (barPx * every < 44) every *= 2;
      const firstBar = Math.max(0, Math.floor(x2t(sl) / barSec));
      const lastBar = Math.ceil(x2t(sl + w) / barSec);
      g.font = "500 12px 'Chakra Petch', system-ui, sans-serif";
      g.textBaseline = "top";
      for (let b = firstBar; b <= lastBar; b++) {
        const x = Math.round(t2x(b * barSec) - sl) + 0.5;
        if (b % every === 0) {
          g.strokeStyle = "rgba(157,107,255,.55)";
          g.beginPath(); g.moveTo(x, 8); g.lineTo(x, h); g.stroke();
          g.fillStyle = "#8E84A8";
          g.fillText(String(b + 1), x + 4, 4);
        } else if (barPx >= 6) {
          g.strokeStyle = "rgba(157,107,255,.25)";
          g.beginPath(); g.moveTo(x, h - 9); g.lineTo(x, h); g.stroke();
        }
        if (barPx >= 48) {                         // vuruslar
          g.strokeStyle = "rgba(157,107,255,.22)";
          for (let k = 1; k < 4; k++) {
            const bx = Math.round(x + (barPx * k) / 4) + 0.5;
            g.beginPath(); g.moveTo(bx, h - 7); g.lineTo(bx, h); g.stroke();
          }
        }
        if (barPx >= 220) {                        // onaltiliklar
          g.strokeStyle = "rgba(157,107,255,.12)";
          for (let k = 1; k < 16; k++) {
            if (k % 4 === 0) continue;
            const bx = Math.round(x + (barPx * k) / 16) + 0.5;
            g.beginPath(); g.moveTo(bx, h - 4); g.lineTo(bx, h); g.stroke();
          }
        }
      }
      // calma cizgisi isareti
      const px = t2x(S.playhead) - sl;
      if (px >= -6 && px <= w + 6) {
        g.fillStyle = "#14F195";
        g.beginPath(); g.moveTo(px - 5, h - 8); g.lineTo(px + 5, h - 8); g.lineTo(px, h); g.closePath(); g.fill();
      }
    }

    function drawPlayhead() {
      if (el.playhead) el.playhead.style.transform = `translateX(${t2x(S.playhead)}px)`;
      opts.onTime?.(S.playhead);
    }

    // ---- dalga formu karolari ----
    function rateFor() {
      let r = 1;
      while (r < S.pps && r < MAX_RATE) r *= 2;
      return r;
    }
    function tileKey(path, rate, idx) { return `${path}|${rate}|${idx}`; }
    function needTile(path, rate, idx) {
      const k = tileKey(path, rate, idx);
      if (S.tiles.has(k) || S.pending.has(k) || !api()?.beat_waveform_tile) return;
      S.pending.add(k);
      api().beat_waveform_tile(path, rate, idx, TILE).then((r) => {
        S.pending.delete(k);
        S.tiles.set(k, r?.ok ? r.peaks || [] : []);
        if (r?.duration) learnDuration(path, r.duration);
        if (S.tiles.size > 600) {                // kaba LRU: en eskiyi at
          const first = S.tiles.keys().next().value;
          S.tiles.delete(first);
        }
        scheduleWaves();
      }).catch(() => { S.pending.delete(k); S.tiles.set(k, []); });
    }
    function learnDuration(path, d) {
      if (!d || S.dur.get(path) === d) return;
      S.dur.set(path, d);
      for (const tr of tracks()) for (const c of tr.clips || []) {
        if (c.path === path && !(Number(c.src_len) > 0)) c.src_len = BC.r6(d);   // geri al'a girmeyen meta veri
      }
    }
    function peakAt(path, rate, i0, i1) {
      let m = -1;
      for (let i = i0; i <= i1; i++) {
        const idx = Math.floor(i / TILE);
        const arr = S.tiles.get(tileKey(path, rate, idx));
        if (!arr) { needTile(path, rate, idx); continue; }
        const v = arr[i - idx * TILE];
        if (v !== undefined && v > m) m = v;
      }
      return m;
    }

    function scheduleWaves() {
      if (S.frame) return;
      S.frame = requestAnimationFrame(() => { S.frame = 0; drawWaves(); drawRuler(); });
    }

    function drawWaves() {
      const sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
      const rate = rateFor();
      const dpr = window.devicePixelRatio || 1;
      for (const card of el.content.querySelectorAll(".kb-clip")) {
        const hit = findClip(card.dataset.clip);
        const cv = card.querySelector("canvas");
        if (!hit || !cv) continue;
        const c = hit.clip;
        const [s, e] = BC.clipBounds(c);
        const cx0 = t2x(s), cx1 = t2x(e);
        const v0 = Math.max(cx0, sl - 40), v1 = Math.min(cx1, sl + vw + 40);
        if (v1 <= v0) { cv.style.display = "none"; continue; }
        const lbl = card.querySelector(".kb-clip-lbl");   // ad etiketi gorunen kenara yapissin
        if (lbl) lbl.style.left = (Math.max(0, Math.min(sl - cx0, cx1 - cx0 - 60)) + 8) + "px";
        const w = Math.max(1, Math.ceil(v1 - v0)), h = Math.max(20, card.clientHeight - 4);
        cv.style.display = "block";
        cv.style.left = (v0 - cx0) + "px";
        cv.style.width = w + "px";
        cv.style.height = h + "px";
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
          cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
        }
        const g = cv.getContext("2d");
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, h);
        const col = getComputedStyle(card).getPropertyValue("--tc").trim() || "#9D6BFF";
        const top = 16, mid = top + (h - top) / 2, amp = (h - top - 6) / 2;
        const gain = Math.min(2, dbToGain(c.gain_db));
        const fi = Number(c.fade_in) || 0, fo = Number(c.fade_out) || 0, len = e - s;
        g.fillStyle = col;
        g.globalAlpha = c.muted ? 0.35 : 0.9;
        for (let px = 0; px < w; px++) {
          const tl0 = x2t(v0 + px), tl1 = x2t(v0 + px + 1);
          const src0 = c.src_in + (tl0 - s), src1 = c.src_in + (tl1 - s);
          const p = peakAt(c.path, rate, Math.floor(src0 * rate), Math.max(Math.floor(src0 * rate), Math.ceil(src1 * rate) - 1));
          if (p < 0) continue;
          const rel = tl0 - s;
          let env = gain;
          if (fi > 0 && rel < fi) env *= rel / fi;
          if (fo > 0 && rel > len - fo) env *= Math.max(0, (len - rel) / fo);
          const bh = Math.max(1, Math.min(1, p * env) * amp);
          g.fillRect(px, mid - bh, 1, bh * 2);
        }
        g.globalAlpha = 1;
        // fade egrileri
        g.strokeStyle = "rgba(237,233,246,.75)";
        g.lineWidth = 1;
        const ox = cx0 - v0;
        if (fi > 0) {
          g.beginPath(); g.moveTo(ox, h - 2); g.lineTo(ox + t2x(fi), top); g.stroke();
          g.fillStyle = "rgba(6,4,10,.35)";
          g.beginPath(); g.moveTo(ox, top); g.lineTo(ox + t2x(fi), top); g.lineTo(ox, h - 2); g.closePath(); g.fill();
        }
        if (fo > 0) {
          const xe = cx1 - v0;
          g.beginPath(); g.moveTo(xe - t2x(fo), top); g.lineTo(xe, h - 2); g.stroke();
          g.fillStyle = "rgba(6,4,10,.35)";
          g.beginPath(); g.moveTo(xe - t2x(fo), top); g.lineTo(xe, top); g.lineTo(xe, h - 2); g.closePath(); g.fill();
        }
      }
    }

    // ---------------- Zoom / kaydirma ----------------
    function setZoom(pps, anchorX) {
      pps = clamp(pps, MIN_PPS, MAX_PPS);
      const ax = anchorX ?? (t2x(S.playhead) - el.scroll.scrollLeft);
      const safeAx = clamp(ax, 0, el.scroll.clientWidth);
      const tAnchor = x2t(el.scroll.scrollLeft + safeAx);
      S.pps = pps;
      render();
      el.scroll.scrollLeft = Math.max(0, t2x(tAnchor) - safeAx);
      opts.onZoom?.(S.pps);
    }
    const zoomBy = (f, ax) => setZoom(S.pps * f, ax);
    function fit() {
      const end = projectEnd() || 60;
      const vw = (el.scroll.clientWidth || 800) - 40;
      S.pps = clamp(vw / (end * 1.05), MIN_PPS, MAX_PPS);
      render();
      el.scroll.scrollLeft = 0;
      opts.onZoom?.(S.pps);
    }
    function ensureVisible(t) {
      const x = t2x(t), sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
      if (x < sl || x > sl + vw - 30) el.scroll.scrollLeft = Math.max(0, x - vw * 0.15);
    }

    el.scroll.addEventListener("scroll", () => {
      if (el.heads) el.heads.scrollTop = el.scroll.scrollTop;
      scheduleWaves();
    }, { passive: true });
    el.scroll.addEventListener("wheel", (ev) => {
      if (!ev.ctrlKey) {
        // dikey tasma yoksa (birkac kanal) tekerlek yatay kaydirsin
        if (!ev.shiftKey && el.scroll.scrollHeight <= el.scroll.clientHeight + 1 && Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
          ev.preventDefault();
          el.scroll.scrollLeft += ev.deltaY;
        }
        return;
      }
      ev.preventDefault();
      const rc = el.scroll.getBoundingClientRect();
      zoomBy(ev.deltaY < 0 ? 1.2 : 1 / 1.2, ev.clientX - rc.left);
    }, { passive: false });
    window.addEventListener("resize", () => { render(); });

    // ---------------- Calma cizgisi / cetvel ----------------
    function setPlayhead(t, keepPlaying = true) {
      S.playhead = Math.max(0, Number(t) || 0);
      drawPlayhead();
      drawRuler();
      if (keepPlaying && Eng.playing) play(S.playhead);
    }
    function rulerSeek(ev) {
      const rc = el.ruler.getBoundingClientRect();
      setPlayhead(snapT(x2t(ev.clientX - rc.left + el.scroll.scrollLeft), ev), false);
    }
    el.ruler.addEventListener("pointerdown", (ev) => {
      const wasPlaying = Eng.playing;
      if (wasPlaying) stopEngine();
      rulerSeek(ev);
      el.ruler.setPointerCapture(ev.pointerId);
      const mv = (e) => rulerSeek(e);
      const up = () => {
        el.ruler.removeEventListener("pointermove", mv);
        el.ruler.removeEventListener("pointerup", up);
        if (wasPlaying) play(S.playhead);
      };
      el.ruler.addEventListener("pointermove", mv);
      el.ruler.addEventListener("pointerup", up);
    });

    // ---------------- Secim + surukleme ----------------
    function refreshSelClasses() {
      for (const card of el.content.querySelectorAll(".kb-clip")) card.classList.toggle("sel", S.sel.has(card.dataset.clip));
      opts.onSelection?.(S.sel);
    }
    function select(id, additive) {
      if (additive) { if (S.sel.has(id)) S.sel.delete(id); else S.sel.add(id); }
      else if (!S.sel.has(id)) { S.sel.clear(); S.sel.add(id); }
      refreshSelClasses();
    }
    function clearSel() { S.sel.clear(); refreshSelClasses(); }

    function laneAtY(clientY) {
      for (const ln of el.content.querySelectorAll(".kb-tl-lane")) {
        const r = ln.getBoundingClientRect();
        if (clientY >= r.top && clientY < r.bottom) return ln.dataset.lane;
      }
      return null;
    }

    el.content.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      hideMenu();
      const card = ev.target.closest(".kb-clip");
      const lane = ev.target.closest(".kb-tl-lane");
      if (lane) opts.onSelectTrack?.(lane.dataset.lane);
      const rc = el.content.getBoundingClientRect();
      const tAt = x2t(ev.clientX - rc.left);
      if (!card) {
        if (!ev.shiftKey) clearSel();
        setPlayhead(snapT(tAt, ev));
        return;
      }
      const id = card.dataset.clip;
      const hit = findClip(id);
      if (!hit) return;
      const mode = ev.target.dataset.h || "move";
      if (mode === "move") select(id, ev.shiftKey);
      else if (!S.sel.has(id)) select(id, false);
      if (ev.shiftKey && mode === "move" && !S.sel.has(id)) return;   // shift ile secimden cikarildi
      ev.preventDefault();
      card.setPointerCapture(ev.pointerId);
      S.drag = {
        mode, id, trId: hit.tr.id, x0: ev.clientX, t0: tAt, moved: false,
        orig: JSON.parse(JSON.stringify(hit.clip)),
        group: [...S.sel].map((cid) => findClip(cid)).filter(Boolean).map((h) => ({ trId: h.tr.id, clip: JSON.parse(JSON.stringify(h.clip)) })),
        before: opts.snap(),
      };
      document.body.classList.add("kb-dragging", `kb-drag-${mode}`);
    });

    el.content.addEventListener("pointermove", (ev) => {
      const card = ev.target.closest?.(".kb-clip");
      if (!S.drag) {
        if (card && !ev.target.dataset.h) card.style.cursor = "grab";
        return;
      }
      const D = S.drag;
      const dxT = x2t(ev.clientX - D.x0);
      if (!D.moved && Math.abs(ev.clientX - D.x0) < 3) return;
      D.moved = true;
      const hit = findClip(D.id);
      if (!hit) return;
      const o = D.orig;
      if (D.mode === "move") {
        let ns = o.start + dxT;
        if (snapOn(ev)) ns = BC.snapTime(ns, bpm(), S.snapDiv);
        let delta = ns - o.start;
        const minStart = Math.min(...D.group.map((g) => g.clip.start));
        if (minStart + delta < 0) delta = -minStart;
        for (const g of D.group) {
          const tr = tracks().find((t) => t.id === g.trId);
          if (!tr) continue;
          tr.clips = BC.move(tr.clips, g.clip.id, g.clip.start + delta);
        }
      } else if (D.mode === "ts") {
        const nc = BC.trimStart(o, snapT(o.start + dxT, ev));
        Object.assign(hit.clip, nc);
      } else if (D.mode === "te") {
        const [, oe] = BC.clipBounds(o);
        const nc = BC.trimEnd(o, snapT(oe + dxT, ev));
        Object.assign(hit.clip, nc);
      } else if (D.mode === "fi") {
        Object.assign(hit.clip, BC.setFade(hit.clip, (Number(o.fade_in) || 0) + dxT, hit.clip.fade_out));
      } else if (D.mode === "fo") {
        Object.assign(hit.clip, BC.setFade(hit.clip, hit.clip.fade_in, (Number(o.fade_out) || 0) - dxT));
      }
      updateCards();
    });

    function endDrag(ev) {
      if (!S.drag) return;
      const D = S.drag;
      S.drag = null;
      document.body.classList.remove("kb-dragging", `kb-drag-${D.mode}`);
      if (!D.moved) return;
      if (opts.snap() !== D.before) {
        const label = { move: "Taşı", ts: "Baştan kırp", te: "Sondan kırp", fi: "Fade in", fo: "Fade out" }[D.mode];
        opts.commitFrom(label, D.before);
        render();
      }
    }
    el.content.addEventListener("pointerup", endDrag);
    el.content.addEventListener("pointercancel", endDrag);

    function updateCards() {
      // surukleme sirasinda yalniz etkilenen kartlarin konum/genisligi
      for (const card of el.content.querySelectorAll(".kb-clip")) {
        const hit = findClip(card.dataset.clip);
        if (!hit) continue;
        const [s, e] = BC.clipBounds(hit.clip);
        card.style.left = t2x(s) + "px";
        card.style.width = Math.max(2, t2x(e - s)) + "px";
      }
      const need = contentWidth();
      if (parseFloat(el.content.style.width) < need) el.content.style.width = need + "px";
      scheduleWaves();
    }

    el.content.addEventListener("dblclick", (ev) => {
      if (ev.target.closest(".kb-clip")) return;
      const lane = ev.target.closest(".kb-tl-lane");
      if (!lane) return;
      const rc = el.content.getBoundingClientRect();
      opts.onPickForTrack?.(lane.dataset.lane, snapT(x2t(ev.clientX - rc.left), ev));
    });

    // ---------------- Sag tik menusu ----------------
    let menu = null;
    function hideMenu() { if (menu) { menu.remove(); menu = null; } }
    el.content.addEventListener("contextmenu", (ev) => {
      const card = ev.target.closest(".kb-clip");
      if (!card) return;
      ev.preventDefault();
      if (!S.sel.has(card.dataset.clip)) select(card.dataset.clip, false);
      const rc = el.content.getBoundingClientRect();
      const tAt = x2t(ev.clientX - rc.left);
      const anyMuted = [...S.sel].some((id) => findClip(id)?.clip.muted);
      hideMenu();
      menu = document.createElement("div");
      menu.className = "kb-ctx";
      menu.innerHTML = `
        <button data-act="split">Böl<kbd>S</kbd></button>
        <button data-act="dup">Kopyala<kbd>Ctrl+D</kbd></button>
        <button data-act="del">Sil<kbd>Del</kbd></button>
        <hr>
        <button data-act="fade">Fade sıfırla</button>
        <button data-act="mute">${anyMuted ? "Klibin sesini aç" : "Klibi sessize al"}</button>`;
      document.body.appendChild(menu);
      const mw = menu.offsetWidth, mh = menu.offsetHeight;
      menu.style.left = Math.min(ev.clientX, window.innerWidth - mw - 8) + "px";
      menu.style.top = Math.min(ev.clientY, window.innerHeight - mh - 8) + "px";
      menu.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        const act = b.dataset.act;
        hideMenu();
        if (act === "split") {
          const inside = [...S.sel].some((id) => { const h = findClip(id); if (!h) return false; const [s, en] = BC.clipBounds(h.clip); return S.playhead > s && S.playhead < en; });
          splitSelected(inside ? S.playhead : tAt);
        } else if (act === "dup") duplicateSelected();
        else if (act === "del") deleteSelected();
        else if (act === "fade") resetFadeSelected();
        else if (act === "mute") toggleMuteSelected();
      });
    });
    document.addEventListener("pointerdown", (ev) => { if (menu && !menu.contains(ev.target)) hideMenu(); });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hideMenu(); });

    // ---------------- Komutlar (geri al yigini beat.js'te) ----------------
    function forSel(fnTrack) {
      const ids = [...S.sel];
      for (const tr of tracks()) {
        const mine = ids.filter((id) => (tr.clips || []).some((c) => c.id === id));
        if (mine.length) fnTrack(tr, mine);
      }
    }
    function splitSelected(t) {
      t = t ?? S.playhead;
      let targets = [...S.sel];
      if (!targets.length) {   // secim yoksa: secili kanalda calma cizgisinin altindaki klip
        const tr = tracks().find((x) => x.id === opts.selTid());
        targets = (tr?.clips || []).filter((c) => { const [s, e] = BC.clipBounds(c); return t > s && t < e; }).map((c) => c.id);
      }
      if (!targets.length) { opts.onStatus?.("Çalma çizgisinin altında bölünecek klip yok."); return; }
      opts.edit("Böl", () => {
        for (const tr of tracks()) {
          for (const id of targets) {
            if ((tr.clips || []).some((c) => c.id === id)) {
              // secim sol parcada kalir: sag parca tiklaninca tek basina suruklenebilsin
              tr.clips = BC.split(tr.clips, id, t, BC.newId());
            }
          }
        }
      });
    }
    function duplicateSelected() {
      if (!S.sel.size) return;
      const fresh = [];
      opts.edit("Kopyala", () => forSel((tr, ids) => {
        for (const id of ids) { const nid = BC.newId(); tr.clips = BC.duplicate(tr.clips, id, nid); fresh.push(nid); }
      }));
      S.sel = new Set(fresh);
      render();
    }
    function deleteSelected() {
      if (!S.sel.size) return;
      opts.edit("Sil", () => forSel((tr, ids) => { for (const id of ids) tr.clips = BC.delete(tr.clips, id); }));
      S.sel.clear();
      render();
    }
    function resetFadeSelected() {
      opts.edit("Fade sıfırla", () => forSel((tr, ids) => {
        tr.clips = tr.clips.map((c) => (ids.includes(c.id) ? BC.setFade(c, 0, 0) : c));
      }));
    }
    function toggleMuteSelected() {
      const anyMuted = [...S.sel].some((id) => findClip(id)?.clip.muted);
      opts.edit(anyMuted ? "Klip sesi aç" : "Klibi sessize al", () => forSel((tr, ids) => {
        tr.clips = tr.clips.map((c) => (ids.includes(c.id) ? Object.assign({}, c, { muted: !anyMuted }) : c));
      }));
    }
    function pruneSelection() {
      const all = new Set(); for (const tr of tracks()) for (const c of tr.clips || []) all.add(c.id);
      for (const id of [...S.sel]) if (!all.has(id)) S.sel.delete(id);
    }

    // ---------------- Web Audio onizleme motoru ----------------
    const Eng = { ctx: null, playing: false, when: 0, from: 0, nodes: [], buffers: new Map(), loading: new Map(), raf: 0, timers: [], els: [], token: 0 };

    function ctx() {
      if (!Eng.ctx) Eng.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
      return Eng.ctx;
    }
    async function mediaUrl(path) {
      const r = await api()?.beat_media_url?.(path).catch(() => null);
      if (!r?.ok) return null;
      if (r.duration) learnDuration(path, Number(r.duration));
      return { url: r.direct_url || r.url, duration: Number(r.duration) || 0 };
    }
    function loadBuffer(path) {
      if (Eng.buffers.has(path)) return Promise.resolve(Eng.buffers.get(path));
      if (Eng.loading.has(path)) return Eng.loading.get(path);
      const p = (async () => {
        const m = await mediaUrl(path);
        if (!m) return null;
        const dur = m.duration || S.dur.get(path) || 0;
        if (dur > LONG_SRC_SEC) { const v = { stream: true, url: m.url }; Eng.buffers.set(path, v); return v; }
        const ab = await fetch(m.url).then((r) => r.arrayBuffer());
        const buf = await ctx().decodeAudioData(ab);
        Eng.buffers.set(path, buf);
        return buf;
      })().catch(() => null).finally(() => Eng.loading.delete(path));
      Eng.loading.set(path, p);
      return p;
    }

    function stopEngine() {
      Eng.token++;
      for (const n of Eng.nodes) { try { n.stop?.(); } catch {} try { n.disconnect?.(); } catch {} }
      for (const t of Eng.timers) clearTimeout(t);
      for (const a of Eng.els) { try { a.pause(); a.removeAttribute("src"); a.load(); } catch {} }
      Eng.nodes = []; Eng.timers = []; Eng.els = [];
      if (Eng.playing) S.playhead = currentTime();
      Eng.playing = false;
      cancelAnimationFrame(Eng.raf);
      opts.onPlayState?.(false);
      drawPlayhead();
    }
    function currentTime() {
      if (!Eng.playing || !Eng.ctx) return S.playhead;
      return Math.max(0, Eng.from + (Eng.ctx.currentTime - Eng.when));
    }

    async function play(from) {
      stopEngine();
      const token = Eng.token;
      const start = Math.max(0, from ?? S.playhead);
      const trs = tracks();
      const hasSolo = trs.some((t) => t.solo);
      const audible = [];
      for (const tr of trs) {
        if (tr.mute || (hasSolo && !tr.solo)) continue;
        for (const c of tr.clips || []) {
          if (c.muted || !c.path) continue;
          if (BC.clipBounds(c)[1] <= start) continue;
          audible.push({ tr, c });
        }
      }
      if (!audible.length) { opts.onStatus?.("Çalınacak klip yok (kanallar boş, sessiz veya çalma çizgisi sonda)."); return false; }
      const paths = [...new Set(audible.map((a) => a.c.path))];
      const slow = paths.some((p) => !Eng.buffers.has(p));
      if (slow) opts.onStatus?.("Önizleme için sesler yükleniyor…");
      const ac = ctx();
      if (ac.state === "suspended") await ac.resume().catch(() => {});
      await Promise.all(paths.map(loadBuffer));
      if (token !== Eng.token) return false;     // bu arada durduruldu / yeniden baslatildi
      const when = ac.currentTime + 0.06;
      Eng.when = when; Eng.from = start; Eng.playing = true;
      const busByTrack = new Map();
      for (const tr of trs) {
        const g = ac.createGain();
        g.gain.value = dbToGain(tr.volume_db);
        const pan = ac.createStereoPanner ? ac.createStereoPanner() : null;
        if (pan) { pan.pan.value = clamp(Number(tr.pan) || 0, -1, 1); g.connect(pan); pan.connect(ac.destination); Eng.nodes.push(pan); }
        else g.connect(ac.destination);
        Eng.nodes.push(g);
        busByTrack.set(tr.id, g);
      }
      let missing = 0;
      for (const { tr, c } of audible) {
        const buf = Eng.buffers.get(c.path);
        if (!buf) { missing++; continue; }
        const [s, e] = BC.clipBounds(c);
        const len = e - s;
        const into = Math.max(0, start - s);
        const at = when + Math.max(0, s - start);
        const tl2ctx = (t) => when + (t - start);
        const g = ac.createGain();
        const base = dbToGain(c.gain_db);
        const fi = Number(c.fade_in) || 0, fo = Number(c.fade_out) || 0;
        const env = (rel) => {
          let v = base;
          if (fi > 0 && rel < fi) v *= Math.max(0, rel / fi);
          if (fo > 0 && rel > len - fo) v *= Math.max(0, (len - rel) / fo);
          return v;
        };
        g.gain.setValueAtTime(env(into), at);
        if (fi > 0 && into < fi) g.gain.linearRampToValueAtTime(base, tl2ctx(s + fi));
        if (fo > 0) {
          const foStart = Math.max(s + into, e - fo);
          g.gain.setValueAtTime(env(foStart - s), tl2ctx(foStart));
          g.gain.linearRampToValueAtTime(0, tl2ctx(e));
        }
        g.connect(busByTrack.get(tr.id));
        Eng.nodes.push(g);
        if (buf.stream) {
          // uzun kaynak: <audio> akisi (yaklasik senkron, onizleme icin)
          const a = new Audio();
          a.crossOrigin = "anonymous";
          a.preload = "auto";
          a.src = buf.url;
          const srcNode = ac.createMediaElementSource(a);
          srcNode.connect(g);
          Eng.nodes.push(srcNode); Eng.els.push(a);
          const delayMs = Math.max(0, (at - ac.currentTime) * 1000);
          const begin = () => {
            if (token !== Eng.token) return;
            const go = () => {
              if (token !== Eng.token) return;
              const late = Math.max(0, ac.currentTime - at);   // meta veri beklerken gecen sure
              try { a.currentTime = c.src_in + into + late; } catch {}
              a.play().catch(() => {});
              Eng.timers.push(setTimeout(() => a.pause(), Math.max(0, len - into - late) * 1000));
            };
            if (a.readyState >= 1) go(); else a.addEventListener("loadedmetadata", go, { once: true });
          };
          Eng.timers.push(setTimeout(begin, delayMs));
        } else {
          const src = ac.createBufferSource();
          src.buffer = buf;
          src.connect(g);
          src.start(at, c.src_in + into, Math.max(0.001, len - into));
          Eng.nodes.push(src);
        }
      }
      if (missing) opts.onStatus?.(`${missing} klibin kaynağı açılamadı (dosya taşınmış olabilir).`);
      else if (slow) opts.onStatus?.("Önizleme çalıyor (efektsiz).");
      opts.onPlayState?.(true);
      const endT = projectEnd();
      const tick = () => {
        if (!Eng.playing) return;
        S.playhead = currentTime();
        drawPlayhead();
        drawRuler();
        if (opts.follow?.()) {
          const x = t2x(S.playhead), sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
          if (x > sl + vw - 40) el.scroll.scrollLeft = x - 60;
        }
        if (S.playhead > endT + 0.25 && !opts.keepRolling?.()) { stopEngine(); return; }
        Eng.raf = requestAnimationFrame(tick);
      };
      Eng.raf = requestAnimationFrame(tick);
      return true;
    }
    function toggle() { if (Eng.playing) stopEngine(); else play(S.playhead); }
    function restartIfPlaying() { if (Eng.playing) play(currentTime()); }
    function dropBuffer(path) { Eng.buffers.delete(path); }

    return {
      render, setZoom, zoomBy, fit, ensureVisible, setPlayhead, play, stop: stopEngine, toggle, restartIfPlaying,
      isPlaying: () => Eng.playing, getPlayhead: () => (Eng.playing ? currentTime() : S.playhead),
      selection: () => S.sel, clearSel, pruneSelection,
      splitSelected, duplicateSelected, deleteSelected, resetFadeSelected, toggleMuteSelected,
      setSnap: (d) => { S.snapDiv = Number(d) || 0; }, getSnap: () => S.snapDiv,
      pps: () => S.pps, projectEnd, dropBuffer, isDragging: () => !!S.drag,
      trackColor,
    };
  }

  root.BeatTimeline = { create, trackColor };
})(window);
