"""Agir medya araclari: Whisper altyazi + UVR5 vokal ayirma (GPU). Ilk kullanimda paket + model iner, ONCE SORULUR.

- Paketler uygulamanin Python ortamina `uv pip install` ile kurulur (paketleme asamasinda ayri karar).
- Isler tek kuyrukta sirayla (GPU bellegi 6 GB: ayni anda iki model calismasin), ALT SURECTE calisir
  (app.tools.*_run); arayuz surecine torch/CUDA yuklenmez, cokse de Kami ayakta kalir.
- Durum download.extra'ya yazilir: ai_whisper / ai_uvr = queued | running | done | error, ai_*_p (0-1), sonuclar.
"""
from __future__ import annotations

import importlib.util
import json
import logging
import os
import queue
import shutil
import subprocess
import sys
import threading
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)

TOOLS: dict[str, dict[str, Any]] = {
    "whisper": {
        "module": "faster_whisper",
        "packages": ["faster-whisper>=1.1", "nvidia-cublas-cu12", "nvidia-cudnn-cu12>=9,<10"],
        "extra_index": "",
        "size_gb": 3.0,    # paketler ~1.4 GB + large-v3-turbo modeli ~1.6 GB
    },
    "uvr": {
        "module": "audio_separator",
        "packages": ["audio-separator[gpu]", "torch>=2.3,<2.9", "torchaudio<2.9"],
        "extra_index": "https://download.pytorch.org/whl/cu128",
        "size_gb": 4.0,    # torch CUDA ~2.8 GB + onnxruntime-gpu + model ~0.6 GB
    },
}
UVR_MODELS = ["model_bs_roformer_ep_317_sdr_12.9755.ckpt", "UVR-MDX-NET-Inst_HQ_3.onnx",
              "htdemucs_ft.yaml"]
WHISPER_MODELS = ["large-v3-turbo", "large-v3", "medium", "small"]

NO_WINDOW = 0x08000000


def python_exe() -> str:
    """pythonw ile calisiyorsak ayni klasordeki python.exe (stdout borusu icin; pencere acilmaz)."""
    exe = sys.executable
    d, b = os.path.split(exe)
    if b.lower() in ("pythonw.exe", "kami.exe"):
        cand = os.path.join(d, "python.exe")
        if os.path.isfile(cand):
            return cand
    return exe


def installed(name: str) -> bool:
    try:
        return importlib.util.find_spec(TOOLS[name]["module"]) is not None
    except (ImportError, ValueError):
        return False


def models_dir(name: str) -> str:
    d = paths.DATA_DIR / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    return str(d)


def install(name: str, on_line: Callable[[str], None] = lambda s: None) -> bool:
    """uv pip install (uv yoksa pip). Uzun surer (GB); cagiran arka planda calistirir."""
    t = TOOLS[name]
    uv = shutil.which("uv")
    if uv:
        cmd = [uv, "pip", "install", "--python", python_exe()]
    else:
        cmd = [python_exe(), "-m", "pip", "install"]
    if t["extra_index"]:
        cmd += ["--extra-index-url", t["extra_index"], "--index-strategy", "unsafe-best-match"] if uv else \
            ["--extra-index-url", t["extra_index"]]
    cmd += t["packages"]
    log.info("Arac kuruluyor: %s", name)
    try:
        p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                             encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
        for line in p.stdout or []:
            on_line(line.rstrip())
        ok = p.wait() == 0
    except OSError:
        log.exception("Kurulum baslatilamadi")
        return False
    importlib.invalidate_caches()
    log.info("Arac kurulumu %s: %s", name, "tamam" if ok else "BASARISIZ")
    return ok and installed(name)


def _run_json(args: list[str], on_msg: Callable[[dict], None], cancel: threading.Event) -> dict:
    """Alt sureci calistir, JSON satirlarini ilet; son 'done'/'error' mesajini dondur."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_TELEMETRY": "1"}
    p = subprocess.Popen([python_exe(), "-m", *args], cwd=str(paths.ROOT), stdout=subprocess.PIPE,
                         stderr=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                         creationflags=NO_WINDOW, env=env)
    last: dict = {"error": "no_output"}
    watcher = threading.Thread(target=lambda: (cancel.wait(), p.poll() is None and p.kill()), daemon=True)
    watcher.start()
    for line in p.stdout or []:
        try:
            msg = json.loads(line)
        except ValueError:
            continue
        if "done" in msg or "error" in msg:
            last = msg
        on_msg(msg)
    p.wait()
    if cancel.is_set():
        return {"error": "cancelled"}
    return last


def embed_subtitle(video: str, srt: str, lang: str) -> bool:
    """SRT'yi videoya YUMUSAK altyazi izi olarak ekle (mp4: mov_text, mkv: srt). Mevcut izler korunur."""
    from app.engines.ytdlp_engine import find_ffmpeg
    ff = find_ffmpeg() or shutil.which("ffmpeg")
    if not ff:
        return False
    ext = os.path.splitext(video)[1].lower()
    codec = "mov_text" if ext in (".mp4", ".m4v", ".mov") else "srt"
    iso = {"tr": "tur", "en": "eng"}.get(lang, lang or "und")
    tmp = video + ".kami_sub" + ext
    cmd = [ff, "-y", "-v", "error", "-i", video, "-i", srt, "-map", "0", "-map", "1", "-c", "copy",
           "-c:s", codec, f"-metadata:s:s:{_sub_count(ff, video)}", f"language={iso}",
           f"-metadata:s:s:{_sub_count(ff, video)}", "title=Whisper", tmp]
    try:
        r = subprocess.run(cmd, capture_output=True, creationflags=NO_WINDOW, timeout=3600)
        if r.returncode != 0 or not os.path.isfile(tmp):
            log.warning("Altyazi gomulemedi: %s", (r.stderr or b"")[-300:].decode("utf-8", "replace"))
            return False
        os.replace(tmp, video)
        return True
    except (OSError, subprocess.SubprocessError):
        log.exception("ffmpeg altyazi gomme hatasi")
        return False
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


def _sub_count(ff: str, video: str) -> int:
    probe = os.path.join(os.path.dirname(ff), "ffprobe.exe")
    if not os.path.isfile(probe):
        return 0
    try:
        r = subprocess.run([probe, "-v", "error", "-select_streams", "s", "-show_entries", "stream=index",
                            "-of", "csv=p=0", video], capture_output=True, text=True, creationflags=NO_WINDOW,
                           timeout=60)
        return len([x for x in r.stdout.split() if x.strip()])
    except (OSError, subprocess.SubprocessError):
        return 0


class AiQueue:
    """Sirali GPU is kuyrugu. set_extra(did, **kw) indirme kaydina durum yazar."""

    def __init__(self, settings, set_extra: Callable[..., None], get_path: Callable[[int], str],
                 notify: Callable[[str], None] = lambda m: None) -> None:
        self.settings = settings
        self.set_extra = set_extra
        self.get_path = get_path
        self.notify = notify
        self._q: queue.Queue = queue.Queue()
        self._cancel: dict[tuple[str, int], threading.Event] = {}
        self.installing: dict[str, str] = {}      # ad -> son kurulum satiri (arayuz gosterir)
        self._thread = threading.Thread(target=self._loop, name="kami-ai", daemon=True)
        self._thread.start()

    # ---- kurulum
    def install_async(self, name: str) -> None:
        if name in self.installing:
            return
        self.installing[name] = "..."

        def work() -> None:
            def line(s: str) -> None:
                if s.strip():
                    self.installing[name] = s.strip()[-120:]
            ok = install(name, line)
            self.installing.pop(name, None)
            self.notify(f"{name}:{'installed' if ok else 'install_failed'}")
        threading.Thread(target=work, name=f"kami-install-{name}", daemon=True).start()

    # ---- isler
    def submit(self, kind: str, did: int, **opts: Any) -> dict[str, Any]:
        if kind not in TOOLS:
            return {"ok": False, "error": "bad_tool"}
        if not installed(kind):
            return {"ok": False, "error": "tool_missing", "tool": kind, "size_gb": TOOLS[kind]["size_gb"]}
        key = (kind, did)
        if key in self._cancel:
            return {"ok": True, "already": True}
        self._cancel[key] = threading.Event()
        self.set_extra(did, **{f"ai_{kind}": "queued", f"ai_{kind}_p": 0})
        self._q.put((kind, did, opts))
        return {"ok": True}

    def cancel(self, kind: str, did: int) -> None:
        ev = self._cancel.get((kind, did))
        if ev:
            ev.set()

    def _loop(self) -> None:
        while True:
            kind, did, opts = self._q.get()
            ev = self._cancel.get((kind, did)) or threading.Event()
            try:
                if ev.is_set():
                    self.set_extra(did, **{f"ai_{kind}": "cancelled"})
                    continue
                self.set_extra(did, **{f"ai_{kind}": "running"})
                getattr(self, f"_do_{kind}")(did, ev, **opts)
            except Exception:
                log.exception("AI isi hatasi: %s #%s", kind, did)
                self.set_extra(did, **{f"ai_{kind}": "error", f"ai_{kind}_err": "internal"})
            finally:
                self._cancel.pop((kind, did), None)

    def _do_whisper(self, did: int, ev: threading.Event, lang: str = "") -> None:
        path = self.get_path(did)
        if not path or not os.path.isfile(path):
            self.set_extra(did, ai_whisper="error", ai_whisper_err="no_file")
            return
        lang = lang or self.settings.get("whisper_lang") or "auto"
        model = self.settings.get("whisper_model") or "large-v3-turbo"
        srt = os.path.splitext(path)[0] + (f".{lang}" if lang != "auto" else "") + ".srt"
        res = _run_json(["app.tools.whisper_run", path, srt, lang, model, models_dir("whisper")],
                        lambda m: "p" in m and self.set_extra(did, ai_whisper_p=m["p"]), ev)
        if "error" in res:
            self.set_extra(did, ai_whisper="cancelled" if res["error"] == "cancelled" else "error",
                           ai_whisper_err=str(res["error"])[:200])
            return
        out = {"ai_whisper": "done", "ai_whisper_p": 1, "ai_whisper_srt": res["done"],
               "ai_whisper_lang": res.get("lang", ""), "ai_whisper_device": res.get("device", "")}
        from app.core.media_meta import kind_of
        if kind_of(path) == "video" and self.settings.get("whisper_embed"):
            out["ai_whisper_embedded"] = embed_subtitle(path, res["done"], res.get("lang", ""))
        self.set_extra(did, **out)
        self.notify(f"whisper:done:{os.path.basename(path)}")

    def _do_uvr(self, did: int, ev: threading.Event) -> None:
        path = self.get_path(did)
        if not path or not os.path.isfile(path):
            self.set_extra(did, ai_uvr="error", ai_uvr_err="no_file")
            return
        model = self.settings.get("uvr_model") or UVR_MODELS[0]
        out_dir = os.path.join(os.path.dirname(path), "Ayrilmis")
        res = _run_json(["app.tools.uvr_run", path, out_dir, model, models_dir("uvr"),
                         self.settings.get("uvr_format") or "mp3"],
                        lambda m: m.get("stage") == "separate" and self.set_extra(did, ai_uvr_p=0.3), ev)
        if "error" in res:
            self.set_extra(did, ai_uvr="cancelled" if res["error"] == "cancelled" else "error",
                           ai_uvr_err=str(res["error"])[:200])
            return
        self.set_extra(did, ai_uvr="done", ai_uvr_p=1, ai_uvr_files=res["done"], ai_uvr_device=res.get("device", ""))
        self.notify(f"uvr:done:{os.path.basename(path)}")
