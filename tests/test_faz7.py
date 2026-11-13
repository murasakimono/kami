"""Faz 7 testleri: Cross-Origin Isolation, VRAM Guard, Profiller, SmartCache/FBO ve Mini-Ada."""
from __future__ import annotations

import json
import urllib.request
from pathlib import Path
from unittest.mock import patch

import pytest

from app import paths
from app.core.profiles import ProfileStore
from app.core.settings import Settings
from app.core.vram_guard import preflight, snapshot
from app.core.web_isolation import UiIsolationServer


def test_ui_isolation_server_coop_coep_headers(tmp_path: Path) -> None:
    (tmp_path / "hello.js").write_text("console.log('kami');", encoding="utf-8")
    srv = UiIsolationServer(root=tmp_path, preferred_port=0)
    port = srv.start()
    try:
        assert port > 0
        with urllib.request.urlopen(srv.url("sab-probe.html"), timeout=5) as resp:
            assert resp.status == 200
            assert resp.headers.get("Cross-Origin-Opener-Policy") == "same-origin"
            assert resp.headers.get("Cross-Origin-Embedder-Policy") == "credentialless"
            assert resp.headers.get("Cross-Origin-Resource-Policy") == "cross-origin"
            body = resp.read().decode("utf-8")
            assert "crossOriginIsolated" in body

        with urllib.request.urlopen(srv.url("hello.js"), timeout=5) as resp:
            assert resp.status == 200
            assert "application/javascript" in (resp.headers.get("Content-Type") or "")
            assert resp.headers.get("Cross-Origin-Opener-Policy") == "same-origin"

        req = urllib.request.Request(f"http://127.0.0.1:{port}/../secret.txt")
        with pytest.raises(urllib.error.HTTPError) as exc:
            urllib.request.urlopen(req, timeout=5)
        assert exc.value.code in (400, 404)
    finally:
        srv.stop()


def test_vram_guard_snapshot_and_preflight() -> None:
    snap = snapshot()
    for key in ("gpu_available", "vram_total_mb", "vram_used_mb", "vram_free_mb", "ram_pct", "cpu_pct", "level"):
        assert key in snap

    low_gpu = {
        "gpu_available": True,
        "gpu_name": "NVIDIA GeForce RTX 4050 Laptop GPU",
        "vram_total_mb": 6144,
        "vram_used_mb": 5800,
        "vram_free_mb": 344,
        "vram_pct": 94.4,
        "gpu_util": 50,
        "enc_util": 10,
        "ram_total_mb": 16384,
        "ram_used_mb": 8192,
        "ram_pct": 50.0,
        "cpu_pct": 25.0,
        "level": "critical",
    }
    flushed = {"called": False}
    with patch("app.core.vram_guard.snapshot", return_value=low_gpu):
        res = preflight(required_mb=2048, flush_cb=lambda: flushed.__setitem__("called", True))
    assert flushed["called"] is True
    assert res["ok"] is False
    assert res["fallback"] == "cpu"
    assert res["reason"] == "vram_low"

    ok_gpu = {**low_gpu, "vram_free_mb": 4096, "vram_pct": 33.3, "level": "ok"}
    with patch("app.core.vram_guard.snapshot", return_value=ok_gpu):
        res_ok = preflight(required_mb=2048)
    assert res_ok["ok"] is True
    assert res_ok["fallback"] is None


def test_profile_store_isolation(tmp_path: Path) -> None:
    settings = Settings(path=tmp_path / "settings.json")
    store = ProfileStore(path=tmp_path / "profiles.json", settings=settings)

    assert store.active_id() == "kisisel"
    profs = store.list_profiles()
    assert {p["id"] for p in profs} >= {"kisisel", "icerik", "magaza"}

    switched = store.switch_profile("magaza")
    assert switched["id"] == "magaza"
    assert settings.get("active_profile") == "magaza"
    assert settings.get("accent_theme") == "altin"

    dl_dir = store.effective_download_dir(tmp_path / "Downloads")
    assert dl_dir == tmp_path / "Downloads" / "Mağaza-İş"

    custom = store.create_profile("Staj Tıp", accent_theme="buz")
    assert custom["id"] == "staj-tip"
    assert store.delete_profile("kisisel") is False
    assert store.delete_profile(custom["id"]) is True


def test_smart_cache_and_mini_island_assets() -> None:
    gl_js = (paths.WEB_DIR / "studio-gl.js").read_text(encoding="utf-8")
    fx_js = (paths.WEB_DIR / "studio-fx.js").read_text(encoding="utf-8")
    island_html = (paths.WEB_DIR / "mini-island.html").read_text(encoding="utf-8")
    assert "processToFbo" in gl_js
    assert "SmartCache" in fx_js
    assert "mini_island_state" in island_html
