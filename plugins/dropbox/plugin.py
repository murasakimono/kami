"""Dropbox paylasim linkleri. Tek dosya dogrudan; klasor API anahtari olmadan listelenemiyor -> Dropbox'in
hazirladigi tek zip olarak iner (zip anlik uretildigi icin tek baglanti, boyut onceden bilinmez)."""
from __future__ import annotations

import re
from urllib.parse import parse_qsl, unquote, urlencode, urlparse, urlunparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, session

_CD_NAME = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"([^\"]+)\"", re.I)


def direct(url: str) -> str:
    p = urlparse(url)
    q = [(k, v) for k, v in parse_qsl(p.query) if k not in ("dl", "raw")] + [("dl", "1")]
    return urlunparse(p._replace(query=urlencode(q), fragment=""))


class Dropbox(CloudProvider):
    name = "dropbox"
    hosts = ("dropbox.com", "db.tt")
    path_re = re.compile(r"^/(s|sh|scl/fi|scl/fo)/")

    def list(self, url: str) -> CloudListing:
        p = urlparse(url)
        is_folder = p.path.startswith(("/sh/", "/scl/fo/"))
        dl = direct(url)
        name, size = "", 0
        r = session().get(dl, stream=True, timeout=30, allow_redirects=True)
        try:
            if r.status_code == 404:
                raise CloudError("cloud_not_found", url)
            if r.status_code in (401, 403, 429, 460):
                raise CloudError("cloud_denied", f"{r.status_code}")
            r.raise_for_status()
            if "text/html" in r.headers.get("Content-Type", ""):
                raise CloudError("cloud_denied", "html")
            m = _CD_NAME.search(r.headers.get("Content-Disposition", ""))
            if m:
                name = unquote(m.group(1)) if m.group(1) else m.group(2)
            size = int(r.headers.get("Content-Length") or 0)
        finally:
            r.close()
        if not name:
            seg = [x for x in p.path.split("/") if x]
            name = unquote(seg[-1]) if seg else "dropbox"
            if is_folder and not name.lower().endswith(".zip"):
                name += ".zip"
        note = "Klasör tek .zip olarak iner / folder downloads as one .zip" if is_folder else ""
        return CloudListing(self.name, name, [CloudFile(name, size, url=dl)], is_folder=False, note=note)


def register(ctx) -> None:
    ctx.register_cloud(Dropbox())
