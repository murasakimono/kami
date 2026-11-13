"""Faz 13 — Kami Kasa: SQLite FTS5 (WAL) + SigLIP semantik video/sahne arama & akilli oto-bolumlendirme."""
from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import math
import re
import sqlite3
import struct
from pathlib import Path
from typing import Any, Iterator

import requests

log = logging.getLogger(__name__)


def _default_db() -> Path:
    from app.core import paths
    return paths.DATA_DIR / "kami_kasa.db"


@contextlib.contextmanager
def _connect(db_path: Path | None = None) -> Iterator[sqlite3.Connection]:
    p = Path(db_path) if db_path else _default_db()
    p.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(p), timeout=15)
    try:
        con.execute("PRAGMA journal_mode=WAL;")
        con.execute("PRAGMA synchronous=NORMAL;")
        con.execute(
            """
            CREATE TABLE IF NOT EXISTS kasa_items (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                path TEXT NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                start_sec REAL NOT NULL DEFAULT 0.0,
                end_sec REAL NOT NULL DEFAULT 0.0,
                tags TEXT NOT NULL DEFAULT '',
                transcript TEXT NOT NULL DEFAULT '',
                embedding BLOB,
                updated_at REAL NOT NULL DEFAULT (strftime('%s','now')),
                UNIQUE(path, start_sec)
            )
            """
        )
        con.execute(
            """
            CREATE VIRTUAL TABLE IF NOT EXISTS kasa_fts USING fts5(
                title, tags, transcript, path,
                content='kasa_items', content_rowid='id'
            )
            """
        )
        con.executescript(
            """
            CREATE TRIGGER IF NOT EXISTS kasa_ai AFTER INSERT ON kasa_items BEGIN
                INSERT INTO kasa_fts(rowid, title, tags, transcript, path)
                VALUES (new.id, new.title, new.tags, new.transcript, new.path);
            END;
            CREATE TRIGGER IF NOT EXISTS kasa_ad AFTER DELETE ON kasa_items BEGIN
                INSERT INTO kasa_fts(kasa_fts, rowid, title, tags, transcript, path)
                VALUES ('delete', old.id, old.title, old.tags, old.transcript, old.path);
            END;
            CREATE TRIGGER IF NOT EXISTS kasa_au AFTER UPDATE ON kasa_items BEGIN
                INSERT INTO kasa_fts(kasa_fts, rowid, title, tags, transcript, path)
                VALUES ('delete', old.id, old.title, old.tags, old.transcript, old.path);
                INSERT INTO kasa_fts(rowid, title, tags, transcript, path)
                VALUES (new.id, new.title, new.tags, new.transcript, new.path);
            END;
            """
        )
        yield con
    finally:
        con.close()


def text_embedding(text: str, dims: int = 64) -> list[float]:
    """Hafif deterministik karakter-trigram projeksiyonu (SigLIP olmadiginda yerel vektor yedegi)."""
    clean = re.sub(r"\s+", " ", (text or "").lower().strip())
    if not clean:
        return []
    vec = [0.0] * dims
    tokens = clean.split()
    grams = list(tokens)
    for tok in tokens:
        if len(tok) >= 3:
            for i in range(len(tok) - 2):
                grams.append(tok[i:i + 3])
    for g in grams:
        h = int.from_bytes(hashlib.blake2b(g.encode("utf-8"), digest_size=4).digest(), "little")
        vec[h % dims] += 1.0
    norm = math.sqrt(sum(v * v for v in vec))
    return [round(v / norm, 5) for v in vec] if norm > 0 else []


def _pack_vec(vec: list[float]) -> bytes:
    return struct.pack(f"<{len(vec)}f", *vec)


def _unpack_vec(blob: bytes) -> list[float]:
    if not blob:
        return []
    n = len(blob) // 4
    return list(struct.unpack(f"<{n}f", blob[:n * 4]))


def _cosine(a: list[float], b: list[float]) -> float:
    if not a or not b or len(a) != len(b):
        return 0.0
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(y * y for y in b))
    return dot / (na * nb) if (na > 0 and nb > 0) else 0.0


def index_segment(
    path: str,
    *,
    title: str = "",
    start_sec: float = 0.0,
    end_sec: float = 0.0,
    tags: str = "",
    transcript: str = "",
    embedding: list[float] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Medya veya sahne segmentini FTS5 + opsiyonel vektor ile indeksler."""
    p = str(path)
    ttl = title or Path(p).stem
    vec = embedding if embedding is not None else text_embedding(f"{ttl} {tags} {transcript}")
    blob = _pack_vec(vec) if vec else None
    with _connect(db_path) as con:
        con.execute(
            """
            INSERT INTO kasa_items(path, title, start_sec, end_sec, tags, transcript, embedding)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(path, start_sec) DO UPDATE SET
                title=excluded.title,
                end_sec=excluded.end_sec,
                tags=excluded.tags,
                transcript=excluded.transcript,
                embedding=COALESCE(excluded.embedding, kasa_items.embedding),
                updated_at=strftime('%s','now')
            """,
            (p, ttl, float(start_sec), float(end_sec), tags, transcript, blob),
        )
        con.commit()
    return {"ok": True, "path": p, "start_sec": float(start_sec)}


def index_video_scenes(
    video_path: str | Path,
    *,
    tags: str = "",
    transcript_segments: list[dict[str, Any]] | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Videoyu sahne gecislerine bolup her sahneyi Kami Kasa'ya indeksler."""
    p = Path(video_path)
    if not p.is_file():
        return {"ok": False, "error": "Video bulunamadi", "indexed": 0}
    from app.core.scene_detect import detect_scenes
    sc = detect_scenes(p)
    scenes = sc.get("scenes") or [{"index": 0, "start": 0.0, "end": 0.0}]
    segs = transcript_segments or []
    # Yeniden indekslemede eski sahne satirlarinin birikmesini onle
    with _connect(db_path) as con:
        con.execute("DELETE FROM kasa_items WHERE path = ?", (str(p),))
        con.commit()
    count = 0
    for s in scenes:
        st = float(s.get("start") or 0.0)
        en = float(s.get("end") or (st + 30.0))
        txt = " ".join(
            str(t.get("text") or "").strip()
            for t in segs
            if float(t.get("start", 0)) < en and float(t.get("end", 0)) >= st
        )
        index_segment(
            str(p),
            title=f"{p.stem} [Sahne {int(s.get('index', count)) + 1}]",
            start_sec=st,
            end_sec=en,
            tags=tags,
            transcript=txt,
            db_path=db_path,
        )
        count += 1
    return {"ok": True, "indexed": count, "method": sc.get("method", "single")}


def search(
    query: str,
    *,
    query_embedding: list[float] | None = None,
    limit: int = 30,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """FTS5 metin aramasi + varsa SigLIP vektor benzerligi ile dogrudan sahne saniyesi dondurur."""
    q = (query or "").strip()
    if not q and not query_embedding:
        return {"ok": True, "results": []}
    q_vec = query_embedding if query_embedding is not None else text_embedding(q)

    results: dict[tuple[str, float], dict[str, Any]] = {}
    with _connect(db_path) as con:
        con.row_factory = sqlite3.Row
        if q:
            tokens = [re.sub(r'["\'*:]', "", t) for t in q.split() if t.strip()]
            fts_q = " OR ".join(f'"{t}"*' for t in tokens) if tokens else ""
            if fts_q:
                rows = con.execute(
                    """
                    SELECT i.path, i.title, i.start_sec, i.end_sec, i.tags, i.transcript,
                           bm25(kasa_fts) AS rank
                    FROM kasa_fts
                    JOIN kasa_items i ON i.id = kasa_fts.rowid
                    WHERE kasa_fts MATCH ?
                    ORDER BY rank ASC
                    LIMIT ?
                    """,
                    (fts_q, int(limit)),
                ).fetchall()
                for r in rows:
                    key = (r["path"], float(r["start_sec"]))
                    results[key] = {
                        "path": r["path"],
                        "title": r["title"],
                        "start_sec": float(r["start_sec"]),
                        "end_sec": float(r["end_sec"]),
                        "tags": r["tags"],
                        "snippet": (r["transcript"] or r["tags"] or r["title"])[:180],
                        "score": round(max(0.1, 1.0 / (1.0 + abs(float(r["rank"])))), 4),
                    }

        if q_vec:
            vec_rows = con.execute(
                "SELECT path, title, start_sec, end_sec, tags, transcript, embedding FROM kasa_items WHERE embedding IS NOT NULL"
            ).fetchall()
            for r in vec_rows:
                sim = _cosine(q_vec, _unpack_vec(r["embedding"]))
                if sim > (0.15 if query_embedding is not None else 0.45):   # trigram yedegi: dusuk esik her seyi eslestirir
                    key = (r["path"], float(r["start_sec"]))
                    cur = results.get(key)
                    score = round((cur["score"] if cur else 0.0) + sim, 4)
                    results[key] = {
                        "path": r["path"],
                        "title": r["title"],
                        "start_sec": float(r["start_sec"]),
                        "end_sec": float(r["end_sec"]),
                        "tags": r["tags"],
                        "snippet": (r["transcript"] or r["tags"] or r["title"])[:180],
                        "score": score,
                    }

    ordered = sorted(results.values(), key=lambda x: x["score"], reverse=True)[:limit]
    return {"ok": True, "results": ordered}


def auto_chapters(
    transcript_segments: list[dict[str, Any]],
    *,
    chunk_seconds: float = 180.0,
    ollama_model: str = "qwen2.5:7b",
    use_ollama: bool = True,
) -> dict[str, Any]:
    """Uzun kayit/ders transkriptini zaman pencerelerine bolup bolum basliklari ve ozet cikarir."""
    if not transcript_segments:
        return {"ok": True, "chapters": [], "engine": "none"}

    sorted_segs = sorted(transcript_segments, key=lambda s: float(s.get("start", 0.0)))
    buckets: list[list[dict[str, Any]]] = []
    cur_bucket: list[dict[str, Any]] = []
    bucket_start = float(sorted_segs[0].get("start", 0.0))

    for seg in sorted_segs:
        st = float(seg.get("start", 0.0))
        if cur_bucket and (st - bucket_start) >= chunk_seconds:
            buckets.append(cur_bucket)
            cur_bucket = []
            bucket_start = st
        cur_bucket.append(seg)
    if cur_bucket:
        buckets.append(cur_bucket)

    chapters: list[dict[str, Any]] = []
    engine = "extractive"
    ollama_ready = False
    if use_ollama:
        try:
            r_tags = requests.get("http://127.0.0.1:11434/api/tags", timeout=1.5)
            ollama_ready = r_tags.status_code == 200
        except Exception:
            ollama_ready = False

    for idx, b in enumerate(buckets):
        st = round(float(b[0].get("start", 0.0)), 2)
        en = round(float(b[-1].get("end", st + 10.0)), 2)
        text = " ".join(str(x.get("text") or "").strip() for x in b if x.get("text")).strip()
        title = f"Bölüm {idx + 1}"
        summary = text[:220] + ("..." if len(text) > 220 else "")

        if ollama_ready and text:
            try:
                resp = requests.post(
                    "http://127.0.0.1:11434/api/generate",
                    json={
                        "model": ollama_model,
                        "prompt": f"Su metne 5 kelimelik Turkce baslik ve 1 cumlelik ozet yaz (JSON: {{\"title\":\"...\",\"summary\":\"...\"}}):\n{text[:1200]}",
                        "stream": False,
                    },
                    timeout=25,
                )
                if resp.status_code == 200:
                    raw = (resp.json().get("response") or "").strip()
                    m = re.search(r"\{.*\}", raw, re.S)
                    if m:
                        parsed = json.loads(m.group(0))
                        title = str(parsed.get("title") or title)[:80]
                        summary = str(parsed.get("summary") or summary)[:260]
                        engine = "ollama"
            except Exception:
                pass

        chapters.append({"index": idx + 1, "start": st, "end": en, "title": title, "summary": summary})

    return {"ok": True, "engine": engine, "chapters": chapters}


def kasa_stats(db_path: Path | None = None) -> dict[str, Any]:
    with _connect(db_path) as con:
        row = con.execute("SELECT COUNT(*) AS cnt, COUNT(DISTINCT path) AS files FROM kasa_items").fetchone()
        return {"ok": True, "segments": int(row[0]), "files": int(row[1])}
