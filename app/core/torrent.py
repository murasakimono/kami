"""Yerel torrent (aria2'nin BitTorrent destegi).

Akis: magnet -> aria2 yalnizca metadata indirir (bt-metadata-only) -> .torrent data/torrents/'a kaydedilir;
.torrent dosyasi/linki -> baytlar dogrudan. Dosya listesi arayuzde secilir (bulut penceresi),
secilenler aria2.addTorrent + select-file ile iner. Paylasim (seed) ayari indirme eklenirken uygulanir.
"""
from __future__ import annotations

import hashlib
import logging
import os
import re
import secrets
import shutil
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

MAX_TORRENT = 10 * 1024 * 1024
# Bu agda DHT onyuklemesi cevapsiz kaliyor (04.11 olculdu): tracker'siz magnet 150 sn'de bulunamadi,
# bu listeyle Ubuntu 33 sn / Sintel 8 sn. Ozel (private) torrentlere EKLENMEZ.
PUBLIC_TRACKERS = ",".join([
    "http://tracker.opentrackr.org:1337/announce",
    "udp://tracker.opentrackr.org:1337/announce",
    "udp://open.stealth.si:80/announce",
    "udp://tracker.torrent.eu.org:451/announce",
    "udp://exodus.desync.com:6969/announce",
    "udp://explodie.org:6969/announce",
])


class TorrentError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


# ---------------------------------------------------------------- bencode
def _bdecode(data: bytes, i: int = 0) -> tuple[Any, int]:
    c = data[i:i + 1]
    if c == b"i":
        end = data.index(b"e", i)
        return int(data[i + 1:end]), end + 1
    if c == b"l":
        i += 1
        out = []
        while data[i:i + 1] != b"e":
            v, i = _bdecode(data, i)
            out.append(v)
        return out, i + 1
    if c == b"d":
        i += 1
        d: dict[bytes, Any] = {}
        while data[i:i + 1] != b"e":
            k, i = _bdecode(data, i)
            v, i = _bdecode(data, i)
            d[k] = v
        return d, i + 1
    if c.isdigit():
        colon = data.index(b":", i)
        n = int(data[i:colon])
        start = colon + 1
        if start + n > len(data):
            raise ValueError("kisa veri")
        return data[start:start + n], start + n
    raise ValueError(f"gecersiz bencode @{i}")


def _info_span(data: bytes) -> tuple[int, int]:
    """Kok sozlukteki 'info' degerinin ham bayt araligi (infohash = sha1(bu aralik))."""
    if data[:1] != b"d":
        raise ValueError("sozluk degil")
    i = 1
    while data[i:i + 1] != b"e":
        k, i = _bdecode(data, i)
        start = i
        _, i = _bdecode(data, i)
        if k == b"info":
            return start, i
    raise ValueError("info yok")


def _text(b: Any) -> str:
    if isinstance(b, bytes):
        return b.decode("utf-8", "replace")
    return str(b or "")


@dataclass
class TorrentMeta:
    name: str
    infohash: str
    files: list[dict[str, Any]] = field(default_factory=list)   # [{path, size}] (path: "a/b.mkv", kok adi YOK)
    multi: bool = False
    private: bool = False

    @property
    def total(self) -> int:
        return sum(f["size"] for f in self.files)


def parse_torrent(data: bytes) -> TorrentMeta:
    try:
        root, _ = _bdecode(data)
        s, e = _info_span(data)
        info = root[b"info"]
        name = _text(info.get(b"name.utf-8") or info.get(b"name")) or "torrent"
        files: list[dict[str, Any]] = []
        if b"files" in info:
            for f in info[b"files"]:
                parts = f.get(b"path.utf-8") or f.get(b"path") or []
                path = "/".join(_text(p) for p in parts if p)
                # BEP 47 dolgu dosyalari (aria2 de listeler, secime koymayiz ama sira icin tutariz)
                pad = b"p" in (f.get(b"attr") or b"")
                files.append({"path": path, "size": int(f.get(b"length") or 0), "pad": pad})
            multi = True
        else:
            files.append({"path": name, "size": int(info.get(b"length") or 0), "pad": False})
            multi = False
    except (ValueError, KeyError, TypeError, AttributeError, IndexError) as exc:
        raise TorrentError("bad_torrent", type(exc).__name__) from None
    private = info.get(b"private") == 1
    return TorrentMeta(name=name, infohash=hashlib.sha1(data[s:e]).hexdigest(), files=files, multi=multi,
                       private=private)


# ---------------------------------------------------------------- servis
class TorrentService:
    """Listeleri token ile tutar (bulut listeleri gibi); .torrent dosyalari data/torrents/<infohash>.torrent."""

    TTL = 3600

    def __init__(self, engine: Any, store_dir: Path) -> None:
        self.engine = engine
        self.dir = Path(store_dir)
        self._lists: dict[str, tuple[float, TorrentMeta, Path]] = {}
        self._lock = threading.Lock()

    # ---- kaynaklar
    def from_bytes(self, data: bytes) -> tuple[str, TorrentMeta]:
        if not data or len(data) > MAX_TORRENT or not data.lstrip().startswith(b"d"):
            raise TorrentError("bad_torrent")
        meta = parse_torrent(data)
        self.dir.mkdir(parents=True, exist_ok=True)
        path = self.dir / f"{meta.infohash}.torrent"
        if not path.exists():
            tmp = path.with_suffix(".tmp")
            tmp.write_bytes(data)
            os.replace(tmp, path)
        return self._keep(meta, path), meta

    def from_magnet(self, magnet: str, timeout: float = 180.0) -> tuple[str, TorrentMeta]:
        """aria2 ile yalnizca metadata (genelde birkac sn; es yoksa zaman asimi)."""
        if not re.match(r"^magnet:\?", magnet or "", re.I) or "xt=urn:btih:" not in magnet.lower():
            raise TorrentError("bad_magnet")
        work = self.dir / "meta" / secrets.token_hex(6)
        work.mkdir(parents=True, exist_ok=True)
        gid = ""
        try:
            gid = self.engine.call("aria2.addUri", [magnet], {
                "dir": str(work), "bt-metadata-only": "true", "bt-save-metadata": "true",
                "follow-torrent": "false", "seed-time": "0", "bt-tracker": PUBLIC_TRACKERS})
            deadline = time.monotonic() + timeout
            while time.monotonic() < deadline:
                st = self.engine.call("aria2.tellStatus", gid, ["status", "errorCode", "errorMessage"])
                status = st.get("status")
                if status == "complete":
                    break
                if status in ("error", "removed"):
                    raise TorrentError("torrent_meta_failed", st.get("errorMessage") or st.get("errorCode") or "")
                time.sleep(0.5)
            else:
                raise TorrentError("torrent_no_peers")
            found = sorted(work.glob("*.torrent"))
            if not found:
                raise TorrentError("torrent_meta_failed", "no_file")
            return self.from_bytes(found[0].read_bytes())
        finally:
            if gid:
                for m in ("aria2.forceRemove", "aria2.removeDownloadResult"):
                    try:
                        self.engine.call(m, gid)
                    except Exception:
                        pass
            shutil.rmtree(work, ignore_errors=True)

    # ---- token
    def _keep(self, meta: TorrentMeta, path: Path) -> str:
        token = secrets.token_urlsafe(9)
        now = time.time()
        with self._lock:
            for k in [k for k, v in self._lists.items() if now - v[0] > self.TTL]:
                self._lists.pop(k, None)
            self._lists[token] = (now, meta, path)
        return token

    def get(self, token: str) -> tuple[TorrentMeta, Path]:
        with self._lock:
            item = self._lists.get(str(token))
        if not item:
            raise TorrentError("cloud_expired")
        return item[1], item[2]

    @staticmethod
    def public(token: str, meta: TorrentMeta) -> dict[str, Any]:
        """Bulut secim penceresinin bekledigi bicim (dolgu dosyalari gizli; index aria2 sirasi icin korunur)."""
        files = [{"path": f["path"], "size": f["size"], "i": i} for i, f in enumerate(meta.files) if not f["pad"]]
        return {"kind": "torrent", "token": token, "title": meta.name, "files": files, "total": meta.total,
                "note": "", "is_folder": meta.multi}
