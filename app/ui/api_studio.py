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
               "studio_myinstants", "studio_fetch_sound", "studio_freesound", "studio_pack_add", "studio_save", "studio_open"}


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
                "freesound": bool(self._fs_store().load())}

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
        if mode == "direct" and (i["kind"] == "audio" or (info.get("height") or 0) <= 1440):
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
            v = (["-c:v", "h264_nvenc", "-preset", "p3", "-cq", "24", "-g", "15", "-bf", "0"] if enc == "h264_nvenc"
                 else ["-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-g", "15", "-bf", "0"])
            args = ["-i", p, "-map", "0:v:0", "-map", "0:a:0?", "-vf", "scale='min(1920,iw)':-2,format=yuv420p", *v, "-c:a", "aac", "-b:a", "160k"]
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
        if not path:
            safe = re.sub(r'[<>:"/\\|?*]+', "_", str(project.get("name") or "Proje")).strip() or "Proje"
            path = str(studio.home_dir() / "Projeler" / f"{safe}{studio.PROJECT_EXT}")
        p = studio.save_project(path, project)
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
        if not self._media or not self._media.ffmpeg():
            return {"ok": False, "error": "no_ffmpeg"}
        return {"ok": True, "job": self._st().export(project, str(out), opts or {})}

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
