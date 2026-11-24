"""Kami Beat Asama 1c: soz paneli + teleprompter saf hesaplari.

app/ui/web/beat-lyrics.js ile BIREBIR ayni semantik (tests/test_beat_1c.py node ile karsilastirir).
Kural: soz METNI hic degistirilmez; burada yalniz ayristirma, bolum eslestirme ve zamanlama vardir.

- Basliklar: tek basina satirda `[Nakarat]`, `[Verse 2: Metehan]` (":" sonrasi atilir).
- Blok: bir basliktan sonraki sozlu satirlar (ilk basliktan onceki satirlar basliksiz blok).
- Satir zamani = blok baslangici (eslesen bolumun start'i) + sira x bar suresi x satir basina bar.
- Elle senkron (anchors): bir satirin zamani sabitlenir; ayni bloktaki sonraki satirlar o kadar kayar
  (bir sonraki capaya kadar). Sonraki bloklar kendi bolumlerine bagli kalir.
"""
from __future__ import annotations

import math
import re
from typing import Any

_HEADER_RE = re.compile(r"^\s*\[\s*([^\]]*?)\s*\]\s*$")
_SYNONYMS = {
    "nakarat": "nakarat", "chorus": "nakarat", "hook": "nakarat", "koro": "nakarat",
    "verse": "verse", "kıta": "verse", "kita": "verse", "kıt'a": "verse",
    "köprü": "köprü", "kopru": "köprü", "bridge": "köprü",
    "intro": "intro", "ıntro": "intro", "giriş": "intro", "giris": "intro",
    "outro": "outro", "çıkış": "outro", "cikis": "outro", "kapanış": "outro", "final": "outro",
    "pre-chorus": "ön nakarat", "prechorus": "ön nakarat", "pre chorus": "ön nakarat", "ön nakarat": "ön nakarat",
    "post-chorus": "nakarat sonrası", "drop": "nakarat",
}


def _r6(x: float) -> float:
    return math.floor(float(x) * 1e6 + 0.5) / 1e6


def _f(v: Any, d: float = 0.0) -> float:
    if v is None or v == "" or isinstance(v, bool):
        return d
    try:
        x = float(v)
    except (TypeError, ValueError):
        return d
    return x if math.isfinite(x) else d


def tr_lower(s: Any) -> str:
    """Turkce kucuk harf (I -> ı, İ -> i); JS tarafi ayni donusumu elle yapar."""
    return str(s or "").replace("I", "ı").replace("İ", "i").lower()


def header_name(line: Any) -> str:
    """`[Nakarat]` -> 'Nakarat'; `[Verse 1: Metehan]` -> 'Verse 1'; baslik degilse ''."""
    m = _HEADER_RE.match(str(line or ""))
    if not m:
        return ""
    name = m.group(1).split(":")[0].strip()
    return name


def section_base(name: Any) -> str:
    """Bolum/baslik adinin karsilastirma anahtari: kucuk harf, sondaki numara atilir, es anlamlilar birlesir."""
    s = tr_lower(name).strip()
    s = re.sub(r"[\s#.\-]*\d+\s*$", "", s).strip()
    s = re.sub(r"\s+", " ", s)
    return _SYNONYMS.get(s, s)


def parse_lyrics(text: Any) -> dict[str, Any]:
    """Satirlari baslik / soz / bos olarak ayirir; soz satirlarina sira numarasi (n), bloklara satir listesi."""
    raw = str(text or "").replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines: list[dict[str, Any]] = []
    blocks: list[dict[str, Any]] = []
    n = 0
    for i, ln in enumerate(raw):
        h = header_name(ln)
        if h or _HEADER_RE.match(ln):
            blocks.append({"header": h, "base": section_base(h), "lines": []})
            lines.append({"i": i, "kind": "header", "text": ln, "header": h, "block": len(blocks) - 1, "n": -1})
            continue
        if not ln.strip():
            lines.append({"i": i, "kind": "blank", "text": ln, "header": "", "block": len(blocks) - 1, "n": -1})
            continue
        if not blocks:
            blocks.append({"header": "", "base": "", "lines": []})
            for x in lines:          # bastaki bos satirlar da bu bloga ait
                x["block"] = 0
        blocks[-1]["lines"].append(n)
        lines.append({"i": i, "kind": "line", "text": ln, "header": "", "block": len(blocks) - 1, "n": n})
        n += 1
    return {"lines": lines, "blocks": blocks, "count": n}


def assign_blocks(blocks: list[dict[str, Any]], sections: list[dict[str, Any]]) -> list[int]:
    """Her blok icin bolum indeksi (-1 = bolum yok). Basligi olan blok, imlecten itibaren adi eslesen ilk
    bolume; eslesen yoksa imlecteki bolume baglanir. Basliksiz blok imlecteki bolume (Intro ise atlanir)."""
    secs = sections or []
    out: list[int] = []
    cur = 0
    for b in blocks or []:
        base = str(b.get("base") or "")
        if cur >= len(secs):
            out.append(-1)
            continue
        if base:
            hit = next((k for k in range(cur, len(secs)) if section_base(secs[k].get("name")) == base), -1)
            k = hit if hit >= 0 else cur
        else:
            k = cur
            if section_base(secs[k].get("name")) == "intro" and k + 1 < len(secs):
                k += 1
        out.append(k)
        cur = k + 1
    return out


def resolve_anchors(anchors: Any, texts: list[str]) -> dict[int, float]:
    """Kayitli capalar ({line, t, text}) -> {satir sirasi: zaman}. Satir metni degistiyse/kaydiysa ayni metnin
    en yakin kopyasi aranir; bulunamazsa sira numarasi kullanilir (metin duzeltilmis olabilir)."""
    out: dict[int, float] = {}
    n = len(texts)
    for a in anchors or []:
        if not isinstance(a, dict):
            continue
        try:
            li = int(a.get("line"))
        except (TypeError, ValueError):
            continue
        t = _f(a.get("t"), -1.0)
        if t < 0:
            continue
        txt = str(a.get("text") or "")
        k = li
        if txt and not (0 <= li < n and texts[li] == txt):
            best = -1
            for j in range(n):
                if texts[j] == txt and (best < 0 or abs(j - li) < abs(best - li)):
                    best = j
            k = best if best >= 0 else li
        if 0 <= k < n:
            out[k] = _r6(t)
    return out


def line_times(text: Any, sections: list[dict[str, Any]] | None, bpm: float, bars_per_line: float = 1.0,
               anchors: Any = None, beats_per_bar: int = 4, start: Any = None) -> list[dict[str, Any]]:
    """Soz satirlarinin zaman cizelgesi zamanlari: [{n, t, block, section, anchored}] (n sirali).
    start (R3, 'Sozler buradan baslar'): verilirse satirli ILK blok bu noktadan baslar (bolume bagliysa da);
    sonraki bloklar kendi bolumlerine bagli kalir, bolumsuz bloklar oncekinin ardindan akar. Elle capalar
    (anchors) her zaman onceliklidir."""
    p = parse_lyrics(text)
    secs = list(sections or [])
    bpm = _f(bpm, 120.0)
    bpm = bpm if bpm > 0 else 120.0
    bpb = max(1, int(_f(beats_per_bar, 4) or 4))
    bar = 60.0 / bpm * bpb
    g_bpl = _f(bars_per_line, 1.0)
    g_bpl = g_bpl if g_bpl > 0 else 1.0
    texts = [x["text"] for x in p["lines"] if x["kind"] == "line"]
    anc = resolve_anchors(anchors, texts)
    owner = assign_blocks(p["blocks"], secs)
    st = lyric_start(start)
    first = next((i for i, b in enumerate(p["blocks"]) if b["lines"]), -1)
    out: list[dict[str, Any]] = []
    prev_end = 0.0
    for bi, b in enumerate(p["blocks"]):
        k = owner[bi] if bi < len(owner) else -1
        sec = secs[k] if 0 <= k < len(secs) else None
        bpl = _f(sec.get("bars_per_line"), 0.0) if sec else 0.0
        step = bar * (bpl if bpl > 0 else g_bpl)
        if bi == first and st is not None:
            start = st
        else:
            start = _f(sec.get("start"), 0.0) if sec else prev_end
        base_t, base_j = start, 0
        t = start
        for j, n in enumerate(b["lines"]):
            if n in anc:
                base_t, base_j = anc[n], j
            t = base_t + (j - base_j) * step
            out.append({"n": n, "t": _r6(t), "block": bi, "section": k, "anchored": n in anc})
        prev_end = (t + step) if b["lines"] else start
    out.sort(key=lambda x: x["n"])
    return out


def lyric_start(v: Any) -> float | None:
    """lyric_times.start dogrulamasi: sonlu ve >= 0 ise sn (r6), degilse None (= baslangic isareti yok)."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    x = _f(v, -1.0)
    return _r6(x) if x >= 0 else None


def sync_line(anchors: Any, n: int, t: float, text: str = "") -> list[dict[str, Any]]:
    """Satir n'yi t anina sabitler (varsa eski capasi degisir). Yeni liste, satir sirasina gore."""
    n = int(n)
    keep = [dict(a) for a in (anchors or []) if isinstance(a, dict) and int(_f(a.get("line"), -1)) != n]
    keep.append({"line": n, "t": _r6(max(0.0, _f(t))), "text": str(text or "")})
    keep.sort(key=lambda a: int(_f(a.get("line"), 0)))
    return keep


def unsync_line(anchors: Any, n: int) -> list[dict[str, Any]]:
    return [dict(a) for a in (anchors or []) if isinstance(a, dict) and int(_f(a.get("line"), -1)) != int(n)]


def active_line(times: list[dict[str, Any]], t: float) -> int:
    """Calma konumunda aktif satirin n'si (zamani <= t olan en gec satir; esitlikte buyuk n). Yoksa -1."""
    t = _f(t)
    best, best_t = -1, -1e18
    for x in times or []:
        xt = _f(x.get("t"))
        if xt <= t + 1e-9 and (xt > best_t or (xt == best_t and int(x["n"]) > best)):
            best, best_t = int(x["n"]), xt
    return best
