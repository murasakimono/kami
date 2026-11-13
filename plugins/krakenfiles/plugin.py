"""KrakenFiles: /view/<id>/file.html cozumleyici."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, session


class KrakenFiles(CloudProvider):
    name = "krakenfiles"
    hosts = ("krakenfiles.com",)
    path_re = re.compile(r"^/view/([^/]+)")

    def list(self, url: str) -> CloudListing:
        m = self.path_re.match(urlparse(url).path)
        if not m:
            raise ValueError("Geçersiz KrakenFiles bağlantısı")
        ident = m.group(1)
        s = session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        page = r.text
        name_m = re.search(r'<span[^>]*class="[^"]*coin-name[^"]*"[^>]*>(.*?)</span>', page, flags=re.S | re.I)
        if not name_m:
            name_m = re.search(r"<h1[^>]*>(.*?)</h1>", page, flags=re.S | re.I)
        name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else ident
        form_m = re.search(r'action=["\'](/download/[^"\']+)["\']', page)
        tok_m = re.search(r'name=["\']token["\'][^>]*value=["\']([^"\']+)["\']', page)
        if not form_m or not tok_m:
            raise RuntimeError("KrakenFiles indirme formu bulunamadı")
        post_url = urljoin(url, form_m.group(1))
        res = s.post(post_url, data={"token": tok_m.group(1)}, headers={"Referer": url, "hash": ident}, timeout=20).json()
        dl = res.get("url") or ""
        if not dl:
            raise RuntimeError("KrakenFiles indirme bağlantısı döndürmedi")
        if dl.startswith("//"):
            dl = "https:" + dl
        return CloudListing(self.name, name or ident, is_folder=False, files=[
            CloudFile(name or ident, 0, url=dl, headers={"Referer": url}),
        ])


def register(ctx) -> None:
    ctx.register_cloud(KrakenFiles())
