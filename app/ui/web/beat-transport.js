"use strict";
/* Kami Beat Asama 1b: kayit akisinin saf zaman hesaplari (window.BeatTransport).
   app/core/beat_transport.py ile BIREBIR ayni semantik (tests/test_beat_1b.py node ile karsilastirir).
   u = dogrusal tasima zamani; dongude u >= b iken t = a + ((u - b) mod (b - a)). Sureler SANIYE. */
(function (root) {
  const MIN_LEN = 0.01;
  const MIN_LAP_PARTIAL = 0.25;
  const r6 = (x) => Math.floor(Number(x) * 1e6 + 0.5) / 1e6;
  const f = (v, d = 0) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return d;
    const x = Number(v);
    return Number.isFinite(x) ? x : d;
  };
  const beatSec = (bpm) => { bpm = f(bpm); return bpm > 0 ? 60 / bpm : 0.5; };
  const bpbOf = (n) => Math.max(1, parseInt(n || 4, 10) || 4);
  const barSec = (bpm, bpb = 4) => beatSec(bpm) * bpbOf(bpb);

  function metronomeTicks(bpm, t0, t1, beatsPerBar = 4, origin = 0) {
    const b = beatSec(bpm);
    const bpb = bpbOf(beatsPerBar);
    t0 = f(t0); t1 = f(t1); origin = f(origin);
    const out = [];
    if (t1 <= t0) return out;
    let k = Math.ceil((t0 - origin) / b - 1e-9);
    for (;;) {
      const t = origin + k * b;
      if (t >= t1 - 1e-9) break;
      const beat = ((k % bpb) + bpb) % bpb;
      out.push({ t: r6(t), k, beat, accent: beat === 0 });
      k++;
      if (out.length > 100000) break;
    }
    return out;
  }

  function countInPlan(recFrom, bpm, bars, beatsPerBar = 4) {
    bars = Math.max(0, Math.min(2, Math.trunc(f(bars))));
    const bpb = bpbOf(beatsPerBar);
    const F = f(recFrom);
    const dur = bars * barSec(bpm, bpb);
    const start = F - dur;
    const ticks = bars ? metronomeTicks(bpm, start, F, bpb, F) : [];
    return { transport_start: r6(start), rec_from: r6(F), duration: r6(dur), beats: bars * bpb, ticks };
  }

  function timelineAt(u, uStart, loopA = null, loopB = null) {
    u = f(u);
    if (loopA === null || loopA === undefined || loopB === null || loopB === undefined) return r6(u);
    const a = f(loopA), b = f(loopB);
    const ln = b - a;
    if (ln < MIN_LEN || f(uStart) >= b || u < b) return r6(u);
    return r6(a + ((u - b) % ln));
  }

  const recordingOrigin = (anchorU, anchorWall, recEpoch0, latencyS = 0) =>
    r6(f(anchorU) - (f(anchorWall) - f(recEpoch0)) - f(latencyS));

  function linearTake(u0e, recLen, keepFrom) {
    u0e = f(u0e); recLen = f(recLen); const F = f(keepFrom);
    const start = Math.max(F, u0e, 0);
    const srcIn = start - u0e;
    if (recLen - srcIn < MIN_LEN) return null;
    return { start: r6(start), src_in: r6(srcIn), src_out: r6(recLen) };
  }

  function loopLaps(u0e, recLen, a, b) {
    u0e = f(u0e); recLen = f(recLen); a = f(a); b = f(b);
    const ln = b - a;
    if (ln < MIN_LEN || recLen < MIN_LEN) return [];
    const laps = [];
    for (let k = 0; k <= 10000; k++) {
      const lapU0 = a + k * ln;
      let srcIn = lapU0 - u0e;
      if (srcIn >= recLen - MIN_LEN) break;
      let start = a;
      if (srcIn < 0) { start = a - srcIn; srcIn = 0; }
      let srcOut = (lapU0 + ln) - u0e;
      const complete = srcOut <= recLen + 0.005 && start === a;
      srcOut = Math.min(srcOut, recLen);
      if (srcOut - srcIn >= MIN_LEN) laps.push({ lap: k, start: r6(start), src_in: r6(srcIn), src_out: r6(srcOut), complete });
    }
    const full = laps.filter((x) => x.complete);
    if (full.length) return full;
    return laps.filter((x) => x.src_out - x.src_in >= MIN_LAP_PARTIAL).slice(0, 1);
  }

  function punchWindow(u0e, recLen, t0, t1, xfade = 0.01) {
    u0e = f(u0e); recLen = f(recLen); t0 = f(t0); t1 = f(t1);
    const h = Math.max(0, f(xfade)) / 2;
    const start = Math.max(t0 - h, u0e, 0);
    const srcIn = start - u0e;
    const srcOut = Math.min((t1 + h) - u0e, recLen);
    if (srcOut - srcIn < MIN_LEN) return null;
    return { start: r6(start), src_in: r6(srcIn), src_out: r6(srcOut) };
  }

  // ---------------- Revize R1: hassas duzenleme ----------------
  const GRID_DIVS = [1, 2, 4, 8, 16, 32];
  const GRID_MIN_PX = 10;
  const NUDGE_MS = { "10ms": 0.01, "1ms": 0.001 };
  const LATENCY_LIMIT_MS = 500;
  const divOf = (div) => { const d = Math.trunc(Number(div)); return Number.isFinite(d) ? d : 0; };

  function gridSec(bpm, div) {
    const d = divOf(div);
    if (!GRID_DIVS.includes(d)) return 0;
    return barSec(bpm, 4) / d;
  }
  function autoGridDiv(pps, bpm, minPx = GRID_MIN_PX) {
    pps = f(pps);
    const mp = f(minPx, GRID_MIN_PX);
    let best = GRID_DIVS[0];
    if (pps <= 0) return best;
    for (const d of GRID_DIVS) if (gridSec(bpm, d) * pps >= mp - 1e-9) best = d;
    return best;
  }
  function resolveGrid(mode, pps, bpm) {
    if (mode === null || mode === undefined || mode === "" || String(mode).toLowerCase() === "auto") return autoGridDiv(pps, bpm);
    const d = Math.trunc(Number(mode));
    if (!Number.isFinite(d)) return 0;
    return GRID_DIVS.includes(d) ? d : 0;
  }
  function snapTo(t, bpm, div) {
    const d = divOf(div);
    if (!GRID_DIVS.includes(d) || f(bpm) <= 0) return r6(Math.max(0, f(t)));
    const g = gridSec(bpm, d);
    return r6(Math.max(0, Math.floor(f(t) / g + 0.5) * g));
  }
  function nudgeTime(t, direction, mode, bpm, div) {
    t = f(t);
    const d = f(direction) > 0 ? 1 : -1;
    if (Object.prototype.hasOwnProperty.call(NUDGE_MS, mode)) return r6(Math.max(0, t + d * NUDGE_MS[mode]));
    const g = gridSec(bpm, div);
    if (g <= 0) return r6(Math.max(0, t + d * NUDGE_MS["10ms"]));
    const k = t / g;
    const n = d > 0 ? Math.floor(k + 1e-6) + 1 : Math.ceil(k - 1e-6) - 1;
    return r6(Math.max(0, n * g));
  }
  function formatPosition(t, bpm, beatsPerBar = 4) {
    t = Math.max(0, f(t));
    const ms = Math.floor(t * 1000 + 0.5);
    const tm = `${Math.floor(ms / 60000)}:${String(Math.floor((ms % 60000) / 1000)).padStart(2, "0")}.${String(ms % 1000).padStart(3, "0")}`;
    const bpb = bpbOf(beatsPerBar);
    const q = t / beatSec(bpm);
    const qi = Math.floor(q + 1e-9);
    const six = Math.min(4, Math.floor((q - qi) * 4 + 1e-9) + 1);
    return { time: tm, bbt: `${Math.floor(qi / bpb) + 1}.${(qi % bpb) + 1}.${six}` };
  }
  // ---------------- Revize R2: kalici gecikme (proje > genel ayar) ----------------
  function effectiveLatencyMs(projectMs, globalMs) {
    const p = f(projectMs);
    if (Math.abs(p) > 1e-9) return { ms: r6(Math.max(-LATENCY_LIMIT_MS, Math.min(LATENCY_LIMIT_MS, p))), source: "project" };
    const g = Math.max(-LATENCY_LIMIT_MS, Math.min(LATENCY_LIMIT_MS, f(globalMs)));
    return { ms: r6(g), source: "global" };
  }

  root.BeatTransport = {
    beatSec, barSec, metronomeTicks, countInPlan, timelineAt, recordingOrigin, linearTake, loopLaps, punchWindow,
    // Python adlari (esdeger testi)
    beat_sec: beatSec, bar_sec: barSec, metronome_ticks: metronomeTicks, count_in_plan: countInPlan,
    timeline_at: timelineAt, recording_origin: recordingOrigin, linear_take: linearTake, loop_laps: loopLaps,
    punch_window: punchWindow,
    GRID_DIVS, gridSec, autoGridDiv, resolveGrid, snapTo, nudgeTime, formatPosition, effectiveLatencyMs,
    grid_sec: gridSec, auto_grid_div: autoGridDiv, resolve_grid: resolveGrid, snap_to: snapTo, nudge_time: nudgeTime,
    format_position: formatPosition, effective_latency_ms: effectiveLatencyMs,
  };
})(typeof window !== "undefined" ? window : globalThis);
