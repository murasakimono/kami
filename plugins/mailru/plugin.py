"""Cloud Mail.ru herkese acik paylasimlari (klasor alt klasorleriyle / tek dosya)."""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, join, session

BASE = "https://cloud.mail.ru/api/v2"


class MailRu(CloudProvider):
    name = "mailru"
    hosts = ("cloud.mail.ru",)
    path_re = re.compile(r"^/public/[^/]+/[^/]+")

    def _folder(self, s, weblink: str, offset: int = 0) -> dict:
        data = get_json(s, BASE + "/folder", params={"weblink": weblink, "offset": offset, "limit": 500})
        return data.get("body") or {}

    def list(self, url: str) -> CloudListing:
        s = session()
        weblink = unquote(urlparse(url).path)[len("/public/"):].strip("/")
        root = self._folder(s, weblink)
        if root.get("type") == "file" or root.get("kind") == "file":
            return CloudListing(self.name, root.get("name") or weblink.rsplit("/", 1)[-1], is_folder=False,
                                files=[CloudFile(root.get("name") or "file", int(root.get("size") or 0), ref=weblink)])
        files: list[CloudFile] = []
        queue = [(weblink, "", root)]
        while queue:
            link, rel, body = queue.pop(0)
            if body is None:
                body = self._folder(s, link)
            items = list(body.get("list") or [])
            total = int((body.get("count") or {}).get("files", 0)) + int((body.get("count") or {}).get("folders", 0))
            while total and len(items) < total:
                more = self._folder(s, link, len(items)).get("list") or []
                if not more:
                    break
                items += more
            for it in items:
                name = it.get("name") or ""
                if it.get("type") == "folder" or it.get("kind") == "folder":
                    queue.append((it.get("weblink") or f"{link}/{name}", join(rel, name), None))
                else:
                    files.append(CloudFile(join(rel, name), int(it.get("size") or 0),
                                           ref=it.get("weblink") or f"{link}/{name}"))
        if len(files) == 1 and files[0].ref.strip("/") == weblink:
            # dosya linki: API dosyayi iceren sahte bir klasor ("/") dondurur
            return CloudListing(self.name, files[0].name, [files[0]], is_folder=False)
        return CloudListing(self.name, root.get("name") or "Cloud Mail.ru", files)

    def file_request(self, listing: CloudListing, f: CloudFile):
        base = listing.ctx.get("dl")
        if not base:
            d = get_json(session(), BASE + "/dispatcher")
            try:
                base = d["body"]["weblink_get"][0]["url"].rstrip("/")
            except (KeyError, IndexError, TypeError):
                raise CloudError("cloud_failed", "dispatcher") from None
            listing.ctx["dl"] = base
        return f"{base}/{quote(f.ref)}", {}, {}


def register(ctx) -> None:
    ctx.register_cloud(MailRu())
