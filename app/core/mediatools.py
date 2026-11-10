"""Kami Player B8/B9 yardimcilari: intro/outro (AniSkip), SponsorBlock, posterler (AniList),
ses cikarma, kayipsiz klip / GIF / Discord'a sigdir, bozuk dosya onarimi, Geri Donusum Kutusu."""
from __future__ import annotations

import ctypes
import json
import logging
import os
import re
import subprocess
import threading
from pathlib import Path
from typing import Any

import requests

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
UA = {"User-Agent": "Kami/1.0 (personal media player)"}
_lock = threading.Lock()


# ---------- kucuk JSON onbellegi ----------
class _Cache:
    def __init__(self, path: Path) -> None:
        self.path = path
        try:
            self.d = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            self.d = {}

    def get(self, k: str):
        return self.d.get(k)

    def set(self, k: str, v) -> None:
        with _lock:
            self.d[k] = v
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                self.path.write_text(json.dumps(self.d, ensure_ascii=False), encoding="utf-8")
            except OSError:
                pass


# ---------- AniList: anime arama (MAL id + poster) ----------
_ANILIST = "https://graphql.anilist.co"
_Q = "query($s:String){Media(search:$s,type:ANIME){id idMal title{romaji english} coverImage{large color} episodes}}"


def anilist(name: str, cache: _Cache) -> dict[str, Any] | None:
    key = "al:" + name.lower().strip()
    hit = cache.get(key)
    if hit is not None:
        return hit or None
    try:
        r = requests.post(_ANILIST, json={"query": _Q, "variables": {"s": name}}, headers=UA, timeout=12)
        m = ((r.json() or {}).get("data") or {}).get("Media") if r.status_code == 200 else None
    except (requests.RequestException, ValueError):
        return None   # ag hatasi: onbellege yazma, sonra tekrar dene
    res = {"mal": m.get("idMal"), "cover": (m.get("coverImage") or {}).get("large") or "",
           "color": (m.get("coverImage") or {}).get("color") or "",
           "title": (m.get("title") or {}).get("english") or (m.get("title") or {}).get("romaji") or ""} if m else {}
    cache.set(key, res)
    return res or None


# ---------- intro/outro: AniSkip ----------
def aniskip(series: str, ep: int, duration: float, cache: _Cache) -> list[dict[str, Any]]:
    if not series or not ep:
        return []
    al = anilist(series, cache)
    if not al or not al.get("mal"):
        return []
    key = f"as:{al['mal']}:{ep}"
    hit = cache.get(key)
    if hit is None:
        try:
            r = requests.get(f"https://api.aniskip.com/v2/skip-times/{al['mal']}/{int(ep)}",
                             params=[("types", "op"), ("types", "ed"), ("types", "recap"), ("types", "mixed-op"), ("types", "mixed-ed"),
                                     ("episodeLength", 0)], headers=UA, timeout=12)   # 0: tum surumler (uzunluk filtresi cok kati)
            js = r.json() if r.status_code in (200, 404) else None
        except (requests.RequestException, ValueError):
            return []
        hit = [{"start": float(x["interval"]["startTime"]), "end": float(x["interval"]["endTime"]),
                "type": x.get("skipType", "op").replace("mixed-", ""), "len": float(x.get("episodeLength") or 0)}
               for x in ((js or {}).get("results") or []) if x.get("interval")]
        cache.set(key, hit)
    out = []
    for s in hit:   # baska surum (farkli uzunluk): orana gore kaydir
        k = duration / s["len"] if s.get("len") and duration and abs(s["len"] - duration) > 10 else 1
        out.append({"start": s["start"] * k, "end": s["end"] * k, "type": s["type"], "src": "aniskip"})
    return out


# ---------- SponsorBlock (YouTube'dan inen dosyalar) ----------
_YT = re.compile(r"(?:\[|v=|youtu\.be/|-)([A-Za-z0-9_-]{11})(?:\]|&|$|\.)")


def youtube_id(path: str, tags: dict[str, str]) -> str:
    for src in (tags.get("purl", ""), tags.get("comment", ""), tags.get("description", ""), Path(path).stem):
        m = re.search(r"(?:youtube\.com/watch\?v=|youtu\.be/)([A-Za-z0-9_-]{11})", src or "") or re.search(r"\[([A-Za-z0-9_-]{11})\]", src or "")
        if m:
            return m.group(1)
    return ""


def sponsorblock(vid: str, cache: _Cache) -> list[dict[str, Any]]:
    if not vid:
        return []
    hit = cache.get("sb:" + vid)
    if hit is None:
        try:
            r = requests.get("https://sponsor.ajay.app/api/skipSegments",
                             params={"videoID": vid, "categories": json.dumps(["sponsor", "selfpromo", "interaction", "intro", "outro", "music_offtopic"])},
                             headers=UA, timeout=12)
            js = r.json() if r.status_code == 200 else []
        except (requests.RequestException, ValueError):
            return []
        hit = [{"start": float(x["segment"][0]), "end": float(x["segment"][1]), "type": x.get("category", "sponsor")} for x in js or []]
        cache.set("sb:" + vid, hit)
    return [{**s, "src": "sponsorblock"} for s in hit]


# ---------- ffmpeg isleri ----------
def _run(cmd: list[str], timeout: int = 3600) -> tuple[bool, str]:
    try:
        r = subprocess.run(cmd, capture_output=True, timeout=timeout, creationflags=NO_WINDOW)
    except subprocess.TimeoutExpired:
        return False, "timeout"
    err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
    return r.returncode == 0, (err[-1] if err else "")[:200]


def _free(p: Path) -> Path:
    if not p.exists():
        return p
    for i in range(2, 100):
        q = p.with_name(f"{p.stem} ({i}){p.suffix}")
        if not q.exists():
            return q
    return p


def extract_audio(ffmpeg: str, path: str, codec: str) -> dict[str, Any]:
    ext = {"aac": ".m4a", "mp3": ".mp3", "opus": ".opus", "vorbis": ".ogg", "flac": ".flac", "alac": ".m4a"}.get(codec, ".mka")
    p = Path(path)
    out = _free(p.with_name(p.stem + " (ses)" + ext))
    ok, err = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-i", str(p), "-vn", "-map", "0:a:0", "-c:a", "copy", str(out)])
    return {"ok": ok, "path": str(out)} if ok else {"ok": False, "error": err}


def clip(ffmpeg: str, path: str, a: float, b: float, mode: str, encoder: str = "libx264") -> dict[str, Any]:
    p = Path(path)
    a, b = max(0.0, float(a)), float(b)
    if b - a < 0.5:
        return {"ok": False, "error": "too_short"}
    tag = f"{int(a // 60):02d}{int(a % 60):02d}-{int(b // 60):02d}{int(b % 60):02d}"
    base = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{a:.3f}", "-to", f"{b:.3f}", "-i", str(p)]
    if mode == "gif":
        out = _free(p.with_name(f"{p.stem} [{tag}].gif"))
        vf = "fps=12,scale='min(480,iw)':-2:flags=lanczos,split[s0][s1];[s0]palettegen=max_colors=128[pl];[s1][pl]paletteuse=dither=bayer"
        ok, err = _run(base + ["-vf", vf, "-an", str(out)])
    elif mode == "discord":   # 10 MB sinirina sigdir: hedef bit hizi = boyut / sure
        out = _free(p.with_name(f"{p.stem} [{tag}] discord.mp4"))
        dur = b - a
        vk = max(150, int(9.2 * 8192 / dur) - 96)
        h = 720 if vk > 1500 else 480 if vk > 600 else 360
        venc = [*("-c:v", encoder), *(("-preset", "p5") if "nvenc" in encoder else ("-preset", "veryfast"))]
        ok, err = _run(base + ["-vf", f"scale=-2:'min({h},ih)'", *venc, "-b:v", f"{vk}k", "-maxrate", f"{vk}k", "-bufsize", f"{vk * 2}k",
                               "-c:a", "aac", "-b:a", "96k", "-ac", "2", "-movflags", "+faststart", str(out)])
        if not ok and encoder != "libx264":
            return clip(ffmpeg, path, a, b, mode, "libx264")
    else:   # kayipsiz: anahtar kareye yakin keser, yeniden kodlamaz
        ext = p.suffix.lower() if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".flac") else ".mkv"
        out = _free(p.with_name(f"{p.stem} [{tag}]{ext}"))
        ok, err = _run(base + ["-map", "0", "-c", "copy", "-avoid_negative_ts", "make_zero", str(out)])
    return {"ok": ok, "path": str(out)} if ok else {"ok": False, "error": err}


def repair(ffmpeg: str, path: str) -> dict[str, Any]:
    """Bozuk/kesik dosya: hatalari yok sayarak yeniden paketle (yeniden kodlama yok), orijinale dokunmaz."""
    p = Path(path)
    ext = p.suffix.lower() if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov", ".m4a", ".mp3", ".flac") else ".mkv"
    out = _free(p.with_name(p.stem + " (onarildi)" + ext))
    ok, err = _run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y", "-err_detect", "ignore_err", "-fflags", "+genpts+discardcorrupt",
                    "-i", str(p), "-map", "0:v?", "-map", "0:a?", "-map", "0:s?", "-dn", "-c", "copy", str(out)])
    if ok and out.exists() and out.stat().st_size > 1024:
        return {"ok": True, "path": str(out)}
    return {"ok": False, "error": err or "repair_failed"}


# ---------- Geri Donusum Kutusu ----------
class _SHFILEOPSTRUCTW(ctypes.Structure):
    _fields_ = [("hwnd", ctypes.c_void_p), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p), ("pTo", ctypes.c_wchar_p),
                ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", ctypes.c_int), ("hNameMappings", ctypes.c_void_p),
                ("lpszProgressTitle", ctypes.c_wchar_p)]


def to_trash(paths: list[str]) -> bool:
    """Dosyalari Geri Donusum Kutusu'na tasir (FOF_ALLOWUNDO). Windows disinda / basarisizsa False."""
    paths = [os.path.abspath(p) for p in paths if p and os.path.exists(p)]
    if not paths:
        return True
    if os.name != "nt":
        return False
    op = _SHFILEOPSTRUCTW(None, 3, "\0".join(paths) + "\0\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, 0, None, None)   # DELETE; ALLOWUNDO|NOCONFIRMATION|SILENT|NOERRORUI
    try:
        return ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op)) == 0 and not op.fAnyOperationsAborted
    except Exception:
        log.exception("Geri Donusum Kutusu")
        return False


def remove_or_trash(path: str) -> None:
    """Silme: once Geri Donusum Kutusu, olmazsa kalici sil."""
    if not to_trash([path]):
        os.remove(path)
