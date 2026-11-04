"""Defter 24 Sorun A: yavas api cagrilari (IPv6 21 sn zaman asimi, ag bekleyen pano kontrolu)."""
from __future__ import annotations

import socket
import threading
import time

from app.core import net
from tests.test_stage6a import make_api, mgr  # noqa: F401  (fixture)


def test_prefer_ipv4_sorts_v4_first(monkeypatch):
    fake = [(socket.AF_INET6, 1, 6, "", ("::1", 443, 0, 0)), (socket.AF_INET, 1, 6, "", ("1.2.3.4", 443)),
            (socket.AF_INET6, 1, 6, "", ("::2", 443, 0, 0)), (socket.AF_INET, 1, 6, "", ("5.6.7.8", 443))]
    monkeypatch.setattr(net, "_orig_getaddrinfo", lambda *a, **k: list(fake))
    out = net._v4_first("x", 443)
    assert [r[4][0] for r in out] == ["1.2.3.4", "5.6.7.8", "::1", "::2"]


class SlowRd:
    """RD hoster listesi aga cikarsa 5 sn bekler: link_supported bunu ASLA beklememeli."""
    def __init__(self):
        from app.core.debrid import DebridService, TokenStore

        class Client:
            def domains(self_inner):
                time.sleep(5)
                return ["mega.nz"]
        self.svc = DebridService(TokenStore(__import__("pathlib").Path("nope")), None, client=Client())
        self.svc.has_token = lambda: True


def test_link_supported_never_waits_network(mgr):  # noqa: F811
    api = make_api(mgr)
    rd = SlowRd().svc
    mgr.debrid = rd
    mgr.settings.set("rd_mode", "ask")
    t0 = time.monotonic()
    assert api.link_supported("https://www.youtube.com/watch?v=tspGk8q11LA") is True
    api.link_supported("https://mega.nz/file/abc")   # liste henuz yok -> False olabilir ama beklemez
    assert time.monotonic() - t0 < 1.0
    # arka plan yenilemesi bitince onbellekten cevap verir
    deadline = time.monotonic() + 8
    while not rd._domains and time.monotonic() < deadline:
        time.sleep(0.05)
    t0 = time.monotonic()
    assert api.link_supported("https://mega.nz/file/abc") is True
    assert time.monotonic() - t0 < 0.1


def test_job_start_returns_immediately_and_result_once(mgr):  # noqa: F811
    api = make_api(mgr)
    gate = threading.Event()
    api.rd_status = lambda: (gate.wait(5), {"ok": True, "x": 1})[1]
    t0 = time.monotonic()
    j = api.job_start("rd_status", [])
    assert j["ok"] and time.monotonic() - t0 < 0.2
    assert api.job_result(j["job"]) == {"state": "running"}
    gate.set()
    for _ in range(100):
        r = api.job_result(j["job"])
        if r["state"] == "done":
            break
        time.sleep(0.02)
    assert r == {"state": "done", "result": {"ok": True, "x": 1}}
    assert api.job_result(j["job"]) == {"state": "lost"}
    assert api.job_start("remove", [1]) == {"ok": False, "error": "bad_job"}   # beyaz liste


def test_aria2_disable_ipv6_flag(tmp_path):
    from app.engines.aria2_engine import Aria2Engine
    e = Aria2Engine(tmp_path / "aria2c.exe", disable_ipv6=True)
    assert e.disable_ipv6 is True
