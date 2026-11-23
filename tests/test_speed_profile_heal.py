"""23.11 canli bulgu: Oda otomatik hiz profili kalici ayara yaziliyordu; Kami odadayken kapaninca hiz 8 MB/s'de takili kaliyordu."""
import time
from types import SimpleNamespace

from app.ui.api import Api


class _S:
    def __init__(self, d): self.d = dict(d)
    def get(self, k, default=None): return self.d.get(k, default)
    def set(self, k, v): self.d[k] = v


def _api(settings):
    a = Api.__new__(Api)
    a._manager = SimpleNamespace(settings=settings)
    a._engine = None
    a._manual_speed_profile = Api._initial_manual_speed_profile(settings)
    a._auto_speed_reason = ""
    return a


PROFS = {"full": 0, "game": 12288, "room": 8192, "night": 4096}


def test_stuck_room_profile_heals_on_start():
    s = _S({"speed_profile": "room", "speed_limit_kib": 8192, "speed_profiles": PROFS})   # eski surumden kalan kayit
    a = _api(s)
    assert a._manual_speed_profile == "full"
    a.heal_speed_profile()
    assert s.get("speed_profile") == "full" and s.get("speed_limit_kib") == 0


def test_manual_choice_survives_auto_room():
    s = _S({"speed_profile": "night", "speed_profile_manual": "night", "speed_profiles": PROFS})
    a = _api(s)
    a.speed_profile_set("room", auto=True, reason="room")
    assert s.get("speed_profile") == "room" and s.get("speed_profile_manual") == "night"
    b = _api(s)            # Kami odadayken kapandi, yeniden acildi
    b.heal_speed_profile()
    assert s.get("speed_profile") == "night" and s.get("speed_limit_kib") == 4096


def test_stale_room_restores_speed():
    s = _S({"speed_profile": "full", "speed_profiles": PROFS})
    a = _api(s)
    a.speed_profile_set("room", auto=True, reason="room")
    a._room_island = {"t": time.time() - 60, "people": []}
    # music_island_tick'in yalniz Oda bekcisi kismini calistir (geri kalani Windows/Spotify ister)
    try:
        a.music_island_tick()
    except Exception:
        pass
    assert s.get("speed_profile") == "full" and a._auto_speed_reason == ""
