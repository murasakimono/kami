"""Google Drive: herkese acik klasor (alt klasorleriyle) ve tek dosya. API anahtari gerekmez.

Klasor: drive.google.com/embeddedfolderview?id=<id> sayfasi (girdi adi + kimlik; boyut vermez).
Dosya:  drive.usercontent.google.com/download?id=<id>&export=download&confirm=t
        Buyuk dosyada "virus taramasi yapilamadi" sayfasi gelirse formdaki uuid ile tekrar.
"""
from __future__ import annotations

import html
import re
from urllib.parse import parse_qs, urlencode, urlparse

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, join, session

DL = "https://drive.usercontent.google.com/download"
_ENTRY = re.compile(
    r'<div class="flip-entry" id="entry-([\w-]+)".*?<a href="([^"]+)".*?<div class="flip-entry-title">([^<]*)</div>',
    re.S)
_DOCS = re.compile(r"docs\.google\.com/(document|spreadsheets|presentation)/d/([\w-]+)")
_EXPORT = {"document": "docx", "spreadsheets": "xlsx", "presentation": "pptx"}
_CD_NAME = re.compile(r"filename\*=UTF-8''([^;]+)|filename=\"([^\"]+)\"", re.I)


def _id_from(url: str) -> tuple[str, str]:
    """-> (folder|file, id)"""
    p = urlparse(url)
    m = re.search(r"/folders/([\w-]{10,})", p.path)
    if m:
        return "folder", m.group(1)
    m = re.search(r"/(?:file/d|document/d|spreadsheets/d|presentation/d)/([\w-]{10,})", p.path)
    if m:
        return "file", m.group(1)
    q = parse_qs(p.query)
    if q.get("id"):
        kind = "folder" if "folderview" in p.path else "file"
        return kind, q["id"][0]
    raise CloudError("cloud_unsupported", url)


class GoogleDrive(CloudProvider):
    name = "gdrive"
    hosts = ("drive.google.com", "drive.usercontent.google.com")

    def can_handle(self, url: str) -> bool:
        if not super().can_handle(url):
            return False
        try:
            _id_from(url)
            return True
        except CloudError:
            return False

    def _folder(self, s, fid: str) -> tuple[str, list[tuple[str, str, bool]]]:
        r = s.get("https://drive.google.com/embeddedfolderview", params={"id": fid}, timeout=20)
        if r.status_code == 404:
            raise CloudError("cloud_not_found", fid)
        if r.status_code in (401, 403) or "accounts.google.com" in r.url:
            raise CloudError("cloud_denied", fid)
        r.raise_for_status()
        m = re.search(r"<title>([^<]*)</title>", r.text)
        title = html.unescape(m.group(1)).strip() if m else fid
        entries = [(eid, html.unescape(name).strip(), html.unescape(href))
                   for eid, href, name in _ENTRY.findall(r.text)]
        return title, entries

    def list(self, url: str) -> CloudListing:
        s = session()
        kind, fid = _id_from(url)
        if kind == "file":
            name, size, dl = self._file_info(s, fid)
            return CloudListing(self.name, name, [CloudFile(name, size, url=dl, ref=fid)], is_folder=False)
        title, entries = self._folder(s, fid)
        files: list[CloudFile] = []
        queue = [("", entries)]
        seen = {fid}
        while queue:
            rel, items = queue.pop(0)
            for eid, name, href in items:
                if "/folders/" in href:
                    if eid not in seen and len(seen) < 2000:
                        seen.add(eid)
                        queue.append((join(rel, name), self._folder(s, eid)[1]))
                    continue
                doc = _DOCS.search(href)
                if doc:  # Google Dokumanlar: indirilmez, Office bicimine disa aktarilir
                    ext = _EXPORT[doc.group(1)]
                    if not name.lower().endswith("." + ext):
                        name = f"{name}.{ext}"
                    url = f"https://docs.google.com/{doc.group(1)}/d/{doc.group(2)}/export?format={ext}"
                    files.append(CloudFile(join(rel, name), 0, url=url, ref=eid))
                else:
                    files.append(CloudFile(join(rel, name), 0, ref=eid))
        return CloudListing(self.name, title, files)

    def _file_info(self, s, fid: str) -> tuple[str, int, str]:
        """Indirme linkini dogrular: -> (dosya adi, boyut, son url)."""
        url = f"{DL}?{urlencode({'id': fid, 'export': 'download', 'confirm': 't'})}"
        for _ in range(2):
            r = s.get(url, stream=True, timeout=30)
            try:
                if r.status_code in (401, 403, 404):
                    raise CloudError("cloud_denied" if r.status_code != 404 else "cloud_not_found", fid)
                r.raise_for_status()
                ctype = r.headers.get("Content-Type", "")
                if "text/html" not in ctype:
                    cd = r.headers.get("Content-Disposition", "")
                    m = _CD_NAME.search(cd)
                    from urllib.parse import unquote
                    name = unquote(m.group(1)) if m and m.group(1) else (m.group(2) if m else fid)
                    return name, int(r.headers.get("Content-Length") or 0), url
                page = r.text
            finally:
                r.close()
            # virus taramasi uyarisi: formdaki gizli alanlarla tekrar
            form = re.search(r'<form[^>]+id="download-form"[^>]+action="([^"]+)"(.*?)</form>', page, re.S)
            if not form:
                if "Quota exceeded" in page or "too many users" in page.lower():
                    raise CloudError("cloud_quota", fid)
                raise CloudError("cloud_denied", fid)
            fields = dict(re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)"', form.group(2)))
            url = f"{html.unescape(form.group(1))}?{urlencode(fields)}"
        raise CloudError("cloud_failed", fid)

    def file_request(self, listing: CloudListing, f: CloudFile):
        if f.url:
            return f.url, {}, {}
        name, size, url = self._file_info(session(), f.ref)
        if size and not f.size:
            f.size = size
        return url, {}, {}


def register(ctx) -> None:
    ctx.register_cloud(GoogleDrive())
