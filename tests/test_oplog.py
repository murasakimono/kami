"""Kami Echo: geri al günlüğü (OpLog) testleri."""
from __future__ import annotations

from app.core.oplog import OpLog


def test_record_list_undo_move(tmp_path):
    log = OpLog(str(tmp_path / "oplog.jsonl"))
    a = tmp_path / "a.txt"
    b = tmp_path / "sub" / "b.txt"
    a.write_text("icerik")
    b.parent.mkdir(parents=True, exist_ok=True)

    e = log.record("move", str(a), str(b))
    assert e["op"] == "move" and e["src"] == str(a)
    assert len(log.list()) == 1

    # gerçek taşımayı simüle et
    a.rename(b)

    res = log.undo(e["id"])
    assert res["ok"] is True
    assert a.is_file() and a.read_text() == "icerik"
    assert not b.exists()


def test_undo_not_found(tmp_path):
    log = OpLog(str(tmp_path / "oplog.jsonl"))
    assert log.undo("yok") == {"ok": False, "error": "not_found"}


def test_list_skips_corrupt_lines(tmp_path):
    log = OpLog(str(tmp_path / "oplog.jsonl"))
    log.record("move", "a", "b")
    with open(log.path, "a", encoding="utf-8") as f:
        f.write("{bozuk json\n")
    entries = log.list()
    assert len(entries) == 1 and entries[0]["op"] == "move"
