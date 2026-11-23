# -*- mode: python ; coding: utf-8 -*-
# Kami paketleme: PyInstaller ONEDIR (onefile DEGIL: acilista %TEMP%'e acma yok, antivirus yanlis alarmi daha az),
# UPX KAPALI (UPX sikistirmasi en sik yanlis alarm sebebi). Iki exe tek klasorde:
#   Kami.exe       (pencereli uygulama)
#   kami_host.exe  (tarayici native messaging relay; konsol alt sistemi, sadece stdlib)
# Calistir: packaging\build.ps1   (bin/, plugins/, extension/ kopyalamayi o yapar)
from PyInstaller.utils.hooks import collect_data_files, collect_dynamic_libs, collect_submodules, copy_metadata

ROOT = SPECPATH + "\\.."

# Agir AI paketleri pakete GIRMEZ (Whisper/UVR ilk kullanimda ayri ortama iner); test/arac kodu da girmez.
EXCLUDES = ["torch", "torchaudio", "torchvision", "faster_whisper", "audio_separator", "librosa", "ctranslate2",
            "onnxruntime", "onnx", "audioread", "scipy", "numba", "llvmlite", "sklearn", "tokenizers",
            "huggingface_hub", "transformers", "pandas", "matplotlib", "pytest", "_pytest", "tools",
            "tests", "app.tools", "tkinter", "PyInstaller"]

hidden = [m for m in collect_submodules("app") if not m.startswith("app.tools")]
hidden += collect_submodules("yt_dlp") + collect_submodules("yt_dlp_ejs")
hidden += ["Cryptodome.Cipher.AES", "Cryptodome.Util.Counter", "pystray._win32", "mutagen.id3", "mutagen.mp3",
           "mutagen.mp4", "mutagen.easyid3", "mutagen.flac", "html.parser", "sqlite3", "winreg"]

datas = [(ROOT + "\\app\\ui\\web", "app\\ui\\web"),
         (ROOT + "\\app\\assets\\sfx", "app\\assets\\sfx"),
         # alt surec betikleri (Whisper/UVR/selftest) DUZ dosya: araclar ortaminin Python'u calistirir
         (ROOT + "\\app\\__init__.py", "toolsrc\\app"),
         (ROOT + "\\app\\tools", "toolsrc\\app\\tools")]
datas += collect_data_files("yt_dlp_ejs") + collect_data_files("webview")
datas += [(ROOT + "\\.venv\\Lib\\site-packages\\rlottie_python\\rlottie.dll", "rlottie_python")]   # Lottie: dll paket klasorunden yuklenir
hidden += ["rlottie_python", "rlottie_python.rlottie_wrapper"] + collect_submodules("rawpy") + collect_submodules("pillow_heif")
binaries = collect_dynamic_libs("rawpy") + collect_dynamic_libs("pillow_heif")
datas += copy_metadata("yt-dlp")   # paketli yt-dlp surumu (data/pylib guncellemesi bununla karsilastirir)

a = Analysis([ROOT + "\\app\\main.py"], pathex=[ROOT], hiddenimports=hidden, binaries=binaries, datas=datas, excludes=EXCLUDES,
             noarchive=False)
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="Kami", icon=ROOT + "\\packaging\\kami.ico",
          console=False, upx=False, version=ROOT + "\\packaging\\version_info.txt")

h = Analysis([ROOT + "\\native_host\\host.py"], pathex=[ROOT], excludes=EXCLUDES + ["app", "yt_dlp", "webview"])
hpyz = PYZ(h.pure)
hexe = EXE(hpyz, h.scripts, [], exclude_binaries=True, name="kami_host", icon=ROOT + "\\packaging\\kami.ico",
           console=True, upx=False)

coll = COLLECT(exe, a.binaries, a.datas, hexe, h.binaries, h.datas, upx=False, name="Kami")
