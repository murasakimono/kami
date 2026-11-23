"""2.5.6: telefondaki Spotify adayi acmasin; odada yalniz ben varken hiz siniri/serit yok."""
import platform
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.ui.api import Api


def test_music_here_only_local():
    assert Api._music_here({"local_librespot": True})
    assert Api._music_here({"device_name": platform.node().upper()})
    assert not Api._music_here({"device_name": "Metehan's iPhone"})
    assert not Api._music_here({"device_name": ""})
    assert not Api._music_here(None)


def test_phone_spotify_does_not_open_island(monkeypatch):
    from app.core import music_hub, winwin
    a = object.__new__(Api)
    a._island_shown, a._island_auto, a._island_win, a._island_factory = False, False, None, None
    calls = []
    a.mini_island_toggle = lambda show=None, persist=True: calls.append(show) or {"ok": True}
    monkeypatch.setattr(music_hub, "cached_now", lambda **k: {"playing": True, "title": "X", "device_name": "iPhone"})
    monkeypatch.setattr(winwin, "find_window", lambda t: 123)
    monkeypatch.setattr(winwin, "is_visible", lambda h: False)
    a.music_island_tick()
    assert True not in calls


def _room_api():
    a = object.__new__(Api)
    a._manager = SimpleNamespace(settings=SimpleNamespace(get=lambda k, d=None: True if k == "room_island" else d))
    a._room_island, a._island_shown, a._island_auto = None, False, False
    a._auto_speed_reason = ""
    a.speed = []
    a.speed_profile_set = lambda p, auto=False, reason="": a.speed.append(p) or setattr(a, "_auto_speed_reason", reason)
    a.mini_island_toggle = MagicMock(side_effect=lambda show=None, persist=True: setattr(a, "_island_shown", bool(show)))
    a._restore_manual_speed = lambda *x, **k: None
    return a


def test_room_alone_no_limit_no_strip(monkeypatch):
    monkeypatch.setattr(Api, "_room_window_visible", staticmethod(lambda: False))   # gizli 'hep acik' oda
    a = _room_api()
    a.room_island_push({"people": [{"name": "Metehan", "me": True}]})
    assert a._room_island is None and "room" not in a.speed and not a._island_shown


def test_room_with_guest_limits_and_strip(monkeypatch):
    monkeypatch.setattr(Api, "_room_window_visible", staticmethod(lambda: False))
    a = _room_api()
    a.room_island_push({"people": [{"name": "Metehan", "me": True}, {"name": "Ilayda"}]})
    assert a._room_island is not None and "room" in a.speed and a._island_shown


def test_room_alone_visible_strip_but_no_limit(monkeypatch):
    monkeypatch.setattr(Api, "_room_window_visible", staticmethod(lambda: True))    # kullanici Oda'yi acti, tek basina
    a = _room_api()
    a.room_island_push({"people": [{"name": "Metehan", "me": True}]})
    assert a._island_shown and "room" not in a.speed


def test_music_here_by_device_type_and_stable():
    assert Api._music_where({"device_name": "METEHAN-PC", "device_type": "Computer"}) is True
    assert Api._music_where({"device_name": "iPhone", "device_type": "Smartphone"}) is False
    assert Api._music_where({"device_name": "Kami"}) is True
    a = object.__new__(Api)
    here, phone = {"local_librespot": True}, {"device_name": "iPhone", "device_type": "Smartphone"}
    assert a._music_here_stable(here)
    assert a._music_here_stable(phone) and a._music_here_stable(phone)   # tek tuk sapma adayi kapatmaz
    assert not a._music_here_stable(phone)                              # 3. ardisik okumada duser
    assert a._music_here_stable(here)
