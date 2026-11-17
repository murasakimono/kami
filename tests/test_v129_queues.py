"""v1.29 coklu kuyruk: sinir, durdur/baslat, saat penceresi, hiz siniri, bitince durma, genel surdurme tutmayi delmez."""
from __future__ import annotations

import datetime as dt

from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.models import DownloadRequest, Status
from app.core.plugin_api import Engine
from app.core.queue_store import DownloadStore
from app.core.settings import Settings


class Eng(Engine):
    name = "fake"
    connections = 16

    def __init__(self):
        self.n, self.calls, self.state = 0, [], {}

    def can_handle(self, request):
        return True

    def start(self, download):
        self.n += 1
        g = f"g{self.n}"
        self.state[g] = "active"
        return g

    def pause(self, gid): self.state[gid] = "paused"
    def resume(self, gid): self.state[gid] = "active"
    def remove(self, gid): self.state.pop(gid, None)

    def call(self, method, *a):
        self.calls.append((method, a))

    def status(self, gids):
        return {g: {"status": self.state.get(g, "missing"), "total": 100, "completed": 100 if self.state.get(g) == "complete" else 10,
                    "speed": 5, "connections": 1, "error_code": "0", "error": "", "path": ""} for g in gids}


def _setup(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.DATA_DIR", tmp_path)
    s = Settings(tmp_path / "s.json")
    s.set("download_dir", str(tmp_path / "dl"))
    eng = Eng()
    m = DownloadManager(DownloadStore(tmp_path / "k.db"), eng, EventBus(), s, prober=None)
    ids = [m.add(DownloadRequest(url=f"https://ornek.com/f{i}.bin", filename=f"f{i}.bin"), confirm=False)[0].id for i in range(4)]
    return m, eng, ids


def test_queue_limit_start_stop_finish(tmp_path, monkeypatch):
    from app.core import queues
    m, eng, ids = _setup(tmp_path, monkeypatch)
    qs = queues.save([{"name": "Gece", "max_active": 2, "limit_kib": 1000}])
    qid = qs[0]["id"]
    r = queues.QueueRunner(m)
    assert r.assign(ids[:3], qid) == 3
    st = {d.id: d for d in m.store.list()}
    assert all(st[i].status == Status.PAUSED and st[i].extra["qhold"] for i in ids[:3])
    assert st[ids[3]].status != Status.PAUSED                       # ana kuyruk etkilenmez
    assert r.set_running(qid, True)
    live = [d for d in m.store.list() if d.id in ids[:3] and d.status in (Status.ACTIVE, Status.WAITING)]
    assert len(live) == 2                                           # esZamanli sinir
    lim = [a for meth, a in eng.calls if meth == "aria2.changeOption"]
    assert lim and lim[-1][1]["max-download-limit"] == "500K"       # 1000 KiB / 2 aktif
    s = r.summary()[0]
    assert s["active"] == 2 and s["waiting"] == 1 and s["total"] == 3
    r.set_running(qid, False)
    assert all(m.store.get(i).status == Status.PAUSED for i in ids[:3])
    # genel "hepsini surdur" kuyruk bekleyenlerini baslatmaz
    from app.ui.api import Api
    fake = Api.__new__(Api)
    fake._manager = m
    Api.resume_all(fake)
    assert all(m.store.get(i).status == Status.PAUSED for i in ids[:3])
    # bitis: hepsi tamamlaninca kuyruk kendini durdurur ve bitis eylemi calisir
    done = []
    r.on_done = done.append
    queues.save([{**queues.load()[0], "on_done": "notify"}])
    r.set_running(qid, True)
    for _ in range(4):
        for d in m.store.list():
            if d.gid and eng.state.get(d.gid) == "active":
                eng.state[d.gid] = "complete"
        m.poll_once()
        r.tick()
    assert all(m.store.get(i).status == Status.COMPLETE for i in ids[:3])
    assert done and not queues.load()[0]["running"]


def test_queue_back_to_main_and_delete(tmp_path, monkeypatch):
    from app.core import queues
    m, eng, ids = _setup(tmp_path, monkeypatch)
    qid = queues.save([{"name": "A"}])[0]["id"]
    r = queues.QueueRunner(m)
    r.assign([ids[0]], qid)
    assert m.store.get(ids[0]).status == Status.PAUSED
    r.assign([ids[0]], queues.MAIN)
    d = m.store.get(ids[0])
    assert "queue" not in d.extra and "qhold" not in d.extra and d.status in (Status.ACTIVE, Status.WAITING)
    assert r.assign([ids[1]], "yok") == 0


def test_schedule_window_and_days():
    from app.core.queues import in_schedule
    q = {"start": "23:00", "stop": "07:00", "days": []}
    assert in_schedule(q, dt.datetime(2026, 11, 17, 23, 30)) and in_schedule(q, dt.datetime(2026, 11, 18, 6, 59))
    assert not in_schedule(q, dt.datetime(2026, 11, 18, 7, 0))
    q["days"] = [0]   # yalniz Pazartesi gecesi (17.11.2026 Sali)
    assert not in_schedule(q, dt.datetime(2026, 11, 17, 23, 30))
    assert in_schedule(q, dt.datetime(2026, 11, 17, 3, 0))          # Pazartesi gecesinin sabahi (Sali 03:00)
    assert in_schedule({"start": "", "stop": ""}, dt.datetime.now()) is None


def test_schedule_transition_runs_queue(tmp_path, monkeypatch):
    from app.core import queues
    m, eng, ids = _setup(tmp_path, monkeypatch)
    qid = queues.save([{"name": "S", "max_active": 1, "start": "02:00", "stop": "03:00"}])[0]["id"]
    r = queues.QueueRunner(m)
    r.assign(ids[:2], qid)
    r.tick(dt.datetime(2026, 11, 17, 1, 59))
    assert not queues.load()[0]["running"]
    r.tick(dt.datetime(2026, 11, 17, 2, 0))
    assert queues.load()[0]["running"]
    assert sum(m.store.get(i).status in (Status.ACTIVE, Status.WAITING) for i in ids[:2]) == 1
    r.tick(dt.datetime(2026, 11, 17, 3, 0))
    assert not queues.load()[0]["running"] and all(m.store.get(i).status == Status.PAUSED for i in ids[:2])


NYAA = b"""<?xml version="1.0" encoding="UTF-8"?><rss xmlns:nyaa="https://nyaa.si/xmlns/nyaa" version="2.0"><channel>
<title>Nyaa - Home - Torrent File RSS</title>
<item><title>[SubsPlease] Dandadan - 07 (1080p) [ABCD1234].mkv</title><link>https://nyaa.si/download/1.torrent</link>
<guid isPermaLink="true">https://nyaa.si/view/1</guid><nyaa:infoHash>aaaabbbbccccddddeeeeffff0000111122223333</nyaa:infoHash><nyaa:size>1.4 GiB</nyaa:size></item>
<item><title>[SubsPlease] Dandadan - 07 (720p) [EF01].mkv</title><link>https://nyaa.si/download/2.torrent</link>
<guid isPermaLink="true">https://nyaa.si/view/2</guid><nyaa:size>700.5 MiB</nyaa:size></item>
<item><title>[Other] Baska Dizi - 03 (1080p).mkv</title><link>https://nyaa.si/download/3.torrent</link><guid>https://nyaa.si/view/3</guid><nyaa:size>1.0 GiB</nyaa:size></item>
</channel></rss>"""

ATOM = b"""<?xml version="1.0"?><feed xmlns="http://www.w3.org/2005/Atom"><title>Podcast</title>
<entry><title>Bolum 12</title><id>tag:x,12</id><link rel="enclosure" href="https://cdn.ornek.com/b12.mp3"/></entry></feed>"""


def test_rss_parse_and_episode_key():
    from app.core import rss
    title, items = rss.parse_feed(NYAA)
    assert title.startswith("Nyaa") and len(items) == 3
    assert items[0]["dl"].startswith("magnet:?xt=urn:btih:aaaa") and items[0]["size"] == int(1.4 * (1 << 30))
    assert items[1]["dl"] == "https://nyaa.si/download/2.torrent"
    assert rss.episode_key(items[0]["title"]) == rss.episode_key(items[1]["title"]) == "dandadan|e007"
    assert rss.episode_key("The.Show.S02E05.1080p.WEB.x265") == "the show|s02e05"
    assert rss.episode_key("Belgesel 2024") == ""
    t2, a = rss.parse_feed(ATOM)
    assert t2 == "Podcast" and a[0]["dl"] == "https://cdn.ornek.com/b12.mp3"
    f = {"include": "1080p", "exclude": "Baska", "max_mb": 2000}
    assert [rss.matches(f, it) for it in items] == [True, False, False]
    assert rss.matches({"include": "/dandadan.*(720|1080)p/"}, items[1])


def test_rss_service_smart_episode_dedupe(tmp_path, monkeypatch):
    monkeypatch.setattr("app.paths.DATA_DIR", tmp_path)
    from app.core import rss
    feed = {"x": NYAA}
    got = []
    svc = rss.RssService(lambda u: feed["x"], lambda it, f: got.append(it["title"]) or True)
    r = svc.add_feed("https://nyaa.si/?page=rss", include="Dandadan")
    assert r["ok"] and r["items"] == 3 and got == []                 # geriye donuk indirme yok
    feed["x"] = NYAA.replace(b"view/1<", b"view/9<").replace(b"view/2<", b"view/8<").replace(b"- 07", b"- 08")
    assert svc.check(force=True) == 1                                  # 08'in yalniz ilk surumu (720p ve 1080p ayni bolum)
    assert len(got) == 1 and "- 08" in got[0]
    assert svc.check(force=True) == 0
    assert svc.public()[0]["seen_n"] >= 5 and "seen" not in svc.public()[0]
