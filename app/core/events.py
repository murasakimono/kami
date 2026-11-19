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
from collections import defaultdict, deque
import time
from typing import Any, Callable

log = logging.getLogger(__name__)

Handler = Callable[..., Any]


class NotificationCenter:
    """Son 100 kritik olayi zaman damgali ve aksiyonlu halka tamponda tutar."""

    def __init__(self, maxlen: int = 100) -> None:
        self._items: deque[dict[str, Any]] = deque(maxlen=maxlen)
        self._lock = threading.Lock()
        self._seq = 0

    def push(self, kind: str, title: str, detail: str = "", *, path: str = "",
             url: str = "", download_id: int = 0) -> dict[str, Any]:
        with self._lock:
            self._seq += 1
            entry = {
                "id": self._seq,
                "ts": time.time(),
                "kind": str(kind or "info"),
                "title": str(title or "")[:160],
                "detail": str(detail or "")[:240],
                "path": str(path or ""),
                "url": str(url or ""),
                "download_id": int(download_id or 0),
                "read": False,
            }
            self._items.appendleft(entry)
            return dict(entry)

    def list(self, limit: int = 0) -> list[dict[str, Any]]:
        with self._lock:
            items = [dict(x) for x in self._items]
        if limit and limit > 0:
            return items[:int(limit)]
        return items

    def unread_count(self) -> int:
        with self._lock:
            return sum(1 for x in self._items if not x.get("read"))

    def mark_all_read(self) -> int:
        with self._lock:
            for x in self._items:
                x["read"] = True
            return len(self._items)

    def clear(self) -> None:
        with self._lock:
            self._items.clear()


class EventBus:
    def __init__(self) -> None:
        self._handlers: dict[str, list[Handler]] = defaultdict(list)
        self._lock = threading.Lock()
        self.notifications = NotificationCenter()

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
