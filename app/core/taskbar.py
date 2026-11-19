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
_TBL_EXTRA: Any = None
_ADDED_THUMBS: set[int] = set()
_WNDPROCS: dict[int, tuple[Any, Any, Any]] = {}


def _get_tbl():
    global _TBL, _TBL_EXTRA
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
        thumb_add = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, wintypes.UINT, ctypes.c_void_p)(vtable[15])
        thumb_upd = ctypes.WINFUNCTYPE(ctypes.c_long, ctypes.c_void_p, wintypes.HWND, wintypes.UINT, ctypes.c_void_p)(vtable[16])
        _TBL = (ptr, set_val, set_state)
        _TBL_EXTRA = (ptr, thumb_add, thumb_upd)
        return _TBL
    except Exception:
        return None


def _make_glyph_hicon(kind: str) -> int:
    """16x16 temiz BGRA HICON uretir (prev | play | pause | next)."""
    import ctypes
    from ctypes import wintypes
    u32, gdi = ctypes.windll.user32, ctypes.windll.gdi32
    W = H = 16
    px = bytearray(W * H * 4)

    def put(x: int, y: int, b: int = 246, g: int = 233, r: int = 237, a: int = 255) -> None:
        if 0 <= x < W and 0 <= y < H:
            o = (y * W + x) * 4
            px[o], px[o + 1], px[o + 2], px[o + 3] = b, g, r, a

    def rect(x0: int, y0: int, x1: int, y1: int, col=(246, 233, 237)) -> None:
        for y in range(y0, y1):
            for x in range(x0, x1):
                put(x, y, *col)

    if kind == "prev":
        rect(3, 3, 5, 13)
        for i in range(6):
            for y in range(8 - i, 8 + i + 1):
                put(7 + i, y)
    elif kind == "next":
        rect(11, 3, 13, 13)
        for i in range(6):
            for y in range(8 - i, 8 + i + 1):
                put(8 - i, y)
    elif kind == "pause":
        rect(4, 3, 7, 13, (166, 230, 46))
        rect(9, 3, 12, 13, (166, 230, 46))
    else:  # play
        for i in range(7):
            for y in range(3 + i // 1, 13 - i // 1):
                put(5 + i, y, 166, 230, 46)

    class _BITMAPINFOHEADER(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", ctypes.c_long), ("biHeight", ctypes.c_long),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", ctypes.c_long),
                    ("biYPelsPerMeter", ctypes.c_long), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    class _ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD), ("yHotspot", wintypes.DWORD),
                    ("hbmMask", wintypes.HBITMAP), ("hbmColor", wintypes.HBITMAP)]

    bmi = _BITMAPINFOHEADER()
    bmi.biSize = ctypes.sizeof(_BITMAPINFOHEADER)
    bmi.biWidth, bmi.biHeight = W, -H
    bmi.biPlanes, bmi.biBitCount, bmi.biCompression = 1, 32, 0
    bits = ctypes.c_void_p()
    hbm_c = gdi.CreateDIBSection(0, ctypes.byref(bmi), 0, ctypes.byref(bits), None, 0)
    if not hbm_c or not bits.value:
        return 0
    ctypes.memmove(bits.value, bytes(px), len(px))
    hbm_m = gdi.CreateBitmap(W, H, 1, 1, None)
    ii = _ICONINFO(1, 0, 0, hbm_m, hbm_c)
    hicon = u32.CreateIconIndirect(ctypes.byref(ii))
    gdi.DeleteObject(hbm_c)
    gdi.DeleteObject(hbm_m)
    return int(hicon or 0)


_THUMB_ICONS: dict[str, int] = {}
THUMB_PREV_ID, THUMB_PLAY_ID, THUMB_NEXT_ID = 4101, 4102, 4103


def _hook_thumb_commands(hwnd: int, on_cmd: Any) -> None:
    if sys.platform != "win32" or not hwnd or on_cmd is None or hwnd in _WNDPROCS:
        return
    import ctypes
    from ctypes import wintypes
    u32 = ctypes.windll.user32
    GWLP_WNDPROC = -4
    WM_COMMAND = 0x0111
    WNDPROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM)
    u32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, wintypes.LPARAM]
    u32.CallWindowProcW.restype = ctypes.c_ssize_t
    u32.GetWindowLongPtrW.restype = ctypes.c_void_p
    u32.SetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
    u32.SetWindowLongPtrW.restype = ctypes.c_void_p
    prev = u32.GetWindowLongPtrW(hwnd, GWLP_WNDPROC)
    if not prev:
        return

    def _proc(h, msg, wp, lp):
        if msg == WM_COMMAND:
            cid = wp & 0xFFFF
            if cid in (THUMB_PREV_ID, THUMB_PLAY_ID, THUMB_NEXT_ID):
                try:
                    import threading
                    threading.Thread(target=on_cmd, args=(cid,), daemon=True).start()
                    return 0
                except Exception:
                    pass
        return u32.CallWindowProcW(prev, h, msg, wp, lp)

    cb = WNDPROC(_proc)
    old = u32.SetWindowLongPtrW(hwnd, GWLP_WNDPROC, ctypes.cast(cb, ctypes.c_void_p))
    if old:
        _WNDPROCS[hwnd] = (cb, old, on_cmd)


def set_thumb_buttons(hwnd: int, playing: bool = False, on_cmd: Any = None) -> bool:
    """Gorev cubugu onizleme karti altina Onceki / Oynat-Duraklat / Sonraki dugmeleri ekler ve gunceller."""
    if sys.platform != "win32" or not hwnd:
        return False
    if not _get_tbl() or not _TBL_EXTRA:
        return False
    import ctypes
    from ctypes import wintypes
    ptr, thumb_add, thumb_upd = _TBL_EXTRA
    THB_ICON, THB_TOOLTIP, THB_FLAGS = 0x2, 0x4, 0x8

    class _THUMBBUTTON(ctypes.Structure):
        _fields_ = [("dwMask", wintypes.DWORD), ("iId", wintypes.UINT), ("iBitmap", wintypes.UINT),
                    ("hIcon", wintypes.HANDLE), ("szTip", ctypes.c_wchar * 260), ("dwFlags", wintypes.DWORD)]

    for k in ("prev", "play", "pause", "next"):
        if k not in _THUMB_ICONS:
            _THUMB_ICONS[k] = _make_glyph_hicon(k)
    arr = (_THUMBBUTTON * 3)()
    specs = [
        (THUMB_PREV_ID, _THUMB_ICONS.get("prev", 0), "Önceki"),
        (THUMB_PLAY_ID, _THUMB_ICONS.get("pause" if playing else "play", 0), "Duraklat" if playing else "Oynat"),
        (THUMB_NEXT_ID, _THUMB_ICONS.get("next", 0), "Sonraki"),
    ]
    for i, (bid, ic, tip) in enumerate(specs):
        arr[i].dwMask = THB_ICON | THB_TOOLTIP | THB_FLAGS
        arr[i].iId = bid
        arr[i].hIcon = ic
        arr[i].szTip = tip
        arr[i].dwFlags = 0
    try:
        if hwnd not in _ADDED_THUMBS:
            hr = thumb_add(ptr, int(hwnd), 3, ctypes.byref(arr))
            if hr != 0:
                return False
            _ADDED_THUMBS.add(hwnd)
            if on_cmd is not None:
                _hook_thumb_commands(hwnd, on_cmd)
        else:
            hr = thumb_upd(ptr, int(hwnd), 3, ctypes.byref(arr))
            return hr == 0
        return True
    except Exception:
        return False


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
