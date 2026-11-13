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

import html
import logging
import os
import re
import threading
import time
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


def _web_ua() -> str:
    return "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"


def _html_to_lyrics(fragment: str) -> str:
    """HTML parcasindan <br> -> satir sonu cevirerek temiz sarki sozu cikarir."""
    s = re.sub(r"<br\s*/?>\r?\n?", "\n", fragment, flags=re.I)
    s = re.sub(r"</?(?:p|div|li|span)[^>]*>", lambda m: "\n" if m.group(0).startswith("</p") or m.group(0).startswith("</div") else "", s, flags=re.I)
    s = re.sub(r"<[^>]+>", "", s)
    s = html.unescape(s)
    lines = [line.rstrip() for line in s.splitlines()]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def genius_search(artist: str, title: str, token: str, session: requests.Session | None = None) -> str:
    """Genius resmi API: en iyi eslesen sarki sayfasinin URL'si. Token yoksa ''."""
    if not token:
        return ""
    q = f"{artist} {title}".strip()
    if not q:
        return ""
    s = session or requests.Session()
    try:
        r = s.get(GENIUS_API, params={"q": q},
                  headers={"Authorization": f"Bearer {token}", "User-Agent": _ua()}, timeout=15)
        if r.status_code != 200:
            log.info("Genius arama: HTTP %s", r.status_code)
            return ""
        hits = (r.json().get("response") or {}).get("hits") or []
    except (requests.RequestException, ValueError, AttributeError):
        log.warning("Genius arama hatasi", exc_info=True)
        return ""
    return _pick_genius_hit(hits, title)


def genius_web_search(artist: str, title: str, session: requests.Session | None = None) -> str:
    """Genius herkese acik web aramasi (token gerektirmez)."""
    q = f"{artist} {title}".strip()
    if not q:
        return ""
    s = session or requests.Session()
    hits: list[dict[str, Any]] = []
    try:
        r = s.get("https://genius.com/api/search/multi", params={"q": q},
                  headers={"User-Agent": _web_ua()}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            sections = ((data.get("response") if isinstance(data, dict) else {}) or {}).get("sections") or []
            for sec in sections:
                if isinstance(sec, dict) and sec.get("type") in ("top_hit", "song"):
                    hits.extend(sec.get("hits") or [])
    except (requests.RequestException, ValueError, AttributeError):
        log.warning("Genius web arama hatasi", exc_info=True)
    return _pick_genius_hit(hits, title)


def _pick_genius_hit(hits: list[dict[str, Any]], title: str) -> str:
    t = title.lower()
    for h in hits:
        res = h.get("result") or {}
        if h.get("type") == "song" and str(res.get("url", "")).startswith("https://genius.com/"):
            if t and t[:12] in (res.get("title") or "").lower():
                return res["url"]
    for h in hits:
        res = h.get("result") or {}
        if h.get("type") == "song" and str(res.get("url", "")).startswith("https://genius.com/"):
            return res["url"]
    return ""


class _GeniusParser:
    """data-lyrics-container='true' bloklarini ic ice <div> derinligiyle cikarir; baslik/ceviriler copunu atlar."""

    def __init__(self) -> None:
        from html.parser import HTMLParser

        class _P(HTMLParser):
            def __init__(self) -> None:
                super().__init__(convert_charrefs=True)
                self.parts: list[str] = []
                self._buf: list[str] = []
                self._in_container = False
                self._depth = 0
                self._skip_depth = 0

            def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
                ad = {k.lower(): (v or "") for k, v in attrs}
                if tag == "div" and not self._in_container and ad.get("data-lyrics-container") == "true":
                    self._in_container = True
                    self._depth = 1
                    self._buf = []
                    return
                if not self._in_container:
                    return
                if self._skip_depth:
                    if tag in ("div", "span", "p", "section"):
                        self._skip_depth += 1
                    return
                if ad.get("data-exclude-from-selection") == "true" or "LyricsHeader" in ad.get("class", ""):
                    if tag in ("div", "span", "p", "section"):
                        self._skip_depth = 1
                    return
                if tag == "div":
                    self._depth += 1
                elif tag == "br":
                    self._buf.append("\n")

            def handle_endtag(self, tag: str) -> None:
                if not self._in_container:
                    return
                if self._skip_depth:
                    if tag in ("div", "span", "p", "section"):
                        self._skip_depth -= 1
                    return
                if tag == "div":
                    self._depth -= 1
                    if self._depth <= 0:
                        txt = "".join(self._buf).strip()
                        if txt:
                            self.parts.append(txt)
                        self._in_container = False
                elif tag == "p":
                    self._buf.append("\n")

            def handle_data(self, data: str) -> None:
                if self._in_container and not self._skip_depth:
                    self._buf.append(data)

        self.parser = _P()

    def parse(self, raw_html: str) -> str:
        self.parser.feed(raw_html)
        self.parser.close()
        text = "\n\n".join(self.parser.parts)
        lines = [line.rstrip() for line in text.splitlines()]
        return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def genius_fetch_lyrics(url: str, session: requests.Session | None = None) -> str:
    """Genius sarki sayfasindan data-lyrics-container bloklarini ceker."""
    if not url or not url.startswith("https://genius.com/"):
        return ""
    s = session or requests.Session()
    try:
        r = s.get(url, headers={"User-Agent": _web_ua()}, timeout=15)
        if r.status_code != 200:
            return ""
        raw_html = r.text
    except requests.RequestException:
        log.warning("Genius sayfa cekme hatasi", exc_info=True)
        return ""
    return _GeniusParser().parse(raw_html)


_TR_ASCII = str.maketrans("çğıİöşüÇĞÖŞÜ", "cgiiosucgosu")


def _az_slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (text or "").translate(_TR_ASCII).lower())


_SESSION: requests.Session | None = None
_LAST_AZ_TS = 0.0
_AZ_LOCK = threading.Lock()
_MISS_CACHE: dict[tuple[str, str], float] = {}
_MISS_TTL = 86400.0


def _shared_session() -> requests.Session:
    global _SESSION
    if _SESSION is None:
        _SESSION = requests.Session()
    return _SESSION


def azlyrics_fetch_lyrics(artist: str, title: str, session: requests.Session | None = None) -> str:
    """AZLyrics uzerinden sarki sozu ceker (dogrudan URL + kilitli hiz siniri)."""
    global _LAST_AZ_TS
    if not artist or not title:
        return ""
    s = session or _shared_session()
    a_clean = re.sub(r"^\s*the\s+", "", artist, flags=re.I)
    urls = [
        f"https://www.azlyrics.com/lyrics/{_az_slug(a_clean)}/{_az_slug(title)}.html",
    ]
    if _az_slug(artist) != _az_slug(a_clean):
        urls.append(f"https://www.azlyrics.com/lyrics/{_az_slug(artist)}/{_az_slug(title)}.html")
    for u in urls:
        try:
            if session is None:
                with _AZ_LOCK:
                    wait = 1.2 - (time.monotonic() - _LAST_AZ_TS)
                    if wait > 0:
                        time.sleep(wait)
                    _LAST_AZ_TS = time.monotonic()
            r = s.get(u, headers={"User-Agent": _web_ua()}, timeout=15)
            if r.status_code == 200:
                text = _extract_azlyrics_html(r.text)
                if text:
                    return text
        except requests.RequestException:
            continue
    return ""


def _extract_azlyrics_html(raw_html: str) -> str:
    m = re.search(r"<!-- Usage of azlyrics\.com content.*?-->\s*(.*?)</div>", raw_html, flags=re.S | re.I)
    if not m:
        m = re.search(r'<div class="ringtone">.*?</div>\s*<b>.*?</b>\s*<br>\s*<div>(.*?)</div>', raw_html, flags=re.S | re.I)
    if not m:
        return ""
    return _html_to_lyrics(m.group(1))


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
    miss_key = (artist.strip().lower(), title.strip().lower())
    if session is None:
        ts = _MISS_CACHE.get(miss_key)
        if ts and (time.time() - ts) < _MISS_TTL:
            return out
    found = lrclib_find(artist, title, g.get("album", ""), g.get("duration", 0), session)
    if found and found["instrumental"]:
        out["lyrics"] = "instrumental"
        return out
    if found:   # 1) senkron, 2) duz metin (zaman damgasiz ama tam soz)
        out.update(write_lyrics(path, found["synced"] or found["plain"], artist, title, embed))
        return out
    url = genius_search(artist, title, genius_token(), session)
    if not url and session is None:
        url = genius_web_search(artist, title)
    if url:
        out["links"]["genius_song"] = url
        g_text = genius_fetch_lyrics(url, session)
        if g_text:
            out.update(write_lyrics(path, g_text, artist, title, embed))
            out["source"] = "genius"
            return out
    az_text = azlyrics_fetch_lyrics(artist, title, session)
    if az_text:
        out.update(write_lyrics(path, az_text, artist, title, embed))
        out["source"] = "azlyrics"
        return out
    if session is None:
        _MISS_CACHE[miss_key] = time.time()
    return out
