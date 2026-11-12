"""main.py: 'if __name__ == "__main__"' blogundan SONRA tanim olmamali (1.1.1'de acilis cokmesi)."""
import ast
from pathlib import Path


def test_no_definitions_after_main_guard():
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8"))
    seen_guard = False
    for node in tree.body:
        if isinstance(node, ast.If) and "__main__" in ast.unparse(node.test):
            seen_guard = True
        elif seen_guard:
            assert not isinstance(node, (ast.FunctionDef, ast.ClassDef, ast.Assign)), f"__main__ sonrasi tanim: satir {node.lineno}"


def _direct_nodes(fn):
    """Fonksiyonun kendi govdesindeki dugumler (ic fonksiyon/lambda govdeleri haric: onlar sonra calisir)."""
    stack = list(fn.body)
    while stack:
        n = stack.pop()
        yield n
        for c in ast.iter_child_nodes(n):
            if not isinstance(c, (ast.FunctionDef, ast.AsyncFunctionDef, ast.Lambda, ast.ClassDef)):
                stack.append(c)


def test_local_import_not_used_before_it():
    """1.6.0 cokmesi: main() icinde 'from app.core import desktop' asagida, 'desktop.' yukarida kullanildi."""
    tree = ast.parse((Path(__file__).resolve().parents[1] / "app" / "main.py").read_text(encoding="utf-8"))
    for fn in [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]:
        nodes = list(_direct_nodes(fn))
        imports = {}
        for n in nodes:
            if isinstance(n, (ast.Import, ast.ImportFrom)):
                for a in n.names:
                    nm = (a.asname or a.name).split(".")[0]
                    imports[nm] = min(imports.get(nm, 10 ** 9), n.lineno)
        for n in nodes:
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load) and n.id in imports:
                assert n.lineno >= imports[n.id], f"{fn.name}: '{n.id}' satir {n.lineno}'da, yerel importu satir {imports[n.id]}'da"
