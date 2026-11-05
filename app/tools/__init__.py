"""Agir yapay zeka araclari icin ALT SUREC giris noktalari (Whisper, UVR). Arayuz surecine torch/CUDA yuklenmez."""

import sys as _sys
if _sys.platform == "win32":   # eksik/uyumsuz DLL icin Windows hata penceresi acma (sessizce hata ver)
    import ctypes as _ct
    _ct.windll.kernel32.SetErrorMode(0x0001 | 0x0002 | 0x8000)
