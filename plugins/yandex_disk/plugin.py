"""Yandex Disk herkese acik paylasimlari (klasor alt klasorleriyle / tek dosya). Resmi public API, anahtar gerekmez."""
from __future__ import annotations

import re

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, join, session

API = "https://cloud-api.yandex.net/v1/disk/public/resources"


class YandexDisk(CloudProvider):
    name = "yandex_disk"
    hosts = ("disk.yandex.ru", "disk.yandex.com", "disk.yandex.com.tr", "disk.yandex.kz", "disk.yandex.by",
             "disk.yandex.uz", "disk.360.yandex.ru", "yadi.sk")
    path_re = re.compile(r"^/(d|i|public)/")

    def _get(self, s, key: str, path: str, offset: int) -> dict:
        return get_json(s, API, params={"public_key": key, "path": path, "limit": 1000, "offset": offset})

    def _items(self, s, key: str, path: str, first: dict | None = None) -> list[dict]:
        data = first or self._get(s, key, path, 0)
        items: list[dict] = []
        while True:
            emb = data.get("_embedded") or {}
            page = emb.get("items") or []
            items += page
            if not page or len(items) >= int(emb.get("total") or 0):
                return items
            data = self._get(s, key, path, len(items))

    def list(self, url: str) -> CloudListing:
        s = session()
        key = url.split("?")[0].split("#")[0]
        root = self._get(s, key, "/", 0)
        if root.get("type") == "file":
            name = root.get("name") or "file"
            return CloudListing(self.name, name, is_folder=False, ctx={"key": key}, files=[
                CloudFile(name, int(root.get("size") or 0), url=root.get("file") or "", ref="/")])
        files: list[CloudFile] = []
        stack: list[tuple[str, str, dict | None]] = [("/", "", root)]
        while stack:
            path, rel, first = stack.pop()
            for it in self._items(s, key, path, first):
                name = it.get("name") or ""
                if it.get("type") == "dir":
                    stack.append((it.get("path") or join(path, name), join(rel, name), None))
                else:
                    files.append(CloudFile(join(rel, name), int(it.get("size") or 0),
                                           url=it.get("file") or "", ref=it.get("path")))
        return CloudListing(self.name, root.get("name") or "Yandex Disk", files, ctx={"key": key})

    def file_request(self, listing: CloudListing, f: CloudFile):
        if f.url:
            return f.url, {}, {}
        # bazi dosyalarda liste "file" alanini vermez -> indirme ucu
        data = get_json(session(), API + "/download", params={"public_key": listing.ctx["key"], "path": f.ref or "/"})
        href = data.get("href")
        if not href:
            raise CloudError("cloud_failed", f.path)
        return href, {}, {}


def register(ctx) -> None:
    ctx.register_cloud(YandexDisk())
