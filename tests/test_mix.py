"""Kami 'For You' Radyo (mix) testleri."""
from __future__ import annotations

from app.core import mix


def test_build_mix_ranks_liked_first():
    items = [
        {"path": "/m/a.mp3", "name": "Artist - Liked Song", "kind": "audio"},
        {"path": "/m/b.mp3", "name": "Other - Not Liked", "kind": "audio"},
    ]
    history = [{"title": "Liked Song", "artist": "Artist", "ts": 4102444800}]  # yakın tarih
    out = mix.build_mix(items, history=history, n=10, seed=0)
    assert out and "Liked" in out[0]["name"]


def test_build_mix_title_only_match():
    items = [
        {"path": "/m/x.mp3", "name": "Someone Else - Liked Song", "kind": "audio"},
        {"path": "/m/y.mp3", "name": "Nope", "kind": "audio"},
    ]
    history = [{"title": "Liked Song", "artist": "Original", "ts": 4102444800}]
    out = mix.build_mix(items, history=history, n=10, seed=1)
    assert "Liked" in out[0]["name"]   # sanatçı farklı olsa da başlık eşleşir


def test_build_mix_excludes_and_limits():
    items = [{"path": f"/m/{i}.mp3", "name": f"Track {i}", "kind": "audio"} for i in range(10)]
    out = mix.build_mix(items, n=4, exclude={"/m/0.mp3"}, seed=2)
    assert len(out) == 4
    assert all(t["path"] != "/m/0.mp3" for t in out)


def test_build_mix_empty_history_still_returns():
    items = [{"path": "/m/a.mp3", "name": "A", "kind": "audio"}]
    out = mix.build_mix(items, n=5, seed=3)
    assert len(out) == 1
