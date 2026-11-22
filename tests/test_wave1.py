"""Dalga 1 (v2.5+) regresyon testleri: RAM/Oyun Kalkani, hiz koruma, mini-player, kurulum ve arayuz birligi."""
from __future__ import annotations

import os
from pathlib import Path
from types import SimpleNamespace

from app.core import ram_guard
from app.core.settings import DEFAULTS, Settings

ROOT = Path(__file__).resolve().parent.parent


def test_wave1_settings_defaults_and_validation(tmp_path):
    assert DEFAULTS["prewarm_player"] is False
    assert DEFAULTS["ram_instant_unload"] is True
    assert DEFAULTS["game_shield_enabled"] is True
    assert DEFAULTS["game_shield_profiles"]["cs2.exe"] == "competitive"

    st = Settings(tmp_path / "settings.json")
    st.set("game_shield_profiles", {"  EldenRing.exe ": "STORY", "Bad.exe": "unknown", "Cs2.EXE": "off"})
    profs = st.get("game_shield_profiles")
    assert profs["eldenring.exe"] == "story"
    assert profs["bad.exe"] == "story"
    assert profs["cs2.exe"] == "off"


def test_evaluate_foreground_classifications():
    assert ram_guard.evaluate_foreground("Kami.exe") == ("", "")
    assert ram_guard.evaluate_foreground("explorer.exe") == ("", "")
    assert ram_guard.evaluate_foreground("cs2.exe") == ("cs2.exe", "competitive")
    assert ram_guard.evaluate_foreground("League of Legends.exe") == ("league of legends.exe", "competitive")
    assert ram_guard.evaluate_foreground("eldenring.exe", known_game_exes={"eldenring.exe"}) == ("eldenring.exe", "story")
    assert ram_guard.evaluate_foreground(
        "Game.exe",
        exe_full_path=r"D:\Games\Cyberpunk 2077\bin\x64\Game.exe",
        known_game_dirs=[r"d:\games\cyberpunk 2077" + os.sep],
    ) == ("game.exe", "story")
    assert ram_guard.evaluate_foreground("cs2.exe", profiles={"cs2.exe": "off"}) == ("", "")


def test_game_shield_lifecycle_and_active_work_protection(tmp_path):
    st = Settings(tmp_path / "settings.json")
    events: list[tuple] = []
    shield = ram_guard.GameShield(
        st,
        on_enter=lambda exe, prof: events.append(("enter", exe, prof)),
        on_leave=lambda: events.append(("leave",)),
    )
    assert shield.tick_once(fg_exe="cs2.exe") == ("cs2.exe", "competitive")
    assert shield.active is True
    assert events == [("enter", "cs2.exe", "competitive")]

    # Ayar kapatilinca kalkandan cikar
    st.set("game_shield_enabled", False)
    assert shield.tick_once(fg_exe="cs2.exe") == ("", "")
    assert shield.active is False
    assert events[-1] == ("leave",)

    # Aktif indirme / AI / ses korumasi
    dl_active = SimpleNamespace(status="active", extra={"ai_uvr": "running"})
    fake_api = SimpleNamespace(
        _thumb_playing=True,
        _manager=SimpleNamespace(snapshot=lambda: [dl_active]),
        _lrc_cancels={"1": object()},
        _ai=SimpleNamespace(_cancel=object()),
        _conv_jobs=[{"state": "running"}],
    )
    work = ram_guard.has_active_background_work(fake_api)
    assert work["downloads"] is True
    assert work["ai"] is True
    assert work["audio"] is True
    assert work["converter"] is True
    assert work["any_busy"] is True


def test_purge_idle_windows_respects_playing_music():
    class _FakeWin:
        def __init__(self) -> None:
            self.destroyed = False
            self._kami_allow_destroy = False

        def destroy(self) -> None:
            self.destroyed = True

    music_w = _FakeWin()
    studio_w = _FakeWin()
    fake_api = SimpleNamespace(
        _window=object(),
        _thumb_playing=True,
        _music_win=music_w,
        _studio_win=studio_w,
        _manager=SimpleNamespace(snapshot=lambda: []),
    )
    res = ram_guard.purge_idle_windows(fake_api, include_visible=True)
    assert res["ok"] is True
    assert music_w.destroyed is False
    assert "music" in res["skipped"]
    assert studio_w.destroyed is True
    assert fake_api._studio_win is None


def test_ram_stats_and_wave1_api_methods(tmp_path, monkeypatch):
    from app import paths
    from app.ui.api import Api

    monkeypatch.setattr(paths, "DATA_DIR", tmp_path)
    st = Settings(tmp_path / "settings.json")
    fake_self = SimpleNamespace(
        _manager=SimpleNamespace(settings=st, snapshot=lambda: []),
        _thumb_playing=False,
        _shield_state={"active": False, "exe": "", "profile": ""},
        _window=None,
    )
    rs = Api.ram_status(fake_self)
    assert rs["ok"] is True and rs["total_mb"] >= 0

    gs = Api.game_shield_set_profile(fake_self, "EldenRing.exe", "story")
    assert gs["ok"] is True and gs["profiles"]["eldenring.exe"] == "story"
    assert Api.game_shield_status(fake_self)["enabled"] is True

    # Picture draft roundtrip
    assert Api.picture_draft_save(fake_self, '{"meta":{"name":"test"}}')["ok"] is True
    loaded = Api.picture_draft_load(fake_self)
    assert loaded["ok"] is True and "test" in loaded["data"]
    assert Api.picture_draft_clear(fake_self)["ok"] is True
    assert Api.picture_draft_load(fake_self)["ok"] is False


def test_wave1_static_contracts():
    iss = (ROOT / "packaging" / "kami.iss").read_text(encoding="utf-8")
    assert "NextButtonClick(CurPageID: Integer)" in iss
    assert "wpReady" in iss
    assert "taskkill.exe" in iss and "/IM Kami.exe" in iss

    pjs = (ROOT / "app" / "ui" / "web" / "player.js").read_text(encoding="utf-8")
    assert "defaultPlaybackRate" in pjs and "plApplyRate" in pjs
    plib = (ROOT / "app" / "ui" / "web" / "player-lib.js").read_text(encoding="utf-8")
    assert "plApplyRate" in plib
    pmus = (ROOT / "app" / "ui" / "web" / "player-music.js").read_text(encoding="utf-8")
    assert "plMiniLabels" in pmus and "pmStem" in pmus

    enh = (ROOT / "app" / "ui" / "web" / "enhance.html").read_text(encoding="utf-8")
    mtag = (ROOT / "app" / "ui" / "web" / "music_tag.html").read_text(encoding="utf-8")
    for html in (enh, mtag):
        assert "--bg:#0D0A12" in html and "--ac:#9D6BFF" in html
        assert "#A3E635" not in html and "#2DD4BF" not in html

    main_src = (ROOT / "app" / "main.py").read_text(encoding="utf-8")
    assert "ram_instant_unload" in main_src and "GameShield" in main_src
    assert '"enhance": (163, 230, 53)' in main_src


def test_mini_player_labels_with_node():
    import json
    import shutil
    import subprocess

    node = shutil.which("node")
    if not node:
        return
    src = (ROOT / "app" / "ui" / "web" / "player-music.js").read_text(encoding="utf-8")
    harness = f"""
const vm = require('vm');
const ctx = {{
  window: {{ addEventListener: () => {{}} }},
  document: {{ addEventListener: () => {{}} }},
  $: () => null,
  PL: {{ info: {{}} }},
  PX: {{ cfg: {{}} }},
  plL: (tr, en) => tr,
  escapeHtml: (s) => String(s),
}};
vm.createContext(ctx);
vm.runInContext({json.dumps(src)} + '; this.__EXP = {{ PM, pmMeta, plMiniLabels }};', ctx);
const {{ PM, pmMeta, plMiniLabels }} = ctx.__EXP;

// 1) Synced LRC yok + normal ID3 etiketi
const r1 = {{ kind: 'audio', title: 'Ölü', path: 'C:/Music/Contra/Ölü.mp3', tags: {{ artist: 'Contra', title: 'Ölü' }} }};
PM.meta = pmMeta(r1);
PM.lines = [];
PM.idx = -1;
const l1 = plMiniLabels(r1);

// 2) Bozuk ID3 (title == artist) + dosya adindan cikarma + LRC yok
const r2 = {{ kind: 'audio', title: 'Contra', path: 'C:/Music/Contra - Tehlikeli [Official Audio].mp3', tags: {{ artist: 'Contra', title: 'Contra' }} }};
PM.meta = pmMeta(r2);
const l2 = plMiniLabels(r2);

// 3) Synced LRC aktif
PM.meta = pmMeta(r1);
PM.lines = [{{ t: 10, text: 'Tek gereken sizler gibi' }}];
PM.idx = 0;
const l3 = plMiniLabels(r1);

console.log(JSON.stringify({{ l1, l2, l3 }}));
"""
    res = subprocess.run([node, "-"], input=harness, capture_output=True, text=True, encoding="utf-8")
    assert res.returncode == 0, f"node failed: {res.stderr}"
    data = json.loads(res.stdout)
    assert data["l1"]["top"] == "Contra"
    assert data["l1"]["sub"] == "Ölü"
    assert data["l2"]["top"] == "Contra"
    assert data["l2"]["sub"] == "Tehlikeli"
    assert data["l3"]["top"] == "Contra — Ölü"
    assert data["l3"]["sub"] == "Tek gereken sizler gibi"

