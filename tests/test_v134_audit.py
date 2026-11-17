from __future__ import annotations

from pathlib import Path


def test_games_dedup_exact_and_variant_titles(monkeypatch, tmp_path):
    from app.core import games
    monkeypatch.setattr(games, "_playtime_path", lambda: tmp_path / "pt.json")
    monkeypatch.setattr(games, "_covers_cache_path", lambda: tmp_path / "cov.json")
    monkeypatch.setattr(games, "_playnite_cache_path", lambda: tmp_path / "pn.json")
    monkeypatch.setattr(games, "_custom_games_path", lambda: tmp_path / "cust.json")
    monkeypatch.setattr(games, "_scan_riot", lambda: [])
    monkeypatch.setattr(games, "import_playnite_library", lambda *a, **kw: {"ok": False})
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


def test_music_local_folder_scan(monkeypatch, tmp_path):
    from app.core import music_hub as mh
    monkeypatch.setattr(mh, "_folders_file", lambda: tmp_path / "folders.json")
    mdir = tmp_path / "Contra"
    mdir.mkdir()
    (mdir / "01_akrep.mp3").write_bytes(b"ID3")
    (mdir / "not_audio.txt").write_text("hi", encoding="utf-8")
    r = mh.local_folders_add(str(mdir))
    assert r["ok"] is True and str(mdir) in r["folders"]
    sc = mh.local_scan_folder(str(mdir))
    assert sc["ok"] is True and len(sc["items"]) == 1 and sc["items"][0]["title"] == "01_akrep"


def test_spotify_like_uses_new_library_endpoints(monkeypatch):
    from app.core import music_hub as mh
    calls = []
    def fake_sp_api(method, path, body=None, token=""):
        calls.append((method, path, body))
        return {"ok": True, "data": [True]}
    monkeypatch.setattr(mh, "_sp_api", fake_sp_api)
    r1 = mh.spotify_like_check("abc123")
    assert r1["ok"] and r1["liked"] is True
    assert calls[-1][0] == "GET" and "/me/library/contains" in calls[-1][1] and "spotify%3Atrack%3Aabc123" in calls[-1][1]
    mh.spotify_like_toggle("spotify:track:xyz", True)
    assert calls[-1][0] == "PUT" and "/me/library?" in calls[-1][1]
    mh.spotify_like_toggle("xyz", False)
    assert calls[-1][0] == "DELETE" and "/me/library?" in calls[-1][1]

