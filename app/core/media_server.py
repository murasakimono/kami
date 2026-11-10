"""Yerel medya sunucusu (Oynatici, P1).

Arayuz file:// ile acilir; video/ses burada HTTP ile verilir cunku:
  - Web Audio AnalyserNode (goz ekolayziri) ancak CORS izinli medyada sesi okuyabilir,
  - tarayicinin oynatamadigi kapsayici/codec (mkv+AC3, HEVC, avi...) ffmpeg ile akista donusturulur.

Guvenlik: sadece 127.0.0.1, adreste oturuma ozel rastgele anahtar, yalnizca register() ile acilan dosyalar.

Yollar (hepsi /<token>/ altinda):
  GET /f/<key>          dosyanin kendisi (Range destekli)          -> "direct"
  GET /x/<key>?t=&a=    ffmpeg akisi, parcali MP4 (t: baslangic sn, a: ses izi sirasi)
                        mod "remux": goruntu kopyalanir, ses AAC; mod "transcode": H.264 (NVENC varsa) + AAC
  GET /s/<key>          altyazi (SRT/VTT -> WebVTT)
  GET /c/<key>          gomulu kapak resmi (muzik)
  GET /p/<key>?t=       ilerleme cubugu onizleme karesi (JPEG, 5 sn'lik dilimlere yuvarlanir, bellekte onbellek)
  GET /k/<key>?t=       t'den onceki en yakin anahtar kare zamani (remux'ta kopya akis anahtar kareden baslar)
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
import re
import secrets
import shutil
import subprocess
import threading
import urllib.parse
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

NO_WINDOW = 0x08000000 if os.name == "nt" else 0
VIDEO_EXT = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".avi", ".ts", ".m2ts", ".wmv", ".flv", ".mpg", ".mpeg", ".3gp", ".ogv"}
AUDIO_EXT = {".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac", ".wma", ".ape", ".alac", ".aiff", ".aif", ".mka", ".wv"}
SUB_EXT = (".srt", ".vtt")
# WebView2 (Chromium) dogrudan oynatabildikleri
OK_CONTAINER = {".mp4", ".m4v", ".mov", ".webm", ".mkv", ".mp3", ".flac", ".wav", ".ogg", ".oga", ".opus", ".m4a", ".aac"}
OK_VCODEC = {"h264", "vp8", "vp9", "av1"}
OK_ACODEC = {"aac", "mp3", "opus", "vorbis", "flac", "pcm_s16le", "pcm_s24le", "pcm_f32le", "pcm_u8"}
CHUNK = 256 * 1024
IMAGE_SUBS = {"hdmv_pgs_subtitle", "dvd_subtitle", "dvb_subtitle", "xsub"}   # resim altyazi: metne cevrilemez
ASS_SUBS = {"ass", "ssa"}


def find_ffprobe(ffmpeg: str) -> str:
    if ffmpeg:
        p = Path(ffmpeg).with_name("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if p.is_file():
            return str(p)
    return shutil.which("ffprobe") or ""


def probe(ffprobe: str, path: str) -> dict[str, Any]:
    """ffprobe ozeti: sure, goruntu codec'i, ses izleri, gomulu altyazilar, kapak."""
    out: dict[str, Any] = {"duration": 0.0, "vcodec": "", "width": 0, "height": 0, "audio": [], "subs": [], "cover": False,
                           "fonts": [], "tags": {}}
    if not ffprobe:
        return out
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams", "-show_chapters", "-of", "json", path],
                           capture_output=True, timeout=20, creationflags=NO_WINDOW)
        data = json.loads(r.stdout or b"{}")
    except Exception:
        log.exception("ffprobe basarisiz: %s", path)
        return out
    try:
        out["duration"] = float((data.get("format") or {}).get("duration") or 0)
    except ValueError:
        pass
    tg: dict[str, str] = {}   # muzik etiketleri: format + ses izi (ogg/opus sozleri izde tutar)
    for src in [(data.get("format") or {}).get("tags") or {}] + [st.get("tags") or {} for st in data.get("streams") or [] if st.get("codec_type") == "audio"][:1]:
        for k, v in src.items():
            k = str(k).lower().split("-")[0]
            if k in ("title", "artist", "album", "album_artist", "track", "date", "genre", "lyrics", "unsyncedlyrics", "syncedlyrics") and v and k not in tg:
                tg[k] = str(v)
    out["tags"] = tg
    chs = []
    for c in data.get("chapters") or []:   # mkv/mp4 bolumleri (seekbar isaretleri)
        try:
            chs.append({"start": float(c.get("start_time") or 0), "end": float(c.get("end_time") or 0),
                        "title": str((c.get("tags") or {}).get("title") or "")})
        except (TypeError, ValueError):
            pass
    out["chapters"] = chs[:200]
    for st in data.get("streams") or []:
        kind, codec = st.get("codec_type"), (st.get("codec_name") or "").lower()
        tags = st.get("tags") or {}
        disp = st.get("disposition") or {}
        if kind == "video":
            if disp.get("attached_pic"):
                out["cover"] = True
            elif not out["vcodec"]:
                out.update(vcodec=codec, width=int(st.get("width") or 0), height=int(st.get("height") or 0))
        elif kind == "audio":
            out["audio"].append({"codec": codec, "lang": tags.get("language", ""), "title": tags.get("title", ""),
                                 "channels": int(st.get("channels") or 0), "default": bool(disp.get("default"))})
        elif kind == "subtitle":
            out["subs"].append({"codec": codec, "lang": tags.get("language", ""), "title": tags.get("title", ""),
                                "default": bool(disp.get("default")), "forced": bool(disp.get("forced"))})
        elif kind == "attachment":
            fn = tags.get("filename", "")
            if fn.lower().endswith((".ttf", ".otf", ".ttc", ".woff", ".woff2")):
                out["fonts"].append(fn)
    return out


def choose_mode(ext: str, info: dict[str, Any], audio_index: int = 0) -> str:
    """direct | remux | transcode"""
    v = info.get("vcodec") or ""
    auds = info.get("audio") or []
    a = (auds[audio_index] if audio_index < len(auds) else (auds[0] if auds else {})).get("codec", "")
    v_ok = not v or v in OK_VCODEC
    a_ok = not a or a in OK_ACODEC or a.startswith("pcm_")
    if not v_ok:
        return "transcode"
    if ext in OK_CONTAINER and a_ok and audio_index == 0:
        return "direct"
    return "remux"


def srt_to_vtt(text: str) -> str:
    text = text.lstrip("﻿").replace("\r\n", "\n").replace("\r", "\n")
    if text.startswith("WEBVTT"):
        return text
    text = re.sub(r"(\d{2}:\d{2}:\d{2}),(\d{3})", r"\1.\2", text)
    return "WEBVTT\n\n" + text


def read_text(path: str) -> str:
    raw = Path(path).read_bytes()
    for enc in ("utf-8-sig", "cp1254", "latin-1"):   # Turkce altyazilar cogu zaman cp1254
        try:
            return raw.decode(enc)
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", "replace")


class MediaServer:
    def __init__(self, ffmpeg_getter, vendor_dir: Path | None = None) -> None:
        self._ffmpeg_getter = ffmpeg_getter
        self.vendor_dir = vendor_dir   # JASSUB (ASS cizici) dosyalari: web/vendor/jassub
        self.token = secrets.token_urlsafe(24)
        self._files: dict[str, dict[str, Any]] = {}   # key -> {path, kind, mode, ...}
        self._by_path: dict[str, str] = {}
        self._lock = threading.Lock()
        self._procs: set[subprocess.Popen] = set()
        self._encoder: str | None = None
        self._thumbs: dict[tuple[str, int], bytes] = {}
        import tempfile
        self.cache_dir = Path(tempfile.gettempdir()) / "kami_player"
        self._xlock = threading.Lock()
        self.httpd = None
        self.growing = lambda path: None   # main: watcher.head (inerken izle) -> bastan inmis byte ya da None

    # ---------- yasam dongusu ----------
    def start(self) -> None:
        from app.core.net import ExclusiveHTTPServer
        self.httpd = ExclusiveHTTPServer.make(("127.0.0.1", 0), _make_handler(self))
        self.httpd.daemon_threads = True
        threading.Thread(target=self.httpd.serve_forever, name="kami-media", daemon=True).start()
        log.info("Medya sunucusu 127.0.0.1:%s", self.port)

    def stop(self) -> None:
        for p in list(self._procs):
            _kill(p)
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()

    @property
    def port(self) -> int:
        return self.httpd.server_address[1] if self.httpd else 0

    @property
    def base(self) -> str:
        return f"http://127.0.0.1:{self.port}/{self.token}"

    def ffmpeg(self) -> str:
        return self._ffmpeg_getter() or ""

    # ---------- kodlayici: NVENC > QSV > AMF > libx264 (bir kez denenir) ----------
    def encoder(self) -> list[str]:
        if self._encoder is None:
            self._encoder = "libx264"
            ff = self.ffmpeg()
            for enc in ("h264_nvenc", "h264_qsv", "h264_amf"):
                try:
                    r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-f", "lavfi", "-i", "color=black:s=256x144:d=0.2",
                                        "-c:v", enc, "-f", "null", "-"], capture_output=True, timeout=15, creationflags=NO_WINDOW)
                    if r.returncode == 0:
                        self._encoder = enc
                        break
                except Exception:
                    continue
            log.info("Oynatici donusturucu: %s", self._encoder)
        return {
            "h264_nvenc": ["-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-rc", "vbr", "-cq", "21", "-b:v", "0"],
            "h264_qsv": ["-c:v", "h264_qsv", "-preset", "faster", "-global_quality", "22"],
            "h264_amf": ["-c:v", "h264_amf", "-quality", "speed", "-rc", "cqp", "-qp_i", "21", "-qp_p", "23"],
            "libx264": ["-c:v", "libx264", "-preset", "veryfast", "-crf", "21"],
        }[self._encoder]

    # ---------- dosya acma ----------
    def register(self, path: str, title: str = "", extra_subs: list[str] | None = None) -> dict[str, Any]:
        p = Path(path)
        if not p.is_file():
            return {"ok": False, "error": "not_found"}
        ext = p.suffix.lower()
        if ext not in VIDEO_EXT | AUDIO_EXT:
            return {"ok": False, "error": "not_media"}
        info = probe(find_ffprobe(self.ffmpeg()), str(p))
        kind = "video" if (info["vcodec"] or (ext in VIDEO_EXT and not info["audio"])) else "audio"
        if ext in AUDIO_EXT and not info["vcodec"]:
            kind = "audio"
        mode = choose_mode(ext, info)
        if mode != "direct" and not self.ffmpeg():
            mode = "direct"   # ffmpeg yoksa yine de dene
        key = self._key_for(str(p))
        subs = self._find_subs(p, extra_subs or [])
        subs += [{"path": str(q), "label": q.name[len(p.stem):-len(q.suffix)].strip(". _-") or "ASS"}
                 for q in self._find_ass(p)]
        with self._lock:
            self._files[key] = {"path": str(p), "kind": kind, "mode": mode, "info": info}
            for i, s in enumerate(subs):
                self._files[f"{key}-s{i}"] = {"path": s["path"], "kind": "sub"}
        a_ok = mode == "direct"
        res = {
            "ok": True, "key": key, "path": str(p), "kind": kind, "vcodec": info["vcodec"], "size": p.stat().st_size, "mode": mode, "title": title or p.stem,
            "duration": info["duration"], "width": info["width"], "height": info["height"],
            "tags": {k: v for k, v in info.get("tags", {}).items() if "lyrics" not in k},
            "chapters": info.get("chapters", []),
            "audio": info["audio"], "embedded_subs": info["subs"],
            "url": f"{self.base}/f/{key}" if a_ok else f"{self.base}/x/{key}",
            "direct_url": f"{self.base}/f/{key}",
            "stream_url": f"{self.base}/x/{key}",
            "cover": f"{self.base}/c/{key}" if info["cover"] else "",
            "thumb_url": f"{self.base}/p/{key}" if kind == "video" else "",
            "subs": [{"label": s["label"], "url": f"{self.base}/s/{key}-s{i}", "ass": s["path"].lower().endswith((".ass", ".ssa")),
                      "raw_url": f"{self.base}/r/{key}-s{i}"} for i, s in enumerate(subs)],
            "embedded": [{"index": i, "lang": e["lang"], "title": e["title"], "codec": e["codec"], "default": e["default"],
                          "forced": e["forced"], "image": e["codec"] in IMAGE_SUBS, "ass": e["codec"] in ASS_SUBS,
                          "url": f"{self.base}/e/{key}?i={i}", "raw_url": f"{self.base}/e/{key}?i={i}&raw=1"}
                         for i, e in enumerate(info["subs"])],
            "fonts": [f"{self.base}/a/{key}?n={urllib.parse.quote(n)}" for n in info["fonts"]],
            "jassub": f"{self.base}/j/" if self.vendor_dir else "",
        }
        log.info("Oynatici: %s (%s, %s, %s/%s)", p.name, kind, mode, info["vcodec"] or "-",
                 (info["audio"][0]["codec"] if info["audio"] else "-"))
        return res

    def register_url(self, urls: list[str], title: str, headers: dict[str, str] | None = None,
                     duration: float = 0.0, kind: str = "video") -> dict[str, Any]:
        """Indirmeden izle (yt-dlp akisi / Real-Debrid linki / dogrudan medya URL'si): ffmpeg kopyalayip parcali MP4 verir.
        urls: [tek dosya] ya da [goruntu, ses] (ayri akislar ffmpeg'de birlesir). Ileri sarma -ss ile (HTTP Range)."""
        if not self.ffmpeg():
            return {"ok": False, "error": "no_ffmpeg"}
        hdr = "".join(f"{k}: {v}\r\n" for k, v in (headers or {}).items() if k.lower() not in ("accept-encoding",))
        info = probe(find_ffprobe(self.ffmpeg()), urls[0]) if len(urls) == 1 else {"duration": 0.0, "vcodec": "", "width": 0, "height": 0,
                                                                                   "audio": [{"codec": "aac", "channels": 2, "lang": "", "title": "", "default": True}],
                                                                                   "subs": [], "cover": False, "fonts": []}
        if len(urls) > 1:
            v = probe(find_ffprobe(self.ffmpeg()), urls[0])
            info.update(vcodec=v["vcodec"], width=v["width"], height=v["height"], duration=v["duration"])
        if duration and not info["duration"]:
            info["duration"] = float(duration)
        if not info["vcodec"] and not info["audio"]:
            kind = kind or "video"
        kind = "video" if info["vcodec"] else "audio"
        mode = "transcode" if info["vcodec"] and info["vcodec"] not in OK_VCODEC else "remux"
        key = secrets.token_urlsafe(9)
        with self._lock:
            self._files[key] = {"path": urls[0], "urls": urls, "headers": hdr, "kind": kind, "mode": mode, "info": info, "remote": True}
        log.info("Oynatici (uzak): %s (%s, %s)", title[:80], kind, mode)
        return {"ok": True, "key": key, "path": "", "remote": True, "kind": kind, "mode": mode, "title": title,
                "vcodec": info["vcodec"], "size": 0, "duration": info["duration"], "width": info["width"], "height": info["height"],
                "audio": info["audio"], "embedded": [], "fonts": [], "subs": [], "cover": "", "thumb_url": "",
                "url": f"{self.base}/x/{key}", "direct_url": f"{self.base}/x/{key}", "stream_url": f"{self.base}/x/{key}",
                "jassub": f"{self.base}/j/" if self.vendor_dir else ""}

    def asset_url(self, path: str, route: str = "f") -> str:
        """Kutuphane kapaklari icin hafif kayit: f = dosyanin kendisi (resim), c = gomulu kapak."""
        key = self._key_for(path)
        with self._lock:
            self._files.setdefault(key, {"path": path, "kind": "asset", "mode": "direct", "info": {}})
        return f"{self.base}/{route}/{key}"

    def _key_for(self, path: str) -> str:
        with self._lock:
            if path not in self._by_path:
                self._by_path[path] = secrets.token_urlsafe(9)
            return self._by_path[path]

    @staticmethod
    def _find_subs(p: Path, extra: list[str]) -> list[dict[str, str]]:
        """Yan dosyalar: film.srt, film.tr.srt, film.en.vtt ... + Whisper ciktilari."""
        found: list[dict[str, str]] = []
        seen: set[str] = set()
        cands = [Path(x) for x in extra if x]
        try:
            cands += sorted(q for q in p.parent.iterdir() if q.suffix.lower() in SUB_EXT and q.name.startswith(p.stem))
        except OSError:
            pass
        for q in cands:
            k = str(q).lower()
            if k in seen or not q.is_file():
                continue
            seen.add(k)
            tail = q.name[len(p.stem):-len(q.suffix)].strip(". _-") if q.name.startswith(p.stem) else q.stem
            found.append({"path": str(q), "label": tail or q.suffix[1:].upper()})
        return found

    @staticmethod
    def _find_ass(p: Path) -> list[Path]:
        try:
            return sorted(q for q in p.parent.iterdir() if q.suffix.lower() in (".ass", ".ssa") and q.name.startswith(p.stem))
        except OSError:
            return []

    # ---------- gomulu altyazi / font cikarma (diskte onbellek; buyuk mkv'de ilk acilis birkac saniye) ----------
    def _cache_base(self, e: dict[str, Any]) -> Path:
        import hashlib
        st = os.stat(e["path"])
        h = hashlib.sha1(f'{e["path"]}|{st.st_size}|{st.st_mtime_ns}'.encode()).hexdigest()[:16]
        d = self.cache_dir / h
        d.mkdir(parents=True, exist_ok=True)
        return d

    def extract_sub(self, e: dict[str, Any], index: int, raw: bool) -> bytes:
        codec = (e["info"]["subs"][index]["codec"] if index < len(e["info"]["subs"]) else "")
        if codec in IMAGE_SUBS:
            return b""
        as_ass = raw and codec in ASS_SUBS
        out = self._cache_base(e) / f"s{index}.{'ass' if as_ass else 'vtt'}"
        with self._xlock:
            if not out.is_file():
                cmd = [self.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-i", e["path"], "-map", f"0:s:{index}",
                       "-c:s", "copy" if as_ass else "webvtt", "-f", "ass" if as_ass else "webvtt", str(out) + ".tmp"]
                r = subprocess.run(cmd, capture_output=True, timeout=300, creationflags=NO_WINDOW)
                if r.returncode != 0:
                    log.info("altyazi cikarilamadi: %s", (r.stderr or b"")[-300:].decode("utf-8", "replace"))
                    return b""
                os.replace(str(out) + ".tmp", out)
        return out.read_bytes()

    def font(self, e: dict[str, Any], name: str) -> bytes:
        if name not in e["info"].get("fonts", []) or "/" in name or "\\" in name:
            return b""
        d = self._cache_base(e) / "fonts"
        f = d / name
        with self._xlock:
            if not f.is_file():
                d.mkdir(exist_ok=True)
                subprocess.run([self.ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", "-dump_attachment:t", "", "-i", e["path"]],
                               cwd=str(d), capture_output=True, timeout=120, creationflags=NO_WINDOW)
        return f.read_bytes() if f.is_file() else b""

    def entry(self, key: str) -> dict[str, Any] | None:
        with self._lock:
            return self._files.get(key)

    # ---------- ffmpeg akisi ----------
    def stream_cmd(self, e: dict[str, Any], start: float, audio_index: int, dialog: bool = False) -> list[str]:
        ff = self.ffmpeg()
        cmd = [ff, "-hide_banner", "-loglevel", "error", "-nostdin"]
        inputs = e.get("urls") or [e["path"]]
        for u in inputs:
            if e.get("remote"):
                cmd += ["-reconnect", "1", "-reconnect_streamed", "1", "-reconnect_delay_max", "5"]
                if e.get("headers"):
                    cmd += ["-headers", e["headers"]]
            if start > 0:
                cmd += ["-ss", f"{start:.3f}"]
            cmd += ["-i", u]
        if e["kind"] == "video" and len(inputs) > 1:   # ayri goruntu + ses akislari
            cmd += ["-map", "0:v:0", "-map", "1:a:0"]
        elif e["kind"] == "video":
            cmd += ["-map", "0:v:0", "-map", f"0:a:{audio_index}?"]
            if e["mode"] == "transcode":
                cmd += self.encoder() + ["-pix_fmt", "yuv420p", "-g", "48"]
                h = int(e["info"].get("height") or 0)
                if h > 2160:
                    cmd += ["-vf", "scale=-2:2160"]
            else:
                cmd += ["-c:v", "copy"]   # remux (ve 'direct' kaydin zorla akisi)
        else:
            cmd += ["-map", f"0:a:{audio_index}" if len(inputs) == 1 else "1:a:0", "-vn"]
        auds = e["info"].get("audio") or []
        ch = (auds[audio_index] if audio_index < len(auds) else {}).get("channels", 0)
        if dialog and ch >= 6:   # 5.1/7.1 -> stereo, merkez (diyalog) one: c2 = FC, c4/c5 = arka/yan
            cmd += ["-af", "pan=stereo|c0=c2+0.30*c0+0.30*c4|c1=c2+0.30*c1+0.30*c5"]
        cmd += ["-c:a", "aac", "-b:a", "224k", "-ac", "2", "-sn", "-dn",
                "-movflags", "frag_keyframe+empty_moov+default_base_moof", "-f", "mp4", "pipe:1"]
        return cmd

    def keyframe_before(self, e: dict[str, Any], t: float) -> float:
        fp = find_ffprobe(self.ffmpeg())
        if not fp or t <= 0:
            return max(0.0, t)
        try:
            r = subprocess.run([fp, "-v", "error", "-select_streams", "v:0", "-skip_frame", "nokey",
                                "-read_intervals", f"{max(0.0, t - 30):.3f}%{t + 0.5:.3f}",
                                "-show_entries", "frame=pts_time,best_effort_timestamp_time", "-of", "csv=p=0", e["path"]],
                               capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
            best = 0.0
            for line in r.stdout.split():
                for v in line.split(","):
                    try:
                        x = float(v)
                    except ValueError:
                        continue
                    if x <= t + 0.01:
                        best = max(best, x)
            return best
        except Exception:
            return max(0.0, t)

    def thumb(self, key: str, e: dict[str, Any], t: float) -> bytes:
        slot = int(max(0.0, t) // 5)
        ck = (key, slot)
        if ck in self._thumbs:
            return self._thumbs[ck]
        r = subprocess.run([self.ffmpeg(), "-hide_banner", "-loglevel", "error", "-ss", str(slot * 5 + 2), "-i", e["path"],
                            "-map", "0:v:0", "-frames:v", "1", "-vf", "scale=208:-2", "-q:v", "6", "-f", "image2", "-c:v", "mjpeg", "pipe:1"],
                           capture_output=True, timeout=15, creationflags=NO_WINDOW)
        data = r.stdout if r.returncode == 0 else b""
        if len(self._thumbs) > 600:
            self._thumbs.pop(next(iter(self._thumbs)))
        self._thumbs[ck] = data
        return data

    def spawn(self, cmd: list[str]) -> subprocess.Popen:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, stdin=subprocess.DEVNULL,
                             creationflags=NO_WINDOW, bufsize=0)
        self._procs.add(p)
        return p

    def done(self, p: subprocess.Popen) -> None:
        _kill(p)
        self._procs.discard(p)


def _kill(p: subprocess.Popen) -> None:
    try:
        if p.poll() is None:
            p.kill()
        p.wait(timeout=3)
    except Exception:
        pass


def _make_handler(server: MediaServer):
    class Handler(BaseHTTPRequestHandler):
        protocol_version = "HTTP/1.1"

        def log_message(self, fmt, *args):
            log.debug("media: " + fmt, *args)

        def _cors(self) -> None:
            self.send_header("Access-Control-Allow-Origin", "*")   # file:// sayfasi (Origin: null) + Web Audio
            self.send_header("Cache-Control", "no-store")

        def _err(self, code: int) -> None:
            self.send_response(code)
            self._cors()
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_OPTIONS(self):
            self.send_response(204)
            self._cors()
            self.send_header("Access-Control-Allow-Headers", "Range")
            self.send_header("Content-Length", "0")
            self.end_headers()

        def do_HEAD(self):
            self.do_GET(head=True)

        def do_GET(self, head: bool = False):
            parts = urllib.parse.urlsplit(self.path)
            seg = parts.path.strip("/").split("/")
            if len(seg) != 3 or not secrets.compare_digest(seg[0], server.token):
                return self._err(403)
            _, route, key = seg
            if route == "j":   # ASS cizici (worker blob olarak buradan alinir: file:// sayfasi worker acamaz)
                return self._vendor(key, head)
            q = urllib.parse.parse_qs(parts.query)
            e = server.entry(key)
            if not e:
                return self._err(404)
            try:
                if route == "f":
                    self._file(e["path"], head)
                elif route == "x":
                    m = (q.get("m") or [""])[0]
                    if m in ("remux", "transcode"):   # dogrudan oynatma basarisiz olunca arayuz zorlar
                        e = {**e, "mode": m}
                    self._stream(e, float((q.get("t") or ["0"])[0] or 0), int((q.get("a") or ["0"])[0] or 0), head,
                                 (q.get("dm") or [""])[0] == "1")
                elif route == "s":
                    if e["path"].lower().endswith((".ass", ".ssa")) and server.ffmpeg():   # ASS -> duz VTT (yedek gorunum)
                        r = subprocess.run([server.ffmpeg(), "-hide_banner", "-loglevel", "error", "-i", e["path"], "-f", "webvtt", "pipe:1"],
                                           capture_output=True, timeout=60, creationflags=NO_WINDOW)
                        data = r.stdout
                    else:
                        data = srt_to_vtt(read_text(e["path"])).encode("utf-8")
                    self._bytes(data, "text/vtt; charset=utf-8", head)
                elif route == "e":
                    data = server.extract_sub(e, int((q.get("i") or ["0"])[0] or 0), (q.get("raw") or [""])[0] == "1")
                    if data:
                        raw = (q.get("raw") or [""])[0] == "1" and data[:20].lstrip().startswith(b"[Script")
                        self._bytes(data, "text/plain; charset=utf-8" if raw else "text/vtt; charset=utf-8", head)
                    else:
                        self._err(404)
                elif route == "r":   # yan altyazi dosyasinin kendisi (ASS icin)
                    self._bytes(read_text(e["path"]).encode("utf-8"), "text/plain; charset=utf-8", head)
                elif route == "a":
                    data = server.font(e, (q.get("n") or [""])[0])
                    if data:
                        self._bytes(data, "font/ttf", head)
                    else:
                        self._err(404)
                elif route == "k":
                    t = float((q.get("t") or ["0"])[0] or 0)
                    kf = server.keyframe_before(e, t) if e["kind"] == "video" and not e.get("remote") else t   # arayuz sadece kopya akista sorar
                    self._bytes(json.dumps({"t": kf}).encode(), "application/json", head)
                elif route == "p":
                    data = server.thumb(key, e, float((q.get("t") or ["0"])[0] or 0)) if e["kind"] == "video" and server.ffmpeg() else b""
                    if data:
                        self._bytes(data, "image/jpeg", head)
                    else:
                        self._err(404)
                elif route == "c":
                    self._cover(e["path"], head)
                else:
                    self._err(404)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                pass

        def _bytes(self, data: bytes, ctype: str, head: bool) -> None:
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            if not head:
                self.wfile.write(data)

        def _file(self, path: str, head: bool) -> None:
            size = os.path.getsize(path)
            ctype = mimetypes.guess_type(path)[0] or "application/octet-stream"
            if path.lower().endswith(".mkv"):
                ctype = "video/webm"   # Chromium mkv'yi webm ayristiricisiyla acar
            start, end = 0, size - 1
            rng = self.headers.get("Range", "")
            m = re.match(r"bytes=(\d*)-(\d*)", rng)
            if m and (m.group(1) or m.group(2)):
                if m.group(1):
                    start = int(m.group(1))
                    end = int(m.group(2)) if m.group(2) else size - 1
                else:
                    start = max(0, size - int(m.group(2)))
                if start >= size:
                    self.send_response(416)
                    self._cors()
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.send_header("Content-Length", "0")
                    self.end_headers()
                    return
                end = min(end, size - 1)
                self.send_response(206)
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            else:
                self.send_response(200)
            self._cors()
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(end - start + 1))
            self.end_headers()
            if head:
                return
            import time as _time
            with open(path, "rb") as f:
                f.seek(start)
                left = end - start + 1
                pos = start
                while left > 0:
                    avail = server.growing(path)
                    waited = 0.0
                    while avail is not None and pos >= avail and waited < 60:   # inerken izle: parca gelene kadar bekle
                        _time.sleep(0.5)
                        waited += 0.5
                        avail = server.growing(path)
                    n = min(CHUNK, left) if avail is None else max(0, min(CHUNK, left, avail - pos))
                    if n <= 0:
                        break
                    buf = f.read(n)
                    if not buf:
                        break
                    self.wfile.write(buf)
                    left -= len(buf)
                    pos += len(buf)

        def _stream(self, e: dict[str, Any], start: float, audio_index: int, head: bool, dialog: bool = False) -> None:
            if not server.ffmpeg():
                return self._err(503)
            self.send_response(200)
            self._cors()
            self.send_header("Content-Type", "video/mp4" if e["kind"] == "video" else "audio/mp4")
            self.send_header("Connection", "close")   # uzunluk belli degil: baglanti kapaninca biter
            self.end_headers()
            self.close_connection = True
            if head:
                return
            p = server.spawn(server.stream_cmd(e, start, audio_index, dialog))
            try:
                while True:
                    buf = p.stdout.read(CHUNK)
                    if not buf:
                        break
                    self.wfile.write(buf)
            finally:
                server.done(p)
                err = (p.stderr.read() if p.stderr else b"")[-600:]
                if err.strip():
                    log.info("ffmpeg akisi: %s", err.decode("utf-8", "replace").strip())

        def _vendor(self, name: str, head: bool) -> None:
            ok = {"jassub-worker.js": "text/javascript", "jassub-worker.wasm": "application/wasm",
                  "jassub-worker-modern.wasm": "application/wasm", "default.woff2": "font/woff2"}
            f = (server.vendor_dir / name) if server.vendor_dir and name in ok else None
            if not f or not f.is_file():
                return self._err(404)
            self._bytes(f.read_bytes(), ok[name], head)

        def _cover(self, path: str, head: bool) -> None:
            ff = server.ffmpeg()
            if not ff:
                return self._err(404)
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-i", path, "-map", "0:v:0", "-frames:v", "1",
                                "-c:v", "mjpeg", "-f", "image2", "pipe:1"], capture_output=True, timeout=20, creationflags=NO_WINDOW)
            if r.returncode or not r.stdout:
                return self._err(404)
            self._bytes(r.stdout, "image/jpeg", head)

    return Handler
