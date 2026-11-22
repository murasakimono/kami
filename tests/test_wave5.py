"""Dalga 5 (Games Companion, Oracle Relay & Sunak Ctrl+K v2) birim ve sozlesme testleri."""
from __future__ import annotations

import json
import zipfile
from pathlib import Path
from unittest.mock import MagicMock, patch

ROOT = Path(__file__).resolve().parent.parent


def test_hltb_and_pcgamingwiki_mocked():
    from app.core import games_companion as gc

    m_hltb = MagicMock(status_code=200)
    m_hltb.json.return_value = {"data": [{"game_name": "Elden Ring", "game_id": 68151, "comp_main": 216000, "comp_plus": 360000, "comp_100": 486000}]}
    with patch("requests.post", return_value=m_hltb):
        h = gc.fetch_hltb_real("Elden Ring")
    assert h["ok"] is True and h["main_hours"] == 60.0

    m_pcg = MagicMock(status_code=200)
    m_pcg.json.return_value = ["Elden Ring", ["Elden Ring"], [""], ["https://www.pcgamingwiki.com/wiki/Elden_Ring"]]
    with patch("requests.get", return_value=m_pcg):
        w = gc.fetch_pcgamingwiki("Elden Ring")
    assert w["ok"] is True and "pcgamingwiki.com" in w["url"]


def test_save_editor_ini_fixer_and_timemachine(tmp_path, monkeypatch):
    from app.core import games_companion as gc

    monkeypatch.setattr(gc, "_timemachine_dir", lambda: tmp_path / "tm")

    sav = tmp_path / "save.json"
    sav.write_text('{"gold": 100}', encoding="utf-8")
    ins = gc.save_inspect(str(sav))
    assert ins["ok"] is True and ins["kind"] == "json"
    wr = gc.save_write(str(sav), '{"gold": 9999}')
    assert wr["ok"] is True and Path(wr["backup"]).is_file()
    assert json.loads(sav.read_text(encoding="utf-8"))["gold"] == 9999

    ini = tmp_path / "Engine.ini"
    ini.write_text("[SystemSettings]\nbSmoothFrameRate=True\n", encoding="utf-8")
    fx = gc.fix_game_ini(str(ini))
    assert fx["ok"] is True and "bSmoothFrameRate=False" in ini.read_text(encoding="utf-8")

    sn = gc.snapshot_save("elden_ring", str(sav))
    assert sn["ok"] is True
    lst = gc.list_snapshots("elden_ring")
    assert len(lst["snapshots"]) == 1
    sav.write_text('{"gold": 0}', encoding="utf-8")
    rs = gc.restore_snapshot(sn["snapshot"], str(tmp_path))
    assert rs["ok"] is True
    assert json.loads(sav.read_text(encoding="utf-8"))["gold"] == 9999


def test_kami_mod_install_and_rollback(tmp_path, monkeypatch):
    from app.core import games_companion as gc

    monkeypatch.setattr(gc, "_mod_backups_dir", lambda: tmp_path / "mb")

    gdir = tmp_path / "Game"
    gdir.mkdir()
    orig = gdir / "lang.pak"
    orig.write_bytes(b"ORIGINAL")

    mz = tmp_path / "tr_yama.zip"
    with zipfile.ZipFile(mz, "w") as zf:
        zf.writestr("lang.pak", b"TURKISH")
        zf.writestr("extra_font.ttf", b"FONT")

    inst = gc.mod_install_zip("cyberpunk", str(gdir), str(mz))
    assert inst["ok"] is True and inst["overwritten"] == 1 and inst["added"] == 1
    assert orig.read_bytes() == b"TURKISH"
    assert (gdir / "extra_font.ttf").is_file()

    rb = gc.mod_rollback(inst["backup_dir"])
    assert rb["ok"] is True and rb["restored"] == 1 and rb["removed"] == 1
    assert orig.read_bytes() == b"ORIGINAL"
    assert not (gdir / "extra_font.ttf").exists()


def test_subtitle_candidate_filter_and_ocr_chain(tmp_path, monkeypatch):
    from PIL import Image
    from app.core import games_companion as gc

    assert gc.is_subtitle_candidate("34 ABC 123") is False
    assert gc.is_subtitle_candidate("HP 100") is False
    assert gc.is_subtitle_candidate("99:59") is False
    assert gc.is_subtitle_candidate("We need to get out of the city before dawn.") is True

    monkeypatch.setattr("app.paths.DATA_DIR", tmp_path)
    gc._OCR_LAST.update(raw="", tr="")
    fake_img = Image.new("RGB", (400, 200), (0, 0, 0))
    with patch("PIL.ImageGrab.grab", return_value=fake_img), \
         patch("app.core.ocr.read_text", return_value={"ok": True, "text": "34 ABC 123"}):
        skip_res = gc.game_ocr_translate()
        assert skip_res["ok"] is True and skip_res["skipped"] is True

    with patch("PIL.ImageGrab.grab", return_value=fake_img), \
         patch("app.core.ocr.read_text", return_value={"ok": True, "text": "Stay close to me until sunrise."}), \
         patch.object(gc, "_translate_to_tr", return_value="Gün doğumuna kadar yanımda kal."):
        ok_res = gc.game_ocr_translate()
        assert ok_res["ok"] is True and ok_res["translated"] == "Gün doğumuna kadar yanımda kal."


def test_oracle_relay_and_crash_recovery(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from app.core import oracle_relay as orel
    from app.ui.api import Api

    monkeypatch.setattr(orel, "_crash_file", lambda: tmp_path / "crash.json")

    mr = MagicMock(status_code=200, headers={"content-type": "application/json"})
    mr.json.return_value = {"alive": True}
    with patch("requests.get", return_value=mr):
        pr = orel.relay_ping("https://relay.example.com", "secret123")
    assert pr["ok"] is True

    fake_mgr = MagicMock()
    fake_mgr.snapshot.return_value = [
        SimpleNamespace(id=7, url="https://x/a.zip", filename="a.zip", status="active", directory="C:/dl"),
        SimpleNamespace(id=8, url="https://x/b.zip", filename="b.zip", status="complete", directory="C:/dl"),
    ]
    fake_api = Api.__new__(Api)
    fake_api._manager = fake_mgr
    snap_res = fake_api.oracle_crash_snapshot()
    assert snap_res["ok"] is True and snap_res["count"] == 1
    ld = orel.load_crash_snapshot()
    assert ld["ok"] is True and len(ld["items"]) == 1 and ld["items"][0]["id"] == 7


def test_wave5_api_surface_and_ui_contracts():
    import ast, collections
    from app.ui.api import Api

    tree = ast.parse((ROOT / "app/ui/api.py").read_text(encoding="utf-8"))
    for cls in [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "Api"]:
        seen = collections.defaultdict(list)
        for item in cls.body:
            if isinstance(item, ast.FunctionDef):
                seen[item.name].append(item.lineno)
        assert not {k: v for k, v in seen.items() if len(v) > 1}, f"Duplicate Api methods: {seen}"

    for m in (
        "games_hltb_real", "games_pcgamingwiki", "games_save_inspect", "games_save_write",
        "games_fix_ini", "games_snapshot_save", "games_tm_list", "games_tm_restore",
        "games_list_snapshots", "games_restore_snapshot",
        "games_mod_install", "games_mod_rollback", "games_launch_tool", "games_ocr_translate",
        "oracle_relay_ping", "oracle_relay_pull", "oracle_crash_snapshot", "oracle_crash_restore",
    ):
        assert hasattr(Api, m), f"Api.{m} eksik"

    for jm in ("games_hltb_real", "games_pcgamingwiki", "games_mod_install", "games_ocr_translate", "oracle_relay_ping", "oracle_relay_pull"):
        assert jm in Api.JOB_METHODS, f"JOB_METHODS icinde {jm} eksik"

    gh = (ROOT / "app/ui/web/games.html").read_text(encoding="utf-8")
    assert "openCompanionOverlay" in gh and "games_tm_list" in gh and "games_tm_restore" in gh

    sj = (ROOT / "app/ui/web/sunak.js").read_text(encoding="utf-8")
    assert "skOpenCmdPalette" in sj and "skModPeek" in sj

    ih = (ROOT / "app/ui/web/index.html").read_text(encoding="utf-8")
    ajs = (ROOT / "app/ui/web/app.js").read_text(encoding="utf-8")
    for bid in ("orRelayPing", "orRelayPull", "orCrashSnap", "orCrashRest"):
        assert bid in ih and bid in ajs
