"""Kami Player+ (v1.28): film/dizi bilgisi, ogrenen intro/outro atlama, IPTV (m3u + XMLTV), DLNA/UPnP yayin.

- Bilgi: diziler TVmaze (anahtarsiz), filmler TMDB (kullanici anahtar girerse), anime AniList (mediatools).
- Intro: kullanici bir bolumde introyu bir kez isaretler; ayni dizinin diger bolumlerinde Chromaprint (fpcalc) parmak izi
  ile yeri bulunur (intro her bolumde ayni saniyede olmayabilir). fpcalc yoksa ayni saniyeler kullanilir.
- IPTV: m3u/m3u8 (yerel ya da URL) -> kanallar; XMLTV rehberi -> simdi/sonra.
- Yayin: SSDP ile ag icindeki MediaRenderer (TV, Kodi, VLC...) bulunur, AVTransport SOAP ile oynatilir; dosya ag ici
  kisa omurlu, rastgele anahtarli bir HTTP adresinden (Range destekli) sunulur.
"""
from __future__ import annotations

import gzip
import json
import logging
import os
import re
import secrets
import shutil
import socket
import subprocess
import threading
import time
import urllib.parse
import xml.etree.ElementTree as ET
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import requests

from app import paths

log = logging.getLogger(__name__)
NO_WINDOW = 0x08000000 if os.name == "nt" else 0
UA = {"User-Agent": "Kami/1.28 (+github.com/murasakimono/kami)"}


# ---------------------------------------------------------------- onbellek
class _Store:
    def __init__(self, name: str) -> None:
        self.f = paths.DATA_DIR / name
        self._lock = threading.Lock()
        try:
            self.d: dict[str, Any] = json.loads(self.f.read_text("utf-8"))
        except (OSError, ValueError):
            self.d = {}

    def get(self, k: str, default: Any = None) -> Any:
        return self.d.get(k, default)

    def set(self, k: str, v: Any) -> None:
        with self._lock:
            self.d[k] = v
            try:
                self.f.parent.mkdir(parents=True, exist_ok=True)
                tmp = self.f.with_suffix(".tmp")
                tmp.write_text(json.dumps(self.d, ensure_ascii=False), "utf-8")
                tmp.replace(self.f)
            except OSError:
                pass


_META: _Store | None = None
_INTRO: _Store | None = None


def _meta() -> _Store:
    global _META
    if _META is None:
        _META = _Store("media_meta.json")
    return _META


def _intro() -> _Store:
    global _INTRO
    if _INTRO is None:
        _INTRO = _Store("intro_marks.json")
    return _INTRO


# ---------------------------------------------------------------- film / dizi bilgisi
def _clean_html(s: str) -> str:
    return re.sub(r"<[^>]+>", "", s or "").strip()


def series_info(name: str) -> dict[str, Any] | None:
    """TVmaze: afis, ozet, yil, turler, puan + bolum adlari {"S1E2": ad}."""
    key = "tv:" + name.lower().strip()
    hit = _meta().get(key)
    if hit is not None and time.time() - hit.get("_t", 0) < 14 * 86400:
        return hit or None
    try:
        r = requests.get("https://api.tvmaze.com/singlesearch/shows", params={"q": name, "embed": "episodes"}, headers=UA, timeout=12)
    except requests.RequestException:
        return None
    if r.status_code == 404:
        _meta().set(key, {"_t": time.time()})
        return None
    if r.status_code != 200:
        return None
    s = r.json()
    eps = {f"S{e.get('season')}E{e.get('number')}": {"name": e.get("name") or "", "summary": _clean_html(e.get("summary") or "")[:300]}
           for e in (s.get("_embedded") or {}).get("episodes") or [] if e.get("number")}
    res = {"_t": time.time(), "source": "tvmaze", "title": s.get("name") or name, "year": (s.get("premiered") or "")[:4],
           "overview": _clean_html(s.get("summary") or "")[:700], "genres": s.get("genres") or [],
           "rating": (s.get("rating") or {}).get("average"), "poster": ((s.get("image") or {}).get("original") or (s.get("image") or {}).get("medium") or ""),
           "episodes": eps, "status": s.get("status") or ""}
    _meta().set(key, res)
    return res


def movie_info(title: str, year: str = "", tmdb_key: str = "") -> dict[str, Any] | None:
    """TMDB (anahtar varsa, Turkce ozet once). Anahtar yoksa None."""
    if not tmdb_key:
        return None
    key = f"mv:{title.lower().strip()}:{year}"
    hit = _meta().get(key)
    if hit is not None and time.time() - hit.get("_t", 0) < 30 * 86400:
        return hit or None
    try:
        r = requests.get("https://api.themoviedb.org/3/search/movie", params={"api_key": tmdb_key, "query": title, "year": year or None,
                                                                             "language": "tr-TR"}, headers=UA, timeout=12)
        js = r.json() if r.status_code == 200 else {}
    except (requests.RequestException, ValueError):
        return None
    m = (js.get("results") or [None])[0]
    if not m:
        _meta().set(key, {"_t": time.time()})
        return None
    res = {"_t": time.time(), "source": "tmdb", "title": m.get("title") or title, "year": (m.get("release_date") or "")[:4],
           "overview": (m.get("overview") or "")[:700], "rating": m.get("vote_average"),
           "poster": f"https://image.tmdb.org/t/p/w500{m['poster_path']}" if m.get("poster_path") else "",
           "backdrop": f"https://image.tmdb.org/t/p/w1280{m['backdrop_path']}" if m.get("backdrop_path") else ""}
    _meta().set(key, res)
    return res


_MOVIE = re.compile(r"^(?P<t>.+?)[\s._(\[]+(?P<y>(19|20)\d{2})(?=[\s._)\]]|$)")


def guess_movie(stem: str) -> tuple[str, str]:
    m = _MOVIE.search(stem)
    if not m:
        return "", ""
    t = re.sub(r"[._]+", " ", m.group("t")).strip(" -")
    return t, m.group("y")


# ---------------------------------------------------------------- intro ogrenme (Chromaprint)
def fpcalc_path() -> str:
    for c in (paths.BIN_DIR / "fpcalc.exe", paths.BIN_DIR / "fpcalc"):
        if c.is_file():
            return str(c)
    return shutil.which("fpcalc") or ""


FP_RATE = 0.1238   # Chromaprint ham parmak izi: ornek basina ~0.124 sn


def fingerprint(path: str, seconds: int = 420) -> list[int]:
    exe = fpcalc_path()
    if not exe:
        return []
    try:
        r = subprocess.run([exe, "-raw", "-length", str(int(seconds)), "-json", path], capture_output=True, timeout=120,
                           creationflags=NO_WINDOW)
        return [int(x) & 0xFFFFFFFF for x in json.loads(r.stdout.decode("utf-8", "replace")).get("fingerprint") or []]
    except (OSError, ValueError, subprocess.SubprocessError):
        return []


def _bits(x: int) -> int:
    return bin(x).count("1")


def best_offset(ref: list[int], seg_start: int, seg_len: int, other: list[int], max_err: float = 0.32) -> int | None:
    """ref[seg_start:seg_start+seg_len] parcasinin other icindeki en iyi konumu (ornek indeksi) ya da None."""
    seg = ref[seg_start:seg_start + seg_len]
    if len(seg) < 20 or len(other) < len(seg):
        return None
    best, best_i = 1.0, None
    step = 1 if len(other) < 4000 else 2
    for i in range(0, len(other) - len(seg) + 1, step):
        err = 0
        for k in range(0, len(seg), 2):   # yarim ornekleme: hiz
            err += _bits(seg[k] ^ other[i + k])
        e = err / (32 * ((len(seg) + 1) // 2))
        if e < best:
            best, best_i = e, i
    return best_i if best <= max_err else None


def learn_intro(path: str, series: str, start: float, end: float, kind: str = "intro") -> dict[str, Any]:
    """Kullanici isaretledi: dizinin referansi olur."""
    if end - start < 3:
        return {"ok": False, "error": "aralik cok kisa"}
    marks = _intro().get(series.lower(), {})
    marks[kind] = {"ref": path, "start": round(start, 2), "end": round(end, 2), "t": time.time()}
    _intro().set(series.lower(), marks)
    return {"ok": True, "series": series, kind: marks[kind]}


def find_intro(path: str, series: str) -> list[dict[str, Any]]:
    """Bu bolumde ogrenilmis intro/outro nerede? [{start, end, type}] (player_skips bicimi)."""
    marks = _intro().get(series.lower(), {}) if series else {}
    out = []
    for kind, m in marks.items():
        st, en = float(m["start"]), float(m["end"])
        if os.path.normcase(m.get("ref", "")) == os.path.normcase(path):
            out.append({"start": st, "end": en, "type": "op" if kind == "intro" else "ed", "source": "kami"})
            continue
        ck = f"pos:{path}:{kind}"
        cache = _intro().get("_cache", {})
        if ck in cache:
            if cache[ck]:
                out.append(cache[ck])
            continue
        res = None
        if kind == "intro" and fpcalc_path() and os.path.isfile(m.get("ref", "")):
            ref = fingerprint(m["ref"], int(min(900, en + 60)))
            oth = fingerprint(path, int(min(900, en + 240)))
            a, n = int(st / FP_RATE), int((en - st) / FP_RATE)
            i = best_offset(ref, a, min(n, 400), oth) if ref and oth else None
            if i is not None:
                s2 = round(i * FP_RATE, 2)
                res = {"start": s2, "end": round(s2 + (en - st), 2), "type": "op", "source": "kami-fp"}
        if res is None and kind == "intro" and not fpcalc_path():
            res = {"start": st, "end": en, "type": "op", "source": "kami"}   # parmak izi yok: ayni saniyeler
        if res is None and kind == "outro":
            res = {"start": st, "end": en, "type": "ed", "source": "kami", "from_end": True}
        cache[ck] = res
        _intro().set("_cache", dict(list(cache.items())[-800:]))
        if res:
            out.append(res)
    return out


# ---------------------------------------------------------------- IPTV
_EXTINF = re.compile(r'#EXTINF:[^,]*?((?:\s+[\w-]+="[^"]*")*)\s*,(.*)$')
_ATTR = re.compile(r'([\w-]+)="([^"]*)"')


def parse_m3u(text: str, base: str = "") -> list[dict[str, Any]]:
    out, cur = [], None
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.upper().startswith("#EXTINF"):
            m = _EXTINF.match(line)
            attrs = dict(_ATTR.findall(m.group(1))) if m else {}
            cur = {"name": (m.group(2).strip() if m else line.split(",", 1)[-1].strip()) or attrs.get("tvg-name", "Kanal"),
                   "group": attrs.get("group-title", ""), "logo": attrs.get("tvg-logo", ""), "id": attrs.get("tvg-id", ""),
                   "chno": attrs.get("tvg-chno", "")}
        elif line.startswith("#EXTGRP:") and cur is not None:
            cur["group"] = line[8:].strip()
        elif not line.startswith("#"):
            url = urllib.parse.urljoin(base, line) if base and not re.match(r"^[a-z]+://", line, re.I) else line
            ch = cur or {"name": url.rsplit("/", 1)[-1] or "Kanal", "group": "", "logo": "", "id": "", "chno": ""}
            ch["url"] = url
            out.append(ch)
            cur = None
    return out


def load_playlist(src: str) -> dict[str, Any]:
    src = (src or "").strip()
    try:
        if re.match(r"^https?://", src, re.I):
            r = requests.get(src, headers=UA, timeout=25)
            r.raise_for_status()
            text, base = r.content.decode("utf-8", "replace"), src
        else:
            text, base = Path(src).read_text("utf-8", "replace"), ""
    except (OSError, requests.RequestException) as exc:
        return {"ok": False, "error": str(exc)[:200]}
    m = re.search(r'url-tvg="([^"]+)"|x-tvg-url="([^"]+)"', text[:2000])
    chans = parse_m3u(text, base)
    return {"ok": bool(chans), "channels": chans[:20000], "epg": (m.group(1) or m.group(2)) if m else "",
            "groups": sorted({c["group"] for c in chans if c["group"]}), "error": "" if chans else "kanal bulunamadi"}


def _xmltv_time(s: str) -> float:
    s = (s or "").strip()
    try:
        base = time.mktime(time.strptime(s[:14], "%Y%m%d%H%M%S"))
        tz = re.search(r"([+-])(\d{2})(\d{2})$", s)
        if tz:   # XMLTV yerel saat + ofset -> UTC epoch
            off = (int(tz.group(2)) * 3600 + int(tz.group(3)) * 60) * (1 if tz.group(1) == "+" else -1)
            local_off = -time.timezone if not time.localtime().tm_isdst else -time.altzone
            base = base - off + local_off
        return base
    except ValueError:
        return 0.0


def parse_xmltv(data: bytes, ids: set[str] | None = None, now: float | None = None) -> dict[str, list[dict[str, Any]]]:
    """{kanal_id: [{start, stop, title, desc}]} — yalniz simdi + sonraki 3 program."""
    if data[:2] == b"\x1f\x8b":
        data = gzip.decompress(data)
    now = now or time.time()
    out: dict[str, list[dict[str, Any]]] = {}
    for _ev, el in ET.iterparse(__import__("io").BytesIO(data), events=("end",)):
        if el.tag != "programme":
            continue
        ch = el.get("channel") or ""
        if ids and ch not in ids:
            el.clear()
            continue
        st, sp = _xmltv_time(el.get("start", "")), _xmltv_time(el.get("stop", ""))
        if sp and sp < now:
            el.clear()
            continue
        lst = out.setdefault(ch, [])
        if len(lst) < 4:
            lst.append({"start": st, "stop": sp, "title": (el.findtext("title") or "").strip(), "desc": (el.findtext("desc") or "").strip()[:240]})
        el.clear()
    for v in out.values():
        v.sort(key=lambda p: p["start"])
    return out


def load_epg(url: str, ids: list[str] | None = None) -> dict[str, Any]:
    try:
        r = requests.get(url, headers=UA, timeout=60)
        r.raise_for_status()
        return {"ok": True, "epg": parse_xmltv(r.content, set(ids or []) or None)}
    except (requests.RequestException, ET.ParseError, OSError) as exc:
        return {"ok": False, "error": str(exc)[:200]}


# ---------------------------------------------------------------- DLNA / UPnP yayin
SSDP = ("239.255.255.250", 1900)
AVT = "urn:schemas-upnp-org:service:AVTransport:1"
RC = "urn:schemas-upnp-org:service:RenderingControl:1"


def lan_ip() -> str:
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


def discover(timeout: float = 3.0) -> list[dict[str, Any]]:
    msg = ("M-SEARCH * HTTP/1.1\r\nHOST: 239.255.255.250:1900\r\nMAN: \"ssdp:discover\"\r\nMX: 2\r\n"
           "ST: urn:schemas-upnp-org:device:MediaRenderer:1\r\n\r\n").encode()
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM, socket.IPPROTO_UDP)
    sock.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_TTL, 2)
    sock.settimeout(0.5)
    locs: set[str] = set()
    try:
        sock.bind((lan_ip(), 0))
        for _ in range(2):
            sock.sendto(msg, SSDP)
        end = time.time() + timeout
        while time.time() < end:
            try:
                data, _a = sock.recvfrom(4096)
            except socket.timeout:
                continue
            m = re.search(rb"(?im)^location:\s*(\S+)", data)
            if m:
                locs.add(m.group(1).decode("utf-8", "replace"))
    except OSError as exc:
        log.info("SSDP: %s", exc)
    finally:
        sock.close()
    devs = []
    for loc in locs:
        d = describe(loc)
        if d:
            devs.append(d)
    return devs


def _ns_strip(root: ET.Element) -> None:
    for el in root.iter():
        if "}" in el.tag:
            el.tag = el.tag.split("}", 1)[1]


def describe(location: str) -> dict[str, Any] | None:
    try:
        r = requests.get(location, timeout=4)
        root = ET.fromstring(r.content)
    except (requests.RequestException, ET.ParseError):
        return None
    _ns_strip(root)
    dev = root.find(".//device")
    if dev is None:
        return None
    svc = {}
    for s in root.iter("service"):
        st, cu = s.findtext("serviceType") or "", s.findtext("controlURL") or ""
        if st.startswith("urn:schemas-upnp-org:service:AVTransport"):
            svc["avt"] = urllib.parse.urljoin(location, cu)
        elif st.startswith("urn:schemas-upnp-org:service:RenderingControl"):
            svc["rc"] = urllib.parse.urljoin(location, cu)
    if "avt" not in svc:
        return None
    return {"name": dev.findtext("friendlyName") or "TV", "model": dev.findtext("modelName") or "", "location": location, **svc,
            "id": dev.findtext("UDN") or location}


def _soap(url: str, service: str, action: str, args: dict[str, Any]) -> str:
    body = "".join(f"<{k}>{_x(v)}</{k}>" for k, v in args.items())
    env = ('<?xml version="1.0" encoding="utf-8"?><s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/" '
           's:encodingStyle="http://schemas.xmlsoap.org/soap/encoding/"><s:Body>'
           f'<u:{action} xmlns:u="{service}">{body}</u:{action}></s:Body></s:Envelope>')
    r = requests.post(url, data=env.encode("utf-8"), timeout=8,
                      headers={"Content-Type": 'text/xml; charset="utf-8"', "SOAPAction": f'"{service}#{action}"'})
    if r.status_code >= 400:
        raise RuntimeError(f"{action}: HTTP {r.status_code} {r.text[:160]}")
    return r.text


def _x(v: Any) -> str:
    return str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _didl(url: str, title: str, mime: str) -> str:
    return ('<DIDL-Lite xmlns="urn:schemas-upnp-org:metadata-1-0/DIDL-Lite/" xmlns:dc="http://purl.org/dc/elements/1.1/" '
            'xmlns:upnp="urn:schemas-upnp-org:metadata-1-0/upnp/"><item id="0" parentID="-1" restricted="1">'
            f"<dc:title>{_x(title)}</dc:title><upnp:class>object.item.videoItem</upnp:class>"
            f'<res protocolInfo="http-get:*:{mime}:*">{_x(url)}</res></item></DIDL-Lite>')


def _fmt(sec: float) -> str:
    sec = max(0, int(sec))
    return f"{sec // 3600:01d}:{sec // 60 % 60:02d}:{sec % 60:02d}"


class CastServer:
    """TV'nin erisecegi ag ici dosya sunucusu: yalniz paylasilan dosya, adres rastgele anahtarli, Range destekli."""

    def __init__(self) -> None:
        self.httpd: ThreadingHTTPServer | None = None
        self.files: dict[str, str] = {}
        self.ip = ""

    def share(self, path: str) -> str:
        if not self.httpd:
            self.ip = lan_ip()
            srv = self

            class H(BaseHTTPRequestHandler):
                def log_message(self, *a):
                    pass

                def _file(self) -> str | None:
                    key = self.path.split("/")[1] if self.path.count("/") >= 1 else ""
                    return srv.files.get(key)

                def do_HEAD(self):
                    self.do_GET(head=True)

                def do_GET(self, head: bool = False):
                    f = self._file()
                    if not f or not os.path.isfile(f):
                        self.send_error(404)
                        return
                    size = os.path.getsize(f)
                    rng = re.match(r"bytes=(\d*)-(\d*)", self.headers.get("Range", ""))
                    a, b = 0, size - 1
                    if rng:
                        a = int(rng.group(1) or 0)
                        b = int(rng.group(2)) if rng.group(2) else size - 1
                    b = min(b, size - 1)
                    self.send_response(206 if rng else 200)
                    self.send_header("Content-Type", _mime(f))
                    self.send_header("Accept-Ranges", "bytes")
                    self.send_header("Content-Length", str(b - a + 1))
                    if rng:
                        self.send_header("Content-Range", f"bytes {a}-{b}/{size}")
                    self.send_header("transferMode.dlna.org", "Streaming")
                    self.send_header("contentFeatures.dlna.org", "DLNA.ORG_OP=01;DLNA.ORG_CI=0;DLNA.ORG_FLAGS=01700000000000000000000000000000")
                    self.end_headers()
                    if head:
                        return
                    try:
                        with open(f, "rb") as fh:
                            fh.seek(a)
                            left = b - a + 1
                            while left > 0:
                                chunk = fh.read(min(1 << 20, left))
                                if not chunk:
                                    break
                                self.wfile.write(chunk)
                                left -= len(chunk)
                    except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
                        pass

            self.httpd = ThreadingHTTPServer((self.ip, 0), H)
            self.httpd.daemon_threads = True
            threading.Thread(target=self.httpd.serve_forever, daemon=True, name="kami-cast").start()
        key = secrets.token_urlsafe(12)
        self.files = {key: path}   # her seferinde yalniz son dosya erisilebilir
        name = urllib.parse.quote(Path(path).name)
        return f"http://{self.ip}:{self.httpd.server_address[1]}/{key}/{name}"

    def stop(self) -> None:
        if self.httpd:
            self.httpd.shutdown()
            self.httpd.server_close()
            self.httpd = None
        self.files = {}


def _mime(f: str) -> str:
    return {".mp4": "video/mp4", ".m4v": "video/mp4", ".mkv": "video/x-matroska", ".webm": "video/webm", ".avi": "video/x-msvideo",
            ".mov": "video/quicktime", ".ts": "video/mp2t", ".mp3": "audio/mpeg", ".flac": "audio/flac", ".m4a": "audio/mp4",
            ".jpg": "image/jpeg", ".png": "image/png"}.get(Path(f).suffix.lower(), "application/octet-stream")


CAST = CastServer()


def cast_play(dev: dict[str, Any], path: str, start: float = 0.0, url: str = "") -> dict[str, Any]:
    """Dosyayi (ya da hazir URL'yi) TV'de oynat."""
    u = url or CAST.share(path)
    title = Path(path).stem if path else "Kami"
    mime = _mime(path) if path else "video/mp4"
    avt = dev["avt"]
    try:
        try:
            _soap(avt, AVT, "Stop", {"InstanceID": 0})
        except Exception:
            pass
        _soap(avt, AVT, "SetAVTransportURI", {"InstanceID": 0, "CurrentURI": u, "CurrentURIMetaData": _didl(u, title, mime)})
        _soap(avt, AVT, "Play", {"InstanceID": 0, "Speed": 1})
        if start > 3:
            time.sleep(1.5)
            try:
                _soap(avt, AVT, "Seek", {"InstanceID": 0, "Unit": "REL_TIME", "Target": _fmt(start)})
            except Exception:
                pass
        return {"ok": True, "url": u}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def cast_control(dev: dict[str, Any], action: str, value: float = 0) -> dict[str, Any]:
    try:
        if action in ("Play", "Pause", "Stop"):
            _soap(dev["avt"], AVT, action, {"InstanceID": 0, **({"Speed": 1} if action == "Play" else {})})
        elif action == "Seek":
            _soap(dev["avt"], AVT, "Seek", {"InstanceID": 0, "Unit": "REL_TIME", "Target": _fmt(value)})
        elif action == "Volume" and dev.get("rc"):
            _soap(dev["rc"], RC, "SetVolume", {"InstanceID": 0, "Channel": "Master", "DesiredVolume": int(max(0, min(100, value)))})
        elif action == "Position":
            t = _soap(dev["avt"], AVT, "GetPositionInfo", {"InstanceID": 0})
            m = re.search(r"<RelTime>([\d:]+)</RelTime>", t)
            d = re.search(r"<TrackDuration>([\d:]+)</TrackDuration>", t)
            hms = lambda s: sum(int(x) * 60 ** i for i, x in enumerate(reversed(s.split(":")))) if s else 0   # noqa: E731
            return {"ok": True, "pos": hms(m.group(1)) if m else 0, "dur": hms(d.group(1)) if d else 0}
        else:
            return {"ok": False, "error": "bad_action"}
        if action == "Stop":
            CAST.stop()
        return {"ok": True}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def anki_connect_mine(word: str, sentence: str, reading: str = "", meaning: str = "",
                      deck: str = "Kami", model: str = "Basic",
                      audio_b64: str = "", image_b64: str = "") -> dict[str, Any]:
    """Yerel AnkiConnect (127.0.0.1:8765) uzerinden cumle + ekran goruntusu karti gonderir."""
    w = str(word or "").strip()
    sent = str(sentence or "").strip()
    if not (w or sent):
        return {"ok": False, "error": "empty_card"}
    url = "http://127.0.0.1:8765"

    def _post(action: str, params: dict[str, Any]) -> Any:
        body = json.dumps({"action": action, "version": 6, "params": params}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=2.5) as resp:
            return json.loads(resp.read().decode("utf-8"))

    try:
        try:
            _post("createDeck", {"deck": deck or "Kami"})
        except Exception:
            pass
        ts = int(time.time() * 1000)
        front = w or sent
        back_parts = [p for p in (meaning, reading, sent if w else "") if p]
        if image_b64:
            raw_img = image_b64.split(",", 1)[1] if "," in image_b64[:60] else image_b64
            fname = f"kami_snap_{ts}.png"
            _post("storeMediaFile", {"filename": fname, "data": raw_img})
            back_parts.append(f'<br><img src="{fname}">')
        if audio_b64:
            raw_aud = audio_b64.split(",", 1)[1] if "," in audio_b64[:60] else audio_b64
            aname = f"kami_clip_{ts}.mp3"
            _post("storeMediaFile", {"filename": aname, "data": raw_aud})
            back_parts.append(f"[sound:{aname}]")
        res = _post("addNote", {
            "note": {
                "deckName": deck or "Kami",
                "modelName": model or "Basic",
                "fields": {"Front": front, "Back": "<br>".join(back_parts) or sent},
                "options": {"allowDuplicate": True},
                "tags": ["kami-player"],
            }
        })
        if isinstance(res, dict) and res.get("error"):
            return {"ok": False, "error": str(res["error"])[:140]}
        return {"ok": True, "id": res.get("result") if isinstance(res, dict) else res}
    except urllib.error.URLError:
        return {"ok": False, "error": "anki_offline"}
    except OSError:
        return {"ok": False, "error": "anki_offline"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:140]}
