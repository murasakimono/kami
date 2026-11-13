"""Canli VRAM, NVENC, CPU ve RAM telemetrisi + 6 GB RTX 4050 OOM on-kontrolu."""
from __future__ import annotations

import gc
import logging
import sys
import threading
from typing import Any, Callable

try:
    import psutil  # type: ignore
except Exception:  # pragma: no cover
    psutil = None

try:
    import pynvml  # type: ignore
except Exception:  # pragma: no cover
    pynvml = None

log = logging.getLogger(__name__)

_NVML_LOCK = threading.Lock()
_NVML_READY: bool | None = None

WARN_VRAM_PCT = 80.0
CRIT_VRAM_PCT = 92.0


def _ensure_nvml() -> bool:
    global _NVML_READY
    if pynvml is None:
        return False
    with _NVML_LOCK:
        if _NVML_READY is not None:
            return _NVML_READY
        try:
            pynvml.nvmlInit()
            _NVML_READY = pynvml.nvmlDeviceGetCount() > 0
        except Exception:
            _NVML_READY = False
        return _NVML_READY


def _read_gpu() -> dict[str, Any]:
    if not _ensure_nvml():
        return {
            "gpu_available": False,
            "gpu_name": "",
            "vram_total_mb": 0,
            "vram_used_mb": 0,
            "vram_free_mb": 0,
            "vram_pct": 0.0,
            "gpu_util": 0,
            "enc_util": 0,
        }
    try:
        handle = pynvml.nvmlDeviceGetHandleByIndex(0)
        raw_name = pynvml.nvmlDeviceGetName(handle)
        gpu_name = raw_name.decode("utf-8", "ignore") if isinstance(raw_name, bytes) else str(raw_name)
        mem = pynvml.nvmlDeviceGetMemoryInfo(handle)
        total_mb = int(mem.total // (1024 * 1024))
        used_mb = int(mem.used // (1024 * 1024))
        free_mb = int(mem.free // (1024 * 1024))
        vram_pct = round((used_mb / total_mb) * 100.0, 1) if total_mb else 0.0
        try:
            util = pynvml.nvmlDeviceGetUtilizationRates(handle)
            gpu_util = int(util.gpu)
        except Exception:
            gpu_util = 0
        try:
            enc_util, _ = pynvml.nvmlDeviceGetEncoderUtilization(handle)
            enc_util = int(enc_util)
        except Exception:
            enc_util = 0
        return {
            "gpu_available": True,
            "gpu_name": gpu_name,
            "vram_total_mb": total_mb,
            "vram_used_mb": used_mb,
            "vram_free_mb": free_mb,
            "vram_pct": vram_pct,
            "gpu_util": gpu_util,
            "enc_util": enc_util,
        }
    except Exception:
        log.debug("NVML okuma hatasi", exc_info=True)
        return {
            "gpu_available": False,
            "gpu_name": "",
            "vram_total_mb": 0,
            "vram_used_mb": 0,
            "vram_free_mb": 0,
            "vram_pct": 0.0,
            "gpu_util": 0,
            "enc_util": 0,
        }


def _read_host() -> dict[str, Any]:
    if psutil is None:
        return {"ram_total_mb": 0, "ram_used_mb": 0, "ram_pct": 0.0, "cpu_pct": 0.0}
    try:
        vm = psutil.virtual_memory()
        cpu = psutil.cpu_percent(interval=None)
        return {
            "ram_total_mb": int(vm.total // (1024 * 1024)),
            "ram_used_mb": int(vm.used // (1024 * 1024)),
            "ram_pct": round(float(vm.percent), 1),
            "cpu_pct": round(float(cpu), 1),
        }
    except Exception:
        return {"ram_total_mb": 0, "ram_used_mb": 0, "ram_pct": 0.0, "cpu_pct": 0.0}


def snapshot() -> dict[str, Any]:
    """Anlik GPU/VRAM/NVENC + RAM/CPU durumunu doner."""
    gpu = _read_gpu()
    host = _read_host()
    pct = gpu["vram_pct"] if gpu["gpu_available"] else host["ram_pct"]
    if pct >= CRIT_VRAM_PCT:
        level = "critical"
    elif pct >= WARN_VRAM_PCT:
        level = "warn"
    else:
        level = "ok"
    return {**gpu, **host, "level": level}


def flush_memory(flush_cb: Callable[[], None] | None = None) -> None:
    """Python GC + yuklu ise torch CUDA cache + ozel temizleyiciyi calistirir."""
    gc.collect()
    if flush_cb is not None:
        try:
            flush_cb()
        except Exception:
            log.debug("flush_cb hatasi", exc_info=True)
    torch = sys.modules.get("torch")
    if torch is not None:
        try:
            if torch.cuda.is_available():
                torch.cuda.empty_cache()
        except Exception:
            pass


def preflight(required_mb: int = 1024, flush_cb: Callable[[], None] | None = None) -> dict[str, Any]:
    """GPU/AI gorevi baslamadan once yeterli bos VRAM var mi kontrol eder.

    6 GB RTX 4050 gibi kartlarda OOM onlemek icin gerekirse once bellek temizler;
    hala yetmiyorsa `fallback="cpu"` onerir.
    """
    req = max(0, int(required_mb or 0))
    snap = snapshot()
    if not snap["gpu_available"]:
        return {
            "ok": True,
            "flushed": False,
            "fallback": "cpu",
            "reason": "no_nvidia_gpu",
            "required_mb": req,
            "snapshot": snap,
        }
    if snap["vram_free_mb"] >= req:
        return {
            "ok": True,
            "flushed": False,
            "fallback": None,
            "reason": "ok",
            "required_mb": req,
            "snapshot": snap,
        }
    flush_memory(flush_cb)
    after = snapshot()
    if after["vram_free_mb"] >= req:
        return {
            "ok": True,
            "flushed": True,
            "fallback": None,
            "reason": "flushed_ok",
            "required_mb": req,
            "snapshot": after,
        }
    return {
        "ok": False,
        "flushed": True,
        "fallback": "cpu",
        "reason": "vram_low",
        "required_mb": req,
        "snapshot": after,
    }
