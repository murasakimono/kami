"""Kami Echo: evrensel geri al (undo) günlüğü.

Yikici/degistirici dosya islemlerini (tasi, yeniden adlandir) JSONL günlüğüne
kaydeder; tek tikla geri almayi saglar. Günlük uygulama yeniden baslasa da kalir.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
import uuid
from typing import Any

log = logging.getLogger(__name__)


class OpLog:
    """Dosya islemi günlüğü + geri al. 'move'/'rename' -> dst'yi src'ye geri tasir."""

    def __init__(self, path: str):
        self.path = path
        self._lock = threading.Lock()

    def record(self, op: str, src: str, dst: str = "") -> dict[str, Any]:
        entry = {"id": uuid.uuid4().hex[:12], "ts": time.time(), "op": op, "src": src, "dst": dst}
        try:
            with self._lock:
                with open(self.path, "a", encoding="utf-8") as f:
                    f.write(json.dumps(entry, ensure_ascii=False) + "\n")
        except OSError:
            log.debug("Echo kaydi yazilamadi: %s", self.path)
        return entry

    def list(self, n: int = 50) -> list[dict[str, Any]]:
        try:
            with self._lock:
                with open(self.path, encoding="utf-8") as f:
                    lines = f.read().splitlines()
        except OSError:
            return []
        out: list[dict[str, Any]] = []
        for ln in lines[-n:]:
            try:
                e = json.loads(ln)
                if isinstance(e, dict):
                    out.append(e)
            except ValueError:
                continue
        return out

    def undo(self, eid: str) -> dict[str, Any]:
        entry = next((e for e in self.list(200) if e.get("id") == eid), None)
        if not entry:
            return {"ok": False, "error": "not_found"}
        op, src, dst = entry.get("op"), entry.get("src", ""), entry.get("dst", "")
        try:
            if op in ("move", "rename"):
                if not os.path.exists(dst):
                    return {"ok": False, "error": "dst_gone"}
                os.makedirs(os.path.dirname(src), exist_ok=True)
                if os.path.exists(src):
                    src = _bump(src)
                os.replace(dst, src)
            else:
                return {"ok": False, "error": "unsupported"}
        except OSError as exc:
            return {"ok": False, "error": str(exc)[:120]}
        self.record("undo", src, dst)
        return {"ok": True, "src": src}


def _bump(path: str) -> str:
    base, ext = os.path.splitext(path)
    n = 1
    while os.path.exists(f"{base} ({n}){ext}"):
        n += 1
    return f"{base} ({n}){ext}"
