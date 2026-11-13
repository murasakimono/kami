"""Tek Isler Merkezi: uzun suren islemler icin ilerleme, iptal ve procjob.attach() yonetimi."""
from __future__ import annotations

import logging
import subprocess
import threading
import time
import uuid
from typing import Any, Callable

from app.core.procjob import attach

log = logging.getLogger("kami")
NOWIN = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class JobCtx:
    def __init__(self, job_id: str, mgr: "JobManager") -> None:
        self.id = job_id
        self._mgr = mgr
        self.cancelled = threading.Event()
        self._procs: list[subprocess.Popen] = []

    def set(self, pct: int | float, msg: str = "") -> None:
        self._mgr._update(self.id, pct=max(0, min(100, int(pct))), msg=msg)

    def run_proc(
        self,
        cmd: list[str],
        *,
        cwd: str | None = None,
        timeout: float | None = None,
        text: bool = True,
    ) -> subprocess.CompletedProcess:
        if self.cancelled.is_set():
            raise RuntimeError("İş kullanıcı tarafından iptal edildi")
        import tempfile
        f_out = tempfile.TemporaryFile(mode="w+b")
        f_err = tempfile.TemporaryFile(mode="w+b")
        try:
            p = attach(
                subprocess.Popen(
                    cmd,
                    cwd=cwd,
                    stdout=f_out,
                    stderr=f_err,
                    creationflags=NOWIN,
                )
            )
            self._procs.append(p)
            deadline = (time.monotonic() + timeout) if timeout else None
            while p.poll() is None:
                if self.cancelled.is_set():
                    try:
                        p.kill()
                    except Exception:
                        pass
                    raise RuntimeError("İş kullanıcı tarafından iptal edildi")
                if deadline and time.monotonic() > deadline:
                    try:
                        p.kill()
                    except Exception:
                        pass
                    raise TimeoutError("İşlem zaman aşımına uğradı")
                time.sleep(0.15)
            f_out.seek(0)
            f_err.seek(0)
            b_out, b_err = f_out.read(), f_err.read()
            if text:
                return subprocess.CompletedProcess(
                    cmd, p.returncode,
                    b_out.decode("utf-8", "replace"),
                    b_err.decode("utf-8", "replace"),
                )
            return subprocess.CompletedProcess(cmd, p.returncode, b_out, b_err)
        finally:
            f_out.close()
            f_err.close()

    def kill_procs(self) -> None:
        for p in list(self._procs):
            if p.poll() is None:
                try:
                    p.kill()
                except Exception:
                    pass


class JobManager:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._ctxs: dict[str, JobCtx] = {}
        self.on_done: Callable[[dict[str, Any]], None] | None = None

    def start(self, kind: str, title: str, fn: Callable[[JobCtx], Any]) -> str:
        jid = uuid.uuid4().hex[:10]
        ctx = JobCtx(jid, self)
        rec = {
            "id": jid,
            "kind": kind,
            "title": title,
            "status": "running",
            "pct": 0,
            "msg": "Başlatılıyor...",
            "result": None,
            "error": "",
            "started_at": time.time(),
            "ended_at": 0.0,
        }
        with self._lock:
            self._jobs[jid] = rec
            self._ctxs[jid] = ctx
            if len(self._jobs) > 40:
                oldest = sorted(self._jobs.values(), key=lambda x: x["started_at"])[:10]
                for o in oldest:
                    if o["status"] != "running":
                        self._jobs.pop(o["id"], None)
                        self._ctxs.pop(o["id"], None)

        def _worker() -> None:
            try:
                res = fn(ctx)
                if ctx.cancelled.is_set():
                    self._finish(jid, "cancelled", None, "İptal edildi")
                elif isinstance(res, dict) and res.get("ok") is False:
                    self._finish(jid, "error", res, str(res.get("error") or "Hata"))
                else:
                    self._finish(jid, "done", res, "")
            except Exception as exc:
                st = "cancelled" if ctx.cancelled.is_set() else "error"
                self._finish(jid, st, None, str(exc)[:220])

        threading.Thread(target=_worker, name=f"kami-job-{kind}", daemon=True).start()
        return jid

    def _update(self, jid: str, **kw: Any) -> None:
        with self._lock:
            if jid in self._jobs:
                self._jobs[jid].update(kw)

    def _finish(self, jid: str, status: str, result: Any, error: str) -> None:
        with self._lock:
            rec = self._jobs.get(jid)
            if not rec:
                return
            rec["status"] = status
            rec["pct"] = 100 if status == "done" else rec["pct"]
            rec["msg"] = "Tamamlandı ✓" if status == "done" else (error or status)
            rec["result"] = result
            rec["error"] = error
            rec["ended_at"] = time.time()
            snap = dict(rec)
        if self.on_done:
            try:
                self.on_done(snap)
            except Exception:
                log.debug("Job on_done hatasi", exc_info=True)

    def cancel(self, jid: str) -> bool:
        with self._lock:
            ctx = self._ctxs.get(jid)
            rec = self._jobs.get(jid)
            if not ctx or not rec or rec["status"] != "running":
                return False
            ctx.cancelled.set()
            rec["msg"] = "İptal ediliyor..."
        ctx.kill_procs()
        return True

    def get(self, jid: str) -> dict[str, Any] | None:
        with self._lock:
            r = self._jobs.get(jid)
            return dict(r) if r else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            items = sorted(self._jobs.values(), key=lambda x: x["started_at"], reverse=True)
            return [dict(x) for x in items[:15]]


jobs = JobManager()
