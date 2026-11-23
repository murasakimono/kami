"""v2.5.3: Uygulama geneli kapanis sinyali.

Arka plan donguleri `while True: sleep(x)` yerine `while not STOP.wait(x)` kullanir; `_shutdown_once`
ilk is olarak STOP.set() cagirir, boylece kapanistan sonra hicbir dongu kapali veritabanina dokunmaz.
"""
from __future__ import annotations

import threading

STOP = threading.Event()


def stopping() -> bool:
    return STOP.is_set()
