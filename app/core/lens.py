"""Kami Lens: gorselle arama. Gorsel Yandex, TinEye ve Google Lens'e ayni anda yuklenir; sonuclar birlestirilir.

- Yandex: benzer siteler (baslik, aciklama, adres, kucuk resim, asil gorsel), diger boyutlar, benzer gorseller.
- TinEye: birebir kopyalar ve gectigi sayfalar.
- Google Lens ve Bing: sonuc sayfasi baglantisi (sayfalari JS ile olusuyor; Kami'de "tarayicida ac").
Resmi olmayan uclar: bir motor degisirse digerleri calismaya devam eder.
"""
from __future__ import annotations

import html
import json
import logging
import mimetypes
import os
import re
from concurrent.futures import ThreadPoolExecutor
from urllib.parse import quote, urljoin

import requests

log = logging.getLogger("kami")
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/140.0 Safari/537.36",
      "Accept-Language": "tr,en;q=0.8"}


def _prep(path: str) -> tuple[bytes, str]:
    """Buyuk/HEIC gorselleri 1600 px JPEG'e indirir (yukleme hizli, motorlar kabul eder)."""
    from io import BytesIO
    from PIL import Image, ImageOps
    raw = open(path, "rb").read()
    mime = mimetypes.guess_type(path)[0] or "image/jpeg"
    try:
        im = Image.open(BytesIO(raw))
        if max(im.size) > 1600 or mime not in ("image/jpeg", "image/png", "image/webp") or len(raw) > 6e6:
            im = ImageOps.exif_transpose(im).convert("RGB")
            im.thumbnail((1600, 1600))
            buf = BytesIO()
            im.save(buf, "JPEG", quality=90)
            return buf.getvalue(), "image/jpeg"
    except Exception:
        pass
    return raw, mime


def yandex(data: bytes, mime: str) -> dict:
    params = {"rpt": "imageview", "format": "json",
              "request": json.dumps({"blocks": [{"block": "b-page_type_search-by-image__link"}]})}
    j = requests.post("https://yandex.com/images/search", params=params, files={"upfile": ("i", data, mime)},
                      headers=UA, timeout=30).json()
    pr = j["blocks"][0]["params"]
    page_url = f"https://yandex.com/images/search?cbir_id={quote(pr['cbirId'], safe='')}&rpt=imageview&url={quote(pr['originalImageUrl'], safe='')}"
    page = requests.get(page_url, headers=UA, timeout=30).text
    out = {"page": page_url, "hosted": pr.get("originalImageUrl", ""), "sites": [], "sizes": [], "similar": [], "tags": []}
    m = next((x for x in re.finditer(r'data-state="([^"]{200,})"', page) if "cbirSites" in x.group(1)), None)
    if not m:
        return out
    st = json.loads(html.unescape(m.group(1))).get("initialState", {})
    fix = lambda u: ("https:" + u) if u and u.startswith("//") else u   # noqa: E731
    for s in (st.get("cbirSites") or {}).get("sites", [])[:60]:
        oi = s.get("originalImage") or {}
        out["sites"].append({"title": s.get("title", ""), "desc": s.get("description", ""), "url": s.get("url", ""),
                             "domain": s.get("domain", ""), "thumb": fix((s.get("thumb") or {}).get("url", "")),
                             "img": oi.get("url", ""), "w": oi.get("width") or 0, "h": oi.get("height") or 0, "engine": "Yandex"})
    for grp in ((st.get("cbirOtherSizes") or {}).get("items") or {}).values():
        for it in grp or []:
            w, _, h = (it.get("text") or "").partition("×")
            if it.get("url"):
                out["sizes"].append({"url": it["url"], "w": int(w) if w.isdigit() else 0, "h": int(h) if h.isdigit() else 0})
    for t in (st.get("cbirSimilar") or {}).get("thumbs", [])[:24]:
        out["similar"].append({"thumb": fix(t.get("imageUrl", "")), "title": t.get("title", ""),
                               "url": urljoin("https://yandex.com", t.get("linkUrl", ""))})
    out["tags"] = [t.get("text") or t.get("title") or "" for t in (st.get("cbirTags") or {}).get("tags", []) if isinstance(t, dict)]
    return out


def tineye(data: bytes, mime: str) -> dict:
    r = requests.post("https://tineye.com/api/v1/result_json/", files={"image": ("i", data, mime)}, headers=UA, timeout=30).json()
    sites = []
    for m in r.get("matches") or []:
        for b in (m.get("backlinks") or [])[:2]:
            sites.append({"title": b.get("image_name", ""), "desc": f"TinEye · {b.get('crawl_date', '')}", "url": b.get("backlink", ""),
                          "domain": re.sub(r"^https?://(www\.)?([^/]+).*", r"\2", b.get("backlink", "")), "thumb": m.get("image_url", ""),
                          "img": b.get("url", ""), "w": m.get("width") or 0, "h": m.get("height") or 0, "engine": "TinEye"})
    return {"total": r.get("num_matches") or len(sites), "sites": sites,
            "page": f"https://tineye.com/search/{r.get('query_hash', '')}" if r.get("query_hash") else "https://tineye.com"}


def google(data: bytes, mime: str) -> dict:
    r = requests.post("https://lens.google.com/v3/upload", files={"encoded_image": ("i", data, mime)}, headers=UA,
                      timeout=30, allow_redirects=False)
    return {"page": r.headers.get("location", "")}


def search(path: str) -> dict:
    data, mime = _prep(path)
    res: dict = {"ok": True, "engines": {}, "errors": {}}
    with ThreadPoolExecutor(3) as ex:
        futs = {name: ex.submit(fn, data, mime) for name, fn in (("yandex", yandex), ("tineye", tineye), ("google", google))}
        for name, f in futs.items():
            try:
                res["engines"][name] = f.result(timeout=45)
            except Exception as exc:
                log.warning("Kami Lens %s: %s", name, exc)
                res["errors"][name] = type(exc).__name__
    y, t, g = (res["engines"].get(k) or {} for k in ("yandex", "tineye", "google"))
    sites, seen = [], set()
    for s in (y.get("sites") or []) + (t.get("sites") or []):   # ayni sayfa iki motordan gelirse bir kez
        key = re.sub(r"^https?://(www\.)?", "", s["url"]).rstrip("/")
        if key and key not in seen:
            seen.add(key)
            sites.append(s)
    sizes = sorted([s for s in (y.get("sizes") or []) if s["w"]] + [{"url": s["img"], "w": s["w"], "h": s["h"]} for s in sites if s.get("img") and s.get("w")],
                   key=lambda s: -(s["w"] * s["h"]))
    hosted = y.get("hosted", "")
    res.update({
        "sites": sites[:80], "similar": y.get("similar") or [], "tags": y.get("tags") or [],
        "biggest": sizes[0] if sizes else None, "sizes": sizes[:12], "tineye_total": t.get("total", 0),
        "links": {"Google Lens": g.get("page", ""), "Yandex": y.get("page", ""), "TinEye": t.get("page", ""),
                  "Bing": f"https://www.bing.com/images/search?view=detailv2&iss=sbi&q=imgurl:{quote(hosted, safe='')}" if hosted else ""},
    })
    if not res["engines"]:
        res["ok"] = False
    return res


def download(url: str, folder: str, stem: str = "lens") -> str:
    r = requests.get(url, headers=UA, timeout=60)
    r.raise_for_status()
    ext = {"image/png": ".png", "image/webp": ".webp", "image/gif": ".gif"}.get(r.headers.get("content-type", "").split(";")[0], ".jpg")
    out = os.path.join(folder, f"{stem} (büyük){ext}")
    n = 2
    while os.path.exists(out):
        out = os.path.join(folder, f"{stem} (büyük {n}){ext}")
        n += 1
    with open(out, "wb") as f:
        f.write(r.content)
    return out
