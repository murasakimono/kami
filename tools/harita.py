"""Kami kod haritasi: her dosyanin sinif/fonksiyon listesi (satir numarasiyla) -> docs/HARITA.md.
Claude bir oturumda buyuk dosyalari bastan okumak yerine once bunu okur, sonra sadece gereken satir araligini acar.
Calistir: uv run --no-project python tools/harita.py
"""
import ast
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "docs" / "HARITA.md"
JS_FN = re.compile(r"^(?:async\s+)?function\s+([A-Za-z0-9_$]+)\s*\(|^(?:const|let)\s+([A-Z][A-Z0-9_]+)\s*=", re.M)


def py_items(p: Path) -> list[str]:
    try:
        tree = ast.parse(p.read_text(encoding="utf-8"))
    except Exception as e:
        return [f"(ayristirilamadi: {e})"]
    out = []
    for n in tree.body:
        if isinstance(n, ast.ClassDef):
            meths = [m.name for m in n.body if isinstance(m, (ast.FunctionDef, ast.AsyncFunctionDef)) and not m.name.startswith("__")]
            out.append(f"class {n.name} L{n.lineno}: " + ", ".join(meths))
        elif isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out.append(f"def {n.name} L{n.lineno}")
    return out


def js_items(p: Path) -> list[str]:
    txt = p.read_text(encoding="utf-8", errors="replace")
    names = []
    for m in JS_FN.finditer(txt):
        line = txt.count("\n", 0, m.start()) + 1
        names.append(f"{m.group(1) or m.group(2)} L{line}")
    return [", ".join(names)] if names else []


def main() -> None:
    lines = ["# Kami kod haritasi (otomatik: tools/harita.py)", ""]
    groups = [("Python", sorted((ROOT / "app").rglob("*.py")), py_items),
              ("Arayuz JS", sorted((ROOT / "app" / "ui" / "web").glob("*.js")) + sorted((ROOT / "app" / "ui" / "web" / "eye").glob("*.js")), js_items),
              ("Eklenti JS", sorted((ROOT / "extension").rglob("*.js")) if (ROOT / "extension").exists() else [], js_items),
              ("Eklentiler (plugins)", sorted((ROOT / "plugins").rglob("*.py")) if (ROOT / "plugins").exists() else [], py_items)]
    for title, files, fn in groups:
        lines += [f"## {title}", ""]
        for p in files:
            if "__pycache__" in p.parts or p.name == "__init__.py":
                continue
            n = sum(1 for _ in p.open(encoding="utf-8", errors="replace"))
            items = fn(p)
            lines.append(f"- **{p.relative_to(ROOT).as_posix()}** ({n} satir)")
            lines += [f"  - {i}" for i in items]
        lines.append("")
    OUT.parent.mkdir(exist_ok=True)
    OUT.write_text("\n".join(lines), encoding="utf-8")
    print(OUT, len(lines), "satir")


if __name__ == "__main__":
    main()
