"""v2.5.3 denetim duzeltmeleri: regresyon testleri (davranis odakli)."""
from __future__ import annotations

import time
from pathlib import Path


def test_notification_push_signature_matches_call(tmp_path):
    from app.core.events import NotificationCenter
    nc = NotificationCenter()
    nc.push("done", "Indirme bitti", "a.mp4", path="C:/x/a.mp4", download_id=5)   # api._on_notify_dl ile ayni imza
    assert nc.unread_count() >= 1


def test_queue_store_list_after_close_returns_empty(tmp_path):
    from app.core.queue_store import DownloadStore
    s = DownloadStore(tmp_path / "k.db")
    s.close()
    assert s.list() == []   # kapanistan sonra gec gelen card_state cokmesin


def test_room_correct_password_never_locked_out(monkeypatch):
    from app.core import room
    r = room.RoomServer.__new__(room.RoomServer)
    r._bad = {}
    r.host_token = "host-tok"
    h = room.hash_pw("dogru-parola")
    r.key_hash = lambda: h
    monkeypatch.setattr(room.time, "sleep", lambda s: None)
    for _ in range(15):
        assert r.key_ok("yanlis", "1.2.3.4") is False
    assert r.key_ok("dogru-parola", "1.2.3.4") is True
    assert r.key_ok(h.split("$")[-1], "1.2.3.4") is False   # ozet parola yerine gecmez


def test_kapsul_reserve_respects_max_dl(tmp_path, monkeypatch):
    from app.core import kapsul
    store: dict = {"c1": {"name": "x", "max_dl": 2, "downloads": 0}}
    monkeypatch.setattr(kapsul, "_load", lambda: store)
    monkeypatch.setattr(kapsul, "_save", lambda items: None)
    monkeypatch.setattr(kapsul, "_notify", lambda *a, **k: None)
    assert kapsul.reserve_download("c1") and kapsul.reserve_download("c1")
    assert kapsul.reserve_download("c1") is False


def test_cleaner_trash_has_no_powershell_script():
    src = (Path(__file__).resolve().parent.parent / "app" / "core" / "cleaner.py").read_text(encoding="utf-8")
    i = src.index("def trash_path") if "def trash_path" in src else src.index("SendToRecycleBin") - 2000
    assert '"powershell"' not in src[i:i + 1500]


def test_spotify_now_cache_serves_without_network(monkeypatch):
    from app.core import music_hub as mh
    calls = []
    monkeypatch.setattr(mh, "_spotify_now_fetch", lambda tok: calls.append(1) or {"ok": True, "playing": True, "title": "x",
                                                                                     "progress_ms": 1000, "duration_ms": 9000})
    mh._NOW_META.update(t=0.0, res=None)
    a = mh.spotify_now("")
    b = mh.spotify_now("")
    assert len(calls) == 1 and a["title"] == b["title"] == "x"
    mh._NOW_META["t"] = time.monotonic() - 5   # bayat: aninda doner, tazeleme arka planda
    c = mh.spotify_now("")
    assert c["progress_ms"] >= 5000


def test_hltb_returns_found_false_on_network_error(monkeypatch):
    import requests
    from app.core import games_companion as gc

    class S:
        def get(self, *a, **k):
            raise requests.ConnectionError("x")
    monkeypatch.setattr(requests, "Session", lambda: S())
    gc._HLTB_TOKEN.update(tok="", t=0.0)
    h = gc.fetch_hltb_real("Oyun")
    assert h["found"] is False and "howlongtobeat.com" in h["url"]


def test_lifecycle_stop_event_exists_and_main_uses_it():
    from app.core.lifecycle import STOP
    assert not STOP.is_set()
    src = (Path(__file__).resolve().parent.parent / "app" / "main.py").read_text(encoding="utf-8")
    assert "_STOP.set()" in src and "while True:\n            time.sleep(2.0)" not in src


def test_room_peer_key_blocks_impersonation():
    from app.core import room
    r = room.Room("host")
    ok, key = r.bind_peer("p1", "")
    assert ok and key
    assert r.bind_peer("p1", "")[0] is False          # baskasi ayni kimlikle yoklayamaz
    assert r.bind_peer("p1", key)[0] is True
    assert r.peer_ok("p1", "yanlis") is False and r.peer_ok("p1", key) is True


def test_ini_fixer_does_not_append_unknown_keys_and_keeps_utf16(tmp_path):
    from app.core import games_companion as gc
    ini = tmp_path / "g.ini"
    ini.write_text("[/Script/Engine]\r\nbUseVSync=True\r\n", encoding="utf-16")
    r = gc.fix_game_ini(str(ini), ["disable_vsync"])
    txt = ini.read_text(encoding="utf-16")
    assert r["ok"] and "bUseVSync=False" in txt and "iPresentInterval" not in txt
    assert "iPresentInterval" in r["not_found"]


def test_kamipack_rejects_files_missing_from_manifest(tmp_path):
    import json, zipfile
    from app.core import kamipack
    pk = tmp_path / "x.kamipack"
    with zipfile.ZipFile(pk, "w") as zf:
        payload = b"{}"
        zf.writestr("manifest.json", json.dumps({"format": kamipack.PACK_FORMAT,
                                                 "sha256": {"payload.json": kamipack._sha256_bytes(payload)}}))
        zf.writestr("payload.json", payload)
        zf.writestr("assets/evil.png", b"x")
    fn = getattr(kamipack, "inspect_kamipack", None) or getattr(kamipack, "verify_kamipack", None) or getattr(kamipack, "read_kamipack")
    assert fn(str(pk))["ok"] is False
