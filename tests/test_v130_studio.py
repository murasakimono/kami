"""v1.30 Studio: otomatik kisa klipler (pencere secimi + duzenlenebilir 9:16 projeler)."""
import shutil
import subprocess

import pytest


def test_score_windows_prefers_hooks_and_clean_ends():
    from app.core.studio_shorts import score_windows
    ph = []
    t = 0.0
    texts = ["ve sonra şey oldu", "bunu neden kimse söylemiyor?", "çünkü asıl hata burada.", "rakamlar 3 kat arttı.", "neyse devam.",
             "sıradan bir cümle", "başka bir cümle", "bir tane daha.", "ama bu da var", "son söz."] * 3
    for x in texts:
        ph.append({"s": t, "e": t + 6.0, "text": x, "n": len(x.split())})
        t += 6.5
    w = score_windows(ph, 20, 40, 2)
    assert len(w) == 2 and all(20 * 0.7 <= x["e"] - x["s"] <= 41 for x in w)
    assert any("neden" in x["hook"] for x in w)
    assert w[0]["e"] <= w[1]["s"]                                   # ortusme yok


def test_make_shorts_energy_mode_builds_projects(tmp_path, monkeypatch):
    ff = shutil.which("ffmpeg")
    if not ff:
        pytest.skip("ffmpeg yok")
    from app.core import studio as S
    monkeypatch.setattr(S, "home_dir", lambda: tmp_path)
    monkeypatch.setattr(S, "CACHE", tmp_path / "cache")
    (tmp_path / "cache").mkdir()
    (tmp_path / "Projeler").mkdir()
    src = tmp_path / "uzun.mp4"
    subprocess.run([ff, "-v", "error", "-f", "lavfi", "-i", "testsrc=size=640x360:rate=25", "-f", "lavfi",
                    "-i", "sine=frequency=440:sample_rate=48000", "-t", "90", "-c:v", "libx264", "-preset", "ultrafast", "-c:a", "aac",
                    "-shortest", str(src)], check=True)
    from app.core import studio_mcp as M
    r = M.TOOLS["make_shorts"]["fn"](file=str(src), count=2, min_sec=15, max_sec=25, captions=False)
    assert r["mode"] == "enerji" and len(r["shorts"]) == 2
    p, pr = M.load(r["shorts"][0]["project"])
    assert (pr["w"], pr["h"]) == (1080, 1920)
    v = [c for c in pr["clips"] if c.get("asset")]
    assert len(v) == 1 and v[0]["fit"] == "cover" and v[0]["in"] == r["shorts"][0]["start"] and 10 <= v[0]["dur"] <= 26
