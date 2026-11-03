"""SQLite tabanli indirme kuyrugu (kalici kayit).

Not: stdlib 'queue' modulunu golgelememek icin dosya adi queue_store.py.
"""
from __future__ import annotations

import json
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Iterable

from app.core.models import Download, Status

_SCHEMA = """
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    url         TEXT NOT NULL,
    filename    TEXT NOT NULL DEFAULT '',
    directory   TEXT NOT NULL DEFAULT '',
    category    TEXT NOT NULL DEFAULT 'other',
    status      TEXT NOT NULL,
    size        INTEGER NOT NULL DEFAULT 0,
    downloaded  INTEGER NOT NULL DEFAULT 0,
    gid         TEXT NOT NULL DEFAULT '',
    error       TEXT NOT NULL DEFAULT '',
    referer     TEXT NOT NULL DEFAULT '',
    headers     TEXT NOT NULL DEFAULT '{}',
    source      TEXT NOT NULL DEFAULT 'ui',
    page_url    TEXT NOT NULL DEFAULT '',
    created_at  REAL NOT NULL,
    finished_at REAL NOT NULL DEFAULT 0
);
CREATE INDEX IF NOT EXISTS idx_downloads_status ON downloads(status);
"""

_COLUMNS = (
    "url", "filename", "directory", "category", "status", "size", "downloaded",
    "gid", "error", "referer", "headers", "source", "page_url", "created_at", "finished_at",
)


class DownloadStore:
    def __init__(self, db_path: Path | str) -> None:
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(db_path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.executescript(_SCHEMA)
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()

    # --- yazma ---
    def add(self, **fields: Any) -> Download:
        fields.setdefault("created_at", time.time())
        fields.setdefault("status", Status.QUEUED)
        row = {k: _to_db(k, v) for k, v in fields.items() if k in _COLUMNS}
        cols = ", ".join(row)
        marks = ", ".join("?" for _ in row)
        with self._lock:
            cur = self._conn.execute(f"INSERT INTO downloads ({cols}) VALUES ({marks})", tuple(row.values()))
            self._conn.commit()
            return self.get(cur.lastrowid)  # type: ignore[return-value]

    def update(self, download_id: int, **fields: Any) -> Download | None:
        row = {k: _to_db(k, v) for k, v in fields.items() if k in _COLUMNS}
        if row:
            sets = ", ".join(f"{k} = ?" for k in row)
            with self._lock:
                self._conn.execute(f"UPDATE downloads SET {sets} WHERE id = ?", (*row.values(), download_id))
                self._conn.commit()
        return self.get(download_id)

    def delete(self, download_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM downloads WHERE id = ?", (download_id,))
            self._conn.commit()

    # --- okuma ---
    def get(self, download_id: int) -> Download | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM downloads WHERE id = ?", (download_id,)).fetchone()
        return _from_row(r) if r else None

    def list(self, statuses: Iterable[Status] | None = None) -> list[Download]:
        q = "SELECT * FROM downloads"
        args: tuple = ()
        if statuses:
            st = [str(s) for s in statuses]
            q += f" WHERE status IN ({', '.join('?' for _ in st)})"
            args = tuple(st)
        q += " ORDER BY id DESC"
        with self._lock:
            rows = self._conn.execute(q, args).fetchall()
        return [_from_row(r) for r in rows]

    def by_gid(self, gid: str) -> Download | None:
        with self._lock:
            r = self._conn.execute("SELECT * FROM downloads WHERE gid = ? ORDER BY id DESC LIMIT 1", (gid,)).fetchone()
        return _from_row(r) if r else None


def _to_db(key: str, value: Any) -> Any:
    if key == "headers":
        return json.dumps(value or {}, ensure_ascii=False)
    if key == "status":
        return str(value)
    return value


def _from_row(r: sqlite3.Row) -> Download:
    return Download(
        id=r["id"],
        url=r["url"],
        filename=r["filename"],
        directory=r["directory"],
        category=r["category"],
        status=Status(r["status"]),
        size=r["size"],
        downloaded=r["downloaded"],
        gid=r["gid"],
        error=r["error"],
        referer=r["referer"],
        headers=json.loads(r["headers"] or "{}"),
        source=r["source"],
        page_url=r["page_url"],
        created_at=r["created_at"],
        finished_at=r["finished_at"],
    )
