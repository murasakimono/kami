"""Ekran kaydi + "son 30 saniye" (replay buffer).

Goruntu: ffmpeg ddagrab (Desktop Duplication, GPU'da kalir) -> h264_nvenc. Oyunda FPS'e etkisi cok dusuk.
Ses: pyaudiowpatch ile WASAPI loopback (sistem sesi) ve mikrofon AYRI izler. Loopback sessizlikte veri
gondermez; parcalar zaman damgasiyla yerine konup bosluklar sessizlikle doldurulur, boylece senkron kaymaz.

Replay: ffmpeg surekli 2 sn'lik .ts parcalarina (halka, ~50 sn) yazar, ses son ~50 sn bellekte tutulur.
Alt+F10 -> son N saniye birlestirilir. Alt+F9 -> normal kayit ac/kapa (mkv, cokse de kurtarilir) -> mp4.
"""
from __future__ import annotations

import collections
import glob
import logging
import os
import shutil
import subprocess
import tempfile
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger("kami")
NOWIN = 0x08000000 if os.name == "nt" else 0
SEG = 2            # replay parca suresi (sn)
WRAP = 26          # halka uzunlugu (parca) -> ~52 sn
RATE_GAP = 0.05    # bu kadar bosluk olursa sessizlik ekle


def clips_dir() -> Path:
    d = Path.home() / "Videos" / "Kami Klipler"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _stamp() -> str:
    return time.strftime("%Y-%m-%d %H.%M.%S")


# ---------------------------------------------------------------- ses
class _Sink:
    """Zaman damgali PCM parcalarini wav'a yazar; bosluklari sessizlikle doldurur, onde gideni kirpar."""

    def __init__(self, path: str, rate: int, ch: int, t0: float) -> None:
        self.w = wave.open(path, "wb")
        self.w.setnchannels(ch); self.w.setsampwidth(2); self.w.setframerate(rate)
        self.rate, self.ch, self.t0, self.pos = rate, ch, t0, 0   # pos: yazilan ornek sayisi
        self.lock = threading.Lock()

    def feed(self, t_start: float, data: bytes) -> None:
        fb = 2 * self.ch
        n = len(data) // fb
        want = int((t_start - self.t0) * self.rate)        # bu parcanin olmasi gereken yeri
        with self.lock:
            if self.w is None:
                return
            if want - self.pos > RATE_GAP * self.rate:       # sessiz gecen sure
                self.w.writeframes(b"\0" * ((want - self.pos) * fb)); self.pos = want
            skip = 0
            if want < 0:
                skip = min(n, -want)
            if skip < n:
                self.w.writeframes(data[skip * fb:]); self.pos += n - skip

    def close(self, t_end: float | None = None) -> None:
        with self.lock:
            if self.w is None:
                return
            if t_end:
                end = int((t_end - self.t0) * self.rate)
                if end > self.pos:
                    self.w.writeframes(b"\0" * ((end - self.pos) * 2 * self.ch)); self.pos = end
            self.w.close(); self.w = None


class AudioTap:
    """Tek bir ses kaynagi (loopback ya da mikrofon). Son `keep` sn bellekte; kayit sirasinda dosyaya da yazar."""

    def __init__(self, kind: str, keep: float = 55.0) -> None:
        self.kind, self.keep = kind, keep
        self.ring: collections.deque[tuple[float, bytes]] = collections.deque()
        self.rate, self.ch = 48000, 2
        self.sinks: list[_Sink] = []
        self.lock = threading.Lock()
        self._pa = self._st = None
        self.error = ""

    def start(self) -> bool:
        try:
            import pyaudiowpatch as pa
        except ImportError:
            self.error = "pyaudiowpatch yok"
            return False
        try:
            self._pa = pa.PyAudio()
            api = self._pa.get_host_api_info_by_type(pa.paWASAPI)
            if self.kind == "mic":
                dev = self._pa.get_device_info_by_index(api["defaultInputDevice"])
            else:
                dev = self._pa.get_device_info_by_index(api["defaultOutputDevice"])
                if not dev.get("isLoopbackDevice"):
                    for lb in self._pa.get_loopback_device_info_generator():
                        if dev["name"] in lb["name"]:
                            dev = lb
                            break
            self.rate = int(dev["defaultSampleRate"])
            self.ch = max(1, min(2, int(dev["maxInputChannels"])))

            def cb(data, frames, tinfo, status):
                now = time.time()
                t = now - frames / self.rate
                with self.lock:
                    self.ring.append((t, data))
                    while self.ring and self.ring[0][0] < now - self.keep:
                        self.ring.popleft()
                    sinks = list(self.sinks)
                for s in sinks:
                    s.feed(t, data)
                return (None, pa.paContinue)

            self._st = self._pa.open(format=pa.paInt16, channels=self.ch, rate=self.rate, input=True,
                                     input_device_index=dev["index"], frames_per_buffer=int(self.rate / 50),
                                     stream_callback=cb)
            self._st.start_stream()
            return True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"[:160]
            log.warning("Ses kaynagi acilamadi (%s): %s", self.kind, self.error)
            self.stop()
            return False

    def stop(self) -> None:
        try:
            if self._st:
                self._st.stop_stream(); self._st.close()
        except Exception:
            pass
        try:
            if self._pa:
                self._pa.terminate()
        except Exception:
            pass
        self._st = self._pa = None

    @property
    def alive(self) -> bool:
        return self._st is not None

    def dump(self, path: str, t0: float, t1: float) -> None:
        """Bellekteki [t0, t1] araligini wav'a yazar."""
        with self.lock:
            items = [x for x in self.ring if x[0] >= t0 - 0.1 and x[0] <= t1]
        s = _Sink(path, self.rate, self.ch, t0)
        for t, d in items:
            s.feed(t, d)
        s.close(t1)

    def add_sink(self, path: str, t0: float) -> _Sink:
        s = _Sink(path, self.rate, self.ch, t0)
        with self.lock:
            self.sinks.append(s)
        return s

    def remove_sink(self, s: _Sink, t_end: float) -> None:
        with self.lock:
            if s in self.sinks:
                self.sinks.remove(s)
        s.close(t_end)


# ---------------------------------------------------------------- goruntu
def _video_args(fps: int, mode: str) -> list[str]:
    src = f"ddagrab=output_idx=0:framerate={fps}:draw_mouse=1"
    if mode == "nvenc":
        return ["-f", "lavfi", "-i", src, "-c:v", "h264_nvenc", "-preset", "p4", "-tune", "ll", "-rc", "vbr",
                "-cq", "21", "-b:v", "0", "-maxrate", "40M", "-bufsize", "80M", "-g", str(fps * SEG)]
    if mode == "nvenc_dl":
        return ["-f", "lavfi", "-i", src + ",hwdownload,format=bgra", "-c:v", "h264_nvenc", "-preset", "p4",
                "-rc", "vbr", "-cq", "21", "-b:v", "0", "-g", str(fps * SEG), "-pix_fmt", "yuv420p"]
    return ["-f", "lavfi", "-i", src + ",hwdownload,format=bgra", "-c:v", "libx264", "-preset", "ultrafast",
            "-crf", "23", "-g", str(fps * SEG), "-pix_fmt", "yuv420p"]


class Recorder:
    def __init__(self, ffmpeg: Callable[[], str], settings: Any, notify: Callable[[str, str, str], None]) -> None:
        self._ffmpeg, self.settings, self.notify = ffmpeg, settings, notify
        self.work = Path(tempfile.gettempdir()) / "kami_replay"
        self.sys = AudioTap("loop")
        self.mic = AudioTap("mic")
        self.buf: subprocess.Popen | None = None
        self.rec: dict[str, Any] | None = None
        self.mode = ""
        self.lock = threading.Lock()
        self.last_error = ""

    # ---- ortak
    def _pick_mode(self) -> str:
        if self.mode:
            return self.mode
        ff = self._ffmpeg()
        tmp = os.path.join(tempfile.gettempdir(), "kami_rec_probe.mp4")
        for m in ("nvenc", "nvenc_dl", "x264"):
            r = subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", *_video_args(30, m), "-t", "0.5", tmp],
                               capture_output=True, creationflags=NOWIN, timeout=30)
            if r.returncode == 0 and os.path.getsize(tmp) > 1000:
                self.mode = m
                log.info("Ekran kaydi kodlayici: %s", m)
                return m
        raise RuntimeError("ekran yakalanamadi")

    def _audio_on(self) -> None:
        if not self.sys.alive:
            self.sys.start()
        if self.settings.get("rec_mic") and not self.mic.alive:
            self.mic.start()
        if not self.settings.get("rec_mic") and self.mic.alive:
            self.mic.stop()

    def _fps(self) -> int:
        return int(self.settings.get("rec_fps") or 60)

    def status(self) -> dict[str, Any]:
        return {"replay": bool(self.buf and self.buf.poll() is None), "recording": bool(self.rec),
                "since": self.rec["t0"] if self.rec else 0, "mode": self.mode, "error": self.last_error,
                "sys_audio": self.sys.alive, "mic": self.mic.alive, "folder": str(clips_dir())}

    # ---- replay buffer
    def start_replay(self) -> bool:
        with self.lock:
            if self.buf and self.buf.poll() is None:
                return True
            try:
                mode = self._pick_mode()
            except Exception as exc:
                self.last_error = str(exc)
                return False
            shutil.rmtree(self.work, ignore_errors=True)
            self.work.mkdir(parents=True, exist_ok=True)
            self._audio_on()
            args = [self._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y", *_video_args(self._fps(), mode),
                    "-f", "segment", "-segment_time", str(SEG), "-segment_wrap", str(WRAP), "-reset_timestamps", "1",
                    "-segment_format", "mpegts", str(self.work / "seg_%03d.ts")]
            self.buf = subprocess.Popen(args, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                        creationflags=NOWIN)
            return True

    def watch(self) -> None:
        """Ekran kilitlenince/UAC'de ddagrab duser; acik kalmasi gerekiyorsa yeniden baslatir."""
        def loop() -> None:
            while True:
                time.sleep(10)
                try:
                    if self.settings.get("rec_replay_enabled") and self.buf is not None and self.buf.poll() is not None:
                        log.info("Kayit tamponu durmus, yeniden baslatiliyor")
                        self.buf = None
                        self.start_replay()
                except Exception:
                    log.exception("tampon izleyici")
        threading.Thread(target=loop, name="kami-replay-watch", daemon=True).start()

    def stop_replay(self) -> None:
        with self.lock:
            p, self.buf = self.buf, None
        if p and p.poll() is None:
            try:
                p.stdin.write(b"q"); p.stdin.flush(); p.wait(5)
            except Exception:
                p.kill()
        if not self.rec:
            self.sys.stop(); self.mic.stop()

    def save_replay(self, seconds: int | None = None) -> str:
        seconds = int(seconds or self.settings.get("rec_replay_seconds") or 30)
        if not (self.buf and self.buf.poll() is None):
            if not self.start_replay():
                raise RuntimeError(self.last_error or "kayit tamponu calismiyor")
            raise RuntimeError("tampon yeni basladi, birkac saniye sonra tekrar dene")
        now = time.time()
        segs = sorted(glob.glob(str(self.work / "seg_*.ts")), key=os.path.getmtime)
        segs = [s for s in segs if os.path.getmtime(s) >= now - seconds - SEG * 2 and os.path.getsize(s) > 0]
        if not segs:
            raise RuntimeError("tampon bos")
        job = Path(tempfile.mkdtemp(prefix="kami_clip_"))
        # yazilmakta olan son parca da dahil (ts kismen okunabilir)
        local = []
        for i, s in enumerate(segs):
            dst = job / f"{i:03d}.ts"
            shutil.copyfile(s, dst)
            local.append(dst)
        t_first = os.path.getmtime(segs[0]) - SEG          # ilk parcanin baslangici (yaklasik)
        (job / "list.txt").write_text("".join(f"file '{p.name}'\n" for p in local), encoding="utf-8")
        ff = self._ffmpeg()
        joined = job / "v.mkv"
        subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y", "-f", "concat", "-safe", "0", "-i",
                        str(job / "list.txt"), "-c", "copy", str(joined)], creationflags=NOWIN, check=True,
                       capture_output=True, timeout=120)
        dur = self._duration(str(joined)) or (now - t_first)
        t_first = now - dur                                   # sona hizala: son kare = simdi
        out = clips_dir() / f"Klip {_stamp()}.mp4"
        self._mux(joined, t_first, now, out, cut=max(0.0, dur - seconds), job=job)
        shutil.rmtree(job, ignore_errors=True)
        return str(out)

    # ---- normal kayit
    def toggle_record(self) -> dict[str, Any]:
        return self.stop_record() if self.rec else self.start_record()

    def start_record(self) -> dict[str, Any]:
        with self.lock:
            if self.rec:
                return {"ok": True, "recording": True}
            try:
                mode = self._pick_mode()
            except Exception as exc:
                return {"ok": False, "error": str(exc)}
            self._audio_on()
            job = Path(tempfile.mkdtemp(prefix="kami_rec_"))
            p = subprocess.Popen([self._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                                  *_video_args(self._fps(), mode), str(job / "v.mkv")],
                                 stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                 creationflags=NOWIN)
            t0 = time.time() + 0.15      # ddagrab acilis gecikmesi (yaklasik)
            sinks = {}
            if self.sys.alive:
                sinks["sys"] = self.sys.add_sink(str(job / "sys.wav"), t0)
            if self.mic.alive:
                sinks["mic"] = self.mic.add_sink(str(job / "mic.wav"), t0)
            self.rec = {"p": p, "job": job, "t0": t0, "sinks": sinks}
            return {"ok": True, "recording": True}

    def stop_record(self) -> dict[str, Any]:
        with self.lock:
            r, self.rec = self.rec, None
        if not r:
            return {"ok": False, "error": "kayit yok"}
        p = r["p"]
        t1 = time.time()
        try:
            p.stdin.write(b"q"); p.stdin.flush(); p.wait(15)
        except Exception:
            p.kill()
        for k, s in r["sinks"].items():
            (self.sys if k == "sys" else self.mic).remove_sink(s, t1)
        job = r["job"]
        out = clips_dir() / f"Kayıt {_stamp()}.mp4"
        try:
            dur = self._duration(str(job / "v.mkv")) or (t1 - r["t0"])
            self._mux(job / "v.mkv", t1 - dur, t1, out, cut=0, job=job, wavs_ready=True)
        except Exception as exc:
            keep = clips_dir() / f"Kayıt {_stamp()} (ham).mkv"
            shutil.move(str(job / "v.mkv"), keep)
            return {"ok": False, "error": str(exc)[:160], "path": str(keep)}
        finally:
            if not (self.buf and self.buf.poll() is None):
                self.sys.stop(); self.mic.stop()
        shutil.rmtree(job, ignore_errors=True)
        return {"ok": True, "path": str(out)}

    # ---- yardimcilar
    def _duration(self, path: str) -> float:
        ff = self._ffmpeg()
        probe = str(Path(ff).with_name("ffprobe" + Path(ff).suffix))
        try:
            r = subprocess.run([probe, "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", path],
                               capture_output=True, text=True, creationflags=NOWIN, timeout=30)
            return float(r.stdout.strip())
        except Exception:
            return 0.0

    def _mux(self, video: Path, t0: float, t1: float, out: Path, cut: float, job: Path, wavs_ready: bool = False) -> None:
        tracks = []
        for tap, name, title in ((self.sys, "sys", "Sistem"), (self.mic, "mic", "Mikrofon")):
            w = job / f"{name}.wav"
            if not wavs_ready and tap.alive:
                tap.dump(str(w), t0, t1)
            if w.exists() and w.stat().st_size > 1000:
                tracks.append((w, title))
        args = [self._ffmpeg(), "-hide_banner", "-loglevel", "error", "-y"]
        ss = ["-ss", f"{cut:.3f}"] if cut > 0.05 else []
        args += [*ss, "-i", str(video)]
        for w, _ in tracks:
            args += [*ss, "-i", str(w)]
        args += ["-map", "0:v:0"]
        for i in range(len(tracks)):
            args += ["-map", f"{i + 1}:a:0"]
        args += ["-c:v", "copy"]
        if tracks:
            args += ["-c:a", "aac", "-b:a", "192k"]
            for i, (_, title) in enumerate(tracks):
                args += [f"-metadata:s:a:{i}", f"title={title}"]
            args += ["-disposition:a:0", "default", "-shortest"]
        args += ["-movflags", "+faststart", str(out)]
        r = subprocess.run(args, capture_output=True, text=True, creationflags=NOWIN, timeout=600)
        if r.returncode != 0:
            raise RuntimeError(r.stderr.strip()[-200:] or "birlestirilemedi")

    def shutdown(self) -> None:
        if self.rec:
            try:
                self.stop_record()
            except Exception:
                log.exception("kayit kapatilamadi")
        self.stop_replay()
        self.sys.stop(); self.mic.stop()
