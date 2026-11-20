"""Kami Lattice (senkron çekirdeği) testleri."""
from __future__ import annotations

from app.core import lattice


def test_diff_detects_push_pull_conflict():
    local = {
        "only_local.txt": {"size": 1, "mtime": 100, "sha1": "a"},
        "both_newer_local.txt": {"size": 1, "mtime": 200, "sha1": "b"},
        "conflict.txt": {"size": 1, "mtime": 300, "sha1": "c"},
    }
    remote = {
        "only_remote.txt": {"size": 1, "mtime": 100, "sha1": "d"},
        "both_newer_local.txt": {"size": 1, "mtime": 100, "sha1": "e"},
        "conflict.txt": {"size": 1, "mtime": 300, "sha1": "f"},
    }
    d = lattice.diff(local, remote)
    assert set(d["to_push"]) == {"only_local.txt", "both_newer_local.txt"}
    assert set(d["to_pull"]) == {"only_remote.txt"}
    assert d["conflicts"] == ["conflict.txt"]


def test_sync_plan_resolves_newer():
    local = {"a.txt": {"size": 1, "mtime": 100, "sha1": "x"}}
    remote = {"a.txt": {"size": 1, "mtime": 200, "sha1": "y"}}
    plan = lattice.sync_plan(local, remote)
    assert plan["push"] == [] and plan["pull"] == ["a.txt"]


def test_sync_plan_conflict_prefers_local():
    local = {"a.txt": {"size": 1, "mtime": 300, "sha1": "x"}}
    remote = {"a.txt": {"size": 1, "mtime": 300, "sha1": "y"}}
    plan = lattice.sync_plan(local, remote, prefer="local")
    assert plan["push"] == ["a.txt"] and plan["pull"] == []


def test_scan_folder_manifest(tmp_path):
    d = tmp_path / "sub"
    d.mkdir()
    (d / "x.txt").write_text("hello")
    man = lattice.scan_folder(str(tmp_path))
    assert man["sub/x.txt"]["size"] == 5
    assert len(man["sub/x.txt"]["sha1"]) == 40


def test_scan_folder_missing_dir():
    assert lattice.scan_folder("/yok/olmayan/klasor") == {}
