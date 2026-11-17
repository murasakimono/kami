"""Kami Muzik: YouTube Music / yt-dlp arama + Spotify Web API kontrolu."""
from __future__ import annotations

import json
import subprocess
import urllib.request
from typing import Any


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
    # Fallback: yt-dlp flat-playlist search
    try:
        from app.engines.ytdlp_engine import find_ytdlp
        exe = find_ytdlp()
        if not exe:
            return {"ok": False, "error": "ytdlp_missing", "items": []}
        r = subprocess.run([exe, "--dump-single-json", "--flat-playlist", f"ytsearch{int(limit)}:{q}"],
                           capture_output=True, text=True, timeout=25)
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
    tok = str(token or "").strip()
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
            return {
                "ok": True,
                "playing": bool(d.get("is_playing")),
                "title": it.get("name", ""),
                "artist": ", ".join(a.get("name", "") for a in (it.get("artists") or [])),
                "progress_ms": d.get("progress_ms", 0),
                "duration_ms": it.get("duration_ms", 0),
            }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}
