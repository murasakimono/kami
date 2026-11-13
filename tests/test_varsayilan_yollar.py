"""Moduller varsayilan veri yolunu app.paths.DATA_DIR'den almali (app.core.paths yok: ImportError'u testler kacirmisti)."""
from app import paths


def test_varsayilan_veri_yollari():
    from app.core import link_crawler, pano_tools, semantic_vault
    assert link_crawler._rules_path().parent == paths.DATA_DIR
    assert pano_tools._shelf_path().parent == paths.DATA_DIR
    assert semantic_vault._default_db().parent == paths.DATA_DIR


def test_ocr_read_text_var():
    from app.core import ocr
    r = ocr.read_text("olmayan_dosya.png")
    assert r["ok"] is False and r["lines"] == []
