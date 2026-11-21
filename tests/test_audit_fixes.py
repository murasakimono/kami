"""Denetim (audit) bulgularinin regresyon testleri.

Her test, bulunan GERCEK bir hatayi kilitler:
  - Kapsul sayfasinda `<script>` icine kacissiz JSON (XSS)
  - Oda portalinda dosyanin tamamini RAM'e okuma + Range eksikligi
  - Var olmayan fonksiyon/metot cagrilari (winwin.show_front, RECORDER, cache_dir, projects_dir)
  - Arayuzdeki olu butonlar (JS adi != Api metodu)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


# ---------------------------------------------------------------- XSS

def test_kapsul_js_script_blogunu_kirmaz():
    """Dosya adinda '</script>' gecse bile <script> blogu kirilmamali (XSS)."""
    from app.core import kapsul

    kotu = "</script><img src=x onerror=alert(1)>"
    s = kapsul._js({"name": kotu, "n": "a&b"})

    assert "</script>" not in s
    assert "<" not in s and ">" not in s
    assert "&" not in s
    # kacis JSON'un anlamini bozmamali: geri okununca ayni deger
    geri = json.loads(s)
    assert geri["name"] == kotu
    assert geri["n"] == "a&b"


def test_kapsul_sayfasi_kacisli_gomuyor():
    """Sablon json.dumps'u dogrudan script icine koymamali."""
    src = (ROOT / "app/core/kapsul.py").read_text(encoding="utf-8")
    assert "const FILES = {_js(" in src
    assert "const FILES = {json.dumps(" not in src


# ---------------------------------------------------------------- room / portal

def test_room_portal_range_ve_parcali_akis():
    """Buyuk video RAM'e tamamen okunmamali; Range (206) desteklenmeli."""
    src = (ROOT / "app/core/room.py").read_text(encoding="utf-8")
    assert "Path(fpath).read_bytes()" not in src, "portal dosyasi hala tek seferde okunuyor"
    assert "Accept-Ranges" in src
    assert "Content-Range" in src
    assert "65536" in src, "64 KB parcali akis yok"


# ---------------------------------------------------------------- var olmayan semboller

def test_main_winwin_show_front_yok():
    """winwin'de show_front yok; find_window + bring_to_front kullanilmali."""
    from app.core import winwin
    assert not hasattr(winwin, "show_front")
    assert hasattr(winwin, "bring_to_front")
    src = (ROOT / "app/main.py").read_text(encoding="utf-8")
    assert "winwin.show_front" not in src


def test_recorder_aktif_ornek_koprusu():
    """games.py 'RECORDER' diye olmayan bir isim import etmemeli; kayit defteri kullanilmali."""
    from app.core import recorder
    assert hasattr(recorder, "set_active") and hasattr(recorder, "active")
    assert not hasattr(recorder, "RECORDER")

    eski = recorder.active()
    isaret = object()
    try:
        recorder.set_active(isaret)          # type: ignore[arg-type]
        assert recorder.active() is isaret
    finally:
        recorder.set_active(eski)            # type: ignore[arg-type]
    assert recorder.active() is eski

    src = (ROOT / "app/core/games.py").read_text(encoding="utf-8")
    assert "from app.core.recorder import RECORDER" not in src


def test_studio_yardimcilari_dogru():
    """studio.py'de cache_dir()/projects_dir() yok; CACHE sabiti ve home_dir() var."""
    from app.core import studio
    assert hasattr(studio, "CACHE")
    assert hasattr(studio, "home_dir")
    assert not hasattr(studio, "cache_dir")
    assert not hasattr(studio, "projects_dir")

    mcp = (ROOT / "app/core/studio_mcp.py").read_text(encoding="utf-8")
    wf = (ROOT / "app/core/studio_workflow.py").read_text(encoding="utf-8")
    assert "S.cache_dir()" not in mcp
    assert "studio.projects_dir()" not in wf


def test_flow_chain_dikey_kirpma_dogru_fonksiyona_bagli():
    from app.core import clip_factory
    assert hasattr(clip_factory, "auto_vertical_reframe")
    assert not hasattr(clip_factory, "vertical_reframe")
    src = (ROOT / "app/core/flow_chain.py").read_text(encoding="utf-8")
    assert "vertical_reframe(src, out, platform=" not in src


def test_api_mini_island_open_main_var():
    from app.ui.api import Api
    assert hasattr(Api, "mini_island_open_main")


# ---------------------------------------------------------------- arayuz <-> Api

def test_tum_js_api_cagrilari_gercek_metotlara_gider():
    """Arayuzdeki her api.<ad>() cagrisi Api'de bulunmali (olu buton olmasin).

    Bu test, denetimde bulunan 6 kirik butonu ve ileride eklenecek ayni tur hatalari yakalar.
    """
    from app.ui.api import Api

    eksik: dict[str, list[str]] = {}
    for f in sorted((ROOT / "app/ui/web").glob("*.js")):
        js = f.read_text(encoding="utf-8", errors="replace")
        adlar = set(re.findall(r"\bapi\.([a-z_][a-z0-9_]*)\(", js))
        adlar |= set(re.findall(r"api\(\)\?\.([a-z_][a-z0-9_]*)\?\.", js))
        adlar -= {"then", "catch", "finally"}
        yok = sorted(n for n in adlar if not hasattr(Api, n))
        if yok:
            eksik[f.name] = yok
    assert not eksik, f"Api'de olmayan arayuz cagrilari: {eksik}"


def test_kami_flow_callapi_adlari_bagli():
    """callApi(\"ad\") bicimindeki cagrilar da Api'de olmali."""
    from app.ui.api import Api
    js = (ROOT / "app/ui/web/kami-flow.js").read_text(encoding="utf-8")
    adlar = set(re.findall(r'callApi\("([A-Za-z_][A-Za-z0-9_]*)"', js))
    assert adlar, "kami-flow.js icinde callApi cagrisi bulunamadi"
    yok = sorted(n for n in adlar if not hasattr(Api, n))
    assert not yok, f"Api'de olmayan callApi adlari: {yok}"
