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
        "packages": ["faster-whisper>=1.1", "av>=11,<19", "nvidia-cublas-cu12", "nvidia-cudnn-cu12==9.10.2.21"],
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


def tool_env(name: str):
    """Kurulu Kami: arac basina AYRI ortam (LOCALAPPDATA/Kami/media-env/<arac>); repo .venv'e bagimlilik YOK."""
    return paths.MEDIA_ENV / name


def _venv_has(venv, module: str) -> bool:
    return (venv / "Scripts" / "python.exe").is_file() and (venv / "Lib" / "site-packages" / module).is_dir()


def python_exe(name: str = "") -> str:
    """pythonw ile calisiyorsak ayni klasordeki python.exe (stdout borusu icin; pencere acilmaz)."""
    if paths.FROZEN:
        return str(tool_env(name) / "Scripts" / "python.exe")
    exe = sys.executable
    d, b = os.path.split(exe)
    if b.lower() in ("pythonw.exe", "kami.exe"):
        cand = os.path.join(d, "python.exe")
        if os.path.isfile(cand):
            return cand
    return exe


def installed(name: str) -> bool:
    if paths.FROZEN:
        return _venv_has(tool_env(name), TOOLS[name]["module"])
    try:
        return importlib.util.find_spec(TOOLS[name]["module"]) is not None
    except (ImportError, ValueError):
        return False


def _stamp_path(name: str):
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
                           capture_output=True, text=True, encoding="utf-8", errors="replace", stdin=subprocess.DEVNULL,
                           creationflags=NO_WINDOW, timeout=300,
                           env={**os.environ, "PYTHONIOENCODING": "utf-8"})
    except (OSError, subprocess.SubprocessError) as exc:
        return {"ok": False, "error": type(exc).__name__}
    for line in reversed((r.stdout or "").splitlines()):
        try:
            return json.loads(line)
        except ValueError:
            continue
    return {"ok": False, "error": "no_output: " + ((r.stderr or "").strip().splitlines() or [""])[-1][:150]}


def models_dir(name: str) -> str:
    d = paths.DATA_DIR / "models" / name
    d.mkdir(parents=True, exist_ok=True)
    if paths.FROZEN and not any(d.iterdir()):   # gelistirmede inmis modeller (GB'larca) tekrar inmesin
        old = paths.Path.home() / "Projeler" / "kami" / "data" / "models" / name
        if old.is_dir() and any(old.iterdir()):
            return str(old)
    return str(d)


LAST_ERROR: dict[str, str] = {}   # arac -> son kurulum hatasi (arayuz toast'ta gosterir)


def _ilog(name: str, text: str) -> None:
    """Kurulum cikisi: logging'den BAGIMSIZ, dogrudan DATA_DIR/install.log'a da yazilir (log kurulumu bozuk olsa bile iz kalir)."""
    log.info("[kurulum %s] %s", name, text)
    try:
        import time
        with open(paths.DATA_DIR / "install.log", "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S')} [{name}] {text}\n")
    except OSError:
        pass


def _fail(name: str, msg: str) -> bool:
    LAST_ERROR[name] = msg[-200:]
    _ilog(name, "HATA: " + msg)
    return False


def _run_logged(name: str, cmd: list[str], on_line: Callable[[str], None]) -> int:
    """Komutu calistir; stdout+stderr her satiri log'a + on_line'a. stdin KAPALI (konsolsuz Kami'de gecersiz handle)."""
    _ilog(name, "$ " + " ".join(cmd))
    p = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                         encoding="utf-8", errors="replace", creationflags=NO_WINDOW)
    tail: list[str] = []
    for line in p.stdout or []:
        line = line.rstrip()
        if line.strip():
            tail = (tail + [line.strip()])[-8:]
            _ilog(name, line)
            on_line(line)
    rc = p.wait()
    if rc != 0:
        LAST_ERROR[name] = f"cikis {rc}: " + (tail[-1] if tail else "")
    return rc


def install(name: str, on_line: Callable[[str], None] = lambda s: None) -> bool:
    """uv pip install (uv yoksa pip). Uzun surer (GB); cagiran arka planda calistirir. Hata: LAST_ERROR[name] + install.log."""
    LAST_ERROR.pop(name, None)
    try:
        return _install(name, on_line)
    except Exception as exc:   # noqa: BLE001 - hicbir hata sessiz kalmasin
        log.exception("Arac kurulumu istisna: %s", name)
        return _fail(name, f"{type(exc).__name__}: {exc}")


def _install(name: str, on_line: Callable[[str], None]) -> bool:
    t = TOOLS[name]
    uv = shutil.which("uv")
    if paths.FROZEN:   # ayri araclar ortami: yoksa uv ile Python 3.12 venv olustur (uv Python'u kendisi indirir)
        uv = str(paths.BIN_DIR / "uv.exe") if (paths.BIN_DIR / "uv.exe").is_file() else uv
        if not uv:
            return _fail(name, "uv.exe bulunamadi (bin klasoru)")
        env_dir = tool_env(name)
        if not (env_dir / "Scripts" / "python.exe").is_file():
            on_line("Python ortami olusturuluyor...")
            env_dir.parent.mkdir(parents=True, exist_ok=True)
            if _run_logged(name, [uv, "venv", "--python", "3.12", "--seed", str(env_dir)], on_line) != 0                     or not (env_dir / "Scripts" / "python.exe").is_file():
                return _fail(name, "Python ortami olusturulamadi: " + LAST_ERROR.get(name, "python.exe yok"))
    if uv:
        cmd = [uv, "pip", "install", "--python", python_exe(name)]
    else:
        cmd = [python_exe(name), "-m", "pip", "install"]
    if t["extra_index"]:
        cmd += ["--extra-index-url", t["extra_index"], "--index-strategy", "unsafe-best-match"] if uv else             ["--extra-index-url", t["extra_index"]]
    cmd += t["packages"]
    log.info("Arac kuruluyor: %s", name)
    ok = _run_logged(name, cmd, on_line) == 0
    importlib.invalidate_caches()
    if not ok:
        return _fail(name, "paket kurulumu basarisiz: " + LAST_ERROR.get(name, ""))
    if not installed(name):
        return _fail(name, f"kurulum bitti ama '{t['module']}' modulu bulunamadi")
    on_line("selftest...")
    st = selftest(name)
    _ilog(name, f"selftest: {st}")
    if not st.get("ok"):
        return _fail(name, "selftest: " + str(st.get("error", ""))[-150:])
    _stamp_path(name).write_text(_spec(name), encoding="utf-8")
    LAST_ERROR.pop(name, None)
    return True


def _run_json(args: list[str], on_msg: Callable[[dict], None], cancel: threading.Event, tool: str = "") -> dict:
    """GPU ile calistir; hata verirse CPU'ya dus (CUDA_VISIBLE_DEVICES=-1) ve sonuca cpu_fallback=True yaz."""
    res = _run_once(args, on_msg, cancel, tool, {})
    if "error" in res and res["error"] != "cancelled" and not cancel.is_set():
        log.warning("%s GPU'da basarisiz (%s); CPU'ya dusuluyor", tool, str(res["error"])[:120])
        res = _run_once(args, on_msg, cancel, tool, {"CUDA_VISIBLE_DEVICES": "-1"})
        if "done" in res:
            res["cpu_fallback"] = True
    return res


def _run_once(args: list[str], on_msg: Callable[[dict], None], cancel: threading.Event, tool: str,
              extra_env: dict) -> dict:
    env = {**os.environ, "PYTHONIOENCODING": "utf-8", "HF_HUB_DISABLE_TELEMETRY": "1", **extra_env}
    p = subprocess.Popen([python_exe(tool), "-m", *args], cwd=str(paths.TOOLSRC_DIR), stdin=subprocess.DEVNULL,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace",
                         creationflags=NO_WINDOW, env=env)
    last: dict = {"error": "no_output"}
    noise = ""
    watcher = threading.Thread(target=lambda: (cancel.wait(), p.poll() is None and p.kill()), daemon=True)
    watcher.start()
    for line in p.stdout or []:
        try:
            msg = json.loads(line)
        except ValueError:
            noise = line.strip()[-150:] or noise   # JSON olmayan satir (ör. Traceback son satiri) hata ipucu
            continue
        if "done" in msg or "error" in msg:
            last = msg
        on_msg(msg)
    p.wait()
    if cancel.is_set():
        return {"error": "cancelled"}
    if last == {"error": "no_output"} and noise:
        log.warning("%s alt surec cikti: %s", tool, noise)
        return {"error": "no_output: " + noise}
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
            self.notify(f"{name}:installed" if ok else f"{name}:install_failed:{LAST_ERROR.get(name, '')}")
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
                        self.set_extra(did, **{f"ai_{kind}": "error", f"ai_{kind}_err": "repair_failed: " + LAST_ERROR.get(tool, "")[:150]})
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
        if res.get("cpu_fallback") or res.get("device") == "cpu":
            self.notify("whisper:cpu:GPU kullanilamadi, islem CPU'da yapildi (yavas)")
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
        if res.get("cpu_fallback"):
            self.notify("uvr:cpu:GPU kullanilamadi, islem CPU'da yapildi (yavas)")
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
