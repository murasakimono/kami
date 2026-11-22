# Muzik etiket / kapak / isimlendirme (music_tag.py) birim testleri.
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.core import music_tag as mt


def test_parse_simple():
    assert mt.parse_name("Eypio - Yanlış") == {"artist": "Eypio", "feat": [], "title": "Yanlış"}


def test_parse_feat_after_artist():
    p = mt.parse_name("Eypio ft. Ahmet - Salak")
    assert p["artist"] == "Eypio"
    assert p["feat"] == ["Ahmet"]
    assert p["title"] == "Salak"


def test_parse_feat_multi_after_artist():
    p = mt.parse_name("Eypio ft. Ahmet, Emre - Napıyorsun Lan?")
    assert p["artist"] == "Eypio"
    assert p["feat"] == ["Ahmet", "Emre"]
    assert p["title"] == "Napıyorsun Lan?"


def test_parse_feat_in_parens():
    p = mt.parse_name("Eypio - Napıyorsun Lan? (ft. Ahmet, Emre)")
    assert p["artist"] == "Eypio"
    assert p["feat"] == ["Ahmet", "Emre"]
    assert p["title"] == "Napıyorsun Lan?"


def test_both_forms_parse_equal():
    a = mt.parse_name("Eypio ft. Ahmet, Emre - Napıyorsun Lan?")
    b = mt.parse_name("Eypio - Napıyorsun Lan? (ft. Ahmet, Emre)")
    assert a == b == {"artist": "Eypio", "feat": ["Ahmet", "Emre"], "title": "Napıyorsun Lan?"}


def test_format_feat_after():
    p = {"artist": "Eypio", "feat": ["Ahmet", "Emre"], "title": "Napıyorsun Lan?"}
    assert mt.format_name(p, "feat_after") == "Eypio ft. Ahmet, Emre - Napıyorsun Lan?"


def test_format_feat_parens():
    p = {"artist": "Eypio", "feat": ["Ahmet", "Emre"], "title": "Napıyorsun Lan?"}
    assert mt.format_name(p, "feat_parens") == "Eypio - Napıyorsun Lan? (ft. Ahmet, Emre)"


def test_format_no_feat():
    p = {"artist": "Eypio", "feat": [], "title": "Yanlış"}
    assert mt.format_name(p, "feat_after") == "Eypio - Yanlış"
    assert mt.format_name(p, "feat_parens") == "Eypio - Yanlış"


def test_real_contra_example():
    # "Contra ft. Orking - Uyu Gelmedik Daha" iki formu da dogru cozulmeli
    p = mt.parse_name("Contra ft. Orking - Uyu Gelmedik Daha")
    assert p["artist"] == "Contra"
    assert p["feat"] == ["Orking"]
    assert p["title"] == "Uyu Gelmedik Daha"


if __name__ == "__main__":
    import traceback
    fails = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                fails += 1
                print(f"FAIL {name}: {e}")
            except Exception:
                fails += 1
                print(f"ERROR {name}:")
                traceback.print_exc()
    print("=" * 40)
    print("OK" if fails == 0 else f"{fails} FAIL")
    sys.exit(1 if fails else 0)
