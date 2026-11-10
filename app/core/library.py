"""Kami Player kutuphanesi: klasor tarama, dizi/sezon/bolum gruplama, oynatma listeleri (data/playlists.json).

Tarama hafif: sadece dosya adlari ve boyut; ffprobe yok. Dizi tanima dosya adindan:
  S01E05, 1x05, "Ep 05", "Episode 5", "Bolum 5", "- 05 -" (anime), "[05]"
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from pathlib import Path
from typing import Any

from app.core.media_server import AUDIO_EXT, VIDEO_EXT

log = logging.getLogger(__name__)

MAX_FILES = 8000
_SXE = re.compile(r"[Ss](\d{1,2})[ ._-]?[Ee](\d{1,3})|(\d{1,2})x(\d{2,3})")
_EP = re.compile(r"(?:\b(?:ep|episode|bolum|bölüm|e)\s*\.?\s*(\d{1,3})\b)|(?:\s-\s(\d{1,3})(?:v\d)?(?:\s|$|\[|\())|(?:\[(\d{1,3})\])", re.I)
_TAGS = re.compile(r"\[[^\]]*\]|\([^)]*\)|\{[^}]*\}")
_JUNK = re.compile(r"\b(1080p|720p|2160p|480p|4k|x264|x265|h\.?264|h\.?265|hevc|aac|ac3|flac|web[- ]?dl|webrip|bluray|bdrip|hdtv|dual|multi|10bit|8bit)\b.*$", re.I)


def natural_key(s: str) -> list:
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def parse_name(stem: str) -> dict[str, Any]:
    """'[Sub] Frieren - 05 [1080p]' -> {'series': 'Frieren', 'season': 1, 'episode': 5}"""
    m = _SXE.search(stem)
    season = episode = 0
    cut = len(stem)
    if m:
        season = int(m.group(1) or m.group(3))
        episode = int(m.group(2) or m.group(4))
        cut = m.start()
    else:
        clean = _TAGS.sub(" ", stem).replace("_", " ")
        m2 = _EP.search(clean + " ")
        if m2:
            episode = int(next(g for g in m2.groups() if g))
            season = 1
            series = clean[:m2.start()]
            series = re.sub(r"[\s._-]+", " ", _JUNK.sub("", series)).strip(" -.")
            return {"series": series, "season": season, "episode": episode}
        m3 = re.search(r"\[(\d{1,3})(?:v\d)?\]", stem)   # [03] (koseli parantezli bolum numarasi)
        if m3:
            series = re.sub(r"[\s._-]+", " ", _JUNK.sub("", _TAGS.sub(" ", stem[:m3.start()]))).strip(" -.")
            if series:
                return {"series": series, "season": 1, "episode": int(m3.group(1))}
    series = _TAGS.sub(" ", stem[:cut]).replace("_", " ")
    series = re.sub(r"[\s._-]+", " ", _JUNK.sub("", series)).strip(" -.")
    return {"series": series if episode else "", "season": season, "episode": episode}


def media_kind(p: Path) -> str:
    ext = p.suffix.lower()
    return "video" if ext in VIDEO_EXT else "audio" if ext in AUDIO_EXT else ""


def siblings(path: str) -> list[str]:
    """Ayni klasordeki ayni turden medya dosyalari, dogal sirayla (otomatik siradakiler listesi)."""
    p = Path(path)
    kind = media_kind(p)
    if not kind:
        return [str(p)]
    try:
        files = [q for q in p.parent.iterdir() if q.is_file() and media_kind(q) == kind]
    except OSError:
        return [str(p)]
    return [str(q) for q in sorted(files, key=lambda q: natural_key(q.name))]


def scan(dirs: list[str]) -> dict[str, Any]:
    items: list[dict[str, Any]] = []
    for d in dirs:
        root = Path(d)
        if not root.is_dir():
            continue
        for dp, dn, fn in os.walk(root):
            dn[:] = [x for x in dn if not x.startswith(".") and x.lower() not in ("$recycle.bin", "system volume information")]
            for name in fn:
                q = Path(dp) / name
                kind = media_kind(q)
                if not kind or name.endswith((".part", ".aria2")):
                    continue
                try:
                    st = q.stat()
                except OSError:
                    continue
                info = parse_name(q.stem) if kind == "video" else {"series": "", "season": 0, "episode": 0}
                items.append({"path": str(q), "name": q.stem, "kind": kind, "size": st.st_size, "mtime": int(st.st_mtime),
                              "folder": q.parent.name, **info})
                if len(items) >= MAX_FILES:
                    break
            if len(items) >= MAX_FILES:
                break
    # dizi: ayni seri adinda 2+ bolum
    groups: dict[str, list[dict[str, Any]]] = {}
    for it in items:
        if it["series"]:
            groups.setdefault(it["series"].lower(), []).append(it)
    series = []
    for key, eps in groups.items():
        if len(eps) < 2:
            for e in eps:
                e["series"] = ""
            continue
        eps.sort(key=lambda e: (e["season"], e["episode"], natural_key(e["name"])))
        series.append({"name": eps[0]["series"], "count": len(eps), "seasons": sorted({e["season"] for e in eps}),
                       "paths": [e["path"] for e in eps], "mtime": max(e["mtime"] for e in eps)})
    series.sort(key=lambda s: -s["mtime"])
    return {"items": items, "series": series, "truncated": len(items) >= MAX_FILES}


class Playlists:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def _load(self) -> dict[str, list[str]]:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return {str(k): [str(x) for x in v] for k, v in data.items() if isinstance(v, list)}
        except (OSError, ValueError, AttributeError):
            return {}

    def all(self) -> dict[str, list[str]]:
        with self._lock:
            return self._load()

    def save(self, name: str, paths: list[str]) -> dict[str, list[str]]:
        name = (name or "").strip()[:80]
        with self._lock:
            data = self._load()
            if name:
                data[name] = [str(p) for p in paths][:2000]
            self._write(data)
            return data

    def delete(self, name: str) -> dict[str, list[str]]:
        with self._lock:
            data = self._load()
            data.pop(name, None)
            self._write(data)
            return data

    def _write(self, data: dict[str, list[str]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)
