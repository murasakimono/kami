"""Kami Lens araclari (v1.30): urun fiyati (Akakce + Trendyol), yazi -> duzenlenebilir metin, tablo -> Excel, QR/barkod.

- Fiyat: Akakce arama sayfasi (HTML, li[data-pr]) + Trendyol arama servisi (JSON, countryCode=TR). Ikisi paralel;
  sonuclar sorguya benzerlikle suzulur, fiyata gore siralanir. Sorgu Lens sonucundan (etiketler + sayfa basliklari)
  ya da gorseldeki yazidan (OCR) onerilir; kullanici duzeltebilir.
- Metin/Tablo: Windows OCR kelime kutulari (privacy._scan). Tablo: satirlar y'ye gore, hucreler bosluga gore, sutunlar
  tum satirlardaki hucre baslangiclarinin kumelenmesiyle; openpyxl ile .xlsx.
- QR/barkod: zxing-cpp (QR, DataMatrix, EAN/UPC, Code128/39, PDF417, Aztec...). EAN/UPC bulunursa fiyat sorgusu da olur.
"""
from __future__ import annotations

import html
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor
from typing import Any

log = logging.getLogger(__name__)
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
      "Accept-Language": "tr-TR,tr;q=0.9"}
_STOP = {"ve", "ile", "icin", "için", "en", "ucuz", "fiyat", "fiyati", "fiyatı", "satin", "satın", "al", "the", "and", "for", "with",
         "a", "of", "in", "on", "new", "yeni", "orijinal", "original", "online", "kampanya", "indirim", "-", "|", "–"}


def _tokens(s: str) -> list[str]:
    return [t for t in re.findall(r"[\wçğıöşüÇĞİÖŞÜ.+-]{2,}", (s or "").lower()) if t not in _STOP]


def _score(query: str, name: str) -> float:
    q, n = set(_tokens(query)), set(_tokens(name))
    return len(q & n) / max(1, len(q)) if q else 0.0


def _num(text: str) -> float:
    t = re.sub(r"[^\d,.]", "", text or "")
    if "," in t:
        t = t.replace(".", "").replace(",", ".")
    elif t.count(".") > 1 or re.search(r"\.\d{3}$", t):
        t = t.replace(".", "")
    try:
        return float(t)
    except ValueError:
        return 0.0


def akakce(query: str, limit: int = 12) -> list[dict[str, Any]]:
    import requests
    r = requests.get("https://www.akakce.com/arama/", params={"q": query}, headers=UA, timeout=15)
    r.raise_for_status()
    page = r.content.decode("utf-8", "replace")
    out, seen = [], set()
    for m in re.finditer(r'<li data-pr="(\d+)"[^>]*>(.*?)</li>', page, re.S):
        pid, blk = m.group(1), m.group(2)
        if pid in seen:
            continue
        a = re.search(r'<a href=["\']?([^"\' >]+)["\']?[^>]*title="([^"]+)"', blk)
        pr = re.search(r'class="pt_v8"[^>]*>\s*([\d.]+)(?:<i>\s*(,\d+))?', blk)
        if not a or not pr:
            continue
        seen.add(pid)
        img = re.search(r'<img[^>]+src=["\']?([^"\' >]+)', blk)
        sellers = re.search(r"\+(\d+)\s*F", blk)
        url = a.group(1)
        out.append({"src": "Akakçe", "name": html.unescape(a.group(2)), "price": _num(pr.group(1) + (pr.group(2) or "")),
                    "url": url if url.startswith("http") else "https://www.akakce.com" + url,
                    "img": img.group(1) if img else "", "note": f"{int(sellers.group(1)) + 1} satıcı" if sellers else "en ucuz"})
        if len(out) >= limit * 3:
            break
    return out


def trendyol(query: str, limit: int = 12) -> list[dict[str, Any]]:
    import requests
    h = {**UA, "Origin": "https://www.trendyol.com", "Referer": "https://www.trendyol.com/"}
    r = requests.get("https://apigw.trendyol.com/discovery-sfint-search-service/api/search/products",
                     params={"q": query, "qt": query, "st": query, "os": "1", "pi": "1", "culture": "tr-TR", "countryCode": "TR"},
                     headers=h, timeout=15)
    r.raise_for_status()
    out = []
    for p in (r.json().get("products") or [])[: limit * 3]:
        price = (p.get("price") or {}).get("discountedPrice") or (p.get("price") or {}).get("current") or 0
        rt = p.get("ratingScore") or {}
        out.append({"src": "Trendyol", "name": f"{(p.get('brand') or '').title()} {p.get('name') or ''}".strip(), "price": float(price or 0),
                    "url": "https://www.trendyol.com" + (p.get("url") or ""), "img": p.get("image") or "",
                    "note": f"★ {rt.get('averageRating', 0):.1f} ({rt.get('totalCount', 0)})" if rt.get("totalCount") else ""})
    return out


def price_search(query: str, limit: int = 12) -> dict[str, Any]:
    query = re.sub(r"\s+", " ", (query or "").strip())[:120]
    if len(query) < 2:
        return {"ok": False, "error": "sorgu"}
    res: dict[str, Any] = {"ok": True, "query": query, "items": [], "errors": {}}
    with ThreadPoolExecutor(2) as ex:
        futs = {"Akakçe": ex.submit(akakce, query, limit), "Trendyol": ex.submit(trendyol, query, limit)}
        for name, f in futs.items():
            try:
                res["items"] += f.result(timeout=25)
            except Exception as exc:
                log.warning("Fiyat %s: %s", name, exc)
                res["errors"][name] = type(exc).__name__
    items = [i for i in res["items"] if i["price"] > 0]
    for i in items:
        i["match"] = round(_score(query, i["name"]), 2)
    best = max((i["match"] for i in items), default=0)
    keep = [i for i in items if i["match"] >= max(0.34, best * 0.6)] or items   # alakasizlari ele
    keep.sort(key=lambda i: (i["price"]))
    res["items"] = keep[: limit * 2]
    if keep:
        ps = sorted(i["price"] for i in keep)
        res["min"], res["median"] = ps[0], ps[len(ps) // 2]
    return res


def product_query(lens: dict[str, Any], ocr_text: str = "") -> str:
    """Lens sonucundan urun sorgusu: etiketler + sayfa basliklarinda en sik gecen anlamli kelimeler."""
    from collections import Counter
    tags = [t for t in (lens.get("tags") or []) if t][:3]
    titles = [s.get("title") or "" for s in (lens.get("sites") or [])[:20]]
    cnt: Counter = Counter()
    for t in titles:
        for w in dict.fromkeys(_tokens(re.split(r"\s[|\-–]\s", t)[0])):
            if not w.isdigit() or len(w) > 3:
                cnt[w] += 1
    common = [w for w, n in cnt.most_common(8) if n >= 2][:5]
    if common:
        return " ".join(common)
    if tags:
        return tags[0]
    line = next((ln for ln in (ocr_text or "").splitlines() if len(ln.strip()) > 3), "")
    return line.strip()[:80]


# ---------------------------------------------------------------- OCR: metin + tablo
def ocr_words(path: str) -> list[dict[str, Any]]:
    from app.core import privacy
    data = privacy._scan(path, False)
    out = []
    for ln in data.get("lines") or []:
        ws = ln.get("words") or []
        for w in (ws if isinstance(ws, list) else [ws]):
            out.append({"t": w.get("t", ""), "x": float(w.get("x", 0)), "y": float(w.get("y", 0)), "w": float(w.get("w", 0)), "h": float(w.get("h", 0))})
    return out


def ocr_text(path: str) -> dict[str, Any]:
    from app.core import privacy
    data = privacy._scan(path, False)
    lines = [ln.get("text", "") for ln in (data.get("lines") or []) if ln.get("text")]
    return {"ok": True, "text": "\n".join(lines), "lines": len(lines)}


def table_from_words(words: list[dict[str, Any]]) -> list[list[str]]:
    if not words:
        return []
    hs = sorted(w["h"] for w in words if w["h"] > 0) or [10]
    mh = hs[len(hs) // 2]
    # satirlar
    rows: list[list[dict]] = []
    for w in sorted(words, key=lambda w: w["y"] + w["h"] / 2):
        cy = w["y"] + w["h"] / 2
        if rows and abs(cy - rows[-1][0]["_cy"]) < mh * 0.6:
            rows[-1].append({**w, "_cy": rows[-1][0]["_cy"]})
        else:
            rows.append([{**w, "_cy": cy}])
    # hucreler (satir icinde buyuk bosluk = yeni hucre)
    cells_rows = []
    for r in rows:
        r.sort(key=lambda w: w["x"])
        cells, cur = [], [r[0]]
        for w in r[1:]:
            prev = cur[-1]
            if w["x"] - (prev["x"] + prev["w"]) > mh * 1.1:
                cells.append(cur)
                cur = [w]
            else:
                cur.append(w)
        cells.append(cur)
        cells_rows.append([{"x": c[0]["x"], "t": " ".join(x["t"] for x in c)} for c in cells])
    # sutun cipaları: tum hucre baslangiclarinin kumelenmesi
    xs = sorted(c["x"] for r in cells_rows for c in r)
    anchors: list[list[float]] = []
    for x in xs:
        if anchors and x - anchors[-1][-1] < mh * 2.2:
            anchors[-1].append(x)
        else:
            anchors.append([x])
    cols = [sum(a) / len(a) for a in anchors]
    table = []
    for r in cells_rows:
        line = [""] * len(cols)
        for c in r:
            k = min(range(len(cols)), key=lambda i: abs(cols[i] - c["x"]))
            line[k] = (line[k] + " " + c["t"]).strip()
        table.append(line)
    return table


def _cell_value(s: str) -> Any:
    t = s.strip()
    if re.fullmatch(r"-?[\d.]+,\d+|-?\d{1,3}(\.\d{3})+|-?\d+", t):
        v = _num(t)
        return int(v) if v.is_integer() and "," not in t else v
    if re.fullmatch(r"-?\d+\.\d+", t):
        return float(t)
    return t


def table_to_xlsx(path: str, out: str = "") -> dict[str, Any]:
    words = ocr_words(path)
    table = table_from_words(words)
    if not table:
        return {"ok": False, "error": "tablo bulunamadı (yazı okunamadı)"}
    import openpyxl
    from openpyxl.styles import Font
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Kami Lens"
    for r in table:
        ws.append([_cell_value(c) for c in r])
    for c in ws[1]:
        c.font = Font(bold=True)
    for i, col in enumerate(ws.columns, 1):
        ws.column_dimensions[openpyxl.utils.get_column_letter(i)].width = min(60, max(8, max(len(str(c.value or "")) for c in col) + 2))
    out = out or os.path.splitext(path)[0] + "_tablo.xlsx"
    wb.save(out)
    return {"ok": True, "path": out, "rows": len(table), "cols": len(table[0]), "preview": table[:8]}


# ---------------------------------------------------------------- QR / barkod
def barcodes(path: str) -> dict[str, Any]:
    import zxingcpp
    from PIL import Image, ImageOps
    im = Image.open(path)
    found = []
    for variant in (im, ImageOps.grayscale(im), ImageOps.autocontrast(ImageOps.grayscale(im))):
        for b in zxingcpp.read_barcodes(variant):
            item = {"format": str(b.format).split(".")[-1], "text": b.text}
            if item not in found:
                found.append(item)
        if found:
            break
    for f in found:
        t = f["text"]
        f["kind"] = "url" if re.match(r"^https?://", t, re.I) else "wifi" if t.startswith("WIFI:") else \
            "product" if re.fullmatch(r"\d{8}|\d{12,14}", t) else "text"
    return {"ok": True, "codes": found}
