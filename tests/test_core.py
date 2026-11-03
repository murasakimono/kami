from __future__ import annotations

import json

from app.core.categories import category_for, filename_from_url, folder_for, sanitize_filename
from app.core.events import EventBus
from app.core.models import Status
from app.core.plugin_loader import load_plugins
from app.core.queue_store import DownloadStore
from app.core.settings import Settings


def test_categories():
    assert category_for("film.MKV") == "video"
    assert category_for("", "https://x.com/a/b/song.mp3?x=1") == "music"
    assert category_for("a.7z") == "archive"
    assert category_for("setup.exe") == "program"
    assert category_for("x.pdf") == "document"
    assert category_for("x.torrent") == "torrent"
    assert category_for("noext", mime="video/mp4") == "video"
    assert category_for("noext") == "other"
    assert filename_from_url("https://h/p/a%20b.zip") == "a b.zip"
    assert sanitize_filename('a<b>:c?.txt') == "a_b__c_.txt"
    assert sanitize_filename("CON.txt") == "_CON.txt"
    assert folder_for("D:\\İndir", "music").endswith("Müzik")
    assert folder_for("D:\\İndir", "other") == "D:\\İndir"
    assert folder_for("D:\\İndir", "music", False) == "D:\\İndir"


def test_events():
    bus = EventBus()
    got, star = [], []
    off = bus.on("x", lambda **kw: got.append(kw))
    bus.on("*", lambda event, **kw: star.append(event))
    bus.on("x", lambda **kw: 1 / 0)  # hata digerlerini durdurmamali
    bus.emit("x", a=1)
    off()
    bus.emit("x", a=2)
    assert got == [{"a": 1}]
    assert star == ["x", "x"]


def test_settings(tmp_path):
    p = tmp_path / "s.json"
    s = Settings(p)
    assert s.get("connections") == 16
    s.set("connections", 99)
    assert s.get("connections") == 16  # aria2 en fazla 16
    s.set("capture_exclude_hosts", "a.com, B.com\nc.com")
    assert Settings(p).get("capture_exclude_hosts") == ["a.com", "b.com", "c.com"]
    try:
        s.set("yok", 1)
        raise AssertionError
    except KeyError:
        pass


def test_store(tmp_path):
    st = DownloadStore(tmp_path / "k.db")
    d = st.add(url="http://a/b.zip", filename="b.zip", directory="C:\\x", category="archive",
               headers={"Cookie": "a=b"})
    assert d.status == Status.QUEUED and d.headers == {"Cookie": "a=b"}
    st.update(d.id, status=Status.ACTIVE, gid="abc")
    assert st.by_gid("abc").id == d.id
    assert [x.id for x in st.list([Status.ACTIVE])] == [d.id]
    assert "headers" not in st.get(d.id).to_public()
    st.delete(d.id)
    assert st.get(d.id) is None


def test_plugin_loader(tmp_path):
    good = tmp_path / "good"
    good.mkdir()
    (good / "helper.py").write_text("X = 'yardimci'\n", encoding="utf-8")
    (good / "plugin.json").write_text(json.dumps({"name": "Good", "version": "1.2"}), encoding="utf-8")
    (good / "plugin.py").write_text(
        "from app.core.plugin_api import Resolver\n"
        "from .helper import X\n"
        "class R(Resolver):\n"
        "    name='r'\n"
        "    def can_handle(self, req): return 'ornek' in req.url\n"
        "    def resolve(self, req): return [req]\n"
        "def register(ctx):\n"
        "    assert X == 'yardimci'\n"
        "    ctx.register_resolver(R())\n", encoding="utf-8")
    bad = tmp_path / "bad"
    bad.mkdir()
    (bad / "plugin.py").write_text("raise RuntimeError('bozuk')\n", encoding="utf-8")
    off = tmp_path / "off"
    off.mkdir()
    (off / "plugin.py").write_text("def register(ctx): raise SystemExit\n", encoding="utf-8")
    (off / "plugin.json").write_text('{"enabled": false}', encoding="utf-8")

    reg = load_plugins(tmp_path, EventBus(), Settings(tmp_path / "s.json"))
    info = {p.id: p for p in reg.plugins}
    assert info["good"].version == "1.2" and info["good"].resolvers == ["r"] and not info["good"].error
    assert "bozuk" in info["bad"].error
    assert info["off"].enabled is False
    assert len(reg.resolvers) == 1
