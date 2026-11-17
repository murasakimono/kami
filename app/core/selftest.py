"""Acilis kendini sinamasi: APP_VERSION degistiginde ilk acilista her modul penceresini gizlice test eder.

- Acik pencerelere dokunmaz (zaten aciksa atlar).
- closing/closed isleyicisi icinde UI cagrisi yapmaz; load_url kullanmaz.
- Sonucu data/selftest.json ve kami.log'a yazar.
"""
from __future__ import annotations

import json
import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable

from app import paths

log = logging.getLogger(__name__)

MODULES: tuple[tuple[str, str, str], ...] = (
    ("player", "Kami Player", "player.html"),
    ("studio", "Kami Studio", "studio.html"),
    ("picture", "Kami Picture", "picture.html"),
    ("reader", "Kami Reader", "reader.html"),
    ("games", "Kami Games", "games.html"),
    ("music", "Kamify", "music.html"),
    ("cleaner", "Kami Cleaner", "cleaner.html"),
)


def selftest_path(data_dir: Path | None = None) -> Path:
    return (data_dir or paths.DATA_DIR) / "selftest.json"


def should_run(current_version: str, data_dir: Path | None = None) -> bool:
    p = selftest_path(data_dir)
    if not p.is_file():
        return True
    try:
        data = json.loads(p.read_text("utf-8"))
        return str(data.get("version") or "") != str(current_version or "")
    except Exception:
        return True


def _write_result(payload: dict[str, Any], data_dir: Path | None = None) -> Path:
    p = selftest_path(data_dir)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")
    tmp.replace(p)
    return p


def run_selftest(
    api: Any,
    current_version: str,
    probe_window_fn: Callable[[str, str, str, float], dict[str, Any]],
    notify_fn: Callable[[str], None] | None = None,
    data_dir: Path | None = None,
    timeout: float = 10.0,
) -> dict[str, Any]:
    """Her modul penceresi icin gizli olustur -> ping -> kapat sinamasi."""
    results: dict[str, dict[str, Any]] = {}
    failed_titles: list[str] = []

    for mod, title, html in MODULES:
        if getattr(api, f"_{mod}_win", None) is not None:
            results[mod] = {"status": "skipped", "reason": "already_open"}
            continue
        t0 = time.monotonic()
        try:
            res = probe_window_fn(mod, title, html, timeout)
            dt_ms = int((time.monotonic() - t0) * 1000)
            ok = bool(res and res.get("ok"))
            entry = {"status": "ok" if ok else "fail", "ms": dt_ms}
            if not ok:
                entry["error"] = str((res or {}).get("error") or "no_response")
                failed_titles.append(title)
            results[mod] = entry
        except Exception as exc:
            dt_ms = int((time.monotonic() - t0) * 1000)
            results[mod] = {"status": "fail", "ms": dt_ms, "error": f"{type(exc).__name__}: {str(exc)[:120]}"}
            failed_titles.append(title)

    all_ok = not failed_titles
    payload = {
        "version": str(current_version),
        "at": int(time.time()),
        "ok": all_ok,
        "results": results,
    }
    _write_result(payload, data_dir=data_dir)
    if all_ok:
        log.info("Acilis kendini sinamasi tamam (%s): %s", current_version, {k: v["status"] for k, v in results.items()})
    else:
        log.warning("Acilis kendini sinamasi hatali (%s): %s", current_version, failed_titles)
        if notify_fn is not None:
            try:
                notify_fn(f"{failed_titles[0]} penceresi cevap vermiyor")
            except Exception:
                log.debug("Selftest bildirimi gonderilemedi", exc_info=True)
    return payload


def probe_pywebview_window(webview_mod: Any, api: Any, mod: str, title: str, html: str, timeout: float = 10.0) -> dict[str, Any]:
    """pywebview ile gizli pencere olustur, JS api.ping() yanitini olc, pencereyi yok et."""
    ready = threading.Event()
    w = webview_mod.create_window(
        f"{title} [SelfTest]",
        url=str(paths.WEB_DIR / html),
        js_api=api,
        width=640,
        height=400,
        hidden=True,
    )
    w.events.loaded += lambda: ready.set()
    try:
        if not ready.wait(timeout=timeout):
            return {"ok": False, "error": "load_timeout"}
        with ThreadPoolExecutor(max_workers=1) as ex:
            val = ex.submit(
                w.evaluate_js,
                "(async()=>{try{return window.pywebview?.api?.ping?await window.pywebview.api.ping():null}catch(e){return {ok:false,error:String(e)}}})()",
            ).result(timeout=timeout)
        if isinstance(val, dict) and val.get("ok"):
            return {"ok": True}
        return {"ok": False, "error": f"bad_ping:{val!r}"[:120]}
    finally:
        try:
            w.destroy()
        except Exception:
            pass
