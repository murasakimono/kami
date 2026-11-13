"""Faz 11.2 — Eklentisiz JSON LinkCrawler & coklu ayna failover motoru.

Kullanici veya topluluk tarafindan yazilan JSON kurallariyla yeni hostlardan
dogrudan akis/indirme linki ve yedek aynalari (failover) cikarir.
"""
from __future__ import annotations

import ipaddress
import json
import logging
import re
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urljoin, urlparse

import requests

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/142.0 Safari/537.36"

DEFAULT_RULES: list[dict[str, Any]] = [
    {
        "name": "generic-html5-media",
        "pattern": r"^https?://.+",
        "extract_regex": [
            r'<source[^>]+src=["\']([^"\']+\.(?:mp4|webm|m3u8|mp3|flac)(?:\?[^"\']*)?)["\']',
            r'<video[^>]+src=["\']([^"\']+\.(?:mp4|webm|m3u8)(?:\?[^"\']*)?)["\']',
        ],
        "mirror_patterns": [
            r'data-mirror=["\'](https?://[^"\']+)["\']',
        ],
        "headers": {"User-Agent": _UA},
        "priority": 1000,
    }
]


def is_safe_public_url(url: str) -> bool:
    """SSRF korumasi: yerel/ozel ag adreslerini reddeder."""
    if not url or not url.lower().startswith(("http://", "https://")):
        return False
    host = (urlparse(url).hostname or "").strip().lower()
    if not host or host in ("localhost", "0.0.0.0"):
        return False
    try:
        ip = ipaddress.ip_address(host)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast or ip.is_reserved:
            return False
    except ValueError:
        if host.endswith(".local") or host.endswith(".internal"):
            return False
    return True


def _rules_path(data_dir: Path | None = None) -> Path:
    if data_dir:
        return Path(data_dir) / "crawler_rules.json"
    return Path(__file__).resolve().parents[2] / "data" / "crawler_rules.json"


def load_rules(data_dir: Path | None = None) -> list[dict[str, Any]]:
    path = _rules_path(data_dir)
    custom: list[dict[str, Any]] = []
    if path.is_file():
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(raw, list):
                custom = [r for r in raw if isinstance(r, dict) and r.get("name") and r.get("pattern")]
        except Exception as exc:
            log.warning("crawler_rules.json okunamadi: %s", exc)
    merged = custom + [r for r in DEFAULT_RULES if r["name"] not in {c["name"] for c in custom}]
    return sorted(merged, key=lambda r: int(r.get("priority", 100)))


def save_rule(rule: dict[str, Any], data_dir: Path | None = None) -> dict[str, Any]:
    name = str(rule.get("name") or "").strip()
    pattern = str(rule.get("pattern") or "").strip()
    extract = rule.get("extract_regex")
    if not name or not pattern or not extract:
        return {"ok": False, "error": "Kuralda name, pattern ve extract_regex zorunludur"}
    re.compile(pattern)
    for rx in (extract if isinstance(extract, list) else [extract]):
        re.compile(rx)
    path = _rules_path(data_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    current: list[dict[str, Any]] = []
    if path.is_file():
        try:
            current = [r for r in json.loads(path.read_text(encoding="utf-8")) if isinstance(r, dict)]
        except Exception:
            current = []
    current = [r for r in current if r.get("name") != name]
    current.append(rule)
    path.write_text(json.dumps(current, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "name": name, "count": len(current)}


def delete_rule(name: str, data_dir: Path | None = None) -> dict[str, Any]:
    path = _rules_path(data_dir)
    if not path.is_file():
        return {"ok": False, "deleted": False}
    try:
        current = [r for r in json.loads(path.read_text(encoding="utf-8")) if isinstance(r, dict)]
    except Exception:
        return {"ok": False, "deleted": False}
    filtered = [r for r in current if r.get("name") != name]
    path.write_text(json.dumps(filtered, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"ok": True, "deleted": len(filtered) != len(current)}


def _http_fetch(url: str, headers: dict[str, str], timeout: float = 12.0) -> str:
    r = requests.get(url, headers=headers, timeout=timeout, allow_redirects=True)
    r.raise_for_status()
    return r.text[:2_000_000]


def crawl(
    url: str,
    *,
    rules: list[dict[str, Any]] | None = None,
    data_dir: Path | None = None,
    fetch_fn: Callable[[str, dict[str, str]], str] | None = None,
) -> dict[str, Any]:
    """URL'yi eslesen JSON kuralina gore cozer ve birincil + ayna linkleri dondurur."""
    if not is_safe_public_url(url):
        return {"ok": False, "matched": False, "urls": [], "error": "Gecersiz veya ozel ag URL'si"}

    active_rules = rules if rules is not None else load_rules(data_dir)
    fetcher = fetch_fn or _http_fetch
    matched_rules = []
    for r in active_rules:
        try:
            if re.search(r["pattern"], url, re.I):
                matched_rules.append(r)
        except re.error:
            continue

    if not matched_rules:
        return {"ok": False, "matched": False, "urls": [], "error": "Eslesen kural bulunamadi"}

    for rule in matched_rules:
        hdrs = {"User-Agent": _UA, **{str(k): str(v) for k, v in (rule.get("headers") or {}).items()}}
        try:
            body = fetcher(url, hdrs)
        except Exception as exc:
            log.debug("LinkCrawler fetch hatasi (%s): %s", rule.get("name"), exc)
            continue

        found: list[str] = []
        extract_list = rule.get("extract_regex") or []
        if isinstance(extract_list, str):
            extract_list = [extract_list]
        mirror_list = rule.get("mirror_patterns") or []
        if isinstance(mirror_list, str):
            mirror_list = [mirror_list]

        for rx in extract_list + mirror_list:
            try:
                for m in re.finditer(rx, body, re.I):
                    cand = (m.group(1) if m.groups() else m.group(0)).strip()
                    cand = cand.replace(r"\/", "/")
                    abs_url = urljoin(url, cand)
                    if is_safe_public_url(abs_url) and abs_url not in found:
                        found.append(abs_url)
            except re.error:
                continue

        if found:
            return {
                "ok": True,
                "matched": True,
                "rule": rule.get("name", ""),
                "primary": found[0],
                "mirrors": found[1:],
                "urls": found,
            }

    return {"ok": False, "matched": True, "rule": matched_rules[0].get("name", ""), "urls": [], "error": "Akis bulunamadi"}


def pick_working_mirror(urls: list[str], *, probe_fn: Callable[[str], bool] | None = None) -> str:
    """Coklu ayna listesinden ilk erisilebilir URL'yi failover ile secer."""
    def _default_probe(u: str) -> bool:
        try:
            r = requests.head(u, headers={"User-Agent": _UA}, timeout=5, allow_redirects=True)
            return 200 <= r.status_code < 400
        except requests.RequestException:
            return False

    check = probe_fn or _default_probe
    for u in urls:
        if is_safe_public_url(u) and check(u):
            return u
    return ""
