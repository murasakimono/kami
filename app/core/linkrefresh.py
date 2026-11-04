"""Link yenileme (Asama 6c): suresi dolan gecici linki kaynaktan yeniden cozer.

download.extra["refresh"]:
  {"type": "rd", "link": <hoster/RD linki>}             -> Real-Debrid unrestrict tekrar
  {"type": "cloud", "share": <paylasim>, "path": <yol>}  -> bulut eklentisi listeyi yeniden alir, ayni dosya
Medya (yt-dlp) isleri zaten her denemede sayfadan yeniden cozuldugu icin burada degil.
Donus: (yeni_url, basliklar|None) ya da None.
"""
from __future__ import annotations

import logging
from typing import Any

log = logging.getLogger(__name__)


class LinkRefresher:
    def __init__(self, manager) -> None:
        self.manager = manager

    def refresh(self, d) -> tuple[str, dict[str, str] | None] | None:
        ref: dict[str, Any] = (d.extra or {}).get("refresh") or {}
        kind = ref.get("type")
        if kind == "rd":
            return self._rd(d, ref)
        if kind == "cloud":
            return self._cloud(d, ref)
        return None

    def _rd(self, d, ref) -> tuple[str, None] | None:
        rd = getattr(self.manager, "debrid", None)
        if rd is None or not ref.get("link"):
            return None
        files = rd.unrestrict_files(ref["link"])
        if not files:
            return None
        match = next((f for f in files if f.get("filename") == d.filename), None) or \
            (files[0] if len(files) == 1 else None)
        return (match["url"], None) if match else None

    def _cloud(self, d, ref) -> tuple[str, dict[str, str]] | None:
        cloud = getattr(self.manager, "cloud", None)
        if cloud is None or not ref.get("share"):
            return None
        token, listing = cloud.list(ref["share"])
        provider, listing = cloud.get(token)
        f = next((x for x in listing.files if x.path == ref.get("path")), None)
        if f is None:
            log.info("Yenileme: dosya paylasimda artik yok (%s)", ref.get("path"))
            return None
        url, headers, _ = provider.file_request(listing, f)
        return url, headers
