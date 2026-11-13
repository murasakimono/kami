import zipfile
from unittest.mock import MagicMock

import app.core.kami_beat as kami_beat
import app.core.kami_hunter as kami_hunter
import app.core.kami_mod as kami_mod
import app.core.phone as phone_mod


def test_atempo_chain_bounds():
    assert kami_beat._atempo_chain(1.5) == "atempo=1.50000"
    chain_slow = kami_beat._atempo_chain(0.25)
    assert chain_slow.count("atempo=") >= 2
    assert "0.50000" in chain_slow
    chain_fast = kami_beat._atempo_chain(3.0)
    assert "atempo=2.0" in chain_fast
    assert "1.50000" in chain_fast


def test_mashup_missing_file(tmp_path):
    res = kami_beat.mashup(str(tmp_path / "missing_v.wav"), str(tmp_path / "missing_b.wav"))
    assert res["ok"] is False
    assert "error" in res


def test_hunter_search_aggregates_and_deduplicates():
    def fake_get(url, params=None, headers=None, timeout=None):
        resp = MagicMock()
        resp.status_code = 200
        if "archive.org/advancedsearch" in url:
            resp.json.return_value = {
                "response": {
                    "docs": [
                        {"identifier": "ia-item-1", "title": "Track One", "mediatype": "audio"},
                    ]
                }
            }
        elif "dailymotion.com" in url:
            resp.json.return_value = {
                "list": [
                    {"id": "dm1", "title": "DM Track", "url": "https://www.dailymotion.com/video/dm1"},
                ]
            }
        elif "web.archive.org/cdx" in url:
            resp.json.return_value = [
                ["urlkey", "timestamp", "original"],
                ["dm1", "20150101000000", "https://www.dailymotion.com/video/dm1"],
                ["old", "20120101000000", "https://example.com/old.mp3"],
            ]
        elif "reddit.com" in url:
            resp.json.return_value = {
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Lost Track",
                                "url": "https://example.com/old.mp3",
                            }
                        },
                        {
                            "data": {
                                "title": "Duplicate DM",
                                "url": "https://www.dailymotion.com/video/dm1",
                            }
                        },
                    ]
                }
            }
        else:
            resp.json.return_value = {}
        return resp

    sess = MagicMock()
    sess.get.side_effect = fake_get
    res = kami_hunter.search("lost track", site="example.com", session=sess)
    assert res["ok"] is True
    urls = [item["url"] for item in res["items"]]
    assert len(urls) == len(set(urls))
    assert any("archive.org/details/ia-item-1" in u for u in urls)
    assert any("dailymotion.com/video/dm1" in u for u in urls)
    assert any("web.archive.org/web/20120101000000id_/https://example.com/old.mp3" in u for u in urls)
    assert any(u == "https://example.com/old.mp3" for u in urls)


def test_mod_install_list_rollback_and_zipslip(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(kami_mod.paths, "DATA_DIR", data_dir)

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    existing = game_dir / "config.txt"
    existing.write_text("original", encoding="utf-8")

    good_zip = tmp_path / "good_mod.zip"
    with zipfile.ZipFile(good_zip, "w") as zf:
        zf.writestr("config.txt", "modded")
        zf.writestr("sub/new.txt", "added")

    inst = kami_mod.install_mod(str(good_zip), str(game_dir))
    assert inst["ok"] is True
    assert existing.read_text(encoding="utf-8") == "modded"
    assert (game_dir / "sub" / "new.txt").read_text(encoding="utf-8") == "added"

    mods = kami_mod.list_mods()
    assert len(mods) == 1
    mod_id = mods[0]["id"]

    rb = kami_mod.rollback_mod(mod_id)
    assert rb["ok"] is True
    assert existing.read_text(encoding="utf-8") == "original"
    assert not (game_dir / "sub" / "new.txt").exists()

    evil_zip = tmp_path / "evil_mod.zip"
    with zipfile.ZipFile(evil_zip, "w") as zf:
        zf.writestr("../evil.txt", "pwned")
    bad = kami_mod.install_mod(str(evil_zip), str(game_dir))
    assert bad["ok"] is False
    assert not (tmp_path / "evil.txt").exists()


def test_phone_bridge_and_on_upload():
    assert "Kami" in phone_mod._BRIDGE_HTML
    assert "'upload'" in phone_mod._BRIDGE_HTML
    assert 'accept="audio/*" capture' in phone_mod._BRIDGE_HTML
    assert "'pad:'+a" in phone_mod._BRIDGE_HTML
    cb = MagicMock()
    srv = phone_mod.PhoneServer(port=0, key=lambda: "k", on_text=lambda t, f: 0)
    assert srv.on_upload is None
    srv.on_upload = cb
    assert srv.on_upload is cb


def test_mod_conflict_prevents_old_rollback(tmp_path, monkeypatch):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    monkeypatch.setattr(kami_mod.paths, "DATA_DIR", data_dir)

    game_dir = tmp_path / "game"
    game_dir.mkdir()
    (game_dir / "shared.txt").write_text("base", encoding="utf-8")

    z1 = tmp_path / "mod_a.zip"
    with zipfile.ZipFile(z1, "w") as zf:
        zf.writestr("shared.txt", "from_a")
    z2 = tmp_path / "mod_b.zip"
    with zipfile.ZipFile(z2, "w") as zf:
        zf.writestr("shared.txt", "from_b")

    r1 = kami_mod.install_mod(str(z1), str(game_dir))
    r2 = kami_mod.install_mod(str(z2), str(game_dir))
    assert r1["ok"] and r2["ok"]

    blocked = kami_mod.rollback_mod(r1["id"])
    assert blocked["ok"] is False
    assert "Çakışan" in blocked["error"]
    assert kami_mod.rollback_mod(r2["id"])["ok"] is True
    assert kami_mod.rollback_mod(r1["id"])["ok"] is True
    assert (game_dir / "shared.txt").read_text(encoding="utf-8") == "base"
