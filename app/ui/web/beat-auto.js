"use strict";
/* Kami Beat Asama 2b (window.BeatAuto): kanal ses/pan otomasyonu — saf hesaplar + serit cizimi.
   Veri: kanal automation = { volume: [[t, db], ...], pan: [[t, v], ...] } (Python beat_mixbus ile ayni kurallar):
   - noktalar arasi DOGRUSAL (ses dB cinsinden, pan -1..1); ilk noktadan once ilk deger, sondan sonra son deger;
   - ses seridi kanal surgusune EKLENIR (0 dB = surgu), pan seridi noktasi varsa pan dugmesinin yerine gecer.
   Web Audio'da gain dogrusal kazanc uzerinde rampa yapar; dB-dogrusal egriye yakin olsun diye ses seridi
   rampPoints ile 20 ms'lik parcalara bolunur (bounce ornek duzeyinde tam dB-dogrusal). */
(function (root) {
  const RANGES = {
    volume: { lo: -40, hi: 12, def: 0, unit: "dB", label: "Ses" },
    pan: { lo: -1, hi: 1, def: 0, unit: "", label: "Pan" },
  };
  const MAX_POINTS = 2000;
  const r4 = (v) => Math.round(v * 1e4) / 1e4;
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const num = (v, d) => { const x = Number(v); return Number.isFinite(x) ? x : d; };

  /** Python normalize_points ile ayni: t>=0, deger aralikta, 4 ondalik, ayni t'de son kazanir, sirali. */
  function normalize(points, param) {
    const R = RANGES[param] || RANGES.volume;
    const m = new Map();
    for (const p of points || []) {
      if (!Array.isArray(p) || p.length < 2) continue;
      const t0 = num(p[0], NaN), v = num(p[1], NaN);
      if (!Number.isFinite(t0) || !Number.isFinite(v)) continue;     // gecersiz nokta atlanir
      m.set(r4(Math.max(0, t0)), r4(clamp(v, R.lo, R.hi)));
    }
    return [...m.keys()].sort((a, b) => a - b).slice(0, MAX_POINTS).map((t) => [t, m.get(t)]);
  }
  function normalizeAll(a) {
    a = a && typeof a === "object" ? a : {};
    return { volume: normalize(a.volume, "volume"), pan: normalize(a.pan, "pan") };
  }
  function hasAuto(tr) { const a = tr?.automation; return !!(a && ((a.volume || []).length || (a.pan || []).length)); }

  /** Noktadaki deger (Python value_at ile birebir). */
  function valueAt(points, t, def = 0) {
    if (!points || !points.length) return def;
    if (t <= points[0][0]) return Number(points[0][1]);
    const last = points[points.length - 1];
    if (t >= last[0]) return Number(last[1]);
    let lo = 0, hi = points.length - 1;
    while (hi - lo > 1) { const mid = (lo + hi) >> 1; if (points[mid][0] <= t) lo = mid; else hi = mid; }
    const [t0, v0] = points[lo], [t1, v1] = points[hi];
    return t1 > t0 ? v0 + (v1 - v0) * (t - t0) / (t1 - t0) : Number(v1);
  }
  /** Ornek duzeyinde zarf (Python envelope ile ayni): t = (start + i) / sr. */
  function envelope(points, startSample, n, sr, def = 0) {
    const out = new Float64Array(n);
    for (let i = 0; i < n; i++) out[i] = valueAt(points, (startSample + i) / sr, def);
    return out;
  }
  /** [ts, te] icin rampa noktalari: uclar + aradaki kirilma noktalari (+ step > 0 ise o araliklarla ara noktalar).
      Web Audio: ilk noktaya setValueAtTime, sonrakilere linearRampToValueAtTime. */
  function rampPoints(points, ts, te, step = 0, def = 0) {
    if (!(te > ts)) return [[ts, valueAt(points, ts, def)]];
    const keys = new Set([ts, te]);
    for (const [t] of points || []) if (t > ts && t < te) keys.add(t);
    let ks = [...keys].sort((a, b) => a - b);
    if (step > 0) {
      const more = [];
      for (let i = 0; i + 1 < ks.length; i++) {
        const a = ks[i], b = ks[i + 1];
        const va = valueAt(points, a, def), vb = valueAt(points, b, def);
        if (va === vb) continue;                       // sabit bolgede ara nokta gereksiz
        const n = Math.min(400, Math.floor((b - a) / step));
        for (let k = 1; k < n; k++) more.push(a + (b - a) * k / n);
      }
      ks = ks.concat(more).sort((a, b) => a - b);
    }
    return ks.map((t) => [t, valueAt(points, t, def)]);
  }
  const dbGain = (db) => Math.pow(10, db / 20);
  /** Web Audio planlamasi: AudioParam'a [ts, te) araligini ctx zamaniyla yazar. map: deger -> param degeri. */
  function schedule(param, points, ts, te, toCtx, map, step, def, fromCtx) {
    const pts = rampPoints(points, ts, te, step, def);
    let first = true;
    for (const [t, v] of pts) {
      const at = toCtx(t);
      if (at < fromCtx) continue;
      if (first) { param.setValueAtTime(map(valueAt(points, Math.max(ts, t), def)), at); first = false; }
      else param.linearRampToValueAtTime(map(v), at);
    }
    if (first) param.setValueAtTime(map(valueAt(points, te, def)), fromCtx);
  }

  // ---- serit geometrisi ----
  const PAD = 6;
  function yOf(v, param, h) {
    const R = RANGES[param] || RANGES.volume;
    return PAD + (1 - (clamp(v, R.lo, R.hi) - R.lo) / (R.hi - R.lo)) * (h - 2 * PAD);
  }
  function vOf(y, param, h) {
    const R = RANGES[param] || RANGES.volume;
    const f = 1 - (y - PAD) / Math.max(1, h - 2 * PAD);
    let v = R.lo + clamp(f, 0, 1) * (R.hi - R.lo);
    v = param === "pan" ? Math.round(v * 100) / 100 : Math.round(v * 10) / 10;
    if (param === "pan" && Math.abs(v) < 0.04) v = 0;            // merkeze yapis
    if (param === "volume" && Math.abs(v) < 0.4) v = 0;
    return v;
  }
  function fmt(v, param) {
    if (param === "pan") return Math.abs(v) < 0.005 ? "C" : (v < 0 ? `L${Math.round(-v * 100)}` : `R${Math.round(v * 100)}`);
    return `${v > 0 ? "+" : ""}${Number(v).toFixed(1)} dB`;
  }
  /** SVG: sifir cizgisi, egri (ilk/son deger seridin basina/sonuna tutulur), noktalar. */
  function laneSvg(points, param, t2x, width, h, selIdx = -1) {
    const R = RANGES[param] || RANGES.volume;
    const z = yOf(R.def, param, h);
    let path = "";
    if (points.length) {
      const xy = points.map(([t, v]) => [t2x(t), yOf(v, param, h)]);
      path = `M0,${xy[0][1].toFixed(1)} ` + xy.map(([x, y]) => `L${x.toFixed(1)},${y.toFixed(1)}`).join(" ")
        + ` L${width},${xy[xy.length - 1][1].toFixed(1)}`;
    }
    const dots = points.map(([t, v], i) => `<circle class="kb-ap${i === selIdx ? " sel" : ""}" data-api="${i}" cx="${t2x(t).toFixed(1)}" cy="${yOf(v, param, h).toFixed(1)}" r="4.5"><title>${fmt(v, param)} @ ${t.toFixed(2)} sn</title></circle>`).join("");
    return `<svg class="kb-auto-svg" width="${width}" height="${h}" viewBox="0 0 ${width} ${h}" preserveAspectRatio="none">`
      + `<line class="kb-auto-zero" x1="0" x2="${width}" y1="${z.toFixed(1)}" y2="${z.toFixed(1)}"/>`
      + (path ? `<path class="kb-auto-line" d="${path}"/>` : "")
      + dots + `</svg>`;
  }
  function hitPoint(points, param, x, y, t2x, h, r = 7) {
    let best = -1, bd = r * r;
    points.forEach(([t, v], i) => {
      const dx = t2x(t) - x, dy = yOf(v, param, h) - y, d = dx * dx + dy * dy;
      if (d <= bd) { bd = d; best = i; }
    });
    return best;
  }
  // ---- duzenleme (kopya dondurur) ----
  function insert(points, t, v, param) {
    const pts = normalize(points, param).filter((p) => Math.abs(p[0] - r4(t)) > 1e-9);
    pts.push([r4(Math.max(0, t)), v]);
    const out = normalize(pts, param);
    return { points: out, idx: out.findIndex((p) => p[0] === r4(Math.max(0, t))) };
  }
  /** Noktayi tasir; komsularinin arasinda kalir (sira korunur). */
  function move(points, idx, t, v, param) {
    const pts = points.map((p) => p.slice());
    if (!pts[idx]) return { points: pts, idx };
    const lo = idx > 0 ? pts[idx - 1][0] + 0.001 : 0;
    const hi = idx < pts.length - 1 ? pts[idx + 1][0] - 0.001 : Infinity;
    const R = RANGES[param] || RANGES.volume;
    pts[idx] = [r4(clamp(t, lo, Math.max(lo, hi))), r4(clamp(v, R.lo, R.hi))];
    return { points: pts, idx };
  }
  function remove(points, idx) { return points.filter((_, i) => i !== idx); }

  root.BeatAuto = { RANGES, normalize, normalizeAll, hasAuto, valueAt, envelope, rampPoints, schedule, dbGain,
                    yOf, vOf, fmt, laneSvg, hitPoint, insert, move, remove };
})(typeof window !== "undefined" ? window : globalThis);
