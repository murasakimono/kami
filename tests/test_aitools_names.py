"""Ozel karakterli dosya adlari: alt surec argumanlari + diskten rozet durumu."""
import json
import sys
import threading

from app import paths
from app.core import aitools

NAME = "ERAY067 & MANSUR - SOFİ.mp4"


def test_args_roundtrip_with_special_chars(tmp_path, monkeypatch):
    (tmp_path / "echo_args.py").write_text(
        "import json, sys\n"
        "a = json.load(open(sys.argv[1][1:], encoding='utf-8'))\n"
        "sys.stdout.write(json.dumps({'done': a}, ensure_ascii=False) + chr(10))\n", encoding="utf-8")
    monkeypatch.setattr(paths, "TOOLSRC_DIR", tmp_path)
    monkeypatch.setattr(aitools, "python_exe", lambda n="": sys.executable)
    src = str(tmp_path / NAME)
    res = aitools._run_once(["echo_args", src, src[:-4] + ".tr.srt", "tr"], lambda m: None, threading.Event(), "x", {})
    assert res["done"] == [src, src[:-4] + ".tr.srt", "tr"]


def test_no_output_reports_exit_and_last_line(tmp_path, monkeypatch):
    (tmp_path / "boom.py").write_text("import sys\nprint('Caused by: x')\nsys.exit(3)\n", encoding="utf-8")
    monkeypatch.setattr(paths, "TOOLSRC_DIR", tmp_path)
    monkeypatch.setattr(aitools, "python_exe", lambda n="": sys.executable)
    res = aitools._run_once(["boom"], lambda m: None, threading.Event(), "x", {})
    assert res["error"] == "no_output (cikis 3): Caused by: x"


def test_disk_state_from_files(tmp_path):
    vid = tmp_path / NAME
    vid.write_bytes(b"x")
    (tmp_path / "ERAY067 & MANSUR - SOFİ.tr.srt").write_text("1", encoding="utf-8")
    sep = tmp_path / "Ayrilmis"
    sep.mkdir()
    (sep / "ERAY067 & MANSUR - SOFİ (Vokal).mp3").write_bytes(b"x")
    aitools._DISK_CACHE.clear()
    ds = aitools.disk_state(str(vid))
    assert ds["ai_whisper_srt"].endswith(".tr.srt") and len(ds["ai_uvr_files"]) == 1
    x = aitools.merge_disk_state({"ai_whisper": "error", "ai_whisper_err": "x"}, str(vid))
    assert x["ai_whisper"] == "done" and x["ai_uvr"] == "done" and "ai_whisper_err" not in x


def test_disk_state_keeps_running_and_empty(tmp_path):
    vid = tmp_path / "a.mp4"
    vid.write_bytes(b"x")
    (tmp_path / "a.srt").write_text("1")
    aitools._DISK_CACHE.clear()
    assert aitools.merge_disk_state({"ai_whisper": "running"}, str(vid))["ai_whisper"] == "running"
    (tmp_path / "a.srt").unlink()
    aitools._DISK_CACHE.clear()
    assert aitools.merge_disk_state({}, str(vid)) == {}
