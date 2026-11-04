"""Eklenti denetimi + testleri (Kami'yi acmadan):

    uv run python -m tools.eklenti_test <ad>          # tek eklenti
    uv run python -m tools.eklenti_test --hepsi       # tum eklentiler
    uv run python -m tools.eklenti_test <ad> --ag     # @pytest.mark.network testleri de (gercek ag)

Adimlar: 1) plugin.json semasi + desen ornekleri (Python), 2) yukleme (register hatasiz, ne kaydetti),
3) bulut saglayicinin can_handle'i ornek linklerle plugin.json ile tutarli mi, 4) plugins/<ad>/test_plugin.py (pytest).
Cikis kodu 0 = gecti.
"""
from __future__ import annotations

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PLUGINS = ROOT / "plugins"


class Loaded:
    """test_plugin.py'deki `plugin` fiksturu."""

    def __init__(self, info, registry) -> None:
        self.info = info
        self.registry = registry
        self.clouds = [o for k, o in info.objects if k == "clouds"]
        self.cloud = self.clouds[0] if self.clouds else None
        self.resolvers = [o for k, o in info.objects if k == "resolvers"]
        self.postprocessors = [o for k, o in info.objects if k == "postprocessors"]

    def matches(self, url: str) -> bool:
        """plugin.json desenleri VE (varsa) bulut saglayicinin can_handle'i ayni seyi demeli."""
        from app.core.plugin_api import match_patterns
        m = match_patterns(url, self.info.url_patterns)
        by_pat = bool(m and m[0] == "share")
        if self.cloud is not None:
            assert self.cloud.can_handle(url) == by_pat, f"can_handle ile plugin.json uyusmuyor: {url}"
        return by_pat


def load_one(pid: str):
    from app.core.events import EventBus
    from app.core.plugin_loader import PluginStore, load_plugins
    from app.core.settings import Settings
    tmp = Path(tempfile.mkdtemp(prefix="kami_pt_"))
    reg = load_plugins(PLUGINS, EventBus(), Settings(tmp / "s.json"), store=PluginStore(tmp / "plugins.json"))
    info = next((p for p in reg.plugins if p.id == pid), None)
    return info, reg


def check(pid: str, network: bool = False) -> bool:
    from app.core.plugin_loader import _read_meta, validate_meta
    folder = PLUGINS / pid
    print(f"== {pid}")
    if not (folder / "plugin.py").is_file():
        print("  X plugin.py yok")
        return False
    meta = _read_meta(folder)
    errs = validate_meta(meta, pid)
    if not (folder / "plugin.json").is_file():
        errs.append("plugin.json yok (zorunlu: ad, surum, url_patterns, settings)")
    for e in errs:
        print("  X plugin.json:", e)
    print(f"  {'OK' if not errs else 'X '} plugin.json ({len(meta.get('url_patterns') or [])} desen, "
          f"{len(meta.get('settings') or [])} ayar)")
    info, reg = load_one(pid)
    if info is None or info.error:
        print("  X yukleme:", info.error if info else "bulunamadi")
        return False
    lo = Loaded(info, reg)
    print(f"  OK yuklendi: bulut={info.clouds} cozucu={info.resolvers} son-islem={info.postprocessors}")
    ok = not errs
    for p in info.url_patterns:
        ex = p.get("examples") or {}
        for u in ex.get("match") or []:
            try:
                if not lo.matches(u):
                    print("  X eslesmedi:", u)
                    ok = False
            except AssertionError as exc:
                print("  X", exc)
                ok = False
        for u in ex.get("no_match") or []:
            try:
                if lo.matches(u):
                    print("  X eslesmemeliydi:", u)
                    ok = False
            except AssertionError as exc:
                print("  X", exc)
                ok = False
    tp = folder / "test_plugin.py"
    if tp.is_file():
        import pytest
        args = [str(tp), "-q", "-p", "tools.eklenti_pytest", "--rootdir", str(ROOT), "-o", "testpaths=",
                "-p", "no:cacheprovider"]
        if network:
            args.append("--ag")
        os_env_pid = {"KAMI_PLUGIN_ID": pid}
        import os
        os.environ.update(os_env_pid)
        rc = pytest.main(args)
        print(f"  {'OK' if rc in (0, 5) else 'X '} test_plugin.py (pytest kod {rc})")
        ok = ok and rc in (0, 5)
    else:
        print("  - test_plugin.py yok (onerilir)")
    print("  SONUC:", "GECTI" if ok else "KALDI")
    return ok


def main(argv: list[str]) -> int:
    sys.path.insert(0, str(ROOT))
    network = "--ag" in argv
    names = [a for a in argv if not a.startswith("--")]
    if "--hepsi" in argv:
        names = sorted(p.name for p in PLUGINS.iterdir() if p.is_dir() and not p.name.startswith(("_", ".")))
    if not names:
        print(__doc__)
        return 2
    results = [check(n, network) for n in names]
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
