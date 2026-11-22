"""Kami "For You" Radyo: dinleme geçmişinden kişisel, tekrar etmeyen karışım kuyruğu.

library.scan() çıktısı + scrobble geçmişi ({title, artist, ts}) ile "sevilen"
parçaları öne çıkarır, çeşitlilik için hafif rastgelelik katar, tekrar etmez.
"""
from __future__ import annotations

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Any

from app.core import media_meta

log = logging.getLogger(__name__)


def build_mix(items: list[dict[str, Any]], *, history: list[dict[str, Any]] | None = None,
              n: int = 20, exclude: set[str] | None = None, seed: Any = None) -> list[dict[str, Any]]:
    """Kişisel 'For You' kuyruğu döndürür.

    items:  library.scan(dirs)["items"] (path, name, kind, ...).
    history: scrobble geçmişi [{title, artist, ts}]; çok/geç dinlenen öne çıkar.
    exclude: kuyrukta olan yollar (tekrar etmez).
    """
    rng = random.Random(seed)
    ex = exclude or set()
    now = time.time()
    w: dict[tuple[str, str], float] = {}
    for e in history or []:
        t = (e.get("title") or "").strip().lower()
        if not t:
            continue
        a = (e.get("artist") or "").strip().lower()
        age_days = max(0.0, now - int(e.get("ts") or 0)) / 86400.0
        w[(a, t)] = w.get((a, t), 0.0) + (1.0 + max(0.0, 1.0 - age_days / 30.0) * 2.0)

    scored: list[tuple[float, dict[str, Any]]] = []
    for it in items:
        path = it.get("path", "")
        if path in ex or not path:
            continue
        artist, title = media_meta.split_artist_title(it.get("name", ""))
        a, t = artist.strip().lower(), title.strip().lower()
        like = w.get((a, t), 0.0)
        if not like and t:
            like = max((v for (aa, tt), v in w.items() if tt == t), default=0.0)
        scored.append((like + rng.random() * 0.5, it))
    scored.sort(key=lambda x: -x[0])
    return [it for _, it in scored[:max(0, n)]]


def bpm_key(track: dict[str, Any], ffmpeg: str = "") -> int:
    """Tempo kovası (5'in katı; 0 = bilinmiyor). Başarısızsa 0."""
    try:
        from app.core import kami_beat
        b = kami_beat.analyze_bpm(track["path"], ffmpeg)
        return int(round(b / 5.0)) * 5 if b and b > 0 else 0
    except Exception:
        return 0


_CAMELOT_MAP: dict[str, tuple[int, str]] = {
    "abm": (1, "A"), "g#m": (1, "A"), "b": (1, "B"),
    "ebm": (2, "A"), "d#m": (2, "A"), "f#": (2, "B"), "gb": (2, "B"),
    "bbm": (3, "A"), "a#m": (3, "A"), "db": (3, "B"), "c#": (3, "B"),
    "fm": (4, "A"), "ab": (4, "B"), "g#": (4, "B"),
    "cm": (5, "A"), "eb": (5, "B"), "d#": (5, "B"),
    "gm": (6, "A"), "bb": (6, "B"), "a#": (6, "B"),
    "dm": (7, "A"), "f": (7, "B"),
    "am": (8, "A"), "c": (8, "B"),
    "em": (9, "A"), "g": (9, "B"),
    "bm": (10, "A"), "d": (10, "B"),
    "f#m": (11, "A"), "gbm": (11, "A"), "a": (11, "B"),
    "c#m": (12, "A"), "dbm": (12, "A"), "e": (12, "B"),
}


def _to_camelot(key_name: str) -> tuple[int, str] | None:
    s = str(key_name or "").strip().lower().replace("minor", "m").replace("major", "").replace(" ", "")
    return _CAMELOT_MAP.get(s)


def harmonic_score(bpm_a: float, key_a: str, bpm_b: float, key_b: str) -> float:
    """Iki parca arasi BPM (yari/cift tempo dahil) + Camelot ton uyumu skoru (0.0..1.0)."""
    bpm_s = 0.5
    if bpm_a > 0 and bpm_b > 0:
        diffs = [abs(bpm_a - bpm_b), abs(bpm_a * 2 - bpm_b), abs(bpm_a - bpm_b * 2)]
        best = min(diffs)
        bpm_s = max(0.0, 1.0 - (best / 24.0))

    ca, cb = _to_camelot(key_a), _to_camelot(key_b)
    key_s = 0.45
    if ca and cb:
        num_d = min((ca[0] - cb[0]) % 12, (cb[0] - ca[0]) % 12)
        if ca == cb:
            key_s = 1.0
        elif ca[1] == cb[1] and num_d == 1:
            key_s = 0.85
        elif ca[0] == cb[0] and ca[1] != cb[1]:
            key_s = 0.85
        elif num_d <= 2:
            key_s = 0.55
        else:
            key_s = 0.15
    return round(bpm_s * 0.65 + key_s * 0.35, 4)


def _analyze_track_cached(path: str, ffmpeg: str, cache: dict[str, Any]) -> tuple[float, str]:
    norm = os.path.normcase(os.path.abspath(path))
    try:
        mt = os.path.getmtime(path)
    except OSError:
        return (0.0, "")
    hit = cache.get(norm)
    if isinstance(hit, dict) and abs(float(hit.get("mtime") or 0) - mt) < 1.0 and hit.get("bpm"):
        return (float(hit.get("bpm") or 0), str(hit.get("key") or ""))
    bpm = 0.0
    key = ""
    try:
        from app.core import kami_beat
        bpm = float(kami_beat.analyze_bpm(path, ffmpeg) or 0.0)
        kinfo = kami_beat.detect_key(path, ffmpeg) or {}
        key = str(kinfo.get("key") or "")
    except Exception:
        pass
    cache[norm] = {"bpm": round(bpm, 1), "key": key, "mtime": mt}
    return (bpm, key)


def build_autodj_mix(
    items: list[dict[str, Any]],
    *,
    n: int = 20,
    ffmpeg: str = "",
    seed_path: str = "",
    cache_path: Path | None = None,
) -> list[dict[str, Any]]:
    """Gercek Auto-DJ: parcalari harmonik BPM + ton gecis uyumu ile siralar."""
    audio = [dict(it) for it in items if it.get("path") and (it.get("kind", "audio") == "audio")]
    if not audio:
        return []

    cache: dict[str, Any] = {}
    if cache_path and cache_path.is_file():
        try:
            cache = json.loads(cache_path.read_text(encoding="utf-8"))
        except Exception:
            cache = {}

    pool: list[dict[str, Any]] = []
    # Ilk analiz maliyetini sinirla (en fazla 45 aday parca)
    for it in audio[:45]:
        bpm, key = _analyze_track_cached(it["path"], ffmpeg, cache)
        it["bpm"] = round(bpm, 1) if bpm else 0
        it["key"] = key
        pool.append(it)

    if cache_path:
        try:
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(cache, ensure_ascii=False), encoding="utf-8")
        except Exception:
            log.debug("bpm cache yazilamadi", exc_info=True)

    seed_norm = os.path.normcase(os.path.abspath(seed_path)) if seed_path else ""
    start_idx = 0
    if seed_norm:
        for idx, it in enumerate(pool):
            if os.path.normcase(os.path.abspath(it["path"])) == seed_norm:
                start_idx = idx
                break

    ordered: list[dict[str, Any]] = []
    cur = pool.pop(start_idx)
    cur["transition_score"] = 100
    ordered.append(cur)

    limit = max(1, min(n, len(pool) + 1))
    while pool and len(ordered) < limit:
        best_i = 0
        best_sc = -1.0
        for i, cand in enumerate(pool):
            sc = harmonic_score(cur.get("bpm") or 0, cur.get("key") or "", cand.get("bpm") or 0, cand.get("key") or "")
            if sc > best_sc:
                best_sc = sc
                best_i = i
        nxt = pool.pop(best_i)
        nxt["transition_score"] = int(round(best_sc * 100))
        ordered.append(nxt)
        cur = nxt

    return ordered
