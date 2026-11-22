"""Opsiyonel libmpv / mpv oynatma motoru (MKV/HEVC/10-bit/ASS donanim cozumu).

Varsayilan oynatici HTML5'tir; kullanici Ayarlar'dan 'libmpv' sectiginde ve ikili mevcutsa
bu motor devreye girer.
"""
from __future__ import annotations

import json
import logging
import os
import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0


def _search_dirs() -> list[Path]:
    dirs = [
        paths.DATA_DIR / "bin" / "mpv",
        paths.BASE_DIR / "bin" / "mpv",
        paths.BASE_DIR / "bin",
        Path(r"C:\Program Files\mpv"),
        Path(r"C:\Program Files (x86)\mpv"),
    ]
    return [d for d in dirs if d.is_dir()]


def find_mpv() -> dict[str, str]:
    """Sistemde kurulu mpv.exe ve libmpv-2.dll yollarini bulur."""
    exe = shutil.which("mpv") or ""
    dll = ""
    for d in _search_dirs():
        if not exe:
            cand = d / ("mpv.exe" if os.name == "nt" else "mpv")
            if cand.is_file():
                exe = str(cand)
        if not dll:
            for dname in ("libmpv-2.dll", "mpv-2.dll", "mpv-1.dll"):
                dcand = d / dname
                if dcand.is_file():
                    dll = str(dcand)
                    break
    return {"exe": exe, "dll": dll}


class MpvController:
    """mpv.exe JSON IPC (Windows named pipe) uzerinden hafif oynatici denetimi."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._proc: subprocess.Popen | None = None
        self._pipe = f"\\\\.\\pipe\\kami-mpv-{os.getpid()}" if os.name == "nt" else f"/tmp/kami-mpv-{os.getpid()}.sock"
        self._current_path = ""
        self._playing = False

    def status(self, settings: Any = None) -> dict[str, Any]:
        found = find_mpv()
        eng = str(settings.get("player_engine", "html5") if settings else "html5")
        alive = bool(self._proc is not None and self._proc.poll() is None)
        if not alive:
            self._playing = False
        return {
            "ok": True,
            "available": bool(found["exe"] or found["dll"]),
            "exe": found["exe"],
            "dll": found["dll"],
            "engine": eng,
            "running": alive,
            "playing": self._playing and alive,
            "path": self._current_path if alive else "",
        }

    def play(self, path: str, start: float = 0.0, rate: float = 1.0, volume: float = 100.0) -> dict[str, Any]:
        found = find_mpv()
        exe = found["exe"]
        if not exe:
            return {"ok": False, "error": "mpv_not_installed"}
        src = str(path or "").strip()
        if not src:
            return {"ok": False, "error": "empty_path"}

        with self._lock:
            alive = self._proc is not None and self._proc.poll() is None
            if alive and self._send_ipc(["loadfile", src, "replace"]):
                if start and start > 0:
                    self._send_ipc(["seek", float(start), "absolute"])
                if rate and rate != 1.0:
                    self._send_ipc(["set_property", "speed", float(rate)])
                self._current_path = src
                self._playing = True
                return {"ok": True, "engine": "libmpv", "reused": True}

            self._stop_locked()
            args = [
                exe,
                "--hwdec=auto-safe",
                "--keep-open=yes",
                "--force-window=yes",
                f"--input-ipc-server={self._pipe}",
                f"--speed={max(0.25, min(4.0, float(rate or 1.0)))}",
                f"--volume={max(0.0, min(150.0, float(volume or 100.0)))}",
            ]
            if start and start > 0:
                args.append(f"--start={float(start):.2f}")
            args.append(src)
            try:
                self._proc = subprocess.Popen(args, creationflags=NO_WINDOW)
                self._current_path = src
                self._playing = True
                return {"ok": True, "engine": "libmpv", "reused": False}
            except Exception as exc:
                log.exception("mpv baslatilamadi")
                return {"ok": False, "error": str(exc)[:140]}

    def _send_ipc(self, cmd: list[Any]) -> bool:
        if os.name != "nt":
            return False
        try:
            payload = (json.dumps({"command": cmd}) + "\n").encode("utf-8")
            with open(self._pipe, "wb", buffering=0) as f:
                f.write(payload)
            return True
        except OSError:
            return False

    def command(self, cmd: list[Any]) -> dict[str, Any]:
        with self._lock:
            if self._proc is None or self._proc.poll() is not None:
                return {"ok": False, "error": "not_running"}
            ok = self._send_ipc(cmd)
            if cmd and cmd[0] == "cycle" and len(cmd) > 1 and cmd[1] == "pause":
                self._playing = not self._playing
            return {"ok": ok}

    def _stop_locked(self) -> None:
        if self._proc is not None:
            try:
                self._send_ipc(["quit"])
                self._proc.wait(timeout=1.5)
            except Exception:
                try:
                    self._proc.terminate()
                except Exception:
                    pass
            self._proc = None
        self._playing = False
        self._current_path = ""

    def stop(self) -> None:
        with self._lock:
            self._stop_locked()


def install_mpv() -> dict[str, Any]:
    """Windows icin resmi mpv paketini DATA_DIR/bin/mpv altina indirip acar."""
    import requests
    dest = paths.DATA_DIR / "bin" / "mpv"
    dest.mkdir(parents=True, exist_ok=True)
    api_url = "https://api.github.com/repos/shinchiro/mpv-winbuild-cmake/releases/latest"
    try:
        r = requests.get(api_url, timeout=20, headers={"User-Agent": "Kami-Media"})
        r.raise_for_status()
        assets = r.json().get("assets") or []
        cand = next((a for a in assets if "mpv-x86_64-" in (a.get("name") or "") and a["name"].endswith(".7z") and "-v3-" not in a["name"]), None)
        if not cand:
            cand = next((a for a in assets if "mpv-x86_64-" in (a.get("name") or "") and a["name"].endswith(".7z")), None)
        if not cand:
            return {"ok": False, "error": "no_release_asset"}
        arc = dest / cand["name"]
        with requests.get(cand["browser_download_url"], stream=True, timeout=60) as dl:
            dl.raise_for_status()
            with open(arc, "wb") as f:
                for ch in dl.iter_content(256 * 1024):
                    if ch:
                        f.write(ch)
        try:
            import py7zr
            with py7zr.SevenZipFile(arc, mode="r") as z:
                z.extractall(path=dest)
        except ImportError:
            sz = shutil.which("7z") or r"C:\Program Files\7-Zip\7z.exe"
            if not Path(sz).is_file():
                return {"ok": False, "error": "need_py7zr_or_7zip"}
            subprocess.run([sz, "x", "-y", f"-o{dest}", str(arc)], check=True, creationflags=NO_WINDOW)
        try:
            arc.unlink()
        except OSError:
            pass
        found = find_mpv()
        return {"ok": bool(found["exe"] or found["dll"]), **found}
    except Exception as exc:
        log.exception("mpv kurulum hatasi")
        return {"ok": False, "error": str(exc)[:160]}


CONTROLLER = MpvController()
