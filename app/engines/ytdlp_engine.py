"""yt-dlp medya motoru (kutuphane olarak).

- Bilgi alma (probe): baslik, sure, kaliteler, liste girdileri.
- Indirme: her medya isi kendi thread'inde; HTTP parcalari (YouTube DASH video/ses, duz MP4)
  Kami'nin aria2 servisine RPC ile verilir (16 baglanti, ilerleme + duraklat/devam).
  HLS/DASH parcalari yt-dlp'nin kendi coklu parca indiricisiyle (-N 8). Birlestirme/gomme ffmpeg.
- Duraklat = isi iptal et (aria2 .aria2 + .part dosyalari kalir); devam = ayni isi bastan calistir,
  aria2 kaldigi yerden surdurur, biten parcalar atlanir.
"""
from __future__ import annotations

import contextlib
import logging
import os
import re
import shutil
import subprocess
import tempfile
import sys
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable
from urllib.parse import parse_qs, urlparse

log = logging.getLogger(__name__)

AUDIO_KBPS = (320, 256, 192, 128)
SPONSORBLOCK_REMOVE = "sponsor,selfpromo,interaction"
_YT_HOSTS = ("youtube.com", "youtu.be", "youtube-nocookie.com")
_update_done = threading.Event()
_update_done.set()  # guncelleme baslatilmadiysa beklenmez
BOT_ERROR = "yt_bot"   # arayuz bu kodu "YouTube bot dogrulamasi" mesajina cevirir
COOKIES = None         # app.core.vault.CookieStore (main.py baglar): eklentiden gelen YouTube/Google cerezleri


class MediaCancelled(Exception):
    """Kullanici duraklatti / sildi."""


class MediaError(Exception):
    pass


# ---------------------------------------------------------------- yardimcilar
def _ytdlp():
    _update_done.wait(timeout=60)
    import yt_dlp  # noqa: WPS433 (gec yukleme: acilis hizli kalsin, guncelleme once bitsin)
    _register_downloader()
    return yt_dlp


def is_youtube(url: str) -> bool:
    host = (urlparse(url).hostname or "").lower()
    return any(host == h or host.endswith("." + h) for h in _YT_HOSTS)


def is_supported(url: str) -> bool:
    """Ag kullanmadan: yt-dlp'nin ozel (generic olmayan) bir cikaricisi bu linki taniyor mu?"""
    if not url.lower().startswith(("http://", "https://")):
        return False
    yt_dlp = _ytdlp()
    for ie in yt_dlp.extractor.gen_extractor_classes():
        name = ie.ie_key()
        if name == "Generic":
            continue
        try:
            if ie.suitable(url) and ie.working():
                return True
        except Exception:
            continue
    return False


def parse_time(text: str) -> float | None:
    """'1:02:03', '2:30', '95' -> saniye. Bos -> None."""
    text = (text or "").strip()
    if not text:
        return None
    if not re.fullmatch(r"\d+(?::\d{1,2}){0,2}(?:\.\d+)?", text):
        raise ValueError(f"gecersiz zaman: {text}")
    total = 0.0
    for part in text.split(":"):
        total = total * 60 + float(part)
    return total


def build_args(opts: dict[str, Any], directory: str) -> list[str]:
    """Kami medya secenekleri -> yt-dlp komut satiri argumanlari (parse_options ile ydl_opts'a cevrilir).

    opts: format (mp4|mp3), quality (best|2160|1440|1080|720|480|360), audio_kbps, subs, embed,
          sponsorblock (mark|remove|off), start, end, no_playlist, headers
    """
    fmt = opts.get("format", "mp4")
    out = "%(title).150B.%(ext)s"
    if opts.get("out_title"):  # eklentinin yakaladigi akis (index.m3u8 vb.): sekme basligi dosya adi olsun
        name = "".join(" " if (c in '/:*?"<>|' or c == chr(92) or ord(c) < 32) else c
                       for c in str(opts["out_title"])).strip(" .")[:150]
        if name:
            out = name.replace("%", "%%") + ".%(ext)s"
    args = ["-P", directory, "-o", out, "--no-mtime",
            "--concurrent-fragments", "8", "--downloader", "http:kamiaria2",
            "--retries", "5", "--fragment-retries", "10"]
    if opts.get("no_playlist", True):
        args.append("--no-playlist")
    if fmt == "mp3":
        kbps = int(opts.get("audio_kbps") or 320)
        if kbps not in AUDIO_KBPS:
            kbps = 320
        args += ["-f", "ba/b", "-x", "--audio-format", "mp3", "--audio-quality", f"{kbps}K"]
    else:
        q = str(opts.get("quality") or "best")
        if q.isdigit():
            args += ["-f", f"bv*[height<={q}]+ba/b[height<={q}]/bv*+ba/b", "-S", f"res:{q},ext:mp4:m4a"]
        else:
            args += ["-f", "bv*+ba/b", "-S", "ext:mp4:m4a"]
        args += ["--merge-output-format", "mp4", "--remux-video", "mp4"]
        if opts.get("subs", True):
            # Sadece insan yapimi EN/TR (otomatik altyazi/ceviri YOK - defter 12), yumusak iz olarak gomulu
            args += ["--sub-langs", "en,en-.*,tr,tr-.*,-live_chat", "--embed-subs"]  # --write-subs yok: gomulunce yan dosya silinir
    if opts.get("embed", True):
        args += ["--embed-thumbnail", "--convert-thumbnails", "jpg", "--embed-metadata", "--embed-chapters"]
    sb = opts.get("sponsorblock", "mark")
    if sb in ("mark", "remove"):
        args += ["--sponsorblock-mark", "all"]
        if sb == "remove":
            args += ["--sponsorblock-remove", SPONSORBLOCK_REMOVE]
    start, end = parse_time(opts.get("start", "")), parse_time(opts.get("end", ""))
    if start is not None or end is not None:
        a = _fmt_secs(start or 0)
        b = _fmt_secs(end) if end is not None else "inf"
        args += ["--download-sections", f"*{a}-{b}"]
    for k, v in (opts.get("headers") or {}).items():
        if k.lower() == "cookie":   # cerez -> cookiefile (MediaJob.run), basliga yazilmaz
            continue
        if k and v and "\n" not in f"{k}{v}" and "\r" not in f"{k}{v}":
            args += ["--add-headers", f"{k}:{v}"]
    return args


def _fmt_secs(s: float) -> str:
    s = float(s)
    return f"{int(s // 3600)}:{int(s % 3600 // 60):02d}:{s % 60:06.3f}"


def _clean_headers(url: str, headers: dict[str, str] | None) -> dict[str, str]:
    """Eklentiden gelen basliklar. YouTube'a tarayici cerezi gonderilmez (format kisitlamasi yaratabiliyor)."""
    if not headers or is_youtube(url):
        return {}
    keep = {}
    for k, v in headers.items():
        if k.lower() in ("cookie", "user-agent", "referer") and v:   # Cookie saklanir, yt-dlp'ye cookiefile olur
            keep[k] = v
    return keep


# ---------------------------------------------------------------- aria2 indirici
_registered = False


def _register_downloader() -> None:
    global _registered
    if _registered:
        return
    from yt_dlp.downloader import external

    class KamiAria2FD(external.ExternalFD):
        SUPPORTED_PROTOCOLS = ("http", "https")

        @classmethod
        def get_basename(cls):
            return "kamiaria2"

        @classmethod
        def available(cls, path=None):
            return True

        def _call_downloader(self, tmpfilename, info_dict):
            job: MediaJob | None = self.params.get("kami_job")
            if job is None:
                raise MediaError("kami_job yok")
            return job.aria2_download(self, tmpfilename, info_dict)

    external._BY_NAME["kamiaria2"] = KamiAria2FD
    _registered = True


# ---------------------------------------------------------------- is
@dataclass
class MediaJob:
    download_id: int
    url: str
    directory: str
    options: dict[str, Any]
    engine: Any                                  # Aria2Engine (call/remove/build)
    connections: int = 16
    on_progress: Callable[..., None] = lambda **kw: None
    cancel: threading.Event = field(default_factory=threading.Event)
    final_path: str = ""
    error: str = ""
    _done_bytes: int = 0
    _est_total: int = 0
    _aria_error: str = ""

    # ---- yt-dlp kancalari ----
    def _hook(self, d: dict[str, Any]) -> None:
        if self.cancel.is_set():
            raise MediaCancelled()
        st = d.get("status")
        if st == "downloading":
            cur = int(d.get("downloaded_bytes") or 0)
            tot = int(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
            downloaded = self._done_bytes + cur
            size = max(self._est_total, self._done_bytes + tot, downloaded)
            self.on_progress(phase="downloading", downloaded=downloaded, size=size,
                             speed=int(d.get("speed") or 0))
        elif st == "finished":
            self._done_bytes += int(d.get("total_bytes") or d.get("downloaded_bytes") or 0)
            self.on_progress(phase="downloading", downloaded=self._done_bytes,
                             size=max(self._est_total, self._done_bytes), speed=0)

    def _pp_hook(self, d: dict[str, Any]) -> None:
        if self.cancel.is_set():
            raise MediaCancelled()
        if d.get("status") == "started":
            self.on_progress(phase="processing", speed=0)

    def _post_hook(self, filepath: str) -> None:
        self.final_path = filepath

    # ---- aria2 ile HTTP parcasi ----
    def aria2_download(self, fd, tmpfilename: str, info_dict: dict[str, Any]) -> int:
        url = info_dict["url"]
        dn, out = os.path.split(os.path.abspath(tmpfilename))
        opts: dict[str, Any] = {
            "dir": dn, "out": out, "continue": "true", "allow-overwrite": "true",
            "auto-file-renaming": "false",
            "split": str(self.connections), "max-connection-per-server": str(self.connections),
        }
        headers = dict(info_dict.get("http_headers") or {})
        try:
            cookie = fd.ydl.cookiejar.get_cookie_header(url)
            if cookie:
                headers["Cookie"] = cookie
        except Exception:
            pass
        hdr = []
        for k, v in headers.items():
            if "\n" in f"{k}{v}" or "\r" in f"{k}{v}":
                continue
            if k.lower() == "user-agent":
                opts["user-agent"] = v
            elif k.lower() == "referer":
                opts["referer"] = v
            else:
                hdr.append(f"{k}: {v}")
        if hdr:
            opts["header"] = hdr
        gid = self.engine.call("aria2.addUri", [url], opts)
        keys = ["status", "totalLength", "completedLength", "downloadSpeed", "errorCode", "errorMessage"]
        try:
            while True:
                if self.cancel.is_set():
                    raise MediaCancelled()
                s = self.engine.call("aria2.tellStatus", gid, keys)
                st = s.get("status")
                total = int(s.get("totalLength") or 0)
                done = int(s.get("completedLength") or 0)
                if st == "complete":
                    return 0
                if st in ("error", "removed"):
                    self._aria_error = f"aria2 {s.get('errorCode')}: {s.get('errorMessage') or ''}".strip()
                    return 1
                fd._hook_progress({
                    "status": "downloading", "downloaded_bytes": done, "total_bytes": total or None,
                    "speed": int(s.get("downloadSpeed") or 0), "tmpfilename": tmpfilename,
                    "filename": tmpfilename[:-5] if tmpfilename.endswith(".part") else tmpfilename,
                }, info_dict)
                time.sleep(0.3)
        finally:
            try:
                self.engine.remove(gid)  # dosya + .aria2 kalir (devam icin)
            except Exception:
                pass

    # ---- calistir ----
    def run(self) -> str:
        """Indirir; son dosya yolunu dondurur. MediaCancelled / MediaError firlatir."""
        yt_dlp = _ytdlp()
        args = build_args(self.options, self.directory)
        ydl_opts = yt_dlp.parse_options(args).ydl_opts
        ydl_opts.update({
            "quiet": True, "no_warnings": False, "noprogress": True, "logger": _YdlLogger(),
            "progress_hooks": [self._hook], "postprocessor_hooks": [self._pp_hook],
            "kami_job": self, "continuedl": True, "ignoreerrors": False,
        })
        ffmpeg = find_ffmpeg()
        if ffmpeg:
            ydl_opts["ffmpeg_location"] = ffmpeg
        try:
            with _cookiefile(self.url, _cookie_of(self.options.get("headers"))) as ck, yt_dlp.YoutubeDL(
                    {**ydl_opts, "cookiefile": ck} if ck else ydl_opts) as ydl:
                ydl.add_post_hook(self._post_hook)
                info = ydl.extract_info(self.url, download=False)
                if self.cancel.is_set():
                    raise MediaCancelled()
                self._est_total = _estimate_size(info)
                self.on_progress(phase="downloading", title=info.get("title") or "",
                                 size=self._est_total, base=_base_name(ydl, info), meta=music_meta(info))
                ydl.process_ie_result(info, download=True)
        except MediaCancelled:
            raise
        except Exception as exc:
            if self.cancel.is_set():
                raise MediaCancelled() from exc
            msg = self._aria_error or _clean_error(str(exc))
            raise MediaError(msg) from exc
        return self.final_path


def music_meta(info: dict[str, Any]) -> dict[str, Any]:
    """Muzik arsivcisi icin yt-dlp alanlari (YouTube Music'te artist/track/album dolu gelir)."""
    def first(*keys):
        for k in keys:
            v = info.get(k)
            if isinstance(v, list):
                v = ", ".join(str(x) for x in v if x)
            if v:
                return str(v)
        return ""
    year = first("release_year") or (first("release_date", "upload_date")[:4])
    return {"artist": first("artists", "artist", "creators", "creator"), "track": first("track"),
            "album": first("album"), "year": year, "title": first("title"),
            "channel": first("channel", "uploader"), "thumbnail": first("thumbnail"),
            "duration": float(info.get("duration") or 0)}


def _base_name(ydl, info: dict[str, Any]) -> str:
    try:
        return os.path.splitext(os.path.basename(ydl.prepare_filename(info)))[0]
    except Exception:
        return ""


def _estimate_size(info: dict[str, Any]) -> int:
    fmts = info.get("requested_formats") or [info]
    total = 0
    for f in fmts:
        total += int(f.get("filesize") or f.get("filesize_approx") or 0)
    return total


def _clean_error(msg: str) -> str:
    msg = re.sub(r"\x1b\[[0-9;]*m", "", msg)
    if re.search(r"confirm you.{0,3}re not a bot|Sign in to confirm", msg, re.I):
        return BOT_ERROR
    return msg.replace("ERROR: ", "").strip()[:400]


def _cookie_of(headers: dict[str, str] | None) -> str:
    return next((str(v) for k, v in (headers or {}).items() if k.lower() == "cookie" and v), "")


@contextlib.contextmanager
def _header_cookiefile(url: str, cookie: str):
    """Eklentiden gelen 'Cookie: a=b; c=d' -> linkin alan adina gecici cookies.txt
    (yt-dlp, cerezi baslikla vermeye 'potential security risk' uyarisi veriyor)."""
    from app.core.vault import to_netscape
    host = (urlparse(url).hostname or "").lower()
    cookies = []
    for part in cookie.split(";"):
        name, sep, value = part.strip().partition("=")
        if sep and name:
            cookies.append({"name": name, "value": value, "domain": host, "path": "/",
                            "secure": url.lower().startswith("https"), "hostOnly": False, "session": True})
    if not host or not cookies:
        yield None
        return
    fd, name = tempfile.mkstemp(prefix="kami_hc_", suffix=".txt")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
            f.write(to_netscape(cookies))
        yield name
    finally:
        with contextlib.suppress(OSError):
            os.remove(name)


SOCIAL_COOKIES = lambda: True   # main: ayar "social_cookies"

def _cookiefile(url: str, cookie_header: str = ""):
    """YouTube: DPAPI deposundan cookies.txt. Diger siteler: eklentinin Cookie basligindan. Yoksa None."""
    if COOKIES is not None and is_youtube(url):
        return COOKIES.cookiefile(url)
    from app.core.vault import group_of
    if COOKIES is not None and group_of(url) and SOCIAL_COOKIES() and COOKIES.groups().count(group_of(url)):
        # Instagram/X/TikTok: eklentinin ilettigi oturum (hikaye/ozel hesap); yoksa sayfa basligindaki cerez
        return COOKIES.cookiefile(url)
    if cookie_header and not is_youtube(url):
        return _header_cookiefile(url, cookie_header)
    return contextlib.nullcontext(None)


class _YdlLogger:
    def debug(self, msg: str) -> None:
        if msg.startswith("[debug]"):
            return

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        log.info("yt-dlp: %s", msg)

    def error(self, msg: str) -> None:
        log.warning("yt-dlp: %s", msg)


# ---------------------------------------------------------------- bilgi alma
def probe(url: str, headers: dict[str, str] | None = None, timeout: float = 30.0) -> dict[str, Any]:
    """Linki yt-dlp ile cozer (indirmeden). Listeler duz (flat) gelir.

    Donus: {kind: video|playlist, title, duration, thumbnail, heights, url, single_url, entries:[...]}
    Desteklenmiyorsa MediaError.
    """
    yt_dlp = _ytdlp()
    opts: dict[str, Any] = {
        "quiet": True, "no_warnings": True, "logger": _YdlLogger(), "skip_download": True,
        "extract_flat": "in_playlist", "socket_timeout": timeout, "noplaylist": False,
        "playlistend": 500,
    }
    h = _clean_headers(url, headers)
    cookie = _cookie_of(h)
    h = {k: v for k, v in h.items() if k.lower() != "cookie"}
    if h:
        opts["http_headers"] = h
    try:
        with _cookiefile(url, cookie) as ck, \
                yt_dlp.YoutubeDL({**opts, "cookiefile": ck} if ck else opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:
        raise MediaError(_clean_error(str(exc))) from exc
    if not info:
        raise MediaError("bilgi alinamadi")
    if info.get("_type") == "playlist" or info.get("entries") is not None:
        entries = []
        for e in info.get("entries") or []:
            if not e:
                continue
            eurl = e.get("url") or e.get("webpage_url") or ""
            if eurl and not eurl.startswith("http") and e.get("ie_key") == "Youtube":
                eurl = f"https://www.youtube.com/watch?v={eurl}"
            if not eurl:
                continue
            entries.append({"url": eurl, "title": e.get("title") or eurl,
                            "duration": e.get("duration") or 0})
        single = ""
        q = parse_qs(urlparse(url).query)
        if is_youtube(url) and q.get("v"):
            single = f"https://www.youtube.com/watch?v={q['v'][0]}"
        return {"kind": "playlist", "title": info.get("title") or url, "url": url,
                "single_url": single, "entries": entries, "heights": [], "duration": 0,
                "thumbnail": ""}
    heights = sorted({int(f["height"]) for f in info.get("formats") or []
                      if f.get("height") and f.get("vcodec") not in (None, "none")}, reverse=True)
    return {"kind": "video", "title": info.get("title") or url, "url": info.get("webpage_url") or url,
            "categories": list(info.get("categories") or []),
            "single_url": "", "entries": [], "heights": heights,
            "duration": info.get("duration") or 0, "thumbnail": info.get("thumbnail") or "",
            "is_live": bool(info.get("is_live"))}


# ---------------------------------------------------------------- calistirici
class MediaRunner:
    """Medya islerini sinirli eszamanlilikla calistirir; durumlari callback ile yoneticiye bildirir."""

    def __init__(self, engine: Any, *, max_concurrent: int = 3,
                 on_event: Callable[..., None] = lambda *a, **kw: None,
                 connections_getter: Callable[[], int] = lambda: 16) -> None:
        self.engine = engine
        self.on_event = on_event          # on_event(download_id, kind, **fields) kind: started|progress|done|error|cancelled
        self._connections = connections_getter
        self._sem = threading.Semaphore(max(1, max_concurrent))
        self._jobs: dict[int, MediaJob] = {}
        self._lock = threading.Lock()

    def start(self, download_id: int, url: str, directory: str, options: dict[str, Any]) -> None:
        with self._lock:
            old = self._jobs.get(download_id)
            if old and not old.cancel.is_set():
                return  # zaten calisiyor
            job = MediaJob(download_id, url, directory, dict(options), self.engine,
                           connections=self._connections(),
                           on_progress=lambda **kw: self.on_event(download_id, "progress", **kw))
            self._jobs[download_id] = job
        threading.Thread(target=self._run, args=(job,), name=f"kami-media-{download_id}", daemon=True).start()

    def cancel(self, download_id: int) -> None:
        with self._lock:
            job = self._jobs.get(download_id)
        if job:
            job.cancel.set()

    def is_running(self, download_id: int) -> bool:
        with self._lock:
            job = self._jobs.get(download_id)
        return bool(job and not job.cancel.is_set())

    def _run(self, job: MediaJob) -> None:
        with self._sem:
            try:
                if job.cancel.is_set():
                    raise MediaCancelled()
                self.on_event(job.download_id, "started")
                path = job.run()
                self.on_event(job.download_id, "done", path=path)
            except MediaCancelled:
                self.on_event(job.download_id, "cancelled")
            except MediaError as exc:
                self.on_event(job.download_id, "error", error=str(exc))
            except Exception as exc:  # beklenmeyen
                log.exception("Medya isi coktu")
                self.on_event(job.download_id, "error", error=str(exc))
            finally:
                with self._lock:
                    if self._jobs.get(job.download_id) is job:
                        del self._jobs[job.download_id]


# ---------------------------------------------------------------- ffmpeg + guncelleme
def find_ffmpeg() -> str:
    from app import paths
    local = paths.ROOT / "bin" / "ffmpeg.exe"
    if local.is_file():
        return str(local)
    return shutil.which("ffmpeg") or ""


def start_self_update(min_interval_h: float, settings) -> None:
    """Acilista yt-dlp'yi arka planda gunceller (gunde en fazla bir kez). yt-dlp bitene kadar yuklenmez."""
    last = float(settings.get("ytdlp_last_update") or 0)
    if time.time() - last < min_interval_h * 3600:
        return
    uv = shutil.which("uv")
    if not uv:
        log.info("uv bulunamadi, yt-dlp guncellemesi atlandi")
        return
    _update_done.clear()

    def work() -> None:
        try:
            r = subprocess.run(
                [uv, "pip", "install", "--python", sys.executable, "-U", "yt-dlp[default,curl-cffi]"],
                capture_output=True, text=True, timeout=90,
                creationflags=0x08000000 if os.name == "nt" else 0)
            out = (r.stdout + r.stderr).strip().splitlines()
            log.info("yt-dlp guncelleme (kod %s): %s", r.returncode, out[-1] if out else "")
            if r.returncode == 0:
                settings.set("ytdlp_last_update", time.time())
        except Exception:
            log.exception("yt-dlp guncellenemedi")
        finally:
            _update_done.set()

    threading.Thread(target=work, name="kami-ytdlp-update", daemon=True).start()
