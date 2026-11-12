"""Indirme bitince: SHA256 dogrulama (hash biliniyorsa), Defender taramasi, Windows bildirimi.

Arka planda tek is parcacigi (sirayla; buyuk dosyalarda disk/CPU'yu bogmasin). Sonuclar
download.extra'ya yazilir: checksum_ok, sha256, scan (scanning | clean | threat | error | unavailable).
"""
from __future__ import annotations

import logging
import os
import queue
import threading
from typing import Any, Callable

from app.core import extras

log = logging.getLogger(__name__)


class PostComplete:
    def __init__(self, manager, notify: Callable[[str, str], bool],
                 focused: Callable[[], bool] = lambda: False) -> None:
        self.manager = manager
        self.notify = notify
        self.focused = focused     # pencere ondeyse sadece uygulama ici bildirim yeter
        self.media = None          # mediapost.MediaPost (Asama 6b): soz, arsiv, otomatik Whisper/UVR
        self.toast = None          # main: dugmeli Windows bildirimi fn(download) -> bool (Oynat / Klasoru ac / Altyazi uret)
        self.after: list = []      # Asama 6c: bitis kurallari vb. -> fn(download_id)
        self._q: queue.Queue = queue.Queue()
        self._thread = threading.Thread(target=self._run, name="kami-post", daemon=True)
        manager.events.on("download.completed", lambda download: self._q.put(("done", download.id)))
        manager.events.on("download.failed", lambda download: self._q.put(("fail", download.id)))

    def start(self) -> None:
        self._thread.start()

    def _lang(self) -> str:
        return self.manager.settings.get("language") or "tr"

    def _t(self, tr: str, en: str) -> str:
        return tr if self._lang() == "tr" else en

    def _set_extra(self, did: int, **kw: Any) -> None:
        d = self.manager.store.get(did)
        if not d:
            return
        nd = self.manager.store.update(did, extra={**(d.extra or {}), **kw})
        self.manager.events.emit("download.updated", download=nd)

    def _run(self) -> None:
        while True:
            kind, did = self._q.get()
            try:
                if kind == "done":
                    self.completed(did)
                else:
                    self.failed(did)
            except Exception:
                log.exception("Bitis sonrasi islem hatasi (#%s)", did)

    def failed(self, did: int) -> None:
        for fn in list(self.after):
            if hasattr(fn, "failed"):
                try:
                    fn.failed(did)
                except Exception:
                    log.exception("Hata sonrasi is")
        d = self.manager.store.get(did)
        if d and self.manager.settings.get("notify_on_error") and not self.focused():
            self.notify("Kami", self._t("Hata: ", "Failed: ") + (d.filename or d.url)[:120])

    def completed(self, did: int) -> None:
        s = self.manager.settings
        d = self.manager.store.get(did)
        if not d:
            return
        path = d.path
        notes: list[str] = []
        expected = (d.extra or {}).get("checksum", "")
        if expected and s.get("checksum_verify") and path and os.path.isfile(path):
            got = extras.sha256_file(path)
            ok = got == expected
            self._set_extra(did, sha256=got, checksum_ok=ok)
            if not ok:
                log.warning("SHA256 uyusmuyor: %s", d.filename)
                notes.append(self._t("SHA256 UYUŞMUYOR", "SHA256 MISMATCH"))
        mode = s.get("defender_mode") or "off"
        if path and extras.should_scan(path, mode):
            self._set_extra(did, scan="scanning")
            res = extras.defender_scan(path)
            self._set_extra(did, scan=res)
            if res == "threat":
                notes.append(self._t("Defender TEHDİT buldu (karantina)", "Defender found a THREAT (quarantined)"))
        if notes or (s.get("notify_on_complete") and not self.focused()):
            msg = self._t("İndi: ", "Downloaded: ") + (d.filename or d.url)[:120]
            if notes:
                msg += "\n⚠ " + " · ".join(notes)
            shown = False
            if not notes and self.toast is not None:
                try:
                    shown = bool(self.toast(d))
                except Exception:
                    log.exception("Dugmeli bildirim")
            if not shown:
                self.notify("Kami", msg)
        if self.media is not None:
            try:
                self.media.process(did)
            except Exception:
                log.exception("Medya bitis isi hatasi (#%s)", did)
        for fn in list(self.after):
            try:
                fn(did)
            except Exception:
                log.exception("Bitis isi hatasi (#%s)", did)
        try:
            self.smart_folder(did)
        except Exception:
            log.exception("Akilli klasorleme hatasi (#%s)", did)

    def smart_folder(self, did: int) -> str:
        """Dizi bolumu inince: <Video>/Diziler/<Dizi>/Sezon NN/ altina tasir (yan altyazilar da). Ayar: smart_series_folders."""
        import re
        import shutil
        from app.core.library import parse_name
        d = self.manager.store.get(did)
        if not d or not self.manager.settings.get("smart_series_folders") or d.category != "video" or not d.path:
            return ""
        if not os.path.isfile(d.path):
            return ""
        info = parse_name(os.path.splitext(d.filename)[0])
        series = re.sub(r'[<>:"/\\|?*]', "_", info.get("series") or "").strip(" .")
        if not series or not info.get("episode"):
            return ""
        root = d.directory
        if os.path.basename(os.path.normpath(root)).lower().startswith("sezon"):
            return ""   # zaten duzenli
        target = os.path.join(root, "Diziler", series, f"Sezon {int(info.get('season') or 1):02d}")
        os.makedirs(target, exist_ok=True)
        stem = os.path.splitext(d.filename)[0]
        for name in os.listdir(root):   # video + ayni adli altyazi / kapak / soz dosyalari
            if name == d.filename or (name.startswith(stem + ".") and re.search(r"\.(srt|ass|vtt|lrc|jpg|png|webp)$", name, re.I)):
                dst = os.path.join(target, name)
                if not os.path.exists(dst):
                    shutil.move(os.path.join(root, name), dst)
        nd = self.manager.store.update(did, directory=target)
        self.manager.events.emit("download.updated", download=nd)
        log.info("Akilli klasor: %s -> %s", d.filename, target)
        return target
