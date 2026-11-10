"""Inerken izle (Asama 6c): torrent / RD (HTTP) videosu sirayla iner, ilk kisim gelince Screenbox'ta acilir.

- HTTP (RD dahil): aria2 stream-piece-selector=inorder (parcalar bastan sona) -> dosyanin basi once dolar.
- Yerel torrent: bt-prioritize-piece=head=64M (videonun basi oncelikli; tam sirali degil ama oynatmaya yeter).
- Bastan kesintisiz inen kisim >= watch_min_mb olunca oynatici acilir (aria2 bitfield ile olculur).
- Oynatici: Screenbox (MS Store, UWP) IApplicationActivationManager::ActivateForFile ile dosyayla acilir;
  bulunamazsa Windows'un varsayilan oynaticisi.
"""
from __future__ import annotations

import ctypes
import logging
import os
import threading
import time
from ctypes import POINTER, byref, c_void_p, c_wchar_p, wintypes
from typing import Any, Callable

log = logging.getLogger(__name__)

SCREENBOX_AUMID = "18496Starpine.Screenbox_rm8wvch11q4my!App"
VIDEO_EXT = (".mp4", ".mkv", ".webm", ".avi", ".mov", ".m4v", ".ts", ".wmv")


class _GUID(ctypes.Structure):
    _fields_ = [("Data1", ctypes.c_ulong), ("Data2", ctypes.c_ushort), ("Data3", ctypes.c_ushort),
                ("Data4", ctypes.c_ubyte * 8)]


def _guid(s: str) -> _GUID:
    g = _GUID()
    ctypes.oledll.ole32.CLSIDFromString(c_wchar_p("{" + s + "}"), byref(g))
    return g


def _vcall(obj: c_void_p, index: int, restype, *argtypes):
    vtbl = ctypes.cast(obj, POINTER(POINTER(c_void_p))).contents
    return ctypes.WINFUNCTYPE(restype, c_void_p, *argtypes)(vtbl[index])


def open_in_uwp(aumid: str, path: str) -> bool:
    """UWP uygulamasini dosyayla ac (Screenbox). Basarisizsa False."""
    ole32, shell32 = ctypes.oledll.ole32, ctypes.oledll.shell32
    try:
        ole32.CoInitializeEx(None, 0x2)
    except OSError:
        pass   # zaten baslatilmis
    item = c_void_p()
    arr = c_void_p()
    aam = c_void_p()
    try:
        shell32.SHCreateItemFromParsingName(c_wchar_p(os.path.abspath(path)), None,
                                            byref(_guid("43826d1e-e718-42ee-bc55-a1e261c37bfe")), byref(item))
        shell32.SHCreateShellItemArrayFromShellItem(item, byref(_guid("b63ea76d-1f85-456f-a19c-48159efa858b")),
                                                    byref(arr))
        ole32.CoCreateInstance(byref(_guid("45BA127D-10A8-46EA-8AB7-56EA9078943C")), None, 0x4,
                               byref(_guid("2e941141-7f97-4756-ba1d-9decde894a3d")), byref(aam))
        pid = wintypes.DWORD()
        hr = _vcall(aam, 4, ctypes.HRESULT, c_wchar_p, c_void_p, c_wchar_p, POINTER(wintypes.DWORD))(
            aam, aumid, arr, None, byref(pid))
        return hr == 0
    except OSError as exc:
        log.info("UWP ile acilamadi (%s): %s", aumid, exc)
        return False
    finally:
        for o in (aam, arr, item):
            if o.value:
                _vcall(o, 2, ctypes.c_ulong)(o)   # Release


def play(path: str, player: str = "screenbox") -> str:
    """-> 'screenbox' | 'default' | ''  (Kami Player main.py'de ayrica yonlendirilir)"""
    if player == "screenbox" and open_in_uwp(SCREENBOX_AUMID, path):
        return "screenbox"
    try:
        os.startfile(path)  # type: ignore[attr-defined]
        return "default"
    except OSError:
        log.exception("Oynatici acilamadi")
        return ""


def contiguous_head(bitfield: str, num_pieces: int, piece_len: int, start: int = 0) -> int:
    """aria2 bitfield (hex) -> 'start' byte'indan itibaren kesintisiz inmis byte sayisi."""
    if not bitfield or not piece_len:
        return 0
    bits = bin(int(bitfield, 16))[2:].zfill(len(bitfield) * 4)[:num_pieces]
    first = start // piece_len
    n = 0
    for b in bits[first:]:
        if b != "1":
            break
        n += 1
    return max(0, (first + n) * piece_len - start)


class Watcher:
    """Bir indirme icin "izle": sira modunu ac, tampon dolunca oynaticiyi ac. Durum download.extra.watch."""

    def __init__(self, manager, set_extra: Callable[..., None], player: Callable[[str], str] = play) -> None:
        self.manager = manager
        self.set_extra = set_extra
        self.player = player
        self._active: dict[int, threading.Event] = {}
        self.heads: dict[str, int] = {}   # yol -> bastan kesintisiz inen byte (Kami Player akisi icin)

    def start(self, did: int) -> dict[str, Any]:
        d = self.manager.store.get(did)
        if not d or not d.gid or d.kind == "media":
            return {"ok": False, "error": "watch_unsupported"}
        if did in self._active:
            return {"ok": True, "already": True}
        eng = self.manager.engine
        try:
            if d.kind == "torrent":
                eng.call("aria2.changeOption", d.gid, {"bt-prioritize-piece": "head=64M"})
            else:
                eng.call("aria2.changeOption", d.gid, {"stream-piece-selector": "inorder"})
        except Exception as exc:
            log.warning("Sira modu acilamadi: %s", exc)
            return {"ok": False, "error": "watch_failed"}
        ev = threading.Event()
        self._active[did] = ev
        self.set_extra(did, watch="buffering", watch_p=0)
        threading.Thread(target=self._wait, args=(did, ev), name=f"kami-watch-{did}", daemon=True).start()
        return {"ok": True}

    def cancel(self, did: int) -> None:
        ev = self._active.pop(did, None)
        if ev:
            ev.set()
            self.set_extra(did, watch="")

    def _target(self, st: dict[str, Any], d) -> tuple[str, int, int]:
        """-> (dosya yolu, dosyanin torrent icindeki baslangic byte'i, dosya boyu)"""
        files = st.get("files") or []
        offset = 0
        best = None
        for f in files:
            length = int(f.get("length") or 0)
            if str(f.get("selected", "true")) == "true" and str(f.get("path", "")).lower().endswith(VIDEO_EXT):
                if best is None or length > best[2]:
                    best = (f["path"], offset, length)
            offset += length
        if best:
            return best
        return d.path, 0, int(d.size or 0)

    def _wait(self, did: int, ev: threading.Event) -> None:
        need_mb = int(self.manager.settings.get("watch_min_mb") or 20)
        opened, how, tracked = False, "", None
        while not ev.wait(1.0):
            d = self.manager.store.get(did)
            if not d or not d.gid:
                break
            try:
                st = self.manager.engine.call("aria2.tellStatus", d.gid,
                                              ["bitfield", "numPieces", "pieceLength", "files", "status"])
            except Exception:
                continue
            path, start, length = self._target(st, d)
            have = contiguous_head(st.get("bitfield") or "", int(st.get("numPieces") or 0),
                                   int(st.get("pieceLength") or 0), start)
            need = min(need_mb * 1024 * 1024, max(1, length) if length else need_mb * 1024 * 1024)
            self.set_extra(did, watch="buffering", watch_p=round(min(1.0, have / need), 2))
            if path and st.get("status") != "complete":
                tracked = os.path.normcase(os.path.abspath(path))
                self.heads[tracked] = have   # Kami Player: sunucu inmemis kisma gecmesin
            if not opened and (have >= need or st.get("status") == "complete"):
                if path and os.path.exists(path):
                    how = self.player(path)
                    opened = True
                    self.set_extra(did, watch="playing" if how else "error", watch_player=how)
                    log.info("Inerken izle: %s (%s)", os.path.basename(path), how or "acilamadi")
                if how != "kami":   # dis oynatici: takip bitti; Kami Player: inis bitene kadar bas konumu guncellenir
                    break
            if st.get("status") == "complete":
                break
        self._active.pop(did, None)
        if tracked:
            self.heads.pop(tracked, None)   # inis bitti / iptal: dosya artik tam

    def head(self, path: str) -> int | None:
        """Kami Player medya sunucusu icin: dosyanin bastan kesintisiz inmis byte sayisi (inmiyorsa None)."""
        return self.heads.get(os.path.normcase(os.path.abspath(path)))
