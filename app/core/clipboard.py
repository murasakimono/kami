"""Windows panosu (ctypes, ek bagimlilik yok) + pano izleyici.

Izleyici: GetClipboardSequenceNumber degisince metni okur; desteklenen link varsa on_link(url) cagirir.
"""
from __future__ import annotations

import ctypes
import logging
import re
import threading
from ctypes import wintypes
from typing import Callable

log = logging.getLogger(__name__)

CF_UNICODETEXT = 13
_user32 = ctypes.WinDLL("user32", use_last_error=True)
_kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
_user32.GetClipboardData.restype = wintypes.HANDLE
_user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
_user32.OpenClipboard.argtypes = [wintypes.HWND]
_kernel32.GlobalLock.argtypes = [wintypes.HGLOBAL]
_kernel32.GlobalLock.restype = ctypes.c_void_p
_kernel32.GlobalUnlock.argtypes = [wintypes.HGLOBAL]

URL_RE = re.compile(r"(?:https?|ftp)://[^\s<>\"']+", re.I)


def sequence() -> int:
    return int(_user32.GetClipboardSequenceNumber())


def get_text() -> str:
    if not _user32.OpenClipboard(None):
        return ""
    try:
        h = _user32.GetClipboardData(CF_UNICODETEXT)
        if not h:
            return ""
        p = _kernel32.GlobalLock(h)
        if not p:
            return ""
        try:
            return ctypes.wstring_at(p)
        finally:
            _kernel32.GlobalUnlock(h)
    finally:
        _user32.CloseClipboard()


def first_url(text: str) -> str:
    m = URL_RE.search(text or "")
    return m.group(0).rstrip(").,;]") if m else ""


class ClipboardWatcher:
    def __init__(self, is_supported: Callable[[str], bool], on_link: Callable[[str], None],
                 enabled: Callable[[], bool], interval: float = 1.0) -> None:
        self.is_supported = is_supported
        self.on_link = on_link
        self.enabled = enabled
        self.interval = interval
        self.ignore_next = False        # Kami'nin kendi kopyalamasi
        self._stop = threading.Event()
        self._last_url = ""

    def start(self) -> None:
        threading.Thread(target=self._run, name="kami-clipboard", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        seq = sequence()                # acilista panoda olan link sorulmaz
        while not self._stop.wait(self.interval):
            try:
                now = sequence()
                if now == seq:
                    continue
                seq = now
                if self.ignore_next:
                    self.ignore_next = False
                    continue
                if not self.enabled():
                    continue
                url = first_url(get_text()[:4000])
                if not url or url == self._last_url:
                    continue
                if self.is_supported(url):
                    self._last_url = url
                    log.info("Panoda desteklenen link: %s", url[:120])
                    self.on_link(url)
            except Exception:
                log.exception("Pano izleme hatasi")
