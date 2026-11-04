"""MEGA herkese acik dosya/klasor linkleri (anahtar linkin # kisminda).

Dosyalar sunucuda AES-128-CTR ile sifreli durur: aria2 sifreli halini cok baglantiyla indirir,
bitince MegaDecrypt son islemi dosyayi yerinde cozer (CTR: bayt konumu korunur, devam ettirme bozulmaz)
ve MEGA'nin CBC-MAC degeriyle dogrular.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import random
import re
import struct
import threading
from urllib.parse import urlparse

from Cryptodome.Cipher import AES
from Cryptodome.Util import Counter

from app.core.cloud import CloudError, CloudFile, CloudListing, CloudProvider, join, session
from app.core.plugin_api import PostProcessor

log = logging.getLogger(__name__)
API = "https://g.api.mega.co.nz/cs"
_ERRORS = {-2: "cloud_failed", -9: "cloud_not_found", -11: "cloud_denied", -16: "cloud_denied",
           -17: "cloud_quota", -18: "cloud_failed", -6: "cloud_quota", -4: "cloud_quota"}


# ---------- kripto yardimcilari ----------
def b64d(s: str) -> bytes:
    s = s.replace("-", "+").replace("_", "/").replace(",", "")
    return base64.b64decode(s + "=" * (-len(s) % 4))


def _xor(a: bytes, b: bytes) -> bytes:
    return bytes(x ^ y for x, y in zip(a, b))


def unpack_file_key(k: bytes) -> tuple[bytes, bytes, bytes]:
    """32 baytlik dosya anahtari -> (aes anahtari, 8 bayt nonce, 8 bayt meta-mac)."""
    return _xor(k[:16], k[16:32]), k[16:24], k[24:32]


def decrypt_attr(data: bytes, key: bytes) -> dict:
    raw = AES.new(key, AES.MODE_CBC, iv=b"\0" * 16).decrypt(data).rstrip(b"\0")
    if not raw.startswith(b"MEGA{"):
        return {}
    try:
        return json.loads(raw[4:].decode("utf-8", "replace"))
    except ValueError:
        return {}


def parse_link(url: str) -> tuple[str, str, bytes, str]:
    """-> (folder|file, handle, anahtar, alt klasor handle'i)"""
    p = urlparse(url)
    frag = p.fragment
    m = re.match(r"^/(folder|file)/([\w-]+)$", p.path)
    if m and frag:
        key, _, rest = frag.partition("/")
        sub = re.search(r"folder/([\w-]+)", rest)
        return m.group(1), m.group(2), b64d(key), sub.group(1) if sub else ""
    m = re.match(r"^(F?)!([\w-]+)!([\w,-]+)", frag)   # eski bicim: #!h!k / #F!h!k
    if m:
        return ("folder" if m.group(1) else "file"), m.group(2), b64d(m.group(3)), ""
    raise CloudError("cloud_unsupported", url)


class _Api:
    def __init__(self, folder: str = "") -> None:
        self.s = session()
        self.seq = random.randint(0, 0xFFFFFFFF)
        self.folder = folder

    def call(self, *cmds: dict) -> list:
        self.seq += 1
        params = {"id": self.seq}
        if self.folder:
            params["n"] = self.folder
        r = self.s.post(API, params=params, data=json.dumps(list(cmds)), timeout=30)
        r.raise_for_status()
        data = r.json()
        if isinstance(data, int):
            raise CloudError(_ERRORS.get(data, "cloud_failed"), f"MEGA {data}")
        for item in data:
            if isinstance(item, int) and item < 0:
                raise CloudError(_ERRORS.get(item, "cloud_failed"), f"MEGA {item}")
        return data


# ---------- saglayici ----------
class Mega(CloudProvider):
    name = "mega"
    hosts = ("mega.nz", "mega.co.nz", "mega.io")

    def can_handle(self, url: str) -> bool:
        if not super().can_handle(url):
            return False
        try:
            parse_link(url)
            return True
        except (CloudError, ValueError):   # ValueError: bozuk base64 anahtar
            return False

    def list(self, url: str) -> CloudListing:
        kind, handle, key, sub = parse_link(url)
        if kind == "file":
            if len(key) != 32:
                raise CloudError("cloud_failed", "anahtar")
            info = _Api().call({"a": "g", "p": handle})[0]
            aes_key, _, _ = unpack_file_key(key)
            name = decrypt_attr(b64d(info.get("at", "")), aes_key).get("n") or handle
            f = CloudFile(name, int(info.get("s") or 0), ref={"p": handle, "key": key.hex()})
            return CloudListing(self.name, name, [f], is_folder=False)

        if len(key) != 16:
            raise CloudError("cloud_failed", "anahtar")
        nodes = _Api(handle).call({"a": "f", "c": 1, "ca": 1, "r": 1})[0].get("f") or []
        info: dict[str, dict] = {}
        for n in nodes:
            k = n.get("k") or ""
            enc = k.split("/")[0].split(":")[-1] if k else ""
            if not enc:
                continue
            try:
                nk = AES.new(key, AES.MODE_ECB).decrypt(b64d(enc))
            except ValueError:
                continue
            if n.get("t") == 0:
                if len(nk) != 32:
                    continue
                aes_key = unpack_file_key(nk)[0]
            elif n.get("t") == 1:
                aes_key = nk[:16]
            else:
                continue
            name = decrypt_attr(b64d(n.get("a", "")), aes_key).get("n") or n["h"]
            info[n["h"]] = {"t": n["t"], "p": n.get("p", ""), "name": name, "s": int(n.get("s") or 0), "k": nk}
        roots = [h for h, v in info.items() if v["t"] == 1 and v["p"] not in info]
        start = sub if sub in info else (roots[0] if roots else "")
        if not start:
            raise CloudError("cloud_empty", url)

        def rel_path(h: str) -> str | None:
            parts = []
            cur = info[h]["p"]
            while cur and cur != start:
                if cur not in info:
                    return None   # baska alt agacta
                parts.append(info[cur]["name"])
                cur = info[cur]["p"]
            return "/".join(reversed(parts)) if cur == start else None

        files = []
        for h, v in info.items():
            if v["t"] != 0:
                continue
            rel = rel_path(h)
            if rel is None:
                continue
            files.append(CloudFile(join(rel, v["name"]), v["s"], ref={"n": h, "key": v["k"].hex()}))
        return CloudListing(self.name, info[start]["name"], files, ctx={"folder": handle})

    def file_request(self, listing: CloudListing, f: CloudFile):
        ref = f.ref
        api = _Api(listing.ctx.get("folder", ""))
        cmd = {"a": "g", "g": 1, "ssl": 2}
        cmd.update({"n": ref["n"]} if "n" in ref else {"p": ref["p"]})
        res = api.call(cmd)[0]
        url = res.get("g")
        if isinstance(url, list):
            url = url[0] if url else ""
        if not url:
            raise CloudError(_ERRORS.get(res.get("e"), "cloud_failed") if res.get("e") else "cloud_failed", f.path)
        return url, {}, {"mega_key": ref["key"]}


# ---------- son islem: sifre cozme ----------
CHUNK = 4 * 1024 * 1024


def _mac_chunks(size: int):
    """MEGA parca sinirlari: 128K, 256K, ... 1M, sonra hep 1M."""
    pos, step = 0, 128 * 1024
    while pos < size:
        n = min(step, size - pos)
        yield pos, n
        pos += n
        if step < 1024 * 1024:
            step += 128 * 1024


def decrypt_file(path: str, key_hex: str) -> bool:
    """Dosyayi yerinde cozer; MAC tutarsa True. (Gecici .megadec dosyasina yazar, sonra degistirir.)"""
    k = bytes.fromhex(key_hex)
    aes_key, nonce, meta_mac = unpack_file_key(k)
    ctr = AES.new(aes_key, AES.MODE_CTR, counter=Counter.new(64, prefix=nonce, initial_value=0))
    ecb = AES.new(aes_key, AES.MODE_ECB)
    size = os.path.getsize(path)
    tmp = path + ".megadec"
    file_mac = b"\0" * 16
    with open(path, "rb") as src, open(tmp, "wb") as dst:
        for _, n in _mac_chunks(size):
            plain = ctr.decrypt(src.read(n))
            dst.write(plain)
            # parca MAC'i: iv = nonce+nonce, CBC-MAC (son blok sifirla doldurulur)
            pad = plain + b"\0" * (-len(plain) % 16)
            cmac = AES.new(aes_key, AES.MODE_CBC, iv=nonce + nonce).encrypt(pad)[-16:]
            file_mac = ecb.encrypt(_xor(file_mac, cmac))
    os.replace(tmp, path)
    w = struct.unpack(">4I", file_mac)
    condensed = struct.pack(">2I", w[0] ^ w[1], w[2] ^ w[3])
    return condensed == meta_mac


class MegaDecrypt(PostProcessor):
    name = "mega_decrypt"

    def applies(self, download) -> bool:
        return download.source == "plugin:mega" and bool((download.options or {}).get("mega_key"))

    def process(self, download) -> None:
        path, key = download.path, download.options["mega_key"]

        def run() -> None:
            try:
                ok = decrypt_file(path, key)
                if ok:
                    log.info("MEGA dosyasi cozuldu: %s", path)
                else:
                    log.warning("MEGA MAC dogrulamasi tutmadi (dosya bozuk olabilir): %s", path)
            except Exception:
                log.exception("MEGA dosyasi cozulemedi: %s", path)

        # buyuk dosyada durum dongusunu bekletmesin
        threading.Thread(target=run, name="mega-decrypt", daemon=True).start()


def register(ctx) -> None:
    ctx.register_cloud(Mega())
    ctx.register_postprocessor(MegaDecrypt())
