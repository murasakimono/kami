"""Kami Studio api'si (Api sinifina karisim olarak eklenir; JS: api.studio_*)."""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130 Safari/537.36"

STUDIO_JOBS = {"studio_info", "studio_peaks", "studio_thumbs", "studio_beats", "studio_silences", "studio_freezes", "studio_scenes",
               "studio_myinstants", "studio_fetch_sound", "studio_freesound", "studio_pack_add", "studio_save", "studio_open",
               "studio_stock", "studio_stock_get", "studio_fonts_download", "studio_template", "studio_sfx", "studio_lut_read",
               "studio_gemini_models", "studio_lottie", "studio_catalog_fonts",
               "studio_multicam_sync", "studio_smart_cut", "studio_audio_enhance", "studio_audio_duck"}


class StudioMixin:
    _studio = None
    _studio_win = None
    _studio_q: list[str] = []
    _studio_saved: dict[str, float] = {}

    # ---- pencere
    def _st(self):
        if self._studio is None:
            from app.core.studio import Studio
            self._studio = Studio(lambda: self._media.ffmpeg() if self._media else "")
        return self._studio

    def studio_show(self, path: str = "") -> dict[str, Any]:
        """Kami Studio penceresini acar (proje ya da medya yolu verilirse kuyruga)."""
        path = str(path or "")
        if path:
            with self._inbox_lock:
                self._studio_q = list(self._studio_q) + [path]
        if self._studio_win is None and getattr(self, "_make_studio_window", None):
            self._studio_win = self._make_studio_window()
        elif getattr(self, "_front_studio", None):
            self._front_studio()
        return {"ok": True}

    def studio_poll(self) -> list[str]:
        with self._inbox_lock:
            q, self._studio_q = list(self._studio_q), []
        return q

    def studio_catalog(self) -> dict[str, Any]:
        from app.core import studio
        cat = studio.catalog()
        for pk in self._studio_packs():
            for k, v in (pk.get("fx") or {}).items():
                cat["fx"][k] = {"name": v.get("name", k), "pack": v.get("pack") or pk.get("name", "Paket"), "css": v.get("css", ""),
                                "ov": v.get("ov", []), "ass": ""}
            cat["zoom"] += pk.get("zoom") or []
        fonts = []
        if self._media:
            fonts = [self._media.asset_url(str(f)) for f in studio.font_files()]
        home = studio.home_dir()
        return {**cat, "fontUrls": fonts, "jassub": f"{self._media.base}/j/" if self._media else "", "home": str(home),
                "packs": [{"name": p.get("name"), "id": p.get("_id"), "fx": len(p.get("fx") or {}), "sounds": len(p.get("sounds") or [])}
                          for p in self._studio_packs()],
                "freesound": bool(self._fs_store().load()), "keys": self.studio_keys_status()}

    # ---- medya
    def studio_info(self, paths: list[str]) -> list[dict[str, Any]]:
        """Ice aktarma: ozet + onizleme adresi (tarayici dogrudan acamiyorsa vekil dosya hazirlanir)."""
        st = self._st()
        out = []
        for p in paths or []:
            p = str(p)
            i = st.info(p)
            if not i.get("ok"):
                out.append({"ok": False, "path": p, "error": i.get("error")})
                continue
            i["url"] = self._studio_url(p, i)
            out.append(i)
        return out

    def _studio_url(self, p: str, i: dict) -> str:
        if not self._media:
            return ""
        if i["kind"] == "image" or i.get("gif"):
            return self._media.asset_url(p)
        from app.core.media_server import choose_mode
        from app.core.media_server import probe
        info = probe(self._st().ffprobe(), p)
        mode = choose_mode(Path(p).suffix.lower(), info)
        if mode == "direct" and (i["kind"] == "audio" or (info.get("height") or 0) <= 1080):
            return self._media.asset_url(p)
        return self._media.asset_url(self._studio_proxy(p, i))

    def _studio_proxy(self, p: str, i: dict) -> str:
        """Onizleme vekili: kisa GOP (hizli kaydirma), en fazla 1080p; ses AAC. Disa aktarim her zaman ASIL dosyadan."""
        import hashlib
        import subprocess
        from app.core.studio import CACHE, NO_WINDOW
        st = os.stat(p)
        key = hashlib.sha1(f"{os.path.abspath(p)}|{st.st_size}|{int(st.st_mtime)}".encode()).hexdigest()[:16]
        out = CACHE / "proxy" / f"{key}{'.m4a' if i['kind'] == 'audio' else '.mp4'}"
        if out.is_file():
            return str(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        ff = self._media.ffmpeg()
        enc = self._st().encoder()
        if i["kind"] == "audio":
            args = ["-i", p, "-vn", "-c:a", "aac", "-b:a", "192k"]
        else:
            max_w = 1280 if (i.get("height") or 0) > 1440 else 1920
            v = (["-c:v", "h264_nvenc", "-preset", "p3", "-cq", "24", "-g", "15", "-bf", "0"] if enc == "h264_nvenc"
                 else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "15", "-bf", "0"])
            args = ["-i", p, "-map", "0:v:0", "-map", "0:a:0?", "-vf", f"scale='min({max_w},iw)':-2,format=yuv420p", *v, "-c:a", "aac", "-b:a", "160k"]
        tmp = out.with_suffix(".part" + out.suffix)
        r = subprocess.run([ff, "-hide_banner", "-nostdin", "-y", "-loglevel", "error", *args, "-movflags", "+faststart", str(tmp)],
                           capture_output=True, timeout=7200, creationflags=NO_WINDOW)
        if r.returncode:
            log.warning("Studio vekil olusmadi: %s", r.stderr[-400:])
            return p
        os.replace(tmp, out)
        return str(out)

    def studio_peaks(self, path: str) -> dict[str, Any]:
        return self._st().peaks(str(path))

    def studio_thumbs(self, path: str, count: int = 12) -> dict[str, Any]:
        return self._st().thumbs(str(path), int(count))

    def studio_beats(self, path: str) -> dict[str, Any]:
        return self._st().beats(str(path))

    def studio_silences(self, path: str, start: float, dur: float, db: float = -35, min_len: float = 0.45) -> list:
        return self._st().silences(str(path), float(start), float(dur), float(db), float(min_len))

    def studio_freezes(self, path: str, start: float, dur: float, min_len: float = 1.0) -> list:
        return self._st().freezes(str(path), float(start), float(dur), float(min_len))

    def studio_scenes(self, path: str, start: float, dur: float, thr: float = 0.35) -> list:
        return self._st().scenes(str(path), float(start), float(dur), float(thr))

    def studio_ass(self, project: dict) -> str:
        return self._st().ass(project or {})

    # ---- proje
    def studio_new(self) -> dict[str, Any]:
        from app.core import studio
        return studio.new_project()

    def studio_save(self, project: dict, path: str = "") -> dict[str, Any]:
        from app.core import studio
        safe = re.sub(r'[<>:"/\\|?*]+', "_", str(project.get("name") or "Proje")).strip() or "Proje"
        pdir = studio.home_dir() / "Projeler"
        want = str(pdir / f"{safe}{studio.PROJECT_EXT}")
        old = ""
        if not path:
            path = want
        elif (os.path.normcase(os.path.dirname(os.path.abspath(path))) == os.path.normcase(str(pdir))
              and os.path.normcase(os.path.abspath(path)) != os.path.normcase(want)):
            # Projeler klasorundeki proje yeniden adlandirildi: dosya da yeni adi alsin
            if not os.path.exists(want):
                old, path = path, want
        p = studio.save_project(path, project)
        if old and os.path.isfile(old):
            try:
                os.remove(old)
                self._studio_saved.pop(old, None)
                self._studio_recent_drop(old)
            except OSError:
                pass
        self._studio_saved[p] = os.path.getmtime(p)
        self._studio_current(p)
        self._studio_recent_add(p, project.get("name", ""))
        return {"ok": True, "path": p}

    def studio_open(self, path: str) -> dict[str, Any]:
        from app.core import studio
        try:
            pr = studio.load_project(str(path))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}
        self._studio_saved[str(path)] = os.path.getmtime(path)
        self._studio_recent_add(str(path), pr.get("name", ""))
        self._studio_current(str(path))
        for a in (pr.get("assets") or {}).values():   # onizleme adresleri her acilista yeniden (sunucu anahtari degisir)
            if os.path.isfile(a.get("path", "")):
                a["url"] = self._studio_url(a["path"], a)
                a.pop("missing", None)
            else:
                a["missing"] = True
        return {"ok": True, "path": str(path), "project": pr}

    def studio_changed(self, path: str) -> bool:
        """MCP / disaridan duzenleme: dosya bizim son kaydimizdan sonra degisti mi?"""
        try:
            m = os.path.getmtime(path)
        except OSError:
            return False
        last = self._studio_saved.get(str(path))
        if last is None or m > last + 0.01:
            self._studio_saved[str(path)] = m
            return last is not None
        return False

    def _studio_current(self, path: str) -> None:
        """MCP sunucusu 'acik proje' olarak bunu kullanir."""
        from app.core.studio import CACHE
        try:
            (CACHE / "current.json").write_text(json.dumps({"path": path, "by": "studio", "t": time.time()}), "utf-8")
        except OSError:
            pass

    def studio_current(self) -> str:
        """MCP yeni proje actiysa Studio ona gecer."""
        from app.core.studio import CACHE
        try:
            d = json.loads((CACHE / "current.json").read_text("utf-8"))
        except (OSError, ValueError):
            return ""
        return d.get("path", "") if d.get("by") == "mcp" else ""

    def _studio_recent_add(self, path: str, name: str) -> None:
        from app.core.studio import CACHE
        f = CACHE / "recent.json"
        try:
            items = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            items = []
        key = os.path.normcase(os.path.abspath(path))
        items = [i for i in items if os.path.normcase(os.path.abspath(i.get("path", ""))) != key]
        items.insert(0, {"path": path, "name": name, "t": time.time()})
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(json.dumps(items[:20], ensure_ascii=False), "utf-8")

    def studio_reveal(self, path: str) -> bool:
        """Dosyayi Gezgin'de secili goster."""
        if not os.path.exists(str(path)):
            return False
        if os.name == "nt":
            import subprocess
            subprocess.Popen(["explorer", "/select,", os.path.normpath(str(path))])
        return True

    def _studio_recent_drop(self, path: str) -> None:
        from app.core.studio import CACHE
        f = CACHE / "recent.json"
        try:
            items = json.loads(f.read_text("utf-8"))
        except (OSError, ValueError):
            return
        key = os.path.normcase(os.path.abspath(path))
        f.write_text(json.dumps([i for i in items if os.path.normcase(os.path.abspath(i.get("path", ""))) != key],
                                ensure_ascii=False), "utf-8")

    def studio_recent(self) -> list[dict[str, Any]]:
        from app.core.studio import CACHE
        try:
            items = json.loads((CACHE / "recent.json").read_text("utf-8"))
        except (OSError, ValueError):
            return []
        return [i for i in items if os.path.isfile(i.get("path", ""))]

    def _studio_dialog(self, kind: str, types: tuple = (), name: str = "", folder: str = "") -> list[str]:
        import webview
        w = self._studio_win or (webview.windows[0] if webview.windows else None)
        if not w:
            return []
        if kind == "save":
            r = w.create_file_dialog(webview.SAVE_DIALOG, directory=folder, save_filename=name, file_types=types)
            return [r] if isinstance(r, str) else list(r or [])
        r = w.create_file_dialog(webview.OPEN_DIALOG, directory=folder, allow_multiple=kind == "multi", file_types=types)
        return list(r or [])

    def studio_pick_media(self) -> list[str]:
        return self._studio_dialog("multi", ("Medya (*.mp4;*.mkv;*.mov;*.webm;*.avi;*.mp3;*.wav;*.flac;*.ogg;*.m4a;*.png;*.jpg;*.jpeg;*.webp;*.gif)",
                                             "Tüm dosyalar (*.*)"))

    def studio_pick_project(self) -> str:
        from app.core import studio
        r = self._studio_dialog("open", ("Kami Studio projesi (*.kstudio)",), folder=str(studio.home_dir() / "Projeler"))
        return r[0] if r else ""

    def studio_pick_save(self, name: str, ext: str = ".mp4") -> str:
        from app.core import studio
        safe = re.sub(r'[<>:"/\\|?*]+', "_", str(name or "Video")).strip() or "Video"
        folder = studio.home_dir() / ("Çıktılar" if ext != studio.PROJECT_EXT else "Projeler")
        types = ("MP4 video (*.mp4)",) if ext == ".mp4" else ("Kami Studio projesi (*.kstudio)",)
        r = self._studio_dialog("save", types, name=safe + ext, folder=str(folder))
        if not r:
            return ""
        p = r[0]
        return p if p.lower().endswith(ext) else p + ext

    # ---- disa aktarim
    def studio_export(self, project: dict, out: str, opts: dict | None = None) -> dict[str, Any]:
        from app.core import studio
        if not self._media or not self._media.ffmpeg():
            return {"ok": False, "error": "no_ffmpeg"}
        o = dict(opts or {})
        pre = studio.DELIVER.get(str(o.get("preset", "")))
        if pre:
            o = {**{k: v for k, v in pre.items() if k != "name"}, **o}
        return {"ok": True, "job": self._st().export(project, str(out), o)}

    def studio_pick_save_ext(self, name: str, ext: str) -> str:
        from app.core import studio
        ext = ext if ext.startswith(".") else "." + ext
        safe = re.sub(r'[<>:"/\\|?*]+', "_", str(name or "Video")).strip() or "Video"
        label = {".mp4": "MP4 video", ".mov": "QuickTime (ProRes)", ".webm": "WebM", ".gif": "GIF", ".mp3": "MP3 ses", ".wav": "WAV ses", ".png": "PNG"}.get(ext, ext)
        r = self._studio_dialog("save", (f"{label} (*{ext})",), name=safe + ext, folder=str(studio.home_dir() / "Çıktılar"))
        if not r:
            return ""
        p = r[0]
        return p if p.lower().endswith(ext) else p + ext

    def studio_job(self, jid: str) -> dict[str, Any]:
        return self._st().job(str(jid))

    def studio_cancel(self, jid: str) -> None:
        self._st().cancel(str(jid))

    # ---- sablonlar
    def studio_template_save(self, name: str, kf: list) -> list:
        from app.core import studio
        return studio.save_template(str(name or "Şablon"), list(kf or []))

    def studio_template_delete(self, tid: str) -> list:
        from app.core import studio
        return studio.delete_template(str(tid))

    # ---- ses / meme kutuphanesi
    def studio_library(self, kind: str = "Sesler") -> list[dict[str, Any]]:
        from app.core import studio
        kind = "Memeler" if kind == "Memeler" else "Sesler"
        root = studio.home_dir() / kind
        out = []
        for f in sorted(root.rglob("*"), key=lambda q: q.stat().st_mtime if q.is_file() else 0, reverse=True):
            if f.is_file() and studio.asset_kind(str(f)):
                out.append({"path": str(f), "name": f.stem, "kind": studio.asset_kind(str(f)), "folder": f.parent.name,
                            "url": self._media.asset_url(str(f)) if self._media else ""})
            if len(out) >= 400:
                break
        return out

    def studio_open_folder(self, kind: str = "") -> bool:
        from app.core import studio
        d = studio.home_dir() / kind if kind else studio.home_dir()
        try:
            os.startfile(str(d))   # type: ignore[attr-defined]
            return True
        except Exception:
            return False

    def studio_myinstants(self, q: str) -> list[dict[str, Any]]:
        """Myinstants arama (resmi API yok; arama sayfasindaki ses dugmeleri)."""
        url = "https://www.myinstants.com/en/search/?name=" + urllib.parse.quote(str(q or "")[:80])
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            html = urllib.request.urlopen(req, timeout=15).read().decode("utf-8", "replace")
        except Exception as exc:
            return [{"error": str(exc)[:120]}]
        out, seen = [], set()
        for m in re.finditer(r"play\('(/media/sounds/[^']+\.mp3)'[^>]*>.*?</button>\s*(?:</div>\s*)?<a[^>]*class=\"instant-link[^\"]*\"[^>]*>([^<]+)</a>", html, re.S):
            u = "https://www.myinstants.com" + m.group(1)
            if u not in seen:
                seen.add(u)
                out.append({"name": re.sub(r"\s+", " ", m.group(2)).strip()[:80], "url": u})
        if not out:   # duzen degistiyse: yalniz ses adresleri
            for m in re.finditer(r"(/media/sounds/[^'\"]+\.mp3)", html):
                u = "https://www.myinstants.com" + m.group(1)
                if u not in seen:
                    seen.add(u)
                    out.append({"name": urllib.parse.unquote(Path(m.group(1)).stem).replace("-", " ").replace("_", " "), "url": u})
        return out[:60]

    def studio_fetch_sound(self, url: str, name: str = "", folder: str = "İndirilen") -> dict[str, Any]:
        """Internetten secilen sesi Sesler\\<klasor> altina indir (kutuphanede kalir)."""
        from app.core import studio
        url = str(url or "")
        if not url.startswith("https://"):
            return {"ok": False, "error": "bad_url"}
        ext = Path(urllib.parse.urlsplit(url).path).suffix.lower() or ".mp3"
        if ext not in studio.AUDIO_EXT | studio.IMAGE_EXT | studio.VIDEO_EXT:
            ext = ".mp3"
        safe = re.sub(r'[<>:"/\\|?*]+', "_", str(name or Path(urllib.parse.urlsplit(url).path).stem))[:80].strip() or "ses"
        d = studio.home_dir() / ("Memeler" if ext in studio.IMAGE_EXT else "Sesler") / folder
        d.mkdir(parents=True, exist_ok=True)
        dst = d / (safe + ext)
        if not dst.is_file():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://www.myinstants.com/"})
                data = urllib.request.urlopen(req, timeout=30).read(40 * 1024 * 1024)
            except Exception as exc:
                return {"ok": False, "error": str(exc)[:120]}
            dst.write_bytes(data)
        i = self._st().info(str(dst))
        if i.get("ok"):
            i["url"] = self._studio_url(str(dst), i)
        return {"ok": True, "path": str(dst), "info": i}

    def _fs_store(self):
        from app import paths
        from app.core.debrid import TokenStore
        return TokenStore(paths.DATA_DIR / "freesound_key.bin")

    def studio_freesound_key(self, key: str) -> dict[str, Any]:
        key = str(key or "").strip()
        if key:
            self._fs_store().save(key)
        else:
            self._fs_store().clear()
        return {"ok": True}

    def studio_freesound(self, q: str) -> list[dict[str, Any]]:
        """Freesound arama (kullanicinin API anahtari, DPAPI). Onizleme MP3'leri anahtarsiz indirilebilir."""
        key = self._fs_store().load()
        if not key:
            return [{"error": "no_key"}]
        url = ("https://freesound.org/apiv2/search/text/?" + urllib.parse.urlencode(
            {"query": str(q or "")[:80], "fields": "id,name,duration,previews,username,license", "page_size": 40, "token": key}))
        try:
            data = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=15).read())
        except Exception as exc:
            return [{"error": str(exc)[:120]}]
        return [{"name": r.get("name", "")[:80], "url": (r.get("previews") or {}).get("preview-hq-mp3", ""), "dur": r.get("duration"),
                 "by": r.get("username", ""), "license": r.get("license", "")} for r in data.get("results") or []]

    # ---- eklenti paketleri (GitHub / URL'den JSON)
    def _studio_packs(self) -> list[dict[str, Any]]:
        from app.core.studio import CACHE
        out = []
        for f in sorted((CACHE / "packs").glob("*.json")):
            try:
                d = json.loads(f.read_text("utf-8"))
                d["_id"] = f.stem
                out.append(d)
            except (OSError, ValueError):
                continue
        return out

    def studio_pack_add(self, url: str) -> dict[str, Any]:
        """Paket: {name, fx:{id:{name,pack,ff,css,ov}}, sounds:[{name,url}], zoom:[{name,kf}]}. github.com adresi raw'a cevrilir."""
        from app.core import studio
        url = str(url or "").strip()
        m = re.match(r"https://github\.com/([^/]+)/([^/]+)/blob/(.+)", url)
        if m:
            url = f"https://raw.githubusercontent.com/{m.group(1)}/{m.group(2)}/{m.group(3)}"
        elif re.match(r"https://github\.com/[^/]+/[^/]+/?$", url):
            url = url.rstrip("/").replace("github.com", "raw.githubusercontent.com") + "/HEAD/kami-studio-pack.json"
        if not url.startswith("https://"):
            return {"ok": False, "error": "bad_url"}
        try:
            d = json.loads(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=20).read(2_000_000))
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:160]}
        if not isinstance(d, dict) or not d.get("name"):
            return {"ok": False, "error": "Paket değil (name alanı yok)"}
        bad = re.compile(r"\b(a?movie|sendcmd|zmq|file|textfile|filename|lut3d|haldclut)\b", re.I)
        fx = {}
        for k, v in (d.get("fx") or {}).items():
            if isinstance(v, dict) and isinstance(v.get("ff"), str) and not bad.search(v["ff"]) and re.fullmatch(r"[\w-]{1,32}", k):
                fx["p_" + k] = {"name": str(v.get("name", k))[:40], "pack": str(v.get("pack") or d["name"])[:30], "ff": v["ff"][:800],
                                "css": str(v.get("css", ""))[:200], "ov": [str(o) for o in v.get("ov", [])][:8]}
        pack = {"name": str(d["name"])[:40], "src": url, "fx": fx,
                "sounds": [{"name": str(s.get("name", ""))[:80], "url": s["url"]} for s in d.get("sounds") or []
                           if isinstance(s, dict) and str(s.get("url", "")).startswith("https://")][:300],
                "zoom": [{"id": "p" + str(i), "name": str(z.get("name", ""))[:40], "kf": z.get("kf", [])[:64]}
                         for i, z in enumerate(d.get("zoom") or []) if isinstance(z, dict)][:50]}
        (studio.CACHE / "packs").mkdir(parents=True, exist_ok=True)
        pid = re.sub(r"[^\w-]+", "_", pack["name"].lower())[:40]
        (studio.CACHE / "packs" / f"{pid}.json").write_text(json.dumps(pack, ensure_ascii=False, indent=1), "utf-8")
        studio.FX.update(fx)   # disa aktarim da tanisin
        return {"ok": True, "name": pack["name"], "fx": len(fx), "sounds": len(pack["sounds"])}

    def studio_pack_remove(self, pid: str) -> bool:
        from app.core.studio import CACHE
        try:
            (CACHE / "packs" / f"{re.sub(r'[^\w-]+', '', str(pid))}.json").unlink()
            return True
        except OSError:
            return False

    def studio_pack_sounds(self) -> list[dict[str, Any]]:
        return [{**s, "pack": p.get("name")} for p in self._studio_packs() for s in p.get("sounds") or []]

    def _studio_load_packs(self) -> None:
        from app.core import studio
        for p in self._studio_packs():
            studio.FX.update(p.get("fx") or {})

    # ---- yapay zeka: kelime zamanli altyazi (Whisper), dikey cerceve (yuz takibi)
    def studio_ai(self, kind: str, path: str, start: float, dur: float, opts: dict | None = None) -> dict[str, Any]:
        """captions | reframe. Arka planda; durum studio_job ile."""
        from app.core import aitools
        tool = {"captions": "whisper", "reframe": "iopaint"}.get(str(kind))
        if not tool:
            return {"ok": False, "error": "bad_kind"}
        if not aitools.installed(tool):
            return {"ok": False, "error": "need_tool", "tool": tool}
        st = self._st()
        jid = "a" + str(int(time.time() * 1000))
        job = {"id": jid, "state": "running", "p": 0.0, "error": "", "cancel": threading.Event(), "started": time.time()}
        st.jobs[jid] = job
        o = dict(opts or {})

        def run() -> None:
            import tempfile
            fd, out = tempfile.mkstemp(prefix="kstudio_ai_", suffix=".json")
            os.close(fd)
            try:
                if kind == "captions":
                    args = ["app.tools.studio_words_run", str(path), out, f"{float(start):.3f}", f"{float(dur):.3f}", o.get("lang", "auto"),
                            self._manager.settings.get("whisper_model") or "large-v3-turbo", aitools.models_dir("whisper"), self._media.ffmpeg()]
                    res = aitools._run_json(args, lambda m: job.update(p=float(m.get("p", job["p"]))), job["cancel"], "whisper")
                else:
                    args = ["app.tools.studio_face_run", str(path), out, f"{float(start):.3f}", f"{float(dur):.3f}", str(o.get("ratio", 9 / 16))]
                    res = aitools._run_once(args, lambda m: job.update(p=float(m.get("p", job["p"]))), job["cancel"], "iopaint", {})
                if "done" in res:
                    job.update(state="done", p=1.0, result=json.loads(Path(out).read_text("utf-8")))
                else:
                    job.update(state="error", error=str(res.get("error", ""))[:300])
            except Exception as exc:
                log.exception("Studio yapay zeka")
                job.update(state="error", error=str(exc)[:200])
            finally:
                try:
                    os.remove(out)
                except OSError:
                    pass
        threading.Thread(target=run, daemon=True, name=f"studio-{kind}").start()
        return {"ok": True, "job": jid}

    def studio_ai_install(self, tool: str) -> dict[str, Any]:
        from app.core import aitools
        tool = "whisper" if tool == "whisper" else "iopaint"
        st = self._st()
        jid = "i" + str(int(time.time() * 1000))
        job = {"id": jid, "state": "running", "p": 0.0, "error": "", "cancel": threading.Event(), "line": ""}
        st.jobs[jid] = job

        def run() -> None:
            ok = aitools.install(tool, lambda s: job.update(line=str(s)[-160:]))
            job.update(state="done" if ok else "error", p=1.0)
        threading.Thread(target=run, daemon=True).start()
        return {"ok": True, "job": jid}

    def studio_mcp_info(self) -> dict[str, Any]:
        """Claude baglantisi: claude_desktop_config.json'a eklenecek komut."""
        import sys
        from app import paths
        if paths.FROZEN:
            cmd = {"command": sys.executable, "args": ["--studio-mcp"]}
        else:
            cmd = {"command": str(Path(sys.executable)), "args": ["-m", "app.core.studio_mcp"], "cwd": str(paths.ROOT)}
        cfg = Path(os.environ.get("APPDATA", "")) / "Claude" / "claude_desktop_config.json"
        return {"server": cmd, "config": str(cfg), "installed": self._mcp_installed(cfg)}

    def _mcp_installed(self, cfg: Path) -> bool:
        try:
            return "kami-studio" in (json.loads(cfg.read_text("utf-8")).get("mcpServers") or {})
        except (OSError, ValueError):
            return False

    def studio_mcp_install(self) -> dict[str, Any]:
        """Claude masaustu yapilandirmasina kami-studio sunucusunu ekler (diger sunuculara dokunmaz)."""
        info = self.studio_mcp_info()
        cfg = Path(info["config"])
        try:
            data = json.loads(cfg.read_text("utf-8")) if cfg.is_file() else {}
        except ValueError:
            return {"ok": False, "error": "Yapılandırma dosyası bozuk, elle düzelt"}
        data.setdefault("mcpServers", {})["kami-studio"] = info["server"]
        cfg.parent.mkdir(parents=True, exist_ok=True)
        if cfg.is_file():
            cfg.with_suffix(".json.bak").write_text(cfg.read_text("utf-8"), "utf-8")
        cfg.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")
        return {"ok": True, "config": str(cfg)}


    # =================================================================================================================
    # Pro: fontlar, LUT, sablonlar, SFX, stok, Gemini/Flow, arka plan silme, Lottie
    def studio_catalog_fonts(self) -> dict[str, Any]:
        """Tum fontlar: {aile: url} (JASSUB ihtiyac olunca indirir)."""
        from app.core import studio
        idx = studio.fonts_index()
        m = {}
        if self._media:
            for fam, path in idx.items():
                try:
                    m[fam] = self._media.asset_url(path)
                except Exception:
                    pass
        return {"fonts": sorted(idx, key=str.lower), "map": m, "google": list(studio.GOOGLE_FONTS)}

    def studio_fonts_download(self) -> dict[str, Any]:
        from app.core import studio
        got = studio.download_google_fonts()
        return {"ok": bool(got), "fonts": got}

    def studio_luts(self) -> list[dict[str, Any]]:
        from app.core import studio
        return [{"name": f.name, "title": f.stem} for f in sorted(studio.lut_dir().glob("*.cube"), key=lambda q: q.name.lower())]

    def studio_lut_read(self, name: str) -> dict[str, Any]:
        from app.core import studio
        f = studio.lut_dir() / Path(str(name)).name
        n, data = studio.parse_cube(f)
        return {"n": n, "data": [round(v, 4) for t in data for v in t]}

    def studio_lut_import(self) -> list[str]:
        import shutil
        from app.core import studio
        got = []
        for p in self._studio_dialog("multi", ("LUT (*.cube)",)):
            try:
                studio.parse_cube(Path(p))
                shutil.copy2(p, studio.lut_dir() / Path(p).name)
                got.append(Path(p).name)
            except Exception as exc:
                log.warning("LUT alinamadi %s: %s", p, exc)
        return got

    def studio_template(self, project: dict, tid: str, t: float, clip_id: str = "") -> dict[str, Any]:
        from app.core import studio
        try:
            added = studio.apply_template(project, str(tid), float(t), self._media.ffmpeg() if self._media else "", str(clip_id or ""),
                                          info=self._st().info)
        except (KeyError, ValueError) as exc:
            return {"ok": False, "error": str(exc)}
        for a in project.get("assets", {}).values():
            if not a.get("url") and os.path.isfile(a.get("path", "")):
                a["url"] = self._studio_url(a["path"], a)
        return {"ok": True, "project": project, "added": added}

    def studio_sfx(self) -> list[dict[str, Any]]:
        from app.core import studio
        got = studio.ensure_sfx(self._media.ffmpeg() if self._media else "")
        return [{"key": k, "name": studio.SFX[k][1], "path": p, "url": self._media.asset_url(p) if self._media else "", "kind": "audio"}
                for k, p in got.items()]

    # ---- anahtarlar (DPAPI)
    _KEYS = ("pexels", "pixabay", "unsplash", "gemini")

    def _key_store(self, name: str):
        from app import paths
        from app.core.debrid import TokenStore
        return TokenStore(paths.DATA_DIR / f"studio_{name}_key.bin")

    def studio_keys_status(self) -> dict[str, bool]:
        return {k: bool(self._key_store(k).load()) for k in self._KEYS}

    def studio_key_set(self, name: str, key: str) -> dict[str, Any]:
        if name not in self._KEYS:
            return {"ok": False}
        key = str(key or "").strip()
        if key:
            self._key_store(name).save(key)
        else:
            self._key_store(name).clear()
        return {"ok": True, "keys": self.studio_keys_status()}

    def _get_json(self, url: str, headers: dict | None = None, timeout: float = 20) -> Any:
        req = urllib.request.Request(url, headers={"User-Agent": UA, **(headers or {})})
        return json.loads(urllib.request.urlopen(req, timeout=timeout).read())

    # ---- stok arama
    def studio_stock(self, source: str, q: str, kind: str = "photo", page: int = 1) -> dict[str, Any]:
        """Kaynaklar: pexels, pixabay, unsplash (anahtar ister), openverse (anahtarsiz). Ortak bicim doner."""
        q = str(q or "").strip()[:100] or "nature"
        page = max(1, int(page or 1))
        try:
            if source == "openverse":
                ep = "audio" if kind == "audio" else "images"
                d = self._get_json(f"https://api.openverse.org/v1/{ep}/?" + urllib.parse.urlencode({"q": q, "page": page, "page_size": 20}),
                                   {"User-Agent": "Kami/1.10 (+https://github.com/murasakimono/kami)"})
                return {"items": [{"id": r["id"], "thumb": r.get("thumbnail") or r.get("url"), "url": r.get("url"), "w": r.get("width"),
                                   "h": r.get("height"), "by": r.get("creator") or "", "page": r.get("foreign_landing_url"),
                                   "license": f"CC {str(r.get('license', '')).upper()} {r.get('license_version', '')}".strip(),
                                   "kind": "audio" if kind == "audio" else "photo", "dur": (r.get("duration") or 0) / 1000,
                                   "name": r.get("title") or q} for r in d.get("results", [])]}
            key = self._key_store(source).load()
            if not key:
                return {"error": "no_key"}
            if source == "pexels":
                if kind == "video":
                    d = self._get_json("https://api.pexels.com/videos/search?" + urllib.parse.urlencode({"query": q, "page": page, "per_page": 30}),
                                       {"Authorization": key})
                    items = []
                    for v in d.get("videos", []):
                        files = sorted([f for f in v.get("video_files", []) if f.get("file_type") == "video/mp4" and f.get("width")],
                                       key=lambda f: f["width"])
                        best = next((f for f in files if f["width"] >= 1920), files[-1] if files else None)
                        prev = next((f for f in files if f["width"] >= 640), files[0] if files else None)
                        if best:
                            items.append({"id": v["id"], "thumb": v.get("image"), "preview": prev["link"] if prev else "", "url": best["link"],
                                          "w": best["width"], "h": best["height"], "dur": v.get("duration"), "by": (v.get("user") or {}).get("name", ""),
                                          "page": v.get("url"), "license": "Pexels", "kind": "video", "name": f"pexels-{v['id']}"})
                    return {"items": items}
                d = self._get_json("https://api.pexels.com/v1/search?" + urllib.parse.urlencode({"query": q, "page": page, "per_page": 30}),
                                   {"Authorization": key})
                return {"items": [{"id": r["id"], "thumb": r["src"]["medium"], "url": r["src"]["original"], "w": r["width"], "h": r["height"],
                                   "by": r.get("photographer", ""), "page": r.get("url"), "license": "Pexels", "kind": "photo",
                                   "name": (r.get("alt") or f"pexels-{r['id']}")[:60]} for r in d.get("photos", [])]}
            if source == "pixabay":
                base = "https://pixabay.com/api/videos/?" if kind == "video" else "https://pixabay.com/api/?"
                d = self._get_json(base + urllib.parse.urlencode({"key": key, "q": q, "page": page, "per_page": 30, "safesearch": "true"}))
                items = []
                for r in d.get("hits", []):
                    if kind == "video":
                        vs = r.get("videos") or {}
                        best = vs.get("large") if (vs.get("large") or {}).get("url") else vs.get("medium") or {}
                        prev = vs.get("small") or vs.get("tiny") or {}
                        items.append({"id": r["id"], "thumb": prev.get("thumbnail") or best.get("thumbnail") or "", "preview": prev.get("url", ""),
                                      "url": best.get("url", ""), "w": best.get("width"), "h": best.get("height"), "dur": r.get("duration"),
                                      "by": r.get("user", ""), "page": r.get("pageURL"), "license": "Pixabay", "kind": "video", "name": f"pixabay-{r['id']}"})
                    else:
                        items.append({"id": r["id"], "thumb": r.get("webformatURL"), "url": r.get("largeImageURL") or r.get("webformatURL"),
                                      "w": r.get("imageWidth"), "h": r.get("imageHeight"), "by": r.get("user", ""), "page": r.get("pageURL"),
                                      "license": "Pixabay", "kind": "photo", "name": (r.get("tags") or f"pixabay-{r['id']}")[:60]})
                return {"items": items}
            if source == "unsplash":
                d = self._get_json("https://api.unsplash.com/search/photos?" + urllib.parse.urlencode({"query": q, "page": page, "per_page": 30}),
                                   {"Authorization": f"Client-ID {key}", "Accept-Version": "v1"})
                return {"items": [{"id": r["id"], "thumb": r["urls"]["small"], "url": r["urls"]["full"], "w": r["width"], "h": r["height"],
                                   "by": (r.get("user") or {}).get("name", ""), "page": (r.get("links") or {}).get("html"),
                                   "dl": (r.get("links") or {}).get("download_location"), "license": "Unsplash", "kind": "photo",
                                   "name": (r.get("alt_description") or f"unsplash-{r['id']}")[:60]} for r in d.get("results", [])]}
        except Exception as exc:
            return {"error": str(exc)[:200]}
        return {"error": "bad_source"}

    def studio_stock_get(self, source: str, item: dict) -> dict[str, Any]:
        """Secilen stok ogesini Videolar\\Kami Studio\\Stok\\<kaynak> altina indirir, ice aktarir; atif bilgisini saklar."""
        from app.core import studio
        url = str(item.get("url") or "")
        if not url.startswith("https://"):
            return {"ok": False, "error": "bad_url"}
        d = studio.home_dir() / "Stok" / str(source).capitalize()
        d.mkdir(parents=True, exist_ok=True)
        ext = Path(urllib.parse.urlsplit(url).path).suffix.lower()
        if ext not in studio.IMAGE_EXT | studio.VIDEO_EXT | studio.AUDIO_EXT:
            ext = ".mp4" if item.get("kind") == "video" else ".mp3" if item.get("kind") == "audio" else ".jpg"
        safe = re.sub(r'[<>:"/\\|?*\s]+', "_", f"{item.get('name', 'stok')}_{item.get('id', '')}")[:90]
        dst = d / (safe + ext)
        try:
            if source == "unsplash" and item.get("dl"):   # Unsplash kurali: indirme sayaci
                key = self._key_store("unsplash").load()
                try:
                    self._get_json(str(item["dl"]), {"Authorization": f"Client-ID {key}"})
                except Exception:
                    pass
            if not dst.is_file():
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=120) as r, open(dst.with_suffix(dst.suffix + ".part"), "wb") as f:
                    while True:
                        b = r.read(1 << 20)
                        if not b:
                            break
                        f.write(b)
                os.replace(dst.with_suffix(dst.suffix + ".part"), dst)
            credits = studio.home_dir() / "Stok" / "atiflar.txt"
            with open(credits, "a", encoding="utf-8") as f:
                f.write(f"{dst.name}\t{item.get('by', '')}\t{item.get('license', '')}\t{item.get('page', '')}\n")
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:200]}
        i = self._st().info(str(dst))
        if i.get("ok"):
            i["url"] = self._studio_url(str(dst), i)
            i["credit"] = f"{item.get('by', '')} / {item.get('license', '')}"
        return {"ok": bool(i.get("ok")), "info": i, "path": str(dst)}

    # ---- Gemini (gorsel / video) + Flow
    GEMINI = "https://generativelanguage.googleapis.com/v1beta"

    def studio_gemini_models(self) -> dict[str, Any]:
        key = self._key_store("gemini").load()
        if not key:
            return {"error": "no_key"}
        try:
            d = self._get_json(f"{self.GEMINI}/models?pageSize=200", {"x-goog-api-key": key})
        except Exception as exc:
            return {"error": str(exc)[:200]}
        img, vid = [], []
        for m in d.get("models", []):
            name = m.get("name", "").replace("models/", "")
            meth = m.get("supportedGenerationMethods") or []
            if "image" in name and "generateContent" in meth:
                img.append({"id": name, "name": m.get("displayName") or name})
            elif ("veo" in name or "omni" in name) and ("predictLongRunning" in meth or "generateVideos" in meth or not meth):
                vid.append({"id": name, "name": m.get("displayName") or name})
        return {"image": img, "video": vid}

    def studio_gemini(self, kind: str, prompt: str, model: str, aspect: str = "16:9", ref: str = "") -> dict[str, Any]:
        """Arka planda uretir; durum studio_job. Sonuc Videolar\\Kami Studio\\Yapay Zeka altina kaydedilir."""
        import base64
        key = self._key_store("gemini").load()
        if not key:
            return {"ok": False, "error": "no_key"}
        st = self._st()
        jid = "g" + str(int(time.time() * 1000))
        job = {"id": jid, "state": "running", "p": 0.05, "error": "", "cancel": threading.Event(), "line": "gönderiliyor"}
        st.jobs[jid] = job
        from app.core import studio
        outdir = studio.home_dir() / "Yapay Zeka"
        outdir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d-%H%M%S")

        def post(url: str, body: dict) -> dict:
            req = urllib.request.Request(url, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": key, "User-Agent": UA})
            try:
                return json.loads(urllib.request.urlopen(req, timeout=180).read())
            except urllib.error.HTTPError as e:
                raise RuntimeError(e.read().decode("utf-8", "replace")[:400]) from e

        def run() -> None:
            try:
                if kind == "image":
                    parts = [{"text": prompt}]
                    if ref and os.path.isfile(ref):
                        mime = "image/png" if ref.lower().endswith(".png") else "image/jpeg"
                        parts.insert(0, {"inline_data": {"mime_type": mime, "data": base64.b64encode(Path(ref).read_bytes()).decode()}})
                    d = post(f"{self.GEMINI}/models/{model}:generateContent",
                             {"contents": [{"parts": parts}], "generationConfig": {"responseModalities": ["IMAGE"], "imageConfig": {"aspectRatio": aspect}}})
                    saved = []
                    for cand in d.get("candidates", []):
                        for prt in (cand.get("content") or {}).get("parts", []):
                            inl = prt.get("inlineData") or prt.get("inline_data")
                            if inl and inl.get("data"):
                                f = outdir / f"gemini-{stamp}-{len(saved) + 1}.png"
                                f.write_bytes(base64.b64decode(inl["data"]))
                                saved.append(str(f))
                    if not saved:
                        raise RuntimeError("görsel dönmedi: " + json.dumps(d)[:300])
                    job.update(state="done", p=1.0, result={"paths": saved})
                else:
                    d = post(f"{self.GEMINI}/models/{model}:predictLongRunning",
                             {"instances": [{"prompt": prompt}], "parameters": {"aspectRatio": aspect}})
                    op = d.get("name")
                    if not op:
                        raise RuntimeError(json.dumps(d)[:300])
                    t0 = time.time()
                    while not job["cancel"].is_set():
                        time.sleep(8)
                        o = self._get_json(f"{self.GEMINI}/{op}", {"x-goog-api-key": key})
                        job.update(p=min(0.95, 0.1 + (time.time() - t0) / 240), line="üretiliyor")
                        if o.get("done"):
                            if o.get("error"):
                                raise RuntimeError(str(o["error"].get("message", o["error"]))[:300])
                            resp = o.get("response") or {}
                            vids = ((resp.get("generateVideoResponse") or {}).get("generatedSamples") or resp.get("generatedVideos") or [])
                            saved = []
                            for i, v in enumerate(vids):
                                uri = ((v.get("video") or {}).get("uri"))
                                if uri:
                                    sep = "&" if "?" in uri else "?"
                                    data = urllib.request.urlopen(urllib.request.Request(f"{uri}{sep}key={key}", headers={"User-Agent": UA}), timeout=300).read()
                                    f = outdir / f"gemini-{stamp}-{i + 1}.mp4"
                                    f.write_bytes(data)
                                    saved.append(str(f))
                            if not saved:
                                raise RuntimeError("video dönmedi")
                            job.update(state="done", p=1.0, result={"paths": saved})
                            return
                    job.update(state="cancelled")
            except Exception as exc:
                log.warning("Gemini: %s", exc)
                job.update(state="error", error=str(exc)[:400])
        threading.Thread(target=run, daemon=True, name="studio-gemini").start()
        return {"ok": True, "job": jid}

    def studio_open_url(self, url: str) -> bool:
        url = str(url or "")
        if not url.startswith("https://"):
            return False
        try:
            os.startfile(url)   # type: ignore[attr-defined]
            return True
        except Exception:
            import webbrowser
            return webbrowser.open(url)

    def studio_downloads_since(self, since: float) -> list[dict[str, Any]]:
        """Indirilenler klasorune since'ten sonra dusen medya (Flow/Gemini'den indirdiklerin) - tek tikla ice aktarma icin."""
        from app.core import studio
        d = Path.home() / "Downloads"
        out = []
        try:
            for f in d.iterdir():
                if f.is_file() and studio.asset_kind(str(f)) and f.stat().st_mtime > float(since) and not f.name.endswith((".part", ".crdownload", ".tmp")):
                    out.append({"path": str(f), "name": f.name, "t": f.stat().st_mtime})
        except OSError:
            pass
        return sorted(out, key=lambda x: -x["t"])[:20]

    # ---- arka plan silme (video, kare kare BiRefNet) ve Lottie
    def studio_matte(self, path: str, start: float, dur: float, model: str = "birefnet-general") -> dict[str, Any]:
        from app.core import aitools
        if not aitools.installed("iopaint"):
            return {"ok": False, "error": "need_tool", "tool": "iopaint"}
        st = self._st()
        jid = "m" + str(int(time.time() * 1000))
        job = {"id": jid, "state": "running", "p": 0.0, "error": "", "cancel": threading.Event(), "started": time.time(), "line": ""}
        st.jobs[jid] = job
        from app.core import studio
        outdir = studio.home_dir() / "Arka plansız"
        outdir.mkdir(parents=True, exist_ok=True)
        out = outdir / f"{Path(path).stem}-{int(float(start))}-{int(float(dur))}s.webm"

        def run() -> None:
            try:   # eski kurulumlar: onnxruntime-gpu CUDA 13 surumu GPU'yu kullanamiyor -> bir kez duzelt
                env = Path(aitools.python_exe("iopaint")).resolve().parent.parent
                mark = env / ".kami_studio_matte2"
                if not mark.exists():
                    job.update(line="yapay zeka ortamı güncelleniyor (bir kez)")
                    if aitools.install("iopaint", lambda s: job.update(line=str(s)[-120:])):
                        mark.write_text("1")
            except Exception:
                log.exception("iopaint ortam duzeltme")
            args = ["app.tools.studio_matte_run", str(path), str(out), f"{float(start):.3f}", f"{float(dur):.3f}", str(model), self._media.ffmpeg()]

            def prog(m: dict) -> None:
                job.update(p=float(m.get("p", job["p"])), line=str(m.get("line", job.get("line", ""))))
            res = aitools._run_once(args, prog, job["cancel"], "iopaint", {})
            if "done" in res and out.is_file():
                i = st.info(str(out))
                i["alpha"] = True
                i["url"] = self._media.asset_url(str(out))
                job.update(state="done", p=1.0, result=i)
            else:
                job.update(state="error", error=str(res.get("error", "olmadı"))[:300])
        threading.Thread(target=run, daemon=True, name="studio-matte").start()
        return {"ok": True, "job": jid}

    def studio_lottie(self, src: str) -> dict[str, Any]:
        """Lottie (.json/.lottie dosyasi ya da LottieFiles adresi) -> seffaf WebM (VP9 alfa) ve ice aktarma bilgisi."""
        from app.core import lottie_conv, studio
        try:
            p = lottie_conv.fetch(str(src), studio.home_dir() / "Animasyonlar")
            out = lottie_conv.to_webm(p, self._media.ffmpeg())
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}
        i = self._st().info(str(out))
        i["alpha"] = True
        i["url"] = self._media.asset_url(str(out))
        return {"ok": True, "info": i}

    def studio_pick_lottie(self) -> str:
        r = self._studio_dialog("open", ("Lottie (*.json;*.lottie)",))
        return r[0] if r else ""

    def studio_frame_png(self, project: dict, t: float, out: str = "") -> dict[str, Any]:
        """Tam cozunurlukte tek kare (kapak/thumbnail)."""
        from app.core import studio
        if not out:
            safe = re.sub(r'[<>:"/\\|?*]+', "_", str(project.get("name", "kare")))
            out = str(studio.home_dir() / "Çıktılar" / f"{safe}-{int(float(t) * 1000)}.png")
        try:
            self._st().frame(project, float(t), out)
            return {"ok": True, "path": out}
        except Exception as exc:
            return {"ok": False, "error": str(exc)[:300]}

    # ---- Faz 8: Premiere Kurgu, Metin Montaj, Multi-Cam, Smart Cut & Broadcast Ses ----

    def studio_transcript_cuts(self, words: list[dict[str, Any]], keep_indices: list[int] | None = None,
                               total_dur: float = 0.0, captions: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        from app.core.studio_edit import remap_captions_for_cuts, transcript_to_cuts
        cuts = transcript_to_cuts(words or [], keep_indices, total_dur=float(total_dur or 0.0))
        remapped = remap_captions_for_cuts(captions or [], cuts) if captions else []
        return {"ok": True, "cuts": cuts, "captions": remapped}

    def studio_multicam_sync(self, paths: list[str]) -> dict[str, Any]:
        from app.core.studio_edit import multicam_sync
        ff = self._media.ffmpeg() if self._media else ""
        return multicam_sync(ff, [str(p) for p in (paths or [])])

    def studio_timeline_edit(self, clips: list[dict[str, Any]], mode: str, clip_id: str,
                             delta: float, edge: str = "out") -> dict[str, Any]:
        from app.core.studio_edit import apply_timeline_edit
        updated = apply_timeline_edit(clips or [], str(mode or "ripple"), str(clip_id), float(delta), str(edge or "out"))
        return {"ok": True, "clips": updated}

    def studio_jl_cut(self, clip: dict[str, Any], audio_lead: float = 0.0, audio_tail: float = 0.0) -> dict[str, Any]:
        from app.core.studio_edit import apply_jl_cut
        return {"ok": True, "clip": apply_jl_cut(clip or {}, float(audio_lead), float(audio_tail))}

    def studio_compound_create(self, clips: list[dict[str, Any]], clip_ids: list[str], name: str = "Bileşik Klip") -> dict[str, Any]:
        from app.core.studio_edit import create_compound_clip
        return create_compound_clip(clips or [], [str(x) for x in (clip_ids or [])], str(name or "Bileşik Klip"))

    def studio_compound_expand(self, clips: list[dict[str, Any]], compound_id: str) -> dict[str, Any]:
        from app.core.studio_edit import expand_compound_clip
        return {"ok": True, "clips": expand_compound_clip(clips or [], str(compound_id))}

    def studio_smart_cut(self, path: str, start: float, end: float, out_path: str = "") -> dict[str, Any]:
        from app.core.studio_edit import smart_cut
        ff = self._media.ffmpeg() if self._media else ""
        return smart_cut(ff, str(path or ""), float(start), float(end), str(out_path or ""))

    def studio_audio_enhance(self, path: str, out_path: str = "", strength: str = "medium") -> dict[str, Any]:
        from app.core.studio_audio import enhance_audio_file
        ff = self._media.ffmpeg() if self._media else ""
        return enhance_audio_file(ff, str(path or ""), str(out_path or ""), str(strength or "medium"))

    def studio_audio_duck(self, music_path: str, voice_path: str, out_path: str) -> dict[str, Any]:
        from app.core.studio_audio import duck_music_with_voice
        ff = self._media.ffmpeg() if self._media else ""
        return duck_music_with_voice(ff, str(music_path or ""), str(voice_path or ""), str(out_path or ""))

    def studio_bilingual_subs(self, segments: list[dict[str, Any]], fmt: str = "ass",
                              width: int = 1920, height: int = 1080) -> dict[str, Any]:
        from app.core.studio_audio import assign_speakers, build_bilingual_ass, build_bilingual_srt
        tagged = assign_speakers(segments or [])
        if str(fmt).lower() == "srt":
            content = build_bilingual_srt(tagged)
        else:
            content = build_bilingual_ass(tagged, width=int(width), height=int(height))
        return {"ok": True, "fmt": str(fmt).lower(), "content": content, "segments": tagged}

    def studio_subtitle_edit(self, path: str, fmt: str = "ass") -> dict[str, Any]:
        from app.core.studio_audio import subtitle_edit_convert
        return subtitle_edit_convert(str(path or ""), str(fmt or "ass"))
