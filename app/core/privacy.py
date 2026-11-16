"""Gizlilik Kalkani: gorseldeki yuzleri, e-posta / telefon / TC kimlik / IBAN / kart numaralarini bulaniklastirir
ve konum (GPS) dahil tum EXIF bilgisini siler. Ek paket yok: Windows'un kendi OCR'i (kelime kutulari) ve
Windows.Media.FaceAnalysis yuz bulucusu (PowerShell + WinRT). Islenmis kopya yazilir, orijinale dokunulmaz.
"""
from __future__ import annotations

import json
import logging
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image, ImageFilter, ImageOps

log = logging.getLogger(__name__)
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

_PS = r"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Runtime.WindowsRuntime
$asTask = ([System.WindowsRuntimeSystemExtensions].GetMethods() | Where-Object { $_.Name -eq 'AsTask' -and $_.GetParameters().Count -eq 1 -and $_.GetParameters()[0].ParameterType.Name -eq 'IAsyncOperation`1' })[0]
function Await($op, $type) { $t = $asTask.MakeGenericMethod($type).Invoke($null, @($op)); $t.Wait(-1) | Out-Null; $t.Result }
[Windows.Storage.StorageFile, Windows.Storage, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.Ocr.OcrEngine, Windows.Foundation, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.BitmapDecoder, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Graphics.Imaging.SoftwareBitmap, Windows.Graphics, ContentType = WindowsRuntime] | Out-Null
[Windows.Media.FaceAnalysis.FaceDetector, Windows.Media, ContentType = WindowsRuntime] | Out-Null
$img = $args[0]; $out = $args[1]; $wantFaces = $args[2] -eq '1'
$file = Await ([Windows.Storage.StorageFile]::GetFileFromPathAsync($img)) ([Windows.Storage.StorageFile])
$stream = Await ($file.OpenAsync([Windows.Storage.FileAccessMode]::Read)) ([Windows.Storage.Streams.IRandomAccessStream])
$dec = Await ([Windows.Graphics.Imaging.BitmapDecoder]::CreateAsync($stream)) ([Windows.Graphics.Imaging.BitmapDecoder])
$bmp = Await ($dec.GetSoftwareBitmapAsync()) ([Windows.Graphics.Imaging.SoftwareBitmap])
$lines = @()
$eng = [Windows.Media.Ocr.OcrEngine]::TryCreateFromUserProfileLanguages()
if ($eng) {
  $res = Await ($eng.RecognizeAsync($bmp)) ([Windows.Media.Ocr.OcrResult])
  foreach ($ln in $res.Lines) {
    $lines += @{ text = $ln.Text; words = @($ln.Words | ForEach-Object { @{ t = $_.Text; x = $_.BoundingRect.X; y = $_.BoundingRect.Y; w = $_.BoundingRect.Width; h = $_.BoundingRect.Height } }) }
  }
}
$faces = @()
if ($wantFaces -and [Windows.Media.FaceAnalysis.FaceDetector]::IsSupported) {
  $det = Await ([Windows.Media.FaceAnalysis.FaceDetector]::CreateAsync()) ([Windows.Media.FaceAnalysis.FaceDetector])
  $gray = [Windows.Graphics.Imaging.SoftwareBitmap]::Convert($bmp, [Windows.Graphics.Imaging.BitmapPixelFormat]::Gray8)
  $found = Await ($det.DetectFacesAsync($gray)) ([System.Collections.Generic.IList[Windows.Media.FaceAnalysis.DetectedFace]])
  foreach ($f in $found) { $faces += @{ x = $f.FaceBox.X; y = $f.FaceBox.Y; w = $f.FaceBox.Width; h = $f.FaceBox.Height } }
}
$stream.Dispose()
[System.IO.File]::WriteAllText($out, (ConvertTo-Json @{ lines = $lines; faces = $faces } -Compress -Depth 6), [System.Text.UTF8Encoding]::new($false))
"""

EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
PHONE = re.compile(r"(?:\+?\d[\d\s().-]{8,}\d)")
IBAN = re.compile(r"\bTR\s?\d{2}(?:\s?\d{4}){5}\s?\d{2}\b", re.I)
DIGITS = re.compile(r"\d[\d\s-]{9,22}\d")
KINDS = ("faces", "email", "phone", "tc", "iban", "card")


def tc_valid(s: str) -> bool:
    """TC kimlik algoritmasi: 11 hane, ilki 0 degil, 10. ve 11. hane kontrol basamagi."""
    if not re.fullmatch(r"[1-9]\d{10}", s):
        return False
    d = [int(c) for c in s]
    return (sum(d[0:9:2]) * 7 - sum(d[1:8:2])) % 10 == d[9] and sum(d[:10]) % 10 == d[10]


def luhn(s: str) -> bool:
    d = [int(c) for c in s][::-1]
    tot = sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])
    return 13 <= len(s) <= 19 and tot % 10 == 0


def find_sensitive(text: str, kinds: set[str]) -> list[tuple[int, int, str]]:
    """Satir metninde hassas parcalar: (baslangic, bitis, tur)."""
    spans: list[tuple[int, int, str]] = []
    if "email" in kinds:
        spans += [(m.start(), m.end(), "email") for m in EMAIL.finditer(text)]
    if "iban" in kinds:
        spans += [(m.start(), m.end(), "iban") for m in IBAN.finditer(text)]
    for m in DIGITS.finditer(text):
        if any(a <= m.start() < b for a, b, _ in spans):   # IBAN'in icindeki rakamlar
            continue
        raw = re.sub(r"\D", "", m.group())
        if "tc" in kinds and len(raw) == 11 and tc_valid(raw):
            spans.append((m.start(), m.end(), "tc"))
        elif "card" in kinds and luhn(raw):
            spans.append((m.start(), m.end(), "card"))
    if "phone" in kinds:
        for m in PHONE.finditer(text):
            raw = re.sub(r"\D", "", m.group())
            if any(a <= m.start() < b for a, b, _ in spans):
                continue
            tr_mobile = (len(raw) == 10 and raw[0] == "5") or (len(raw) == 11 and raw.startswith("05")) \
                or (len(raw) == 12 and raw.startswith("905")) or (len(raw) == 11 and raw.startswith("0") and raw[1] in "234")
            intl = m.group().strip().startswith("+") and 10 <= len(raw) <= 13
            if tr_mobile or intl:
                spans.append((m.start(), m.end(), "phone"))
    return spans


def _scan(path: str, faces: bool) -> dict[str, Any]:
    if os.name != "nt":
        return {"lines": [], "faces": []}
    tmp = tempfile.mkdtemp(prefix="kami_gizli_")
    ps1, out = os.path.join(tmp, "s.ps1"), os.path.join(tmp, "o.json")
    try:
        with open(ps1, "w", encoding="utf-8-sig") as f:
            f.write(_PS)
        subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", ps1,
                        path, out, "1" if faces else "0"], capture_output=True, timeout=60, creationflags=NO_WINDOW)
        with open(out, encoding="utf-8") as f:
            data = json.load(f)
        for k in ("lines", "faces"):
            v = data.get(k) or []
            data[k] = v if isinstance(v, list) else [v]
        return data
    except Exception as exc:
        log.warning("Gizlilik taramasi basarisiz: %s", exc)
        return {"lines": [], "faces": []}
    finally:
        for p in (ps1, out):
            try:
                os.remove(p)
            except OSError:
                pass
        try:
            os.rmdir(tmp)
        except OSError:
            pass


def regions(scan: dict[str, Any], kinds: set[str]) -> list[dict[str, Any]]:
    """OCR satirlari + yuz kutularindan bulaniklastirilacak dikdortgenler."""
    out: list[dict[str, Any]] = []
    for ln in scan.get("lines") or []:
        words = ln.get("words") or []
        if isinstance(words, dict):
            words = [words]
        text, pos = "", []
        for w in words:   # Windows OCR satir metni = kelimeler + bosluk: karakter konumundan kelimeye
            if text:
                text += " "
            pos.append((len(text), len(text) + len(w.get("t") or ""), w))
            text += w.get("t") or ""
        for a, b, kind in find_sensitive(text, kinds):
            hit = [w for s, e, w in pos if s < b and e > a]
            if hit:
                x0 = min(w["x"] for w in hit); y0 = min(w["y"] for w in hit)
                x1 = max(w["x"] + w["w"] for w in hit); y1 = max(w["y"] + w["h"] for w in hit)
                out.append({"kind": kind, "box": [x0, y0, x1, y1]})
    if "faces" in kinds:
        for f in scan.get("faces") or []:
            out.append({"kind": "face", "box": [f["x"], f["y"], f["x"] + f["w"], f["y"] + f["h"]]})
    return out


def shield_image(src: str, dst: str = "", kinds: list[str] | None = None, extra_boxes: list[list[float]] | None = None) -> dict[str, Any]:
    """Hassas bolgeleri pikselle + EXIF/GPS'i sil. Doner: {ok, path, found: {tur: adet}}."""
    p = Path(src)
    if not p.is_file():
        return {"ok": False, "error": "Gorsel bulunamadi"}
    ks = set(kinds or KINDS)
    scan = _scan(str(p), "faces" in ks)
    regs = regions(scan, ks) + [{"kind": "manual", "box": b} for b in (extra_boxes or [])]
    with Image.open(p) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
    W, H = im.size
    for r in regs:
        x0, y0, x1, y1 = r["box"]
        pad = 0.25 if r["kind"] == "face" else 0.15
        dw, dh = (x1 - x0) * pad, (y1 - y0) * pad
        box = (max(0, int(x0 - dw)), max(0, int(y0 - dh)), min(W, int(x1 + dw)), min(H, int(y1 + dh)))
        if box[2] - box[0] < 2 or box[3] - box[1] < 2:
            continue
        part = im.crop(box)
        k = max(6, min(part.size) // 6)   # kaba pikselleme (geri dondurulemez) + yumusatma
        part = part.resize((max(1, part.width // k), max(1, part.height // k)), Image.BILINEAR).resize(part.size, Image.NEAREST)
        im.paste(part.filter(ImageFilter.GaussianBlur(2)), box)
    out = Path(dst) if dst else p.with_name(f"{p.stem}_gizli{p.suffix if p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp') else '.png'}")
    fmt = {".jpg": "JPEG", ".jpeg": "JPEG", ".webp": "WEBP"}.get(out.suffix.lower(), "PNG")
    im.save(out, fmt, **({"quality": 95} if fmt in ("JPEG", "WEBP") else {}))   # exif verilmedi: konum dahil hepsi silinir
    found: dict[str, int] = {}
    for r in regs:
        found[r["kind"]] = found.get(r["kind"], 0) + 1
    return {"ok": True, "path": str(out), "found": found, "ocr": bool(scan.get("lines")), "regions": regs}
