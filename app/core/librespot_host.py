"""Dahili Spotify Connect calici (go-librespot): harici Spotify istemcisi acmadan ses calar."""
from __future__ import annotations

import atexit
import json
import logging
import os
import shutil
import socket
import subprocess
import tarfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)

_LATEST_WIN_URL = (
    "https://github.com/devgianlu/go-librespot/releases/download/v0.10.6/"
    "go-librespot_windows_amd64.tar.gz"
)
_LOCK = threading.RLock()
_PROC: subprocess.Popen[bytes] | None = None
_PORT: int = 0
_PAIR_CACHE: dict[str, Any] = {}


def find_binary() -> str:
    """Paketlenmis veya indirilmis go-librespot.exe yolunu dondurur."""
    for p in (
        paths.BIN_DIR / "go-librespot.exe",
        paths.DATA_DIR / "bin" / "go-librespot.exe",
    ):
        if p.is_file():
            return str(p)
    w = shutil.which("go-librespot")
    return w or ""


def ensure_binary() -> str:
    """Binary yoksa GitHub son surumunden DATA_DIR/bin altina indirir."""
    exe = find_binary()
    if exe:
        return exe
    dest_dir = paths.DATA_DIR / "bin"
    dest_dir.mkdir(parents=True, exist_ok=True)
    tgz = dest_dir / "go-librespot.tar.gz.tmp"
    dest = dest_dir / "go-librespot.exe"
    try:
        req = urllib.request.Request(_LATEST_WIN_URL, headers={"User-Agent": "Kami"})
        with urllib.request.urlopen(req, timeout=30) as resp, open(tgz, "wb") as f:
            shutil.copyfileobj(resp, f)
        with tarfile.open(tgz, "r:gz") as tf:
            member = next((m for m in tf.getmembers() if m.name.endswith("go-librespot.exe")), None)
            if not member:
                return ""
            src = tf.extractfile(member)
            if not src:
                return ""
            tmp_exe = dest_dir / "go-librespot.exe.tmp"
            with src, open(tmp_exe, "wb") as out:
                shutil.copyfileobj(src, out)
            os.replace(tmp_exe, dest)
        return str(dest) if dest.is_file() else ""
    except Exception:
        log.debug("go-librespot indirilemedi", exc_info=True)
        return ""
    finally:
        try:
            if tgz.exists():
                tgz.unlink()
        except OSError:
            pass


def _config_dir() -> Path:
    d = paths.DATA_DIR / "go-librespot"
    d.mkdir(parents=True, exist_ok=True)
    return d


def has_credentials() -> bool:
    """state.json icinde kalici Spotify kimlik bilgisi kayitli mi?"""
    sf = _config_dir() / "state.json"
    if not sf.is_file():
        return False
    try:
        data = json.loads(sf.read_text(encoding="utf-8"))
        creds = data.get("credentials") or {}
        return bool(creds.get("username") and creds.get("data"))
    except Exception:
        return False


def _pick_port() -> int:
    for p in (3678, 0):
        try:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
                s.bind(("127.0.0.1", p))
                return int(s.getsockname()[1])
        except OSError:
            continue
    return 3678


def _write_config(port: int, zeroconf: bool = False) -> Path:
    cfg_dir = _config_dir()
    cfg_path = cfg_dir / "config.yml"
    # device_auth: tarayicida tek seferlik spotify.com/pair eslestirmesi -> state.json'a kalici yazilir;
    # zeroconf varsayilan kapali: ortak agdaki baskalari hoparloru gormesin.
    zc = "true" if zeroconf else "false"
    text = (
        'device_name: "Kami"\n'
        'device_type: "computer"\n'
        'audio_backend: "wasapi"\n'
        "bitrate: 320\n"
        f"zeroconf_enabled: {zc}\n"
        'zeroconf_backend: "builtin"\n'
        "server:\n"
        "  enabled: true\n"
        '  address: "127.0.0.1"\n'
        f"  port: {int(port)}\n"
        "cache:\n"
        "  enabled: true\n"
        '  size_limit: "512MB"\n'
        "credentials:\n"
        '  type: "device_auth"\n'
    )
    cfg_path.write_text(text, encoding="utf-8")
    return cfg_path


def _api(method: str, path: str, body: dict[str, Any] | None = None, timeout: float = 4.0) -> dict[str, Any]:
    if not _PORT:
        return {"ok": False, "status": 0, "error": "not_running"}
    url = f"http://127.0.0.1:{_PORT}{path}"
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8", errors="replace").strip()
            parsed = json.loads(raw) if raw else {}
            return {"ok": True, "status": resp.status, "data": parsed}
    except urllib.error.HTTPError as exc:
        err = ""
        try:
            err = exc.read().decode("utf-8", errors="replace").strip()
        except Exception:
            pass
        return {"ok": False, "status": exc.code, "error": err or f"HTTP {exc.code}"}
    except Exception as exc:
        return {"ok": False, "status": 0, "error": str(exc)[:120]}


def is_running() -> bool:
    return _PROC is not None and _PROC.poll() is None and _PORT > 0


def ensure_started(download: bool = False) -> dict[str, Any]:
    """go-librespot arka plan surecini baslatir ve HTTP API hazir olana dek bekler."""
    global _PROC, _PORT
    with _LOCK:
        if is_running():
            return {"ok": True, "port": _PORT}
        exe = ensure_binary() if download else find_binary()
        if not exe:
            return {"ok": False, "error": "binary_missing"}
        _PORT = _pick_port()
        cfg_dir = _config_dir()
        _write_config(_PORT)
        log_file = cfg_dir / "librespot.log"
        creation = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        try:
            lf = open(log_file, "ab")
            _PROC = subprocess.Popen(
                [exe, "--config_dir", str(cfg_dir)],
                stdout=lf,
                stderr=subprocess.STDOUT,
                creationflags=creation,
            )
            lf.close()
        except Exception as exc:
            _PROC = None
            _PORT = 0
            return {"ok": False, "error": str(exc)[:120]}

    # API sunucusu ayaga kalkana kadar kisa bekleme (en cok ~3 sn)
    deadline = time.monotonic() + 3.0
    while time.monotonic() < deadline:
        if _PROC is None or _PROC.poll() is not None:
            return {"ok": False, "error": "process_exited"}
        r = _api("GET", "/", timeout=0.6)
        if r.get("status") in (200, 204):
            return {"ok": True, "port": _PORT}
        time.sleep(0.15)
    return {"ok": is_running(), "port": _PORT}


def stop() -> None:
    """Uygulama kapanirken dahili go-librespot surecini kapatir."""
    global _PROC, _PORT
    with _LOCK:
        p = _PROC
        _PROC = None
        _PORT = 0
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=2.0)
            except Exception:
                try:
                    p.kill()
                except Exception:
                    pass


atexit.register(stop)


def reset_credentials() -> dict[str, Any]:
    """Kayitli state.json kimligini temizler ve yeniden eslestirme icin sureci yeniden baslatir."""
    stop()
    sf = _config_dir() / "state.json"
    try:
        if sf.is_file():
            sf.unlink()
    except OSError:
        pass
    _PAIR_CACHE.clear()
    return ensure_started(download=False)


def status() -> dict[str, Any]:
    """Dahili oynatici durumunu + eslestirme gerekiyorsa pairing URL/kodunu dondurur."""
    exe = find_binary()
    if not exe:
        return {"ok": False, "installed": False, "running": False, "paired": False}
    if not is_running():
        st = ensure_started(download=False)
        if not st.get("ok"):
            return {"ok": False, "installed": True, "running": False, "paired": has_credentials(),
                    "error": st.get("error", "")}

    r = _api("GET", "/status", timeout=1.5)
    if r.get("ok") and isinstance(r.get("data"), dict) and r["data"].get("username"):
        d = r["data"]
        _PAIR_CACHE.clear()
        return {
            "ok": True,
            "installed": True,
            "running": True,
            "paired": True,
            "active": not d.get("stopped", True),
            "device_id": d.get("device_id", ""),
            "device_name": d.get("device_name", "Kami"),
            "username": d.get("username", ""),
            "data": d,
        }

    # Aktif oturum yoksa /auth/code veya state.json kontrol et
    ac = _api("GET", "/auth/code", timeout=1.5)
    if ac.get("ok") and isinstance(ac.get("data"), dict) and ac["data"].get("url"):
        _PAIR_CACHE.update(ac["data"])
        return {
            "ok": True,
            "installed": True,
            "running": True,
            "paired": False,
            "pair_url": ac["data"].get("url", ""),
            "pair_code": ac["data"].get("code", ""),
            "expires_at": ac["data"].get("expires_at", ""),
        }

    # state.json olmadan 'paired' sayma (HTTP / 200 donse bile eslesmemis olabilir)
    paired = has_credentials()
    return {
        "ok": True,
        "installed": True,
        "running": True,
        "paired": paired,
        "device_name": "Kami",
        "pair_url": _PAIR_CACHE.get("url", "") if not paired else "",
        "pair_code": _PAIR_CACHE.get("code", "") if not paired else "",
    }


def play_uri(uri: str = "", context_uri: str = "", position_ms: int = 0) -> dict[str, Any]:
    """Dogrudan go-librespot /player/play uzerinden calar (harici Spotify uygulamasi gerekmez)."""
    st = status()
    if not st.get("running"):
        return {"ok": False, "error": "not_running"}
    if not st.get("paired"):
        return {
            "ok": False,
            "error": "librespot_pair",
            "pair_url": st.get("pair_url", ""),
            "pair_code": st.get("pair_code", ""),
            "message": "Dahili Spotify oynatıcıyı 1 kez eşleştir (spotify.com/pair).",
        }
    body: dict[str, Any] = {}
    if context_uri:
        body["uri"] = context_uri
        if uri:
            body["skip_to_uri"] = uri
    elif uri:
        body["uri"] = uri
    else:
        return {"ok": False, "error": "empty_uri"}
    if position_ms > 0:
        body["position"] = int(position_ms)
    r = _api("POST", "/player/play", body, timeout=8.0)
    if r.get("ok"):
        return {"ok": True, "local_librespot": True}
    return {"ok": False, "error": r.get("error") or "play_failed"}


def control(action: str) -> dict[str, Any]:
    routes = {
        "play": "/player/resume",
        "pause": "/player/pause",
        "next": "/player/next",
        "previous": "/player/prev",
        "toggle": "/player/playpause",
    }
    ep = routes.get(str(action or "").lower().strip())
    if not ep:
        return {"ok": False, "error": "bad_action"}
    r = _api("POST", ep, timeout=3.0)
    return {"ok": bool(r.get("ok")), "error": r.get("error", "")}


def set_volume(percent: int) -> dict[str, Any]:
    v = max(0, min(100, int(percent)))
    r = _api("POST", "/player/volume", {"volume": v}, timeout=3.0)
    return {"ok": bool(r.get("ok"))}


def seek(position_ms: int) -> dict[str, Any]:
    r = _api("POST", "/player/seek", {"position": max(0, int(position_ms))}, timeout=3.0)
    return {"ok": bool(r.get("ok"))}


def queue_add(uri: str) -> dict[str, Any]:
    r = _api("POST", "/player/add_to_queue", {"uri": str(uri or "")}, timeout=3.0)
    return {"ok": bool(r.get("ok"))}
