"""Mediafire: herkese acik klasor (alt klasorleriyle) ve tek dosya. Liste resmi API'den, indirme linki dosya sayfasindan."""
from __future__ import annotations

import base64
import html
import re
from urllib.parse import urlparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, get_json, join, session

API = "https://www.mediafire.com/api/1.5"
_DL = re.compile(r'href="(https?://download\d*\.mediafire\.com/[^"]+)"')
_SCRAMBLED = re.compile(r'data-scrambled-url="([^"]+)"')


class Mediafire(CloudProvider):
    name = "mediafire"
    hosts = ("mediafire.com",)
    path_re = re.compile(r"^/(folder|file|file_premium|view|download)/|^/\?")

    def can_handle(self, url: str) -> bool:
        p = urlparse(url)
        host = (p.hostname or "").lower()
        if not (host == "mediafire.com" or host.endswith(".mediafire.com")):
            return False
        return bool(re.match(r"^/(folder|file|file_premium|view|download)/\w+", p.path)) or (p.path in ("", "/") and bool(p.query))

    @staticmethod
    def _api(s, method: str, **params) -> dict:
        data = get_json(s, f"{API}/{method}.php", params={**params, "response_format": "json"})
        resp = data.get("response") or {}
        if resp.get("result") == "Error":
            msg = str(resp.get("message") or "")
            raise CloudError("cloud_not_found" if "not found" in msg.lower() or "invalid" in msg.lower()
                             else "cloud_failed", msg)
        return resp

    def list(self, url: str) -> CloudListing:
        s = session()
        p = urlparse(url)
        m = re.match(r"^/folder/(\w+)", p.path)
        if m:
            key = m.group(1)
            info = self._api(s, "folder/get_info", folder_key=key).get("folder_info") or {}
            files: list[CloudFile] = []
            queue = [(key, "")]
            seen = {key}
            while queue:
                fk, rel = queue.pop(0)
                for f in self._content(s, fk, "files"):
                    if f.get("password_protected") == "yes":
                        continue
                    files.append(CloudFile(join(rel, f.get("filename") or f["quickkey"]), int(f.get("size") or 0),
                                           ref=f["quickkey"]))
                for d in self._content(s, fk, "folders"):
                    if d.get("folderkey") and d["folderkey"] not in seen:
                        seen.add(d["folderkey"])
                        queue.append((d["folderkey"], join(rel, d.get("name") or d["folderkey"])))
            return CloudListing(self.name, info.get("name") or key, files)
        m = re.match(r"^/(?:file|file_premium|view|download)/(\w+)", p.path)
        qk = m.group(1) if m else p.query.split("&")[0]
        fi = self._api(s, "file/get_info", quick_key=qk).get("file_info") or {}
        if fi.get("password_protected") == "yes":
            raise CloudError("cloud_password", qk)
        name = fi.get("filename") or qk
        return CloudListing(self.name, name, [CloudFile(name, int(fi.get("size") or 0), ref=qk)], is_folder=False)

    def _content(self, s, key: str, ctype: str) -> list[dict]:
        out: list[dict] = []
        chunk = 1
        while chunk < 500:
            fc = self._api(s, "folder/get_content", folder_key=key, content_type=ctype, chunk=chunk,
                           filter="all").get("folder_content") or {}
            out += fc.get(ctype) or []
            if fc.get("more_chunks") != "yes":
                break
            chunk += 1
        return out

    def file_request(self, listing: CloudListing, f: CloudFile):
        r = session().get(f"https://www.mediafire.com/file/{f.ref}", timeout=30)
        r.raise_for_status()
        m = _DL.search(r.text)
        if m:
            return html.unescape(m.group(1)), {}, {}
        sm = _SCRAMBLED.search(r.text)
        if sm:
            try:
                return base64.b64decode(sm.group(1)).decode(), {}, {}
            except Exception:
                pass
        if "dangerous" in r.text.lower() or "blocked" in r.text.lower():
            raise CloudError("cloud_denied", f.ref)
        raise CloudError("cloud_failed", f"indirme linki bulunamadi: {f.ref}")


def register(ctx) -> None:
    ctx.register_cloud(Mediafire())
