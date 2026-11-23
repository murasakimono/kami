"use strict";
/* Kami Beat Asama 1a: saf klip islemleri (window.BeatClips).
   app/core/beat_clips.py ile BIREBIR ayni semantik; aritmetik ayni sirada, sonuclar r6 ile
   mikro-saniyeye yuvarlanir. tests/test_beat_1a.py node ile iki uygulamayi karsilastirir.
   Sureler SANIYE. Fonksiyonlar girdiyi degistirmez, yeni nesne/dizi dondurur. */
(function (root) {
  const MIN_LEN = 0.01;
  const DIVISIONS = [1, 2, 4, 8, 16];

  const r6 = (x) => Math.floor(Number(x) * 1e6 + 0.5) / 1e6;
  const num = (v, d = 0) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return d;
    const f = Number(v);
    return Number.isFinite(f) ? f : d;
  };
  const newId = () => "c_" + Math.random().toString(16).slice(2, 10).padEnd(8, "0");
  const copy = (c) => Object.assign({}, c);

  const clipLen = (c) => r6(num(c.src_out) - num(c.src_in));
  function clipBounds(c) {
    const s = num(c.start);
    return [r6(s), r6(s + clipLen(c))];
  }
  function overlaps(a, b) {
    const [a0, a1] = clipBounds(a);
    const [b0, b1] = clipBounds(b);
    return a0 < b1 && b0 < a1;
  }
  function clampFades(c) {
    const ln = clipLen(c);
    const fi = Math.max(0, Math.min(num(c.fade_in), ln));
    const fo = Math.max(0, Math.min(num(c.fade_out), r6(ln - fi)));
    c.fade_in = r6(fi);
    c.fade_out = r6(fo);
    return c;
  }
  const hasLen = (c) => c.src_len !== null && c.src_len !== undefined && num(c.src_len) > 0;

  function normalize(clip) {
    const c = copy(clip);
    c.id = String(c.id || newId());
    c.take_id = String(c.take_id || "");
    c.path = String(c.path || "");
    let srcIn = Math.max(0, num(c.src_in));
    let srcOut = num(c.src_out, srcIn + MIN_LEN);
    if (hasLen(c)) {
      const sl = r6(num(c.src_len));
      c.src_len = sl;
      srcOut = Math.min(srcOut, sl);
      srcIn = Math.min(srcIn, r6(sl - MIN_LEN));
    } else {
      delete c.src_len;
    }
    if (srcOut - srcIn < MIN_LEN) srcOut = srcIn + MIN_LEN;
    c.src_in = r6(srcIn);
    c.src_out = r6(srcOut);
    c.start = r6(Math.max(0, num(c.start)));
    c.gain_db = r6(num(c.gain_db));
    c.muted = !!c.muted;
    c.fade_in = num(c.fade_in);
    c.fade_out = num(c.fade_out);
    return clampFades(c);
  }

  const find = (clips, id) => clips.findIndex((c) => c.id === id);

  function snapTime(t, bpm, division = 4) {
    t = num(t);
    bpm = num(bpm);
    division = parseInt(division, 10);
    if (bpm <= 0 || !DIVISIONS.includes(division)) return r6(Math.max(0, t));
    const grid = (60 / bpm) * 4 / division;
    return r6(Math.max(0, Math.floor(t / grid + 0.5) * grid));
  }

  function split(clips, clipId, t, newIdArg) {
    const out = clips.map(copy);
    const i = find(out, clipId);
    if (i < 0) return out;
    const c = out[i];
    const [s, e] = clipBounds(c);
    t = num(t);
    if (t < s + MIN_LEN || t > e - MIN_LEN) return out;
    const cut = r6(num(c.src_in) + (t - s));
    const left = copy(c);
    left.src_out = cut;
    left.fade_out = 0;
    const right = copy(c);
    right.id = newIdArg || newId();
    right.src_in = cut;
    right.start = r6(t);
    right.fade_in = 0;
    out[i] = clampFades(left);
    out.splice(i + 1, 0, clampFades(right));
    return out;
  }

  function trimStart(clip, newStart) {
    const c = copy(clip);
    const [s, e] = clipBounds(c);
    const srcIn = num(c.src_in);
    const lo = Math.max(0, s - srcIn);
    const hi = e - MIN_LEN;
    const ns = Math.max(lo, Math.min(num(newStart), hi));
    c.src_in = r6(srcIn + (ns - s));
    c.start = r6(ns);
    return clampFades(c);
  }

  function trimEnd(clip, newEnd) {
    const c = copy(clip);
    const s = num(c.start);
    const srcIn = num(c.src_in);
    const lo = s + MIN_LEN;
    let ne = Math.max(lo, num(newEnd));
    if (hasLen(c)) {
      ne = Math.min(ne, s + (num(c.src_len) - srcIn));
      ne = Math.max(lo, ne);
    }
    c.src_out = r6(srcIn + (ne - s));
    return clampFades(c);
  }

  function move(clips, clipId, newStart, snap) {
    const out = clips.map(copy);
    const i = find(out, clipId);
    if (i < 0) return out;
    let ns = num(newStart);
    if (snap) ns = snapTime(ns, num(snap.bpm), snap.division ?? 4);
    out[i].start = r6(Math.max(0, ns));
    return out;
  }

  function duplicate(clips, clipId, newIdArg) {
    const out = clips.map(copy);
    const i = find(out, clipId);
    if (i < 0) return out;
    const c = copy(out[i]);
    c.id = newIdArg || newId();
    c.start = clipBounds(out[i])[1];
    out.splice(i + 1, 0, c);
    return out;
  }

  const del = (clips, clipId) => clips.filter((c) => c.id !== clipId).map(copy);

  function setFade(clip, fadeIn, fadeOut) {
    const c = copy(clip);
    c.fade_in = Math.max(0, num(fadeIn));
    c.fade_out = Math.max(0, num(fadeOut));
    return clampFades(c);
  }

  const trackEnd = (clips) => clips.reduce((m, c) => Math.max(m, clipBounds(c)[1]), 0);

  root.BeatClips = {
    MIN_LEN, DIVISIONS, r6, newId, clipLen, clipBounds, overlaps, normalize, snapTime,
    split, trimStart, trimEnd, move, duplicate, delete: del, setFade, trackEnd,
    // Python adlariyla esdeger takma adlar (esdeger testi icin)
    clip_len: clipLen, clip_bounds: clipBounds, snap_time: snapTime, trim_start: trimStart,
    trim_end: trimEnd, set_fade: setFade, track_end: trackEnd,
  };
})(typeof window !== "undefined" ? window : globalThis);
