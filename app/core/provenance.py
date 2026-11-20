"""Kami Provenance: indirilen dosyanin kanitlanabilir kaynak kaydi.

Her tamamlanan dosyanin yanina <dosya>.kami.json sidecar yazilir:
kaynak URL, zaman, boyut, sha256 (varsa), referrer, kategori. Sidecar
tasinabilir ve bilgi panelinden okunabilir; "bu dosya nereden geldi, güvenli mi?"
sorusunun cevabini saklar. Yazma hatasi indirmeyi ASLA bozmaz.
"""
from __future__ import annotations

import json
import logging
import os
import time
from typing import Any

log = logging.getLogger(__name__)
SIDECAR_SUFFIX = ".kami.json"
_SCHEMA = 1


def sidecar_path(path: str) -> str:
    return path + SIDECAR_SUFFIX


def write(path: str, *, url: str = "", size: int = 0, sha256: str = "", referer: str = "",
          page_url: str = "", source: str = "", category: str = "", extra: dict[str, Any] | None = None) -> bool:
    """Dosyanin yanina kayit yazar; basarisizsa False doner (indirmeyi bozmaz)."""
    try:
        if not path or not os.path.isfile(path):
            return False
        st = os.stat(path)
        ex = extra or {}
        rec: dict[str, Any] = {
            "v": _SCHEMA,
            "name": os.path.basename(path),
            "url": url or "",
            "size": int(size or st.st_size),
            "mtime": st.st_mtime,
            "ts": time.time(),
            "sha256": sha256 or ex.get("sha256") or "",
            "referer": referer or "",
            "page_url": page_url or "",
            "source": source or "",
            "category": category or "",
        }
        tmp = path + SIDECAR_SUFFIX + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, indent=2)
        os.replace(tmp, sidecar_path(path))
        return True
    except (OSError, ValueError, TypeError):
        log.debug("Provenance yazilamadi: %s", path)
        return False


def read(path: str) -> dict[str, Any] | None:
    """Sidecar'i okur; yoksa/bozuksa None."""
    try:
        with open(sidecar_path(path), encoding="utf-8") as f:
            rec = json.load(f)
        return rec if isinstance(rec, dict) else None
    except (OSError, ValueError):
        return None
