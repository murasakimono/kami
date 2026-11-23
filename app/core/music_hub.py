"""Kami Muzik: YouTube Music / yt-dlp arama + Spotify Web API kontrolu + senkron sozler."""
from __future__ import annotations

import json
import os
import threading
import time
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
SP_PORT = 47361   # 47395 web_isolation sunucusunda
SP_REDIRECT = f"http://127.0.0.1:{SP_PORT}/callback"   # Spotify: localhost yasak, loopback IP serbest
SP_SCOPES = (
    "user-read-currently-playing user-read-playback-state user-modify-playback-state "
    "user-library-read user-library-modify "
    "playlist-read-private playlist-read-collaborative playlist-modify-public playlist-modify-private "
    "user-read-recently-played"
)
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
        _SP_CACHE["expired"] = False
        return _SP_CACHE["token"]
    except Exception:
        _SP_CACHE["expired"] = True
        return ""


def spotify_oauth_status() -> dict[str, Any]:
    o = _sp_oauth()
    has_ref = bool(o.get("refresh_token"))
    expired = bool(_SP_CACHE.get("expired"))
    if has_ref and not _SP_CACHE.get("token"):
        tok = spotify_access_token()
        expired = not bool(tok)
    return {"connected": has_ref and not expired, "expired": has_ref and expired,
            "client_id": o.get("client_id", ""), "redirect": SP_REDIRECT}


def spotify_logout() -> dict[str, Any]:
    _sp_oauth_store().clear()
    _SP_CACHE.update(token="", exp=0.0)
    return {"ok": True}


_SP_STATES: dict[str, tuple[str, str]] = {}
_SP_SRV: Any = None
_SP_LOCK = None


def spotify_login(client_id: str, timeout: float = 110.0) -> dict[str, Any]:
    """Tarayicida Spotify izin sayfasini acar, 127.0.0.1 geri donusunu dinler, kodu PKCE ile token'a cevirir."""
    import base64
    import hashlib
    import http.server
    import secrets
    import threading
    import urllib.parse
    import webbrowser
    global _SP_SRV, _SP_LOCK
    if _SP_LOCK is None:
        _SP_LOCK = threading.Lock()
    cid = str(client_id or "").strip()
    if not cid:
        return {"ok": False, "error": "no_client_id"}
    verifier = secrets.token_urlsafe(64)[:96]
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    _SP_STATES[state] = (verifier, cid)
    if len(_SP_STATES) > 8:
        _SP_STATES.pop(next(iter(_SP_STATES)))
    got: dict[str, str] = {}
    done = threading.Event()

    class Srv(http.server.ThreadingHTTPServer):
        allow_reuse_address = True

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            u = urllib.parse.urlsplit(self.path)
            if u.path != "/callback":
                self.send_response(404); self.end_headers(); return
            q = {k: v[0] for k, v in urllib.parse.parse_qs(u.query).items()}
            st = q.get("state", "")
            ok = st in _SP_STATES and "code" in q
            got.update(q if ok else {"error": q.get("error", "state_mismatch")})
            body = ("<body style='background:#08070C;color:#2EE6A6;font-family:sans-serif;display:grid;place-items:center;height:90vh'>"
                    "<h2>✓ Kami Spotify'a bağlandı. Bu sekmeyi kapatabilirsin.</h2></body>" if ok
                    else f"<body style='background:#08070C;color:#FF6B81;font-family:sans-serif;display:grid;place-items:center;height:90vh'><h2>Bağlanamadı: {got.get('error')}</h2></body>")
            self.send_response(200); self.send_header("Content-Type", "text/html; charset=utf-8"); self.end_headers()
            self.wfile.write(body.encode("utf-8"))
            done.set()

        def log_message(self, *a):
            pass

    with _SP_LOCK:
        if _SP_SRV is not None:
            try:
                _SP_SRV.shutdown(); _SP_SRV.server_close()
            except Exception:
                pass
            _SP_SRV = None
        try:
            srv = Srv(("127.0.0.1", SP_PORT), H)
            _SP_SRV = srv
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
        try:
            srv.shutdown(); srv.server_close()
        except Exception:
            pass
        if _SP_SRV is srv:
            _SP_SRV = None
    if "code" not in got:
        return {"ok": False, "error": got.get("error", "denied")}
    use_ver, use_cid = _SP_STATES.pop(got.get("state", ""), (verifier, cid))
    try:
        d = _sp_token_request({"grant_type": "authorization_code", "code": got["code"], "redirect_uri": SP_REDIRECT,
                               "client_id": use_cid, "code_verifier": use_ver})
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:160]}
    if not d.get("access_token"):
        return {"ok": False, "error": d.get("error_description") or "no_token"}
    _sp_keep(d, use_cid)
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
        data = _ytdlp_flat(f"ytsearch{int(limit)}:{q}", 25)
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


def _ytdlp_flat(target: str, timeout: int = 30) -> dict[str, Any]:
    """yt-dlp'yi gomulu Python kutuphanesi olarak calistirir (Kami'de ayri yt-dlp.exe yok).
    Eskiden var olmayan find_ytdlp import ediliyordu -> YT Music arama/liste hep ImportError."""
    from app.engines.ytdlp_engine import _ytdlp
    yd = _ytdlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "extract_flat": "in_playlist",
            "socket_timeout": min(20, timeout), "noplaylist": False}
    with yd.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(target, download=False) or {}
    return ydl.sanitize_info(info) if hasattr(ydl, "sanitize_info") else info


def _librespot_now() -> dict[str, Any] | None:
    try:
        from app.core import librespot_host
        if not librespot_host.is_running():
            return None
        st = librespot_host.status()
        d = st.get("data") if isinstance(st.get("data"), dict) else None
        tr = (d or {}).get("track") or {}
        if not d or not tr.get("name"):
            return None
        uri = str(tr.get("uri") or "")
        tid = uri.split(":")[-1] if uri.startswith("spotify:track:") else ""
        steps = max(1, int(d.get("volume_steps") or 100))
        vol = round(int(d.get("volume") or 100) * 100 / steps)
        rep = "track" if d.get("repeat_track") else ("context" if d.get("repeat_context") else "off")
        return {
            "ok": True,
            "playing": not bool(d.get("paused") or d.get("stopped")),
            "id": tid,
            "uri": uri,
            "title": tr.get("name", ""),
            "artist": ", ".join(tr.get("artist_names") or []),
            "album": tr.get("album_name", ""),
            "cover": tr.get("album_cover_url", ""),
            "progress_ms": int(tr.get("position") or 0),
            "duration_ms": int(tr.get("duration") or 0),
            "shuffle": bool(d.get("shuffle_context")),
            "repeat": rep,
            "device_id": d.get("device_id", ""),
            "device_name": d.get("device_name", "Kami"),
            "volume": vol,
            "local_librespot": True,
        }
    except Exception:
        return None


_LAST_NOW: dict[str, Any] = {}


def cached_now(allow_paused: bool = False) -> dict[str, Any] | None:
    """Ag cagrisi yapmadan mevcut yerel (go-librespot) veya son bilinen oynatma durumunu dondurur."""
    loc = _librespot_now()
    if loc and loc.get("title"):
        return loc
    if _LAST_NOW.get("title") and (allow_paused or _LAST_NOW.get("playing")):
        return dict(_LAST_NOW)
    return None


# v2.5.3: "Simdi calan" onbellegi. Arayuz (Kamify, mini ada, Sunak) saniyede birkac kez soruyordu ve her soru
# Spotify'a 6 sn zaman asimli senkron istek atiyordu (kami.log: 5401 "yavas api cagrisi"). Artik:
#  - 1.5 sn icinde tekrar soran onbellekten alir,
#  - 20 sn'ye kadar bayat sonuc aninda doner (calan parcanin ilerlemesi tahminle ilerletilir), tazeleme arka planda,
#  - ayni anda yalniz tek ag istegi.
_NOW_LOCK = threading.Lock()
_NOW_META: dict[str, Any] = {"t": 0.0, "res": None}
_NOW_TTL = 1.5
_NOW_STALE_MAX = 20.0


def invalidate_now() -> None:
    _NOW_META["t"] = 0.0


def _now_extrapolate(res: dict[str, Any], age: float) -> dict[str, Any]:
    out = dict(res)
    if out.get("playing") and out.get("duration_ms"):
        out["progress_ms"] = min(int(out.get("progress_ms") or 0) + int(age * 1000), int(out["duration_ms"]))
    return out


def _now_store(res: dict[str, Any]) -> dict[str, Any]:
    _NOW_META["res"], _NOW_META["t"] = dict(res), time.monotonic()
    return res


def _now_bg(token: str) -> None:
    try:
        _now_store(_spotify_now_fetch(token))
    except Exception:
        pass
    finally:
        _NOW_LOCK.release()


def spotify_now(token: str) -> dict[str, Any]:
    res, age = _NOW_META["res"], time.monotonic() - float(_NOW_META["t"])
    if res is not None and age < _NOW_TTL:
        return _now_extrapolate(res, age)
    if res is not None and age < _NOW_STALE_MAX:
        if _NOW_LOCK.acquire(blocking=False):
            threading.Thread(target=_now_bg, args=(token,), name="kami-sp-now", daemon=True).start()
        return _now_extrapolate(res, age)
    with _NOW_LOCK:
        res, age = _NOW_META["res"], time.monotonic() - float(_NOW_META["t"])
        if res is not None and age < _NOW_TTL:   # beklerken baska is parcacigi tazeledi
            return _now_extrapolate(res, age)
        return _now_store(_spotify_now_fetch(token))


def _spotify_now_fetch(token: str) -> dict[str, Any]:
    tok = get_spotify_token(token)
    if not tok:
        lib = _librespot_now()
        if lib:
            _LAST_NOW.clear()
            _LAST_NOW.update(lib)
            return lib
        return {"ok": False, "error": "no_token"}
    req = urllib.request.Request("https://api.spotify.com/v1/me/player",
                                 headers={"Authorization": f"Bearer {tok}"})
    try:
        with urllib.request.urlopen(req, timeout=6) as resp:
            if resp.status == 204:
                res = _librespot_now() or {"ok": True, "playing": False}
                if res.get("title") or not _LAST_NOW.get("title"):
                    _LAST_NOW.clear()
                    _LAST_NOW.update(res)
                return res
            d = json.loads(resp.read().decode("utf-8"))
            it = d.get("item") or {}
            title = it.get("name", "")
            if not title:
                lib = _librespot_now()
                if lib and lib.get("title"):
                    _LAST_NOW.clear()
                    _LAST_NOW.update(lib)
                    return lib
                return _LAST_NOW if _LAST_NOW.get("title") else {"ok": True, "playing": False}
            imgs = ((it.get("album") or {}).get("images") or [{}])
            dev = d.get("device") or {}
            res = {
                "ok": True,
                "playing": bool(d.get("is_playing")),
                "id": it.get("id", ""),
                "uri": it.get("uri", ""),
                "title": title,
                "artist": ", ".join(a.get("name", "") for a in (it.get("artists") or [])),
                "album": (it.get("album") or {}).get("name", ""),
                "cover": imgs[0].get("url", "") if imgs else "",
                "progress_ms": d.get("progress_ms", 0),
                "duration_ms": it.get("duration_ms", 0),
                "shuffle": bool(d.get("shuffle_state")),
                "repeat": str(d.get("repeat_state") or "off"),
                "device_id": dev.get("id", ""),
                "device_name": dev.get("name", ""),
                "volume": int(dev.get("volume_percent") if dev.get("volume_percent") is not None else 100),
            }
            if not res["playing"]:
                lib = _librespot_now()
                if lib and lib.get("playing") and lib.get("title"):
                    _LAST_NOW.clear()
                    _LAST_NOW.update(lib)
                    return lib
            _LAST_NOW.clear()
            _LAST_NOW.update(res)
            return res
    except Exception as exc:
        lib = _librespot_now()
        if lib and lib.get("title"):
            _LAST_NOW.clear()
            _LAST_NOW.update(lib)
            return lib
        return {"ok": False, "error": str(exc)[:120]}


def _sp_api(method: str, path: str, body: dict[str, Any] | None = None, token: str = "") -> dict[str, Any]:
    tok = get_spotify_token(token)
    if not tok:
        return {"ok": False, "error": "no_token"}
    url = path if path.startswith("https://") else f"https://api.spotify.com/v1{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else (b"" if method in ("PUT", "POST", "DELETE") else None)
    headers = {"Authorization": f"Bearer {tok}"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    if method != "GET":
        invalidate_now()   # v2.5.3: oynat/duraklat/atla sonrasi bir sonraki "simdi calan" tazelensin
    try:
        with urllib.request.urlopen(req, timeout=8) as resp:
            if resp.status == 204:
                return {"ok": True}
            raw = resp.read().decode("utf-8", errors="replace").strip()
            return {"ok": True, "data": json.loads(raw) if raw else {}}
    except urllib.error.HTTPError as exc:
        err_txt = exc.read().decode("utf-8", errors="replace")[:180]
        return {"ok": False, "status": exc.code, "error": err_txt or str(exc)}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def spotify_search(query: str, kind: str = "track,album,playlist", limit: int = 10) -> dict[str, Any]:
    import urllib.parse
    q = str(query or "").strip()
    if not q:
        return {"ok": False, "tracks": [], "albums": [], "playlists": []}
    qs = urllib.parse.urlencode({"q": q, "type": kind, "limit": min(10, max(1, int(limit)))})
    r = _sp_api("GET", f"/search?{qs}")
    if not r.get("ok"):
        return {**r, "tracks": [], "albums": [], "playlists": []}
    d = r.get("data") or {}
    tracks = [{
        "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
        "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
        "album": (t.get("album") or {}).get("name", ""),
        "cover": ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
        "duration_ms": t.get("duration_ms", 0),
    } for t in ((d.get("tracks") or {}).get("items") or []) if t]
    albums = [{
        "id": a.get("id", ""), "uri": a.get("uri", ""), "title": a.get("name", ""),
        "artist": ", ".join(x.get("name", "") for x in (a.get("artists") or [])),
        "cover": (a.get("images") or [{}])[0].get("url", ""),
        "total": a.get("total_tracks", 0),
    } for a in ((d.get("albums") or {}).get("items") or []) if a]
    playlists = [{
        "id": p.get("id", ""), "uri": p.get("uri", ""), "title": p.get("name", ""),
        "owner": (p.get("owner") or {}).get("display_name", ""),
        "cover": (p.get("images") or [{}])[0].get("url", ""),
        "total": (p.get("tracks") or {}).get("total", 0),
    } for p in ((d.get("playlists") or {}).get("items") or []) if p]
    return {"ok": True, "tracks": tracks, "albums": albums, "playlists": playlists}


def spotify_playlists(limit: int = 40) -> dict[str, Any]:
    r = _sp_api("GET", f"/me/playlists?limit={min(50, int(limit))}")
    if not r.get("ok"):
        return {**r, "items": []}
    me = _sp_me_id()
    items = [{
        "id": p.get("id", ""), "uri": p.get("uri", ""), "title": p.get("name", ""),
        "owner": (p.get("owner") or {}).get("display_name", ""),
        "cover": (p.get("images") or [{}])[0].get("url", ""),
        # Subat 2026: ozetteki sayi 'tracks' yerine 'items' alaninda
        "total": (p.get("items") or p.get("tracks") or {}).get("total", 0),
        # yalniz kendi / ortak listeler degistirilebilir (digerlerine ekleme 403)
        "editable": bool(p.get("collaborative")) or (bool(me) and (p.get("owner") or {}).get("id") == me),
    } for p in ((r.get("data") or {}).get("items") or []) if p]
    return {"ok": True, "items": items}


_SP_ME: dict[str, str] = {}


def _sp_me_id() -> str:
    if not _SP_ME.get("id"):
        r = _sp_api("GET", "/me")
        if r.get("ok"):
            _SP_ME["id"] = str((r.get("data") or {}).get("id") or "")
    return _SP_ME.get("id", "")


def spotify_playlist_tracks(playlist_id: str, limit: int = 100) -> dict[str, Any]:
    pid = str(playlist_id or "").strip()
    if not pid:
        return {"ok": False, "items": []}
    r = _sp_api("GET", f"/playlists/{pid}/items?limit={min(100, int(limit))}")
    if not r.get("ok"):
        return {**r, "items": []}
    items = []
    for x in ((r.get("data") or {}).get("items") or []):
        t = (x or {}).get("item") or (x or {}).get("track") or {}
        if not t or not t.get("uri"):
            continue
        items.append({
            "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
            "album": (t.get("album") or {}).get("name", ""),
            "cover": ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
            "duration_ms": t.get("duration_ms", 0),
        })
    return {"ok": True, "items": items}


def spotify_saved_tracks(limit: int = 50) -> dict[str, Any]:
    r = _sp_api("GET", f"/me/tracks?limit={min(50, int(limit))}")
    if not r.get("ok"):
        return {**r, "items": []}
    items = []
    for x in ((r.get("data") or {}).get("items") or []):
        t = (x or {}).get("track") or {}
        if not t or not t.get("uri"):
            continue
        items.append({
            "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
            "album": (t.get("album") or {}).get("name", ""),
            "cover": ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
            "duration_ms": t.get("duration_ms", 0),
        })
    return {"ok": True, "items": items}


def spotify_recent_tracks(limit: int = 30) -> dict[str, Any]:
    r = _sp_api("GET", f"/me/player/recently-played?limit={min(50, int(limit))}")
    if not r.get("ok"):
        return {**r, "items": []}
    items = []
    for x in ((r.get("data") or {}).get("items") or []):
        t = (x or {}).get("track") or {}
        if not t or not t.get("uri"):
            continue
        items.append({
            "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
            "album": (t.get("album") or {}).get("name", ""),
            "cover": ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
            "duration_ms": t.get("duration_ms", 0),
        })
    return {"ok": True, "items": items}


def spotify_play_uri(uri: str = "", context_uri: str = "", position_ms: int = 0) -> dict[str, Any]:
    body: dict[str, Any] = {}
    if context_uri:
        body["context_uri"] = context_uri
        if uri:
            body["offset"] = {"uri": uri}
    elif uri:
        if ":track:" in uri:
            body["uris"] = [uri]
        else:
            body["context_uri"] = uri
    if position_ms > 0:
        body["position_ms"] = int(position_ms)
    # Dahili go-librespot: acik baska aktif cihaz yoksa (veya secili cihaz Kami ise) dogrudan go-librespot calar.
    from app.core import librespot_host
    ls_st = librespot_host.status()
    ls_id = str(ls_st.get("device_id") or "")
    dev = _sp_pick_device(launch=False)
    if ls_st.get("paired") and (not dev or (ls_id and dev == ls_id)):
        lr = librespot_host.play_uri(uri=uri, context_uri=context_uri, position_ms=position_ms)
        if lr.get("ok"):
            return lr
    if not dev:
        if ls_st.get("running") and ls_st.get("pair_url") and not ls_st.get("paired"):
            return {
                "ok": False,
                "error": "librespot_pair",
                "pair_url": ls_st.get("pair_url", ""),
                "pair_code": ls_st.get("pair_code", ""),
                "message": f"Dahili Spotify oynatıcıyı 1 kez eşleştir ({ls_st.get('pair_code') or 'spotify.com/pair'}).",
            }
        dev = _sp_pick_device(launch=True)
    if not dev:
        return {"ok": False, "error": "no_device",
                "message": "Spotify açık bir cihaz bulamadı. Dahili oynatıcıyı eşleştir veya Spotify uygulamasını aç."}
    r = _sp_api("PUT", f"/me/player/play?device_id={dev}", body)
    return _sp_explain(r)


def _sp_explain(r: dict[str, Any]) -> dict[str, Any]:
    if r.get("ok"):
        return r
    txt = str(r.get("error") or "")
    if "PREMIUM_REQUIRED" in txt or r.get("status") == 403:
        r["message"] = "Spotify uzaktan çalmayı yalnızca Premium hesapta izin veriyor."
    elif "NO_ACTIVE_DEVICE" in txt or r.get("status") == 404:
        r["message"] = "Spotify cihazı bulunamadı. Spotify uygulamasını açıp tekrar dene."
    elif r.get("error") == "no_token":
        r["message"] = "Spotify bağlı değil. Sol alttan Bağla'ya bas."
    else:
        r["message"] = "Spotify çalmayı başlatamadı: " + txt[:100]
    return r


def _sp_pick_device(launch: bool = False) -> str:
    def pick() -> str:
        d = spotify_devices().get("devices") or []
        act = [x for x in d if x.get("active")]
        pc = [x for x in d if str(x.get("type", "")).lower() == "computer"]
        return ((act or pc or d or [{}])[0]).get("id", "")
    dev = pick()
    if dev or not launch:
        return dev
    try:
        if os.name == "nt":
            os.startfile("spotify:")   # noqa: S606 - kullanicinin kendi Spotify uygulamasi
    except OSError:
        return ""
    deadline = time.time() + 12
    while time.time() < deadline:
        time.sleep(1.0)
        dev = pick()
        if dev:
            return dev
    return ""


def spotify_queue_add(uri: str) -> dict[str, Any]:
    import urllib.parse
    if not uri:
        return {"ok": False, "error": "empty_uri"}
    return _sp_api("POST", f"/me/player/queue?uri={urllib.parse.quote(uri)}")


def spotify_playlist_create(name: str, description: str = "", public: bool = False) -> dict[str, Any]:
    nm = str(name or "").strip()
    if not nm:
        return {"ok": False, "error": "empty_name"}
    return _sp_api("POST", "/me/playlists", {"name": nm, "description": description, "public": bool(public)})


def spotify_playlist_modify(playlist_id: str, uris: list[str], remove: bool = False) -> dict[str, Any]:
    pid = str(playlist_id or "").strip()
    if not pid or not uris:
        return {"ok": False, "error": "missing_args"}
    if remove:
        return _sp_api("DELETE", f"/playlists/{pid}/items", {"items": [{"uri": u} for u in uris]})
    return _sp_api("POST", f"/playlists/{pid}/items", {"uris": list(uris)})


def spotify_playlist_details(playlist_id: str, name: str = "", description: str = "") -> dict[str, Any]:
    """Playlist adini ve/veya aciklamasini (bio) degistir."""
    pid = str(playlist_id or "").strip()
    if not pid:
        return {"ok": False, "error": "missing_args"}
    body: dict[str, Any] = {}
    if str(name or "").strip():
        body["name"] = str(name).strip()
    if str(description or "").strip():
        body["description"] = str(description)
    if not body:
        return {"ok": False, "error": "empty"}
    return _sp_api("PUT", f"/playlists/{pid}", body)


def spotify_playlist_cover(playlist_id: str, image_b64: str) -> dict[str, Any]:
    """Playlist kapagini degistir (base64 JPEG, max 256KB)."""
    pid = str(playlist_id or "").strip()
    if not pid or not image_b64:
        return {"ok": False, "error": "missing_args"}
    tok = get_spotify_token("")
    if not tok:
        return {"ok": False, "error": "no_token"}
    import base64
    raw = base64.b64decode(image_b64)
    req = urllib.request.Request(f"https://api.spotify.com/v1/playlists/{pid}/images", data=raw, method="PUT",
                                 headers={"Authorization": f"Bearer {tok}", "Content-Type": "image/jpeg"})
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return {"ok": resp.status in (200, 202, 204)}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "error": exc.read().decode("utf-8", errors="replace")[:180]}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def spotify_devices() -> dict[str, Any]:
    r = _sp_api("GET", "/me/player/devices")
    devs = [{
        "id": d.get("id", ""), "name": d.get("name", ""), "type": d.get("type", ""),
        "active": bool(d.get("is_active")), "volume": int(d.get("volume_percent") or 100),
    } for d in (((r.get("data") or {}).get("devices") or []) if r.get("ok") else []) if d.get("id")]
    try:
        from app.core import librespot_host
        if librespot_host.is_running():
            st = librespot_host.status()
            d_id = str(st.get("device_id") or "")
            if st.get("paired") and d_id and not any(x.get("id") == d_id for x in devs):
                devs.insert(0, {"id": d_id, "name": "Kami (Dahili)", "type": "Computer", "active": bool(st.get("active")), "volume": 100})
    except Exception:
        pass
    if not r.get("ok") and not devs:
        return {**r, "devices": []}
    return {"ok": True, "devices": devs}


def spotify_transfer(device_id: str) -> dict[str, Any]:
    if not device_id:
        return {"ok": False, "error": "empty_device"}
    return _sp_api("PUT", "/me/player", {"device_ids": [device_id], "play": True})


def spotify_seek(position_ms: int) -> dict[str, Any]:
    from app.core import librespot_host
    if librespot_host.is_running() and (librespot_host.status().get("active")):
        r = librespot_host.seek(position_ms)
        if r.get("ok"):
            return r
    return _sp_api("PUT", f"/me/player/seek?position_ms={max(0, int(position_ms))}")


def spotify_shuffle(state: bool) -> dict[str, Any]:
    return _sp_api("PUT", f"/me/player/shuffle?state={'true' if state else 'false'}")


def spotify_repeat(state: str) -> dict[str, Any]:
    st = state if state in ("off", "context", "track") else "off"
    return _sp_api("PUT", f"/me/player/repeat?state={st}")


def spotify_volume(percent: int) -> dict[str, Any]:
    v = max(0, min(100, int(percent)))
    from app.core import librespot_host
    if librespot_host.is_running() and (librespot_host.status().get("active")):
        r = librespot_host.set_volume(v)
        if r.get("ok"):
            return r
    return _sp_api("PUT", f"/me/player/volume?volume_percent={v}")


def spotify_like_check(track_id: str) -> dict[str, Any]:
    import urllib.parse
    ref = str(track_id or "").strip()
    if not ref:
        return {"ok": False, "liked": False}
    uri = ref if ref.startswith("spotify:") else f"spotify:track:{ref}"
    r = _sp_api("GET", f"/me/library/contains?uris={urllib.parse.quote(uri)}")
    if not r.get("ok"):
        return {**r, "liked": False}
    arr = r.get("data") if isinstance(r.get("data"), list) else []
    return {"ok": True, "liked": bool(arr and arr[0])}


def spotify_like_toggle(track_id: str, like: bool) -> dict[str, Any]:
    import urllib.parse
    ref = str(track_id or "").strip()
    if not ref:
        return {"ok": False, "error": "empty_id"}
    uri = ref if ref.startswith("spotify:") else f"spotify:track:{ref}"
    return _sp_api("PUT" if like else "DELETE", f"/me/library?uris={urllib.parse.quote(uri)}", {"uris": [uri]})


def spotify_queue_list() -> dict[str, Any]:
    r = _sp_api("GET", "/me/player/queue")
    if not r.get("ok"):
        return {**r, "queue": []}
    q = []
    for t in ((r.get("data") or {}).get("queue") or []):
        if not t or not t.get("uri"):
            continue
        q.append({
            "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
            "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
            "album": (t.get("album") or {}).get("name", ""),
            "cover": ((t.get("album") or {}).get("images") or [{}])[-1].get("url", ""),
        })
    return {"ok": True, "queue": q}


def spotify_album_tracks(album_id: str, limit: int = 50) -> dict[str, Any]:
    aid = str(album_id or "").strip()
    if not aid:
        return {"ok": False, "items": []}
    r = _sp_api("GET", f"/albums/{aid}/tracks?limit={min(50, int(limit))}")
    if not r.get("ok"):
        return {**r, "items": []}
    items = [{
        "id": t.get("id", ""), "uri": t.get("uri", ""), "title": t.get("name", ""),
        "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
        "album": "",
        "cover": "",
        "duration_ms": t.get("duration_ms", 0),
    } for t in ((r.get("data") or {}).get("items") or []) if t and t.get("uri")]
    return {"ok": True, "items": items}


# ---------- Yerel Muzik Klasorleri (or. Downloads\Contra\...) ----------
AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".m4a", ".opus", ".aac", ".wma"}


def _folders_file():
    from app import paths
    return paths.DATA_DIR / "music_folders.json"


def local_folders_list() -> list[str]:
    p = _folders_file()
    try:
        if p.is_file():
            return [str(x) for x in json.loads(p.read_text(encoding="utf-8")) if isinstance(x, str)]
    except Exception:
        pass
    return []


def local_folders_add(folder: str) -> dict[str, Any]:
    from pathlib import Path
    fp = Path(str(folder or "").strip().strip('"'))
    if not fp.is_dir():
        return {"ok": False, "error": "Klasor bulunamadi"}
    cur = local_folders_list()
    s = str(fp)
    if s not in cur:
        cur.append(s)
        _folders_file().parent.mkdir(parents=True, exist_ok=True)
        _folders_file().write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "folders": cur}


def local_folders_remove(folder: str) -> dict[str, Any]:
    s = str(folder or "").strip()
    cur = [x for x in local_folders_list() if x != s]
    _folders_file().parent.mkdir(parents=True, exist_ok=True)
    _folders_file().write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "folders": cur}


def local_folder_rename(folder: str, new_name: str) -> dict[str, Any]:
    """Yerel muzik klasorunun adini degistir (dosya sisteminde) + listeyi guncelle."""
    from pathlib import Path
    fp = Path(str(folder or "").strip().strip('"'))
    nn = str(new_name or "").strip()
    if not fp.is_dir():
        return {"ok": False, "error": "Klasor bulunamadi"}
    if not nn or any(c in nn for c in '<>:"|?*') or nn in (".", ".."):
        return {"ok": False, "error": "Gecersiz ad"}
    target = fp.parent / nn
    if target.exists():
        return {"ok": False, "error": "Bu ad zaten var"}
    try:
        fp.rename(target)
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120]}
    cur = local_folders_list()
    s_old, s_new = str(fp), str(target)
    cur = [s_new if x == s_old else x for x in cur]
    _folders_file().parent.mkdir(parents=True, exist_ok=True)
    _folders_file().write_text(json.dumps(cur, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "new_path": s_new}


def local_folder_cover(folder: str, image_b64: str) -> dict[str, Any]:
    """Yerel muzik klasorune folder.jpg kapak yazar."""
    from pathlib import Path
    import base64
    fp = Path(str(folder or "").strip().strip('"'))
    if not fp.is_dir():
        return {"ok": False, "error": "Klasor bulunamadi"}
    try:
        raw = base64.b64decode(image_b64)
    except Exception:
        return {"ok": False, "error": "bad_image"}
    out = fp / "folder.jpg"
    try:
        out.write_bytes(raw)
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:120]}
    return {"ok": True, "path": str(out)}


def local_scan_folder(folder: str = "", query: str = "", limit: int = 500) -> dict[str, Any]:
    from pathlib import Path
    roots = [Path(folder)] if folder else [Path(x) for x in local_folders_list()]
    q = str(query or "").strip().lower()
    items: list[dict[str, Any]] = []
    for root in roots:
        if not root.is_dir():
            continue
        for f in sorted(root.rglob("*")):
            if not f.is_file() or f.suffix.lower() not in AUDIO_EXT or f.name.startswith("._") or "__MACOSX" in f.parts:
                continue
            if q and q not in f.name.lower() and q not in f.parent.name.lower():
                continue
            items.append({
                "path": str(f),
                "title": f.stem,
                "folder": f.parent.name,
                "root": str(root),
                "ext": f.suffix.lower().lstrip("."),
                "cover": str(f.parent / "folder.jpg") if (f.parent / "folder.jpg").is_file() else "",
            })
            if len(items) >= limit:
                break
    # Klasor kapaklari: "Klasoru Duzenle > Kapak Degistir" folder.jpg yazar; arayuz buradan okur.
    covers: dict[str, str] = {}
    for root in roots:
        if root.is_dir() and (root / "folder.jpg").is_file():
            covers[str(root)] = str(root / "folder.jpg")
    return {"ok": True, "folders": local_folders_list(), "covers": covers, "items": items}


# ---------- YouTube Music Playlist & Spotify <-> YTM Gecis ----------
def _ytm_playlists_file():
    from app import paths
    return paths.DATA_DIR / "ytm_playlists.json"


def ytm_saved_playlists() -> list[dict[str, str]]:
    p = _ytm_playlists_file()
    try:
        if p.is_file():
            return list(json.loads(p.read_text(encoding="utf-8")))
    except Exception:
        pass
    return []


def ytm_extract_playlist_id(url_or_id: str) -> str:
    import re
    s = str(url_or_id or "").strip()
    m = re.search(r"[?&]list=([A-Za-z0-9_-]+)", s)
    return m.group(1) if m else s


def ytm_get_playlist(url_or_id: str, limit: int = 2000, save: bool = True) -> dict[str, Any]:
    pid = ytm_extract_playlist_id(url_or_id)
    if not pid:
        return {"ok": False, "error": "empty_id", "items": []}
    title, items = "", []
    try:
        from ytmusicapi import YTMusic  # type: ignore
        pl = YTMusic().get_playlist(pid, limit=int(limit))
        title = str(pl.get("title") or pid)
        for t in (pl.get("tracks") or []):
            vid = t.get("videoId")
            nm = str(t.get("title") or "").strip()
            if not vid or not nm or nm in ("[Deleted video]", "[Private video]"):
                continue
            items.append({
                "id": vid,
                "title": nm,
                "artist": ", ".join(a.get("name", "") for a in (t.get("artists") or [])),
                "dur": str(t.get("duration") or ""),
                "url": f"https://music.youtube.com/watch?v={vid}",
            })
    except Exception:
        items = []

    if not items:
        try:
            d = _ytdlp_flat(f"https://www.youtube.com/playlist?list={pid}", 60)
            title = str(d.get("title") or pid)
            for e in (d.get("entries") or [])[:int(limit)]:
                vid = e.get("id") or ""
                nm = str(e.get("title") or "").strip()
                if not vid or not nm or nm in ("[Deleted video]", "[Private video]"):
                    continue
                items.append({
                    "id": vid,
                    "title": nm,
                    "artist": str(e.get("uploader") or e.get("channel") or ""),
                    "dur": str(e.get("duration_string") or ""),
                    "url": f"https://music.youtube.com/watch?v={vid}",
                })
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:120], "items": []}

    if not items:
        return {"ok": False, "error": "playlist_empty_or_private", "items": []}

    if save:
        cur = [x for x in ytm_saved_playlists() if x.get("id") != pid]
        cur.insert(0, {"id": pid, "title": title or pid})
        _ytm_playlists_file().parent.mkdir(parents=True, exist_ok=True)
        _ytm_playlists_file().write_text(json.dumps(cur[:30], ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "id": pid, "title": title or pid, "items": items}


def ytm_to_spotify_playlist(url_or_id: str, new_name: str = "") -> dict[str, Any]:
    pl = ytm_get_playlist(url_or_id, limit=100, save=True)
    if not pl.get("ok"):
        return pl
    name = (new_name or "").strip() or f"{pl['title']} (YTM)"
    cr = spotify_playlist_create(name, description="Kami ile YouTube Music'ten aktarıldı")
    if not cr.get("ok"):
        return cr
    sp_pid = ((cr.get("data") or {}).get("id") or "")
    if not sp_pid:
        return {"ok": False, "error": "no_playlist_id"}
    uris: list[str] = []
    for it in pl["items"]:
        q = f"{it['artist']} {it['title']}".strip()
        sr = spotify_search(q, kind="track", limit=1)
        tr = (sr.get("tracks") or [None])[0]
        if tr and tr.get("uri"):
            uris.append(tr["uri"])
    for i in range(0, len(uris), 50):
        spotify_playlist_modify(sp_pid, uris[i:i + 50], remove=False)
    return {"ok": True, "playlist_id": sp_pid, "name": name, "matched": len(uris), "total": len(pl["items"])}


def spotify_control(token: str, action: str) -> dict[str, Any]:
    """Alt cubuk: oynat/duraklat/ileri/geri. v1.35.4: PKCE oturumu (_sp_api) + cihaz secimi + dahili go-librespot."""
    act = str(action or "").lower().strip()
    routes = {"play": ("PUT", "/me/player/play"), "pause": ("PUT", "/me/player/pause"),
              "next": ("POST", "/me/player/next"), "previous": ("POST", "/me/player/previous")}
    if act not in routes:
        return {"ok": False, "error": "bad_action"}
    invalidate_now()
    from app.core import librespot_host
    if librespot_host.is_running() and librespot_host.status().get("active"):
        r = librespot_host.control(act)
        if r.get("ok"):
            return r
    method, path = routes[act]
    if act == "play":
        dev = _sp_pick_device(launch=True)
        if not dev:
            return {"ok": False, "error": "no_device",
                    "message": "Spotify açık bir cihaz bulamadı. Dahili oynatıcıyı eşleştir veya Spotify uygulamasını aç."}
        path += f"?device_id={dev}"
    return _sp_explain(_sp_api(method, path))


def fetch_track_lyrics(title: str, artist: str = "") -> dict[str, Any]:
    t = str(title or "").strip()
    a = str(artist or "").strip()
    if not t:
        return {"ok": False, "lines": [], "plain": "", "word_synced": False}
    try:
        from app.core.lyrics import amll_ttml_find, lrclib_find, parse_elrc_words
        word_lines = amll_ttml_find(a, t)
        if word_lines:
            return {"ok": True, "synced": True, "word_synced": True, "lines": word_lines, "plain": "\n".join(x["text"] for x in word_lines), "source": "amll/elrc"}
        res = lrclib_find(a, t)
        if not res:
            return {"ok": False, "lines": [], "plain": "", "word_synced": False}
        synced_raw = str(res.get("synced") or "").strip()
        plain_raw = str(res.get("plain") or "").strip()
        lines = parse_elrc_words(synced_raw) if synced_raw else []
        word_synced = any(bool(ln.get("words")) for ln in lines)
        return {
            "ok": bool(lines or plain_raw),
            "synced": bool(lines),
            "word_synced": word_synced,
            "lines": lines,
            "plain": plain_raw,
            "source": "lrclib",
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120], "lines": [], "plain": "", "word_synced": False}
