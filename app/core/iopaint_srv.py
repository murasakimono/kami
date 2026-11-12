"""Kami Picture yapay zeka arka ucu: IOPaint (Apache-2.0) yerel sunucusu, ayri ortamda (media-env/iopaint).

LaMa nesne silme / leke iyilestirme (inpaint), SAM-HQ tikla-sec (SAM2 Windows torch'unda "No available kernel" veriyor), RMBG arka plan kaldirma, Real-ESRGAN 4x buyutme,
GFPGAN yuz duzeltme. Ilk kullanimda kurulur (onayla, ~4.5 GB); modeller kendi klasorune iner.
Sunucu istek gelince acilir, 10 dk bos kalirsa kapanir (GPU bellegi oyunlara kalsin).
"""
from __future__ import annotations

import base64
import json
import logging
import socket
import subprocess
import threading
import time
import urllib.request
from typing import Any

from app import paths
from app.core import aitools

log = logging.getLogger("kami")
NOWIN = 0x08000000
IDLE_SEC = 600


class IOPaint:
    def __init__(self) -> None:
        self.proc: subprocess.Popen | None = None
        self.port = 0
        self.lock = threading.Lock()
        self.last = 0.0
        self.state = "off"     # off | starting | ready | error
        self.error = ""
        self.device = ""
        threading.Thread(target=self._idle, name="kami-iopaint-idle", daemon=True).start()

    def _idle(self) -> None:
        while True:
            time.sleep(30)
            if self.proc and self.proc.poll() is None and time.time() - self.last > IDLE_SEC:
                log.info("IOPaint bosta, kapatiliyor")
                self.stop()

    def stop(self) -> None:
        p, self.proc = self.proc, None
        self.state = "off"
        if p and p.poll() is None:
            p.terminate()

    def _cuda(self) -> bool:
        try:
            r = subprocess.run([aitools.python_exe("iopaint"), "-c", "import torch;print(torch.cuda.is_available())"],
                               capture_output=True, text=True, timeout=60, creationflags=NOWIN, env=aitools._clean_env())
            return r.stdout.strip().endswith("True")
        except Exception:
            return False

    def ensure(self, timeout: float = 900) -> None:
        """Sunucuyu acar ve hazir olana kadar bekler (ilk acilista modeller iner)."""
        self.last = time.time()
        with self.lock:
            if self.proc and self.proc.poll() is None and self.state == "ready":
                return
            if not aitools.installed("iopaint"):
                raise RuntimeError("not_installed")
            if not (self.proc and self.proc.poll() is None):
                with socket.socket() as s:
                    s.bind(("127.0.0.1", 0))
                    self.port = s.getsockname()[1]
                dev = "cuda" if self._cuda() else "cpu"
                self.device = dev
                mdir = aitools.models_dir("iopaint")
                cmd = [aitools.python_exe("iopaint"), "-m", "iopaint", "start", "--host", "127.0.0.1", "--port", str(self.port),
                       "--model", "lama", "--device", dev, "--model-dir", mdir,
                       "--enable-interactive-seg", "--interactive-seg-model", "sam_hq_vit_b", "--interactive-seg-device", dev,
                       "--enable-remove-bg", "--remove-bg-device", dev,
                       "--enable-realesrgan", "--realesrgan-device", dev,
                       "--enable-gfpgan", "--gfpgan-device", dev]
                logf = open(paths.DATA_DIR / "iopaint.log", "a", encoding="utf-8")   # noqa: SIM115
                self.state, self.error = "starting", ""
                log.info("IOPaint baslatiliyor (%s, port %s)", dev, self.port)
                self.proc = subprocess.Popen(cmd, stdout=logf, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                             creationflags=NOWIN, env=aitools._clean_env(), cwd=mdir)
            end = time.time() + timeout
            while time.time() < end:
                if self.proc.poll() is not None:
                    self.state, self.error = "error", "IOPaint kapandi (data/iopaint.log)"
                    raise RuntimeError(self.error)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/v1/server-config", timeout=3):
                        self.state = "ready"
                        return
                except Exception:
                    time.sleep(1.5)
            self.state, self.error = "error", "zaman asimi"
            raise RuntimeError("IOPaint baslamadi (zaman asimi)")

    def _post(self, path: str, body: dict[str, Any], timeout: float = 600) -> bytes:
        self.ensure()
        self.last = time.time()
        req = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=timeout) as r:
            data = r.read()
        self.last = time.time()
        return data

    @staticmethod
    def _b64(data_url: str) -> str:
        return data_url.split(",", 1)[1] if "," in data_url else data_url

    def inpaint(self, image: str, mask: str) -> str:
        """LaMa: maskedeki alani cevreye uygun doldurur (nesne silme, leke, yama)."""
        out = self._post("/api/v1/inpaint", {"image": self._b64(image), "mask": self._b64(mask), "hd_strategy": "Crop",
                                             "hd_strategy_crop_trigger_size": 1280, "hd_strategy_crop_margin": 196})
        return "data:image/png;base64," + base64.b64encode(out).decode()

    def plugin(self, name: str, image: str, clicks: list | None = None, scale: float = 4.0, mask: bool = False) -> str:
        out = self._post("/api/v1/run_plugin_gen_mask" if mask else "/api/v1/run_plugin_gen_image",
                         {"name": name, "image": self._b64(image), "clicks": clicks or [], "scale": scale})
        return "data:image/png;base64," + base64.b64encode(out).decode()


SERVER = IOPaint()
