"""Video Iyilestirici testleri: filtre zinciri, preset sozlesmesi, uctan uca filtre yolu.

Model (Real-ESRGAN / RIFE) gerektiren presetler burada CALISTIRILMAZ: indirme agi gerektirir.
Onlarin argumanlari studio_enhance tarafinda zaten test ediliyor (tests/test_v125.py).
"""
from __future__ import annotations

import shutil
import uuid
import subprocess
import time
from pathlib import Path

import pytest

from app.core import video_enhance as ve

INFO_DUZ = {"interlaced": False, "width": 640, "height": 360, "fps": 30.0}
INFO_TARAMA = {"interlaced": True, "width": 720, "height": 480, "fps": 25.0}


def _ffmpeg() -> str | None:
    return shutil.which("ffmpeg")


@pytest.fixture()
def workdir():
    """Calisma alani icinde gecici klasor.

    NOT: pytest'in tmp_path'i ve tempfile.mkdtemp() bu ortamda yazilamaz klasor uretiyor
    (sandbox DACL'i), bu yuzden duz mkdir kullaniliyor.
    """
    base = Path.cwd() / ".tmp" / "enh-tests"
    base.mkdir(parents=True, exist_ok=True)
    d = base / ("enh-" + uuid.uuid4().hex[:10])
    d.mkdir()
    try:
        yield d
    finally:
        shutil.rmtree(d, ignore_errors=True)


# ---------------------------------------------------------------- presetler

def test_preset_sozlesmesi():
    liste = ve.presets()
    assert {p["id"] for p in liste} == set(ve.PRESETS)
    for p in liste:
        assert p["ad"] and p["aciklama"], p
        assert isinstance(p["model"], bool)
        assert p["upscale"] in (0, 2, 4)
        assert p["interp"] in (0, 2, 4)


def test_gerekli_araclar():
    assert ve.required_tools("temizle") == []
    assert ve.required_tools("hizli") == []
    assert ve.required_tools("netlestir") == ["esrgan"]
    assert ve.required_tools("akici") == ["rife"]
    assert ve.required_tools("sinema") == ["esrgan", "rife"]
    assert ve.required_tools("yeniden") == ["flashvsr"]
    assert ve.required_tools("yok") == []


def test_flashvsr_preset_sozlesmesi():
    p = next(x for x in ve.presets() if x["id"] == "yeniden")
    assert p["flashvsr"] is True and p["upscale"] == 4
    # flashvsr presetinde ncnn araclari istenmemeli
    assert ve.required_tools("yeniden") == ["flashvsr"]


def test_flashvsr_vram_bayraklari():
    """Olculen calisan yapilandirma: -m tiny + --tiled-vae. tiled-dit upstream bug'i var."""
    from app.core import flashvsr as fv
    f = fv.vram_flags(4)
    for must in ("--tiled-vae", "--color-fix"):
        assert must in f, must
    assert f[f.index("-m") + 1] == "tiny"       # olculen calisan mod
    assert "--tiled-dit" not in f               # tile videolari yazilmiyor (upstream bug)
    assert "--unload-dit" not in f
    # opt-in: yalniz istenirse
    g = fv.vram_flags(4, "tiny-long", 192, tiled_dit=True, unload_dit=True)
    assert "--tiled-dit" in g and "--unload-dit" in g
    assert g[g.index("--tile-size") + 1] == "192"
    # tile degeri guvenli araliga kirpilir
    lo = fv.vram_flags(4, "tiny", 8, tiled_dit=True)
    hi = fv.vram_flags(4, "tiny", 4096, tiled_dit=True)
    assert lo[lo.index("--tile-size") + 1] == "128"
    assert hi[hi.index("--tile-size") + 1] == "512"
    # gecersiz mod -> tiny
    assert fv.vram_flags(4, "sacma")[fv.vram_flags(4, "sacma").index("-m") + 1] == "tiny"


def test_flashvsr_komut_satiri():
    """build_args, dogruladigim CLI cagrisiyla ayni sekli uretmeli."""
    from app.core import flashvsr as fv
    a = fv.build_args("C:/x/girdi.mp4", {"scale": 4}, "C:/out")
    assert a[0] == str(fv.PY) and a[1] == "run.py"
    assert a[a.index("-i") + 1] == "C:/x/girdi.mp4"
    assert a[-1] == "C:/out"
    assert a[a.index("-s") + 1] == "4"


def test_flashvsr_durum_sozlesmesi():
    from app.core import flashvsr as fv
    st = fv.status()
    assert set(st) >= {"installed", "weights", "size_gb", "root"}
    assert isinstance(st["installed"], bool) and isinstance(st["weights"], bool)
    assert st["size_gb"] > 1


# ---------------------------------------------------------------- TensorRT yolu (Faz 2)

def test_trt_preset_sozlesmesi():
    p = next(x for x in ve.presets() if x["id"] == "trt")
    assert p["trt"] is True and p["upscale"] == 2
    assert ve.required_tools("trt") == ["trt"]


def test_trt_matris_secimi():
    """SD'de BT.601, HD'de BT.709: yanlis matris renk kaymasina yol acar."""
    from app.core import vs_trt
    assert vs_trt.matrix_for(480) == "470bg"
    assert vs_trt.matrix_for(720) == "709"
    assert vs_trt.matrix_for(1080) == "709"


def test_trt_script_uretimi():
    from app.core import vs_trt
    s = vs_trt.script("C:/x/g.mp4", "C:/m/e.engine", width=1280, height=720)
    assert "core.trt.Model" in s and "engine_path" in s
    assert "format=vs.RGBS" in s              # motor float32 bekler (RGB24 degil)
    assert "matrix_in_s='709'" in s
    assert "set_output()" in s
    assert "\\" not in s                      # .vpy icinde ters bolu kacis sorunu olmasin
    # tilesize klip boyutunu asamaz (vs-mlrt hatasi)
    assert "tilesize=720" in s                # 4096 -> min(1280,720)


def test_trt_engine_adi():
    from app.core import vs_trt
    assert vs_trt.engine(2).name == "esrgan_x2_fp16.engine"
    assert vs_trt.engine(4).name == "esrgan_x4_fp16.engine"
    assert vs_trt.engine(3).name == "esrgan_x2_fp16.engine"   # 3x yok -> 2x


def test_trt_durum_sozlesmesi():
    from app.core import vs_trt
    st = vs_trt.status()
    assert set(st) >= {"installed", "size_gb", "root", "engines"}
    assert isinstance(st["installed"], bool) and isinstance(st["engines"], list)


# ---------------------------------------------------------------- filtreler

def test_interlace_karari():
    # interlaced kaynakta otomatik acilir
    assert any("bwdif" in f for f in ve.filters("temizle", INFO_TARAMA, {}))
    # progressive kaynakta otomatik acilmaz
    assert not any("bwdif" in f for f in ve.filters("temizle", INFO_DUZ, {}))
    # zorla ac / kapat
    assert any("bwdif" in f for f in ve.filters("temizle", INFO_DUZ, {"deinterlace": "on"}))
    assert not any("bwdif" in f for f in ve.filters("temizle", INFO_TARAMA, {"deinterlace": "off"}))


def test_denoise_seviyeleri():
    assert ve.filters("temizle", INFO_DUZ, {"denoise": 0}) == []
    assert "hqdn3d=1.5:1.5:6:6" in ve.filters("temizle", INFO_DUZ, {"denoise": 1})
    assert "hqdn3d=3:3:9:9" in ve.filters("temizle", INFO_DUZ, {"denoise": 2})
    f3 = ve.filters("temizle", INFO_DUZ, {"denoise": 3})
    assert "hqdn3d=4.5:4.5:12:12" in f3
    assert any("atadenoise" in f for f in f3), "seviye 3'te zamansal temizlik de olmali"


def test_denoise_otomatik():
    # AI yolu daha temiz girdi ister -> seviye 2, saf filtre yolu -> seviye 1
    assert "hqdn3d=3:3:9:9" in ve.filters("netlestir", INFO_DUZ, {})
    assert "hqdn3d=1.5:1.5:6:6" in ve.filters("temizle", INFO_DUZ, {})


def test_buyutme_yalniz_filtre_yolunda():
    # hizli: ffmpeg buyutur
    assert any("scale=trunc(iw*2" in f for f in ve.filters("hizli", INFO_DUZ, {"denoise": 0}))
    assert any("unsharp" in f for f in ve.filters("hizli", INFO_DUZ, {"denoise": 0}))
    # netlestir: model buyutur, ffmpeg scale EKLEMEZ
    assert not any("scale=" in f for f in ve.filters("netlestir", INFO_DUZ, {"denoise": 0}))


def test_akici_boyut_degistirmez():
    assert not any("scale=" in f for f in ve.filters("akici", INFO_DUZ, {"denoise": 0}))


# ---------------------------------------------------------------- yardimcilar

def test_ses_kopyalama_karari():
    assert ve._audio_copy_ok("aac")
    assert ve._audio_copy_ok("MP3")
    assert not ve._audio_copy_ok("flac")   # mp4 icine oldugu gibi konmaz -> aac'e cevrilir
    assert not ve._audio_copy_ok("")


def test_cikti_adi_tekil(workdir):
    src = "C:/x/klip adÃ„Â±!.mp4"
    a = ve._out_path(workdir, src, "temizle")
    assert a.suffix == ".mp4" and "klip_ad" in a.name
    a.write_bytes(b"x")                       # dosya olusunca ad degismeli
    b = ve._out_path(workdir, src, "temizle")
    assert b != a and b.name.endswith("_2.mp4")


def test_gecersiz_girdiler():
    assert ve.job("olmayan-is")["state"] == "error"
    assert ve.start("olmayan-preset", "x", "ffmpeg")["error"] == "bad_preset"
    assert ve.start("temizle", str(Path("olmayan_dosya_xyz.mp4")), "ffmpeg")["error"] == "dosya_yok"
    assert ve.install_start("olmayan-arac")["ok"] is False


# ---------------------------------------------------------------- disk temizligi

def test_rm_dir_siler(workdir):
    d = workdir / "in_p000"
    d.mkdir()
    (d / "00000001.png").write_bytes(b"x")
    job = {}
    assert ve._rm_dir(d, job) is True
    assert not d.exists()
    assert job.get("leftover", 0) == 0
    # zaten yok olan klasor de sorun degil
    assert ve._rm_dir(d, job) is True


def test_rm_dir_hatayi_sessiz_yutmez(workdir):
    """Eski davranis: rmtree(ignore_errors=True) hatayi yutuyordu, GB'larca PNG kaliyordu."""
    f = workdir / "silinemez.txt"
    f.write_bytes(b"x")
    job = {}
    assert ve._rm_dir(f, job) is False          # dosyaya rmtree -> hata
    assert job["leftover"] == 1
    assert job["leftover_path"].endswith("silinemez.txt")
    assert f.is_file()


# ---------------------------------------------------------------- gercek ffmpeg

@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg yok")
def test_probe_gercek_dosya(workdir):
    src = workdir / "kucuk.mp4"
    subprocess.run([_ffmpeg(), "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    info = ve.probe(_ffmpeg(), str(src))
    assert (info["width"], info["height"]) == (320, 240)
    assert abs(info["fps"] - 25) < 0.5
    assert info["frames"] >= 20
    assert info["interlaced"] is False
    assert info["duration"] > 0.5


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg yok")
def test_temizle_uctan_uca(workdir):
    ff = _ffmpeg()
    src = workdir / "kaynak.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=25:duration=1",
                    "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "-shortest",
                    str(src)], check=True)
    res = ve.start("temizle", str(src), ff, {"denoise": 2}, workdir / "out")
    assert res["ok"], res
    jid = res["job"]
    t0 = time.time()
    st: dict = {}
    while time.time() - t0 < 120:
        st = ve.job(jid)
        if st["state"] != "running":
            break
        time.sleep(0.2)
    assert st.get("state") == "done", st
    out = Path(st["result"]["path"])
    assert out.is_file() and out.stat().st_size > 1000
    inf = ve.probe(ff, str(out))
    assert (inf["width"], inf["height"]) == (320, 240)   # temizle boyut degistirmez
    assert inf["audio"] is True                          # ses korunmus


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg yok")
def test_iptal_yarim_cikti_birakmaz(workdir, monkeypatch):
    """Temizle/Hizli buyut ciktiyi dogrudan hedefe yazar; iptal edilince yarim mp4 KALMAMALI."""
    ff = _ffmpeg()
    monkeypatch.setenv(ve.WORK_ENV, str(workdir / "work"))
    src = workdir / "uzun2.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=1280x720:rate=30:duration=20",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    out = workdir / "out"
    res = ve.start("temizle", str(src), ff, {"denoise": 3}, out)
    assert res["ok"], res
    jid = res["job"]
    time.sleep(0.6)                     # kodlama baslamis ama bitmemis olsun (20 sn 720p)
    ve.cancel(jid)
    st: dict = {}
    t0 = time.time()
    while time.time() - t0 < 90:
        st = ve.job(jid)
        if st["state"] != "running":
            break
        time.sleep(0.1)
    assert st.get("state") == "cancelled", st
    kalan = list(out.glob("*.mp4")) if out.exists() else []
    assert not kalan, f"iptalden sonra yarim cikti kaldi: {kalan}"


@pytest.mark.skipif(not _ffmpeg(), reason="ffmpeg yok")
def test_parcali_iste_her_parca_temizlenir(workdir, monkeypatch):
    """Uzun video parcalanir; HER parca bitince o parcanin PNG'leri silinmeli.

    Disk davranisi: tum videonun kareleri degil, tek parcanin kareleri kadar yer kaplar.
    """
    from app.core import studio_enhance as se
    if not se.installed("esrgan"):
        pytest.skip("Real-ESRGAN kurulu degil")
    ff = _ffmpeg()
    src = workdir / "uzun.mp4"
    subprocess.run([ff, "-hide_banner", "-loglevel", "error", "-y",
                    "-f", "lavfi", "-i", "testsrc=size=160x120:rate=25:duration=8",
                    "-c:v", "libx264", "-pix_fmt", "yuv420p", str(src)], check=True)
    monkeypatch.setenv(ve.WORK_ENV, str(workdir / "work"))   # sistem temp'i yerine test alani
    removed: list[str] = []
    real = ve._rm_dir

    def spy(p, job=None):
        removed.append(Path(p).name)
        return real(p, job)

    monkeypatch.setattr(ve, "_rm_dir", spy)
    res = ve.start("netlestir", str(src), ff,
                   {"scale": 2, "denoise": 0, "chunk_frames": 130}, workdir / "out")
    assert res["ok"], res
    jid = res["job"]
    t0 = time.time()
    st: dict = {}
    while time.time() - t0 < 300:
        st = ve.job(jid)
        if st["state"] != "running":
            break
        time.sleep(0.2)
    assert st.get("state") == "done", st
    # 8 sn @25 fps = 200 kare, 130'luk parca -> 2 parca -> her parca temizlenmeli
    parca_temizligi = [n for n in removed if n.startswith("in_p")]
    assert len(parca_temizligi) >= 2, f"parca basina temizlik yok: {removed}"
    assert st["result"]["info"]["frames"] >= 190

