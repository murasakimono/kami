"""Real-Debrid: yapistir-gec (hoster linki / magnet / .torrent -> RD -> dogrudan link -> aria2) + hesap listesi.

Token Ayarlar'dan girilir, DPAPI ile data/rd_token.bin'e yazilir. Token ASLA loga, arayuze ya da
istisna metnine konmaz (yalnizca Authorization basliginda gider).

Torrent akisi: addMagnet/addTorrent -> selectFiles(all) -> RD indirir (cogu zaman onbellekte, aninda) ->
"downloaded" olunca linkler unrestrict edilir -> aria2. Bekleyen torrentler data/rd_pending.json'da
tutulur (Kami kapanip acilsa da bitince kuyruga girer).
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

import requests

log = logging.getLogger(__name__)

API = "https://api.real-debrid.com/rest/1.0"
UA = "Kami/0.4"
MAGNET_RE = re.compile(r"^magnet:\?", re.I)
FAILED_STATES = {"magnet_error", "error", "virus", "dead"}


class DebridError(Exception):
    """code: arayuz anahtari (err_<code>), detail: RD'nin hata adi (token icermez)."""

    def __init__(self, code: str, detail: str = "") -> None:
        super().__init__(code)
        self.code = code
        self.detail = detail


def is_magnet(text: str) -> bool:
    return bool(MAGNET_RE.match((text or "").strip()))


def is_torrent_url(url: str) -> bool:
    try:
        return urlparse(url).path.lower().endswith(".torrent")
    except ValueError:
        return False


def host_of(url: str) -> str:
    try:
        return (urlparse(url).hostname or "").lower().removeprefix("www.")
    except ValueError:
        return ""


# RD API hata listesi (api.real-debrid.com, "error_code") -> Kami kodu (arayuzde err_<kod> metni).
_RD_CODES: dict[int, str] = {
    -1: "rd_service", 25: "rd_service", 37: "rd_service",
    5: "rd_slow", 34: "rd_slow",
    8: "rd_bad_token",
    9: "rd_denied", 10: "rd_denied", 11: "rd_denied", 14: "rd_locked", 15: "rd_denied", 20: "rd_premium",
    16: "rd_unsupported",
    17: "rd_hoster_down", 18: "rd_hoster_limit", 19: "rd_hoster_down",
    21: "rd_too_many",
    22: "rd_ip",
    23: "rd_traffic", 36: "rd_traffic",
    24: "rd_unavailable",
    26: "rd_torrent_big", 29: "rd_torrent_big",
    27: "rd_bad_torrent", 30: "rd_bad_torrent",
    28: "rd_not_allowed",
    33: "rd_already",
    35: "rd_infringing",
}
_RD_NAMES: dict[str, str] = {
    "bad_token": "rd_bad_token", "bad_token_type": "rd_bad_token",
    "permission_denied": "rd_denied", "account_locked": "rd_locked", "not_premium": "rd_premium",
    "hoster_not_free": "rd_premium", "hoster_unsupported": "rd_unsupported", "unsupported_hoster": "rd_unsupported",
    "hoster_in_maintenance": "rd_hoster_down", "hoster_unavailable": "rd_hoster_down",
    "hoster_limit_reached": "rd_hoster_limit", "too_many_active_downloads": "rd_too_many",
    "ip_not_allowed": "rd_ip", "traffic_exhausted": "rd_traffic", "fair_usage_limit": "rd_traffic",
    "file_unavailable": "rd_unavailable", "unavailable_file": "rd_unavailable",
    "torrent_too_big": "rd_torrent_big", "upload_too_big": "rd_torrent_big",
    "torrent_file_invalid": "rd_bad_torrent", "upload_error": "rd_bad_torrent",
    "file_not_allowed": "rd_not_allowed", "torrent_already_active": "rd_already",
    "infringing_file": "rd_infringing", "slow_down": "rd_slow", "too_many_requests": "rd_slow",
    "service_unavailable": "rd_service", "internal_error": "rd_service", "disabled_endpoint": "rd_service",
}


def rd_error_code(name: str, error_code: Any = None, status: int = 0) -> str:
    """RD hata adi / numarasi -> Kami kodu. Bilinmeyen -> rd_failed (detay olarak ham ad gosterilir)."""
    code = _RD_NAMES.get(str(name or "").lower())
    if not code:
        try:
            code = _RD_CODES.get(int(error_code))
        except (TypeError, ValueError):
            code = None
    if not code and status == 401:
        code = "rd_bad_token"
    if not code and status == 403:
        code = "rd_denied"
    return code or "rd_failed"


# ---------------------------------------------------------------- token deposu (DPAPI)
class TokenStore:
    def __init__(self, path: Path) -> None:
        self.path = path
        self._lock = threading.Lock()

    def save(self, token: str) -> None:
        from app.core.vault import protect
        with self._lock:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_bytes(protect(token.encode("utf-8")))
            os.replace(tmp, self.path)

    def load(self) -> str:
        from app.core.vault import unprotect
        with self._lock:
            try:
                return unprotect(self.path.read_bytes()).decode("utf-8")
            except (OSError, ValueError, UnicodeDecodeError):
                return ""

    def clear(self) -> None:
        with self._lock:
            try:
                self.path.unlink()
            except OSError:
                pass


# ---------------------------------------------------------------- API istemcisi
class RealDebridClient:
    def __init__(self, token_getter: Callable[[], str], session: requests.Session | None = None) -> None:
        self._token = token_getter
        self.s = session or requests.Session()
        self.s.headers["User-Agent"] = UA

    def _req(self, method: str, path: str, *, auth: bool = True, **kw: Any) -> Any:
        headers = kw.pop("headers", {})
        if auth:
            token = self._token()
            if not token:
                raise DebridError("rd_no_token")
            headers["Authorization"] = f"Bearer {token}"
        kw.setdefault("timeout", 25)
        try:
            r = self.s.request(method, API + path, headers=headers, **kw)
        except requests.RequestException as exc:
            raise DebridError("rd_network", type(exc).__name__) from None   # metinde URL/baslik olmasin
        if r.status_code == 204 or not r.content:
            if r.status_code >= 400:
                raise DebridError("rd_failed", f"http_{r.status_code}")
            return None
        try:
            data = r.json()
        except ValueError:
            raise DebridError("rd_failed", f"http_{r.status_code}") from None
        if r.status_code >= 400:
            d = data if isinstance(data, dict) else {}
            name = str(d.get("error") or f"http_{r.status_code}")
            raise DebridError(rd_error_code(name, d.get("error_code"), r.status_code), name)
        return data

    # hesap
    def user(self) -> dict[str, Any]:
        return self._req("GET", "/user")

    def domains(self) -> list[str]:
        return list(self._req("GET", "/hosts/domains", auth=False) or [])

    # yapistir-gec
    def unrestrict(self, link: str) -> dict[str, Any]:
        return self._req("POST", "/unrestrict/link", data={"link": link})

    def unrestrict_folder(self, link: str) -> list[str]:
        return list(self._req("POST", "/unrestrict/folder", data={"link": link}) or [])

    # torrent
    def add_magnet(self, magnet: str) -> str:
        return str(self._req("POST", "/torrents/addMagnet", data={"magnet": magnet})["id"])

    def add_torrent(self, data: bytes) -> str:
        return str(self._req("PUT", "/torrents/addTorrent", data=data,
                             headers={"Content-Type": "application/x-bittorrent"})["id"])

    def select_all(self, tid: str) -> None:
        self._req("POST", f"/torrents/selectFiles/{tid}", data={"files": "all"})

    def torrent_info(self, tid: str) -> dict[str, Any]:
        return self._req("GET", f"/torrents/info/{tid}")

    def torrents(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._req("GET", "/torrents", params={"limit": limit}) or [])

    def downloads(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(self._req("GET", "/downloads", params={"limit": limit}) or [])

    def delete_torrent(self, tid: str) -> None:
        self._req("DELETE", f"/torrents/delete/{tid}")

    def delete_download(self, did: str) -> None:
        self._req("DELETE", f"/downloads/delete/{did}")


# ---------------------------------------------------------------- servis
class DebridService:
    """Yonetici ile RD arasindaki yapistirici. enqueue(list[dict]) -> aria2 kuyrugu (yonetici verir)."""

    DOMAINS_TTL = 6 * 3600

    def __init__(self, token_store: TokenStore, pending_path: Path | None = None,
                 client: RealDebridClient | None = None, poll_interval: float = 5.0) -> None:
        self.tokens = token_store
        self.client = client or RealDebridClient(token_store.load)
        self.pending_path = pending_path
        self.poll_interval = poll_interval
        self.enqueue: Callable[[list[dict[str, Any]], str], int] | None = None   # (dosyalar, klasor adi) -> eklenen
        self.notify: Callable[[dict[str, Any]], None] = lambda ev: None         # arayuze bildirim
        self._domains: set[str] = set()
        self._domains_at = 0.0
        self._lock = threading.Lock()
        self._pending: dict[str, dict[str, Any]] = self._load_pending()
        self._live: dict[str, dict[str, Any]] = {}     # tid -> son torrent_info ozeti (kaydedilmez)
        self._wake = threading.Event()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._user_cache: tuple[float, dict[str, Any]] | None = None

    # ---- token
    def has_token(self) -> bool:
        return bool(self.tokens.load())

    def set_token(self, token: str) -> dict[str, Any]:
        token = (token or "").strip()
        if not re.fullmatch(r"[A-Za-z0-9]{20,100}", token):
            raise DebridError("rd_bad_token", "format")
        probe = RealDebridClient(lambda: token, self.client.s)
        user = probe.user()           # gecersizse rd_bad_token firlatir, kaydetmeyiz
        self.tokens.save(token)
        self._user_cache = (time.time(), user)
        log.info("Real-Debrid token kaydedildi (kullanici: %s)", user.get("username", "?"))
        self._wake.set()
        return user

    def clear_token(self) -> None:
        self.tokens.clear()
        self._user_cache = None
        log.info("Real-Debrid token silindi")

    def status(self) -> dict[str, Any]:
        if not self.has_token():
            return {"has_token": False}
        try:
            if not self._user_cache or time.time() - self._user_cache[0] > 300:
                self._user_cache = (time.time(), self.client.user())
            u = self._user_cache[1]
            return {"has_token": True, "ok": True, "username": u.get("username", ""),
                    "type": u.get("type", ""), "expiration": u.get("expiration", ""),
                    "premium_days": int((u.get("premium") or 0) // 86400)}
        except DebridError as exc:
            return {"has_token": True, "ok": False, "error": exc.code}

    # ---- hoster destegi
    def domains(self) -> set[str]:
        if time.time() - self._domains_at > self.DOMAINS_TTL or not self._domains:
            try:
                self._domains = {d.lower() for d in self.client.domains()}
                self._domains_at = time.time()
            except DebridError as exc:
                log.warning("RD hoster listesi alinamadi: %s", exc.detail or exc.code)
                self._domains_at = time.time() - self.DOMAINS_TTL + 300   # 5 dk sonra tekrar dene
        return self._domains

    def supports(self, url: str) -> bool:
        h = host_of(url)
        if not h:
            return False
        doms = self.domains()
        return any(h == d or h.endswith("." + d) for d in doms)

    # ---- yapistir-gec
    def unrestrict_files(self, link: str) -> list[dict[str, Any]]:
        """Hoster linki -> [{url, filename, size}]. Klasor linkinde (MEGA klasoru vb.) icindeki her dosya."""
        try:
            items = [self.client.unrestrict(link)]
        except DebridError as exc:
            if exc.code != "rd_failed":     # olu dosya / token hatasi: klasor denemesi anlamsiz
                raise
            try:
                links = self.client.unrestrict_folder(link)
            except DebridError:
                raise exc from None
            if not links:
                raise exc from None
            items = [self.client.unrestrict(x) for x in links]
        return [{"url": it["download"], "filename": it.get("filename") or "", "size": int(it.get("filesize") or 0)}
                for it in items if it.get("download")]

    def add_link(self, link: str) -> int:
        files = self.unrestrict_files(link)
        if not files:
            raise DebridError("rd_failed", "no_links")
        log.info("RD'den gecirildi: %s -> %d dosya", host_of(link), len(files))
        return self._enqueue(files, "")

    def add_magnet(self, magnet: str) -> str:
        tid = self.client.add_magnet(magnet.strip())
        self._track(tid)
        return tid

    def add_torrent_bytes(self, data: bytes) -> str:
        if not data or not data.lstrip().startswith(b"d"):
            raise DebridError("rd_bad_torrent")
        tid = self.client.add_torrent(data)
        self._track(tid)
        return tid

    def add_any(self, text: str, torrent_fetch: Callable[[str], bytes] | None = None) -> dict[str, Any]:
        """Yapistirilan tek satir: magnet | .torrent linki | hoster linki."""
        text = (text or "").strip()
        if is_magnet(text):
            return {"torrent": self.add_magnet(text)}
        if not text.lower().startswith(("http://", "https://")):
            raise DebridError("bad_url")
        if is_torrent_url(text) and torrent_fetch is not None:
            return {"torrent": self.add_torrent_bytes(torrent_fetch(text))}
        return {"added": self.add_link(text)}

    def queue_torrent(self, tid: str) -> int:
        """Hesaptaki (bitmis) bir torrenti Kami'de indir."""
        info = self.client.torrent_info(tid)
        if info.get("status") != "downloaded":
            self._track(tid)
            return 0
        return self._queue_finished(info)

    def queue_download(self, item: dict[str, Any]) -> int:
        return self._enqueue([{"url": item["download"], "filename": item.get("filename") or "",
                               "size": int(item.get("filesize") or 0)}], "")

    # ---- hesap listesi
    def account_lists(self) -> dict[str, Any]:
        torrents = [{"id": t.get("id"), "name": t.get("filename") or "", "status": t.get("status") or "",
                     "progress": float(t.get("progress") or 0), "size": int(t.get("bytes") or 0),
                     "added": t.get("added") or "", "links": len(t.get("links") or []),
                     "kami": t.get("id") in self._pending}
                    for t in self.client.torrents()]
        downloads = [{"id": d.get("id"), "name": d.get("filename") or "", "size": int(d.get("filesize") or 0),
                      "host": d.get("host") or "", "generated": d.get("generated") or "",
                      "download": d.get("download") or ""}
                     for d in self.client.downloads()]
        return {"torrents": torrents, "downloads": downloads}

    # ---- bekleyen torrentler
    def _track(self, tid: str) -> None:
        with self._lock:
            self._pending.setdefault(tid, {"added": time.time(), "selected": False})
            self._save_pending()
        self._wake.set()

    def _load_pending(self) -> dict[str, dict[str, Any]]:
        if not self.pending_path:
            return {}
        try:
            data = json.loads(self.pending_path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_pending(self) -> None:
        if not self.pending_path:
            return
        try:
            self.pending_path.write_text(json.dumps(self._pending), encoding="utf-8")
        except OSError:
            log.exception("rd_pending yazilamadi")

    def start(self) -> None:
        self._thread = threading.Thread(target=self._loop, name="kami-rd", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        self._wake.set()

    def _loop(self) -> None:
        while not self._stop.is_set():
            if self._pending and self.has_token():
                self.poll_once()
            self._wake.wait(self.poll_interval)
            self._wake.clear()

    def poll_once(self) -> None:
        for tid in list(self._pending):
            try:
                self._step(tid)
            except DebridError as exc:
                if exc.code in ("rd_bad_token", "rd_no_token", "rd_network"):
                    return    # sonra tekrar
                log.warning("RD torrent %s: %s %s", tid, exc.code, exc.detail)
                self._drop(tid)
                self.notify({"kind": "error", "error": exc.code, "detail": exc.detail})

    def progress(self) -> list[dict[str, Any]]:
        """Kami'nin bekledigi RD torrentlerinin son durumu (arayuz: RD'de hazirlaniyor %, es, hiz)."""
        with self._lock:
            out = []
            for tid, p in self._pending.items():
                live = self._live.get(tid) or {}
                out.append({"id": tid, "name": live.get("name") or "", "status": live.get("status") or "queued",
                            "progress": live.get("progress", 0.0), "seeders": live.get("seeders"),
                            "speed": live.get("speed", 0)})
            return out

    def _step(self, tid: str) -> None:
        info = self.client.torrent_info(tid)
        st = info.get("status") or ""
        with self._lock:
            self._live[tid] = {"name": info.get("filename") or info.get("original_filename") or "",
                               "status": st, "progress": float(info.get("progress") or 0),
                               "seeders": info.get("seeders"), "speed": int(info.get("speed") or 0)}
        if st == "waiting_files_selection":
            self.client.select_all(tid)
            return
        if st in FAILED_STATES:
            self._drop(tid)
            log.warning("RD torrent basarisiz: %s (%s)", info.get("filename"), st)
            self.notify({"kind": "error", "error": "rd_torrent_failed", "name": info.get("filename") or ""})
            return
        if st == "downloaded":
            n = self._queue_finished(info)
            self._drop(tid)
            self.notify({"kind": "queued", "name": info.get("filename") or "", "count": n})

    def _drop(self, tid: str) -> None:
        with self._lock:
            self._pending.pop(tid, None)
            self._live.pop(tid, None)
            self._save_pending()

    def _queue_finished(self, info: dict[str, Any]) -> int:
        links = list(info.get("links") or [])
        selected = [f for f in info.get("files") or [] if f.get("selected")]
        files: list[dict[str, Any]] = []
        for i, link in enumerate(links):
            u = self.client.unrestrict(link)
            if not u.get("download"):
                continue
            rel = ""
            if len(links) == len(selected):    # link sirasi = secili dosya sirasi; klasor yapisini koru
                rel = str(selected[i].get("path") or "").strip("/")
            files.append({"url": u["download"], "filename": u.get("filename") or "",
                          "size": int(u.get("filesize") or 0), "rel": rel})
        folder = (info.get("filename") or "") if len(files) > 1 else ""
        for f in files:    # torrent kok klasoru zaten 'folder': Album/Album/... olmasin
            if folder and f["rel"].startswith(folder + "/"):
                f["rel"] = f["rel"][len(folder) + 1:]
        log.info("RD torrent hazir: %s -> %d dosya kuyruga", info.get("filename"), len(files))
        return self._enqueue(files, folder)

    def _enqueue(self, files: list[dict[str, Any]], folder: str) -> int:
        if self.enqueue is None:
            raise DebridError("rd_failed", "no_queue")
        return self.enqueue(files, folder)
