"""Faz 11 testleri: aria2 torrent onizleme, JSON LinkCrawler, DVR & Web Arsivi, dHash cift dosya & bit-rot."""
from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.core import library_health, link_crawler, web_archive
from app.core.models import Download
from app.engines.aria2_engine import Aria2Engine


def test_aria2_torrent_preview_and_file_allocation_preserved(tmp_path: Path):
    eng = Aria2Engine(exe=tmp_path / "aria2c.exe", dht_file=tmp_path / "dht.dat")
    dl = Download(
        id=1,
        url="magnet:?xt=urn:btih:0123456789abcdef0123456789abcdef01234567",
        filename="sample.mkv",
        directory=str(tmp_path),
        category="video",
        status="queued",
        kind="torrent",
        options={"select": "1", "stop_seeding": True},
    )
    opts = eng.build_torrent_options(dl)
    assert opts["bt-prioritize-piece"] == "head=20M"
    assert opts["bt-remove-unselected-file"] == "true"
    assert opts["seed-time"] == "0"

    src = Path(Aria2Engine.__module__.replace(".", "/") + ".py")
    raw = src.read_text(encoding="utf-8")
    assert '"--file-allocation=none"' in raw
    assert '"--bt-save-metadata=true"' in raw


def test_link_crawler_rules_ssrf_and_failover(tmp_path: Path):
    res_bad = link_crawler.crawl("http://127.0.0.1:8080/secret.mp4")
    assert res_bad["ok"] is False

    saved = link_crawler.save_rule({
        "name": "test-host",
        "pattern": r"example\.com/watch/",
        "extract_regex": [r'data-stream="(https://[^"]+)"'],
        "mirror_patterns": [r'data-mirror="(https://[^"]+)"'],
        "priority": 1,
    }, data_dir=tmp_path)
    assert saved["ok"] is True

    fake_html = (
        '<div data-stream="https://cdn1.example.com/v.mp4" '
        'data-mirror="https://cdn2.example.com/v.mp4"></div>'
    )
    out = link_crawler.crawl(
        "https://example.com/watch/123",
        data_dir=tmp_path,
        fetch_fn=lambda _u, _h: fake_html,
    )
    assert out["ok"] is True
    assert out["rule"] == "test-host"
    assert out["primary"] == "https://cdn1.example.com/v.mp4"
    assert out["mirrors"] == ["https://cdn2.example.com/v.mp4"]

    picked = link_crawler.pick_working_mirror(
        out["urls"],
        probe_fn=lambda u: u.endswith("cdn2.example.com/v.mp4"),
    )
    assert picked == "https://cdn2.example.com/v.mp4"

    deleted = link_crawler.delete_rule("test-host", data_dir=tmp_path)
    assert deleted["deleted"] is True


def test_web_archive_dvr_opts_and_html_inlining(tmp_path: Path):
    opts = web_archive.build_live_dvr_opts(tmp_path, from_start=True, embed_chapters=True)
    assert opts["live_from_start"] is True
    assert opts["postprocessors"][0]["add_chapters"] is True

    bad = web_archive.archive_webpage("http://192.168.1.1/admin", tmp_path / "x.html", prefer_cli=False)
    assert bad["ok"] is False


def test_library_health_dhash_duplicates_and_bitrot(tmp_path: Path):
    img1 = tmp_path / "a.png"
    img2 = tmp_path / "b_copy.png"
    img3 = tmp_path / "different.png"

    im = Image.new("RGB", (64, 64))
    for x in range(64):
        for y in range(64):
            im.putpixel((x, y), (x * 4, y * 4, (x + y) * 2))
    im.save(img1)
    im.resize((48, 48)).save(img2)

    im_diff = Image.new("RGB", (64, 64))
    for x in range(64):
        for y in range(64):
            im_diff.putpixel((x, y), (255 - x * 4, 255 - y * 4, 40))
    im_diff.save(img3)

    dups = library_health.find_duplicates(tmp_path, include_video=False)
    assert dups["ok"] is True
    assert len(dups["groups"]) == 1
    assert str(img2) in dups["groups"][0]["duplicates"] or str(img1) in dups["groups"][0]["duplicates"]

    manifest = tmp_path / ".kami_health.json"
    first = library_health.scan_health(tmp_path, manifest)
    assert first["ok"] is True
    assert len(first["new_files"]) == 3

    # Ayni mtime ile sessiz bozulma (bit-rot) simule et
    st = img3.stat()
    img3.write_bytes(b"corrupted-bytes-bitrot")
    import os
    os.utime(img3, ns=(st.st_atime_ns, st.st_mtime_ns))

    second = library_health.scan_health(tmp_path, manifest)
    assert second["ok"] is False
    assert len(second["corrupted_bitrot"]) == 1
    assert second["corrupted_bitrot"][0]["file"] == "different.png"
