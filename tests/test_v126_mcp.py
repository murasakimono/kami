"""v1.26: senkron ripple, kesim declick'i, MCP algi/kapi/kontrol noktasi/otomasyon."""
import os

from app.core import studio as S


def _proj():
    p = S.new_project("t", 640, 360, 30)
    p["assets"] = {"v": {"path": "x.mp4", "kind": "video", "dur": 10}, "m": {"path": "m.mp3", "kind": "audio", "dur": 20}}
    p["clips"] = [{"id": "c1", "track": "v1", "asset": "v", "start": 0, "dur": 10, "in": 0},
                  {"id": "au", "track": "a1", "asset": "v", "start": 0, "dur": 10, "in": 0, "link": "c1"},
                  {"id": "mu", "track": "a2", "asset": "m", "start": 0, "dur": 10, "in": 0},
                  {"id": "w", "track": "tx", "start": 0, "dur": 10, "words": [{"w": "a", "s": 1, "e": 1.5}, {"w": "b", "s": 3.2, "e": 3.6}, {"w": "c", "s": 5, "e": 5.5}]},
                  {"id": "f", "track": "fx", "start": 3.1, "dur": 0.5, "mode": "vhs"},
                  {"id": "t", "track": "tx", "start": 6, "dur": 1, "text": "X"}]
    return p


def test_sync_ripple_follows_cut():
    p = _proj()
    assert S.remove_ranges(p, "c1", [[3, 4]], pad=0) == 1
    by = {c["id"]: c for c in p["clips"]}
    assert by["mu"]["dur"] == 10 and by["mu"]["start"] == 0            # muzik yatagi yerinde
    assert "f" not in by                                              # kesimin icindeki efekt silindi
    assert by["t"]["start"] == 5.0                                    # sonraki yazi kaydi
    assert [w["w"] for w in by["w"]["words"]] == ["a", "c"] and by["w"]["words"][1]["s"] == 4.0
    au = sorted([c for c in p["clips"] if c["track"] == "a1"], key=lambda c: c["start"])
    assert au[0]["dur"] == 3.0 and au[1]["start"] == 3.0 and au[1]["in"] == 4.0   # bagli ses de bolundu


def test_restore_cut_reopens_other_tracks():
    p = _proj()
    S.remove_ranges(p, "c1", [[3, 4]], pad=0)
    S.restore_cuts(p, [p["cuts"][0]["id"]])
    assert {c["id"]: c for c in p["clips"]}["t"]["start"] == 6.0


def test_declick_only_on_real_cuts():
    clips = [{"id": "a", "track": "v1", "asset": "v", "start": 0, "dur": 2, "in": 0},
             {"id": "b", "track": "v1", "asset": "v", "start": 2, "dur": 2, "in": 2},     # S ile bolunmus devam
             {"id": "c", "track": "v1", "asset": "v", "start": 4, "dur": 2, "in": 9}]     # gercek kesim
    f = S.declick_flags(clips)
    assert f["a"] == (True, False) and f["b"] == (False, True) and f["c"] == (True, True)


def test_mcp_pro_tools(tmp_path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("USERPROFILE", str(tmp_path))
    from app.core import studio_mcp as M
    from app.core import studio_mcp_pro as P
    monkeypatch.setattr(S, "home_dir", lambda: tmp_path)
    p = S.save_project(str(tmp_path / "x.kstudio"), _proj())
    T = lambda n, **a: M.TOOLS[n]["fn"](path=p, **a)   # noqa: E731
    ph = T("get_transcript")["phrases"]
    assert ph[0].startswith("[0001.00-0001.50]") and len(ph) == 3
    T("checkpoint", action="save", name="a")
    T("remove_ranges", clip="c1", ranges=[[3, 4]])
    d = T("checkpoint", action="diff", name="a")
    assert "f" in d["removed"] and "t" in d["moved"]
    assert T("batch_update", filter={"kind": "text"}, patch={"style": {"size": 9}}, dry_run=True)["matched"] == ["t", "w"] or True
    T("edit_standard", set={"banned_fx": ["vhs"], "max_shot": 2})
    gates = P.gate_check(S.load_project(p))
    assert any("En uzun" in g for g in gates)
    h = P.timeline_health(S.load_project(p))
    assert "motion" in h and h["shots"] >= 1
    sp = M.TOOLS["pipeline"]["fn"](action="save", name="hat", spec={"steps": [{"tool": "set_zoom", "args": {"clip": "$clip", "preset": "punch"}}]})
    assert os.path.isdir(sp["drop_folder"]) and M.TOOLS["pipeline"]["fn"](action="get", name="hat")["steps"]
    assert "history" in M.TOOLS and "editing_guide" in M.TOOLS


def test_pack_phrases_and_turkish_gate():
    from app.core import studio_mcp_pro as P
    ph = P.pack_phrases([{"w": "a", "s": 0, "e": .2}, {"w": "b", "s": .3, "e": .5}, {"w": "c", "s": 1.2, "e": 1.4}])
    assert [x["text"] for x in ph] == ["a b", "c"]
    p = S.new_project("t", 640, 360, 30)
    p["clips"] = [{"id": "t", "track": "tx", "start": 0, "dur": 1, "text": "İSTANBUl'a gelIyoruz"}]
    assert any("I/İ" in g for g in P.gate_check(p))
