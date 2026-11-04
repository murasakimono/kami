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


TRACKER_LIST_URL = "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt"
_TRACKER_FILE: Path | None = None     # data/trackers.txt (main ayarlar); guncel liste burada


def set_tracker_file(path: Path) -> None:
    global _TRACKER_FILE
    _TRACKER_FILE = Path(path)


def trackers() -> str:
    """Yerlesik liste + (varsa) indirilmis guncel liste; tekrarsiz, en cok 40."""
    out = PUBLIC_TRACKERS.split(",")
    if _TRACKER_FILE and _TRACKER_FILE.exists():
        try:
            for ln in _TRACKER_FILE.read_text(encoding="utf-8").split():
                if ln.startswith(("udp://", "http://", "https://")) and ln not in out:
                    out.append(ln)
        except OSError:
            pass
    return ",".join(out[:40])


def update_trackers(max_age_h: float = 24.0) -> bool:
    """Guncel izleyici listesini indir (gunde bir). Sadece bicimi dogru satirlar yazilir."""
    if not _TRACKER_FILE:
        return False
    try:
        if _TRACKER_FILE.exists() and time.time() - _TRACKER_FILE.stat().st_mtime < max_age_h * 3600:
            return False
        import requests
        r = requests.get(TRACKER_LIST_URL, timeout=15)
        r.raise_for_status()
        lines = [ln.strip() for ln in r.text[:200_000].split() if
                 re.fullmatch(r"(udp|https?)://[A-Za-z0-9.\-]+:\d{1,5}/announce", ln.strip())]
        if not lines:
            return False
        _TRACKER_FILE.parent.mkdir(parents=True, exist_ok=True)
        _TRACKER_FILE.write_text("\n".join(lines[:60]), encoding="utf-8")
        log.info("Izleyici listesi guncellendi: %d", len(lines))
        return True
    except Exception as exc:
        log.warning("Izleyici listesi alinamadi: %s", type(exc).__name__)
        return False


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
        self._jobs: dict[str, dict[str, Any]] = {}
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

    def from_magnet(self, magnet: str, timeout: float = 180.0, on_progress=None,
                    cancel: threading.Event | None = None) -> tuple[str, TorrentMeta]:
        """aria2 ile yalnizca metadata (genelde birkac sn; es yoksa zaman asimi).
        on_progress({peers, seeders, elapsed}) her yarim saniyede; cancel set edilirse durur."""
        if not re.match(r"^magnet:\?", magnet or "", re.I) or "xt=urn:btih:" not in magnet.lower():
            raise TorrentError("bad_magnet")
        work = self.dir / "meta" / secrets.token_hex(6)
        work.mkdir(parents=True, exist_ok=True)
        gid = ""
        t0 = time.monotonic()
        try:
            gid = self.engine.call("aria2.addUri", [magnet], {
                "dir": str(work), "bt-metadata-only": "true", "bt-save-metadata": "true",
                "follow-torrent": "false", "seed-time": "0", "bt-tracker": trackers()})
            deadline = t0 + timeout
            while time.monotonic() < deadline:
                if cancel is not None and cancel.is_set():
                    raise TorrentError("cancelled")
                st = self.engine.call("aria2.tellStatus", gid,
                                      ["status", "errorCode", "errorMessage", "connections", "numSeeders"])
                status = st.get("status")
                if status == "complete":
                    break
                if status in ("error", "removed"):
                    raise TorrentError("torrent_meta_failed", st.get("errorMessage") or st.get("errorCode") or "")
                if on_progress:
                    on_progress({"peers": int(st.get("connections") or 0), "seeders": int(st.get("numSeeders") or 0),
                                 "elapsed": int(time.monotonic() - t0)})
                time.sleep(0.5)
            else:
                raise TorrentError("torrent_no_peers")
            found = sorted(work.glob("*.torrent"))
            if not found:
                raise TorrentError("torrent_meta_failed", "no_file")
            log.info("Magnet meta verisi %.0f sn'de alindi", time.monotonic() - t0)
            return self.from_bytes(found[0].read_bytes())
        finally:
            if gid:
                for m in ("aria2.forceRemove", "aria2.removeDownloadResult"):
                    try:
                        self.engine.call(m, gid)
                    except Exception:
                        pass
            shutil.rmtree(work, ignore_errors=True)

    # ---- arka plan meta veri isleri (arayuz bekletilmez, "N es" gosterir)
    def start_magnet(self, magnet: str, timeout: float = 180.0) -> str:
        if not re.match(r"^magnet:\?", magnet or "", re.I) or "xt=urn:btih:" not in magnet.lower():
            raise TorrentError("bad_magnet")
        jid = secrets.token_urlsafe(6)
        job = {"state": "searching", "peers": 0, "seeders": 0, "elapsed": 0, "cancel": threading.Event(),
               "at": time.time()}
        with self._lock:
            for k in [k for k, v in self._jobs.items() if time.time() - v["at"] > self.TTL]:
                self._jobs.pop(k, None)
            self._jobs[jid] = job

        def run() -> None:
            try:
                token, meta = self.from_magnet(magnet, timeout, on_progress=job.update, cancel=job["cancel"])
                job.update(state="done", token=token)
            except TorrentError as exc:
                log.warning("Magnet meta verisi alinamadi: %s %s", exc.code, exc.detail)
                job.update(state="error", error=exc.code, detail=exc.detail)
            except Exception as exc:
                log.exception("Magnet meta verisi hatasi")
                job.update(state="error", error="torrent_meta_failed", detail=type(exc).__name__)

        threading.Thread(target=run, name="kami-magnet-meta", daemon=True).start()
        return jid

    def job(self, jid: str) -> dict[str, Any]:
        with self._lock:
            job = self._jobs.get(str(jid))
        if not job:
            return {"state": "error", "error": "cloud_expired"}
        return {k: v for k, v in job.items() if k not in ("cancel", "at")}

    def cancel_job(self, jid: str) -> None:
        with self._lock:
            job = self._jobs.get(str(jid))
        if job:
            job["cancel"].set()

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
