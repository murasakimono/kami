"""Yeni eklenti iskeleti: plugins/_sablon -> plugins/<ad>

    uv run python -m tools.yeni_eklenti <ad> ["Gorunen Ad"]

<ad>: kucuk harf/rakam/_ (ornek: ornek_site). Sonra plugin.json desenlerini + plugin.py list()'i doldur,
    uv run python -m tools.eklenti_test <ad>
ile dene. Rehber: docs/EKLENTI-REHBERI.md
"""
from __future__ import annotations

import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"


def make(pid: str, name: str = "") -> Path:
    from app.core.plugin_loader import ID_RE
    if not ID_RE.match(pid):
        raise SystemExit(f"Gecersiz ad: {pid!r} (kucuk harf ile baslar; harf/rakam/_; ornek: ornek_site)")
    dest = PLUGINS / pid
    if dest.exists():
        raise SystemExit(f"Zaten var: {dest}")
    name = name or pid.replace("_", " ").title()
    cls = "".join(w.capitalize() for w in pid.split("_")) or "Eklenti"
    shutil.copytree(PLUGINS / "_sablon", dest, ignore=shutil.ignore_patterns("__pycache__"))
    for f in dest.rglob("*"):
        if f.is_file() and f.suffix in (".py", ".json", ".md", ".html", ".js"):
            t = f.read_text(encoding="utf-8")
            f.write_text(t.replace("__ID__", pid).replace("__NAME__", name).replace("__CLASS__", cls),
                         encoding="utf-8", newline="\n")
    return dest


def main(argv: list[str]) -> int:
    if not argv:
        print(__doc__)
        return 2
    dest = make(argv[0], argv[1] if len(argv) > 1 else "")
    print(f"Olusturuldu: {dest}")
    print(f"Siradaki: plugin.json desenleri + plugin.py list() -> uv run python -m tools.eklenti_test {argv[0]}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
