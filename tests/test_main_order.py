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
