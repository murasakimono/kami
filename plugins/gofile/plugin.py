"""GoFile: misafir token ile /d/<id> icerigini (alt klasorleriyle) cozer."""
from __future__ import annotations

import re
from urllib.parse import urlparse

from app.core.cloud import CloudFile, CloudListing, CloudProvider, join, session

API = "https://api.gofile.io"


class GoFile(CloudProvider):
    name = "gofile"
    hosts = ("gofile.io",)
    path_re = re.compile(r"^/d/([^/]+)")

    def list(self, url: str) -> CloudListing:
        m = self.path_re.match(urlparse(url).path)
        if not m:
            raise ValueError("Geçersiz GoFile bağlantısı")
        cid = m.group(1)
        s = session()
        acc = s.post(f"{API}/accounts", timeout=15).json()
        token = ((acc.get("data") or {}).get("token")) or ""
        if not token:
            raise RuntimeError("GoFile misafir oturumu alınamadı")
        headers = {"Authorization": f"Bearer {token}", "Cookie": f"accountToken={token}"}
        r = s.get(f"{API}/contents/{cid}", params={"wt": "4fd6sg89d7s6"}, headers=headers, timeout=20).json()
        if r.get("status") != "ok":
            raise RuntimeError(f"GoFile hatası: {r.get('status')}")
        root = r.get("data") or {}
        files: list[CloudFile] = []
        self._walk(s, root, "", headers, files)
        return CloudListing(self.name, root.get("name") or cid, is_folder=True, files=files)

    def _walk(self, s, node: dict, rel: str, headers: dict, out: list[CloudFile]) -> None:
        children = node.get("children") or {}
        for item in (children.values() if isinstance(children, dict) else children):
            if not isinstance(item, dict):
                continue
            name = item.get("name") or item.get("id") or "file"
            if item.get("type") == "folder":
                sub_id = item.get("id")
                sub = item
                if sub_id and not item.get("children"):
                    try:
                        res = s.get(f"{API}/contents/{sub_id}", params={"wt": "4fd6sg89d7s6"},
                                    headers=headers, timeout=20).json()
                        if res.get("status") == "ok":
                            sub = res.get("data") or item
                    except Exception:
                        pass
                self._walk(s, sub, join(rel, name), headers, out)
            else:
                link = item.get("link") or item.get("directLink") or ""
                if link:
                    out.append(CloudFile(
                        join(rel, name), int(item.get("size") or 0),
                        url=link, headers=dict(headers),
                    ))


def register(ctx) -> None:
    ctx.register_cloud(GoFile())
