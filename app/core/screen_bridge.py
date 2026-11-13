"""Faz 16.1 — Kablosuz Ekran Yansitma (UxPlay AirPlay & scrcpy Android) Koprusu.

Mevcut phone.py (iPhone Kestirmesi -> link gonderme) korunur; bu modul canli ekran yansitma & kaydi yonetir.
"""
from __future__ import annotations

import logging
import shutil
import subprocess
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PROCS: dict[str, subprocess.Popen] = {}


def find_mirror_bins() -> dict[str, str]:
    return {
        "scrcpy": shutil.which("scrcpy") or shutil.which("scrcpy.exe") or "",
        "uxplay": shutil.which("uxplay") or shutil.which("uxplay.exe") or "",
    }


def mirror_status() -> dict[str, Any]:
    bins = find_mirror_bins()
    running = {k: (p.poll() is None) for k, p in _PROCS.items() if p is not None}
    return {
        "ok": True,
        "scrcpy_installed": bool(bins["scrcpy"]),
        "uxplay_installed": bool(bins["uxplay"]),
        "running": running,
    }


def start_mirror(kind: str = "scrcpy", *, record_path: str = "", window_title: str = "Kami Kopru") -> dict[str, Any]:
    k = (kind or "scrcpy").strip().lower()
    if k not in ("scrcpy", "uxplay"):
        return {"ok": False, "error": "Desteklenen tur: scrcpy veya uxplay"}

    cur = _PROCS.get(k)
    if cur is not None and cur.poll() is None:
        return {"ok": True, "kind": k, "already_running": True, "pid": cur.pid}

    exe = find_mirror_bins().get(k, "")
    if not exe:
        return {"ok": False, "error": f"{k} kurulu degil (PATH uzerinde bulunamadi)"}

    if k == "scrcpy":
        cmd = [exe, "--window-title", window_title]
        if record_path:
            Path(record_path).parent.mkdir(parents=True, exist_ok=True)
            cmd += ["--record", str(record_path)]
    else:
        cmd = [exe, "-n", window_title]

    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, creationflags=NO_WINDOW)
        _PROCS[k] = proc
        return {"ok": True, "kind": k, "pid": proc.pid, "record_path": record_path}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def stop_mirror(kind: str = "") -> dict[str, Any]:
    targets = [kind.lower()] if kind else list(_PROCS.keys())
    stopped: list[str] = []
    for k in targets:
        p = _PROCS.pop(k, None)
        if p is not None and p.poll() is None:
            try:
                p.terminate()
                p.wait(timeout=3)
            except Exception:
                p.kill()
            stopped.append(k)
    return {"ok": True, "stopped": stopped}
