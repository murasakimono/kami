"use strict";
/* Kami Beat Asama 1a/1b: saf klip islemleri + take destesi (window.BeatClips).
   app/core/beat_clips.py ile BIREBIR ayni semantik; aritmetik ayni sirada, sonuclar r6 ile
   mikro-saniyeye yuvarlanir. tests/test_beat_1a.py node ile iki uygulamayi karsilastirir.
   Sureler SANIYE. Fonksiyonlar girdiyi degistirmez, yeni nesne/dizi dondurur. */
(function (root) {
  const MIN_LEN = 0.01;
  const DIVISIONS = [1, 2, 4, 8, 16, 32];

  const r6 = (x) => Math.floor(Number(x) * 1e6 + 0.5) / 1e6;
  const num = (v, d = 0) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return d;
    const f = Number(v);
    return Number.isFinite(f) ? f : d;
  };
  const newId = () => "c_" + Math.random().toString(16).slice(2, 10).padEnd(8, "0");
  const copy = (c) => Object.assign({}, c);
  // R4: klip fx zincirinin derin kopyasi
  const fxCopy = (fx) => (Array.isArray(fx) ? fx : []).filter((f) => f && typeof f === "object" && !Array.isArray(f))
    .map((f) => { const d = Object.assign({}, f); if (d.params && typeof d.params === "object") d.params = Object.assign({}, d.params); return d; });
  const withFx = (c) => { if (Array.isArray(c.fx)) c.fx = fxCopy(c.fx); return c; };

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
    if (c.stack_id) {                 // 1b: take destesi (alan yoksa tek klip = deste yok)
      c.stack_id = String(c.stack_id);
      c.stack_active = !!c.stack_active;
    } else {
      delete c.stack_id;
      delete c.stack_active;
    }
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
    withFx(left);
    withFx(right);   // R4: klip fx zinciri parcalar arasinda paylasilmaz (derin kopya)
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
    const c = withFx(copy(out[i]));
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

  // ---------------- 1b: take destesi (beat_clips.py ile birebir) ----------------
  const XFADE = 0.01;
  const newStackId = () => "s_" + Math.random().toString(16).slice(2, 10).padEnd(8, "0");
  function stackMembers(clips, stackId) {
    if (!stackId) return [];
    return clips.filter((c) => c.stack_id === stackId).map(copy);
  }
  function stackActiveId(clips, stackId) {
    const mem = clips.filter((c) => stackId && c.stack_id === stackId);
    if (!mem.length) return "";
    const a = mem.find((c) => c.stack_active);
    return String((a || mem[mem.length - 1]).id);
  }
  function stackSetActive(clips, stackId, clipId) {
    const out = clips.map(copy);
    if (!stackId || !out.some((c) => c.stack_id === stackId && c.id === clipId)) return out;
    for (const c of out) if (c.stack_id === stackId) c.stack_active = c.id === clipId;
    return out;
  }
  function isAudibleMember(clips, clip) {
    return !clip.stack_id || stackActiveId(clips, clip.stack_id) === clip.id;
  }
  function stackView(clips) {
    const act = new Map();
    const out = [];
    for (const c of clips) {
      const sid = c.stack_id;
      if (sid) {
        if (!act.has(sid)) act.set(sid, stackActiveId(clips, sid));
        if (act.get(sid) !== c.id) continue;
      }
      out.push(copy(c));
    }
    return out;
  }
  function dissolveSingletons(out) {
    const counts = new Map();
    for (const c of out) if (c.stack_id) counts.set(c.stack_id, (counts.get(c.stack_id) || 0) + 1);
    for (const c of out) if (c.stack_id && counts.get(c.stack_id) < 2) { delete c.stack_id; delete c.stack_active; }
    return out;
  }
  function stackPush(clips, stackId, clip) {
    const out = clips.map(copy);
    const nc = copy(clip);
    nc.stack_id = stackId;
    nc.stack_active = true;
    let last = -1;
    out.forEach((c, i) => { if (c.stack_id === stackId) { c.stack_active = false; last = i; } });
    if (last < 0) out.push(nc); else out.splice(last + 1, 0, nc);
    return out;
  }
  function stackRemove(clips, clipId) {
    const i = find(clips, clipId);
    if (i < 0) return clips.map(copy);
    const sid = clips[i].stack_id;
    let out = clips.filter((c) => c.id !== clipId).map(copy);
    if (sid) {
      const mem = out.filter((c) => c.stack_id === sid);
      if (mem.length && !mem.some((c) => c.stack_active)) mem[mem.length - 1].stack_active = true;
      out = dissolveSingletons(out);
    }
    return out;
  }

  // ---------------- Revize 4: klip / bolge efekti (beat_clips.py ile birebir) ----------------
  const hasClipFx = (c) => (c.fx || []).some((f) => f && typeof f === "object" && !f.bypass) || !!c.skip_track_fx;

  function regionSplit(clips, clipId, t0, t1, xfade = XFADE, ids = null, fx = null) {
    let gen;
    if (Array.isArray(ids)) { const pool = ids.slice(); gen = (k) => (pool.length ? pool.shift() : (k === "s" ? newStackId() : newId())); }
    else gen = ids || ((k) => (k === "s" ? newStackId() : newId()));
    const i = find(clips, clipId);
    if (i < 0) return { clips: clips.map(copy), mid_id: "" };
    const target = clips[i];
    const sid = target.stack_id;
    const members = sid ? clips.filter((c) => c.stack_id === sid) : [target];
    const actId = sid ? stackActiveId(clips, sid) : target.id;
    const act = members.find((c) => c.id === actId) || target;
    const [s, e] = clipBounds(act);
    t0 = Math.max(num(t0), s);
    t1 = Math.min(num(t1), e);
    if (t1 - t0 < MIN_LEN) return { clips: clips.map(copy), mid_id: "" };
    const xf = Math.max(0, num(xfade));
    const h = xf / 2;
    const hasB = t0 - s >= MIN_LEN;
    const hasA = e - t1 >= MIN_LEN;
    let sb = "", sm = "", sa = "";
    if (sid) {
      sb = sid;
      sm = hasB ? gen("s") : sid;
      sa = hasA ? gen("s") : sid;
    }
    const befores = [], mids = [], afters = [];
    let midId = "";
    for (const m of members) {
      const [ms, me] = clipBounds(m);
      const isAct = m.id === actId;
      const first = [m.id];
      const nid = () => (first.length ? first.pop() : gen("c"));
      if (hasB) {
        const b = withFx(setFade(trimEnd(m, Math.min(me, t0 + h)), m.fade_in, xf));
        b.id = nid();
        if (sid) { b.stack_id = sb; b.stack_active = !!m.stack_active; }
        befores.push(b);
      }
      let md = m;
      if (hasA) md = trimEnd(md, Math.min(me, t1 + h));
      if (hasB) md = trimStart(md, Math.max(ms, t0 - h));
      md = withFx(setFade(md, hasB ? xf : m.fade_in, hasA ? xf : m.fade_out));
      md.id = nid();
      if (sid) { md.stack_id = sm; md.stack_active = !!m.stack_active; }
      if (isAct) {
        midId = md.id;
        if (fx !== null && fx !== undefined) md.fx = fxCopy(fx);
      }
      mids.push(md);
      if (hasA) {
        const a = withFx(setFade(trimStart(m, Math.max(ms, t1 - h)), xf, m.fade_out));
        a.id = nid();
        if (sid) { a.stack_id = sa; a.stack_active = !!m.stack_active; }
        afters.push(a);
      }
    }
    const old = new Set(members.map((c) => c.id));
    const firstI = Math.min(...members.map((c) => find(clips, c.id)));
    const rest = clips.filter((c) => !old.has(c.id)).map(copy);
    const out = rest.slice(0, firstI).concat(befores, mids, afters, rest.slice(firstI));
    return { clips: dissolveSingletons(out), mid_id: midId };
  }

  function applyFxToStack(clips, clipId) {
    const out = clips.map(copy);
    const i = find(out, clipId);
    if (i < 0 || !out[i].stack_id) return out;
    const src = out[i];
    for (const c of out) {
      if (c.stack_id === src.stack_id && c.id !== src.id) { c.fx = fxCopy(src.fx); c.skip_track_fx = !!src.skip_track_fx; }
    }
    return out;
  }

  root.BeatClips = {
    XFADE, newStackId, stackMembers, stackActiveId, stackSetActive, isAudibleMember, stackView, stackPush, stackRemove,
    stack_members: stackMembers, stack_active_id: stackActiveId, stack_set_active: stackSetActive,
    is_audible_member: isAudibleMember, stack_view: stackView, stack_push: stackPush, stack_remove: stackRemove,
    MIN_LEN, DIVISIONS, r6, newId, clipLen, clipBounds, overlaps, normalize, snapTime,
    split, trimStart, trimEnd, move, duplicate, delete: del, setFade, trackEnd,
    // Python adlariyla esdeger takma adlar (esdeger testi icin)
    clip_len: clipLen, clip_bounds: clipBounds, snap_time: snapTime, trim_start: trimStart,
    trim_end: trimEnd, set_fade: setFade, track_end: trackEnd,
    // R4
    hasClipFx, regionSplit, applyFxToStack, has_clip_fx: hasClipFx, region_split: regionSplit, apply_fx_to_stack: applyFxToStack,
  };
})(typeof window !== "undefined" ? window : globalThis);
