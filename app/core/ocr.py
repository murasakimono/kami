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
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($img)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$results = @()
foreach ($want in ($lang -split ',')) {
  $eng = $null
  if ($want -and $want -ne '*') {
    $tag = $avail | Where-Object { $_ -eq $want -or $_.StartsWith($want + '-') } | Select-Object -First 1
    if ($tag) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromLanguage([Windows.Globalization.Language]::new($tag)) }
  }
  if (-not $eng -and ($want -eq '*' -or -not $want)) { $eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages() }
  if (-not $eng) { continue }
  $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  $results += @{ lang = $eng.RecognizerLanguage.LanguageTag; lines = @($res.Lines | ForEach-Object { $_.Text }) }
}
$stream.Dispose()
$o = @{ results = $results; avail = $avail }
[System.IO.File]::WriteAllText($out, (ConvertTo-Json $o -Compress -Depth 5), [System.Text.UTF8Encoding]::new($false))
"""
_CJK = "぀-ヿ㐀-鿿豈-﫿ｦ-ﾟ　-〿！-｠"
_CJK_GAP = re.compile(f"(?<=[{_CJK}]) +(?=[{_CJK}])")


def _best(cands: list[tuple[str, str]]) -> tuple[str, str]:
    """Birden cok motor okuduysa: CJK motoru gercekten CJK yazi bulduysa onu, yoksa ilk (profil) sonucu sec."""
    for lg, text in cands:
        if lg.split("-")[0] in ("ja", "zh", "ko"):
            chars = [c for c in text if not c.isspace()]
            cjk = sum(1 for c in chars if re.match(f"[{_CJK}\uac00-\ud7af]", c))
            if chars and cjk / len(chars) >= 0.5 and cjk >= 2:
                return lg, text
    latin = [c for c in cands if c[0].split("-")[0] not in ("ja", "zh", "ko")]
    return (latin or cands)[0]


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
    # otomatik: kullanici profili dilleri + (kuruluysa) Japonca/Cince/Korece; en uygun sonuc secilir
    langs = str(lang or "")[:8] or "*,ja,zh,ko"
    tmp = tempfile.mkdtemp(prefix="kami_ocr_")
    img, out, ps1 = (os.path.join(tmp, n) for n in ("in.png", "out.json", "ocr.ps1"))
    try:
        with open(img, "wb") as f:
            f.write(raw)
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(_PS)
        r = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1, img, langs, out],
            capture_output=True, timeout=40, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if not os.path.isfile(out):
            err = (r.stderr or b"").decode("utf-8", "replace").strip().splitlines()
            return {"ok": False, "error": (err[0] if err else f"ocr_failed ({r.returncode})")[:200]}
        with open(out, encoding="utf-8") as f:
            o = json.load(f)
        avail = o.get("avail") or []
        avail = avail if isinstance(avail, list) else [avail]
        res = o.get("results") or []
        res = res if isinstance(res, list) else [res]
        cands = []
        for r_ in res:
            lines = r_.get("lines") or []
            lines = [lines] if isinstance(lines, str) else lines
            text = "\n".join(_CJK_GAP.sub("", ln) for ln in lines if ln).strip()   # Windows OCR Japoncada harf arasina bosluk koyar
            if text:
                cands.append((r_.get("lang") or "", text))
        if not cands:
            return {"ok": True, "text": "", "lang": "", "avail": avail}
        return {"ok": True, "text": _best(cands)[1], "lang": _best(cands)[0], "avail": avail}
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


def read_text(image_path, lang: str = "") -> dict:
    """Dosyadan OCR (klip/vurgu/pano/manga modulleri icin): {ok, text, lines, lang}. lang: "en,tr" gibi."""
    try:
        with open(image_path, "rb") as f:
            raw = f.read()
    except OSError as exc:
        return {"ok": False, "error": str(exc)[:200], "text": "", "lines": []}
    res = recognize(base64.b64encode(raw).decode("ascii"), lang)
    text = str(res.get("text") or "")
    return {**res, "text": text, "lines": [ln for ln in text.splitlines() if ln.strip()]}
