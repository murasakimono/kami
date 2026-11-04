"""Bulut eklentileri (Asama 3): link tanima, listeleme (ag sahte), alt klasor yapisi, MEGA kriptosu."""
from __future__ import annotations

import base64
import json
import os
import sys

import pytest
from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from app import paths
from app.core.cloud import CloudFile, CloudListing, CloudProvider, CloudService
from app.core.events import EventBus
from app.core.manager import DownloadManager
from app.core.plugin_loader import load_plugins
from app.core.queue_store import DownloadStore
from app.core.settings import Settings
from tests.test_manager_retry import FakeEngine


@pytest.fixture(scope="module")
def registry(tmp_path_factory):
    s = Settings(tmp_path_factory.mktemp("s") / "s.json")
    reg = load_plugins(paths.PLUGINS_DIR, EventBus(), s)
    assert not [p.error for p in reg.plugins if p.error]
    return reg


def _which(reg, url):
    svc = CloudService(reg.clouds)
    p = svc.provider_for(url)
    return p.name if p else None


@pytest.mark.parametrize("url,name", [
    ("https://disk.yandex.ru/d/4Z0GsDwfR4gkPA", "yandex_disk"),
    ("https://yadi.sk/i/t_pNaarK8UJ-bQ", "yandex_disk"),
    ("https://disk.yandex.com.tr/d/abc", "yandex_disk"),
    ("https://cloud.mail.ru/public/C76Y/rumhiAWE3", "mailru"),
    ("https://pixeldrain.com/u/VFjemoqC", "pixeldrain"),
    ("https://pixeldrain.com/l/abcd", "pixeldrain"),
    ("https://pixeldrain.com/d/abcd/alt", "pixeldrain"),
    ("https://www.dropbox.com/scl/fo/abc/def?rlkey=x&dl=0", "dropbox"),
    ("https://www.dropbox.com/s/abc/file.zip?dl=0", "dropbox"),
    ("https://drive.google.com/drive/folders/15uNXeRBIhVvZJIhL4yTw4IsStMhUaaxl", "gdrive"),
    ("https://drive.google.com/file/d/1NEVRByyKxcUCdyqLU4UCYoHaMaOx4GUE/view", "gdrive"),
    ("https://drive.google.com/open?id=1NEVRByyKxcUCdyqLU4UCYoHaMaOx4GUE", "gdrive"),
    ("https://www.mediafire.com/folder/xqub019s2e2l1/no_more_slimes", "mediafire"),
    ("https://www.mediafire.com/file/v91fqemfiau67jr/a.txt/file", "mediafire"),
    ("https://mega.nz/folder/bNkA3CrZ#1x5qLYhi9sKLP4qs5Up6Qg", "mega"),
    ("https://mega.nz/file/MAkg2Iab#bc9Y2U6d93IlRRKVYpcC9hLZjS4G278OPdH6nTFPDNQ", "mega"),
    ("https://mega.nz/#F!abcdefgh!1x5qLYhi9sKLP4qs5Up6Qg", "mega"),
    # tanimamasi gerekenler
    ("https://disk.yandex.ru/client/disk", None),
    ("https://drive.google.com/drive/my-drive", None),
    ("https://mega.nz/folder/abc", None),          # anahtarsiz
    ("https://www.mediafire.com/", None),
    ("https://www.youtube.com/watch?v=x", None),
    ("https://pixeldrain.com/", None),
])
def test_can_handle(registry, url, name):
    assert _which(registry, url) == name


def _plugin_module(name):
    return sys.modules[f"kami_plugins.{name}"]


def test_yandex_listing_recurses(registry, monkeypatch):
    tree = {
        "/": {"type": "dir", "name": "Kok", "_embedded": {"total": 2, "items": [
            {"type": "file", "name": "a.txt", "path": "/a.txt", "size": 3, "file": "https://dl/a"},
            {"type": "dir", "name": "Alt", "path": "/Alt"}]}},
        "/Alt": {"type": "dir", "name": "Alt", "_embedded": {"total": 1, "items": [
            {"type": "file", "name": "b.bin", "path": "/Alt/b.bin", "size": 5}]}},
    }
    mod = _plugin_module("yandex_disk")
    calls = []

    def fake(s, url, params=None, **kw):
        calls.append((url, params.get("path")))
        if url.endswith("/download"):
            return {"href": "https://dl/b"}
        return tree[params["path"]]

    monkeypatch.setattr(mod, "get_json", fake)
    svc = CloudService(registry.clouds)
    token, listing = svc.list("https://disk.yandex.ru/d/XYZ")
    assert listing.title == "Kok" and listing.is_folder
    assert sorted((f.path, f.size) for f in listing.files) == [("Alt/b.bin", 5), ("a.txt", 3)]
    p, _ = svc.get(token)
    b = next(f for f in listing.files if f.name == "b.bin")
    assert p.file_request(listing, b)[0] == "https://dl/b"   # "file" alani yoksa indirme ucu


class _FakeCloud(CloudProvider):
    name = "fake"
    hosts = ("fake.test",)

    def list(self, url):
        return CloudListing(self.name, "Paylasim: 1", [
            CloudFile("kok.txt", 10, url="http://fake.test/1"),
            CloudFile("Alt/Ic:ice/derin.bin", 20, url="http://fake.test/2"),
            CloudFile("Alt/bozuk.bin", 1, url=""),   # linki cozulemeyen dosya digerlerini durdurmasin
        ])

    def file_request(self, listing, f):
        u, h, o = super().file_request(listing, f)
        return u, {"Cookie": "a=b"}, {"x": 1}


def test_add_cloud_keeps_folder_structure(tmp_path):
    s = Settings(tmp_path / "s.json")
    s.set("download_dir", str(tmp_path / "dl"))
    eng = FakeEngine(0)
    from app.core.plugin_api import PluginRegistry
    reg = PluginRegistry()
    reg.clouds.append(_FakeCloud())
    mgr = DownloadManager(DownloadStore(tmp_path / "k.db"), eng, EventBus(), s, reg, prober=None)
    token, listing = mgr.cloud.list("https://fake.test/share")
    added = mgr.add_cloud(token, [0, 1, 2])
    assert len(added) == 2
    root = os.path.join(str(tmp_path / "dl"), "Paylasim_ 1")
    by_name = {d.filename: d for d in added}
    assert by_name["kok.txt"].directory == root
    assert by_name["derin.bin"].directory == os.path.join(root, "Alt", "Ic_ice")
    d = mgr.store.get(by_name["derin.bin"].id)
    assert d.source == "plugin:fake" and d.headers == {"Cookie": "a=b"} and d.options == {"x": 1}
    assert d.size == 20


# ---------- MEGA ----------
def _b64e(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def test_mega_parse_link(registry):
    mega = _plugin_module("mega")
    k16 = os.urandom(16)
    assert mega.parse_link(f"https://mega.nz/folder/AbCd1234#{_b64e(k16)}") == ("folder", "AbCd1234", k16, "")
    assert mega.parse_link(f"https://mega.nz/folder/AbCd1234#{_b64e(k16)}/folder/SubF1234")[3] == "SubF1234"
    assert mega.parse_link(f"https://mega.nz/#F!AbCd1234!{_b64e(k16)}")[:3] == ("folder", "AbCd1234", k16)


def _mega_encrypt(plain: bytes, aes_key: bytes, nonce: bytes) -> tuple[bytes, bytes]:
    """Test icin MEGA tarzi sifreleme + meta-mac (bagimsiz yazilmis CBC-MAC)."""
    ctr = AES.new(aes_key, AES.MODE_CTR, counter=Counter.new(64, prefix=nonce, initial_value=0))
    enc = ctr.encrypt(plain)
    ecb = AES.new(aes_key, AES.MODE_ECB)
    mac = b"\0" * 16
    pos, step = 0, 128 * 1024
    while pos < len(plain):
        chunk = plain[pos:pos + step]
        cmac = nonce + nonce
        for i in range(0, len(chunk), 16):
            block = chunk[i:i + 16].ljust(16, b"\0")
            cmac = ecb.encrypt(bytes(a ^ b for a, b in zip(cmac, block)))
        mac = ecb.encrypt(bytes(a ^ b for a, b in zip(mac, cmac)))
        pos += len(chunk)
        if step < 1024 * 1024:
            step += 128 * 1024
    w = [int.from_bytes(mac[i:i + 4], "big") for i in range(0, 16, 4)]
    meta = (w[0] ^ w[1]).to_bytes(4, "big") + (w[2] ^ w[3]).to_bytes(4, "big")
    return enc, meta


@pytest.mark.parametrize("size", [0, 5, 128 * 1024, 3 * 1024 * 1024 + 7])
def test_mega_decrypt_roundtrip(registry, tmp_path, size):
    mega = _plugin_module("mega")
    plain = os.urandom(size)
    aes_key, nonce = os.urandom(16), os.urandom(8)
    enc, meta = _mega_encrypt(plain, aes_key, nonce)
    # 32 baytlik dosya anahtari: k[0:16] ^ k[16:32] = aes_key, k[16:24] = nonce, k[24:32] = meta-mac
    second = nonce + meta
    first = bytes(a ^ b for a, b in zip(aes_key, second))
    path = tmp_path / "f.bin"
    path.write_bytes(enc)
    assert mega.decrypt_file(str(path), (first + second).hex()) is True
    assert path.read_bytes() == plain
    assert not (tmp_path / "f.bin.megadec").exists()


def test_mega_attr_and_listing(registry, monkeypatch):
    mega = _plugin_module("mega")
    share = os.urandom(16)

    def enc_attr(name, key):
        raw = b"MEGA" + json.dumps({"n": name}).encode()
        raw += b"\0" * (-len(raw) % 16)
        return _b64e(AES.new(key, AES.MODE_CBC, iv=b"\0" * 16).encrypt(raw))

    def enc_key(k):
        return _b64e(AES.new(share, AES.MODE_ECB).encrypt(k))

    root_k, sub_k, file_k = os.urandom(16), os.urandom(16), os.urandom(32)
    file_aes = bytes(a ^ b for a, b in zip(file_k[:16], file_k[16:]))
    nodes = [
        {"h": "ROOT", "p": "OWNR", "t": 1, "a": enc_attr("Kok", root_k), "k": f"ROOT:{enc_key(root_k)}"},
        {"h": "SUB1", "p": "ROOT", "t": 1, "a": enc_attr("Alt", sub_k), "k": f"ROOT:{enc_key(sub_k)}"},
        {"h": "FIL1", "p": "SUB1", "t": 0, "s": 42, "a": enc_attr("x.mp4", file_aes), "k": f"ROOT:{enc_key(file_k)}"},
    ]
    monkeypatch.setattr(mega._Api, "call", lambda self, *c: [{"f": nodes}])
    listing = mega.Mega().list(f"https://mega.nz/folder/ROOT#{_b64e(share)}")
    assert listing.title == "Kok"
    assert [(f.path, f.size) for f in listing.files] == [("Alt/x.mp4", 42)]
    assert listing.files[0].ref["key"] == file_k.hex()
