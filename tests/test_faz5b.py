"""Faz 5b: RAW acma (rawpy) ve Picture yardimcilari."""
from types import SimpleNamespace


def _api():
    from app.ui.api import Api
    return Api, SimpleNamespace(IMAGE_EXT=Api.IMAGE_EXT, RAW_EXT=Api.RAW_EXT, _open_raw=Api._open_raw)


def test_raw_extensions_recognised():
    Api, _ = _api()
    for ext in (".cr3", ".nef", ".arw", ".raf", ".dng"):
        assert ext in Api.RAW_EXT and ext in Api.IMAGE_EXT


def test_broken_raw_fails_gracefully(tmp_path):
    Api, fake = _api()
    p = tmp_path / "bozuk.dng"
    p.write_bytes(b"not a raw file" * 10)
    r = Api.image_data(fake, str(p))
    assert r["ok"] is False and r["error"]


def test_rawpy_importable():
    import rawpy  # noqa: F401  (pyproject bagimliligi; paketli surumde de olmali)
