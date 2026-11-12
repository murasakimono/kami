"""Alt surecleri Kami'ye bagla: Kami kapanir ya da coker/sonlandirilirsa onlar da kapansin (Windows Job Object).

Ekran kaydi tamponu (ffmpeg), Cloudflare tuneli, IOPaint sunucusu Kami zorla kapatildiginda arkada kaliyordu.
"""
from __future__ import annotations

import ctypes
import logging
import os
import subprocess
from ctypes import wintypes

log = logging.getLogger("kami")
_JOB = None


def _job():
    global _JOB
    if _JOB is not None or os.name != "nt":
        return _JOB
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class IO(ctypes.Structure):
        _fields_ = [(n, ctypes.c_ulonglong) for n in ("r", "w", "o", "rb", "wb", "ob")]

    class BASIC(ctypes.Structure):
        _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                    ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                    ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                    ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD), ("SchedulingClass", wintypes.DWORD)]

    class EXT(ctypes.Structure):
        _fields_ = [("BasicLimitInformation", BASIC), ("IoInfo", IO), ("ProcessMemoryLimit", ctypes.c_size_t),
                    ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                    ("PeakJobMemoryUsed", ctypes.c_size_t)]
    k32.CreateJobObjectW.restype = wintypes.HANDLE
    h = k32.CreateJobObjectW(None, None)
    if not h:
        return None
    info = EXT()
    info.BasicLimitInformation.LimitFlags = 0x2000   # JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
    if not k32.SetInformationJobObject(h, 9, ctypes.byref(info), ctypes.sizeof(info)):
        return None
    _JOB = h
    return h


def attach(proc: subprocess.Popen) -> subprocess.Popen:
    try:
        h = _job()
        if h:
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.AssignProcessToJobObject(wintypes.HANDLE(h), wintypes.HANDLE(int(proc._handle)))
    except Exception:
        log.debug("Job Object baglanamadi", exc_info=True)
    return proc
