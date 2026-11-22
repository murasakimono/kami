"""Paket 2 arayuz kilidi, tek kapatma, ayna kilidi, Settings/room ve orta bug regresyon testleri."""
from __future__ import annotations

import ast
import http.client
import io
import json
import subprocess
import tempfile
import threading
import types
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parent.parent


def test_job_methods_and_js_slow_wiring():
    from app.ui.api import Api

    assert "scene_search" in Api.JOB_METHODS
    assert "item_peek" in Api.JOB_METHODS
    assert "music_lrc_polish_ollama" in Api.JOB_METHODS
    assert "music_whisper_lrc" not in Api.JOB_METHODS
    assert hasattr(Api, "audio_peaks")

    eco = (ROOT / "app/ui/web/ecosystem.js").read_text(encoding="utf-8")
    sunak = (ROOT / "app/ui/web/sunak.js").read_text(encoding="utf-8")
    k20 = (ROOT / "app/ui/web/kami-20.js").read_text(encoding="utf-8")
    kf = (ROOT / "app/ui/web/kamify-v138.js").read_text(encoding="utf-8")

    assert 'slow("scene_search"' in eco
    assert 'slow("item_peek"' in sunak
    assert 'slow("music_lrc_polish_ollama"' in k20
    assert 'slow("music_lrc_polish_ollama"' in kf


def test_aria2_engine_start_does_not_block_on_mirrors(tmp_path: Path, monkeypatch):
    from app.core import mirrors
    from app.core.models import Download
    from app.engines.aria2_engine import Aria2Engine

    eng = Aria2Engine(exe=tmp_path / "aria2c.exe", dht_file=tmp_path / "dht.dat")
    eng.auto_mirror = True
    calls: list[tuple] = []
    change_ev = threading.Event()
    gate = threading.Event()

    def fake_call(method, *params):
        calls.append((method, params))
        if method == "aria2.addUri":
            return "gid-1"
        if method == "aria2.changeUri":
            change_ev.set()
            return [0, 1]
        return None

    def slow_find(url, headers=None):
        gate.wait(2.0)
        return ["https://mirror.example.com/file.bin"]

    monkeypatch.setattr(eng, "call", fake_call)
    monkeypatch.setattr(mirrors, "find", slow_find)

    dl = Download(
        id=1,
        url="https://origin.example.com/file.bin",
        filename="file.bin",
        directory=str(tmp_path),
        category="other",
        status="queued",
    )
    t0 = threading.Event()
    gid = eng.start(dl)
    assert gid == "gid-1"
    # start() mirror bulunmasini beklemeden donebilmeli; changeUri henuz cagrilmamali
    assert not change_ev.is_set()
    gate.set()
    assert change_ev.wait(2.0)
    assert any(m == "aria2.changeUri" and p[0] == "gid-1" for m, p in calls)
    del t0


def test_settings_load_coerces_and_falls_back_on_corrupt_types(tmp_path: Path):
    from app.core.settings import DEFAULTS, Settings

    p = tmp_path / "settings.json"
    p.write_text(
        json.dumps({"connections": "abc", "max_concurrent": "12", "player_engine": "bad_engine"}),
        encoding="utf-8",
    )
    st = Settings(p)
    assert st.get("connections") == DEFAULTS["connections"]
    assert st.get("max_concurrent") == 12
    assert st.get("player_engine") == DEFAULTS["player_engine"]


def test_room_cors_narrowing_and_poll_invalid_n():
    from urllib.parse import urlparse
    from app.core import room

    srv = room.RoomServer()
    info = srv.start("TestHost", tunnel=False, room_id="corsroom1")
    try:
        parsed = urlparse(info["local"])
        port = parsed.port
        base_path = parsed.path.rstrip("/")

        # Guvenli origin'ler izinli
        for origin in ("null", "http://127.0.0.1:8080", "https://kami-oda.kami-metehan.workers.dev"):
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
            c.request("GET", f"{base_path}/info", headers={"Origin": origin})
            r = c.getresponse()
            r.read()
            assert r.status == 200
            assert r.getheader("Access-Control-Allow-Origin") == origin
            c.close()

        # Yabanci origin engelli (ACAO donmez)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", f"{base_path}/info", headers={"Origin": "https://evil.example"})
        r = c.getresponse()
        r.read()
        assert r.status == 200
        assert r.getheader("Access-Control-Allow-Origin") is None
        c.close()

        # poll?n=abc ValueError atmamali (200 donmeli)
        c = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
        c.request("GET", f"{base_path}/poll?id=u1&n=abc&a=xyz")
        r = c.getresponse()
        body = json.loads(r.read().decode("utf-8"))
        assert r.status == 200 and "events" in body
        c.close()
    finally:
        srv.stop()


def test_medium_fixes_m3u_hex_tts_and_librespot(tmp_path: Path, monkeypatch):
    from app.core import librespot_host, music_tag, picture_pro, reader

    # 1) m3u_export path traversal reddi + temiz ad
    song = tmp_path / "song.mp3"
    song.write_bytes(b"ID3")
    bad = music_tag.m3u_export(str(tmp_path), name="../../evil")
    assert bad["ok"] is False and bad["error"] == "invalid_name"
    good = music_tag.m3u_export(str(tmp_path), name="favori*liste")
    assert good["ok"] is True and Path(good["path"]).parent == tmp_path.resolve()

    # 2) _parse_hex_rgba gecersiz hex'te cokmemeli
    assert picture_pro._parse_hex_rgba("#ZZZZZZ") == (255, 255, 255, 255)
    assert picture_pro._parse_hex_rgba("#ff00aa") == (255, 0, 170, 255)

    # 3) reader.speak Piper hatasinda gecici .wav dosyasini silmeli
    monkeypatch.setattr(reader, "ensure_tts", lambda _lang: tmp_path / "m.onnx")
    monkeypatch.setattr(reader, "piper_exe", lambda: tmp_path / "piper.exe")
    fake_wav = Path(tempfile.gettempdir()) / f"kami_tts_{threading.get_ident()}.wav"

    def fake_run(*_a, **_kw):
        fake_wav.write_bytes(b"RIFF")
        return types.SimpleNamespace(returncode=1, stderr=b"piper err")

    with patch("subprocess.run", side_effect=fake_run):
        try:
            reader.speak("deneme", lang="tr")
            assert False, "RuntimeError bekleniyordu"
        except RuntimeError:
            pass
    assert not fake_wav.exists()

    # 4) librespot_host Popen hata atarsa log dosyasi kapanmali
    monkeypatch.setattr(librespot_host, "find_binary", lambda: "go-librespot.exe")
    monkeypatch.setattr(librespot_host, "_config_dir", lambda: tmp_path)
    monkeypatch.setattr(librespot_host, "_write_config", lambda _p: None)
    monkeypatch.setattr(librespot_host, "_pick_port", lambda: 12345)
    librespot_host._PROC = None
    opened_files: list[io.BytesIO] = []
    orig_open = open

    class _TrackedFile(io.BytesIO):
        def __exit__(self, *args):
            super().close()
            return False

    def fake_open(file, mode="r", *a, **kw):
        if str(file).endswith("librespot.log") and "a" in str(mode):
            f = _TrackedFile()
            opened_files.append(f)
            return f
        return orig_open(file, mode, *a, **kw)

    with patch("builtins.open", side_effect=fake_open), patch("subprocess.Popen", side_effect=OSError("boom")):
        res = librespot_host.ensure_started(download=False)
    assert res["ok"] is False and len(opened_files) == 1 and opened_files[0].closed is True


def test_main_py_unified_idempotent_shutdown():
    src = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "def _shutdown_once()" in src
    assert "shutdown_lock = threading.Lock()" in src
    tree = ast.parse(src)
    calls: dict[str, list[str]] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "quit_app":
            calls["quit_app"] = [
                sub.func.id for sub in ast.walk(node)
                if isinstance(sub, ast.Call) and isinstance(sub.func, ast.Name)
            ]
    assert "_shutdown_once" in calls.get("quit_app", [])
    assert src.count("_shutdown_once()") >= 3  # def disinda quit_app + finally icinde
