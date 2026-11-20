"""Kami Ghost-Resume: ölü indirme için boyut/hash eşleşmeli çapraz kaynak bulucu.

İndirme %N'de ölürse ve kaynak link de ölürse, aynı içeriği (boyut/hash) başka
kaynaktan bulup kaldığı yerden devam etmeyi sağlar.
- Ayna (mirrors.find): hızlı (~3 sn), aynı içeriğin aynası — en güvenilir.
- Avcı (kami_hunter.search): yavaş, ada göre kayıp medya — yalnızca istenirse.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


def find_mirrors(url: str, headers: dict | None = None, limit: int = 6) -> list[dict[str, Any]]:
    """Aynı dosyanın ayna adresleri (SourceForge/Metalink). [{'url','source':'mirror'}]"""
    from app.core import mirrors
    try:
        return [{"url": u, "source": "mirror"} for u in mirrors.find(url, headers=headers, limit=limit)]
    except Exception:
        log.debug("Ayna arama basarisiz: %s", url)
        return []


def find_by_name(filename: str) -> list[dict[str, Any]]:
    """Kayıp medya araması (Internet Archive vb.). [{'url','title','source':'hunter'}]"""
    from app.core import kami_hunter
    try:
        res = kami_hunter.search(filename, cluster=False)
        return [{"url": it.get("url", ""), "title": it.get("title", ""), "source": "hunter"}
                for it in (res.get("items") or []) if it.get("url")]
    except Exception:
        log.debug("Hunter arama basarisiz: %s", filename)
        return []


def rank(candidates: list[dict[str, Any]], *, size: int = 0, sha256: str = "") -> list[dict[str, Any]]:
    """Boyut/hash eşleşmesine göre sırala (eşleşenler önce; ayna güvenilir)."""
    def score(c: dict[str, Any]) -> int:
        s = 0
        if sha256 and c.get("sha256") == sha256:
            s += 1000
        if size and int(c.get("size") or 0) == size:
            s += 100
        if c.get("source") == "mirror":
            s += 10
        return s
    return sorted(candidates, key=score, reverse=True)


def find_alternates(url: str = "", *, filename: str = "", size: int = 0, sha256: str = "",
                    headers: dict | None = None, use_hunter: bool = True) -> dict[str, Any]:
    """Ölü indirme için sıralı alternatif kaynaklar döndürür (ağ çağrısı yapar)."""
    cands: list[dict[str, Any]] = []
    if url:
        cands += find_mirrors(url, headers=headers)
    if filename and use_hunter:
        cands += find_by_name(filename)
    return {"ok": True, "alternates": rank(cands, size=size, sha256=sha256)}
