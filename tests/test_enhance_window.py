"""Video Iyilestirici pencere/koprü dikisi (GUI acmadan).

Neden ayri dosya: bu ortamda pywebview/.NET yuklenemedigi icin pencere gozle acilamiyor;
burada pencere FABRIKASI ve koprü yuzeyi dogrulanir (GUI cizimi degil, kablolama).
"""
from __future__ import annotations

from app import paths
from app.ui.api import Api
from app.ui.api_enhance import EnhanceMixin


class _FakeApi(EnhanceMixin):
    """Api'nin yalnizca pencere acma tarafini taklit eder.

    _open_mod_window GERCEK Api'den alinir (kopyalanmaz): boylece test edilen sey
    gercek kablolama olur, taklit degil.
    """

    _open_mod_window = Api._open_mod_window

    def __init__(self) -> None:
        self.made = 0
        self.fronted = 0

    # _open_mod_window bu ikisini arar (app/ui/api.py ile ayni sozlesme)
    def _make_enhance_window(self):
        self.made += 1
        return f"win-{self.made}"

    def _front_enhance(self) -> None:
        self.fronted += 1


def test_enhance_open_pencereyi_uretir():
    f = _FakeApi()
    r = f.enhance_open()
    assert r == {"ok": True}
    assert f.made == 1, "ilk cagri pencere fabrikasini cagirmali"
    assert f.fronted == 1, "pencere one getirilmeli"


def test_enhance_open_ikinci_cagri_yeniden_uretmez():
    """Pencere zaten varsa yeniden yaratilmaz (main.py: _enhance_win saklanir)."""
    f = _FakeApi()
    f._enhance_win = "win-once"          # main.py'nin yazdigi nitelik
    assert f.enhance_open() == {"ok": True}
    assert f.made == 0
    assert f.fronted == 1


def test_enhance_html_yerinde():
    assert (paths.WEB_DIR / "enhance.html").is_file()


def test_main_modul_tablosunda_enhance_var():
    """main.py modul dongusu bu anahtari gorurse _make_enhance_window kurulur."""
    src = (paths.WEB_DIR.parents[1] / "main.py").read_text(encoding="utf-8")
    assert '"enhance", "Kami İyileştirici", "enhance.html"' in src
    assert '"enhance": (163, 230, 53)' in src


def test_enhance_kopru_yuzeyi():
    """JS'in cagirdigi tum enhance_* metotlari Api'de bulunmali."""
    gerekli = ["enhance_open", "enhance_presets", "enhance_tools", "enhance_probe", "enhance_pick",
               "enhance_start", "enhance_job", "enhance_jobs", "enhance_cancel", "enhance_install",
               "enhance_open_output"]
    eksik = [m for m in gerekli if not hasattr(EnhanceMixin, m)]
    assert not eksik, f"eksik metot: {eksik}"
