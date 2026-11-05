"""Kami native messaging relay.

Tarayici eklentisi -> (stdin: 4 bayt uzunluk + JSON) -> bu betik -> 127.0.0.1 kopru -> Kami
Yanit ayni yoldan geri doner. Hizli acilsin diye yalnizca stdlib kullanir, app paketini yuklemez.

Mesajlar:  {"type": "ping"} | {"type": "add", ...indirme bilgisi} | {"type": "show"} | {"type": "media", url, mode}
Kami kapaliysa: {"ok": false, "error": "offline"}  -> eklenti indirmeyi tarayiciya birakir.
"""
from __future__ import annotations

import json
import os
import struct
import sys
import urllib.error
import urllib.request
from pathlib import Path

if getattr(sys, "frozen", False):   # kurulu Kami: kami_host.exe; veri %LOCALAPPDATA%\Kami\data
    _DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "Kami" / "data"
else:
    _DATA = Path(__file__).resolve().parent.parent / "data"
BRIDGE_INFO = Path(os.environ.get("KAMI_BRIDGE_INFO") or _DATA / "bridge.json")  # e2e testleri icin
MAX_IN = 8 * 1024 * 1024        # tarayicidan gelen tek mesaj icin makul ust sinir
ROUTES = {"ping": "/v1/ping", "add": "/v1/add", "show": "/v1/show", "set_capture": "/v1/capture",
          "media": "/v1/media", "cookies": "/v1/cookies", "rd": "/v1/rd"}


def _binary_stdio() -> None:
    if os.name == "nt":
        import msvcrt
        msvcrt.setmode(sys.stdin.fileno(), os.O_BINARY)
        msvcrt.setmode(sys.stdout.fileno(), os.O_BINARY)


def read_message(stream) -> dict | None:
    raw_len = stream.read(4)
    if len(raw_len) < 4:
        return None
    (length,) = struct.unpack("<I", raw_len)
    if length > MAX_IN:
        raise ValueError("mesaj cok buyuk")
    data = stream.read(length)
    return json.loads(data.decode("utf-8"))


def write_message(stream, payload: dict) -> None:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    stream.write(struct.pack("<I", len(data)))
    stream.write(data)
    stream.flush()


def _hlog(text: str) -> None:
    """host.log: Brave'in basLattigi host'un ortami/hatalari (DATA yazilamazsa %TEMP%). 200 KB'i asinca sifirlanir."""
    import time
    for d in (_DATA, Path(os.environ.get("TEMP") or "."),):
        try:
            d.mkdir(parents=True, exist_ok=True)
            f = d / ("host.log" if d == _DATA else "kami_host.log")
            if f.exists() and f.stat().st_size > 200_000:
                f.unlink()
            with open(f, "a", encoding="utf-8") as fh:
                fh.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} pid={os.getpid()} {text}\n")
            return
        except OSError:
            continue


def _env_dump() -> str:
    keys = ("LOCALAPPDATA", "USERPROFILE", "APPDATA", "TEMP", "USERNAME")
    env = {k: os.environ.get(k) for k in keys}
    env.update({k: v for k, v in os.environ.items() if k.startswith("KAMI_")})
    parent = BRIDGE_INFO.parent
    try:
        listing = os.listdir(parent)
    except OSError as exc:
        listing = f"{exc!r}"
    return (f"exe={sys.executable} cwd={os.getcwd()} env={env} info={BRIDGE_INFO} exists={BRIDGE_INFO.exists()} "
            f"dir_list={listing}")


def _read_registry() -> dict | None:
    """Kami kopru bilgisini HKCU/Software/Kami/Bridge/Info (REG_SZ JSON) olarak da yazar: dosyaya bagimli olma."""
    if os.name != "nt":
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Kami\Bridge") as k:
            return json.loads(winreg.QueryValueEx(k, "Info")[0])
    except (OSError, ValueError, ImportError):
        return None


def _load_info(info_path: Path) -> dict:
    try:
        return json.loads(info_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        _hlog(f"bridge dosyasi okunamadi: {exc!r} errno={getattr(exc, 'errno', None)} "
              f"winerror={getattr(exc, 'winerror', None)} path={info_path}")
        if info_path == BRIDGE_INFO:
            reg = _read_registry()
            if reg and "port" in reg and "token" in reg:
                _hlog("registry'den okundu")
                return reg
            _hlog("registry de bos")
        raise


def forward(msg: dict, info_path: Path | None = None, timeout: float | None = None) -> dict:
    route = ROUTES.get(str(msg.get("type", "")))
    if timeout is None:   # RD istegi RD'nin cevabini bekler (kopru en fazla 20 sn)
        timeout = 25.0 if msg.get("type") == "rd" else 8.0
    if not route:
        return {"ok": False, "error": "unknown_type"}
    info_path = info_path or BRIDGE_INFO
    try:
        info = _load_info(info_path)
        port = int(info["port"])
        token = str(info["token"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": "offline", "detail": f"bridge.json okunamadi ({info_path}): {type(exc).__name__}: {str(exc)[:100]}"}
    body = {k: v for k, v in msg.items() if k != "type"}
    req = urllib.request.Request(
        f"http://127.0.0.1:{port}{route}",
        data=json.dumps(body).encode("utf-8"),
        headers={"Content-Type": "application/json", "X-Kami-Token": token},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            return json.loads(exc.read())
        except ValueError:
            return {"ok": False, "error": f"http_{exc.code}"}
    except (OSError, ValueError) as exc:
        return {"ok": False, "error": "offline",
                "detail": f"Kami'ye baglanilamadi (127.0.0.1:{port}, pid {info.get('pid')}): {type(exc).__name__}: {str(exc)[:120]}"}


def main() -> int:
    _binary_stdio()
    _hlog("basladi " + _env_dump())
    stdin, stdout = sys.stdin.buffer, sys.stdout.buffer
    # sendNativeMessage tek mesaj gonderir; connectNative ise surekli baglanti tutar. Ikisini de destekle.
    while True:
        try:
            msg = read_message(stdin)
        except (ValueError, json.JSONDecodeError) as exc:
            write_message(stdout, {"ok": False, "error": f"bad_message: {exc}"})
            return 1
        if msg is None:
            return 0
        try:
            res = forward(msg)
        except Exception as exc:   # host cokmesin: eklenti nedenini gorsun
            res = {"ok": False, "error": "offline", "detail": f"host hatasi: {type(exc).__name__}: {str(exc)[:120]}"}
        write_message(stdout, res)


if __name__ == "__main__":
    sys.exit(main())
