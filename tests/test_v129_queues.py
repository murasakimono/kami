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
