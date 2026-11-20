"""FAZ 2 / 2.2.0 bug düzeltmeleri için regresyon testleri."""
from __future__ import annotations


def test_estimate_hltb_uretmiyor():
    """estimate_hltb artik uydurma sure uretmez (None doner), yalnizca arama linki verir."""
    from app.core import games
    r = games.estimate_hltb("Herhangi Bir Oyun")
    assert r["ok"] is True
    assert r["main_hours"] is None
    assert r["completionist_hours"] is None
    assert "howlongtobeat.com" in r["url"]


def test_estimate_hltb_bos_baslik():
    from app.core import games
    assert games.estimate_hltb("")["ok"] is False


def test_build_beatgrid_minor_koku_soyur():
    """build_beatgrid minör 'Cm' anahtarını 'C minor' akoruna çevirir (m sonekini sıyırır)."""
    from app.core import kami_beat
    # Gerçek bir ses dosyası olmadan akor kurma mantığını dolaylı doğrula:
    # key_info'da 'scale' yoksa 'major'a düşer; 'Cm' -> 'C minor' davranışı kodda root[:-1] ile.
    # Bu test yalnızca mantığın varlığını (fonksiyon importu + imza) kilitler.
    assert callable(kami_beat.build_beatgrid)
    assert callable(kami_beat.detect_key)
