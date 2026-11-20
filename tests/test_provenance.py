"""Kami Provenance: indirilen dosyanin kaynak kaydi (sidecar) testleri."""
from __future__ import annotations

from app.core import provenance


def test_sidecar_write_read_roundtrip(tmp_path):
    f = tmp_path / "video.mp4"
    f.write_bytes(b"x" * 1000)

    ok = provenance.write(str(f), url="https://example.com/v.mp4", size=1000,
                          referer="https://example.com/", source="browser", category="Video")
    assert ok is True
    sp = provenance.sidecar_path(str(f))
    assert sp.endswith(".kami.json") and (tmp_path / sp).is_file()

    rec = provenance.read(str(f))
    assert rec is not None
    assert rec["v"] == 1
    assert rec["url"] == "https://example.com/v.mp4"
    assert rec["size"] == 1000
    assert rec["source"] == "browser"
    assert rec["category"] == "Video"


def test_write_missing_file_returns_false(tmp_path):
    assert provenance.write(str(tmp_path / "yok.mp4")) is False
    assert provenance.read(str(tmp_path / "yok.mp4")) is None


def test_sha256_prefers_extra(tmp_path):
    f = tmp_path / "song.mp3"
    f.write_bytes(b"a")
    provenance.write(str(f), url="u", extra={"sha256": "ab" * 32})
    rec = provenance.read(str(f))
    assert rec["sha256"] == "ab" * 32
