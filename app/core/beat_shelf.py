"""Kami Beat Asama 1e-1: beat rafi + lisans takibi.

Kullanicinin verdigi bir YouTube (veya yt-dlp'nin destekledigi baska) baglantisindaki beat, Kami'nin mevcut
yt-dlp motoruyla (app.engines.ytdlp_engine.MediaJob, yalniz ses / mp3 320) indirilir ve rafa duser.
Raf: recordings_dir()/beat_shelf.json, dosyalar recordings_dir()/beats/.

Lisans: video aciklamasi + basliktan anahtar sozcuk TAHMINI (kullanici duzeltebilir; user_set=True olur):
    license = {kind: free_nonprofit|free_profit|credit_required|lease_required|unknown, credit_text, evidence[]}
Yayin oncesi uyari (release_warnings): bounce/disa aktarmada beat ticari kullanima kapaliysa / lisans gerekiyorsa
ya da kredi zorunluysa gosterilir.
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
import uuid
from pathlib import Path
from typing import Any, Callable

from app.core import beat_studio

log = logging.getLogger(__name__)

LICENSE_KINDS = ("free_nonprofit", "free_profit", "credit_required", "lease_required", "unknown")
LICENSE_LABELS = {
    "free_nonprofit": "Ücretsiz · yalnız kâr amacı gütmeyen",
    "free_profit": "Ücretsiz · ticari dahil",
    "credit_required": "Ücretsiz · kredi zorunlu",
    "lease_required": "Lisans gerekli (lease / satın al)",
    "unknown": "Bilinmiyor",
}
_LOCK = threading.Lock()
_PROGRESS: dict[str, Any] = {"phase": "", "pct": 0.0, "title": "", "error": ""}

# --- anahtar sozcukler (kucuk harf, aciklama + baslik) ---
_FREE_PROFIT = (r"free\s*(?:for|4)\s*(?:profit|commercial)", r"free\s+to\s+use\s+(?:for\s+)?(?:profit|commercial)",
                r"free\s+for\s+monetiz", r"royalty[\s-]*free\s+(?:for\s+)?commercial", r"100\s*%\s*free",
                r"free\s+for\s+(?:any|all)\s+use", r"ticari\s+kullan[ıi]m(?:a)?\s+(?:serbest|[üu]cretsiz|a[çc][ıi]k)")
_FREE_NONPROFIT = (r"free\s*(?:for|4)\s*non[\s-]*(?:profit|commercial)", r"non[\s-]*(?:profit|commercial)\s+(?:use\s+)?only",
                   r"not\s+for\s+(?:profit|commercial)", r"free\s+download\s+for\s+non",
                   r"for\s+non[\s-]*profit\s+use", r"ticari\s+olmayan", r"kar\s+amac[ıi]\s+g[üu]tmeyen")
_LEASE = (r"\bpurchase\b", r"\bbuy\b", r"\blease\b", r"beatstars", r"airbit", r"traktrain", r"exclusive\s+rights",
          r"\buntagged\b", r"\blicen[cs]e\b", r"\bsat[ıi]n\s+al", r"\blisans\b")
_CREDIT = (r"\bcredit\b", r"must\s+credit", r"give\s+credit", r"credit\s+(?:me|required|the\s+producer)", r"\bkredi\b")
_FREE_TAG = (r"[\[\(]\s*free\s*[\]\)]", r"\bfree\s+(?:type\s+)?beat\b")
_PROD = re.compile(r"\(?\s*\bprod(?:uced)?\b\.?\s*(?:by|x)?\s*[:\-]?\s*([^\n\|\)\]\(\[,]{2,40})", re.I)


def _find(patterns: tuple[str, ...], text: str) -> list[str]:
    ev = []
    for p in patterns:
        m = re.search(p, text, re.I)
        if m:
            a, b = max(0, m.start() - 25), min(len(text), m.end() + 25)
            ev.append(text[a:b].replace("\n", " ").strip())
    return ev


def guess_producer(title: str = "", description: str = "", uploader: str = "") -> str:
    for src in (title, description):
        m = _PROD.search(src or "")
        if m:
            name = re.sub(r"\s+", " ", m.group(1)).strip(" .-_*")
            name = re.split(r"\s+(?:type\s+beat|beat|instrumental|bpm)\b", name, flags=re.I)[0].strip(" .-_*")
            if name and len(name) >= 2:
                return name[:40]
    return str(uploader or "").strip()[:40]


def infer_license(description: str = "", title: str = "", uploader: str = "") -> dict[str, Any]:
    """Aciklama metninden lisans TAHMINI. Oncelik: acik 'free for profit' (kredi istenirse credit_required) >
    'free for non-profit' > satin alma / lease > yalniz kredi > basliktaki [FREE] (guvenli taraf: non-profit) > bilinmiyor."""
    text = f"{title or ''}\n{description or ''}"
    low = text.lower()
    producer = guess_producer(title, description, uploader)
    credit_text = f"prod. by {producer}" if producer else ""
    fp, fnp, lease, cred = _find(_FREE_PROFIT, low), _find(_FREE_NONPROFIT, low), _find(_LEASE, low), _find(_CREDIT, low)
    if fp and not fnp:
        kind, ev = ("credit_required", fp + cred) if cred else ("free_profit", fp)
    elif fnp:
        kind, ev = "free_nonprofit", fnp + lease[:1]
    elif lease:
        kind, ev = "lease_required", lease
    elif cred:
        kind, ev = "credit_required", cred
    elif _find(_FREE_TAG, low):
        kind, ev = "free_nonprofit", _find(_FREE_TAG, low)
    else:
        kind, ev = "unknown", []
    ev = list(dict.fromkeys(ev))
    return {"kind": kind, "credit_text": credit_text, "evidence": ev[:3], "guessed": True, "user_set": False}


def parse_bpm_key(text: str) -> dict[str, Any]:
    out: dict[str, Any] = {"bpm": 0.0, "key": ""}
    t = str(text or "")
    m = re.search(r"\b(\d{2,3}(?:[.,]\d)?)\s*bpm\b", t, re.I) or re.search(r"\bbpm\s*[:\-]?\s*(\d{2,3}(?:[.,]\d)?)\b", t, re.I)
    if m:
        v = float(m.group(1).replace(",", "."))
        if 50 <= v <= 220:
            out["bpm"] = v
    m = re.search(r"\bkey\s*[:\-]\s*([A-G](?:#|b|♯|♭)?)\s*(minor|min|m|major|maj)?\b", t, re.I) \
        or re.search(r"\b([A-G](?:#|b|♯|♭)?)\s*(minor|min|major|maj)\b", t)
    if m:
        root = m.group(1)[0].upper() + m.group(1)[1:].replace("♯", "#").replace("♭", "b")
        q = (m.group(2) or "").lower()
        out["key"] = root + ("m" if q in ("minor", "min", "m") else "")
    return out


# ---------------- kalicilik ----------------
def beats_dir() -> Path:
    d = beat_studio.recordings_dir() / "beats"
    d.mkdir(parents=True, exist_ok=True)
    return d


def shelf_path() -> Path:
    return beat_studio.recordings_dir() / "beat_shelf.json"


def load_shelf() -> list[dict[str, Any]]:
    fp = shelf_path()
    if not fp.is_file():
        return []
    try:
        data = json.loads(fp.read_text(encoding="utf-8"))
        items = data.get("items") if isinstance(data, dict) else data
        return [i for i in (items or []) if isinstance(i, dict) and i.get("id")]
    except Exception:
        log.warning("beat_shelf.json okunamadi", exc_info=True)
        return []


def save_shelf(items: list[dict[str, Any]]) -> None:
    beat_studio._atomic_write(shelf_path(), json.dumps({"version": 1, "items": items}, ensure_ascii=False, indent=1))


def _norm_license(lic: Any) -> dict[str, Any]:
    lic = dict(lic or {}) if isinstance(lic, dict) else {"kind": str(lic or "")}
    kind = lic.get("kind") if lic.get("kind") in LICENSE_KINDS else "unknown"
    return {"kind": kind, "credit_text": str(lic.get("credit_text") or "")[:120],
            "evidence": [str(e)[:160] for e in (lic.get("evidence") or [])][:3],
            "guessed": bool(lic.get("guessed", False)), "user_set": bool(lic.get("user_set", False))}


def add_item(fields: dict[str, Any]) -> dict[str, Any]:
    """Rafa ekler (ayni kaynak URL varsa gunceller). Donus: oge."""
    with _LOCK:
        items = load_shelf()
        url = str(fields.get("source_url") or "")
        cur = next((i for i in items if url and i.get("source_url") == url), None)
        item = cur if cur is not None else {"id": "b_" + uuid.uuid4().hex[:8], "added_at": time.time()}
        for k in ("title", "producer", "source_url", "file", "note"):
            if k in fields:
                item[k] = str(fields.get(k) or "")
        item["bpm"] = float(fields.get("bpm") or item.get("bpm") or 0.0)
        item["key"] = str(fields.get("key") or item.get("key") or "")
        item["duration"] = float(fields.get("duration") or item.get("duration") or 0.0)
        if "license" in fields:
            item["license"] = _norm_license(fields["license"])
        item.setdefault("license", _norm_license({"kind": "unknown"}))
        item.setdefault("note", "")
        if cur is None:
            items.insert(0, item)
        save_shelf(items)
        return item


def update_item(item_id: str, fields: dict[str, Any]) -> dict[str, Any]:
    """Kullanici duzeltmesi: title, producer, bpm, key, note, license{kind, credit_text}."""
    with _LOCK:
        items = load_shelf()
        it = next((i for i in items if i.get("id") == item_id), None)
        if it is None:
            return {"ok": False, "error": "not_found"}
        for k in ("title", "producer", "note", "key"):
            if k in fields:
                it[k] = str(fields.get(k) or "")[:200]
        if "bpm" in fields:
            try:
                it["bpm"] = max(0.0, min(300.0, float(fields.get("bpm") or 0.0)))
            except (TypeError, ValueError):
                pass
        if isinstance(fields.get("license"), dict):
            lic = dict(it.get("license") or {})
            lic.update({k: v for k, v in fields["license"].items() if k in ("kind", "credit_text")})
            lic["user_set"], lic["guessed"] = True, False
            it["license"] = _norm_license(lic)
        save_shelf(items)
        return {"ok": True, "item": it}


def remove_item(item_id: str, delete_file: bool = False) -> dict[str, Any]:
    with _LOCK:
        items = load_shelf()
        it = next((i for i in items if i.get("id") == item_id), None)
        if it is None:
            return {"ok": False, "error": "not_found"}
        items = [i for i in items if i.get("id") != item_id]
        save_shelf(items)
    if delete_file and it.get("file"):
        try:
            fp = Path(it["file"]).resolve()
            if beats_dir().resolve() in fp.parents:        # yalniz Kami'nin indirdigi dosyalar silinir
                fp.unlink(missing_ok=True)
        except Exception:
            pass
    return {"ok": True}


def _key_root(k: str) -> str:
    return str(k or "").strip().lower()


def list_items(query: str = "", bpm_min: float = 0.0, bpm_max: float = 0.0, key: str = "",
               license_kind: str = "") -> dict[str, Any]:
    q = str(query or "").strip().lower()
    out = []
    for it in load_shelf():
        hay = " ".join(str(it.get(k) or "") for k in ("title", "producer", "note", "key")).lower()
        if q and not all(w in hay for w in q.split()):
            continue
        bpm = float(it.get("bpm") or 0.0)
        if bpm_min and (not bpm or bpm < float(bpm_min)):
            continue
        if bpm_max and (not bpm or bpm > float(bpm_max)):
            continue
        if key and _key_root(it.get("key")) != _key_root(key):
            continue
        if license_kind and (it.get("license") or {}).get("kind") != license_kind:
            continue
        o = dict(it)
        o["exists"] = bool(it.get("file")) and os.path.isfile(str(it.get("file")))
        out.append(o)
    return {"ok": True, "items": out, "labels": LICENSE_LABELS}


# ---------------- indirme (mevcut yt-dlp motoru) ----------------
def progress() -> dict[str, Any]:
    return dict(_PROGRESS)


def fetch_info(url: str) -> dict[str, Any]:
    """yt-dlp ile indirmeden: baslik, yukleyen, aciklama, sure."""
    from app.engines import ytdlp_engine as yt
    yt_dlp = yt._ytdlp()
    opts = {"quiet": True, "no_warnings": True, "skip_download": True, "noplaylist": True, "logger": yt._YdlLogger(),
            "socket_timeout": 30}
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False) or {}
    if info.get("_type") == "playlist" or info.get("entries"):
        raise ValueError("playlist_not_supported")
    return {"title": info.get("title") or "", "uploader": info.get("uploader") or info.get("channel") or "",
            "description": info.get("description") or "", "duration": float(info.get("duration") or 0.0),
            "url": info.get("webpage_url") or url, "tags": list(info.get("tags") or [])}


def download_audio(url: str, engine: Any = None, on_progress: Callable[..., None] | None = None) -> str:
    """Kami'nin medya isi (MediaJob) ile yalniz ses (mp3 320) -> beats/. Son dosya yolu."""
    from app.engines import ytdlp_engine as yt
    job = yt.MediaJob(0, url, str(beats_dir()),
                      {"format": "mp3", "audio_kbps": 320, "embed": False, "sponsorblock": "off", "no_playlist": True,
                       "subs": False}, engine, on_progress=on_progress or (lambda **kw: None))
    return job.run()


def add_from_url(url: str, engine: Any = None, info_fn=None, download_fn=None, analyze: bool = True) -> dict[str, Any]:
    """Baglantidan beat indir -> rafa ekle. info_fn/download_fn testlerde sahte verilir."""
    url = str(url or "").strip()
    if not re.match(r"^https?://", url):
        return {"ok": False, "error": "bad_url"}
    _PROGRESS.update(phase="info", pct=0.0, title="", error="")
    try:
        info = (info_fn or fetch_info)(url)
    except Exception as exc:
        _PROGRESS.update(phase="error", error=str(exc)[:160])
        return {"ok": False, "error": "info_failed", "detail": str(exc)[:160]}
    _PROGRESS.update(phase="download", title=info.get("title") or "")

    def prog(**kw):
        size, done = float(kw.get("size") or 0), float(kw.get("downloaded") or 0)
        if size > 0:
            _PROGRESS["pct"] = round(min(99.0, 100.0 * done / size), 1)
        if kw.get("phase") == "processing":
            _PROGRESS["phase"] = "convert"
    try:
        path = (download_fn or (lambda u, p: download_audio(u, engine, p)))(info.get("url") or url, prog)
    except Exception as exc:
        _PROGRESS.update(phase="error", error=str(exc)[:160])
        return {"ok": False, "error": "download_failed", "detail": str(exc)[:160]}
    if not path or not os.path.isfile(path):
        _PROGRESS.update(phase="error", error="no_file")
        return {"ok": False, "error": "download_failed"}
    text = f"{info.get('title', '')}\n{info.get('description', '')}\n{' '.join(info.get('tags') or [])}"
    bk = parse_bpm_key(text)
    if analyze and (not bk["bpm"] or not bk["key"]):
        _PROGRESS.update(phase="analyze")
        try:
            from app.core import kami_beat
            if not bk["bpm"]:
                bk["bpm"] = float(kami_beat.analyze_bpm(path) or 0.0)
            if not bk["key"]:
                bk["key"] = str((kami_beat.detect_key(path) or {}).get("key") or "")
        except Exception:
            log.debug("raf analizi atlandi", exc_info=True)
    lic = infer_license(info.get("description", ""), info.get("title", ""), info.get("uploader", ""))
    item = add_item({"title": info.get("title") or Path(path).stem, "producer": guess_producer(
        info.get("title", ""), info.get("description", ""), info.get("uploader", "")),
        "source_url": info.get("url") or url, "file": path, "bpm": bk["bpm"], "key": bk["key"],
        "duration": info.get("duration") or 0.0, "license": lic})
    _PROGRESS.update(phase="done", pct=100.0)
    return {"ok": True, "item": item}


def add_local_file(path: str, title: str = "") -> dict[str, Any]:
    """Diskteki bir beat dosyasini rafa ekler (kopyalamaz; lisans bilinmiyor)."""
    if not path or not os.path.isfile(path):
        return {"ok": False, "error": "not_found"}
    bk = parse_bpm_key(Path(path).stem)
    return {"ok": True, "item": add_item({"title": title or Path(path).stem, "producer": guess_producer(Path(path).stem),
                                          "source_url": "", "file": path, "bpm": bk["bpm"], "key": bk["key"],
                                          "license": {"kind": "unknown"}})}


# ---------------- projeye ekleme + yayin oncesi uyari ----------------
def beat_meta_for(item: dict[str, Any]) -> dict[str, Any]:
    lic = _norm_license(item.get("license"))
    return {"shelf_id": item.get("id", ""), "title": item.get("title", ""), "producer": item.get("producer", ""),
            "source_url": item.get("source_url", ""), "path": item.get("file", ""), "license": lic,
            "credit_text": lic.get("credit_text") or (f"prod. by {item['producer']}" if item.get("producer") else "")}


def add_to_project(pid: str, item_id: str, start: float = -1.0, track_id: str = "") -> dict[str, Any]:
    it = next((i for i in load_shelf() if i.get("id") == item_id), None)
    if it is None:
        return {"ok": False, "error": "not_found"}
    if not it.get("file") or not os.path.isfile(str(it["file"])):
        return {"ok": False, "error": "file_missing"}
    ld = beat_studio.load_project(pid)
    if not ld.get("ok"):
        return ld
    tid = track_id or next((t.get("id") for t in ld["project"].get("tracks", []) if t.get("role") == "beat"), "beat")
    res = beat_studio.add_take_to_track(pid, tid, str(it["file"]), label=str(it.get("title") or "Beat")[:60],
                                        start=None if start is None or float(start) < 0 else float(start))
    if not res.get("ok"):
        return res
    proj = res["project"]
    proj["beat_meta"] = beat_meta_for(it)
    if float(it.get("bpm") or 0) > 0:
        proj["bpm"] = float(it["bpm"])          # raftaki (aciklamadan / elle duzeltilmis) deger analizden once gelir
    if it.get("key"):
        proj["key"] = str(it["key"])
    beat_studio.save_project(proj)
    return {**res, "project": proj, "beat_meta": proj["beat_meta"]}


def release_warnings(proj: dict[str, Any]) -> list[dict[str, Any]]:
    """Bounce / disa aktarma oncesi lisans uyarilari. Beat kanalinda raftaki dosya artik yoksa (kullanici kendi
    beat'ini koymus) uyari verilmez."""
    meta = proj.get("beat_meta") if isinstance(proj.get("beat_meta"), dict) else None
    if not meta:
        return []
    path = str(meta.get("path") or "")
    used = any(str(c.get("path") or "") == path and not c.get("muted")
               for t in proj.get("tracks", []) if t.get("role") == "beat" and not t.get("mute")
               for c in (t.get("clips") or []))
    if path and not used:
        return []
    lic = _norm_license(meta.get("license"))
    kind, credit = lic["kind"], str(meta.get("credit_text") or lic.get("credit_text") or "")
    title = str(meta.get("title") or "Beat")
    out: list[dict[str, Any]] = []
    if kind == "free_nonprofit":
        out.append({"kind": kind, "level": "block", "title": title, "credit_text": credit,
                    "message": "Bu beat ticari kullanıma kapalı (yalnız kâr amacı gütmeyen kullanım). "
                               "Para kazanılan bir yerde yayınlamadan önce lisans al."})
    elif kind == "lease_required":
        out.append({"kind": kind, "level": "block", "title": title, "credit_text": credit,
                    "message": "Bu beat için lisans gerekli (lease / satın alma) — yayınlamadan önce lisansını al."})
    if kind == "credit_required" or (kind in ("free_nonprofit", "free_profit") and credit):
        out.append({"kind": "credit", "level": "warn" if kind == "credit_required" else "info", "title": title,
                    "credit_text": credit,
                    "message": ("Kredi zorunlu — yayın açıklamasına ekle: " if kind == "credit_required"
                                else "Kredi önerilir: ") + (credit or "yapımcı adı")})
    if kind == "unknown":
        out.append({"kind": kind, "level": "info", "title": title, "credit_text": credit,
                    "message": "Beat lisansı bilinmiyor — kaynak açıklamasını kontrol et ve raftan düzelt."})
    return out
