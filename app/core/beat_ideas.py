"""Kami Beat Asama 1e-2: fikir rafi (kisa sesli notlar, 10-30 sn).

Kaynaklar: PC mikrofonundan hizli kayit (Kabin kaydedicisi, projesiz), iPhone Booth (sunucuda hedef = fikir rafi),
dosya surukle-birak. Her fikir: ad, etiketler, not, istege bagli baglanti (proje + soz satiri numarasi).
Kalicilik: recordings_dir()/ideas.json + recordings_dir()/ideas/ (ses dosyalari buraya kopyalanir/tasinir).
"""
from __future__ import annotations

import json
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.core import beat_studio

log = logging.getLogger(__name__)

QUICK_MAX_SEC = 30.0          # hizli kayit ust siniri (arayuz otomatik durdurur)
SOURCES = ("pc", "iphone", "file")
_LOCK = threading.Lock()


def ideas_dir() -> Path:
    d = beat_studio.recordings_dir() / "ideas"
    d.mkdir(parents=True, exist_ok=True)
    return d


def ideas_path() -> Path:
    return beat_studio.recordings_dir() / "ideas.json"


def load_ideas() -> list[dict[str, Any]]:
    fp = ideas_path()
    if not fp.is_file():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        return [i for i in (items or []) if isinstance(i, dict) and i.get("id")]
    except Exception:
        log.warning("ideas.json okunamadi", exc_info=True)
        return []


def save_ideas(items: list[dict[str, Any]]) -> None:
    beat_studio._atomic_write(ideas_path(), json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=1))


def _tags(v: Any) -> list[str]:
    if isinstance(v, str):
        v = re.split(r"[,#]", v)
    out = []
    for t in v or []:
        t = str(t).strip().lower()[:24]
        if t and t not in out:
            out.append(t)
    return out[:12]


def _inside_ideas(p: str) -> bool:
    try:
        return ideas_dir().resolve() in Path(p).resolve().parents
    except Exception:
        return False


def add_idea(path: str, name: str = "", tags: Any = None, note: str = "", source: str = "file",
             move: bool = False) -> dict[str, Any]:
    """Ses dosyasini ideas/ altina alir (move=True: Kami'nin kendi ham kaydi tasinir, degilse kopyalanir)."""
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "not_found"}
    src = Path(path)
    if _inside_ideas(path):
        dst = src
    else:
        stem = re.sub(r"[^\w\-]+", "_", src.stem)[:40] or "fikir"
        dst = ideas_dir() / f"{time.strftime('%Y%m%d_%H%M%S')}_{stem}_{uuid.uuid4().hex[:4]}{src.suffix.lower() or '.wav'}"
        try:
            if move:
                shutil.move(str(src), dst)
            else:
                shutil.copy2(str(src), dst)
        except Exception as exc:
            return {"ok": False, "error": "copy_failed", "detail": str(exc)[:120]}
    dur = beat_studio.audio_duration(str(dst))
    wf = beat_studio.waveform_peaks(str(dst), 48)
    with _LOCK:
        items = load_ideas()
        n = len(items) + 1
        item = {"id": "i_" + uuid.uuid4().hex[:8], "name": str(name or "").strip()[:60] or f"Fikir {n}",
                "tags": _tags(tags), "note": str(note or "")[:500], "file": str(dst),
                "duration": round(float(dur or 0.0), 2), "source": source if source in SOURCES else "file",
                "created_at": time.time(), "link": None, "peaks": wf.get("peaks") or []}
        items.insert(0, item)
        save_ideas(items)
    return {"ok": True, "item": item, "long": float(dur or 0.0) > QUICK_MAX_SEC + 0.5}


def list_ideas(query: str = "", tag: str = "", project: str = "") -> dict[str, Any]:
    q = str(query or "").strip().lower()
    tg = str(tag or "").strip().lower()
    out = []
    for it in load_ideas():
        if tg and tg not in (it.get("tags") or []):
            continue
        if project and ((it.get("link") or {}).get("project") != project):
            continue
        hay = " ".join([str(it.get("name") or ""), str(it.get("note") or ""), " ".join(it.get("tags") or [])]).lower()
        if q and not all(w in hay for w in q.split()):
            continue
        out.append(dict(it, exists=os.path.isfile(str(it.get("file") or ""))))
    tags = sorted({t for it in load_ideas() for t in (it.get("tags") or [])})
    return {"ok": True, "items": out, "tags": tags}


def update_idea(idea_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    with _LOCK:
        items = load_ideas()
        it = next((i for i in items if i.get("id") == idea_id), None)
        if it is None:
            return {"ok": False, "error": "not_found"}
        if "name" in fields and str(fields["name"] or "").strip():
            it["name"] = str(fields["name"]).strip()[:60]
        if "note" in fields:
            it["note"] = str(fields.get("note") or "")[:500]
        if "tags" in fields:
            it["tags"] = _tags(fields.get("tags"))
        save_ideas(items)
        return {"ok": True, "item": it}


def remove_idea(idea_id: str) -> dict[str, Any]:
    with _LOCK:
        items = load_ideas()
        it = next((i for i in items if i.get("id") == idea_id), None)
        if it is None:
            return {"ok": False, "error": "not_found"}
        save_ideas([i for i in items if i.get("id") != idea_id])
    f = str(it.get("file") or "")
    if f and _inside_ideas(f):
        try:
            Path(f).unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}


def link_idea(idea_id: str, pid: str = "", line: int = -1) -> dict[str, Any]:
    """pid bos ya da line < 0 -> baglanti kaldirilir. line: soz metnindeki satir indeksi (0 tabanli)."""
    with _LOCK:
        items = load_ideas()
        it = next((i for i in items if i.get("id") == idea_id), None)
        if it is None:
            return {"ok": False, "error": "not_found"}
        it["link"] = {"project": str(pid), "line": int(line)} if pid and int(line) >= 0 else None
        save_ideas(items)
        return {"ok": True, "item": it}


def ideas_for_project(pid: str) -> dict[str, Any]:
    """{satir: [{id, name, file, duration}]} - soz panelindeki kucuk mikrofon ikonlari icin."""
    by_line: dict[str, list[dict[str, Any]]] = {}
    for it in load_ideas():
        ln = it.get("link") or {}
        if ln.get("project") == pid and int(ln.get("line", -1)) >= 0:
            by_line.setdefault(str(int(ln["line"])), []).append(
                {"id": it["id"], "name": it.get("name", ""), "file": it.get("file", ""), "duration": it.get("duration", 0)})
    return {"ok": True, "lines": by_line}


def add_idea_to_project(pid: str, idea_id: str, track_id: str = "vocal1", start: float = -1.0) -> dict[str, Any]:
    it = next((i for i in load_ideas() if i.get("id") == idea_id), None)
    if it is None:
        return {"ok": False, "error": "not_found"}
    if not os.path.isfile(str(it.get("file") or "")):
        return {"ok": False, "error": "file_missing"}
    return beat_studio.add_take_to_track(pid, track_id or "vocal1", str(it["file"]), label=f"Fikir: {it.get('name', '')}"[:60],
                                         start=None if start is None or float(start) < 0 else float(start))
