"""Kami Player sozlugu: altyazida tiklanan kelimenin anlami (yerel SQLite, cevrimdisi).

Kaynak: kaikki.org Vikisozluk cikarimlari (wiktextract, JSONL.gz), ilk kullanimda indirilip veritabanina islenir.
  tr  : Turkce Vikisozluk (~44 MB indirme) -> kelimelerin TURKCE aciklamalari (bircok dildeki kelime icin)
  en  : English Wiktionary (~2.9 GB indirme) -> kapsamli INGILIZCE aciklamalar; sadece LANGS dillerindeki kelimeler alinir
Tablo: entry(word, lw, lang, pos, gloss, ipa, src, base)  lw = kucuk harf; base = cekim/yapim halinin kok kelimesi.
"""
from __future__ import annotations

import gzip
import io
import json
import logging
import re
import sqlite3
import threading
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

log = logging.getLogger(__name__)

PACKS = {
    "tr": {"url": "https://kaikki.org/dictionary/downloads/tr/tr-extract.jsonl.gz", "size_mb": 44, "name": "Türkçe Vikisözlük"},
    "en": {"url": "https://kaikki.org/dictionary/raw-wiktextract-data.jsonl.gz", "size_mb": 2900, "name": "English Wiktionary"},
}
LANGS = {"en", "ja", "tr", "ko", "zh", "de", "fr", "es", "it", "ru"}   # English Wiktionary'den alinacak kelime dilleri
MAX_SENSES = 6
_WORD = re.compile(r"[^\w'\-]+", re.U)


class Dictionary:
    def __init__(self, db_path: Path) -> None:
        self.path = db_path
        self.progress: dict[str, Any] = {}   # pack -> {state, p, msg}
        self._lock = threading.Lock()

    # ---------- durum ----------
    def _conn(self) -> sqlite3.Connection:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        c = sqlite3.connect(str(self.path), timeout=5)
        c.execute("PRAGMA journal_mode=WAL")   # kurulum yazarken arama okuyabilsin
        c.execute("CREATE TABLE IF NOT EXISTS entry(word TEXT, lw TEXT, lang TEXT, pos TEXT, gloss TEXT, ipa TEXT, src TEXT, base TEXT)")
        c.execute("CREATE TABLE IF NOT EXISTS pack(name TEXT PRIMARY KEY, done INTEGER, rows INTEGER)")
        return c

    def status(self) -> dict[str, Any]:
        out = {"packs": {}, "progress": dict(self.progress)}
        if self.path.is_file():
            try:
                with self._conn() as c:
                    for name, done, rows in c.execute("SELECT name, done, rows FROM pack"):
                        out["packs"][name] = {"done": bool(done), "rows": rows}
            except sqlite3.Error:
                pass
        for k, v in PACKS.items():
            out["packs"].setdefault(k, {"done": False, "rows": 0})
            out["packs"][k].update(name=v["name"], size_mb=v["size_mb"])
        return out

    def installed(self) -> bool:
        return any(p["done"] for p in self.status()["packs"].values())

    # ---------- kurulum (arka plan is parcacigi) ----------
    def install(self, pack: str, on_done: Callable[[bool, str], None] = lambda ok, msg: None) -> bool:
        if pack not in PACKS or self.progress.get(pack, {}).get("state") == "running":
            return False
        self.progress[pack] = {"state": "running", "p": 0.0, "msg": "indiriliyor"}
        threading.Thread(target=self._install, args=(pack, on_done), name=f"kami-dict-{pack}", daemon=True).start()
        return True

    def _install(self, pack: str, on_done) -> None:
        url = PACKS[pack]["url"]
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Kami (personal dictionary)"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length") or 0)
                counter = _Counting(resp)
                gz = gzip.GzipFile(fileobj=counter)
                lines = io.TextIOWrapper(gz, encoding="utf-8", errors="replace")
                with self._lock, self._conn() as c:
                    c.execute("DELETE FROM entry WHERE src=?", (pack,))
                    c.execute("DROP INDEX IF EXISTS ix_lw")
                    batch, rows, last = [], 0, time.monotonic()
                    for line in lines:
                        row = self._row(line, pack)
                        if row:
                            batch.append(row)
                        if len(batch) >= 5000:
                            c.executemany("INSERT INTO entry VALUES (?,?,?,?,?,?,?,?)", batch)
                            rows += len(batch)
                            batch.clear()
                        if time.monotonic() - last > 1.0:
                            last = time.monotonic()
                            self.progress[pack] = {"state": "running", "p": round(counter.n / total, 3) if total else 0,
                                                   "msg": f"{rows:,} kelime".replace(",", ".")}
                    if batch:
                        c.executemany("INSERT INTO entry VALUES (?,?,?,?,?,?,?,?)", batch)
                        rows += len(batch)
                    self.progress[pack] = {"state": "running", "p": 1.0, "msg": "dizin olusturuluyor"}
                    c.execute("CREATE INDEX IF NOT EXISTS ix_lw ON entry(lw)")
                    c.execute("INSERT OR REPLACE INTO pack VALUES (?,?,?)", (pack, 1, rows))
            self.progress[pack] = {"state": "done", "p": 1.0, "msg": f"{rows} kayit"}
            log.info("Sozluk kuruldu: %s (%d kayit)", pack, rows)
            on_done(True, pack)
        except Exception as exc:
            log.exception("Sozluk kurulamadi: %s", pack)
            self.progress[pack] = {"state": "error", "p": 0, "msg": f"{type(exc).__name__}: {str(exc)[:120]}"}
            on_done(False, str(exc))

    @staticmethod
    def _row(line: str, pack: str):
        try:
            e = json.loads(line)
        except ValueError:
            return None
        word = e.get("word")
        lang = e.get("lang_code") or ""
        if not word or not isinstance(word, str) or len(word) > 60:
            return None
        if pack == "en" and lang not in LANGS:
            return None
        glosses, base = [], ""
        for s in (e.get("senses") or [])[:MAX_SENSES]:
            g = s.get("glosses") or s.get("raw_glosses") or []
            if g:
                glosses.append(g[-1] if isinstance(g[-1], str) else str(g[-1]))
            fo = s.get("form_of") or s.get("alt_of") or []
            if fo and not base and isinstance(fo[0], dict):
                base = fo[0].get("word") or ""
        if not glosses:
            return None
        ipa = next((s.get("ipa") for s in (e.get("sounds") or []) if s.get("ipa")), "") or ""
        return (word, word.lower(), lang, e.get("pos") or "", json.dumps(glosses, ensure_ascii=False), ipa, pack, base)

    # ---------- arama ----------
    def lookup(self, word: str, lang: str = "") -> list[dict[str, Any]]:
        w = _WORD.sub(" ", str(word or "")).strip().split(" ")[0].strip("'-") if lang not in ("ja", "zh", "ko") else str(word or "").strip()
        if not w or not self.path.is_file():
            return []
        cands = [w.lower()]
        if lang in ("", "en"):   # basit Ingilizce kok denemeleri (form_of tutmazsa)
            lw = w.lower()
            for suf, rep in (("ies", "y"), ("es", ""), ("s", ""), ("ied", "y"), ("ed", ""), ("ed", "e"), ("ing", ""), ("ing", "e"), ("'s", "")):
                if lw.endswith(suf) and len(lw) - len(suf) >= 2:
                    cands.append(lw[: -len(suf)] + rep)
        out: list[dict[str, Any]] = []
        seen = set()
        with self._conn() as c:
            for cand in cands:
                q = "SELECT word, lang, pos, gloss, ipa, src, base FROM entry WHERE lw=?" + (" AND lang=?" if lang else "") + " LIMIT 12"
                for word_, lg, pos, gloss, ipa, src, base in c.execute(q, (cand, lang) if lang else (cand,)):
                    key = (word_, lg, pos, src)
                    if key in seen:
                        continue
                    seen.add(key)
                    out.append({"word": word_, "lang": lg, "pos": pos, "glosses": json.loads(gloss), "ipa": ipa, "src": src, "base": base})
                if out:
                    break
            bases = {e["base"] for e in out if e["base"]} - {e["word"] for e in out}
            for b in list(bases)[:2]:   # cekim halleri: kok kelimenin anlami da gelsin
                for word_, lg, pos, gloss, ipa, src, base in c.execute(
                        "SELECT word, lang, pos, gloss, ipa, src, base FROM entry WHERE lw=?" + (" AND lang=?" if lang else "") + " LIMIT 4",
                        (b.lower(), lang) if lang else (b.lower(),)):
                    out.append({"word": word_, "lang": lg, "pos": pos, "glosses": json.loads(gloss), "ipa": ipa, "src": src, "base": base})
        out.sort(key=lambda e: (e["src"] != "tr", e["lang"] != (lang or e["lang"])))   # Turkce aciklamalar once
        return out[:14]

    def longest_match(self, text: str, start: int, lang: str = "ja") -> str:
        """Bosluksuz yazi (Japonca/Cince): tiklanan karakterden baslayan sozlukte bulunan en uzun kelime."""
        if not self.path.is_file():
            return text[start:start + 1]
        with self._conn() as c:
            for n in range(min(10, len(text) - start), 0, -1):
                sub = text[start:start + n]
                if c.execute("SELECT 1 FROM entry WHERE lw=? LIMIT 1", (sub.lower(),)).fetchone():
                    return sub
        return text[start:start + 1]


class _Counting(io.RawIOBase):
    """Indirilen sikistirilmis byte sayaci (ilerleme yuzdesi icin)."""

    def __init__(self, f) -> None:
        self.f = f
        self.n = 0

    def readable(self) -> bool:
        return True

    def readinto(self, b) -> int:
        data = self.f.read(len(b))
        n = len(data)
        b[:n] = data
        self.n += n
        return n
