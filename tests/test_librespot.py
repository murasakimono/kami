"""go-librespot (dahili Spotify Connect calici) birim testleri."""
from __future__ import annotations

import json


def test_librespot_config_and_credentials(tmp_path, monkeypatch):
    from app import paths
    from app.core import librespot_host

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    cfg = librespot_host._write_config(3678)
    txt = cfg.read_text(encoding="utf-8")
    assert 'device_name: "Kami"' in txt
    assert 'audio_backend: "wasapi"' in txt
    assert "port: 3678" in txt
    assert 'type: "device_auth"' in txt
    assert not librespot_host.has_credentials()

    state = tmp_path / "go-librespot" / "state.json"
    state.write_text(json.dumps({"credentials": {"username": "u1", "data": "abc"}}), encoding="utf-8")
    assert librespot_host.has_credentials()


def test_music_hub_prefers_librespot_when_no_external_device(monkeypatch):
    from app.core import librespot_host, music_hub

    monkeypatch.setattr(music_hub, "_sp_pick_device", lambda launch=False: "")
    monkeypatch.setattr(librespot_host, "status", lambda: {"ok": True, "installed": True, "running": True, "paired": True})
    called = {}
    monkeypatch.setattr(
        librespot_host,
        "play_uri",
        lambda uri="", context_uri="", position_ms=0: called.update({"uri": uri, "ctx": context_uri}) or {"ok": True, "local_librespot": True},
    )

    r = music_hub.spotify_play_uri("spotify:track:abc")
    assert r["ok"] is True and r["local_librespot"] is True
    assert called == {"uri": "spotify:track:abc", "ctx": ""}


def test_music_hub_returns_pair_prompt_when_unpaired(monkeypatch):
    from app.core import librespot_host, music_hub

    monkeypatch.setattr(music_hub, "_sp_pick_device", lambda launch=False: "")
    monkeypatch.setattr(
        librespot_host,
        "status",
        lambda: {"ok": True, "installed": True, "running": True, "paired": False, "pair_url": "https://spotify.com/pair?code=XYZ", "pair_code": "XYZ"},
    )

    r = music_hub.spotify_play_uri("spotify:track:abc")
    assert r["ok"] is False
    assert r["error"] == "librespot_pair"
    assert r["pair_code"] == "XYZ"
