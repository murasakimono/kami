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


def forward(msg: dict, info_path: Path | None = None, timeout: float | None = None) -> dict:
    route = ROUTES.get(str(msg.get("type", "")))
    if timeout is None:   # RD istegi RD'nin cevabini bekler (kopru en fazla 20 sn)
        timeout = 25.0 if msg.get("type") == "rd" else 8.0
    if not route:
        return {"ok": False, "error": "unknown_type"}
    info_path = info_path or BRIDGE_INFO
    try:
        info = json.loads(info_path.read_text(encoding="utf-8"))
        port = int(info["port"])
        token = str(info["token"])
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return {"ok": False, "error": "offline", "detail": f"bridge.json okunamadi ({info_path}): {type(exc).__name__}"}
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
