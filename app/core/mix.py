"""Kami "For You" Radyo: dinleme geçmişinden kişisel, tekrar etmeyen karışım kuyruğu.

library.scan() çıktısı + scrobble geçmişi ({title, artist, ts}) ile "sevilen"
parçaları öne çıkarır, çeşitlilik için hafif rastgelelik katar, tekrar etmez.
"""
from __future__ import annotations

import random
import time
from typing import Any

from app.core import media_meta


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
