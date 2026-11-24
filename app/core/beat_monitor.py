"""Kami Beat Asama 1d-2: kulaklikta efektli dinleme (canli izleme / monitoring).

Varsayilan KAPALI. Acilinca mikrofon sesi hafif oda havasi (kucuk reverb) + istege bagli ton duzeltme ile
kulakliga geri verilir. KAYDA HAM SES girer: izleme akisi kayit dosyasina hicbir sey yazmaz; izleme acikken
PC kaydedici ayni mikrofonu ikinci kez acmak yerine bu akisin HAM giris bloklarini dinler (tap).

Motor: sounddevice tam cift yonlu akis (blok 128-256, latency="low"; Windows'ta WASAPI paylasimli mod -
ozel (exclusive) mod Kami'nin calan beat'ini susturacagi icin kullanilmaz). Efekt: pedalboard varsa
gercek Reverb (+ ton duzeltme icin kullanicinin VST3 pitch-duzeltme eklentisi), yoksa saf numpy "oda havasi"
(blok boyundan uzun geri beslemeli gecikme hatlari -> blok bazinda vektorize, durumlu).
Gecikme olculup gosterilir; 20 ms ustu uyari. Akis kurulamazsa acik hata doner, ozellik pasif kalir.
"""
from __future__ import annotations

import logging
import threading
from typing import Any, Callable

from app.core import beat_fx

log = logging.getLogger(__name__)

WARN_MS = 20.0
BLOCK_CHOICES = (128, 192, 256)
DEFAULT_BLOCK = 128
ROOM_FX = {"type": "reverb", "room_size": 0.12, "damping": 0.6, "wet_level": 0.1, "dry_level": 1.0, "width": 0.8}
TUNE_HINTS = ("autotune", "auto-tune", "auto tune", "graillon", "mautopitch", "autopitch", "pitch correct",
              "pitchcorrect", "gsnap", "keepforest", "melda pitch", "reatune", "voloco")


def find_tune_vst(plugins: list[dict[str, Any]] | None) -> dict[str, Any] | None:
    """Taranmis VST3 listesinden (beat_vst_scan) gercek zamanli ton duzeltme eklentisi."""
    for p in plugins or []:
        nm = str(p.get("name") or "").lower()
        if any(h in nm for h in TUNE_HINTS) and p.get("path"):
            return p
    return None


def monitor_chain(reverb: bool = True, tune: bool = False, tune_vst: dict[str, Any] | None = None) -> dict[str, Any]:
    """Izleme efekt zinciri + not. tune istenip eklenti yoksa 'tune_unavailable' notu (zincire eklenmez)."""
    fx: list[dict[str, Any]] = []
    notes: list[str] = []
    if tune:
        if tune_vst and tune_vst.get("path"):
            fx.append({"type": "vst3", "path": str(tune_vst["path"]), "name": str(tune_vst.get("name") or "Tune")})
        else:
            notes.append("tune_unavailable")
    if reverb:
        fx.append(dict(ROOM_FX))
    return {"fx": fx, "notes": notes}


def latency_ms(blocksize: int, sr: int, stream_latency: Any) -> float:
    """Gidis-donus izleme gecikmesi (ms) = giris + cikis surucu gecikmesi + bir blok isleme payi."""
    try:
        if isinstance(stream_latency, (list, tuple)):
            lin, lout = float(stream_latency[0] or 0.0), float(stream_latency[1] or 0.0)
        else:
            lin, lout = float(stream_latency or 0.0), 0.0
    except (TypeError, ValueError):
        lin = lout = 0.0
    blk = max(0, int(blocksize or 0)) / float(sr or 48000)
    return round((lin + lout + blk) * 1000.0, 1)


def latency_report(ms: float) -> dict[str, Any]:
    ms = float(ms or 0.0)
    warn = ms > WARN_MS
    msg = f"İzleme gecikmesi: {ms:.0f} ms"
    if warn:
        msg += " — Gecikme yüksek, kuru dinleme önerilir"
    return {"latency_ms": round(ms, 1), "warn": warn, "message": msg}


class RoomAir:
    """pedalboard'suz zarif yedek: kucuk oda havasi. Paralel geri beslemeli tarak (comb) gecikme hatlari;
    her hat >= blok boyu oldugundan bir blok yalniz gecmis tampona bagli -> blok bazinda vektorize ve
    blok boyundan bagimsiz (128 ya da 256 ile ayni cikti)."""

    DELAYS_MS = (29.7, 37.1, 41.1, 43.7)

    def __init__(self, sr: int = 48000, wet: float = 0.1, feedback: float = 0.55, max_block: int = 1024):
        import numpy as np
        self.sr = int(sr)
        self.wet = float(wet)
        self.fb = float(feedback)
        self.delays = [max(max_block, int(round(d / 1000.0 * self.sr))) for d in self.DELAYS_MS]
        self.bufs = [np.zeros(d, dtype="float32") for d in self.delays]    # her hattin cikis gecmisi (dairesel)
        self.pos = [0 for _ in self.delays]

    def process(self, x):
        """x: (n,) ya da (n,1) mono float32 -> (n,2) stereo (kuru + islak)."""
        import numpy as np
        m = np.asarray(x, dtype="float32").reshape(-1)
        n = len(m)
        wet = np.zeros(n, dtype="float32")
        for k, d in enumerate(self.delays):
            buf, p = self.bufs[k], self.pos[k]
            if n > d:
                raise ValueError("block_too_large")
            idx = (p + np.arange(n)) % d
            past = buf[idx]                         # d ornek once bu hattin ciktisi
            y = m + self.fb * past                  # y[t] = x[t] + fb * y[t-d]
            buf[idx] = y
            self.pos[k] = (p + n) % d
            wet += past
        wet *= self.wet / len(self.delays)
        l = m + wet
        r = m + np.roll(wet, 7) if n > 7 else m + wet
        return np.stack([l, r], axis=1).astype("float32")


class Monitor:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream = None
        self._taps: list[Callable[[Any, int], None]] = []
        self._device: int | None = None
        self._sr = 48000
        self._block = DEFAULT_BLOCK
        self._latency = 0.0
        self._engine = "none"
        self._board = None
        self._borrowed: list[tuple[str, Any]] = []
        self._air: RoomAir | None = None
        self._xruns = 0
        self._error = ""
        self._notes: list[str] = []
        self._reverb = True
        self._tune = False

    @property
    def running(self) -> bool:
        return self._stream is not None

    def can_tap(self, device_id: int | None) -> bool:
        dev = device_id if device_id is not None and device_id >= 0 else None
        return self.running and dev == self._device

    def add_tap(self, fn: Callable[[Any, int], None]) -> None:
        with self._lock:
            if fn not in self._taps:
                self._taps.append(fn)

    def remove_tap(self, fn: Callable[[Any, int], None]) -> None:
        with self._lock:
            if fn in self._taps:
                self._taps.remove(fn)

    def status(self) -> dict[str, Any]:
        rep = latency_report(self._latency) if self.running else {"latency_ms": 0.0, "warn": False, "message": ""}
        return {"ok": True, "running": self.running, "engine": self._engine, "blocksize": self._block, "sr": self._sr,
                "xruns": self._xruns, "error": self._error, "notes": list(self._notes), "reverb": self._reverb,
                "tune": self._tune, "taps": len(self._taps), **rep}

    def _process(self, mono):
        """Bir blok: (n,1) ham giris -> (n,2) kulaklik cikisi."""
        import numpy as np
        if self._board is not None:
            x = np.ascontiguousarray(np.repeat(mono.reshape(1, -1), 2, axis=0), dtype="float32")
            y = self._board(x, self._sr, reset=False)
            y = np.asarray(y, dtype="float32").T
            if len(y) < len(mono):
                y = np.concatenate([y, np.zeros((len(mono) - len(y), y.shape[1]), dtype="float32")])
            return y[: len(mono), :2]
        if self._air is not None:
            return self._air.process(mono)
        m = np.asarray(mono, dtype="float32").reshape(-1, 1)
        return np.repeat(m, 2, axis=1)

    def _callback(self, indata, outdata, frames, time_info, status) -> None:
        if status:
            self._xruns += 1
        for fn in list(self._taps):           # kayda HAM ses
            try:
                fn(indata, frames)
            except Exception:
                log.debug("izleme tap hatasi", exc_info=True)
        try:
            y = self._process(indata[:, :1])
            nch = outdata.shape[1]
            outdata[:] = y[:, :nch] if nch <= 2 else y[:, :1].repeat(nch, axis=1)
        except Exception:
            outdata.fill(0)

    def start(self, device_id: int | None = None, out_device: int | None = None, blocksize: int = DEFAULT_BLOCK,
              sr: int = 48000, reverb: bool = True, tune: bool = False, vst_plugins: list[dict[str, Any]] | None = None) -> dict[str, Any]:
        with self._lock:
            if self._stream is not None:
                return {"ok": False, "error": "already_running", **self.status()}
            self._error = ""
            self._xruns = 0
            blk = int(blocksize) if int(blocksize or 0) in BLOCK_CHOICES else DEFAULT_BLOCK
            self._block, self._sr = blk, int(sr or 48000)
            self._reverb, self._tune = bool(reverb), bool(tune)
            ch = monitor_chain(reverb, tune, find_tune_vst(vst_plugins) if tune else None)
            self._notes = ch["notes"]
            self._board, self._air, self._borrowed = None, None, []
            pb = beat_fx.pedalboard_module()
            if ch["fx"] and pb is not None:
                plugins, borrowed, skipped = beat_fx.build_plugins(pb, ch["fx"])
                self._borrowed = borrowed
                if skipped:
                    self._notes.append("skipped:" + ",".join(skipped))
                if plugins:
                    self._board = pb.Pedalboard(plugins)
                    self._engine = "pedalboard"
            if self._board is None:
                if reverb:
                    self._air = RoomAir(self._sr, max_block=blk)
                    self._engine = "numpy"
                else:
                    self._engine = "dry"
                if tune and "tune_unavailable" not in self._notes:
                    self._notes.append("tune_unavailable")
            try:
                import sounddevice as sd
            except Exception as exc:
                self._error = "sounddevice_missing"
                self._release()
                return {"ok": False, "error": "sounddevice_missing", "detail": str(exc)[:120], **self.status()}
            dev_in = device_id if device_id is not None and device_id >= 0 else None
            dev_out = out_device if out_device is not None and out_device >= 0 else None
            try:
                st = sd.Stream(samplerate=self._sr, blocksize=blk, channels=(1, 2), dtype="float32",
                               device=(dev_in, dev_out), latency="low", callback=self._callback)
                st.start()
            except Exception as exc:
                self._error = str(exc)[:160] or "stream_failed"
                self._release()
                return {"ok": False, "error": "stream_failed", "detail": self._error, **self.status()}
            self._stream = st
            self._device = dev_in
            self._latency = latency_ms(blk, self._sr, getattr(st, "latency", 0.0))
            return {"ok": True, **self.status()}

    def _release(self) -> None:
        for vp, plg in self._borrowed:
            try:
                beat_fx.POOL.release(vp, plg)
            except Exception:
                pass
        self._borrowed = []
        self._board = None
        self._air = None
        self._engine = "none"

    def stop(self, force: bool = False) -> dict[str, Any]:
        with self._lock:
            if self._stream is None:
                return {"ok": True, "running": False}
            if self._taps and not force:
                return {"ok": False, "error": "recording_active"}
            try:
                self._stream.stop()
                self._stream.close()
            except Exception:
                pass
            self._stream = None
            self._device = None
            self._taps = []
            self._latency = 0.0
            self._release()
            return {"ok": True, "running": False}


MONITOR = Monitor()

