"""Kami Booth: PC mikrofonu (ATK N9) 48 kHz kayit + iPhone 15 Pro Max kablosuz WAV & Teleprompter sunucusu."""
from __future__ import annotations

import base64
import hmac
import json
import logging
import os
import secrets
import socket
import threading
import time
import urllib.parse
import uuid
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from app import paths
from app.core import beat_studio

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

    def status(self) -> dict[str, Any]:
        return {
            "ok": True,
            "recording": self._recording,
            "elapsed": round(time.time() - self._started_at, 1) if self._recording else 0.0,
            "project_id": self._project_id,
            "track_id": self._track_id,
        }

    def start(self, project_id: str = "", track_id: str = "vocal1", device_id: int | None = None, sr: int = 48000) -> dict[str, Any]:
        with self._lock:
            if self._recording:
                return {"ok": False, "error": "already_recording"}
            try:
                import sounddevice as sd
                self._chunks = []
                self._sr = int(sr or 48000)
                self._project_id = project_id
                self._track_id = track_id or "vocal1"

                def _cb(indata, frames, time_info, status):
                    self._chunks.append(indata.copy())

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

    def stop(self, ai_clean: bool = True) -> dict[str, Any]:
        with self._lock:
            if not self._recording:
                return {"ok": False, "error": "not_recording"}
            try:
                if self._stream is not None:
                    self._stream.stop()
                    self._stream.close()
            finally:
                self._stream = None
                self._recording = False

            if not self._chunks:
                return {"ok": False, "error": "empty_recording"}

            import numpy as np
            mono = np.concatenate(self._chunks, axis=0)
            stereo = np.repeat(mono, 2, axis=1).astype("float32")
            fname = f"pc_mic_{int(time.time())}_{uuid.uuid4().hex[:4]}.wav"
            out_path = str(beat_studio.recordings_dir() / fname)
            beat_studio._write_wav_np(out_path, stereo, self._sr)

            if ai_clean:
                clean_path = str(beat_studio.recordings_dir() / f"clean_{fname}")
                res = beat_studio.apply_fx_chain(
                    out_path,
                    clean_path,
                    [{"type": "noisegate", "threshold_db": -44.0, "ratio": 5.0}, {"type": "highpass", "cutoff_hz": 85.0}],
                    use_denoise=True,
                )
                if res.get("ok"):
                    out_path = clean_path

            take = None
            if self._project_id:
                tr_res = beat_studio.add_take_to_track(self._project_id, self._track_id, out_path, label="PC Mic Take")
                take = tr_res.get("take")
            return {"ok": True, "path": out_path, "take": take, "duration": round(len(stereo) / self._sr, 2)}


RECORDER = PcRecorder()


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

    def set_target(self, project_id: str, track_id: str = "vocal1") -> None:
        self._project_id = project_id
        self._track_id = track_id or "vocal1"

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
            "last_upload": self._last_upload,
        }

    def start(self, project_id: str = "", track_id: str = "vocal1") -> dict[str, Any]:
        with self._lock:
            self._project_id = project_id or self._project_id
            self._track_id = track_id or self._track_id
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
                    ok, _ = self._check_auth()
                    if not ok:
                        code = 401 if parsed.path.startswith("/api/") else 403
                        return self._send_json(code, {"ok": False, "error": "unauthorized"})
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
                        return self._send_json(200, {"ok": True, "lyrics": lyrics, "bpm": bpm, "project_name": name})

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
                    ok, _ = self._check_auth()
                    if not ok:
                        return self._send_json(401, {"ok": False, "error": "unauthorized"})
                    if not parsed.path.startswith("/api/upload_wav"):
                        return self._send_json(404, {"ok": False})
                    try:
                        ln = int(self.headers.get("Content-Length") or "0")
                        if ln <= 0 or ln > 120 * 1024 * 1024:
                            return self._send_json(400, {"ok": False, "error": "invalid_size"})
                        body = self.rfile.read(ln)
                        ctype = (self.headers.get("Content-Type") or "").lower()
                        if "application/json" in ctype:
                            payload = json.loads(body.decode("utf-8"))
                            b64 = str(payload.get("data_url") or "").split(",")[-1]
                            wav_bytes = base64.b64decode(b64)
                        else:
                            wav_bytes = body
                        fname = f"iphone_booth_{int(time.time())}_{uuid.uuid4().hex[:4]}.wav"
                        out_p = beat_studio.recordings_dir() / fname
                        out_p.write_bytes(wav_bytes)
                        take = None
                        if owner._project_id:
                            tr = beat_studio.add_take_to_track(owner._project_id, owner._track_id, str(out_p), label="iPhone Booth Take")
                            take = tr.get("take")
                        owner._last_upload = {"path": str(out_p), "take": take, "ts": time.time()}
                        return self._send_json(200, {"ok": True, "path": str(out_p), "take": take})
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
