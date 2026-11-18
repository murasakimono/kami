"""Windows gorev cubugu ilerleme cubugu (ITaskbarList3 via ctypes COM).

Kullanici penceresi arkadayken aktif indirme yuzdesini ve durumunu (yesil/sari/kirmizi) gosterir.
"""
from __future__ import annotations

import sys
from typing import Any

# TBPF flags (Win32 ShObjIdl_core.h)
TBPF_NOPROGRESS = 0x0
TBPF_INDETERMINATE = 0x1
TBPF_NORMAL = 0x2
TBPF_ERROR = 0x4
TBPF_PAUSED = 0x8

_STATE_MAP = {
    "none": TBPF_NOPROGRESS,
    "indeterminate": TBPF_INDETERMINATE,
    "normal": TBPF_NORMAL,
    "error": TBPF_ERROR,
    "paused": TBPF_PAUSED,
}

_TBL: Any = None


def _get_tbl():
    global _TBL
    if sys.platform != "win32":
        return None
    if _TBL is not None:
        return _TBL
    try:
        import ctypes
        from ctypes import wintypes

        class GUID(ctypes.Structure):
            _fields_ = [("Data1", wintypes.DWORD), ("Data2", wintypes.WORD),
                        ("Data3", wintypes.WORD), ("Data4", ctypes.c_ubyte * 8)]

        def _guid(s: str) -> GUID:
            import uuid
            u = uuid.UUID(s)
            b = u.bytes_le
            return GUID.from_buffer_copy(b)

        ole32 = ctypes.windll.ole32
        ole32.CoInitializeEx(None, 0x2)  # COINIT_APARTMENTTHREADED
        clsid = _guid("{56FDF344-FD6D-11D0-958A-006097C9A090}")
        iid = _guid("{EA1AFB91-9E28-4B86-90E9-9E9F8A5EEFAF}")
        ptr = ctypes.c_void_p()
        hr = ole32.CoCreateInstance(ctypes.byref(clsid), None, 1, ctypes.byref(iid), ctypes.byref(ptr))
        if hr != 0 or not ptr.value:
            return None
        vtable = ctypes.cast(ctypes.cast(ptr, ctypes.POINTER(ctypes.c_void_p))[0], ctypes.POINTER(ctypes.c_void_p))
        hr_init = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p)(vtable[3])
        hr_init(ptr)
        set_val = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_uint64, ctypes.c_uint64)(vtable[9])
        set_state = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, ctypes.c_int)(vtable[10])
        _TBL = (ptr, set_val, set_state)
        return _TBL
    except Exception:
        return None


def set_progress(hwnd: int, pct: int = 0, state: str = "none") -> bool:
    if sys.platform != "win32" or not hwnd:
        return False
    tbl = _get_tbl()
    if not tbl:
        return False
    ptr, set_val, set_state = tbl
    flag = _STATE_MAP.get(str(state or "none").lower(), TBPF_NOPROGRESS)
    try:
        set_state(ptr, int(hwnd), int(flag))
        if flag in (TBPF_NORMAL, TBPF_PAUSED, TBPF_ERROR):
            v = max(0, min(100, int(pct)))
            set_val(ptr, int(hwnd), v, 100)
        return True
    except Exception:
        return False
