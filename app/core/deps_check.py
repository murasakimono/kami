"""v2.5.3: Paketlenmis Kami.exe icinde ucuncu taraf bagimliliklarin gercekten yuklenebildigini dogrular.

Neden: testler gelistirme ortaminda (.venv) gecerken kurulu exe'de bir paket eksik kalabiliyordu (2.5.x Beat:
noisereduce/scipy). build.py, PyInstaller'dan sonra `Kami.exe --selfcheck-deps <json>` calistirir; zorunlu bir
modul eksikse kurulum paketi uretilmez. Kami Doktor da ayni listeyi kullanir.
"""
from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

# (modul, hangi ozellik kullaniyor, zorunlu mu)
MODULES: list[tuple[str, str, bool]] = [
    ("webview", "arayuz (pywebview)", True),
    ("requests", "ag istekleri", True),
    ("yt_dlp", "video/ses indirme", True),
    ("curl_cffi", "yt-dlp tarayici taklidi", True),
    ("PIL", "gorsel isleme", True),
    ("numpy", "ses/gorsel hesaplama", True),
    ("mutagen", "muzik etiketleri", True),
    ("Cryptodome.Cipher.AES", "MEGA eklentisi", True),
    ("pystray", "sistem tepsisi", True),
    ("psutil", "RAM/oyun kalkani", True),
    ("pypdf", "Reader PDF", True),
    ("pypdfium2", "Reader PDF render", True),
    ("pymupdf", "Reader/Doc Studio", True),
    ("openpyxl", "tablo disa aktarma", True),
    ("zxingcpp", "QR kodlari (Booth, Oda)", True),
    ("vtracer", "Picture vektorlestirme", True),
    ("rawpy", "Picture RAW", True),
    ("rlottie_python", "Lottie animasyonlari", True),
    ("pynvml", "GPU izleme", True),
    ("pyaudiowpatch", "ekran kaydi sesi", True),
    ("pedalboard", "Kami Beat FX/VST3 zinciri", True),
    ("soundfile", "Kami Beat ses okuma/yazma", True),
    ("sounddevice", "Kami Booth PC kaydi", True),
]


def check() -> dict[str, Any]:
    missing: list[dict[str, str]] = []
    ok: list[str] = []
    for mod, feat, required in MODULES:
        try:
            importlib.import_module(mod)
            ok.append(mod)
        except Exception as exc:   # ImportError, DLL yukleme hatasi (OSError) vb.
            missing.append({"module": mod, "feature": feat, "required": required, "error": f"{type(exc).__name__}: {exc}"[:200]})
    return {"ok": not any(m["required"] for m in missing), "loaded": ok, "missing": missing}


def run_cli(out_path: str) -> int:
    res = check()
    Path(out_path).write_text(json.dumps(res, ensure_ascii=False, indent=1), encoding="utf-8")
    return 0 if res["ok"] else 3
