"""v2.5.5: Player kutuphane kucuk resimleri, pencere boyu sigdirma, Picture/Studio/Bildirim arac cubugu duzeltmeleri."""
from pathlib import Path

from app import main as kmain

WEB = Path(__file__).resolve().parents[1] / "app" / "ui" / "web"


def test_fit_win_never_grows_and_returns_ints():
    w, h = kmain._fit_win(1320, 860)
    assert isinstance(w, int) and isinstance(h, int)
    assert 0 < w <= 1320 and 0 < h <= 860


def test_library_thumbs_only_existing_media(tmp_path):
    from app.ui.api import Api

    class _Media:
        def asset_url(self, p, route="f"):
            return f"http://x/{route}/{Path(p).name}"

    api = Api.__new__(Api)
    api._media = _Media()
    vid = tmp_path / "a.mkv"
    vid.write_bytes(b"x")
    txt = tmp_path / "b.txt"
    txt.write_bytes(b"x")
    r = api.library_thumbs([str(vid), str(txt), str(tmp_path / "yok.mp4")])
    assert r["ok"] and list(r["thumbs"]) == [str(vid)]
    assert r["thumbs"][str(vid)].endswith("/t/a.mkv")


def test_media_server_has_thumb_route():
    src = (Path(kmain.__file__).parent / "core" / "media_server.py").read_text(encoding="utf-8")
    assert 'route == "t"' in src and "thumb=True" in src and "thumbnail=40" in src


def test_ui_wiring():
    assert "picture-fit.js" in (WEB / "picture.html").read_text(encoding="utf-8")
    assert 'class="tl-zoom"' in (WEB / "studio.html").read_text(encoding="utf-8")
    assert "library_thumbs" in (WEB / "player-extra.js").read_text(encoding="utf-8")
    assert "placeNotif" in (WEB / "sunak.js").read_text(encoding="utf-8")
