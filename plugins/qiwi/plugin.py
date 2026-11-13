"""Qiwi.gg: /file/<id> ve /folder/<id> cozumleyici."""
from __future__ import annotations

import html
import re
from urllib.parse import urljoin, urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, head_size, session


class Qiwi(CloudProvider):
    name = "qiwi"
    hosts = ("qiwi.gg",)
    path_re = re.compile(r"^/(file|folder)/([^/]+)")

    def list(self, url: str) -> CloudListing:
        m = self.path_re.match(urlparse(url).path)
        if not m:
            raise ValueError("Geçersiz Qiwi.gg bağlantısı")
        kind, ident = m.group(1), m.group(2)
        s = session()
        if kind == "file":
            f = self._parse_file(s, url, ident)
            return CloudListing(self.name, f.rel_path, is_folder=False, files=[f])
        r = s.get(url, timeout=20)
        r.raise_for_status()
        links = re.findall(r'href=["\'](/file/[^"\']+)["\']', r.text, flags=re.I)
        seen: set[str] = set()
        files: list[CloudFile] = []
        for href in links:
            full = urljoin(url, href)
            if full in seen:
                continue
            seen.add(full)
            try:
                files.append(self._parse_file(s, full, href.rsplit("/", 1)[-1]))
            except Exception:
                continue
        title_m = re.search(r"<h1[^>]*>(.*?)</h1>", r.text, flags=re.S | re.I)
        title = html.unescape(re.sub(r"<[^>]+>", "", title_m.group(1))).strip() if title_m else ident
        return CloudListing(self.name, title or ident, is_folder=True, files=files)

    @staticmethod
    def _parse_file(s, url: str, ident: str) -> CloudFile:
        r = s.get(url, timeout=20)
        r.raise_for_status()
        page = r.text
        dl_m = re.search(r'href=["\'](https?://[^"\']*spyderrock\.com/[^"\']+)["\']', page, flags=re.I)
        if not dl_m:
            dl_m = re.search(r'<a[^>]+download[^>]+href=["\'](https?://[^"\']+)["\']', page, flags=re.I)
        if not dl_m:
            raise RuntimeError(f"Qiwi indirme bağlantısı bulunamadı: {url}")
        dl_url = html.unescape(dl_m.group(1))
        name_m = re.search(r'<h1[^>]*class="[^"]*page_TextHeading[^"]*"[^>]*>(.*?)</h1>', page, flags=re.S | re.I)
        if not name_m:
            name_m = re.search(r"<title>(.*?)</title>", page, flags=re.S | re.I)
        name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else ident
        name = re.sub(r"\s*[-|]\s*qiwi\.gg.*$", "", name, flags=re.I).strip() or ident
        hdrs = {"Referer": url}
        return CloudFile(name, head_size(s, dl_url, hdrs), url=dl_url, headers=hdrs)


def register(ctx) -> None:
    ctx.register_cloud(Qiwi())
