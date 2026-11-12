"""Kami Reader: manga/cizgi roman (CBZ/CBR/CB7/ZIP/RAR, resim klasoru) ve PDF.

- Arsivler: zip Python ile; rar/7z Windows'un tar.exe'si (libarchive) ile bir kez onbellek klasorune acilir.
- PDF: pypdfium2 ile sayfa resmi, kelime kutulari (secip vurgulamak ve arama icin), kucuk resimler.
- Okuma durumu, vurgular, notlar, yer imleri: DATA_DIR/reader/<hash>.json
- Sesli okuma: Piper (yerel, cevrimdisi). Ilk kullanimda piper.exe + ses modeli indirilir.
"""
from __future__ import annotations

import base64
import hashlib
import io
import json
import logging
import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import zipfile
from pathlib import Path
from typing import Any

from app import paths

log = logging.getLogger("kami")
NOWIN = 0x08000000 if os.name == "nt" else 0
IMG = (".jpg", ".jpeg", ".png", ".webp", ".gif", ".bmp", ".avif", ".jfif")
COMIC = (".cbz", ".cbr", ".cb7", ".cbt", ".zip", ".rar", ".7z")
BOOK = (".pdf",)
READ_EXT = COMIC + BOOK
ROOT = paths.DATA_DIR / "reader"


def _natkey(s: str):
    return [int(t) if t.isdigit() else t.lower() for t in re.split(r"(\d+)", s)]


def _key(path: str) -> str:
    st = os.stat(path) if os.path.isfile(path) else None
    raw = f"{os.path.abspath(path).lower()}|{st.st_size if st else 0}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _data_url(raw: bytes, mime: str) -> str:
    return f"data:{mime};base64," + base64.b64encode(raw).decode("ascii")


# ---------------------------------------------------------------- belge
class Doc:
    def __init__(self, path: str) -> None:
        self.path = os.path.abspath(path)
        self.key = _key(self.path)
        ext = os.path.splitext(self.path)[1].lower()
        self.kind = "pdf" if ext == ".pdf" else "comic"
        self.pages: list[str] = []          # comic: dosya yollari / zip uyeleri
        self._zip: zipfile.ZipFile | None = None
        self._pdf = None
        self.lock = threading.Lock()
        if os.path.isdir(self.path):
            self.pages = sorted((str(p) for p in Path(self.path).rglob("*") if p.suffix.lower() in IMG), key=_natkey)
        elif self.kind == "pdf":
            import pypdfium2 as pdfium
            self._pdf = pdfium.PdfDocument(self.path)
        elif zipfile.is_zipfile(self.path):
            self._zip = zipfile.ZipFile(self.path)
            self.pages = sorted((n for n in self._zip.namelist() if n.lower().endswith(IMG) and "__MACOSX" not in n), key=_natkey)
        else:
            out = Path(tempfile.gettempdir()) / "kami_reader" / self.key
            if not out.exists() or not any(out.rglob("*")):
                out.mkdir(parents=True, exist_ok=True)
                r = subprocess.run(["tar", "-xf", self.path, "-C", str(out)], capture_output=True, text=True,
                                   creationflags=NOWIN, timeout=300)
                if r.returncode != 0 and not any(out.rglob("*")):
                    raise RuntimeError("arsiv acilamadi: " + (r.stderr.strip()[-120:] or "?"))
            self.pages = sorted((str(p) for p in out.rglob("*") if p.suffix.lower() in IMG), key=_natkey)

    @property
    def count(self) -> int:
        return len(self._pdf) if self._pdf is not None else len(self.pages)

    @property
    def title(self) -> str:
        return os.path.splitext(os.path.basename(self.path.rstrip("\\/")))[0]

    def page_image(self, i: int, width: int = 1400) -> dict[str, Any]:
        from PIL import Image
        with self.lock:
            if self._pdf is not None:
                pg = self._pdf[i]
                w, h = pg.get_size()
                scale = max(0.5, min(4.0, width / max(w, 1)))
                im = pg.render(scale=scale).to_pil()
                pg.close()
                buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=88)
                return {"src": _data_url(buf.getvalue(), "image/jpeg"), "w": im.width, "h": im.height, "pw": w, "ph": h}
            name = self.pages[i]
            raw = self._zip.read(name) if self._zip else Path(name).read_bytes()
        im = Image.open(io.BytesIO(raw))
        if im.width > width * 1.5:            # cok buyuk sayfalari kucult (webtoon serileri uzun ama dar)
            im = im.convert("RGB"); im.thumbnail((int(width * 1.5), 100000))
            buf = io.BytesIO(); im.save(buf, "JPEG", quality=90)
            return {"src": _data_url(buf.getvalue(), "image/jpeg"), "w": im.width, "h": im.height}
        mime = {"PNG": "image/png", "WEBP": "image/webp", "GIF": "image/gif"}.get(im.format or "", "image/jpeg")
        if (im.format or "").upper() not in ("PNG", "WEBP", "GIF", "JPEG", "MPO"):
            buf = io.BytesIO(); im.convert("RGB").save(buf, "JPEG", quality=90); raw, mime = buf.getvalue(), "image/jpeg"
        return {"src": _data_url(raw, mime), "w": im.width, "h": im.height}

    def thumb(self, i: int) -> str:
        return self.page_image(i, 180)["src"]

    def words(self, i: int) -> list[list]:
        """PDF sayfasindaki kelimeler: [metin, x0, y0, x1, y1] (0-1 araliginda, sol-ust kokenli)."""
        if self._pdf is None:
            return []
        with self.lock:
            pg = self._pdf[i]
            w, h = pg.get_size()
            tp = pg.get_textpage()
            n = tp.count_chars()
            out, cur, box = [], "", None
            for k in range(n):
                ch = tp.get_text_range(k, 1)
                if not ch or ch.isspace():
                    if cur:
                        out.append([cur, *box]); cur, box = "", None
                    continue
                l, b, r, t = tp.get_charbox(k)
                bx = [l / w, 1 - t / h, r / w, 1 - b / h]
                if box is None:
                    box = bx
                elif bx[0] < box[0] - 0.02 or abs(bx[1] - box[1]) > 0.02:   # yeni satir: kelimeyi kapat
                    out.append([cur, *box]); cur, box = "", bx
                else:
                    box = [min(box[0], bx[0]), min(box[1], bx[1]), max(box[2], bx[2]), max(box[3], bx[3])]
                cur += ch
            if cur:
                out.append([cur, *box])
            tp.close(); pg.close()
        return [[t, round(a, 4), round(b, 4), round(c, 4), round(d, 4)] for t, a, b, c, d in out]

    def text(self, i: int) -> str:
        if self._pdf is None:
            return ""
        with self.lock:
            pg = self._pdf[i]; tp = pg.get_textpage()
            s = tp.get_text_range()
            tp.close(); pg.close()
        return s

    def search(self, q: str, limit: int = 200) -> list[dict[str, Any]]:
        q = (q or "").strip().lower()
        if not q or self._pdf is None:
            return []
        hits = []
        for i in range(self.count):
            t = self.text(i)
            low = t.lower()
            start = 0
            while len(hits) < limit:
                k = low.find(q, start)
                if k < 0:
                    break
                hits.append({"page": i, "ctx": t[max(0, k - 40):k + len(q) + 40].replace("\n", " ")})
                start = k + len(q)
        return hits

    def outline(self) -> list[dict[str, Any]]:
        if self._pdf is None:
            return []
        out = []
        try:
            for it in self._pdf.get_toc(max_depth=4):
                dest = it.get_dest()
                idx = dest.get_index() if dest is not None else None
                if idx is not None:
                    out.append({"t": it.get_title(), "page": idx, "lvl": getattr(it, "level", 0)})
        except Exception:
            pass
        return out[:400]

    def close(self) -> None:
        try:
            if self._zip:
                self._zip.close()
            if self._pdf is not None:
                self._pdf.close()
        except Exception:
            pass


# ---------------------------------------------------------------- not defteri
def state_path(key: str) -> Path:
    ROOT.mkdir(parents=True, exist_ok=True)
    return ROOT / f"{key}.json"


def load_state(key: str) -> dict[str, Any]:
    try:
        return json.loads(state_path(key).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"page": 0, "marks": [], "hl": [], "settings": {}}


def save_state(key: str, st: dict[str, Any], path: str = "", title: str = "") -> None:
    st = dict(st)
    if path:
        st["path"], st["title"], st["opened"] = path, title, time.time()
    state_path(key).write_text(json.dumps(st, ensure_ascii=False), encoding="utf-8")


def recent(limit: int = 30) -> list[dict[str, Any]]:
    if not ROOT.exists():
        return []
    out = []
    for f in ROOT.glob("*.json"):
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if d.get("path") and os.path.exists(d["path"]):
            out.append({"path": d["path"], "title": d.get("title", ""), "page": d.get("page", 0),
                        "count": d.get("count", 0), "opened": d.get("opened", 0), "hl": len(d.get("hl", []))})
    return sorted(out, key=lambda x: -x["opened"])[:limit]


def cover(path: str) -> str:
    """Kitaplik kapagi: ilk sayfanin kucuk resmi (diskte onbellek)."""
    key = _key(path)
    f = ROOT / "covers" / f"{key}.txt"
    if f.exists():
        return f.read_text(encoding="ascii")
    d = Doc(path)
    try:
        src = d.thumb(0) if d.count else ""
    finally:
        d.close()
    if src:
        f.parent.mkdir(parents=True, exist_ok=True)
        f.write_text(src, encoding="ascii")
    return src


# ---------------------------------------------------------------- sesli okuma (Piper)
PIPER_ZIP = "https://github.com/rhasspy/piper/releases/download/2023.11.14-2/piper_windows_amd64.zip"
VOICES = {
    "tr": "https://huggingface.co/rhasspy/piper-voices/resolve/main/tr/tr_TR/dfki/medium/tr_TR-dfki-medium.onnx",
    "en": "https://huggingface.co/rhasspy/piper-voices/resolve/main/en/en_US/lessac/medium/en_US-lessac-medium.onnx",
}
TTS_DIR = paths.DATA_DIR / "tools" / "piper"
_tts_lock = threading.Lock()
TTS_STATE: dict[str, Any] = {"state": "idle", "msg": ""}


def _dl(url: str, dest: Path) -> None:
    import requests
    tmp = dest.with_suffix(dest.suffix + ".part")
    with requests.get(url, stream=True, timeout=60, headers={"User-Agent": "Kami"}) as r:
        r.raise_for_status()
        total = int(r.headers.get("content-length") or 0)
        got = 0
        with open(tmp, "wb") as f:
            for chunk in r.iter_content(1 << 16):
                f.write(chunk); got += len(chunk)
                if total:
                    TTS_STATE["msg"] = f"{dest.name} %{got * 100 // total}"
    tmp.replace(dest)


def piper_exe() -> Path:
    return TTS_DIR / "piper" / "piper.exe"


def ensure_tts(lang: str) -> Path:
    """piper.exe ve dil modelini hazirlar; model yolunu dondurur."""
    lang = lang if lang in VOICES else "tr"
    with _tts_lock:
        TTS_DIR.mkdir(parents=True, exist_ok=True)
        if not piper_exe().exists():
            TTS_STATE.update(state="installing", msg="Piper")
            z = TTS_DIR / "piper.zip"
            _dl(PIPER_ZIP, z)
            with zipfile.ZipFile(z) as zf:
                zf.extractall(TTS_DIR)
            z.unlink(missing_ok=True)
        model = TTS_DIR / os.path.basename(VOICES[lang])
        if not model.exists():
            TTS_STATE.update(state="installing", msg=model.name)
            _dl(VOICES[lang] + ".json", Path(str(model) + ".json"))
            _dl(VOICES[lang], model)
        TTS_STATE.update(state="ready", msg="")
        return model


def guess_lang(text: str) -> str:
    tr = sum(text.count(c) for c in "çğışöüÇĞİŞÖÜ")
    return "tr" if tr >= max(2, len(text) // 400) else "en"


def split_sentences(text: str, size: int = 280) -> list[str]:
    text = re.sub(r"-\n(\w)", r"\1", text or "")          # satir sonu tirelemesini birlestir
    text = re.sub(r"\s+", " ", text).strip()
    parts, cur = [], ""
    for s in re.split(r"(?<=[.!?…:;])\s+", text):
        if len(cur) + len(s) > size and cur:
            parts.append(cur.strip()); cur = ""
        cur += s + " "
    if cur.strip():
        parts.append(cur.strip())
    return parts


def speak(text: str, lang: str = "", rate: float = 1.0) -> str:
    """Metni Piper ile wav'a cevirir; data URL dondurur."""
    lang = lang or guess_lang(text)
    model = ensure_tts(lang)
    out = Path(tempfile.gettempdir()) / f"kami_tts_{threading.get_ident()}.wav"
    r = subprocess.run([str(piper_exe()), "-m", str(model), "-f", str(out), "--length_scale", f"{1 / max(0.5, rate):.2f}"],
                       input=text.encode("utf-8"), capture_output=True, creationflags=NOWIN, timeout=120,
                       cwd=str(piper_exe().parent))
    if r.returncode != 0 or not out.exists():
        raise RuntimeError((r.stderr or b"").decode("utf-8", "replace").strip()[-160:] or "piper hata")
    raw = out.read_bytes()
    out.unlink(missing_ok=True)
    return _data_url(raw, "audio/wav")


def tts_installed(lang: str = "tr") -> bool:
    return piper_exe().exists() and (TTS_DIR / os.path.basename(VOICES.get(lang, VOICES["tr"]))).exists()


def cleanup_cache() -> None:
    shutil.rmtree(Path(tempfile.gettempdir()) / "kami_reader", ignore_errors=True)
