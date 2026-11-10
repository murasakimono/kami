"""Ekran ustu OCR (B6): oynaticida secilen kare bolgesindeki yaziyi okur.

Windows'un yerlesik OCR'i (Windows.Media.Ocr, WinRT) Windows PowerShell 5.1 uzerinden; ek indirme yok.
Dil paketi yuklu olmayan dil (or. Japonca) icin Windows Ayarlar > Dil'den "Optik karakter tanima" eklenmeli;
yoksa kullanici profili dilleriyle denenir.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import tempfile

log = logging.getLogger(__name__)

_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Globalization.Language, Windows.Globalization, ContentType = WindowsRuntime] | Out-Null
$img = $args[0]; $lang = $args[1]; $out = $args[2]
$avail = @([Windows.Media.Ocr.OcrEngine]::AvailableRecognizerLanguages | ForEach-Object { $_.LanguageTag })
$eng = $null
if ($lang) {
  $tag = $avail | Where-Object { $_ -eq $lang -or $_.StartsWith($lang + '-') } | Select-Object -First 1
  if ($tag) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag)) }
}
if (-not $eng) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($img)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
$stream.Dispose()
$o = @{ lines = @($res.Lines | ForEach-Object { $_.Text }); lang = $eng.RecognizerLanguage.LanguageTag; avail = $avail }
[System.IO.File]::WriteAllText($out, (ConvertTo-Json $o -Compress), [System.Text.UTF8Encoding]::new($false))
"""
_CJK = "぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ　-〿！-｠"
_CJK_GAP = re.compile(f"(?<=[{_CJK}]) +(?=[{_CJK}])")


def recognize(png_b64: str, lang: str = "") -> dict:
    """png_b64: 'data:image/png;base64,...' veya ham base64. Doner: {ok, text, lang, avail} | {ok: False, error}."""
    if os.name != "nt":
        return {"ok": False, "error": "windows_only"}
    data = str(png_b64 or "")
    if "," in data[:80]:
        data = data.split(",", 1)[1]
    try:
        raw = base64.b64decode(data, validate=False)
    except ValueError:
        return {"ok": False, "error": "bad_image"}
    if len(raw) < 100 or len(raw) > 25 * 2**20:
        return {"ok": False, "error": "bad_image"}
    tmp = tempfile.mkdtemp(prefix="kami_ocr_")
    img, out, ps1 = (os.path.join(tmp, n) for n in ("in.png", "out.json", "ocr.ps1"))
    try:
        with open(img, "wb") as f:
            f.write(raw)
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(_PS)
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1, img, str(lang or "")[:8], out],
            capture_output=True, timeout=40, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not os.path.isfile(out):
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            return {"ok": False, "error": (err[0] if err else f"ocr_failed ({r.returncode})")[:200]}
        with open(out, encoding="utf-8") as f:
            o = json.load(f)
        lines = o.get("lines") or []
        if isinstance(lines, str):
            lines = [lines]
        text = "\n".join(_CJK_GAP.sub("", ln) for ln in lines if ln).strip()   # Windows OCR Japoncada harf arasina bosluk koyar
        avail = o.get("avail") or []
        return {"ok": True, "text": text, "lang": o.get("lang") or "", "avail": avail if isinstance(avail, list) else [avail]}
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": "timeout"}
    except Exception as exc:
        log.exception("OCR basarisiz")
        return {"ok": False, "error": f"{type(exc).__name__}: {str(exc)[:160]}"}
    finally:
        for p in (img, out, ps1):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass
