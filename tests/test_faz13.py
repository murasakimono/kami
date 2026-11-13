"""Faz 13 testleri: Kami Kasa FTS5 WAL + vektor semantik arama, oto-bolumlendirme & VirtualGrid."""
from __future__ import annotations

from pathlib import Path

from app.core import semantic_vault


def test_semantic_vault_fts5_and_vector_search(tmp_path: Path):
    db = tmp_path / "kasa.db"
    semantic_vault.index_segment(
        "C:/videos/tokyo.mp4",
        title="Tokyo Gece",
        start_sec=42.5,
        end_sec=68.0,
        tags="gece yagmur neon sokak",
        transcript="yagmur altinda neon tabelalar parliyor",
        embedding=[0.9, 0.1, 0.0, 0.2],
        db_path=db,
    )
    semantic_vault.index_segment(
        "C:/videos/dag.mp4",
        title="Karli Dag",
        start_sec=10.0,
        end_sec=25.0,
        tags="kar gunes zirve",
        transcript="sabah gunesi zirveye vuruyor",
        embedding=[0.0, 0.2, 0.9, 0.1],
        db_path=db,
    )

    res = semantic_vault.search("neon yagmur", query_embedding=[0.88, 0.12, 0.0, 0.2], db_path=db)
    assert res["ok"] is True
    assert len(res["results"]) >= 1
    top = res["results"][0]
    assert top["path"] == "C:/videos/tokyo.mp4"
    assert top["start_sec"] == 42.5

    st = semantic_vault.kasa_stats(db_path=db)
    assert st["ok"] is True
    assert st["segments"] == 2
    assert st["files"] == 2


def test_auto_chapters_extractive_fallback():
    segs = [
        {"start": 0.0, "end": 50.0, "text": "Giris ve sistem mimarisi anlatimi."},
        {"start": 60.0, "end": 120.0, "text": "Veritabani tasarimi ve WAL modu."},
        {"start": 200.0, "end": 260.0, "text": "Kapanis ve test sonuclari."},
    ]
    out = semantic_vault.auto_chapters(segs, chunk_seconds=180.0, use_ollama=False)
    assert out["ok"] is True
    assert out["engine"] == "extractive"
    assert len(out["chapters"]) == 2
    assert out["chapters"][0]["start"] == 0.0
    assert out["chapters"][1]["start"] == 200.0


def test_virtual_grid_js_contract():
    js = Path("app/ui/web/virtual-grid.js").read_text(encoding="utf-8")
    assert "KamiVirtualGrid" in js
    assert "replaceChildren" in js
    assert "overscan" in js
