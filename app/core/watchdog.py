"""Donma teshisi: yavas api cagrisi logu + arayuz kalp atisi bekcisi.

- log_slow_calls(Api): JS'in cagirdigi her metot 2 sn'den uzun surerse log'a uyari.
- UiWatchdog: arayuz her 0.5 sn get_state cagiriyor (kalp atisi). Pencere gorunurken 8 sn ses
  gelmezse log'a "arayuz yanit vermiyor" + tum is parcaciklarinin yigini (py-spy'a gerek kalmasin).
"""
from __future__ import annotations

import functools
import inspect
import logging
import os
import sys
import threading
import time
import traceback
from typing import Callable

log = logging.getLogger("kami.watchdog")

SLOW_CALL_SEC = float(os.environ.get("KAMI_SLOW_SEC") or 2.0)   # olcum icin: KAMI_SLOW_SEC=0.05
UI_STALL_SEC = 8.0
UI_RECOVER_SEC = 25.0     # bu kadar sure kalp atisi yoksa (pencere gorunurken) sayfayi yeniden yukle
UI_RECOVER_GAP = 120.0    # iki kurtarma arasi en az


def log_slow_calls(cls, threshold: float = SLOW_CALL_SEC):
    """Sinifin alt cizgisiz (JS'e acik) metotlarini sure olcen sarmalayiciyla degistirir."""
    for name, fn in list(vars(cls).items()):
        if name.startswith("_") or not callable(fn) or isinstance(fn, (staticmethod, classmethod, property)):
            continue

        def make(f, n):
            @functools.wraps(f)
            def wrapper(*a, **kw):
                t0 = time.monotonic()
                try:
                    return f(*a, **kw)
                finally:
                    dt = time.monotonic() - t0
                    if dt > threshold:
                        log.warning("Yavas api cagrisi: %s %.1f sn", n, dt)
            # pywebview JS taslagini getfullargspec ile kurar; __wrapped__'i izlemez, __signature__'u okur
            wrapper.__signature__ = inspect.signature(f)
            return wrapper

        setattr(cls, name, make(fn, name))
    return cls


def thread_dump() -> str:
    names = {t.ident: t.name for t in threading.enumerate()}
    out = []
    for ident, frame in sys._current_frames().items():
        out.append(f"--- {names.get(ident, ident)}\n" + "".join(traceback.format_stack(frame, limit=12)))
    return "\n".join(out)


class UiWatchdog:
    def __init__(self, visible: Callable[[], bool], stall: float = UI_STALL_SEC,
                 on_recover: Callable[[], None] | None = None, recover_after: float = UI_RECOVER_SEC) -> None:
        self.visible = visible
        self.stall = stall
        self.on_recover = on_recover
        self.recover_after = recover_after
        self._recovered = False
        self._last_recover = -1e9
        self.recoveries = 0
        self.last_beat = time.monotonic()
        self._visible_since = time.monotonic()
        self._was_visible = False
        self._reported = False
        self._stop = threading.Event()

    def beat(self) -> None:
        if self._reported:
            log.warning("Arayuz yeniden yanit veriyor (%.1f sn sonra)", time.monotonic() - self.last_beat)
            self._reported = False
        self._recovered = False
        self.last_beat = time.monotonic()

    def check(self, now: float | None = None) -> bool:
        """True: donma bildirildi (testler icin ayri)."""
        now = time.monotonic() if now is None else now
        try:
            vis = bool(self.visible())
        except Exception:
            vis = False
        if vis and not self._was_visible:
            self._visible_since = now   # gizli/kucukken JS zamanlayicisi durur: geri gelince sure tani
        self._was_visible = vis
        if not vis:
            return False
        since = now - max(self.last_beat, self._visible_since)
        if self._reported:
            # Kendini toparlama: JS tarafi (oluk/bos sayfa, cokmus cizici) hala atmiyorsa sayfayi yeniden yukle
            if (self.on_recover and not self._recovered and since > self.recover_after
                    and now - self._last_recover > UI_RECOVER_GAP):
                self._recovered = True
                self._last_recover = now
                self.recoveries += 1
                log.warning("Arayuz %.0f sn'dir yanit vermiyor: sayfa yeniden yukleniyor", since)
                threading.Thread(target=self._safe_recover, name="kami-ui-recover", daemon=True).start()
                return True
            return False
        if since > self.stall:
            self._reported = True
            log.warning("Arayuz %.0f sn'dir yanit vermiyor. Is parcaciklari:\n%s", since, thread_dump())
            return True
        return False

    def _safe_recover(self) -> None:
        try:
            self.on_recover()
        except Exception:
            log.exception("Arayuz kurtarma basarisiz")

    def start(self) -> None:
        def loop():
            while not self._stop.wait(2.0):
                self.check()
        threading.Thread(target=loop, name="kami-watchdog", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()
