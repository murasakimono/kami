"""Dalga 4 (Video, Studio, Picture Tarif & Oda) birim ve sozlesme testleri."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from PIL import Image

ROOT = Path(__file__).resolve().parent.parent


def test_video_enhance_gpu_preset_and_batch():
    from app.core import video_enhance as ve

    assert "gpu_fast" in ve.PRESETS
    with patch("app.core.video_enhance._nvenc_ok", return_value=True):
        args = ve._vcodec_args("ffmpeg", use_gpu=True)
        assert "h264_nvenc" in args
    with patch("app.core.video_enhance._nvenc_ok", return_value=False):
        args = ve._vcodec_args("ffmpeg", use_gpu=True)
        assert "libx264" in args

    r_bad = ve.preview_split("gpu_fast", "C:/olmayan_video.mp4", "ffmpeg")
    assert r_bad["ok"] is False
    b_bad = ve.batch_start("gpu_fast", [], "ffmpeg")
    assert b_bad["ok"] is False


def test_studio_probe_encoders_and_queue(tmp_path):
    from app.core.studio import Studio

    st = Studio(lambda: "ffmpeg")
    mock_ok = MagicMock(returncode=0)
    mock_fail = MagicMock(returncode=1)

    def fake_run(args, timeout=30):
        return mock_ok if "h264_nvenc" in args or "libx264" in args else mock_fail

    with patch.object(st, "_run", side_effect=fake_run):
        pr = st.probe_encoders()
    assert pr["ok"] is True
    assert pr["recommended"] == "h264_nvenc"
    assert any(e["id"] == "h264_nvenc" and e["ok"] for e in pr["encoders"])

    with patch.object(st, "_export", side_effect=lambda job, proj, out, opts: job.update(state="done", p=1.0)):
        qa = st.queue_add({"name": "Test"}, str(tmp_path / "out.mp4"))
        assert qa["ok"] is True
        ql = st.queue_list()
        assert ql["ok"] is True and len(ql["items"]) == 1


def test_picture_tarif_pipeline(tmp_path):
    from app.core import picture_pro

    src = tmp_path / "sample.png"
    Image.new("RGB", (400, 200), (120, 60, 200)).save(src)
    out_dir = tmp_path / "out"
    res = picture_pro.run_tarif_pipeline(
        [str(src)],
        [
            {"op": "fit_square", "size": 256},
            {"op": "contrast", "factor": 1.2},
            {"op": "sharpen", "amount": 100},
            {"op": "format", "ext": "webp"},
        ],
        out_dir=str(out_dir),
    )
    assert res["ok"] is True
    assert res["count"] == 1
    out_p = Path(res["done"][0])
    assert out_p.is_file() and out_p.suffix == ".webp"
    with Image.open(out_p) as im:
        assert im.size == (256, 256)


def test_wave4_api_surface_and_ui_contracts():
    from app.ui.api import Api

    for m in (
        "enhance_preview_split", "enhance_batch_start", "pic_tarif_run",
        "studio_probe_encoders", "studio_render_queue_add",
        "studio_render_queue_list", "studio_render_queue_cancel", "studio_render_queue_clear",
    ):
        assert hasattr(Api, m), f"Api.{m} eksik"

    for jm in ("enhance_preview_split", "enhance_batch_start", "pic_tarif_run"):
        assert jm in Api.JOB_METHODS, f"JOB_METHODS icinde {jm} eksik"

    enh = (ROOT / "app/ui/web/enhance.html").read_text(encoding="utf-8")
    assert "spBefore" in enh and "qRunBtn" in enh and "enhance_preview_split" in enh and "Array.isArray(r?.done)" in enh

    st_html = (ROOT / "app/ui/web/studio.html").read_text(encoding="utf-8")
    assert 'data-a="gpuprobe"' in st_html and 'data-a="rqueue"' in st_html

    pic_html = (ROOT / "app/ui/web/picture.html").read_text(encoding="utf-8")
    pic_js = (ROOT / "app/ui/web/picture.js").read_text(encoding="utf-8")
    assert 'data-a="tarif"' in pic_html
    assert "pic_tarif_run" in pic_js and "openTarifModal" in pic_js

    rm = (ROOT / "app/ui/web/room.js").read_text(encoding="utf-8")
    assert "streamVol" in rm and "contentHint" in rm and "> 0.6" in rm
