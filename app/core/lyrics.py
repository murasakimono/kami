"""Sarki sozu (defter 12, ONAY 1).

Sira (05.11 karari):
1) LRCLIB senkron soz -> yanina .lrc + MP3'e USLT (Dopamine okur).
2) LRCLIB duz metin (plainLyrics; zaman damgasiz ama TAM soz) -> yanina .txt + USLT.
3) Yoksa: UVR5 vokal + Whisper ile yaziya dokme (aitools "lyrics" isi; iki arac kuruluysa) -> .lrc,
   "yapay zeka ile cikarildi, hatali olabilir" etiketiyle.
4) Genius RESMI API ile sarki sayfasi linki (token varsa) + AZLyrics arama linki. Sayfalardan metin KAZINMAZ.
Ek: "Sozu yapistir" - kullanicinin elle kopyaladigi soz gomulur + .lrc/.txt yazilir.
"""
from __future__ import annotations

import logging
import os
import re
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


LRC_LINE = re.compile(r"^\s*\[\d{1,3}:\d{2}(?:[.:]\d{1,3})?\]")
AI_NOTE = "Yapay zekâ ile çıkarıldı, hatalı olabilir / AI transcribed, may contain errors"


def is_lrc(text: str) -> bool:
    lines = [x for x in (text or "").splitlines() if x.strip()]
    return bool(lines) and sum(1 for x in lines if LRC_LINE.match(x)) >= max(1, len(lines) // 2)


def srt_to_lrc(srt: str) -> str:
    """Whisper SRT -> LRC satirlari ([mm:ss.xx] metin)."""
    out = []
    for block in re.split(r"\n\s*\n", (srt or "").strip()):
        lines = block.strip().splitlines()
        tline = next((i for i, x in enumerate(lines) if "-->" in x), None)
        if tline is None:
            continue
        m = re.match(r"(\d+):(\d+):(\d+)[,.](\d+)", lines[tline].strip())
        text = " ".join(x.strip() for x in lines[tline + 1:] if x.strip())
        if not m or not text:
            continue
        h, mi, se, ms = (int(g) for g in m.groups())
        total = h * 3600 + mi * 60 + se + ms / 1000
        out.append(f"[{int(total // 60):02d}:{total % 60:05.2f}]{text}")
    return "\n".join(out)


def write_lyrics(path: str, text: str, artist: str = "", title: str = "", embed: bool = True,
                 ai: bool = False) -> dict[str, Any]:
    """Soz metnini dosyanin yanina yaz (.lrc senkronsa, degilse .txt) + MP3'e USLT olarak gom."""
    from app.core import media_meta
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return {"lyrics": "none"}
    synced = is_lrc(text)
    base = os.path.splitext(path)[0]
    head = "".join(f"[{k}:{v}]\n" for k, v in (("ar", artist), ("ti", title)) if v)
    if ai:
        head += f"[re:Kami AI]\n[by:{AI_NOTE}]\n"
    if synced:
        side = base + ".lrc"
        body = head + text + "\n"
    else:
        side = base + ".txt"
        body = (f"({AI_NOTE})\n\n" if ai else "") + text + "\n"
    with open(side, "w", encoding="utf-8", newline="\n") as f:
        f.write(body)
    if embed and path.lower().endswith(".mp3"):
        media_meta.write_mp3_tags(path, lyrics=(f"({AI_NOTE})\n" if ai else "") + text)
    kind = "ai" if ai else ("synced" if synced else "plain")
    return {"lyrics": kind, "lrc" if synced else "txt": side}


def paste(path: str, text: str, title_hint: str = "", embed: bool = True) -> dict[str, Any]:
    """Kullanicinin elle kopyaladigi soz (Genius/AZLyrics'ten): gomulur + .lrc/.txt yazilir. Kazima yok."""
    from app.core import media_meta
    g = media_meta.guess(path, title_hint)
    return {**write_lyrics(path, text, g["artist"], g["title"], embed), "artist": g["artist"], "title": g["title"]}


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
    if found:   # 1) senkron, 2) duz metin (zaman damgasiz ama tam soz)
        out.update(write_lyrics(path, found["synced"] or found["plain"], artist, title, embed))
        return out
    url = genius_search(artist, title, genius_token(), session)
    if url:
        out["links"]["genius_song"] = url
    return out
