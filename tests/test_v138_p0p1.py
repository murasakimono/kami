"""v1.38.0 P0/P1 birim ve regresyon testleri (Dalga 1-4)."""
from __future__ import annotations

import io
import json
import sys
import time
from pathlib import Path

import pytest


def test_settings_v138_defaults_and_coercion(tmp_path: Path):
    from app.core.settings import Settings

    s = Settings(tmp_path / "settings.json")
    assert s.get("island_music_expand") is True
    assert s.get("reader_page_anim") == "curl3d"
    assert s.get("speed_profile") == "full"
    assert isinstance(s.get("speed_profiles"), dict)
    assert isinstance(s.get("pano_exclude_apps"), list)

    s.set("reader_page_anim", False)
    assert s.get("reader_page_anim") == "off"
    s.set("reader_page_anim", True)
    assert s.get("reader_page_anim") == "curl3d"
    s.set("island_music_expand", False)
    assert s.get("island_music_expand") is False


def test_notification_center_ring_and_read():
    from app.core.events import NotificationCenter

    nc = NotificationCenter(maxlen=5)
    for i in range(7):
        nc.push("info", f"Baslik {i}", f"Detay {i}", download_id=i)
    items = nc.list()
    assert len(items) == 5
    assert items[0]["title"] == "Baslik 6"
    assert nc.unread_count() == 5

    nc.mark_all_read()
    assert nc.unread_count() == 0
    nc.clear()
    assert nc.list() == []


def test_music_hub_cached_now_allow_paused(monkeypatch):
    from app.core import music_hub

    snap = {"playing": False, "title": "Gece", "artist": "X", "ts": time.time()}
    monkeypatch.setattr(music_hub, "_librespot_now", lambda: None)
    monkeypatch.setattr(music_hub, "_LAST_NOW", snap)
    assert music_hub.cached_now(allow_paused=False) is None
    res = music_hub.cached_now(allow_paused=True)
    assert res is not None and res["title"] == "Gece"


def test_lyrics_ttml_and_elrc_word_timings():
    from app.core import lyrics

    ttml = """<?xml version="1.0" encoding="utf-8"?>
    <tt xmlns="http://www.w3.org/ns/ttml"><body><div>
      <p begin="00:01.000" end="00:03.500">
        <span begin="00:01.000" end="00:01.800">Merhaba</span>
        <span begin="00:02.000" end="00:03.200">Dünya</span>
      </p>
    </div></body></tt>"""
    t_lines = lyrics.parse_ttml_words(ttml)
    assert len(t_lines) == 1
    assert t_lines[0]["text"] == "Merhaba Dünya"
    assert len(t_lines[0]["words"]) == 2
    assert t_lines[0]["words"][0] == {"t": 1.0, "end": 1.8, "w": "Merhaba"}

    elrc = "[00:10.00]<00:10.00>Bir <00:10.50>satır\n"
    e_lines = lyrics.parse_elrc_words(elrc)
    assert len(e_lines) == 1
    assert e_lines[0]["words"][0]["w"] == "Bir"
    assert e_lines[0]["words"][1]["w"] == "satır"


def test_room_coalesce_queue_and_stage_react():
    from app.core.room import Room

    r = Room("Ali")
    r.say("Sistem", "Ali   odaya   katıldı", kind="sys")
    assert "  " not in r.events[-1]["text"]

    # Join/leave 12 sn icinde spam olmamali
    r.touch("p1", "Zeynep")
    count_after_join = len([m for m in r.events if "Zeynep" in str(m.get("text", ""))])
    r.touch("p1", "Zeynep")
    assert len([m for m in r.events if "Zeynep" in str(m.get("text", ""))]) == count_after_join

    q1 = r.queue_add("Parça 1", "https://youtu.be/abc", "Ali", kind="yt")
    q2 = r.queue_add("Parça 2", "https://youtu.be/def", "Zeynep", kind="yt")
    assert len(q2["queue"]) == 2
    nxt = r.queue_next()
    assert nxt["next"]["title"] == "Parça 1"
    assert len(nxt["queue"]) == 1
    rem = r.queue_remove(q1["item"]["id"] if q1["item"]["id"] in [x["id"] for x in r.media_queue] else q2["item"]["id"])
    assert rem["ok"] is True


def test_studio_finish_chapters_and_silences(monkeypatch):
    from app.core import studio_finish

    meta = studio_finish.format_ffmetadata_chapters([{"t": 0, "title": "Giriş"}, {"t": 12.5, "title": "Nakarat=1"}], total_dur=30.0)
    assert meta.startswith(";FFMETADATA1")
    assert "START=0" in meta and "END=12500" in meta and "Nakarat\\=1" in meta

    monkeypatch.setattr(studio_finish, "_ff", lambda *a, **kw: "[silencedetect] silence_start: 1.25\n[silencedetect] silence_end: 3.00 | silence_duration: 1.75\nDuration: 00:00:10.00\n")
    sil = studio_finish.detect_silences("ffmpeg", "dummy.mp4")
    assert sil == [[1.25, 3.0]]


def test_player_plus_anki_connect_mine(monkeypatch):
    import urllib.request
    from app.core import player_plus

    calls = []

    class FakeResp:
        def __init__(self, payload):
            self._b = json.dumps(payload).encode("utf-8")

        def read(self):
            return self._b

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

    def fake_urlopen(req, timeout=2.5):
        body = json.loads(req.data.decode("utf-8"))
        calls.append(body["action"])
        return FakeResp({"result": 99123, "error": None})

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)
    res = player_plus.anki_connect_mine("kelime", "Örnek cümle", reading="ke-li-me", meaning="word", image_b64="data:image/png;base64,AAAA")
    assert res["ok"] is True and res["id"] == 99123
    assert calls == ["createDeck", "storeMediaFile", "addNote"]


def test_games_tool_filter_and_save_snapshots(tmp_path: Path, monkeypatch):
    from app import paths
    from app.core import games

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data")
    assert bool(games._TOOL_PATTERNS.search("Wallpaper Engine")) is True
    assert bool(games._TOOL_PATTERNS.search("Lossless Scaling")) is True
    assert bool(games._TOOL_PATTERNS.search("Elden Ring")) is False

    save_dir = tmp_path / "mygame_save"
    save_dir.mkdir()
    (save_dir / "slot1.sav").write_text("OLD_DATA", encoding="utf-8")

    snap = games.create_save_snapshot("elden_ring", "Elden Ring", str(save_dir))
    assert snap["ok"] is True and snap["files"] == 1
    snaps = games.list_save_snapshots("elden_ring")
    assert len(snaps) == 1

    (save_dir / "slot1.sav").write_text("NEW_CORRUPT", encoding="utf-8")
    restored = games.restore_save_snapshot("elden_ring", snap["id"], str(save_dir))
    assert restored["ok"] is True
    assert (save_dir / "slot1.sav").read_text(encoding="utf-8") == "OLD_DATA"
    assert restored["pre_backup"].startswith("pre_restore_")


def test_cleaner_drives_ext_largest_dups_similar_caches_preview(tmp_path: Path, monkeypatch):
    from PIL import Image
    from app import paths
    from app.core import cleaner

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "kami_data")
    scan_dir = tmp_path / "scan"
    scan_dir.mkdir()

    # Exact duplicate pair + distinct big file
    (scan_dir / "dup_a.bin").write_bytes(b"ABCD1234" * 800)
    (scan_dir / "dup_b.bin").write_bytes(b"ABCD1234" * 800)
    (scan_dir / "big.txt").write_bytes(b"Z" * 12000)

    # Visually similar gradient images vs orthogonal striped image for 64-bit dHash
    grad = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            grad.putpixel((x, y), (x * 4, (x * 2 + y * 2) % 256, 40))
    grad.save(scan_dir / "shot1.png")
    grad.resize((40, 40)).save(scan_dir / "shot1_small.png")

    orth = Image.new("RGB", (64, 64))
    for y in range(64):
        for x in range(64):
            val = 250 if (63 - x) * 4 > 120 else 10
            orth.putpixel((x, y), (val, 255 - x * 4, y * 4))
    orth.save(scan_dir / "other.png")

    dr = cleaner.drive_summary()
    assert dr["ok"] is True and len(dr["drives"]) >= 1

    ext_res = cleaner.by_ext(str(scan_dir))
    assert ext_res["ok"] is True and ext_res["total_files"] == 6

    lg = cleaner.largest_files(str(scan_dir), limit=3)
    assert lg["items"][0]["name"] == "big.txt"

    dups = cleaner.find_duplicates(str(scan_dir), min_size=1024)
    assert len(dups["groups"]) == 1
    assert {f["name"] for f in dups["groups"][0]["files"]} == {"dup_a.bin", "dup_b.bin"}

    sim = cleaner.find_similar_images(str(scan_dir), threshold=8)
    assert len(sim["groups"]) == 1
    assert {i["name"] for i in sim["groups"][0]["items"]} == {"shot1.png", "shot1_small.png"}

    caches = cleaner.scan_safe_caches()
    assert caches["ok"] is True
    for it in caches["items"]:
        assert cleaner._protected(it["path"]) is False

    p_img = cleaner.preview_file(str(scan_dir / "shot1.png"))
    assert p_img["ok"] is True and p_img["kind"] == "image" and p_img["url"].startswith("data:image/png;base64,")
    p_txt = cleaner.preview_file(str(scan_dir / "big.txt"))
    assert p_txt["ok"] is True and p_txt["kind"] == "text" and "ZZZZ" in p_txt["text"]


def test_pano_shelf_ocr_indexing(tmp_path: Path, monkeypatch):
    from PIL import Image
    from app.core import ocr, pano_tools

    img_p = tmp_path / "note.png"
    Image.new("RGB", (32, 32), (20, 40, 80)).save(img_p)
    monkeypatch.setattr(ocr, "read_text", lambda p, lang="": {"text": "Fatura #2026 Toplam 450 TL"})

    res = pano_tools.add_shelf_item("file", str(img_p), data_dir=tmp_path, async_ocr=False)
    assert res["ok"] is True
    assert res["item"]["ocr_text"] == "Fatura #2026 Toplam 450 TL"
    saved = pano_tools.list_shelf(data_dir=tmp_path)
    assert saved[0]["ocr_text"] == "Fatura #2026 Toplam 450 TL"


def test_doctor_turkish_diacritics():
    from app.core import doctor

    assert doctor.check_data_dir()["name"] == "Veri klasörü"
    eng_ok = doctor.check_engine(type("E", (), {"running": True})())
    assert eng_ok["name"] == "İndirme motoru (aria2)"
    assert eng_ok["detail"] == "Çalışıyor"
    assert doctor.check_module_windows(None)["name"] == "Modül pencereleri"


def test_api_picture_beautify_and_pin(tmp_path: Path):
    from PIL import Image
    from app.ui.api import Api

    img_p = tmp_path / "sample.png"
    Image.new("RGB", (320, 180), (140, 80, 220)).save(img_p)

    api = object.__new__(Api)
    d = api.picture_data_url(str(img_p))
    assert d["ok"] is True and d["url"].startswith("data:image/png;base64,")

    saved = api.picture_save_data_url(d["url"], str(img_p), "_beautify")
    assert saved["ok"] is True and Path(saved["path"]).is_file()

    pin = api.picture_pin(str(img_p))
    assert pin["ok"] is True and pin["w"] > pin["h"]
    info = api.pin_info(pin["pid"])
    assert info["ok"] is True and info["url"].startswith("data:image/png;base64,")
    assert api.pin_close(pin["pid"])["ok"] is True


def test_kami_20_icons_m3_s4_blue_o1_and_dust_janitor_lrc(tmp_path: Path, monkeypatch):
    from app import paths
    from app.core import cleaner, extras, games, icons, lyrics, settings

    assert extras.APP_VERSION == "2.0.2"

    # 1) Kami 2.0 Settings defaults
    s = settings.Settings(tmp_path / "settings20.json")
    assert s.get("rec_cursor_zoom") is True
    assert s.get("studio_safe_zone") is False
    assert s.get("media_dearrow") is False
    assert s.get("whisper_strong_song") is True
    assert s.get("scrobbler_hotkey") == "ctrl+shift+g"

    # 2) Kami 2.0 Icons (Main M3, Studio S4 all-blue, Oda O1)
    for k in ("main", "player", "studio", "picture", "reader", "games", "music", "cleaner", "room"):
        im = icons.render_icon_image(k, size=32)
        assert im.size == (32, 32)
    ico_out = icons.write_ico("studio", tmp_path / "studio.ico")
    assert ico_out.is_file() and ico_out.stat().st_size > 1000

    # 3) Editable LRC read/save for local MP3
    mp3_p = tmp_path / "underground_track.mp3"
    mp3_p.write_bytes(b"ID3" + b"\x00" * 128)
    saved_lrc = lyrics.save_edited_lrc(
        str(mp3_p),
        [{"t": 12.5, "text": "Birinci bar satırı"}, {"t": 16.25, "text": "İkinci bar satırı"}],
        artist="Saian",
        title="Yeraltı",
        embed=False,
    )
    assert saved_lrc["ok"] is True
    rd_lrc = lyrics.read_local_lrc(str(mp3_p))
    assert rd_lrc["ok"] is True and rd_lrc["synced"] is True
    assert len(rd_lrc["lines"]) == 2
    assert rd_lrc["lines"][0]["t"] == 12.5

    # 4) C12 Kami Dust & C9 Janitor dry-run
    dust = cleaner.scan_kami_dust(min_idle_days=3650, min_size_kb=999999)
    assert dust["ok"] is True and dust["feature"] == "Kami Dust"
    jan = cleaner.run_folder_janitor(download_dir=str(tmp_path), dry_run=True)
    assert jan["ok"] is True and jan["dry_run"] is True

    # 5) Games Shelf folder scanner
    gdir = tmp_path / "GamesRoot" / "Fellah Kombat"
    gdir.mkdir(parents=True)
    (gdir / "FellahKombat.exe").write_bytes(b"MZ" + b"\x00" * 4096)
    monkeypatch.setattr(paths, "DATA_DIR", tmp_path / "data20")
    shelf = games.scan_folder_for_games(str(tmp_path / "GamesRoot"), auto_add=False)
    assert shelf["ok"] is True and shelf["count"] == 1 and shelf["found"][0]["title"] == "Fellah Kombat"

