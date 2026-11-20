"""Kami: JS -> Python köprü yüzey doğrulaması.

'api.foo(...)' / 'pywebview.api.foo(...)' çağrılarının Api (ve StudioMixin)
üzerinde bir karşılığı olmalı. Tek taraflı rename/typo (ör. music_lrc_whisper ->
music_whisper_lrc) burada test zamanında yakalanır; yalnızca kullanıcı butona
tıklayınca patlamaz.
"""
from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API_PY = ROOT / "app" / "ui" / "api.py"
STUDIO_PY = ROOT / "app" / "ui" / "api_studio.py"
WEB = ROOT / "app" / "ui" / "web"

# JS tarafında bilerek köprü OLMAYAN 'api' (yerel değişken) metotları.
# Böyle bir ad çıkarsa buraya gerekçesiyle ekle.
ALLOWLIST: set[str] = set()

# Köprü çağrısı: pywebview.api.X(...) / window.pywebview.api.X(...) / api.X(...).
# 'api' yalnızca nokta/kelime karakteri ile başlamadığında eşleşir (x.api sahte eşleşmesini önler).
_CALL = re.compile(r"(?:pywebview\.api|(?<![\w.])api)\.([A-Za-z_]\w*)\s*\(")
_METHOD = re.compile(r"^ {4}(?:async )?def ([A-Za-z_]\w*)\s*\(", re.M)


def _py_methods(text: str) -> set[str]:
    return {m.group(1) for m in _METHOD.finditer(text)}


def test_js_bridge_surface_matches_api():
    py = _py_methods(API_PY.read_text(encoding="utf-8"))
    py |= _py_methods(STUDIO_PY.read_text(encoding="utf-8"))
    assert len(py) > 400, f"Api yüzeyi beklenenden küçük: {len(py)}"

    called: dict[str, list[str]] = {}
    for f in sorted(WEB.rglob("*")):
        if f.suffix not in (".js", ".html") or "vendor" in f.parts:
            continue
        text = f.read_text(encoding="utf-8", errors="replace")
        for m in _CALL.finditer(text):
            called.setdefault(m.group(1), []).append(str(f.relative_to(ROOT)))

    assert len(called) > 100, f"Köprü çağrı taraması beklenenden az buldu: {len(called)}"

    missing = sorted(set(called) - py - ALLOWLIST)
    assert not missing, (
        "Şu JS köprü çağrıları Api'de yok (rename/typo olabilir):\n"
        + "\n".join(f"  {n}  ->  {', '.join(called[n][:3])}" for n in missing)
    )
