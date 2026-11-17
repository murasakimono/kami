"""Kami Muzik: YouTube Music / yt-dlp arama + Spotify Web API kontrolu + senkron sozler."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any


def _sp_store():
    from app import paths
    from app.core.debrid import TokenStore
    return TokenStore(paths.DATA_DIR / "spotify_token.bin")


def set_spotify_token(token: str) -> dict[str, Any]:
    tok = str(token or "").strip()
    st = _sp_store()
    if tok:
        st.save(tok)
    else:
        st.clear()
    return {"ok": True, "has_token": bool(tok)}


def get_spotify_token(fallback: str = "") -> str:
    return (_sp_store().load() or str(fallback or "")).strip()


def search_ytmusic(query: str, limit: int = 12) -> dict[str, Any]:
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "items": []}
    try:
        from ytmusicapi import YTMusic  # type: ignore
        ytm = YTMusic()
        res = ytm.search(q, filter="songs", limit=int(limit))
        items = [{
            "id": x.get("videoId", ""),
            "title": x.get("title", ""),
            "artist": ", ".join(a.get("name", "") for a in (x.get("artists") or [])),
            "dur": x.get("duration", ""),
            "url": f"https://music.youtube.com/watch?v={x.get('videoId', '')}",
            "thumb": (x.get("thumbnails") or [{}])[-1].get("url", ""),
        } for x in res if x.get("videoId")]
        return {"ok": True, "source": "ytmusicapi", "items": items}
    except Exception:
        pass
    try:
        from app.engines.ytdlp_engine import find_ytdlp
        exe = find_ytdlp()
        if not exe:
            return {"ok": False, "error": "ytdlp_missing", "items": []}
        r = subprocess.run([exe, "--dump-single-json", "--flat-playlist", f"ytsearch{int(limit)}:{q}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=25,
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        data = json.loads(r.stdout or "{}")
        items = [{
            "id": e.get("id", ""),
            "title": e.get("title", ""),
            "artist": e.get("uploader", "") or e.get("channel", ""),
            "dur": str(e.get("duration_string") or ""),
            "url": e.get("url") or f"https://www.youtube.com/watch?v={e.get('id', '')}",
            "thumb": "",
        } for e in (data.get("entries") or []) if e.get("id")]
        return {"ok": True, "source": "yt-dlp", "items": items}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "items": []}


def spotify_now(token: str) -> dict[str, Any]:
    tok = get_spotify_token(token)
    if not tok:
        return {"ok": False, "error": "no_token"}
    req = urllib.request.Request("https://api.spotify.com/v1/me/player/currently-playing",
                                 headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 204:
                return {"ok": True, "playing": False}
            d = json.loads(resp.read().decode("utf-8"))
            it = d.get("item") or {}
            imgs = ((it.get("album") or {}).get("images") or [{}])
            return {
                "ok": True,
                "playing": bool(d.get("is_playing")),
                "id": it.get("id", ""),
                "title": it.get("name", ""),
                "artist": ", ".join(a.get("name", "") for a in (it.get("artists") or [])),
                "album": (it.get("album") or {}).get("name", ""),
                "cover": imgs[0].get("url", "") if imgs else "",
                "progress_ms": d.get("progress_ms", 0),
                "duration_ms": it.get("duration_ms", 0),
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def spotify_control(token: str, action: str) -> dict[str, Any]:
    tok = get_spotify_token(token)
    if not tok:
        return {"ok": False, "error": "no_token"}
    act = str(action or "").lower().strip()
    routes = {
        "play": ("PUT", "https://api.spotify.com/v1/me/player/play"),
        "pause": ("PUT", "https://api.spotify.com/v1/me/player/pause"),
        "next": ("POST", "https://api.spotify.com/v1/me/player/next"),
        "previous": ("POST", "https://api.spotify.com/v1/me/player/previous"),
    }
    if act not in routes:
        return {"ok": False, "error": "bad_action"}
    method, url = routes[act]
    req = urllib.request.Request(url, data=b"", method=method, headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            return {"ok": resp.status in (200, 202, 204)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def fetch_track_lyrics(title: str, artist: str = "") -> dict[str, Any]:
    t = str(title or "").strip()
    a = str(artist or "").strip()
    if not t:
        return {"ok": False, "lines": [], "plain": ""}
    try:
        from app.core.lyrics import fetch_lyrics
        res = fetch_lyrics(f"{a} - {t}" if a else t)
        if not res:
            return {"ok": False, "lines": [], "plain": ""}
        return {
            "ok": True,
            "synced": bool(res.get("synced")),
            "lines": res.get("lines") or [],
            "plain": res.get("plain") or "",
            "source": res.get("source") or "",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "lines": [], "plain": ""}
