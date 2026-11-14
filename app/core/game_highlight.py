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


def default_killfeed_roi() -> tuple[int, int, int, int]:
    """Birincil ekranin sag-ust kosesi (cogu FPS/MOBA'da kill-feed burada): genislik %35, yukseklik %30."""
    try:
        u32 = ctypes.windll.user32
        sw, sh = int(u32.GetSystemMetrics(0)), int(u32.GetSystemMetrics(1))
    except Exception:
        sw, sh = 1920, 1080
    return (int(sw * 0.65), 0, sw, int(sh * 0.30))


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
                # ROI verilmediyse tum ekrani degil sag-ust kill-feed kosesini oku (hiz + yanlis tetik onleme)
                im = ImageGrab.grab(bbox=self.roi or default_killfeed_roi())
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
            if self.recorder is None:
                return {"triggered": False, "reason": "no_recorder", "title": title}
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
        if self.running and self._thread is not None and self._thread.is_alive():
            return {"ok": True, "running": True}
        # Her dongu kendi durdurma bayragini kullanir: hizli stop->start iki thread birakmaz
        stop_ev = threading.Event()
        self._stop = stop_ev
        self.running = True

        def _loop() -> None:
            while not stop_ev.is_set():
                try:
                    self.check_once()
                except Exception as exc:
                    log.debug("HighlightWatcher dongu hatasi: %s", exc)
                stop_ev.wait(max(0.5, float(interval_sec)))
            if self._stop is stop_ev:
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
    """pyvirtualcam ve GPU matting hazirlik durumunu raporlar (agir torch'u ana surece YUKLEMEDEN)."""
    import importlib.util
    has_vcam = importlib.util.find_spec("pyvirtualcam") is not None
    has_rvm = importlib.util.find_spec("torch") is not None
    return {
        "ok": True,
        "pyvirtualcam_installed": has_vcam,
        "gpu_matting_ready": has_rvm,
        "note": "Hazir" if has_vcam else "pyvirtualcam (OBS Virtual Camera) kurulu degil",
    }


def _detect_audio_peaks(video_path: str, top_n: int = 8, min_gap_s: float = 1.5, win_s: float = 0.25) -> tuple[list[float], float]:
    """FFmpeg ile video sesindeki en yuksek RMS tepe noktalarini (sn) ve toplam sureyi cikarir."""
    import array
    import math
    import subprocess
    from app.engines.ytdlp_engine import find_ffmpeg

    ff = find_ffmpeg()
    if not ff:
        return [], 0.0
    sr = 8000
    step = max(1, int(sr * win_s))
    nowin = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    try:
        r = subprocess.run(
            [ff, "-v", "error", "-i", str(video_path), "-vn", "-ac", "1", "-ar", str(sr), "-f", "s16le", "pipe:1"],
            capture_output=True,
            timeout=30,
            creationflags=nowin,
        )
    except Exception:
        return [], 0.0

    raw = r.stdout or b""
    samples = array.array("h")
    usable = len(raw) - (len(raw) % 2)
    if usable <= 0:
        return [], 0.0
    samples.frombytes(raw[:usable])
    total_dur = round(len(samples) / float(sr), 3)

    windows: list[tuple[float, float]] = []
    for i in range(0, len(samples), step):
        seg = samples[i : i + step]
        if not seg:
            continue
        rms = math.sqrt(sum(float(x) * float(x) for x in seg) / len(seg))
        t_sec = round((i + len(seg) * 0.5) / float(sr), 2)
        windows.append((rms, t_sec))

    windows.sort(key=lambda pair: pair[0], reverse=True)
    picked: list[float] = []
    for rms, t_sec in windows:
        if rms <= 0:
            break
        if all(abs(t_sec - p) >= min_gap_s for p in picked):
            picked.append(t_sec)
        if len(picked) >= top_n:
            break
    picked.sort()
    return picked, total_dur


def build_fragmovie_project(
    clip_paths: list[str] | str,
    out_kstudio: str = "",
    title: str = "Oyun Fragmovie",
    clip_pre_s: float = 1.6,
    clip_post_s: float = 1.2,
) -> dict[str, Any]:
    """Vurgu kliplerindeki ses tepe noktalarina (kill/hit) hizali .kstudio Fragmovie projesi uretir."""
    from app.core import studio as S
    from app.engines.ytdlp_engine import find_ffmpeg

    st = S.Studio(find_ffmpeg)

    if isinstance(clip_paths, str):
        raw_list = [p.strip() for p in clip_paths.replace(";", "\n").splitlines() if p.strip()]
    else:
        raw_list = [str(p or "").strip() for p in (clip_paths or []) if str(p or "").strip()]

    valid_files = [str(Path(p)) for p in raw_list if Path(p).is_file()]
    if not valid_files:
        return {"ok": False, "error": "Gecerli video klibi bulunamadi"}

    pr = S.new_project(name=title or "Oyun Fragmovie")
    trans_mode = next((k for k in ("flash", "whip", "zoom", "glitch", "fade") if k in S.TRANS), "")
    fx_mode = next((k for k in ("rgb-split", "chromatic", "shake", "glitch", "vignette") if k in S.FX), "")
    sfx_id = next((k for k in ("whoosh", "hitmarker", "tik", "boom") if k in getattr(S, "SFX", {})), "")

    cursor = 0.0
    segments_added = 0
    all_peaks: list[dict[str, Any]] = []
    for fpath in valid_files:
        info = st.info(fpath)
        if not info.get("ok"):
            continue
        dur = float(info.get("dur") or 0)
        aid = S.add_asset(pr, info)
        peaks, audio_dur = _detect_audio_peaks(fpath, top_n=4, min_gap_s=2.0)
        eff_dur = dur or audio_dur or 4.0
        if not peaks:
            peaks = [round(min(eff_dur * 0.5, max(0.5, eff_dur - 0.5)), 2)]

        for idx_p, pk in enumerate(peaks):
            in_t = max(0.0, round(pk - clip_pre_s, 3))
            out_t = min(eff_dur, round(pk + clip_post_s, 3))
            seg_d = max(0.6, round(out_t - in_t, 3))
            kw: dict[str, Any] = {
                "asset": aid,
                "track": "v1",
                "start": round(cursor, 3),
                "in": in_t,
                "dur": seg_d,
            }
            if trans_mode and (segments_added > 0 or idx_p > 0):
                kw["trans"] = {"in": trans_mode, "dur": 0.25}
            c = S.add_clip(pr, **kw)
            peak_in_timeline = round(cursor + max(0.0, pk - in_t), 3)
            pr.setdefault("markers", []).append({"t": peak_in_timeline, "label": f"Vurgu {segments_added + 1}", "color": "#f43f5e"})
            if fx_mode:
                S.add_clip(pr, mode=fx_mode, track="fx", start=max(0.0, round(peak_in_timeline - 0.12, 3)), dur=0.35)
            all_peaks.append({"file": Path(fpath).name, "peak_src": pk, "timeline_s": peak_in_timeline, "clip_id": c.get("id")})
            cursor = round(cursor + seg_d, 3)
            segments_added += 1

    if segments_added == 0:
        return {"ok": False, "error": "Video dosyalari Studio varligi olarak cozumlenemedi"}

    dst = Path(out_kstudio) if out_kstudio else (S.home_dir() / "Projeler" / f"{title or 'Oyun Fragmovie'}{S.PROJECT_EXT}")
    saved = S.save_project(str(dst), pr)
    return {
        "ok": True,
        "path": saved,
        "clips_count": segments_added,
        "duration": cursor,
        "peaks": all_peaks,
        "sfx_hint": sfx_id,
    }
