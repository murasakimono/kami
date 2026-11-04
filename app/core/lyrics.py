"""Sarki sozu (defter 12, ONAY 1).

1) LRCLIB (ucretsiz acik API, zaman damgali): /api/get (sanatci+baslik+sure) -> yoksa /api/search.
   Senkron soz -> yanina .lrc + MP3'e USLT olarak gomulur (Pure Music okur). Sadece duz soz varsa .txt yerine
   yine USLT (zaman damgasiz).
2) LRCLIB'de yoksa: Genius RESMI API ile arama (token varsa) -> sarki sayfasi linki. Metin Genius/AZLyrics
   sayfalarindan KAZINMAZ; arayuzde "Genius'ta ac / AZLyrics'te ara" linkleri.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable
from urllib.parse import quote_plus

import requests

log = logging.getLogger(__name__)

LRCLIB = "https://lrclib.net/api"
GENIUS_API = "https://api.genius.com/search"


def _ua() -> str:
    from app.core.extras import APP_VERSION, GITHUB_REPO
    return f"Kami/{APP_VERSION} (https://github.com/{GITHUB_REPO})"


def search_links(artist: str, title: str) -> dict[str, str]:
    q = quote_plus(f"{artist} {title}".strip())
    return {"genius": f"https://genius.com/search?q={q}",
            "azlyrics": f"https://search.azlyrics.com/search.php?q={q}"}


def lrclib_find(artist: str, title: str, album: str = "", duration: float = 0,
                session: requests.Session | None = None) -> dict[str, Any] | None:
    """-> {synced, plain, instrumental, id} ya da None."""
    s = session or requests.Session()
    h = {"User-Agent": _ua()}
    if artist and title:
        params: dict[str, Any] = {"artist_name": artist, "track_name": title}
        if album:
            params["album_name"] = album
        if duration:
            params["duration"] = int(round(duration))
        try:
            r = s.get(f"{LRCLIB}/get", params=params, headers=h, timeout=15)
            if r.status_code == 200:
                return _pick(r.json())
        except (requests.RequestException, ValueError):
            log.warning("LRCLIB get hatasi", exc_info=True)
    try:   # serbest arama: sureye en yakin, senkron olan once
        params = {"track_name": title, "artist_name": artist} if artist else {"q": title}
        r = s.get(f"{LRCLIB}/search", params=params, headers=h, timeout=15)
        if r.status_code != 200:
            return None
        hits = [x for x in (r.json() or []) if isinstance(x, dict) and (x.get("syncedLyrics") or x.get("plainLyrics"))]
    except (requests.RequestException, ValueError):
        log.warning("LRCLIB search hatasi", exc_info=True)
        return None
    if not hits:
        return None
    if duration:
        hits = [x for x in hits if abs(float(x.get("duration") or 0) - duration) <= 8] or []
        if not hits:
            return None
    hits.sort(key=lambda x: (not x.get("syncedLyrics"), abs(float(x.get("duration") or 0) - (duration or 0))))
    return _pick(hits[0])


def _pick(d: dict[str, Any]) -> dict[str, Any] | None:
    if not isinstance(d, dict):
        return None
    if d.get("instrumental"):
        return {"synced": "", "plain": "", "instrumental": True, "id": d.get("id")}
    if not (d.get("syncedLyrics") or d.get("plainLyrics")):
        return None
    return {"synced": d.get("syncedLyrics") or "", "plain": d.get("plainLyrics") or "",
            "instrumental": False, "id": d.get("id")}


def genius_search(artist: str, title: str, token: str, session: requests.Session | None = None) -> str:
    """Genius resmi API: en iyi eslesen sarki sayfasinin URL'si (metin cekilmez). Yoksa ''."""
    if not token:
        return ""
    s = session or requests.Session()
    try:
        r = s.get(GENIUS_API, params={"q": f"{artist} {title}".strip()},
                  headers={"Authorization": f"Bearer {token}", "User-Agent": _ua()}, timeout=15)
        if r.status_code != 200:
            log.info("Genius arama: HTTP %s", r.status_code)
            return ""
        hits = (r.json().get("response") or {}).get("hits") or []
    except (requests.RequestException, ValueError, AttributeError):
        log.warning("Genius arama hatasi", exc_info=True)
        return ""
    t = title.lower()
    for h in hits:
        res = h.get("result") or {}
        if h.get("type") == "song" and res.get("url", "").startswith("https://genius.com/"):
            if t and t[:12] in (res.get("title") or "").lower():
                return res["url"]
    for h in hits:
        res = h.get("result") or {}
        if h.get("type") == "song" and res.get("url", "").startswith("https://genius.com/"):
            return res["url"]
    return ""


def fetch_for_file(path: str, title_hint: str = "", embed: bool = True,
                   genius_token: Callable[[], str] = lambda: "",
                   session: requests.Session | None = None) -> dict[str, Any]:
    """Dosya icin soz bul: .lrc yaz + gom. Sonuc download.extra'ya yazilacak ozet:
    {lyrics: synced|plain|instrumental|none, lrc: yol, links: {genius, azlyrics, genius_song}}"""
    from app.core import media_meta
    g = media_meta.guess(path, title_hint)
    artist, title = g["artist"], g["title"]
    out: dict[str, Any] = {"lyrics": "none", "artist": artist, "title": title,
                           "links": search_links(artist, title)}
    if not title:
        return out
    found = lrclib_find(artist, title, g.get("album", ""), g.get("duration", 0), session)
    if found and found["instrumental"]:
        out["lyrics"] = "instrumental"
        return out
    if found:
        text = found["synced"] or found["plain"]
        out["lyrics"] = "synced" if found["synced"] else "plain"
        if found["synced"]:
            lrc = os.path.splitext(path)[0] + ".lrc"
            head = "".join(f"[{k}:{v}]\n" for k, v in (("ar", artist), ("ti", title)) if v)
            with open(lrc, "w", encoding="utf-8", newline="\n") as f:
                f.write(head + found["synced"].strip() + "\n")
            out["lrc"] = lrc
        if embed and path.lower().endswith(".mp3"):
            media_meta.write_mp3_tags(path, lyrics=text)
        return out
    url = genius_search(artist, title, genius_token(), session)
    if url:
        out["links"]["genius_song"] = url
    return out
