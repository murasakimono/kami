"""Kami Video Iyilestirici koprusu: JS -> pywebview.api.enhance_*.

Api sinifina karisir (api.py: class Api(StudioMixin, EnhanceMixin)). Agir is yok burada:
motor app/core/video_enhance.py, ikililer app/core/studio_enhance.py (ncnn-vulkan) tarafinda.
"""
from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)


class EnhanceMixin:
    # ---- pencere

    def enhance_open(self) -> dict[str, Any]:
        """Araç penceresini acar/one getirir."""
        return self._open_mod_window("enhance")

    # ---- durum

    def enhance_presets(self) -> list[dict[str, Any]]:
        from app.core import video_enhance as ve
        return ve.presets()

    def enhance_tools(self) -> dict[str, Any]:
        """Kurulu ikililer + varsayilan cikti klasoru."""
        from app.core import studio, video_enhance as ve
        return {"tools": ve.tools(),
                "out_dir": str(studio.home_dir() / ve.OUT_SUBDIR),
                "ffmpeg": bool(self._media.ffmpeg())}

    def enhance_probe(self, path: str) -> dict[str, Any]:
        """Video bilgisi (boyut, fps, kare, interlace). Hata olursa bos sozluk."""
        from app.core import video_enhance as ve
        try:
            return ve.probe(self._media.ffmpeg(), str(path))
        except Exception as exc:
            log.warning("enhance_probe: %s", exc)
            return {}

    # ---- dosya secimi

    def enhance_pick(self) -> list[str]:
        """Video dosyasi secme diyalogu."""
        import webview
        w = getattr(self, "_enhance_win", None) or self._window
        if not w:
            return []
        types = ("Medya (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.ts;*.m2ts;*.wmv;*.flv;*.m4v)", "Tüm dosyalar (*.*)")
        r = w.create_file_dialog(webview.OPEN_DIALOG, allow_multiple=False, file_types=types)
        return list(r or [])

    # ---- is

    def enhance_start(self, preset: str, path: str, opts: dict | None = None) -> dict[str, Any]:
        """Iyilestirmeyi baslatir -> {ok, job} | {ok:False, error, tool}."""
        from app.core import studio, video_enhance as ve
        return ve.start(str(preset), str(path), self._media.ffmpeg(), dict(opts or {}),
                        studio.home_dir() / ve.OUT_SUBDIR)

    def enhance_job(self, jid: str) -> dict[str, Any]:
        from app.core import video_enhance as ve
        return ve.job(str(jid))

    def enhance_jobs(self) -> list[dict[str, Any]]:
        from app.core import video_enhance as ve
        return ve.jobs()

    def enhance_cancel(self, jid: str) -> dict[str, Any]:
        from app.core import video_enhance as ve
        ve.cancel(str(jid))
        return {"ok": True}

    def enhance_install(self, tool: str) -> dict[str, Any]:
        """Real-ESRGAN / RIFE ikilisini indirir; ilerleme enhance_job'dan izlenir."""
        from app.core import video_enhance as ve
        return ve.install_start(str(tool))

    def enhance_open_output(self, path: str = "") -> dict[str, Any]:
        """Cikti klasorunu (ya da dosyayi) Gezgin'de acar."""
        from app.core import studio, video_enhance as ve
        p = Path(str(path)) if path else (studio.home_dir() / ve.OUT_SUBDIR)
        target = p if p.exists() else p.parent
        if not target.exists():
            return {"ok": False, "error": "yol_yok"}
        import os
        os.startfile(str(target))   # noqa: S606 - Windows gezgini
        return {"ok": True, "path": str(target)}
