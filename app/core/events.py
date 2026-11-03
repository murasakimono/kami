"""Basit, thread-safe olay yolu (pub/sub).

Olay adlari (Asama 1):
  download.added      (download: Download)
  download.updated    (download: Download)
  download.completed  (download: Download)
  download.failed     (download: Download)
  download.removed    (download_id: int)
  ui.attention        (reason: str)   -> pencereyi one getir
"""
from __future__ import annotations

import logging
import threading
from collections import defaultdict
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[..., Any]


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()

    def on(self, event: str, handler: Handler) -> Callable[[], None]:
        """Abone ol. Aboneligi iptal eden fonksiyonu dondurur."""
        with self._lock:
            self._handlers[event].append(handler)

        def off() -> None:
            with self._lock:
                if handler in self._handlers[event]:
                    self._handlers[event].remove(handler)

        return off

    def emit(self, event: str, **payload: Any) -> None:
        with self._lock:
            direct = list(self._handlers.get(event, ()))
            wildcard = list(self._handlers.get("*", ())) if event != "*" else []
        for h in direct:
            try:
                h(**payload)
            except Exception:
                log.exception("Olay isleyicisi hata verdi: %s", event)
        for h in wildcard:  # joker aboneler olay adini da alir
            try:
                h(event=event, **payload)
            except Exception:
                log.exception("Joker olay isleyicisi hata verdi: %s", event)
