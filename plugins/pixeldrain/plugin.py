"""Pixeldrain: tek dosya (/u/), liste (/l/) ve dosya sistemi klasoru (/d/, alt klasorleriyle)."""
from __future__ import annotations

import re
from urllib.parse import quote, unquote, urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, get_json, join, session

API = "https://pixeldrain.com/api"


class Pixeldrain(CloudProvider):
    name = "pixeldrain"
    hosts = ("pixeldrain.com", "pixeldrain.net", "pixeldra.in")
    path_re = re.compile(r"^/(u|l|d)/[^/]+")

    def list(self, url: str) -> CloudListing:
        s = session()
        parts = unquote(urlparse(url).path).strip("/").split("/")
        kind, ident = parts[0], parts[1]
        if kind == "u":
            info = get_json(s, f"{API}/file/{ident}/info")
            name = info.get("name") or ident
            return CloudListing(self.name, name, is_folder=False, files=[
                CloudFile(name, int(info.get("size") or 0), url=f"{API}/file/{ident}?download")])
        if kind == "l":
            data = get_json(s, f"{API}/list/{ident}")
            files = [CloudFile(f.get("name") or f["id"], int(f.get("size") or 0),
                               url=f"{API}/file/{f['id']}?download") for f in data.get("files") or []]
            return CloudListing(self.name, data.get("title") or ident, files)
        # /d/<yol>: dosya sistemi (bucket); alt klasorler gezilir
        start = "/".join(parts[1:])
        root = self._stat(s, start)
        node = root["path"][root.get("base_index", 0)]
        if node.get("type") == "file":
            return CloudListing(self.name, node.get("name") or ident, is_folder=False, files=[
                CloudFile(node.get("name") or ident, int(node.get("file_size") or 0), url=self._dl(start))])
        files: list[CloudFile] = []
        queue = [(start, "", root)]
        while queue:
            path, rel, data = queue.pop(0)
            data = data or self._stat(s, path)
            for ch in data.get("children") or []:
                name = ch.get("name") or ""
                child = (ch.get("path") or f"/{path}/{name}").lstrip("/")
                if ch.get("type") == "dir":
                    queue.append((child, join(rel, name), None))
                else:
                    files.append(CloudFile(join(rel, name), int(ch.get("file_size") or 0), url=self._dl(child)))
        return CloudListing(self.name, node.get("name") or ident, files)

    @staticmethod
    def _stat(s, path: str) -> dict:
        return get_json(s, f"{API}/filesystem/{quote(path)}?stat")

    @staticmethod
    def _dl(path: str) -> str:
        return f"{API}/filesystem/{quote(path)}?attach"


def register(ctx) -> None:
    ctx.register_cloud(Pixeldrain())
