"""Site kurallari (Asama 6c): ornek "YouTube sarki -> MP3 320 + Muzik klasoru".

Kural: {id, name, enabled, host, music, ext, format, audio_kbps, quality, folder, auto}
  host   : "youtube.com" (alt alan adlari dahil; bos = her site)
  music  : True -> sadece muzik (YouTube Music linki ya da yt-dlp kategorisi "Music")
  ext    : "zip,rar" (dosya indirmeleri icin uzanti; bos = hepsi)
  format : "" | mp3 | mp4 ; audio_kbps: 0|128..320 ; quality: ""|best|1080|720...
  folder : "" | kategori (music/video/archive/program/document/other) | mutlak klasor yolu
  auto   : True -> medya secim penceresini atla, dogrudan indir
Ilk eslesen kural uygulanir (liste sirasi = oncelik).
"""
from __future__ import annotations

import os
import uuid
from typing import Any
from urllib.parse import urlparse

CATEGORIES = ("music", "video", "archive", "program", "document", "other")
DEFAULT_RULES = [{"id": "yt-music", "name": "YouTube şarkı → MP3 320 + Müzik", "enabled": True,
                  "host": "youtube.com", "music": True, "ext": "", "format": "mp3", "audio_kbps": 320,
                  "quality": "", "folder": "music", "auto": False}]


def clean_rule(r: dict[str, Any]) -> dict[str, Any]:
    fmt = str(r.get("format") or "")
    folder = str(r.get("folder") or "").strip()
    if folder and folder not in CATEGORIES and not os.path.isabs(folder):
        raise ValueError("rule_folder")
    kbps = int(r.get("audio_kbps") or 0)
    return {
        "id": str(r.get("id") or uuid.uuid4().hex[:8])[:16],
        "name": str(r.get("name") or "")[:80],
        "enabled": bool(r.get("enabled", True)),
        "host": str(r.get("host") or "").strip().lower().removeprefix("www.").strip("/")[:120],
        "music": bool(r.get("music")),
        "ext": ",".join(x.strip().lower().lstrip(".") for x in str(r.get("ext") or "").split(",") if x.strip()),
        "format": fmt if fmt in ("mp3", "mp4") else "",
        "audio_kbps": kbps if kbps in (0, 128, 192, 256, 320) else 320,
        "quality": str(r.get("quality") or ""),
        "folder": folder,
        "auto": bool(r.get("auto")),
    }


def _host_ok(rule_host: str, *urls: str) -> bool:
    if not rule_host:
        return True
    for u in urls:
        h = (urlparse(u or "").hostname or "").lower()
        if h and (h == rule_host or h.endswith("." + rule_host)):
            return True
    return False


def is_music(url: str, info: dict[str, Any] | None) -> bool:
    host = (urlparse(url or "").hostname or "").lower()
    if host == "music.youtube.com":
        return True
    cats = [str(c).lower() for c in (info or {}).get("categories") or []]
    return "music" in cats


def match(rules: list[dict[str, Any]], url: str, page_url: str = "", *, media: bool,
          info: dict[str, Any] | None = None, filename: str = "") -> dict[str, Any] | None:
    for r in rules or []:
        if not r.get("enabled"):
            continue
        if not _host_ok(r.get("host", ""), url, page_url):
            continue
        if r.get("music") and not (media and is_music(url, info)):
            continue
        if r.get("ext"):
            if media:
                continue
            ext = os.path.splitext(filename or urlparse(url).path)[1].lower().lstrip(".")
            if ext not in r["ext"].split(","):
                continue
        if media and not (r.get("format") or r.get("folder")):
            continue
        return r
    return None


def media_options(rule: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    if rule.get("format"):
        out["format"] = rule["format"]
    if rule.get("audio_kbps"):
        out["audio_kbps"] = rule["audio_kbps"]
    if rule.get("quality"):
        out["quality"] = rule["quality"]
    return out


def folder_path(rule: dict[str, Any], base_dir: str) -> str:
    """Kuralin klasoru -> mutlak yol ('' = varsayilan kategori klasoru)."""
    from app.core.categories import CATEGORY_FOLDERS
    f = rule.get("folder") or ""
    if not f:
        return ""
    if f in CATEGORIES:
        return os.path.join(base_dir, CATEGORY_FOLDERS.get(f, f))
    return f
