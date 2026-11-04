"""Kilitlenme testi (defter 23): gercek Kami penceresi acikken kopruye art arda magnet + RD + show
istekleri gonderilir; pencere mesaj dongusu (SendMessageTimeout WM_NULL) ve kopru gecikmesi olculur.

    .venv\\Scripts\\python tests\\e2e\\freeze_check.py [sure_sn]

Ayri veri klasoru (KAMI_DATA_DIR) kullanir; gercek ayarlara/kuyruga dokunmaz.
"""
from __future__ import annotations

import ctypes
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.core.winwin import find_window  # noqa: E402

user32 = ctypes.WinDLL("user32")
user32.SendMessageTimeoutW.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM,
                                       wintypes.UINT, wintypes.UINT, ctypes.POINTER(ctypes.c_size_t)]


def post(info, path, body, timeout=30.0):
    req = urllib.request.Request(f"http://127.0.0.1:{info['port']}{path}", data=json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json", "X-Kami-Token": info["token"]},
                                 method="POST")
    t0 = time.monotonic()
    with urllib.request.urlopen(req, timeout=timeout) as r:
        json.loads(r.read())
    return time.monotonic() - t0


def main() -> int:
    duration = float(sys.argv[1]) if len(sys.argv) > 1 else 25.0
    data = Path(tempfile.mkdtemp(prefix="kami_freeze_"))
    env = {**os.environ, "KAMI_DATA_DIR": str(data)}
    proc = subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "python.exe"), "-m", "app.main"], cwd=ROOT, env=env)
    try:
        info_path = data / "bridge.json"
        hwnd = 0
        deadline = time.monotonic() + 40
        while time.monotonic() < deadline and not (info_path.exists() and hwnd):
            time.sleep(0.3)
            if info_path.exists():   # venv python.exe bir baslatici: gercek pid bridge.json'da
                hwnd = find_window("Kami", json.loads(info_path.read_text(encoding="utf-8"))["pid"])
        if not hwnd:
            print("FAIL: pencere acilmadi"); return 1
        info = json.loads(info_path.read_text(encoding="utf-8"))
        time.sleep(3)   # arayuz yuklensin

        lat: dict[str, list[float]] = {}
        errors: list[str] = []
        stop = threading.Event()

        def spam(name, path, body, gap):
            i = 0
            while not stop.is_set():
                i += 1
                b = dict(body)
                if "url" in b and "{i}" in b["url"]:
                    b["url"] = b["url"].replace("{i}", f"{i:040x}"[-40:])
                try:
                    lat.setdefault(name, []).append(post(info, path, b))
                except Exception as exc:
                    errors.append(f"{name}: {exc}")
                stop.wait(gap)

        jobs = [
            ("magnet", "/v1/rd", {"url": "magnet:?xt=urn:btih:{i}&dn=test", "source": "magnet"}, 1.0),
            ("rd", "/v1/rd", {"url": "https://example.com/file{i}.zip"}, 0.7),
            ("show", "/v1/show", {}, 0.4),
            ("ping", "/v1/ping", {}, 0.3),
        ]
        threads = [threading.Thread(target=spam, args=j, daemon=True) for j in jobs]
        for t in threads:
            t.start()

        worst = 0.0
        hung = 0
        t_end = time.monotonic() + duration
        while time.monotonic() < t_end:
            res = ctypes.c_size_t()
            t0 = time.monotonic()
            ok = user32.SendMessageTimeoutW(hwnd, 0, 0, 0, 0x0002, 3000, ctypes.byref(res))  # WM_NULL, ABORTIFHUNG
            dt = time.monotonic() - t0
            worst = max(worst, dt)
            if not ok:
                hung += 1
            time.sleep(0.25)
        stop.set()
        for t in threads:
            t.join(35)

        print(f"Pencere mesaj dongusu: en kotu {worst*1000:.0f} ms, cevapsiz {hung}")
        for name, *_ in jobs:
            v = lat.get(name)
            if not v:
                print(f"  kopru {name}: HIC CEVAP YOK")
                continue
            print(f"  kopru {name}: {len(v)} istek, en kotu {max(v)*1000:.0f} ms, ort {sum(v)/len(v)*1000:.0f} ms")
        log = (data / "kami.log").read_text(encoding="utf-8", errors="replace") if (data / "kami.log").exists() else ""
        stalls = [ln for ln in log.splitlines() if "yanit vermiyor" in ln]
        print(f"  watchdog donma uyarisi: {len(stalls)}; hata: {len(errors)} {errors[:3]}")
        bad = hung or worst > 1.0 or stalls or errors or any(max(v) > 3.0 for k, v in lat.items() if v and k != "rd") or len(lat) < len(jobs)
        print("SONUC:", "FAIL" if bad else "OK")
        return 1 if bad else 0
    finally:
        proc.terminate()
        try:
            proc.wait(10)
        except Exception:
            proc.kill()


if __name__ == "__main__":
    sys.exit(main())
