"""24.11: YouTube koruma hatasinda acil yt-dlp guncellemesi + yeniden deneme."""
import sys
import types

from app.engines import ytdlp_engine as ye


def test_challenge_patterns():
    assert ye.looks_like_challenge("ERROR: [youtube] x: Requested format is not available.")
    assert ye.looks_like_challenge("[youtube] x: n challenge solving failed: Some formats may be missing")
    assert ye.looks_like_challenge("Only images are available for download")
    assert not ye.looks_like_challenge("HTTP Error 404: Not Found")


def test_emergency_only_youtube_and_rate_limited(monkeypatch):
    calls = []
    monkeypatch.setattr(ye, "update_pylib", lambda p: calls.append(p) or "2099.1.1")
    monkeypatch.setattr(ye, "_reload_ytdlp", lambda: True)
    from app import paths
    monkeypatch.setattr(paths, "FROZEN", True, raising=False)
    monkeypatch.setattr(ye, "_emergency_last", 0.0)
    assert not ye.emergency_update("https://vimeo.com/1", "Requested format is not available")
    assert not ye.emergency_update("https://www.youtube.com/watch?v=a", "HTTP Error 404")
    assert ye.emergency_update("https://www.youtube.com/watch?v=a", "Requested format is not available")
    assert not ye.emergency_update("https://www.youtube.com/watch?v=a", "Requested format is not available")  # 30 dk siniri
    assert len(calls) == 1


def test_emergency_already_latest(monkeypatch):
    monkeypatch.setattr(ye, "update_pylib", lambda p: "")
    from app import paths
    monkeypatch.setattr(paths, "FROZEN", True, raising=False)
    monkeypatch.setattr(ye, "_emergency_last", 0.0)
    assert not ye.emergency_update("https://youtu.be/a", "n challenge solving failed")


def test_reload_skips_when_job_active(monkeypatch):
    monkeypatch.setattr(ye, "_active_jobs", 1)
    sys.modules.setdefault("yt_dlp_fake_marker", types.ModuleType("x"))
    assert ye._reload_ytdlp() is False


def test_reload_purges_modules(monkeypatch):
    monkeypatch.setattr(ye, "_active_jobs", 0)
    fake = types.ModuleType("yt_dlp")
    monkeypatch.setitem(sys.modules, "yt_dlp", fake)
    monkeypatch.setitem(sys.modules, "yt_dlp.extractor", types.ModuleType("yt_dlp.extractor"))
    monkeypatch.setattr(ye, "_registered", True)
    assert ye._reload_ytdlp() is True
    assert "yt_dlp" not in sys.modules and "yt_dlp.extractor" not in sys.modules
    assert ye._registered is False


def test_probe_retries_once_after_update(monkeypatch):
    n = {"c": 0}

    def fake_probe(url, headers=None, timeout=30.0):
        n["c"] += 1
        if n["c"] == 1:
            e = ye.MediaError("x")
            e.raw = "Requested format is not available"
            raise e
        return {"kind": "video"}
    monkeypatch.setattr(ye, "_probe", fake_probe)
    monkeypatch.setattr(ye, "emergency_update", lambda u, m: True)
    assert ye.probe("https://www.youtube.com/watch?v=a") == {"kind": "video"} and n["c"] == 2
