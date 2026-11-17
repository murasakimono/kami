"""Coklu kuyruk (v1.29, IDM 'kuyruklar' mantigi).

- Ana kuyruk ("main") = eski davranis: aria2'nin genel esZamanli siniri gecerli, burada hic dokunulmaz.
- Adli kuyruklar (data/queues.json): her birinin kendi esZamanli siniri, kendi hiz siniri (KiB/s, kuyruktaki
  aktif islere bolunur), istege bagli saat penceresi (gun secimiyle) ve elle Baslat/Durdur'u vardir.
- Uyelik Download.extra["queue"]; kuyruk tutmasi extra["qhold"]=True (kullanici duraklatmasindan ayri:
  kullanicinin elle duraklattigina zamanlayici dokunmaz).
- Kuyruk bitince istege bagli eylem: "" | "notify" | "shutdown" (shutdown Kami'nin mevcut kapatma akisini cagirir).
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import re
import threading
import uuid
from typing import Any, Callable

from app import paths
from app.core.models import Status

log = logging.getLogger(__name__)
MAIN = "main"
_HM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


def _file():
    return paths.DATA_DIR / "queues.json"


def _clean(q: dict[str, Any]) -> dict[str, Any]:
    days = sorted({int(x) for x in (q.get("days") or []) if str(x).isdigit() and 0 <= int(x) <= 6})
    out = {"id": str(q.get("id") or uuid.uuid4().hex[:8])[:16], "name": str(q.get("name") or "Kuyruk")[:40],
           "max_active": max(1, min(16, int(q.get("max_active") or 1))),
           "limit_kib": max(0, int(q.get("limit_kib") or 0)),
           "start": str(q.get("start") or ""), "stop": str(q.get("stop") or ""), "days": days,
           "running": bool(q.get("running")), "on_done": str(q.get("on_done") or "") if q.get("on_done") in ("notify", "shutdown") else ""}
    if not (_HM.match(out["start"]) and _HM.match(out["stop"])):
        out["start"] = out["stop"] = ""
    return out


def load() -> list[dict[str, Any]]:
    try:
        return [_clean(q) for q in json.loads(_file().read_text("utf-8")) if isinstance(q, dict)][:20]
    except (OSError, ValueError):
        return []


def save(qs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    out, seen = [], set()
    for q in qs[:20]:
        c = _clean(q)
        if c["id"] == MAIN or c["id"] in seen:
            c["id"] = uuid.uuid4().hex[:8]
        seen.add(c["id"])
        out.append(c)
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(_file())
    return out


def _hm(s: str) -> int:
    h, m = s.split(":")
    return int(h) * 60 + int(m)


def in_schedule(q: dict[str, Any], now: dt.datetime) -> bool | None:
    """Saat penceresi tanimliysa icinde mi (gece yarisini asabilir); tanimsizsa None."""
    if not q.get("start"):
        return None
    a, b, cur = _hm(q["start"]), _hm(q["stop"]), now.hour * 60 + now.minute
    inside = True if a == b else (a <= cur < b if a < b else (cur >= a or cur < b))
    if inside and q.get("days"):
        # gece yarisini asan pencerede sabahki kisim onceki gune aittir
        day = (now - dt.timedelta(days=1)).weekday() if a > b and cur < b else now.weekday()
        inside = day in q["days"]
    return inside


class QueueRunner:
    """2 sn'de bir adli kuyruklari yonetir. manager: DownloadManager; on_done(q) kuyruk bittiginde."""

    def __init__(self, manager, on_done: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.m = manager
        self.on_done = on_done
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self._sched_prev: dict[str, bool] = {}
        self._had_work: dict[str, bool] = {}
        self._limits: dict[int, int] = {}

    # ---- uyelik
    def _set_extra(self, did: int, **kw: Any) -> None:
        d = self.m.store.get(did)
        if not d:
            return
        ex = {**(d.extra or {}), **kw}
        for k, v in list(kw.items()):
            if v is None:
                ex.pop(k, None)
        nd = self.m.store.update(did, extra=ex)
        self.m.events.emit("download.updated", download=nd)

    def assign(self, ids: list[int], qid: str) -> int:
        qs = {q["id"]: q for q in load()}
        if qid != MAIN and qid not in qs:
            return 0
        n = 0
        for did in ids:
            d = self.m.store.get(int(did))
            if not d or d.status.is_finished:
                continue
            if qid == MAIN:
                was_held = (d.extra or {}).get("qhold")
                self._set_extra(d.id, queue=None, qhold=None)
                if was_held and d.status == Status.PAUSED:
                    self.m.resume(d.id)
                self._clear_limit(d)
            else:
                self._set_extra(d.id, queue=qid)
                if d.status in (Status.ACTIVE, Status.WAITING, Status.QUEUED) and not qs[qid]["running"]:
                    self.m.pause(d.id)
                    self._set_extra(d.id, qhold=True)
                elif d.status == Status.PAUSED:
                    self._set_extra(d.id, qhold=True)
            n += 1
        self.tick()
        return n

    def set_running(self, qid: str, on: bool) -> bool:
        qs = load()
        for q in qs:
            if q["id"] == qid:
                q["running"] = bool(on)
                save(qs)
                self.tick()
                return True
        return False

    def members(self, qid: str) -> list:
        return [d for d in self.m.store.list() if (d.extra or {}).get("queue") == qid]

    def summary(self) -> list[dict[str, Any]]:
        out = []
        for q in load():
            ms = self.members(q["id"])
            out.append({**q, "total": len(ms), "active": sum(d.status in (Status.ACTIVE, Status.WAITING) for d in ms),
                        "done": sum(d.status == Status.COMPLETE for d in ms),
                        "waiting": sum(d.status == Status.PAUSED and (d.extra or {}).get("qhold") for d in ms)})
        return out

    # ---- hiz siniri (aria2 is basina)
    def _clear_limit(self, d) -> None:
        if self._limits.pop(d.id, None) and d.gid and d.kind != "media":
            try:
                self.m.engine.call("aria2.changeOption", d.gid, {"max-download-limit": "0"})
            except Exception:
                pass

    def _apply_limit(self, d, kib: int) -> None:
        if d.kind == "media" or not d.gid or self._limits.get(d.id) == kib:
            return
        try:
            self.m.engine.call("aria2.changeOption", d.gid, {"max-download-limit": f"{kib}K" if kib else "0"})
            self._limits[d.id] = kib
        except Exception:
            log.debug("kuyruk hiz siniri uygulanamadi #%s", d.id)

    # ---- dongu
    def tick(self, now: dt.datetime | None = None) -> None:
        with self._lock:
            self._tick(now or dt.datetime.now())

    def _tick(self, now: dt.datetime) -> None:
        qs = load()
        changed = False
        for q in qs:
            sch = in_schedule(q, now)
            if sch is not None:
                prev = self._sched_prev.get(q["id"])
                self._sched_prev[q["id"]] = sch
                if prev is not None and prev != sch:   # yalniz gecislerde: elle baslat/durdur gecerli kalir
                    q["running"] = sch
                    changed = True
                    log.info("Kuyruk %s zamanlayici: %s", q["name"], "basla" if sch else "dur")
            ms = self.members(q["id"])
            live = [d for d in ms if d.status in (Status.ACTIVE, Status.WAITING, Status.QUEUED)]
            held = sorted((d for d in ms if d.status == Status.PAUSED and (d.extra or {}).get("qhold")),
                          key=lambda d: (-(d.position or 0), d.id))
            if not q["running"]:
                for d in live:
                    self.m.pause(d.id)
                    self._set_extra(d.id, qhold=True)
                self._had_work[q["id"]] = False
                continue
            # fazla calisani tut (sinir dusurulduyse), eksikse siradakini baslat
            for d in sorted(live, key=lambda d: (d.position or 0, -d.id))[: max(0, len(live) - q["max_active"])]:
                self.m.pause(d.id)
                self._set_extra(d.id, qhold=True)
                live.remove(d)
            for d in held[: max(0, q["max_active"] - len(live))]:
                self._set_extra(d.id, qhold=None)
                self.m.resume(d.id)
                live.append(d)
            if q["limit_kib"] and live:
                per = max(1, q["limit_kib"] // len(live))
                for d in live:
                    cur = self.m.store.get(d.id)
                    if cur:
                        self._apply_limit(cur, per)
            elif not q["limit_kib"]:
                for d in live:
                    if d.id in self._limits:
                        self._clear_limit(d)
            work = bool(live or held)
            if self._had_work.get(q["id"]) and not work:
                q["running"] = False   # bitti: kuyruk kendini durdurur
                changed = True
                log.info("Kuyruk bitti: %s", q["name"])
                if q["on_done"] and self.on_done:
                    try:
                        self.on_done(q)
                    except Exception:
                        log.exception("Kuyruk bitis eylemi")
            self._had_work[q["id"]] = work
        if changed:
            save(qs)

    def start(self) -> None:
        def loop() -> None:
            while not self._stop.wait(2):
                try:
                    self.tick()
                except Exception:
                    log.exception("Kuyruk dongusu")
        threading.Thread(target=loop, name="kami-queues", daemon=True).start()

    def stop(self) -> None:
        self._stop.set()


def held(d) -> bool:
    """Genel 'hepsini surdur' kuyruk tutmasini delmesin."""
    return bool((d.extra or {}).get("qhold"))

