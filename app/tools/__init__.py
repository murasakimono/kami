"""Agir yapay zeka araclari icin ALT SUREC giris noktalari (Whisper, UVR). Arayuz surecine torch/CUDA yuklenmez."""

import sys as _sys
if _sys.platform == "win32":   # eksik/uyumsuz DLL icin Windows hata penceresi acma (sessizce hata ver)
    import ctypes as _ct
    _ct.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)


def load_args(argv: list[str]) -> list[str]:
    """`@dosya.json` verilirse argumanlar UTF-8 JSON listesinden okunur (komut satiri kodlamasi / & / Turkce harf sorunu yok)."""
    if len(argv) == 1 and argv[0].startswith("@"):
        import json
        with open(argv[0][1:], encoding="utf-8") as f:
            return [str(x) for x in json.load(f)]
    return argv
