"""Opsiyonel Discord Rich Presence (saf Python IPC — harici kutuphane gerektirmez).

Windows'ta yerel Discord named pipe (\\\\.\\pipe\\discord-ipc-0..9) uzerinden calan sarki/video
bilgisini paylasir. Discord acik degilse veya ayar kapaliysa sifir maliyetle pas gecer.
"""
from __future__ import annotations

import json
import logging
import os
import struct
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

# Varsayilan Kami RPC istemci kimligi (kullanici isterse ayar/env ile degistirebilir)
DEFAULT_CLIENT_ID = os.environ.get("KAMI_DISCORD_CLIENT_ID", "1312041260000000000")


class DiscordPresence:
    """Discord Masaustu RPC istemcisi."""

    def __init__(self, client_id: str = DEFAULT_CLIENT_ID) -> None:
        self._client_id = client_id
        self._lock = threading.Lock()
        self._pipe = None
        self._last_sent = 0.0
        self._last_sig = ""

    def _connect(self) -> bool:
        if os.name != "nt":
            return False
        if self._pipe is not None:
            return True
        for idx in range(10):
            path = f"\\\\.\\pipe\\discord-ipc-{idx}"
            try:
                f = open(path, "r+b", buffering=0)
                self._pipe = f
                self._write_frame(0, {"v": 1, "client_id": self._client_id})
                self._read_frame()
                return True
            except OSError:
                self._close_pipe()
                continue
            except Exception:
                self._close_pipe()
                continue
        return False

    def _write_frame(self, op: int, payload: dict[str, Any]) -> None:
        if self._pipe is None:
            return
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        pkt = struct.pack("<II", op, len(data)) + data
        self._pipe.write(pkt)
        self._pipe.flush()

    def _read_frame(self) -> tuple[int, dict[str, Any]]:
        if self._pipe is None:
            return (0, {})
        hdr = self._pipe.read(8)
        if len(hdr) < 8:
            return (0, {})
        op, length = struct.unpack("<II", hdr)
        body = self._pipe.read(min(length, 65536))
        try:
            return (op, json.loads(body.decode("utf-8", errors="replace")))
        except Exception:
            return (op, {})

    def _close_pipe(self) -> None:
        if self._pipe is not None:
            try:
                self._pipe.close()
            except Exception:
                pass
            self._pipe = None

    def update(
        self,
        title: str,
        artist: str = "",
        mode: str = "Kami Player",
        duration: float = 0.0,
        elapsed: float = 0.0,
        paused: bool = False,
    ) -> dict[str, Any]:
        t = str(title or "").strip()[:120]
        a = str(artist or "").strip()[:120]
        m = str(mode or "Kami Player").strip()[:60]
        if not t:
            return self.clear()
        sig = f"{t}|{a}|{m}|{paused}"
        now = time.time()
        with self._lock:
            if sig == self._last_sig and now - self._last_sent < 10.0:
                return {"ok": True, "throttled": True}
            if not self._connect():
                return {"ok": False, "error": "discord_not_running"}
            state_txt = f"{a} · {m}" if a else m
            if paused:
                state_txt = f"⏸ {state_txt}"
            activity: dict[str, Any] = {
                "details": t,
                "state": state_txt[:120],
                "assets": {"large_text": "Kami"},
            }
            if not paused and duration > 0 and elapsed >= 0:
                start_ts = int(now - max(0.0, elapsed))
                end_ts = int(start_ts + duration)
                activity["timestamps"] = {"start": start_ts, "end": end_ts}
            payload = {
                "cmd": "SET_ACTIVITY",
                "args": {"pid": os.getpid(), "activity": activity},
                "nonce": f"kami-{int(now * 1000)}",
            }
            try:
                self._write_frame(1, payload)
                self._last_sent = now
                self._last_sig = sig
                return {"ok": True}
            except Exception:
                self._close_pipe()
                return {"ok": False, "error": "ipc_write_failed"}

    def clear(self) -> dict[str, Any]:
        with self._lock:
            self._last_sig = ""
            if self._pipe is None:
                return {"ok": True}
            try:
                self._write_frame(1, {"cmd": "SET_ACTIVITY", "args": {"pid": os.getpid(), "activity": None}, "nonce": "clear"})
                return {"ok": True}
            except Exception:
                self._close_pipe()
                return {"ok": False}

    def close(self) -> None:
        self.clear()
        with self._lock:
            self._close_pipe()


PRESENCE = DiscordPresence()
