"""Performans izleyici (v1.30): Kami surec agaci (Kami + WebView2 + aria2 + ffmpeg + yt-dlp + yapay zeka alt surecleri)
ve sistem: CPU, RAM, disk G/C, ag, GPU (nvidia-smi varsa). Ucuz: 1 sn'de bir cagrilir, psutil cpu_percent araliksiz."""
from __future__ import annotations

import os
import shutil
import subprocess
import time
from typing import Any

import psutil

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
_prev: dict[str, Any] = {}
_procs: dict[int, psutil.Process] = {}
_gpu: dict[str, Any] = {"t": 0.0, "v": None}


def _group(name: str, cmd: str) -> str:
    n = name.lower()
    if "msedgewebview2" in n:
        return "Arayüz (WebView2)"
    if "aria2" in n:
        return "aria2 (indirme)"
    if "ffmpeg" in n or "ffprobe" in n:
        return "ffmpeg"
    if "yt-dlp" in cmd or "yt_dlp" in cmd:
        return "yt-dlp"
    if "media-env" in cmd or "whisper" in cmd or "uvr" in cmd or "iopaint" in cmd or "ncnn" in cmd:
        return "Yapay zekâ"
    if n.startswith("kami") or "python" in n:
        return "Kami"
    return name


def _gpu_stats() -> dict[str, Any] | None:
    if time.time() - _gpu["t"] < 3:
        return _gpu["v"]
    _gpu["t"] = time.time()
    exe = shutil.which("nvidia-smi")
    if not exe:
        _gpu["v"] = None
        return None
    try:
        r = subprocess.run([exe, "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name", "--format=csv,noheader,nounits"],
                           capture_output=True, text=True, timeout=3, creationflags=NO_WINDOW)
        u, mu, mt, tmp, name = [x.strip() for x in r.stdout.splitlines()[0].split(",")[:5]]
        _gpu["v"] = {"util": float(u), "mem": float(mu), "mem_total": float(mt), "temp": float(tmp), "name": name}
    except Exception:
        _gpu["v"] = None
    return _gpu["v"]


def snapshot(dl_speed: int = 0) -> dict[str, Any]:
    me = psutil.Process(os.getpid())
    tree = [me] + me.children(recursive=True)
    groups: dict[str, dict[str, float]] = {}
    alive = set()
    for p in tree:
        try:
            pp = _procs.get(p.pid)
            if pp is None:
                pp = _procs[p.pid] = p
                pp.cpu_percent(None)   # ilk olcum taban
            alive.add(p.pid)
            with pp.oneshot():
                g = _group(pp.name(), " ".join(pp.cmdline()[:4]) if pp.pid != me.pid else "")
                e = groups.setdefault(g, {"cpu": 0.0, "mem": 0.0, "n": 0})
                e["cpu"] += pp.cpu_percent(None) / max(1, psutil.cpu_count() or 1)
                e["mem"] += pp.memory_info().rss
                e["n"] += 1
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            continue
    for pid in list(_procs):
        if pid not in alive:
            _procs.pop(pid, None)
    now = time.time()
    io, net = psutil.disk_io_counters(), psutil.net_io_counters()
    rates = {"disk_r": 0.0, "disk_w": 0.0, "net_rx": 0.0, "net_tx": 0.0}
    if _prev and io and net:
        dt = max(0.2, now - _prev["t"])
        rates = {"disk_r": (io.read_bytes - _prev["dr"]) / dt, "disk_w": (io.write_bytes - _prev["dw"]) / dt,
                 "net_rx": (net.bytes_recv - _prev["nr"]) / dt, "net_tx": (net.bytes_sent - _prev["nt"]) / dt}
    if io and net:
        _prev.update(t=now, dr=io.read_bytes, dw=io.write_bytes, nr=net.bytes_recv, nt=net.bytes_sent)
    vm = psutil.virtual_memory()
    kami_cpu = sum(v["cpu"] for v in groups.values())
    kami_mem = sum(v["mem"] for v in groups.values())
    return {"cpu": psutil.cpu_percent(None), "ram": vm.percent, "ram_used": vm.used, "ram_total": vm.total,
            "kami_cpu": round(kami_cpu, 1), "kami_mem": kami_mem, "dl_speed": dl_speed, **{k: round(v) for k, v in rates.items()},
            "groups": sorted(({"name": k, "cpu": round(v["cpu"], 1), "mem": v["mem"], "n": v["n"]} for k, v in groups.items()), key=lambda x: -x["mem"]),
            "gpu": _gpu_stats()}
