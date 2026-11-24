"""Kami Booth: PC mikrofonu (ATK N9) 48 kHz kayit + iPhone 15 Pro Max kablosuz WAV & Teleprompter sunucusu."""
from __future__ import annotations

import base64
import hmac
import json
import logging
import math
import os
import secrets
import socket
import subprocess
import threading
import time
import urllib.parse
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app import paths
from app.core import beat_studio, kami_beat

log = logging.getLogger(__name__)


def _local_ip() -> str:
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


def list_input_devices() -> dict[str, Any]:
    """Sistemdeki ses giris cihazlarini (ATK N9 vb.) listeler."""
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        default_in = sd.default.device[0] if isinstance(sd.default.device, (list, tuple)) else -1
        out = []
        for idx, d in enumerate(devs):
            if int(d.get("max_input_channels") or 0) > 0:
                out.append({
                    "id": idx,
                    "name": str(d.get("name") or f"Mic {idx}"),
                    "channels": int(d.get("max_input_channels") or 1),
                    "sr": int(d.get("default_samplerate") or 48000),
                    "default": idx == default_in,
                })
        return {"ok": True, "devices": out}
    except Exception as exc:
        return {"ok": False, "devices": [], "error": str(exc)[:120]}


class PcRecorder:
    """sounddevice tabanli dusuk gecikmeli 48 kHz mikrofon kaydedici."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream = None
        self._chunks: list[Any] = []
        self._recording = False
        self._sr = 48000
        self._project_id = ""
        self._track_id = "vocal1"
        self._started_at = 0.0
        self._timeline_start: float | None = None
        self._epoch0: float | None = None     # 1b: kaydin 0. orneginin duvar saati (time.time)
        self._frames = 0
        self._level = 0.0                     # son status okumasindan beri tepe (0..1)
        self._tapped = False                  # 1d-2: izleme akisinin ham girisini dinliyor (mikrofon ikinci kez acilmaz)

    def _tap(self, indata, frames: int) -> None:
        self._on_block(indata, frames)

    def _on_block(self, indata, frames: int) -> None:
        """Ses geri cagrisi: parcayi sakla, ilk blokta zaman capasini kur, tepe seviyesini guncelle."""
        if self._epoch0 is None:
            self._epoch0 = time.time() - frames / float(self._sr or 48000)
        self._chunks.append(indata.copy())
        self._frames += int(frames)
        try:
            pk = float(abs(indata).max()) if frames else 0.0
        except Exception:
            pk = 0.0
        if pk > self._level:
            self._level = pk

    def status(self) -> dict[str, Any]:
        lvl = self._level
        self._level = 0.0
        db = round(20.0 * math.log10(lvl), 1) if lvl > 1e-6 else -120.0
        return {
            "ok": True,
            "recording": self._recording,
            "elapsed": round(time.time() - self._started_at, 1) if self._recording else 0.0,
            "rec_sec": round(self._frames / float(self._sr or 48000), 2) if self._recording else 0.0,
            "level": round(min(1.0, lvl), 4),
            "level_db": db,
            "clip": lvl >= 0.999,
            "project_id": self._project_id,
            "track_id": self._track_id,
        }

    def start(self, project_id: str = "", track_id: str = "vocal1", device_id: int | None = None, sr: int = 48000,
              timeline_start: float | None = None) -> dict[str, Any]:
        with self._lock:
            if self._recording:
                return {"ok": False, "error": "already_recording"}
            try:
                import sounddevice as sd
                self._chunks = []
                self._sr = int(sr or 48000)
                self._project_id = project_id
                self._track_id = track_id or "vocal1"
                self._timeline_start = timeline_start   # Kami Beat 1a: kayit zaman cizelgesinde nereden basladi
                self._epoch0 = None
                self._frames = 0
                self._level = 0.0

                from app.core import beat_monitor
                if beat_monitor.MONITOR.can_tap(device_id):
                    # 1d-2: efektli dinleme acik -> ayni mikrofonun HAM bloklari kayda (efekt yalniz kulaklikta)
                    self._sr = beat_monitor.MONITOR.status().get("sr") or self._sr
                    beat_monitor.MONITOR.add_tap(self._tap)
                    self._tapped = True
                    self._recording = True
                    self._started_at = time.time()
                    return {"ok": True, "sr": self._sr, "tapped": True}

                def _cb(indata, frames, time_info, status):
                    self._on_block(indata, frames)

                self._stream = sd.InputStream(
                    samplerate=self._sr,
                    channels=1,
                    dtype="float32",
                    device=device_id if device_id is not None and device_id >= 0 else None,
                    callback=_cb,
                )
                self._stream.start()
                self._recording = True
                self._started_at = time.time()
                return {"ok": True, "sr": self._sr}
            except Exception as exc:
                self._stream = None
                self._recording = False
                return {"ok": False, "error": str(exc)[:140]}

    def _close_stream(self) -> None:
        if self._tapped:
            from app.core import beat_monitor
            beat_monitor.MONITOR.remove_tap(self._tap)
            self._tapped = False
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        finally:
            self._stream = None
            self._recording = False

    def _write_raw(self, prefix: str = "") -> tuple[str, int] | None:
        if not self._chunks:
            return None
        import numpy as np
        mono = np.concatenate(self._chunks, axis=0)
        stereo = np.repeat(mono, 2, axis=1).astype("float32")
        fname = f"{prefix}pc_mic_{int(time.time())}_{uuid.uuid4().hex[:4]}.wav"
        out_path = str(beat_studio.recordings_dir() / fname)
        beat_studio._write_wav_np(out_path, stereo, self._sr)
        return out_path, len(stereo)

    def cancel(self) -> dict[str, Any]:
        """1b (Esc): kayit iptal - take/klip eklenmez, ham ses '_iptal' onekiyle saklanir."""
        with self._lock:
            if not self._recording:
                return {"ok": False, "error": "not_recording"}
            self._close_stream()
            w = self._write_raw("_iptal_")
            self._chunks = []
            return {"ok": True, "cancelled": True, "path": w[0] if w else ""}

    def stop(self, ai_clean: bool = True, plan: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:
            if not self._recording:
                return {"ok": False, "error": "not_recording"}
            self._close_stream()

            w = self._write_raw()
            self._chunks = []
            if not w:
                return {"ok": False, "error": "empty_recording"}
            out_path, n_frames = w
            raw_path = out_path

            if ai_clean:
                clean_path = str(beat_studio.recordings_dir() / f"clean_{os.path.basename(raw_path)}")
                res = beat_studio.apply_fx_chain(
                    out_path,
                    clean_path,
                    [{"type": "noisegate", "threshold_db": -44.0, "ratio": 5.0}, {"type": "highpass", "cutoff_hz": 85.0}],
                    use_denoise=True,
                )
                if res.get("ok"):
                    out_path = clean_path

            take = None
            res: dict[str, Any] = {"ok": True, "path": out_path, "raw_path": raw_path, "duration": round(n_frames / self._sr, 2)}
            if self._project_id and plan and isinstance(plan, dict) and self._epoch0 is not None:
                # 1b: sayim / dongu / punch yerlesimi (zaman capasi ile)
                tid = str(plan.get("track_id") or self._track_id)
                ar = beat_studio.apply_recording(self._project_id, tid, out_path, plan, self._epoch0)
                if not ar.get("ok"):
                    res.update(ok=False, error=ar.get("error", "apply_failed"))
                    return res
                res.update({k: ar[k] for k in ("project", "take", "takes", "new_clip_ids", "mode") if k in ar})
                return res
            if self._project_id:
                tr_res = beat_studio.add_take_to_track(self._project_id, self._track_id, out_path, label="PC Mic Take",
                                                       start=self._timeline_start, from_recording=self._timeline_start is not None)
                take = tr_res.get("take")
            res["take"] = take
            return res


RECORDER = PcRecorder()


class LatencyListener:
    """Revize R2: alkis/tik testinde yalniz KAYDEDER. Tik arayuzde Web Audio ile (kullanicinin duydugu cikistan)
    calinir; arayuz tikin duvar saatini (1b saat capasi) stop()'a verir, gecikme kayittan hesaplanir."""

    MAX_SEC = 12.0

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._stream = None
        self._chunks: list[Any] = []
        self._sr = 48000
        self._epoch0: float | None = None
        self._frames = 0

    def _on_block(self, indata, frames: int) -> None:
        if self._epoch0 is None:
            self._epoch0 = time.time() - frames / float(self._sr or 48000)
        if self._frames < self.MAX_SEC * self._sr:
            self._chunks.append(indata.copy())
            self._frames += int(frames)

    def start(self, device_id: int | None = None, sr: int = 48000) -> dict[str, Any]:
        with self._lock:
            if RECORDER._recording:
                return {"ok": False, "error": "already_recording"}
            self._close()
            try:
                import sounddevice as sd
            except Exception:
                return {"ok": False, "error": "sounddevice_missing"}
            self._chunks, self._frames, self._epoch0, self._sr = [], 0, None, int(sr or 48000)
            try:
                self._stream = sd.InputStream(samplerate=self._sr, channels=1, dtype="float32",
                                              device=device_id if device_id is not None and device_id >= 0 else None,
                                              callback=lambda indata, frames, ti, st: self._on_block(indata, frames))
                self._stream.start()
            except Exception as exc:
                self._stream = None
                return {"ok": False, "error": str(exc)[:140]}
            return {"ok": True, "sr": self._sr}

    def _close(self) -> None:
        try:
            if self._stream is not None:
                self._stream.stop()
                self._stream.close()
        except Exception:
            pass
        self._stream = None

    def ready(self) -> bool:
        return self._epoch0 is not None

    def stop(self, play_wall: float) -> dict[str, Any]:
        """play_wall: tik dizisinin ilk orneginin calindigi duvar saati (epoch sn)."""
        with self._lock:
            self._close()
            if not self._chunks or self._epoch0 is None:
                return {"ok": False, "error": "no_signal", "reason": "silent_device"}
            import numpy as np
            rec = np.concatenate(self._chunks, axis=0).reshape(-1)
            self._chunks = []
            return beat_studio.latency_from_recording(rec, self._sr, self._epoch0, float(play_wall))

    def cancel(self) -> dict[str, Any]:
        with self._lock:
            self._close()
            self._chunks = []
            return {"ok": True}


LATENCY = LatencyListener()


class BoothServer:
    """iPhone 15 Pro Max kablosuz 48 kHz WAV kayit + canli Teleprompter HTTP koprusu."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._srv: ThreadingHTTPServer | None = None
        self._thread: threading.Thread | None = None
        self._port = 0
        self._token = ""
        self._project_id = ""
        self._track_id = "vocal1"
        self._last_upload: dict[str, Any] | None = None
        self._target = "track"                # 1e-2: "track" (proje kanali) | "idea" (fikir rafi)

    def set_target(self, project_id: str, track_id: str = "vocal1", target: str = "") -> None:
        self._project_id = project_id
        self._track_id = track_id or "vocal1"
        if target in ("track", "idea"):
            self._target = target

    def status(self) -> dict[str, Any]:
        running = self._srv is not None
        url = f"http://{_local_ip()}:{self._port}/?token={self._token}" if running and self._port and self._token else ""
        return {
            "ok": True,
            "running": running,
            "port": self._port,
            "token": self._token,
            "url": url,
            "project_id": self._project_id,
            "track_id": self._track_id,
            "target": self._target,
            "last_upload": self._last_upload,
        }

    def start(self, project_id: str = "", track_id: str = "vocal1", target: str = "") -> dict[str, Any]:
        with self._lock:
            self._project_id = project_id or self._project_id
            self._track_id = track_id or self._track_id
            if target in ("track", "idea"):
                self._target = target
            if self._srv is not None:
                return self.status()
            self._token = secrets.token_urlsafe(24)
            owner = self

            class _Handler(BaseHTTPRequestHandler):
                def log_message(self, fmt, *args):
                    return

                def _send_json(self, code: int, obj: dict[str, Any]):
                    raw = json.dumps(obj, ensure_ascii=False).encode("utf-8")
                    self.send_response(code)
                    self.send_header("Content-Type", "application/json; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.end_headers()
                    self.wfile.write(raw)

                def _check_auth(self) -> tuple[bool, bool]:
                    tok = owner._token
                    if not tok:
                        return False, False
                    hdr = (self.headers.get("X-Booth-Token") or "").strip()
                    if hdr and hmac.compare_digest(hdr, tok):
                        return True, False
                    raw_cookie = self.headers.get("Cookie") or ""
                    if raw_cookie:
                        try:
                            jar = SimpleCookie()
                            jar.load(raw_cookie)
                            morsel = jar.get("kami_booth_tok")
                            if morsel and morsel.value and hmac.compare_digest(morsel.value, tok):
                                return True, False
                        except Exception:
                            pass
                    q = urllib.parse.parse_qs(urllib.parse.urlsplit(self.path).query).get("token", [""])[0].strip()
                    if q and hmac.compare_digest(q, tok):
                        return True, True
                    return False, False

                def do_GET(self):
                    parsed = urllib.parse.urlsplit(self.path)
                    ok, via_query = self._check_auth()
                    if ok and via_query and parsed.path.startswith("/api/"):
                        ok = False   # v2.5.3: URL anahtari yalniz QR eslesmesinde (sayfa) gecerli; API cerez/baslik ister
                    if not ok:
                        code = 401 if parsed.path.startswith("/api/") else 403
                        return self._send_json(code, {"ok": False, "error": "unauthorized"})
                    if via_query:   # v2.5.3: cerezi kur, anahtarsiz temiz adrese yonlendir (gecmiste/ekranda token kalmasin)
                        self.send_response(303)
                        self.send_header("Set-Cookie", f"kami_booth_tok={owner._token}; HttpOnly; SameSite=Strict; Path=/")
                        self.send_header("Location", "/")
                        self.send_header("Content-Length", "0")
                        self.end_headers()
                        return
                    if parsed.path.startswith("/api/teleprompter"):
                        lyrics = ""
                        bpm = 120.0
                        name = "Kami Booth"
                        if owner._project_id:
                            lr = beat_studio.load_project(owner._project_id)
                            if lr.get("ok"):
                                p = lr["project"]
                                lyrics = p.get("lyrics", "")
                                bpm = float(p.get("bpm") or 120.0)
                                name = p.get("name", name)
                        return self._send_json(200, {"ok": True, "lyrics": lyrics, "bpm": bpm, "project_name": name,
                                                     "target": owner._target})

                    html_p = paths.WEB_DIR / "booth_mobile.html"
                    if not html_p.is_file():
                        return self._send_json(404, {"ok": False, "error": "booth_mobile_missing"})
                    raw = html_p.read_bytes()
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(raw)))
                    self.send_header("Set-Cookie", f"kami_booth_tok={owner._token}; HttpOnly; SameSite=Strict; Path=/")
                    self.end_headers()
                    self.wfile.write(raw)

                def do_POST(self):
                    parsed = urllib.parse.urlsplit(self.path)
                    ok, via_query = self._check_auth()
                    if not ok or via_query:
                        return self._send_json(401, {"ok": False, "error": "unauthorized"})
                    if not parsed.path.startswith("/api/upload_wav"):
                        return self._send_json(404, {"ok": False})
                    try:
                        ln = int(self.headers.get("Content-Length") or "0")
                        if ln <= 0 or ln > 120 * 1024 * 1024:
                            return self._send_json(400, {"ok": False, "error": "invalid_size"})
                        body = self.rfile.read(ln)
                        ctype = (self.headers.get("Content-Type") or "").lower()
                        target = (self.headers.get("X-Booth-Target") or "").strip().lower()
                        if "application/json" in ctype:
                            payload = json.loads(body.decode("utf-8"))
                            target = str(payload.get("target") or target).lower()
                            b64 = str(payload.get("data_url") or "").split(",")[-1]
                            wav_bytes = base64.b64decode(b64)
                        else:
                            wav_bytes = body
                        fname = f"iphone_booth_{int(time.time())}_{uuid.uuid4().hex[:4]}.wav"
                        out_p = beat_studio.recordings_dir() / fname
                        if "wav" in ctype or "application/json" in ctype or wav_bytes[:4] == b"RIFF":
                            out_p.write_bytes(wav_bytes)
                        else:   # v2.5.3: telefon kayit uygulamasindan gelen m4a/caf/mp3 -> 48 kHz WAV
                            raw_p = out_p.with_suffix(".src")
                            raw_p.write_bytes(wav_bytes)
                            ff = kami_beat._find_ffmpeg()
                            r_ = subprocess.run([ff, "-y", "-hide_banner", "-loglevel", "error", "-i", str(raw_p), "-ar", "48000", str(out_p)],
                                                capture_output=True, timeout=300, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0)) if ff else None
                            raw_p.unlink(missing_ok=True)
                            if not r_ or r_.returncode != 0 or not out_p.is_file():
                                return self._send_json(400, {"ok": False, "error": "unsupported_audio"})
                        if target not in ("track", "idea"):
                            target = owner._target
                        if target == "idea":   # 1e-2: fikir rafina (projeye dokunmaz)
                            from app.core import beat_ideas
                            nm = urllib.parse.unquote(self.headers.get("X-Booth-Name") or "")
                            ir = beat_ideas.add_idea(str(out_p), name=os.path.splitext(nm)[0][:60], source="iphone", move=True)
                            idea = ir.get("item")
                            owner._last_upload = {"path": (idea or {}).get("file", str(out_p)), "take": None, "idea": idea,
                                                  "target": "idea", "ts": time.time()}
                            return self._send_json(200 if ir.get("ok") else 500, {"ok": bool(ir.get("ok")), "target": "idea",
                                                                                  "idea": idea, "error": ir.get("error")})
                        take = None
                        if owner._project_id:
                            tr = beat_studio.add_take_to_track(owner._project_id, owner._track_id, str(out_p), label="iPhone Booth Take")
                            take = tr.get("take")
                        owner._last_upload = {"path": str(out_p), "take": take, "target": "track", "ts": time.time()}
                        return self._send_json(200, {"ok": True, "path": str(out_p), "take": take, "target": "track"})
                    except Exception as exc:
                        return self._send_json(500, {"ok": False, "error": str(exc)[:120]})

            self._srv = ThreadingHTTPServer(("0.0.0.0", 0), _Handler)
            self._port = int(self._srv.server_address[1])
            self._thread = threading.Thread(target=self._srv.serve_forever, daemon=True, name="kami-booth-http")
            self._thread.start()
            return self.status()

    def stop(self) -> dict[str, Any]:
        with self._lock:
            if self._srv is not None:
                try:
                    self._srv.shutdown()
                    self._srv.server_close()
                except Exception:
                    pass
                self._srv = None
                self._port = 0
                self._token = ""
                self._thread = None
            return {"ok": True}


BOOTH = BoothServer()
