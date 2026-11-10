"""aria2c motoru: arka planda aria2c sureci, JSON-RPC ile kontrol.

- Sadece 127.0.0.1'i dinler, her acilista rastgele port + gizli anahtar.
- --stop-with-process ile Kami kapanirsa aria2c de kapanir.
- Yarim kalan indirmeler .aria2 kontrol dosyasi sayesinde ayni dir/out ile yeniden eklenince devam eder.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from app.core.models import Download, DownloadRequest
from app.core.plugin_api import Engine

log = logging.getLogger(__name__)

CREATE_NO_WINDOW = 0x08000000


class Aria2Error(RuntimeError):
    def __init__(self, message: str, code: int | None = None) -> None:
        super().__init__(message)
        self.code = code


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class Aria2Engine(Engine):
    name = "aria2"

    def __init__(self, exe: Path, *, connections: int = 16, max_concurrent: int = 3,
                 max_tries: int = 5, speed_limit_kib: int = 0, log_file: Path | None = None,
                 bt_port: int = 0, upload_limit_kib: int = 0, dht_file: Path | None = None,
                 disable_ipv6: bool = False) -> None:
        self.disable_ipv6 = disable_ipv6        # agda IPv6 yoksa (net.ipv6_works) her AAAA icin 21 sn beklemesin
        self.bt_port = bt_port                  # 0 = aria2 varsayilani (6881-6999)
        self.upload_limit_kib = upload_limit_kib
        self.dht_file = dht_file
        self.exe = Path(exe)
        self.connections = connections
        self.max_concurrent = max_concurrent
        self.max_tries = max_tries
        self.speed_limit_kib = speed_limit_kib
        self.log_file = log_file
        self.port = 0
        self._secret = ""
        self._proc: subprocess.Popen | None = None
        self._ids = itertools.count(1)
        self._lock = threading.Lock()

    # ---------- surec ----------
    def start_service(self, timeout: float = 10.0) -> None:
        if not self.exe.is_file():
            raise FileNotFoundError(f"aria2c bulunamadi: {self.exe}")
        self.port = _free_port()
        self._secret = secrets.token_hex(16)
        args = [
            str(self.exe),
            "--enable-rpc=true",
            "--rpc-listen-all=false",
            f"--rpc-listen-port={self.port}",
            f"--rpc-secret={self._secret}",
            f"--stop-with-process={os.getpid()}",
            f"--max-concurrent-downloads={self.max_concurrent}",
            f"--split={self.connections}",
            f"--max-connection-per-server={self.connections}",
            "--min-split-size=1M",
            "--piece-length=1M",
            "--continue=true",
            # sunucu devam etmeyi (Range) desteklemiyorsa hata verip durma, bastan indir
            "--always-resume=false",
            "--auto-file-renaming=true",
            "--allow-overwrite=false",
            "--content-disposition-default-utf8=true",
            # falloc yonetici yetkisi ister; yoksa sifir doldurmaya dusup aria2'yi bloke ediyor (04.11 olculdu)
            "--file-allocation=none",
            "--disk-cache=64M",
            f"--max-tries={self.max_tries}",
            "--retry-wait=3",
            "--connect-timeout=30",
            "--timeout=60",
            "--max-download-result=10000",
            "--console-log-level=warn",
            "--summary-interval=0",
            "--quiet=true",
        ]
        if self.speed_limit_kib:
            args.append(f"--max-overall-download-limit={self.speed_limit_kib}K")
        # BitTorrent (yerel torrent): port, yukleme siniri, DHT tablosu kalici (magnet metadata'si hizli bulunsun)
        if self.bt_port:
            args += [f"--listen-port={self.bt_port}", f"--dht-listen-port={self.bt_port}"]
        if self.upload_limit_kib:
            args.append(f"--max-overall-upload-limit={self.upload_limit_kib}K")
        if self.dht_file:
            # dht.dat ilk calistirmada bos: giris noktasi olmadan magnet metadata'si bulunamiyor (04.11 olculdu)
            args += [f"--dht-file-path={self.dht_file}", "--enable-dht=true", "--bt-enable-lpd=true",
                     "--enable-peer-exchange=true", "--dht-entry-point=router.bittorrent.com:6881",
                     # cevapsiz izleyicide 60 sn beklemesin (meta veri daha cabuk)
                     "--bt-tracker-connect-timeout=10", "--bt-tracker-timeout=15", "--bt-max-peers=80"]
        # addTorrent ile verilen .torrent'i indirme klasorune <sha1>.torrent olarak kopyalamasin (biz data/'da tutuyoruz)
        args.append("--rpc-save-upload-metadata=false")
        if self.disable_ipv6:
            args.append("--disable-ipv6=true")
        if self.log_file:
            args += [f"--log={self.log_file}", "--log-level=warn"]
        self._proc = subprocess.Popen(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=CREATE_NO_WINDOW if os.name == "nt" else 0,
        )
        deadline = time.monotonic() + timeout
        last_err: Exception | None = None
        while time.monotonic() < deadline:
            if self._proc.poll() is not None:
                raise Aria2Error(f"aria2c hemen kapandi (cikis kodu {self._proc.returncode})")
            try:
                ver = self.call("aria2.getVersion")
                log.info("aria2 %s hazir, port %s", ver.get("version"), self.port)
                return
            except (OSError, Aria2Error) as exc:
                last_err = exc
                time.sleep(0.1)
        raise Aria2Error(f"aria2c RPC yanit vermedi: {last_err}")

    def shutdown(self) -> None:
        if self._proc and self._proc.poll() is None:
            try:
                self.call("aria2.forceShutdown", timeout=3)
                self._proc.wait(timeout=5)
            except Exception:
                self._proc.kill()
        self._proc = None

    @property
    def running(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    # ---------- RPC ----------
    def call(self, method: str, *params: Any, timeout: float = 10.0) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": str(next(self._ids)),
            "method": method,
            "params": [f"token:{self._secret}", *params],
        }
        return self._post(payload, timeout)

    def multicall(self, calls: list[tuple[str, list[Any]]], timeout: float = 10.0) -> list[Any]:
        """system.multicall; her eleman icin sonuc ya da {'error': ...} doner."""
        if not calls:
            return []
        token = f"token:{self._secret}"
        payload = {
            "jsonrpc": "2.0",
            "id": str(next(self._ids)),
            "method": "system.multicall",
            "params": [[{"methodName": m, "params": [token, *p]} for m, p in calls]],
        }
        results = self._post(payload, timeout)
        out = []
        for r in results:
            if isinstance(r, list) and r:
                out.append(r[0])
            else:
                out.append({"error": r})
        return out

    def _post(self, payload: dict, timeout: float) -> Any:
        data = json.dumps(payload).encode()
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/jsonrpc", data=data,
            headers={"Content-Type": "application/json"}, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout) as resp:
                body = json.loads(resp.read())
        except urllib.error.HTTPError as exc:
            # aria2 hata durumunda da JSON govde dondurur (400)
            try:
                body = json.loads(exc.read())
            except Exception:
                raise Aria2Error(f"HTTP {exc.code}") from exc
        if "error" in body:
            err = body["error"]
            raise Aria2Error(err.get("message", "aria2 hatasi"), err.get("code"))
        return body.get("result")

    # ---------- Engine sozlesmesi ----------
    def can_handle(self, request: DownloadRequest) -> bool:
        return request.url.lower().startswith(("http://", "https://", "ftp://", "sftp://"))

    def build_options(self, download: Download) -> dict[str, Any]:
        conn = self.connections
        if download.max_conn:
            conn = max(1, min(conn, download.max_conn))
        opts: dict[str, Any] = {
            "dir": download.directory,
            "split": str(conn),
            "max-connection-per-server": str(conn),
            "continue": "true",
            "remote-time": "true",   # dosya tarihi sunucudaki Last-Modified olsun
        }
        if download.filename:
            opts["out"] = download.filename
        if download.referer:
            opts["referer"] = download.referer
        headers = []
        for k, v in (download.headers or {}).items():
            if not k or v is None or "\n" in k or "\n" in str(v) or "\r" in str(v):
                continue
            if k.lower() == "user-agent":
                opts["user-agent"] = str(v)
            elif k.lower() == "referer":
                opts.setdefault("referer", str(v))
            else:
                headers.append(f"{k}: {v}")
        if headers:
            opts["header"] = headers
        return opts

    def build_torrent_options(self, download: Download) -> dict[str, Any]:
        o = download.options or {}
        opts: dict[str, Any] = {"dir": download.directory, "continue": "true", "follow-torrent": "false"}
        if o.get("select"):
            opts["select-file"] = str(o["select"])
            # parca sinirindaki komsu (secilmeyen) dosyalar kismen yaziliyor; bitince silinsin
            opts["bt-remove-unselected-file"] = "true"
        # paylasim: kapali -> indirme biter bitmez durur; acik -> oran 1.0'a kadar (aria2 varsayilani)
        if o.get("extra_trackers"):
            from app.core.torrent import trackers
            opts["bt-tracker"] = trackers()
        if o.get("stop_seeding", True):
            opts["seed-time"] = "0"
        else:
            opts["seed-ratio"] = "1.0"
        return opts

    def start(self, download: Download) -> str:
        with self._lock:
            if download.kind == "torrent":
                import base64
                data = Path(download.options["torrent_file"]).read_bytes()
                return self.call("aria2.addTorrent", base64.b64encode(data).decode("ascii"), [],
                                 self.build_torrent_options(download))
            return self.call("aria2.addUri", [download.url], self.build_options(download))

    def pause(self, gid: str) -> None:
        try:
            self.call("aria2.pause", gid)
        except Aria2Error as exc:
            log.debug("pause %s: %s", gid, exc)

    def resume(self, gid: str) -> None:
        self.call("aria2.unpause", gid)

    def remove(self, gid: str) -> None:
        for method in ("aria2.forceRemove", "aria2.removeDownloadResult"):
            try:
                self.call(method, gid)
            except Aria2Error:
                pass
        # forceRemove sonrasi sonuc kaydi hemen olusmayabilir; bir kez daha dene
        try:
            self.call("aria2.removeDownloadResult", gid)
        except Aria2Error:
            pass

    _KEYS = ["gid", "status", "totalLength", "completedLength", "downloadSpeed",
             "connections", "errorCode", "errorMessage", "files", "dir", "seeder", "uploadSpeed"]

    def status(self, gids: list[str]) -> dict[str, dict[str, Any]]:
        results = self.multicall([("aria2.tellStatus", [g, self._KEYS]) for g in gids])
        out: dict[str, dict[str, Any]] = {}
        for gid, r in zip(gids, results):
            if not isinstance(r, dict) or "error" in r and "status" not in r:
                out[gid] = {"status": "missing"}
                continue
            files = r.get("files") or []
            path = files[0].get("path", "") if files else ""
            out[gid] = {
                "status": r.get("status", ""),
                "total": int(r.get("totalLength", 0) or 0),
                "completed": int(r.get("completedLength", 0) or 0),
                "speed": int(r.get("downloadSpeed", 0) or 0),
                "connections": int(r.get("connections", 0) or 0),
                "error_code": r.get("errorCode", "0"),
                "error": r.get("errorMessage", ""),
                "path": path,
                "seeder": r.get("seeder") == "true",
                "upload_speed": int(r.get("uploadSpeed", 0) or 0),
            }
        return out

    def set_global(self, **options: Any) -> None:
        opts = {k.replace("_", "-"): str(v) for k, v in options.items()}
        self.call("aria2.changeGlobalOption", opts)
