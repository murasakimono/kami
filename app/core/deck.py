"""Kami Deck (v1.28): telefonu Stream Deck gibi kullan + uzaktan indirme yonetimi.

Telefon sayfasi (/deck, Kami > Ayarlar > Telefon anahtariyla) profilleri (Genel, Studio, Player, Indirme...) ve
tuslari gosterir; tus -> eylem kimligi + istege bagli arguman. Profiller telefondan da duzenlenir, deck.json'da durur.
Eylem turleri:
- app:*      Kami pencereleri (Studio, Picture, Player, Reader, Oda)
- rec:*      ekran kaydi / son 30 sn
- room:*     oda mikrofon / kulaklik
- player:*   Kami Player komutu (sayfa veri yolundan alir)
- studio:*   Kami Studio komutu (sayfa veri yolundan alir: klavye kisayolu olarak calisir)
- dl:*       indirmeler: hepsini duraklat/surdur, hiz siniri
- sys:*      sistem: medya tuslari, ses, ozel kisayol (one gelen pencereye), program/link ac
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)

CATALOG: list[dict[str, str]] = [
    {"id": "app:studio", "label": "Studio", "icon": "🎬", "group": "Uygulama"},
    {"id": "app:picture", "label": "Picture", "icon": "🖼", "group": "Uygulama"},
    {"id": "app:player", "label": "Player", "icon": "▶", "group": "Uygulama"},
    {"id": "app:reader", "label": "Reader", "icon": "📖", "group": "Uygulama"},
    {"id": "app:room", "label": "Oda", "icon": "🎧", "group": "Uygulama"},
    {"id": "app:show", "label": "Kami", "icon": "🟣", "group": "Uygulama"},
    {"id": "rec:toggle", "label": "Kayıt", "icon": "⏺", "group": "Kayıt"},
    {"id": "rec:replay", "label": "Son 30 sn", "icon": "⏱", "group": "Kayıt"},
    {"id": "room:mute", "label": "Mikrofon", "icon": "🎙", "group": "Oda"},
    {"id": "room:deaf", "label": "Kulaklık", "icon": "🔇", "group": "Oda"},
    {"id": "player:toggle", "label": "Oynat/Duraklat", "icon": "⏯", "group": "Player"},
    {"id": "player:back10", "label": "−10 sn", "icon": "⏪", "group": "Player"},
    {"id": "player:fwd10", "label": "+10 sn", "icon": "⏩", "group": "Player"},
    {"id": "player:prev", "label": "Önceki", "icon": "⏮", "group": "Player"},
    {"id": "player:next", "label": "Sonraki", "icon": "⏭", "group": "Player"},
    {"id": "player:volup", "label": "Ses +", "icon": "🔊", "group": "Player"},
    {"id": "player:voldown", "label": "Ses −", "icon": "🔉", "group": "Player"},
    {"id": "player:full", "label": "Tam ekran", "icon": "⛶", "group": "Player"},
    {"id": "player:subs", "label": "Altyazı", "icon": "💬", "group": "Player"},
    {"id": "studio:play", "label": "Oynat", "icon": "⏯", "group": "Studio"},
    {"id": "studio:split", "label": "Böl", "icon": "✂", "group": "Studio"},
    {"id": "studio:undo", "label": "Geri al", "icon": "↶", "group": "Studio"},
    {"id": "studio:redo", "label": "Yinele", "icon": "↷", "group": "Studio"},
    {"id": "studio:marker", "label": "İşaret", "icon": "🔖", "group": "Studio"},
    {"id": "studio:trimL", "label": "Baştan kırp", "icon": "⇤", "group": "Studio"},
    {"id": "studio:trimR", "label": "Sondan kırp", "icon": "⇥", "group": "Studio"},
    {"id": "studio:delete", "label": "Sil (ripple)", "icon": "⌫", "group": "Studio"},
    {"id": "studio:save", "label": "Kaydet", "icon": "💾", "group": "Studio"},
    {"id": "studio:export", "label": "Dışa aktar", "icon": "📤", "group": "Studio"},
    {"id": "dl:pause_all", "label": "Hepsini duraklat", "icon": "⏸", "group": "İndirme"},
    {"id": "dl:resume_all", "label": "Hepsini sürdür", "icon": "▶", "group": "İndirme"},
    {"id": "dl:limit", "label": "Hız sınırı", "icon": "🐢", "group": "İndirme", "arg": "KiB/s (0 = sınırsız)"},
    {"id": "sys:playpause", "label": "Medya ⏯", "icon": "⏯", "group": "Sistem"},
    {"id": "sys:next", "label": "Medya ⏭", "icon": "⏭", "group": "Sistem"},
    {"id": "sys:prev", "label": "Medya ⏮", "icon": "⏮", "group": "Sistem"},
    {"id": "sys:volup", "label": "Sistem ses +", "icon": "🔊", "group": "Sistem"},
    {"id": "sys:voldown", "label": "Sistem ses −", "icon": "🔉", "group": "Sistem"},
    {"id": "sys:mute", "label": "Sistem sessiz", "icon": "🔇", "group": "Sistem"},
    {"id": "sys:hotkey", "label": "Kısayol gönder", "icon": "⌨", "group": "Sistem", "arg": "örn. ctrl+shift+m, f13, alt+tab"},
    {"id": "sys:open", "label": "Aç (program/link)", "icon": "🚀", "group": "Sistem", "arg": "yol ya da https://…"},
    {"id": "sys:text", "label": "Metin yaz", "icon": "✍", "group": "Sistem", "arg": "yazılacak metin"},
]
_IDS = {c["id"] for c in CATALOG}

DEFAULT_PROFILES = [
    {"name": "Genel", "buttons": [{"a": x} for x in ("app:studio", "app:picture", "app:player", "app:room", "rec:toggle", "rec:replay",
                                                     "room:mute", "room:deaf", "sys:playpause", "sys:prev", "sys:next", "sys:mute")]},
    {"name": "Studio", "buttons": [{"a": x} for x in ("studio:play", "studio:split", "studio:undo", "studio:redo", "studio:trimL",
                                                      "studio:trimR", "studio:delete", "studio:marker", "studio:save", "studio:export")]},
    {"name": "Player", "buttons": [{"a": x} for x in ("player:toggle", "player:back10", "player:fwd10", "player:prev", "player:next",
                                                      "player:volup", "player:voldown", "player:subs", "player:full")]},
    {"name": "İndirme", "buttons": [{"a": "dl:pause_all"}, {"a": "dl:resume_all"}, {"a": "dl:limit", "arg": "2048", "label": "2 MB/s"},
                                    {"a": "dl:limit", "arg": "0", "label": "Sınırsız"}]},
]


def _file():
    return paths.DATA_DIR / "deck.json"


def load() -> dict[str, Any]:
    try:
        d = json.loads(_file().read_text("utf-8"))
        if isinstance(d.get("profiles"), list) and d["profiles"]:
            return d
    except (OSError, ValueError):
        pass
    return {"profiles": json.loads(json.dumps(DEFAULT_PROFILES)), "cols": 4}


def save(data: dict[str, Any]) -> dict[str, Any]:
    profs = []
    for p in (data.get("profiles") or [])[:12]:
        btns = []
        for b in (p.get("buttons") or [])[:40]:
            a = str(b.get("a") or "")
            if a not in _IDS:
                continue
            btns.append({"a": a, **{k: str(b[k])[:200] for k in ("arg", "label", "icon", "color") if b.get(k)}})
        profs.append({"name": str(p.get("name") or "Profil")[:30], "buttons": btns})
    if not profs:
        profs = json.loads(json.dumps(DEFAULT_PROFILES))
    out = {"profiles": profs, "cols": max(2, min(6, int(data.get("cols") or 4)))}
    tmp = _file().with_suffix(".tmp")
    tmp.write_text(json.dumps(out, ensure_ascii=False, indent=1), "utf-8")
    tmp.replace(_file())
    return out


# ---------------------------------------------------------------- sayfa veri yolu (Studio / Player pencereleri yoklar)
_BUS: dict[str, list[tuple[float, str]]] = {"player": [], "studio": []}
_BUS_LOCK = threading.Lock()


def bus_push(target: str, cmd: str) -> None:
    with _BUS_LOCK:
        q = _BUS.setdefault(target, [])
        q.append((time.time(), cmd))
        del q[:-20]


def bus_poll(target: str) -> list[str]:
    with _BUS_LOCK:
        q = _BUS.get(target, [])
        now = time.time()
        out = [c for t, c in q if now - t < 5]   # 5 sn'den eski komut uygulanmaz (pencere kapaliyken birikmesin)
        _BUS[target] = []
    return out


# ---------------------------------------------------------------- sistem tuslari (Windows SendInput)
VK = {"ctrl": 0x11, "control": 0x11, "shift": 0x10, "alt": 0x12, "win": 0x5B, "tab": 0x09, "enter": 0x0D, "esc": 0x1B, "escape": 0x1B,
      "space": 0x20, "backspace": 0x08, "delete": 0x2E, "home": 0x24, "end": 0x23, "pageup": 0x21, "pagedown": 0x22,
      "left": 0x25, "up": 0x26, "right": 0x27, "down": 0x28, "insert": 0x2D, "printscreen": 0x2C,
      "playpause": 0xB3, "next": 0xB0, "prev": 0xB1, "stop": 0xB2, "volup": 0xAF, "voldown": 0xAE, "mute": 0xAD}
for _i in range(1, 25):
    VK[f"f{_i}"] = 0x6F + _i
_EXT = {0x25, 0x26, 0x27, 0x28, 0x2D, 0x2E, 0x24, 0x23, 0x21, 0x22, 0x5B, 0xB3, 0xB0, 0xB1, 0xB2, 0xAF, 0xAE, 0xAD}


def parse_hotkey(s: str) -> list[int]:
    keys = []
    for part in re.split(r"\s*\+\s*", (s or "").strip().lower()):
        if not part:
            continue
        if part in VK:
            keys.append(VK[part])
        elif len(part) == 1 and (part.isalnum()):
            keys.append(ord(part.upper()))
        else:
            raise ValueError(f"bilinmeyen tus: {part}")
    return keys


def send_keys(vks: list[int]) -> None:
    if os.name != "nt":
        raise RuntimeError("yalniz Windows")
    import ctypes
    u = ctypes.windll.user32
    for v in vks:
        u.keybd_event(v, 0, 1 if v in _EXT else 0, 0)
        time.sleep(0.01)
    for v in reversed(vks):
        u.keybd_event(v, 0, (1 if v in _EXT else 0) | 2, 0)
        time.sleep(0.01)


def type_text(text: str) -> None:
    if os.name != "nt":
        raise RuntimeError("yalniz Windows")
    import ctypes
    from ctypes import wintypes

    class KI(ctypes.Structure):
        _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD), ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                    ("dwExtraInfo", ctypes.POINTER(ctypes.c_ulong))]

    class INP(ctypes.Structure):
        class _U(ctypes.Union):
            _fields_ = [("ki", KI), ("pad", ctypes.c_byte * 32)]
        _anonymous_ = ("u",)
        _fields_ = [("type", wintypes.DWORD), ("u", _U)]

    for ch in str(text)[:2000]:   # Unicode: Turkce harfler dahil, klavye duzeninden bagimsiz
        for flags in (0x0004, 0x0004 | 0x0002):
            i = INP(type=1)
            i.ki = KI(0, ord(ch), flags, 0, None)
            ctypes.windll.user32.SendInput(1, ctypes.byref(i), ctypes.sizeof(INP))


def run(action: str, arg: str, handlers: dict[str, Callable[..., Any]]) -> dict[str, Any]:
    """handlers: api'den gelen geri cagrilar (app_*, rec_*, room_cmd, dl_*). Hata metni telefona doner."""
    if action not in _IDS:
        return {"ok": False, "error": "bilinmeyen eylem"}
    kind, name = action.split(":", 1)
    try:
        if kind == "player" or kind == "studio":
            if kind == "studio" and handlers.get("studio_open"):
                handlers["studio_open"]()   # kapaliysa ac (zaten aciksa one getirir)
            bus_push(kind, name)
        elif kind == "sys":
            if name in ("playpause", "next", "prev", "volup", "voldown", "mute"):
                send_keys([VK[name]])
            elif name == "hotkey":
                send_keys(parse_hotkey(arg))
            elif name == "text":
                type_text(arg)
            elif name == "open":
                if not arg:
                    raise ValueError("yol/link bos")
                if re.match(r"^https?://", arg, re.I):
                    import webbrowser
                    webbrowser.open(arg)
                else:
                    os.startfile(os.path.expandvars(arg))   # type: ignore[attr-defined]
        else:
            fn = handlers.get(action) or handlers.get(kind)
            if not fn:
                raise ValueError("bu eylem bu kurulumda yok")
            fn(name, arg) if handlers.get(kind) and not handlers.get(action) else fn(arg)
        return {"ok": True}
    except Exception as exc:
        log.info("Deck eylemi %s: %s", action, exc)
        return {"ok": False, "error": str(exc)[:160]}
