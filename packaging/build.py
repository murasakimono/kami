"""Kami kurulum paketi:  uv run python packaging/build.py [--no-installer] [--no-scan]

1) packaging/version_info.txt (exe ozellikleri) 2) PyInstaller onedir (packaging/kami.spec)
3) bin/: aria2c, ffmpeg, ffprobe, deno (YouTube JS cozucu), uv (Whisper/UVR araclari ortami icin), fpcalc (varsa)
4) plugins/ (+ _sablon), extension/ (ozel anahtar .pem HARIC), docs/
5) Inno Setup -> build_out/Kami-Setup-<surum>.exe   6) Windows Defender taramasi (yanlis alarm kontrolu)
Whisper/UVR paketleri ve modelleri kuruluma GIRMEZ.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "build_out"
DIST = OUT / "dist" / "Kami"
ISCC = [Path.home() / "AppData/Local/Programs/Inno Setup 6/ISCC.exe", Path("C:/Program Files (x86)/Inno Setup 6/ISCC.exe")]


def version() -> str:
    m = re.search(r'APP_VERSION = "([\d.]+)"', (ROOT / "app/core/extras.py").read_text(encoding="utf-8"))
    return m.group(1)


def sync_extension_version(v: str) -> None:
    """Brave'deki eklenti surumu uygulamayla ayni olsun (manifest elle unutuluyordu)."""
    mf = ROOT / "extension" / "manifest.json"
    t = mf.read_text(encoding="utf-8")
    t2 = re.sub(r'"version":\s*"[\d.]+"', f'"version": "{v}"', t, count=1)
    if t2 != t:
        mf.write_text(t2, encoding="utf-8")


def write_version_info(v: str) -> None:
    n = (tuple(int(x) for x in v.split(".")) + (0, 0, 0))[:4]
    (ROOT / "packaging/version_info.txt").write_text(f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={n}, prodvers={n}, mask=0x3f, flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0),
  kids=[StringFileInfo([StringTable('041F04B0', [
    StringStruct('CompanyName', 'Metehan'), StringStruct('FileDescription', 'Kami Download Manager'),
    StringStruct('FileVersion', '{v}'), StringStruct('InternalName', 'Kami'),
    StringStruct('LegalCopyright', 'Kisisel kullanim'), StringStruct('OriginalFilename', 'Kami.exe'),
    StringStruct('ProductName', 'Kami (KDM)'), StringStruct('ProductVersion', '{v}')])]),
    VarFileInfo([VarStruct('Translation', [1055, 1200])])]
)
""", encoding="utf-8")


def which_real(name: str) -> Path | None:
    """winget 'Links' kisayolu yerine gercek exe (kopyalanabilir)."""
    p = shutil.which(name)
    if not p:
        return None
    rp = Path(p).resolve()
    if rp.suffix.lower() != ".exe" and rp.with_suffix(".exe").is_file():
        rp = rp.with_suffix(".exe")
    return rp if rp.is_file() else None


def copy_bins() -> list[str]:
    b = DIST / "bin"
    b.mkdir(parents=True, exist_ok=True)
    got = []
    for src in [ROOT / "bin/aria2c.exe", ROOT / "bin/fpcalc.exe"]:
        if src.is_file():
            shutil.copy2(src, b / src.name)
            got.append(src.name)
    for name in ("ffmpeg", "ffprobe", "deno", "uv"):
        local = ROOT / "bin" / f"{name}.exe"
        src = local if local.is_file() else which_real(name)
        if src:
            shutil.copy2(src, b / f"{name}.exe")
            got.append(f"{name}.exe")
    if "aria2c.exe" not in got or "ffmpeg.exe" not in got:
        raise SystemExit(f"Eksik zorunlu ikili: {got}")
    return got


def copy_tree(src: Path, dst: Path, ignore=()) -> None:
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", *ignore))


def main(argv: list[str]) -> int:
    v = version()
    print(f"== Kami {v}")
    write_version_info(v)
    sync_extension_version(v)
    r = subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", "--distpath", str(OUT / "dist"),
                        "--workpath", str(OUT / "work"), str(ROOT / "packaging/kami.spec")], cwd=ROOT)
    if r.returncode:
        return r.returncode
    print("bin:", copy_bins())
    copy_tree(ROOT / "plugins", DIST / "plugins")
    copy_tree(ROOT / "extension", DIST / "extension", ignore=("*.pem",))
    copy_tree(ROOT / "docs", DIST / "docs")
    assert not list((DIST / "extension").glob("*.pem")), "ozel anahtar pakete girmemeli"
    size = sum(f.stat().st_size for f in DIST.rglob("*") if f.is_file()) / 1e6
    print(f"dist: {DIST} ({size:.0f} MB)")
    if "--no-installer" not in argv:
        iscc = next((p for p in ISCC if p.is_file()), None)
        if not iscc:
            raise SystemExit("Inno Setup (ISCC.exe) yok: winget install JRSoftware.InnoSetup")
        r = subprocess.run([str(iscc), f"/DAppVersion={v}", f"/DDistDir={DIST}", f"/DOutDir={OUT}",
                            str(ROOT / "packaging/kami.iss")], cwd=ROOT)
        if r.returncode:
            return r.returncode
        setup = OUT / f"Kami-Setup-{v}.exe"
        print(f"kurulum: {setup} ({setup.stat().st_size / 1e6:.0f} MB)")
    if "--no-scan" not in argv:
        scan(OUT)
    return 0


def scan(path: Path) -> None:
    mp = Path("C:/Program Files/Windows Defender/MpCmdRun.exe")
    if not mp.is_file():
        print("Defender bulunamadi, tarama atlandi")
        return
    r = subprocess.run([str(mp), "-Scan", "-ScanType", "3", "-File", str(path), "-DisableRemediation"],
                       capture_output=True, text=True)
    print("Defender:", (r.stdout.strip().splitlines() or ["?"])[-1], f"(kod {r.returncode}; 0 = tehdit yok)")


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
