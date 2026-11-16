"""Kami Kasa gomme istemcisi: 'kasa' arac ortaminda (fastembed/ONNX, CPU) kalici bir alt surec.

Modeller bir kez yuklenir, sonraki aramalar milisaniyeler surer. 10 dk bosta kalan surec kapanir.
Arac kurulu degilse available() False doner: Kasa FTS5 tam metin aramasiyla calismaya devam eder.
"""
from __future__ import annotations

import itertools
import json
import logging
import os
import subprocess
import tempfile
import threading
import time
from typing import Any

log = logging.getLogger(__name__)
IDLE_SEC = 600.0


class _Worker:
    def __init__(self) -> None:
        self._p: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._ids = itertools.count(1)
        self._last = 0.0
        threading.Thread(target=self._reaper, name="kami-kasa-idle", daemon=True).start()

    def _start(self) -> None:
        from app import paths
        from app.core import aitools
        fd, argfile = tempfile.mkstemp(prefix="kami_kasa_", suffix=".json")
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump([aitools.models_dir("kasa")], f)
        self._p = subprocess.Popen(
            [aitools.python_exe("kasa"), "-m", "app.tools.kasa_embed_run", "@" + argfile],
            cwd=str(paths.TOOLSRC_DIR), stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
            text=True, encoding="utf-8", errors="replace", creationflags=aitools.NO_WINDOW,
            env={**aitools._clean_env(), "HF_HUB_DISABLE_TELEMETRY": "1"})
        line = self._p.stdout.readline() if self._p.stdout else ""   # {"ready": true}
        try:
            os.remove(argfile)
        except OSError:
            pass
        if '"ready"' not in line:
            self.close()
            raise RuntimeError("Kasa gomme sureci baslamadi")

    def call(self, req: dict[str, Any], timeout: float = 300.0) -> dict[str, Any]:
        with self._lock:
            if self._p is None or self._p.poll() is not None:
                self._start()
            rid = next(self._ids)
            assert self._p and self._p.stdin and self._p.stdout
            self._p.stdin.write(json.dumps({**req, "id": rid}, ensure_ascii=False) + "\n")
            self._p.stdin.flush()
            t0 = time.monotonic()
            while time.monotonic() - t0 < timeout:
                line = self._p.stdout.readline()
                if not line:
                    self.close()
                    raise RuntimeError("Kasa gomme sureci kapandi")
                try:
                    msg = json.loads(line)
                except ValueError:
                    continue
                if msg.get("id") == rid:
                    self._last = time.monotonic()
                    if msg.get("error"):
                        raise RuntimeError(msg["error"])
                    return msg
            self.close()
            raise TimeoutError("Kasa gomme zaman asimi")

    def close(self) -> None:
        p, self._p = self._p, None
        if p and p.poll() is None:
            try:
                p.kill()
            except OSError:
                pass

    def _reaper(self) -> None:
        while True:
            time.sleep(30)
            if self._p is not None and self._last and time.monotonic() - self._last > IDLE_SEC and not self._lock.locked():
                with self._lock:
                    self.close()


_W: _Worker | None = None


def available() -> bool:
    try:
        from app.core import aitools
        return aitools.installed("kasa")
    except Exception:
        return False


def _w() -> _Worker:
    global _W
    if _W is None:
        _W = _Worker()
    return _W


def embed_text(texts: list[str]) -> list[list[float]]:
    return _w().call({"op": "text", "texts": texts}).get("vecs") or []


def embed_images(paths_: list[str]) -> list[list[float]]:
    return _w().call({"op": "image", "paths": paths_}, timeout=900).get("vecs") or []


def embed_clip_text(texts: list[str]) -> list[list[float]]:
    return _w().call({"op": "clip_text", "texts": texts}).get("vecs") or []


def shutdown() -> None:
    if _W is not None:
        _W.close()
