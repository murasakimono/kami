"use strict";
/* Kami Beat Asama 1c: soz paneli + teleprompter saf hesaplari (window.BeatLyrics).
   app/core/beat_lyrics.py ile BIREBIR ayni semantik (tests/test_beat_1c.py node ile karsilastirir).
   Soz METNI hic degistirilmez; yalniz ayristirma, bolum eslestirme ve zamanlama. Sureler SANIYE. */
(function (root) {
  const HEADER_RE = /^\s*\[\s*([^\]]*?)\s*\]\s*$/;
  const SYN = {
    "nakarat": "nakarat", "chorus": "nakarat", "hook": "nakarat", "koro": "nakarat",
    "verse": "verse", "kıta": "verse", "kita": "verse", "kıt'a": "verse",
    "köprü": "köprü", "kopru": "köprü", "bridge": "köprü",
    "intro": "intro", "ıntro": "intro", "giriş": "intro", "giris": "intro",
    "outro": "outro", "çıkış": "outro", "cikis": "outro", "kapanış": "outro", "final": "outro",
    "pre-chorus": "ön nakarat", "prechorus": "ön nakarat", "pre chorus": "ön nakarat", "ön nakarat": "ön nakarat",
    "post-chorus": "nakarat sonrası", "drop": "nakarat",
  };
  const r6 = (x) => Math.floor(Number(x) * 1e6 + 0.5) / 1e6;
  const f = (v, d = 0) => {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return d;
    const x = Number(v);
    return Number.isFinite(x) ? x : d;
  };
  const toInt = (v) => { const x = Number(v); return Number.isFinite(x) && v !== null && v !== "" && typeof v !== "boolean" ? Math.trunc(x) : null; };

  const trLower = (s) => String(s ?? "").replace(/I/g, "ı").replace(/İ/g, "i").toLowerCase();

  function headerName(line) {
    const m = HEADER_RE.exec(String(line ?? ""));
    if (!m) return "";
    return m[1].split(":")[0].trim();
  }

  function sectionBase(name) {
    let s = trLower(name).trim();
    s = s.replace(/[\s#.\-]*\d+\s*$/, "").trim();
    s = s.replace(/\s+/g, " ");
    return Object.prototype.hasOwnProperty.call(SYN, s) ? SYN[s] : s;
  }

  function parseLyrics(text) {
    const raw = String(text ?? "").replace(/\r\n/g, "\n").replace(/\r/g, "\n").split("\n");
    const lines = [], blocks = [];
    let n = 0;
    raw.forEach((ln, i) => {
      const h = headerName(ln);
      if (h || HEADER_RE.test(ln)) {
        blocks.push({ header: h, base: sectionBase(h), lines: [] });
        lines.push({ i, kind: "header", text: ln, header: h, block: blocks.length - 1, n: -1 });
        return;
      }
      if (!ln.trim()) {
        lines.push({ i, kind: "blank", text: ln, header: "", block: blocks.length - 1, n: -1 });
        return;
      }
      if (!blocks.length) {
        blocks.push({ header: "", base: "", lines: [] });
        for (const x of lines) x.block = 0;
      }
      blocks[blocks.length - 1].lines.push(n);
      lines.push({ i, kind: "line", text: ln, header: "", block: blocks.length - 1, n });
      n++;
    });
    return { lines, blocks, count: n };
  }

  function assignBlocks(blocks, sections) {
    const secs = sections || [];
    const out = [];
    let cur = 0;
    for (const b of blocks || []) {
      const base = String(b.base || "");
      if (cur >= secs.length) { out.push(-1); continue; }
      let k;
      if (base) {
        let hit = -1;
        for (let j = cur; j < secs.length; j++) if (sectionBase(secs[j].name) === base) { hit = j; break; }
        k = hit >= 0 ? hit : cur;
      } else {
        k = cur;
        if (sectionBase(secs[k].name) === "intro" && k + 1 < secs.length) k += 1;
      }
      out.push(k);
      cur = k + 1;
    }
    return out;
  }

  function resolveAnchors(anchors, texts) {
    const out = {};
    const n = texts.length;
    for (const a of anchors || []) {
      if (!a || typeof a !== "object" || Array.isArray(a)) continue;
      const li = toInt(a.line);
      if (li === null) continue;
      const t = f(a.t, -1);
      if (t < 0) continue;
      const txt = String(a.text || "");
      let k = li;
      if (txt && !(li >= 0 && li < n && texts[li] === txt)) {
        let best = -1;
        for (let j = 0; j < n; j++) {
          if (texts[j] === txt && (best < 0 || Math.abs(j - li) < Math.abs(best - li))) best = j;
        }
        k = best >= 0 ? best : li;
      }
      if (k >= 0 && k < n) out[k] = r6(t);
    }
    return out;
  }

  function lyricStart(v) {
    if (v === null || v === undefined || v === "" || typeof v === "boolean") return null;
    const x = f(v, -1);
    return x >= 0 ? r6(x) : null;
  }

  function lineTimes(text, sections, bpm, barsPerLine = 1, anchors = null, beatsPerBar = 4, start = null) {
    const p = parseLyrics(text);
    const secs = sections ? Array.from(sections) : [];
    bpm = f(bpm, 120);
    bpm = bpm > 0 ? bpm : 120;
    const bpb = Math.max(1, Math.trunc(f(beatsPerBar, 4)) || 4);
    const bar = 60 / bpm * bpb;
    let gBpl = f(barsPerLine, 1);
    gBpl = gBpl > 0 ? gBpl : 1;
    const texts = p.lines.filter((x) => x.kind === "line").map((x) => x.text);
    const anc = resolveAnchors(anchors, texts);
    const owner = assignBlocks(p.blocks, secs);
    const st = lyricStart(start);
    const first = p.blocks.findIndex((b) => b.lines.length > 0);
    const out = [];
    let prevEnd = 0;
    p.blocks.forEach((b, bi) => {
      const k = bi < owner.length ? owner[bi] : -1;
      const sec = k >= 0 && k < secs.length ? secs[k] : null;
      const bpl = sec ? f(sec.bars_per_line, 0) : 0;
      const step = bar * (bpl > 0 ? bpl : gBpl);
      const start = bi === first && st !== null ? st : (sec ? f(sec.start, 0) : prevEnd);
      let baseT = start, baseJ = 0, t = start;
      b.lines.forEach((n, j) => {
        const has = Object.prototype.hasOwnProperty.call(anc, n);
        if (has) { baseT = anc[n]; baseJ = j; }
        t = baseT + (j - baseJ) * step;
        out.push({ n, t: r6(t), block: bi, section: k, anchored: has });
      });
      prevEnd = b.lines.length ? t + step : start;
    });
    out.sort((x, y) => x.n - y.n);
    return out;
  }

  function syncLine(anchors, n, t, text = "") {
    n = Math.trunc(Number(n));
    const keep = (anchors || []).filter((a) => a && typeof a === "object" && Math.trunc(f(a.line, -1)) !== n).map((a) => Object.assign({}, a));
    keep.push({ line: n, t: r6(Math.max(0, f(t))), text: String(text || "") });
    keep.sort((a, b) => Math.trunc(f(a.line, 0)) - Math.trunc(f(b.line, 0)));
    return keep;
  }
  function unsyncLine(anchors, n) {
    return (anchors || []).filter((a) => a && typeof a === "object" && Math.trunc(f(a.line, -1)) !== Math.trunc(Number(n))).map((a) => Object.assign({}, a));
  }

  function activeLine(times, t) {
    t = f(t);
    let best = -1, bestT = -1e18;
    for (const x of times || []) {
      const xt = f(x.t);
      if (xt <= t + 1e-9 && (xt > bestT || (xt === bestT && Math.trunc(x.n) > best))) { best = Math.trunc(x.n); bestT = xt; }
    }
    return best;
  }

  const api = {
    trLower, headerName, sectionBase, parseLyrics, assignBlocks, resolveAnchors, lineTimes, syncLine, unsyncLine, activeLine,
    lyricStart,
  };
  // Python adlariyla da (testler ayni adla cagirir)
  Object.assign(api, {
    tr_lower: trLower, header_name: headerName, section_base: sectionBase, parse_lyrics: parseLyrics,
    assign_blocks: assignBlocks, resolve_anchors: resolveAnchors, line_times: lineTimes, sync_line: syncLine,
    unsync_line: unsyncLine, active_line: activeLine, lyric_start: lyricStart,
  });
  root.BeatLyrics = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
})(typeof window !== "undefined" ? window : globalThis);
