"""Kami 2.0 canli inceleme hata duzeltme ve regresyon testleri."""
from __future__ import annotations

import inspect
import json
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parent.parent


def test_winwin_resize_pill_accepts_anchor_top_center():
    from app.core import winwin

    sig = inspect.signature(winwin.resize_pill)
    assert "anchor_top_center" in sig.parameters
    # Olmayan pencere icin TypeError yerine False donmeli
    assert winwin.resize_pill("Olmayan Pencere 200", 540, 76, anchor_top_center=True) is False


def test_room_has_hmac_import_and_portal_js_prefix():
    from app.core import room, phone

    assert hasattr(room, "hmac")
    assert "location.pathname.replace(/\\/+$/,'').replace(/\\/portal$/,'')" in phone._PORTAL_HTML


def test_phone_portal_data_includes_paths_and_recent_media(tmp_path: Path):
    from app.core.phone import PhoneServer

    sample = tmp_path / "ornek.mp4"
    sample.write_bytes(b"mp4")
    srv = PhoneServer(
        0,
        lambda: "secret",
        lambda txt: 0,
        status=lambda: [{"id": 1, "name": "indirilen.mp4", "path": str(sample), "percent": 100, "label": "bitti"}],
    )
    extra_vid = tmp_path / "son_acilan.mkv"
    extra_vid.write_bytes(b"mkv")
    srv.recent_media = lambda: [{"id": None, "name": "son_acilan.mkv", "path": str(extra_vid), "pct": 0, "label": "Son"}]
    data = srv.portal_data()
    assert data["ok"] is True
    paths = {m["path"] for m in data["media"]}
    assert str(sample.resolve()) in paths
    assert str(extra_vid.resolve()) in paths
    assert srv.resolve_portal_file(str(sample)) == str(sample.resolve())
    assert srv.resolve_portal_file(str(extra_vid)) == str(extra_vid.resolve())


def test_music_hub_spotify_now_falls_back_to_librespot(monkeypatch):
    from app.core import music_hub

    fake_lib = {
        "ok": True,
        "playing": True,
        "id": "t1",
        "uri": "spotify:track:t1",
        "title": "Bagpipes From Baghdad",
        "artist": "Eminem",
        "album": "Relapse",
        "cover": "https://img/cover.jpg",
        "progress_ms": 12000,
        "duration_ms": 283000,
        "device_name": "Kami",
    }
    monkeypatch.setattr(music_hub, "get_spotify_token", lambda tok="": "fake-tok")
    monkeypatch.setattr(music_hub, "_librespot_now", lambda: dict(fake_lib))

    class _FakeResp:
        def __init__(self, status: int, payload: dict):
            self.status = status
            self._b = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    # 1) Web API item bos donerse librespot kullanilmali
    monkeypatch.setattr(music_hub.urllib.request, "urlopen", lambda req, timeout=6: _FakeResp(200, {"is_playing": False, "item": {}}))
    res1 = music_hub.spotify_now("")
    assert res1["title"] == "Bagpipes From Baghdad"
    assert res1["playing"] is True

    # 2) Web API hata firlatirsa da librespot'a dusmeli
    def _boom(*a, **kw):
        raise RuntimeError("429")

    monkeypatch.setattr(music_hub.urllib.request, "urlopen", _boom)
    res2 = music_hub.spotify_now("")
    assert res2["title"] == "Bagpipes From Baghdad"


def test_api_whisper_lrc_methods_and_async_job(tmp_path: Path, monkeypatch):
    from app.ui.api import Api
    from app.core import aitools

    mp3 = tmp_path / "song.mp3"
    mp3.write_bytes(b"ID3")
    api = object.__new__(Api)
    import threading
    api._inbox_lock = threading.Lock()
    api._jobs = {}
    api._manager = SimpleNamespace(settings=SimpleNamespace(get=lambda k, d=None: {"whisper_lang": "tr", "lyrics_embed": True}.get(k, d)))

    monkeypatch.setattr(aitools, "installed", lambda name: False)
    miss = api.music_lrc_whisper(str(mp3), "tr", True)
    assert miss["ok"] is False and miss["error"] == "tool_missing" and miss["tool"] == "whisper"

    monkeypatch.setattr(aitools, "installed", lambda name: True)
    monkeypatch.setattr(
        aitools,
        "generate_mp3_lrc",
        lambda path, **kw: {"ok": True, "path": path, "lines": [{"t": 1.0, "text": "deneme"}]},
    )
    queued = api.music_whisper_lrc(str(mp3), "tr", True)
    assert queued["ok"] is True and queued["queued"] is True and queued["job_id"]
    for _ in range(50):
        st = api.music_lrc_job_status(queued["job_id"])
        if st.get("state") == "done":
            assert st["result"]["lines"][0]["text"] == "deneme"
            break
        import time
        time.sleep(0.02)
    else:
        raise AssertionError("Whisper LRC arka plan isi zamaninda bitmedi")


def test_web_and_main_live_regression_markers():
    main_py = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "main_ready.is_set()" in main_py
    assert "resizable=True," in main_py

    guard_js = (ROOT / "app" / "ui" / "web" / "kami-guard.js").read_text(encoding="utf-8")
    assert "err.code === 1" in guard_js

    gpu_js = (ROOT / "app" / "ui" / "web" / "sunak-gpu.js").read_text(encoding="utf-8")
    assert '"low-power"' in gpu_js
    assert '"high-performance"' not in gpu_js
    assert 'window.addEventListener("blur", syncRun)' in gpu_js

    player_js = (ROOT / "app" / "ui" / "web" / "player.js").read_text(encoding="utf-8")
    assert "PL.eqRaf = requestAnimationFrame(loop)" in player_js

    kami20_js = (ROOT / "app" / "ui" / "web" / "kami-20.js").read_text(encoding="utf-8")
    assert "music_whisper_lrc" in kami20_js
    assert "music_lrc_polish_ollama" in kami20_js
