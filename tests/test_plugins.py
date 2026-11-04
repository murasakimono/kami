"""Eklenti (addon) sistemi: plugin.json denetimi, ac/kapat, yeniden yukle, ayar semasi, desenlerin tarayiciya gidisi."""
import json
from pathlib import Path

from app.core.events import EventBus
from app.core.plugin_api import match_patterns
from app.core.plugin_loader import PluginStore, load_plugins, reload_plugin, set_enabled, validate_meta
from app.core.settings import Settings

ROOT = Path(__file__).resolve().parent.parent

PLUGIN_PY = '''
from app.core.cloud import CloudListing, CloudProvider
class P(CloudProvider):
    name = "deneme"
    def __init__(self, ctx): self.ctx = ctx
    def list(self, url): return CloudListing(self.name, VERSION + ":" + str(self.ctx.setting("adet")), [])
VERSION = "v1"
def register(ctx): ctx.register_cloud(P(ctx))
'''
META = {"name": "Deneme", "version": "1.0.0", "kinds": ["cloud"],
        "url_patterns": [{"name": "Deneme", "host": r"(^|\.)deneme\.test$", "share": r"^/s/\w+",
                          "examples": {"match": ["https://deneme.test/s/abc"], "no_match": ["https://deneme.test/x"]}}],
        "settings": [{"key": "adet", "type": "int", "default": 3, "min": 1, "max": 9, "label": {"tr": "Adet"}},
                     {"key": "anahtar", "type": "secret", "label": {"tr": "Anahtar"}}]}


def make(tmp_path):
    d = tmp_path / "plugins" / "deneme"
    d.mkdir(parents=True)
    (d / "plugin.py").write_text(PLUGIN_PY, encoding="utf-8")
    (d / "plugin.json").write_text(json.dumps(META), encoding="utf-8")
    store = PluginStore(tmp_path / "data" / "plugins.json")
    reg = load_plugins(tmp_path / "plugins", EventBus(), Settings(tmp_path / "s.json"), store=store)
    return d, store, reg


def test_validate_meta():
    assert validate_meta(META, "deneme") == []
    bad = {"name": "X", "version": "1", "kinds": ["uzay"],
           "url_patterns": [{"host": "x", "share": "(", "examples": {}}, {"name": "y"}],
           "settings": [{"key": "a", "type": "renk", "label": "A"}, {"key": "a", "type": "choice", "label": "B"}]}
    errs = " | ".join(validate_meta(bad, "Kotu-Ad"))
    for frag in ("klasor adi", "1.2.3", "kind: uzay", "gecersiz regex", "'host' ve 'share'", "type renk",
                 "tekrar eden", "choices"):
        assert frag in errs, frag
    meta = json.loads(json.dumps(META))
    meta["url_patterns"][0]["examples"]["match"].append("https://deneme.test/baska")
    assert any("ornek eslesmedi" in e for e in validate_meta(meta, "deneme"))


def test_patterns_semantics():
    pats = META["url_patterns"]
    assert match_patterns("https://www.deneme.test/s/abc?x=1", pats) == ("share", "Deneme")
    assert match_patterns("https://deneme.test/x", pats) is None
    assert match_patterns("ftp://deneme.test/s/abc", pats) is None


def test_enable_disable_reload_and_settings(tmp_path):
    d, store, reg = make(tmp_path)
    info = reg.plugins[0]
    prov = reg.clouds[0]
    assert prov.can_handle("https://deneme.test/s/abc") and not prov.can_handle("https://deneme.test/x")
    assert prov.list("u").title == "v1:3"                       # varsayilan ayar
    store.set_value("deneme", "adet", 5)
    assert prov.list("u").title == "v1:5"
    assert reg.url_patterns() == [{"name": "Deneme", "host": META["url_patterns"][0]["host"],
                                   "share": r"^/s/\w+", "plugin": "deneme"}]   # examples gitmez
    set_enabled(reg, "deneme", False)
    assert reg.clouds == [] and reg.url_patterns() == [] and not info.enabled
    assert PluginStore(tmp_path / "data" / "plugins.json").is_enabled("deneme", True) is False   # kalici
    set_enabled(reg, "deneme", True)
    assert len(reg.clouds) == 1
    (d / "plugin.py").write_text(PLUGIN_PY.replace('"v1"', '"v2"'), encoding="utf-8")
    reload_plugin(reg, "deneme")
    assert len(reg.clouds) == 1 and reg.clouds[0].list("u").title == "v2:5"
    (d / "plugin.py").write_text("def register(ctx): raise RuntimeError('bozuk')", encoding="utf-8")
    reload_plugin(reg, "deneme")
    assert reg.clouds == [] and "bozuk" in info.error            # bozuk eklenti Kami'yi dusurmez


def test_api_plugin_settings_and_ping(tmp_path, monkeypatch):
    from app.core.debrid import TokenStore
    from app.ui.api import Api
    d, store, reg = make(tmp_path)
    saved = {}
    monkeypatch.setattr(TokenStore, "save", lambda self, v: saved.__setitem__(self.path.name, v))
    monkeypatch.setattr(TokenStore, "load", lambda self: saved.get(self.path.name, ""))

    class M:
        registry = reg
        settings = Settings(tmp_path / "s2.json")
    api = Api.__new__(Api)
    api._registry = reg
    p = api.plugins()[0]
    assert p["id"] == "deneme" and p["sites"] == ["Deneme"]
    f = {x["key"]: x for x in p["settings"]}
    assert f["adet"]["value"] == 3 and f["anahtar"]["has_value"] is False and "value" not in f["anahtar"]
    assert api.plugin_set("deneme", "adet", 50) == {"ok": True, "value": 9}          # max'a kirpilir
    assert api.plugin_set("deneme", "yok", 1)["ok"] is False
    assert api.plugin_set("deneme", "anahtar", " gizli ")["ok"] and saved["deneme.anahtar.bin"] == "gizli"
    assert api.plugins()[0]["settings"][1]["has_value"] is True
    assert api.plugin_set_enabled("deneme", False)["ok"] and api.plugins()[0]["enabled"] is False
    # kopru ping'i desenleri tasir (tarayici eklentisi cloud_sites.js'i buradan gunceller)
    from app.core.bridge_server import BridgeServer
    srv = BridgeServer.__new__(BridgeServer)
    srv.manager = M()
    api.plugin_set_enabled("deneme", True)
    code, res = srv.handle("/v1/ping", {})
    assert code == 200 and res["sites"][0]["name"] == "Deneme"


def test_real_plugins_valid_and_consistent():
    """Mevcut bulut eklentileri: plugin.json gecerli, ornekler hem desenle hem can_handle ile tutarli."""
    import sys
    sys.path.insert(0, str(ROOT))
    from tools.eklenti_test import Loaded, load_one
    from app.core.plugin_loader import _read_meta
    for folder in sorted((ROOT / "plugins").iterdir()):
        if not folder.is_dir() or folder.name.startswith("_"):
            continue
        assert validate_meta(_read_meta(folder), folder.name) == [], folder.name
        info, reg = load_one(folder.name)
        lo = Loaded(info, reg)
        for pat in info.url_patterns:
            for u in pat["examples"]["match"]:
                assert lo.matches(u), u
            for u in pat["examples"].get("no_match", []):
                assert not lo.matches(u), u
