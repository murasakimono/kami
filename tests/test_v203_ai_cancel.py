"""Kami 2.0.3: AI isi iptali (alt surec agaci), acilista takili ai_* temizligi, UVR ilerleme %95'te donmaz."""
from __future__ import annotations

import subprocess
import sys
import threading
import time
from types import SimpleNamespace


def test_cancel_kills_subprocess_tree(monkeypatch):
    from app.core import aitools

    code = ("import subprocess,sys,time;"
            "subprocess.Popen([sys.executable,'-c','import time;time.sleep(60)']);time.sleep(60)")
    monkeypatch.setattr(aitools, "python_exe", lambda tool: sys.executable)
    monkeypatch.setattr(aitools, "_diag_popen", lambda *a, **k: None)
    real = subprocess.Popen
    monkeypatch.setattr(aitools.subprocess, "Popen",
                        lambda cmd, **kw: real(cmd, **kw) if cmd[0] == "taskkill" else
                        real([sys.executable, "-c", code], **{k: v for k, v in kw.items() if k != "env"}))
    ev = threading.Event()
    threading.Timer(1.5, ev.set).start()
    t0 = time.time()
    res = aitools._run_once(["app.tools.x"], lambda m: None, ev, "uvr", {})
    assert res == {"error": "cancelled"}
    assert time.time() - t0 < 20


def test_reset_stale_ai():
    from app.core.aitools import reset_stale_ai

    rows = {1: {"ai_uvr": "running", "ai_uvr_p": 0.95, "title": "a"},
            2: {"ai_whisper": "done", "ai_whisper_p": 1},
            3: {"ai_lyrics": "queued", "ai_lyrics_p": 0, "ai_uvr": "done", "ai_uvr_files": ["x"]}}
    store = SimpleNamespace(list=lambda: [SimpleNamespace(id=i, extra=dict(x)) for i, x in rows.items()],
                            update=lambda i, extra: rows.__setitem__(i, extra))
    assert reset_stale_ai(store) == 2
    assert rows[1] == {"title": "a"}
    assert rows[2] == {"ai_whisper": "done", "ai_whisper_p": 1}
    assert rows[3] == {"ai_uvr": "done", "ai_uvr_files": ["x"]}


def test_queue_cancel_marks_cancelled():
    from app.core import aitools

    seen = {}
    q = aitools.AiQueue.__new__(aitools.AiQueue)
    q.set_extra = lambda did, **kw: seen.update(kw)
    q.get_path = lambda did: ""   # cancel() artık temizlik için yola bakar
    ev = threading.Event()
    q._cancel = {("uvr", 7): ev}
    q.cancel("uvr", 7)
    assert ev.is_set() and seen["ai_uvr"] == "cancelled"


def test_uvr_progress_never_stalls_at_95():
    import math
    est = 10.0
    p_at = lambda t: 0.3 + 0.67 * (1 - math.exp(-t / est))
    assert p_at(10 * est) <= 0.97 and p_at(3 * est) > p_at(2 * est) > 0.3
    assert p_at(2 * est) > 0.85   # eski tavan 0.95'e kadar dogrusal degil, yumusak yaklasir
    assert p_at(20 * est) > p_at(10 * est)


def test_cleanup_ai_partials(tmp_path):
    from app.core import aitools

    path = str(tmp_path / "song.mp3")
    uvr_dir = tmp_path / "Ayrilmis"
    uvr_dir.mkdir()
    (uvr_dir / "song (Vokal).mp3").write_text("yarim")
    (uvr_dir / "song (Enstrumantal).mp3").write_text("yarim")
    (uvr_dir / "other (Vokal).mp3").write_text("baska")   # farkli stem: dokunulmamali
    (tmp_path / "song.srt.part").write_text("yarim")

    aitools.cleanup_ai_partials(path, "uvr")
    assert not (uvr_dir / "song (Vokal).mp3").exists()
    assert not (uvr_dir / "song (Enstrumantal).mp3").exists()
    assert (uvr_dir / "other (Vokal).mp3").exists()

    aitools.cleanup_ai_partials(path, "whisper")
    assert not (tmp_path / "song.srt.part").exists()

    # desteklenmeyen kind / bos yol: hata yok, hicbir sey silinmez
    aitools.cleanup_ai_partials(path, "lyrics")
    aitools.cleanup_ai_partials("", "uvr")
