from __future__ import annotations

from pathlib import Path
from PIL import Image, PngImagePlugin

from app.core import converter, ghost, hardsub, studio


def test_converter_has_nvenc_caches(monkeypatch):
    converter._NVENC_OK.clear()
    calls = []

    def fake_run(*a, **kw):
        calls.append(a[0])

        class R:
            returncode = 0

        return R()

    monkeypatch.setattr(converter.subprocess, "run", fake_run)
    assert converter.has_nvenc("ffmpeg-fake") is True
    assert converter.has_nvenc("ffmpeg-fake") is True
    assert len(calls) == 1


def test_ghost_image_strips_metadata_and_shields(tmp_path):
    src = tmp_path / "photo.png"
    im = Image.new("RGB", (64, 64), (120, 40, 200))
    meta = PngImagePlugin.PngInfo()
    meta.add_text("Software", "SecretCamera")
    im.save(src, pnginfo=meta)

    r1 = ghost.process(str(src), shield=False)
    assert r1["ok"] is True
    out1 = Path(r1["out"])
    assert out1.is_file()
    with Image.open(out1) as clean:
        assert "Software" not in clean.info

    r2 = ghost.process(str(src), shield=True)
    assert r2["ok"] is True
    out2 = Path(r2["out"])
    assert out2.is_file() and out2 != out1


def test_hardsub_merge_cues_and_timestamps():
    assert hardsub._fmt_ts(65.25) == "00:01:05,250"
    frames = [
        (0.0, ""),
        (1.0, "Hello world"),
        (2.0, "Hello world!"),
        (3.0, ""),
        (4.0, "Second line"),
    ]
    cues = hardsub._merge_cues(frames)
    assert len(cues) == 2
    assert cues[0][2] == "Hello world!"
    assert cues[1][2] == "Second line"


def test_hardsub_batch_translate_preserves_newlines(monkeypatch):
    seen = []

    class FakeResp:
        ok = True

        def __init__(self, q):
            self.q = q

        def json(self):
            return [[[f"TR:{ln}\n" if idx < len(self.q.splitlines()) - 1 else f"TR:{ln}", ln]
                     for idx, ln in enumerate(self.q.splitlines())]]

    def fake_get(url, timeout=10):
        from urllib.parse import parse_qs, unquote, urlparse
        q = unquote(parse_qs(urlparse(url).query)["q"][0])
        seen.append(q)
        return FakeResp(q)

    monkeypatch.setattr(hardsub.requests, "get", fake_get)
    res = hardsub.translate_batch(["Hello", "World", "Test"])
    assert res == ["TR:Hello", "TR:World", "TR:Test"]
    assert len(seen) == 1

