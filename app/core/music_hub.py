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
    """Once kalici OAuth (PKCE, kendini yeniler), yoksa elle yapistirilan token."""
    return (spotify_access_token() or _sp_store().load() or str(fallback or "")).strip()


# ---------- Kalici Spotify girisi: Authorization Code + PKCE (istemci sirri yok) ----------
SP_PORT = 47395
SP_REDIRECT = f"http://127.0.0.1:{SP_PORT}/callback"   # Spotify: localhost yasak, loopback IP serbest
SP_SCOPES = "user-read-currently-playing user-read-playback-state user-modify-playback-state"
_SP_CACHE: dict[str, Any] = {"token": "", "exp": 0.0}


def _sp_oauth_store():
    from app import paths
    from app.core.debrid import TokenStore
    return TokenStore(paths.DATA_DIR / "spotify_oauth.bin")   # DPAPI: {client_id, refresh_token}


def _sp_oauth() -> dict[str, Any]:
    try:
        return json.loads(_sp_oauth_store().load() or "{}")
    except ValueError:
        return {}


def _sp_token_request(fields: dict[str, str]) -> dict[str, Any]:
    import urllib.parse
    req = urllib.request.Request("https://accounts.spotify.com/api/token", data=urllib.parse.urlencode(fields).encode(),
                                 headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read().decode("utf-8"))


def _sp_keep(d: dict[str, Any], client_id: str) -> None:
    import time
    _SP_CACHE.update(token=d.get("access_token", ""), exp=time.time() + int(d.get("expires_in", 3600)) - 60)
    old = _sp_oauth()
    _sp_oauth_store().save(json.dumps({"client_id": client_id, "refresh_token": d.get("refresh_token") or old.get("refresh_token", "")}))


def spotify_access_token() -> str:
    """Gecerli erisim token'i; suresi dolmussa refresh token ile sessizce yeniler (her saat elle yapistirma yok)."""
    import time
    if _SP_CACHE["token"] and time.time() < _SP_CACHE["exp"]:
        return _SP_CACHE["token"]
    o = _sp_oauth()
    if not o.get("refresh_token") or not o.get("client_id"):
        return ""
    try:
        d = _sp_token_request({"grant_type": "refresh_token", "refresh_token": o["refresh_token"], "client_id": o["client_id"]})
        _sp_keep(d, o["client_id"])
        return _SP_CACHE["token"]
    except Exception:
        return ""


def spotify_oauth_status() -> dict[str, Any]:
    o = _sp_oauth()
    return {"connected": bool(o.get("refresh_token")), "client_id": o.get("client_id", ""), "redirect": SP_REDIRECT}


def spotify_logout() -> dict[str, Any]:
    _sp_oauth_store().clear()
    _SP_CACHE.update(token="", exp=0.0)
    return {"ok": True}


def spotify_login(client_id: str, timeout: float = 110.0) -> dict[str, Any]:
    """Tarayicida Spotify izin sayfasini acar, 127.0.0.1 geri donusunu dinler, kodu PKCE ile token'a cevirir."""
    import base64
    import hashlib
    import http.server
    import secrets
    import threading
    import urllib.parse
    import webbrowser
    cid = str(client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "no_client_id"}
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict[str, str] = {}
    done = threading.Event()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            if u.path != "/callback":
                self.send_response(404); self.end_headers(); return
            ok = q.get("state") == state and "code" in q
            got.update(q if ok else {"error": q.get("error", "state_mismatch")})
            body = ("<h2 style='font-family:sans-serif;color:#2EE6A6'>Kami Spotify'a bağlandı. Bu sekmeyi kapatabilirsin.</h2>" if ok
                    else f"<h2 style='font-family:sans-serif;color:#FF6B81'>Bağlanamadı: {got.get('error')}</h2>")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            done.set()

        def log_message(self, *a):
            pass

    try:
        srv = http.server.HTTPServer(("127.0.0.1", SP_PORT), H)
    except OSError:
        return {"ok": False, "error": "port_busy"}
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        webbrowser.open("https://accounts.spotify.com/authorize?" + urllib.parse.urlencode({
            "client_id": cid, "response_type": "code", "redirect_uri": SP_REDIRECT, "scope": SP_SCOPES,
            "code_challenge_method": "S256", "code_challenge": challenge, "state": state}))
        if not done.wait(timeout):
            return {"ok": False, "error": "timeout"}
    finally:
        srv.shutdown(); srv.server_close()
    if "code" not in got:
        return {"ok": False, "error": got.get("error", "denied")}
    try:
        d = _sp_token_request({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": SP_REDIRECT,
                               "client_id": cid, "code_verifier": verifier})
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
    if not d.get("access_token"):
        return {"ok": False, "error": d.get("error_description") or "no_token"}
    _sp_keep(d, cid)
    return {"ok": True}


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
