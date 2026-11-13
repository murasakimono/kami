"""Faz 14.3 — Oto Oyun Vurgu Yakalayici (recorder.save_replay tetikleyici) & Sanal Kamera Koprusu."""
from __future__ import annotations

import ctypes
import logging
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

DEFAULT_GAMES = (
    "valorant",
    "counter-strike",
    "cs2",
    "league of legends",
    "apex legends",
    "fortnite",
    "overwatch",
    "warframe",
)
DEFAULT_KEYWORDS = ("victory", "ace", "pentakill", "quadra", "eliminated", "zafer", "mvp")


def active_window_title() -> str:
    """Windows aktif pencere basligini dondurur."""
    try:
        u32 = ctypes.windll.user32
        hwnd = u32.GetForegroundWindow()
        if not hwnd:
            return ""
        n = u32.GetWindowTextLengthW(hwnd)
        if n <= 0:
            return ""
        buf = ctypes.create_unicode_buffer(n + 1)
        u32.GetWindowTextW(hwnd, buf, n + 1)
        return buf.value or ""
    except Exception:
        return ""


def is_game_active(title: str, games: tuple[str, ...] | list[str] = DEFAULT_GAMES) -> bool:
    low = (title or "").lower()
    return any(g.lower() in low for g in games if g)


def detect_roi_highlight(image_path: str | Path, keywords: tuple[str, ...] | list[str] = DEFAULT_KEYWORDS) -> dict[str, Any]:
    """ROI gorselinde (kill-feed / zafer bandi) OCR ile anahtar kelime arar."""
    p = Path(image_path)
    if not p.is_file():
        return {"hit": False, "keyword": "", "text": ""}
    try:
        from app.core import ocr
        res = ocr.read_text(str(p), lang="en,tr")
        text = " ".join(res.get("lines") or [])
        low = text.lower()
        import re as _re
        for kw in keywords:
            if _re.search(r"(?<!\w)" + _re.escape(kw.lower()) + r"(?!\w)", low):
                return {"hit": True, "keyword": kw, "text": text}
        return {"hit": False, "keyword": "", "text": text}
    except Exception:
        return {"hit": False, "keyword": "", "text": ""}


class HighlightWatcher:
    """Oyun acikken belirli araliklarla ROI'yi izleyip otomatik recorder.save_replay() tetikler."""

    def __init__(self, recorder: Any, *, cooldown_sec: float = 45.0) -> None:
        self.recorder = recorder
        self.cooldown_sec = float(cooldown_sec)
        self.games: list[str] = list(DEFAULT_GAMES)
        self.keywords: list[str] = list(DEFAULT_KEYWORDS)
        self.roi: tuple[int, int, int, int] | None = None
        self.running = False
        self.last_trigger = 0.0
        self.saved_clips: list[str] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def check_once(
        self,
        *,
        window_title_fn: Callable[[], str] | None = None,
        grab_roi_fn: Callable[[], Path | None] | None = None,
        detect_fn: Callable[[str | Path, list[str]], dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        title = (window_title_fn or active_window_title)()
        if not is_game_active(title, self.games):
            return {"triggered": False, "reason": "no_game", "title": title}

        now = time.monotonic()
        if self.last_trigger and (now - self.last_trigger) < self.cooldown_sec:
            return {"triggered": False, "reason": "cooldown", "title": title}

        roi_file: Path | None = None
        cleanup = False
        if grab_roi_fn is not None:
            roi_file = grab_roi_fn()
        else:
            try:
                from PIL import ImageGrab
                im = ImageGrab.grab(bbox=self.roi)
                tmp = Path(tempfile.gettempdir()) / f"kami_roi_{int(time.time() * 1000)}.png"
                im.save(tmp)
                roi_file = tmp
                cleanup = True
            except Exception:
                return {"triggered": False, "reason": "grab_failed", "title": title}

        if not roi_file or not Path(roi_file).is_file():
            return {"triggered": False, "reason": "empty_roi", "title": title}

        try:
            hit = (detect_fn or detect_roi_highlight)(roi_file, self.keywords)
            if not hit.get("hit"):
                return {"triggered": False, "reason": "no_keyword", "title": title}
            clip_path = self.recorder.save_replay()
            self.last_trigger = now
            self.saved_clips.append(clip_path)
            return {"triggered": True, "keyword": hit.get("keyword", ""), "clip": clip_path, "title": title}
        finally:
            if cleanup and roi_file:
                Path(roi_file).unlink(missing_ok=True)

    def start(self, games: list[str] | None = None, keywords: list[str] | None = None, interval_sec: float = 2.0) -> dict[str, Any]:
        if games:
            self.games = list(games)
        if keywords:
            self.keywords = list(keywords)
        if self.running:
            return {"ok": True, "running": True}
        self._stop.clear()
        self.running = True

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.check_once()
                except Exception as exc:
                    log.debug("HighlightWatcher dongu hatasi: %s", exc)
                self._stop.wait(max(0.5, float(interval_sec)))
            self.running = False

        self._thread = threading.Thread(target=_loop, name="kami-highlight-watch", daemon=True)
        self._thread.start()
        return {"ok": True, "running": True, "games": self.games, "keywords": self.keywords}

    def stop(self) -> dict[str, Any]:
        self._stop.set()
        self.running = False
        return {"ok": True, "running": False, "saved_clips": list(self.saved_clips)}

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "running": self.running,
            "games": self.games,
            "keywords": self.keywords,
            "saved_count": len(self.saved_clips),
            "last_clip": self.saved_clips[-1] if self.saved_clips else "",
        }


def virtual_camera_status() -> dict[str, Any]:
    """pyvirtualcam ve RobustVideoMatting hazirlik durumunu raporlar."""
    has_vcam = False
    has_rvm = False
    try:
        import pyvirtualcam  # noqa: F401
        has_vcam = True
    except Exception:
        pass
    try:
        import torch  # noqa: F401
        has_rvm = True
    except Exception:
        pass
    return {
        "ok": True,
        "pyvirtualcam_installed": has_vcam,
        "gpu_matting_ready": has_rvm,
        "note": "Hazir" if has_vcam else "pyvirtualcam (OBS Virtual Camera) kurulu degil",
    }
