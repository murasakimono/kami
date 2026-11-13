"""Send.cm: form POST / yonlendirme ile dogrudan dosya baglantisi cozer."""
from __future__ import annotations

import html
import re
from urllib.parse import urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, session


class SendCm(CloudProvider):
    name = "sendcm"
    hosts = ("send.cm", "send.now")
    path_re = re.compile(r"^/(?:d/)?([a-zA-Z0-9]{6,})")

    def list(self, url: str) -> CloudListing:
        m = self.path_re.match(urlparse(url).path)
        if not m:
            raise ValueError("Geçersiz Send.cm bağlantısı")
        ident = m.group(1)
        s = session()
        r = s.get(url, timeout=20)
        r.raise_for_status()
        page = r.text
        name_m = re.search(r'<h6[^>]*>(.*?)</h6>', page, flags=re.S | re.I) or re.search(r"<title>(.*?)</title>", page, flags=re.S | re.I)
        name = html.unescape(re.sub(r"<[^>]+>", "", name_m.group(1))).strip() if name_m else ident
        name = re.sub(r"^\s*Download\s+", "", name, flags=re.I).strip() or ident
        fields: dict[str, str] = {}
        for tag in re.findall(r"<input\b[^>]*>", page, flags=re.I):
            if not re.search(r'type=["\']hidden["\']', tag, flags=re.I):
                continue
            nm = re.search(r'name=["\']([^"\']+)["\']', tag, flags=re.I)
            if not nm:
                continue
            vm = re.search(r'value=["\']([^"\']*)["\']', tag, flags=re.I)
            fields[nm.group(1)] = html.unescape(vm.group(1)) if vm else ""
        if not fields:
            fields = {"op": "download2", "id": ident, "rand": "", "referer": url, "method_free": "", "method_premium": ""}
        hdrs = {"Referer": url}
        post_r = s.post(url, data=fields, headers=hdrs, allow_redirects=False, timeout=20)
        dl = post_r.headers.get("Location") or ""
        if not dl:
            dl_m = re.search(r'href=["\'](https?://[^"\']+/d/[^"\']+)["\']', post_r.text, flags=re.I)
            dl = html.unescape(dl_m.group(1)) if dl_m else ""
        if not dl:
            raise RuntimeError("Send.cm indirme bağlantısı alınamadı")
        return CloudListing(self.name, name, is_folder=False, files=[
            CloudFile(name, 0, url=dl, headers=hdrs),
        ])


def register(ctx) -> None:
    ctx.register_cloud(SendCm())
