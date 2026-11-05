r"""Agir medya araclari: Whisper altyazi + UVR5 vokal ayirma (GPU). Ilk kullanimda paket + model iner, ONCE SORULUR.

- Gelistirmede paketler uygulamanin .venv'ine `uv pip install` ile kurulur. KURULU Kami.exe'de ayri bir ortam:
  %LOCALAPPDATA%\Kami\tools\venv (paketle gelen bin\uv.exe ile Python 3.12 + paketler; modeller kuruluma girmez).
  Gelistirme .venv'inde araclar zaten kuruluysa o kullanilir (7 GB tekrar inmesin).
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
        # av<19: PyAV 19 av.open'dan metadata_errors'u kaldirdi, faster-whisper 1.2.1 hala kullaniyor (05.11 olculdu)
        "packages": ["faster-whisper>=1.1", "av>=11,<19", "nvidia-cublas-cu12", "nvidia-cudnn-cu12>=9,<10"],
        "extra_index": "",
        "size_gb": 3.0,    # paketler ~1.4 GB + large-v3-turbo modeli ~1.6 GB
    },
    "uvr": {
        "module": "audio_separator",
        # audioread: librosa 1.0 artik cekmiyor ama audio-separator (VR, spec_utils) ice aktariyor
        "packages": ["audio-separator[gpu]", "audioread>=3", "soundfile", "torch>=2.3,<2.9", "torchaudio<2.9"],
        "extra_index": "https://download.pytorch.org/whl/cu128",
        "size_gb": 4.0,    # torch CUDA ~2.8 GB + onnxruntime-gpu + model ~0.6 GB
    },
}
# Is turu -> gereken araclar. "lyrics": UVR ile vokali ayir + Whisper ile sozleri yaziya dok (soz bulunamazsa)
JOBS: dict[str, tuple[str, ...]] = {"whisper": ("whisper",), "uvr": ("uvr",), "lyrics": ("uvr", "whisper")}
UVR_MODELS = ["model_bs_roformer_ep_317_sdr_12.9755.ckpt", "UVR-MDX-NET-Inst_HQ_3.onnx",
              "htdemucs_ft.yaml"]
WHISPER_MODELS = ["large-v3-turbo", "large-v3", "medium", "small"]

NO_WINDOW = 0x08000000


LEGACY_VENV = paths.Path.home() / "Projeler" / "kami" / ".venv"


def _venv_has(venv, module: str) -> bool:
    return (venv / "Scripts" / "python.exe").is_file() and (venv / "Lib" / "site-packages" / module).is_dir()


def tools_venv(name: str = ""):
    """Kurulu Kami: araclarin Python ortami (once kendi ortami, yoksa araclari kurulu gelistirme .venv'i)."""
    if name and not _venv_has(paths.TOOLS_ENV, TOOLS[name]["module"]) and _venv_has(LEGACY_VENV, TOOLS[name]["module"]):
        return LEGACY_VENV
    return paths.TOOLS_ENV


def python_exe(name: str = "") -> str:
    """pythonw ile calisiyorsak ayni klasordeki python.exe (stdout borusu icin; pencere acilmaz)."""
    if paths.FROZEN:
        return str(tools_venv(name) / "Scripts" / "python.exe")
    exe = sys.executable
    d, b = os.path.split(exe)
    if b.lower() in ("pythonw.exe", "kami.exe"):
        cand = os.path.join(d, "python.exe")
        if os.path.isfile(cand):
            return cand
    return exe


def installed(name: str) -> bool:
    if paths.FROZEN:
        return _venv_has(tools_venv(name), TOOLS[name]["module"])
    try:
        return importlib.util.find_spec(TOOLS[name]["module"]) is not None
    except (ImportError, ValueError):
        return False


def _stamp_path(name: str):
    if paths.FROZEN and tools_venv(name) == LEGACY_VENV:   # gelistirme ortami: onun damgasi
        return paths.Path.home() / "Projeler" / "kami" / "data" / "models" / name / ".kami_ok"
    return paths.DATA_DIR / "models" / name / ".kami_ok"


def _spec(name: str) -> str:
    return "|".join(TOOLS[name]["packages"])


def needs_repair(name: str) -> bool:
    """Paket var ama bu surumun paket listesiyle kurulup kendi kendine testten gecmemis (eski/bozuk kurulum)."""
    if not installed(name):
        return False
    try:
        return _stamp_path(name).read_text(encoding="utf-8") != _spec(name)
    except OSError:
        return True


def selftest(name: str) -> dict:
    """Alt surecte app.tools.selftest: model indirmeden ice aktarma + kucuk ses cozme."""
    folder = os.path.join(models_dir(name), "_selftest")
    try:
        r = subprocess.run([python_exe(name), "-m", "app.tools.selftest", name, folder], cwd=str(paths.TOOLSRC_DIR),
                           capture_output=True, text=True, encoding="utf-8", errors="replace",
                           creationflags=NO_WINDOW, timeout=300,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": type(exc).__name__}
    for line in reversed((r.stdout or "").splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"ok": False, "error": "no_output"}


def models_dir(name: str) -> str:
    d = paths.DATA_DIR / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    if paths.FROZEN and not any(d.iterdir()):   # gelistirmede inmis modeller (GB'larca) tekrar inmesin
        old = paths.Path.home() / "Projeler" / "kami" / "data" / "models" / name
        if old.is_dir() and any(old.iterdir()):
            return str(old)
    return str(d)


def install(name: str, on_line: Callable[[str], None] = lambda s: None) -> bool:
    """uv pip install (uv yoksa pip). Uzun surer (GB); cagiran arka planda calistirir."""
    t = TOOLS[name]
    uv = shutil.which("uv")
    if paths.FROZEN:   # ayri araclar ortami: yoksa uv ile Python 3.12 venv olustur
        uv = str(paths.BIN_DIR / "uv.exe") if (paths.BIN_DIR / "uv.exe").is_file() else uv
        if not uv:
            on_line("uv bulunamadi")
            return False
        if not (paths.TOOLS_ENV / "Scripts" / "python.exe").is_file():
            on_line("Python ortami olusturuluyor...")
            paths.TOOLS_ENV.parent.mkdir(parents=True, exist_ok=True)
            r = subprocess.run([uv, "venv", "--python", "3.12", str(paths.TOOLS_ENV)], capture_output=True,
                               text=True, creationflags=NO_WINDOW)
            if r.returncode != 0:
                log.warning("Araclar ortami olusturulamadi: %s", r.stderr[-300:])
                return False
    if uv:
        cmd = [uv, "pip", "install", "--python", python_exe(name)]
    else:
        cmd = [python_exe(name), "-m", "pip", "install"]
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
    if not (ok and installed(name)):
        return False
    on_line("selftest...")
    st = selftest(name)
    log.info("Arac kendi kendine testi %s: %s", name, st)
    if not st.get("ok"):
        on_line("selftest: " + str(st.get("error", ""))[:100])
        return False
    _stamp_path(name).write_text(_spec(name), encoding="utf-8")
    return True


def _run_json(args: list[str], on_msg: Callable[[dict], None], cancel: threading.Event, tool: str = "") -> dict:
    """Alt sureci calistir, JSON satirlarini ilet; son 'done'/'error' mesajini dondur."""
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_TELEMETRY": "1"}
    p = subprocess.Popen([python_exe(tool), "-m", *args], cwd=str(paths.TOOLSRC_DIR), stdout=subprocess.PIPE,
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
        if kind not in JOBS:
            return {"ok": False, "error": "bad_tool"}
        for tool in JOBS[kind]:
            if not installed(tool):
                return {"ok": False, "error": "tool_missing", "tool": tool, "size_gb": TOOLS[tool]["size_gb"]}
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
                broken = [t for t in JOBS[kind] if needs_repair(t)]
                for tool in broken:   # eski kurulum (ör. PyAV 19 / audioread eksik): sadece farki kurar
                    self.set_extra(did, **{f"ai_{kind}": "running", f"ai_{kind}_p": 0})
                    log.info("Arac onariliyor: %s", tool)
                    if not install(tool):
                        self.set_extra(did, **{f"ai_{kind}": "error", f"ai_{kind}_err": "repair_failed"})
                        break
                else:
                    broken = []
                if broken:
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
                        lambda m: "p" in m and self.set_extra(did, ai_whisper_p=m["p"]), ev, "whisper")
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
                        lambda m: m.get("stage") == "separate" and self.set_extra(did, ai_uvr_p=0.3), ev, "uvr")
        if "error" in res:
            self.set_extra(did, ai_uvr="cancelled" if res["error"] == "cancelled" else "error",
                           ai_uvr_err=str(res["error"])[:200])
            return
        self.set_extra(did, ai_uvr="done", ai_uvr_p=1, ai_uvr_files=res["done"], ai_uvr_device=res.get("device", ""))
        self.notify(f"uvr:done:{os.path.basename(path)}")

    def _do_lyrics(self, did: int, ev: threading.Event, lang: str = "") -> None:
        """Soz bulunamayan sarki: UVR5 vokal -> Whisper (vokal uzerinde) -> zaman damgali .lrc (AI etiketli)."""
        import tempfile
        from app.core import lyrics, media_meta
        path = self.get_path(did)
        if not path or not os.path.isfile(path):
            self.set_extra(did, ai_lyrics="error", ai_lyrics_err="no_file")
            return
        tmp = tempfile.mkdtemp(prefix="kami_lyr_", dir=models_dir("uvr"))
        try:
            res = _run_json(["app.tools.uvr_run", path, tmp, self.settings.get("uvr_model") or UVR_MODELS[0],
                             models_dir("uvr"), "wav"],
                            lambda m: m.get("stage") == "separate" and self.set_extra(did, ai_lyrics_p=0.2), ev, "uvr")
            if "error" in res:
                raise _JobError(res["error"])
            vocal = next((f for f in res["done"] if "(Vokal)" in os.path.basename(f)), "")
            if not vocal:
                raise _JobError("no_vocal")
            srt = os.path.join(tmp, "vocal.srt")
            lang = lang or self.settings.get("whisper_lang") or "auto"
            res = _run_json(["app.tools.whisper_run", vocal, srt, lang,
                             self.settings.get("whisper_model") or "large-v3-turbo", models_dir("whisper")],
                            lambda m: "p" in m and self.set_extra(did, ai_lyrics_p=0.5 + m["p"] / 2), ev, "whisper")
            if "error" in res:
                raise _JobError(res["error"])
            with open(srt, encoding="utf-8") as f:
                lrc = lyrics.srt_to_lrc(f.read())
            if not lrc:
                raise _JobError("no_speech")
            g = media_meta.guess(path, "")
            out = lyrics.write_lyrics(path, lrc, g["artist"], g["title"], bool(self.settings.get("lyrics_embed")),
                                      ai=True)
            self.set_extra(did, ai_lyrics="done", ai_lyrics_p=1, lyrics="ai", lyrics_lrc=out.get("lrc", ""))
            self.notify(f"lyrics:done:{os.path.basename(path)}")
        except _JobError as exc:
            err = str(exc)
            self.set_extra(did, ai_lyrics="cancelled" if err == "cancelled" else "error", ai_lyrics_err=err[:200])
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


class _JobError(Exception):
    pass
