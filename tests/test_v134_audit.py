from __future__ import annotations

from pathlib import Path


def test_games_dedup_exact_and_variant_titles(monkeypatch, tmp_path):
    from app.core import games
    monkeypatch.setattr(games, "_playtime_path", lambda: tmp_path / "pt.json")
    monkeypatch.setattr(games, "_covers_cache_path", lambda: tmp_path / "cov.json")
    monkeypatch.setattr(games, "_scan_steam", lambda: [
        {"store": "Steam", "id": "100", "title": "Cyberpunk 2077", "path": "C:/Games/CP", "size": 10, "installed": True, "launch": "steam://rungameid/100", "cover": "c1"},
    ])
    monkeypatch.setattr(games, "_scan_epic", lambda: [
        {"store": "Epic", "id": "cp_ep", "title": "  cyberpunk   2077 ", "path": "", "size": 0, "installed": True, "launch": "epic://cp", "cover": ""},
    ])
    monkeypatch.setattr(games, "_scan_gog", lambda: [
        {"store": "GOG", "id": "cp_gog", "title": "Cyberpunk 2077: Definitive Edition", "path": "", "size": 0, "installed": True, "launch": "C:/GOG/CP", "cover": ""},
    ])
    monkeypatch.setattr(games, "_scan_steam_owned", lambda: [
        {"store": "Steam", "id": "100", "title": "Cyberpunk 2077", "path": "", "size": 0, "installed": False, "launch": "steam://install/100", "cover": "c1"},
    ])
    res = games.list_games(include_owned=True)
    assert res["ok"] is True
    assert res["count"] == 1
    assert len(res["games"][0]["stores"]) == 3


def test_voice_cmd_turkish_normalization():
    from app.core.voice_cmd import parse_voice_command
    r1 = parse_voice_command("Hey Kami başlat")
    assert r1["ok"] and r1["action"] == "play"
    r2 = parse_voice_command("kami ekranı oku lütfen", require_wake=False)
    assert r2["ok"] and r2["action"] in ("ocr", "unknown")
    r3 = parse_voice_command("Hey Kami sustur")
    assert r3["ok"] and r3["action"] == "mute"


def test_kasa_doc_indexing_and_search(tmp_path):
    from app.core import semantic_vault as sv
    md = tmp_path / "kardiyoloji_notlari.md"
    md.write_text("Atriyal fibrilasyon EKG bulgulari: duzensiz R-R araligi ve P dalgasi yoklugu.", encoding="utf-8")
    db = tmp_path / "kasa.db"
    res = sv.index_document(md, db_path=db)
    assert res["ok"] is True and res["indexed"] >= 1
    hit = sv.semantic_search("Atriyal fibrilasyon", limit=5, db_path=db)
    assert len(hit["results"]) >= 1
    assert hit["results"][0]["kind"] == "doc"


def test_studio_google_fonts_and_tr_map(tmp_path):
    from app.core import studio
    assert len(studio.GOOGLE_FONTS) >= 40
    tr_map = studio.font_tr_map({})
    assert tr_map == {}
