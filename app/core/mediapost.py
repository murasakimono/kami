"""Medya bitis isleri (Asama 6b): PostComplete'in kuyrugunda, SHA256/Defender'dan sonra calisir.

Muzik: soz (LRCLIB/Genius linki) -> MusicBrainz arsivi (etiket + Sanatci/Album klasoru + kapak) -> otomatik UVR.
Video: altyazi izi yoksa ve ayar aciksa Whisper. Hepsi Ayarlar'dan acilip kapanir.
"""
from __future__ import annotations

import logging
import os
from typing import Any, Callable

from app.core import media_meta
from app.core.categories import CATEGORY_FOLDERS

log = logging.getLogger(__name__)


class MediaPost:
    def __init__(self, manager, ai=None, genius_token: Callable[[], str] = lambda: "") -> None:
        self.manager = manager
        self.ai = ai                       # aitools.AiQueue (None: testlerde)
        self.genius_token = genius_token

    @property
    def s(self):
        return self.manager.settings

    def music_dir(self) -> str:
        d = self.s.get("music_dir")
        if d:
            return d
        return os.path.join(self.manager.base_dir(), CATEGORY_FOLDERS.get("music", "Müzik"))

    def set_extra(self, did: int, **kw: Any) -> None:
        d = self.manager.store.get(did)
        if not d:
            return
        nd = self.manager.store.update(did, extra={**(d.extra or {}), **kw})
        self.manager.events.emit("download.updated", download=nd)

    # ---- elle (arayuz) ve otomatik
    def lyrics(self, did: int) -> dict[str, Any]:
        from app.core import lyrics
        d = self.manager.store.get(did)
        if not d or not d.path or not os.path.isfile(d.path):
            return {"ok": False, "error": "no_file"}
        try:
            res = lyrics.fetch_for_file(d.path, (d.extra or {}).get("title") or d.filename,
                                        embed=bool(self.s.get("lyrics_embed")), genius_token=self.genius_token)
        except Exception as exc:
            log.exception("Soz alinamadi")
            return {"ok": False, "error": type(exc).__name__}
        self.set_extra(did, lyrics=res["lyrics"], lyrics_links=res["links"], lyrics_lrc=res.get("lrc", ""))
        return {"ok": True, **res}

    def archive(self, did: int) -> dict[str, Any]:
        from app.core import musicarchive
        d = self.manager.store.get(did)
        if not d or not d.path or not os.path.isfile(d.path):
            return {"ok": False, "error": "no_file"}
        try:
            res = musicarchive.archive(d.path, self.music_dir(), (d.extra or {}).get("title") or d.filename)
        except Exception as exc:
            log.exception("Arsivleme hatasi")
            return {"ok": False, "error": type(exc).__name__}
        if res.get("archive") == "ok" and res.get("path") and res["path"] != d.path:
            self.manager.store.update(did, filename=os.path.basename(res["path"]),
                                      directory=os.path.dirname(res["path"]))
        self.set_extra(did, archive=res.get("archive"), album=res.get("album", ""))
        return {"ok": res.get("archive") == "ok", **res}

    def process(self, did: int) -> None:
        d = self.manager.store.get(did)
        if not d or not d.path or not os.path.isfile(d.path):
            return
        kind = media_meta.kind_of(d.path)
        if kind == "audio":
            if self.s.get("lyrics_auto"):
                self.lyrics(did)
            if self.s.get("music_archive"):
                self.archive(did)
            if self.s.get("uvr_auto") and self.ai is not None:
                r = self.ai.submit("uvr", did)
                if not r.get("ok"):
                    log.info("Otomatik UVR atlandi: %s", r.get("error"))
        elif kind == "video" and self.s.get("whisper_auto") and self.ai is not None:
            if not self._has_subs(d.path):
                r = self.ai.submit("whisper", did)
                if not r.get("ok"):
                    log.info("Otomatik Whisper atlandi: %s", r.get("error"))

    @staticmethod
    def _has_subs(path: str) -> bool:
        from app.core.aitools import _sub_count
        from app.engines.ytdlp_engine import find_ffmpeg
        ff = find_ffmpeg()
        return bool(ff and _sub_count(ff, path) > 0)
