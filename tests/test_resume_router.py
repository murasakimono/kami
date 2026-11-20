"""Kami Ghost-Resume (resume_router) testleri."""
from __future__ import annotations

from app.core import resume_router


def test_rank_prefers_sha256_then_size_then_mirror():
    cands = [
        {"url": "hunter-size", "source": "hunter", "size": 100},
        {"url": "mirror-size", "source": "mirror", "size": 100},
        {"url": "hash-match", "source": "hunter", "sha256": "x" * 64, "size": 100},
        {"url": "wrong-size", "source": "hunter", "size": 999},
    ]
    out = resume_router.rank(cands, size=100, sha256="x" * 64)
    assert [c["url"] for c in out] == ["hash-match", "mirror-size", "hunter-size", "wrong-size"]


def test_find_alternates_empty_no_network():
    res = resume_router.find_alternates("", filename="", use_hunter=False)
    assert res == {"ok": True, "alternates": []}


def test_find_mirrors_empty_for_local_host():
    # yerel adres: mirrors.find ağa çıkmadan [] döner
    assert resume_router.find_mirrors("http://127.0.0.1/x") == []
    assert resume_router.find_mirrors("ftp://yok") == []
