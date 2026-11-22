"""Oracle Cloud (Frankfurt) ayri VM sifreli Kami Relay istemcisi & indirme cokme kurtarma."""
from __future__ import annotations

import hashlib
import hmac
import json
import logging
import time
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger(__name__)


def _crash_file() -> Path:
    return paths.DATA_DIR / "download_crash_recovery.json"


def _sign_payload(secret: str, ts: str, body: bytes) -> str:
    mac = hmac.new(secret.encode("utf-8"), f"{ts}.".encode("utf-8") + body, hashlib.sha256)
    return mac.hexdigest()


def relay_ping(relay_url: str, secret: str = "") -> dict[str, Any]:
    """Oracle Relay VM baglanti ve HMAC imza dogrulama testi."""
    import requests
    url = str(relay_url or "").strip().rstrip("/")
    if not url:
        return {"ok": False, "error": "empty_relay_url"}
    ts = str(int(time.time()))
    sig = _sign_payload(secret or "", ts, b"ping") if secret else ""
    try:
        r = requests.get(
            f"{url}/api/health",
            headers={"X-Kami-Ts": ts, "X-Kami-Sig": sig},
            timeout=6,
        )
        if r.status_code == 200:
            return {"ok": True, "status": r.json() if r.headers.get("content-type", "").startswith("application/json") else {"alive": True}}
        return {"ok": False, "error": f"http_{r.status_code}"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def relay_push_event(relay_url: str, secret: str, event_type: str, payload: dict[str, Any]) -> dict[str, Any]:
    """Indirme tamamlandi / bildirim / durum olayini HMAC-SHA256 imzali olarak Oracle Relay'e gonderir."""
    import requests
    url = str(relay_url or "").strip().rstrip("/")
    if not url:
        return {"ok": False, "error": "empty_relay_url"}
    body = json.dumps({"type": event_type, "payload": payload, "ts": time.time()}, ensure_ascii=False).encode("utf-8")
    ts = str(int(time.time()))
    sig = _sign_payload(secret or "", ts, body)
    try:
        r = requests.post(
            f"{url}/api/events",
            data=body,
            headers={"Content-Type": "application/json", "X-Kami-Ts": ts, "X-Kami-Sig": sig},
            timeout=8,
        )
        return {"ok": r.status_code == 200, "code": r.status_code}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:120]}


def relay_pull_queue(relay_url: str, secret: str) -> dict[str, Any]:
    """iPhone mobil veriden Oracle Relay'e gonderilen uzaktan indirme linklerini ceker."""
    import requests
    url = str(relay_url or "").strip().rstrip("/")
    if not url:
        return {"ok": False, "items": [], "error": "empty_relay_url"}
    ts = str(int(time.time()))
    sig = _sign_payload(secret or "", ts, b"pull")
    try:
        r = requests.get(
            f"{url}/api/queue/pull",
            headers={"X-Kami-Ts": ts, "X-Kami-Sig": sig},
            timeout=8,
        )
        if r.status_code == 200:
            data = r.json() or {}
            return {"ok": True, "items": list(data.get("items") or [])}
        return {"ok": False, "items": [], "error": f"http_{r.status_code}"}
    except Exception as exc:
        return {"ok": False, "items": [], "error": str(exc)[:120]}


def save_crash_snapshot(downloads: list[dict[str, Any]]) -> dict[str, Any]:
    """Aktif/bekleyen indirmelerin kurtarma goruntusunu diske yazar."""
    active = [
        {"id": d.get("id"), "url": d.get("url"), "title": d.get("title"), "status": d.get("status"), "dir": d.get("dir")}
        for d in (downloads or [])
        if d.get("status") in ("active", "queued", "paused")
    ]
    _crash_file().write_text(json.dumps({"ts": time.time(), "items": active}, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "count": len(active)}


def load_crash_snapshot() -> dict[str, Any]:
    f = _crash_file()
    if not f.is_file():
        return {"ok": True, "items": []}
    try:
        data = json.loads(f.read_text(encoding="utf-8"))
        return {"ok": True, "items": list(data.get("items") or []), "ts": data.get("ts", 0)}
    except Exception as exc:
        return {"ok": False, "items": [], "error": str(exc)[:120]}
