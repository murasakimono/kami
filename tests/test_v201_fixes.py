"""Kami 2.0.1 canli hata duzeltmeleri & LCS LRC Hizalayici testleri."""
from __future__ import annotations

import json
import subprocess
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "app" / "ui" / "web"


def test_version_201():
    from app.core import extras

    assert extras.APP_VERSION == "2.0.2"


def test_notification_center_list_limit():
    from app.core.events import NotificationCenter

    nc = NotificationCenter(maxlen=20)
    for i in range(10):
        nc.push("info", f"Baslik {i}", f"Detay {i}")
    top4 = nc.list(limit=4)
    assert len(top4) == 4
    assert top4[0]["title"] == "Baslik 9"
    assert len(nc.list()) == 10


def test_lyrics_no_duplicate_headers_and_is_lrc(tmp_path: Path):
    from app.core import lyrics

    raw_elrc = (
        "[ar:Contra]\n"
        "[ti:Uyu Gelmedik Daha]\n"
        "[re:Kami AI]\n"
        "[00:06.62]<00:06.62>Beynim <00:07.66>yorulur\n"
    )
    assert lyrics.is_lrc(raw_elrc) is True

    mp3 = tmp_path / "Contra - Uyu Gelmedik Daha.mp3"
    mp3.write_bytes(b"fake")
    out = lyrics.write_lyrics(str(mp3), raw_elrc, "Contra", "Uyu Gelmedik Daha.mp3", embed=False, ai=False)
    assert out["lyrics"] == "synced"
    saved = Path(out["lrc"]).read_text(encoding="utf-8")
    assert saved.count("[ar:") == 1
    assert saved.count("[ti:") == 1
    assert ".mp3]" not in saved

    # Ilk kayit basliksizsa .mp3 uzantisini temizleyip tek baslik yazmali
    plain_lrc = "[00:06.62]Ilk satir\n[00:10.00]Ikinci satir\n"
    mp3_b = tmp_path / "TrackTwo.mp3"
    mp3_b.write_bytes(b"fake")
    out_b = lyrics.write_lyrics(str(mp3_b), plain_lrc, "Sanatci", "Sanatci - Parca.mp3", embed=False, ai=False)
    saved_b = Path(out_b["lrc"]).read_text(encoding="utf-8")
    assert "[ti:Parca]" in saved_b
    assert ".mp3" not in saved_b


def test_ui_fixes_201():
    sunak_js = (WEB / "sunak.js").read_text(encoding="utf-8")
    assert 'querySelector(":scope > span")' in sunak_js

    sunak_css = (WEB / "sunak.css").read_text(encoding="utf-8")
    assert "#sunak .sk-g > span" in sunak_css

    games_html = (WEB / "games.html").read_text(encoding="utf-8")
    assert "toggleMode" in games_html
    assert "cov-ov" not in games_html

    rd_plus = (WEB / "reader-plus.js").read_text(encoding="utf-8")
    assert "#rdToolsBtn" in rd_plus

    ed_css = (WEB / "editor.css").read_text(encoding="utf-8")
    ed_js = (WEB / "editor.js").read_text(encoding="utf-8")
    assert "320px" in ed_css and ".ed-rail" in ed_css
    assert "R = 118" in ed_js and "edRail" in ed_js

    km_css = (WEB / "kami-motion.css").read_text(encoding="utf-8")
    km_js = (WEB / "kami-motion.js").read_text(encoding="utf-8")
    assert "white-space: pre;" in km_css
    assert "#kpal .kp-l > .kp-rows" in km_css
    assert "width: 14px !important;" in km_css
    assert "#skAltar.drop" not in km_css
    assert "getBoundingClientRect()" in km_js
    assert '"#skAltar,' not in km_js

    pl_css = (WEB / "player.css").read_text(encoding="utf-8")
    assert ".px-row > i" in pl_css
    assert ".px-row > span:not(.km-eq)" in pl_css

    gpu_js = (WEB / "sunak-gpu.js").read_text(encoding="utf-8")
    assert "this.state.drop || this.swallowT > 0" in gpu_js

    k20_js = (WEB / "kami-20.js").read_text(encoding="utf-8")
    assert "window.KamiLrcAlign" in k20_js
    assert "k20LqAlignRun" in k20_js

    pm_js = (WEB / "player-music.js").read_text(encoding="utf-8")
    assert "window.plReloadLyrics" in pm_js
    assert "pmReload" in pm_js
    assert "PM.rawSynced" in pm_js

    kf_js = (WEB / "kamify-v138.js").read_text(encoding="utf-8")
    assert "music_lrc_job_status" in kf_js
    assert "kfAlignReal" in kf_js

    api_py = (ROOT / "app" / "ui" / "api.py").read_text(encoding="utf-8")
    assert "_notify_player_lyrics" in api_py


def test_lrc_align_algorithm_in_node():
    node_code = r"""
const fs = require('fs');
const vm = require('vm');
const noop = () => {};
const el = () => ({ style: { setProperty: noop, removeProperty: noop }, dataset: {}, classList: { add: noop, remove: noop, toggle: noop }, querySelector: el, querySelectorAll: () => [], addEventListener: noop, append: noop, appendChild: noop, setAttribute: noop, getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 30 }) });
const sandbox = {
  window: { addEventListener: noop, pywebview: null },
  document: {
    title: 'Kami', head: { appendChild: noop }, body: { appendChild: noop, append: noop, addEventListener: noop },
    createElement: () => el(), addEventListener: noop, querySelector: () => null, querySelectorAll: () => [],
  },
  location: { pathname: '/index.html' },
  navigator: {},
  setInterval: noop, setTimeout: noop, clearInterval: noop, clearTimeout: noop,
  console, Math, Date, Number, String, Array, Set, Map, Uint16Array,
};
sandbox.window.window = sandbox.window;
vm.runInNewContext(fs.readFileSync('app/ui/web/kami-20.js', 'utf8'), sandbox);
const raw = [
  '[ar:Contra]',
  '[ti:Test]',
  '[00:06.62]<00:06.62>Beynim <00:07.66>sikisiyo <00:08.14>gece <00:08.36>dortten <00:08.88>beri',
  '[00:09.14]<00:09.14>Sanki <00:09.58>kizli <00:09.94>erkekli <00:10.58>evi'
].join('\n');
const real = "Beynim sikişiyor gece 4'ten beri\nSanki kızlı erkekli öğrenci evi";
const out = sandbox.window.KamiLrcAlign(raw, real);
console.log(JSON.stringify(out));
"""
    proc = subprocess.run(
        ["node", "-e", node_code],
        cwd=str(ROOT),
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
    )
    out = json.loads(proc.stdout.strip())
    lines = out.splitlines()
    assert lines[0] == "[ar:Contra]"
    assert lines[1] == "[ti:Test]"
    assert lines[2].startswith("[00:06.62]<00:06.62>Beynim")
    assert "<00:08.14>gece" in lines[2]
    assert "<00:10.58>evi" in lines[3]
    assert "öğrenci" in lines[3]
