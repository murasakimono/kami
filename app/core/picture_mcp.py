"""Kami Picture MCP sunucusu (stdio).

Claude veya Antigravity, Kami Picture'in Photoshop/Lightroom/Mockup/Makro araclarini
ve acik gorseli MCP uzerinden okuyup isleyebilir.
Calistirma: `python -m app.core.picture_mcp` veya kurulu Kami'de `Kami.exe --picture-mcp`.
"""
from __future__ import annotations

import base64
import io
import json
import os
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Callable

from PIL import Image

from app import paths
from app.core import picture_pro as PP

PROTO = "2025-06-18"


def _current_file() -> Path:
    return paths.DATA_DIR / "picture_current.json"


def set_current_image(path: str, by: str = "mcp") -> dict[str, Any]:
    p = Path(path)
    if not p.is_file():
        raise FileNotFoundError(f"Görsel bulunamadı: {path}")
    cf = _current_file()
    cf.parent.mkdir(parents=True, exist_ok=True)
    payload = {"path": str(p.resolve()), "by": by, "t": time.time()}
    cf.write_text(json.dumps(payload, ensure_ascii=False), "utf-8")
    return {"ok": True, **payload}


def cur_image(image: str = "") -> str:
    if image:
        if not os.path.isfile(image):
            raise FileNotFoundError(f"Görsel bulunamadı: {image}")
        return image
    try:
        p = json.loads(_current_file().read_text("utf-8")).get("path", "")
    except (OSError, ValueError):
        p = ""
    if not p or not os.path.isfile(p):
        raise RuntimeError("Aktif görsel yok. Önce `pic_open` çağır veya `image` yolunu ver.")
    return p


TOOLS: dict[str, dict[str, Any]] = {}


def tool(name: str, desc: str, props: dict[str, Any], required: list[str] | None = None):
    def deco(fn: Callable[..., Any]):
        TOOLS[name] = {
            "fn": fn,
            "schema": {
                "name": name,
                "description": desc,
                "inputSchema": {"type": "object", "properties": props, "required": required or []},
            },
        }
        return fn

    return deco


@tool("pic_open", "Aktif Kami Picture görselini ayarlar ve Picture önizlemesini günceller.", {
    "image": {"type": "string", "description": "Görsel dosya yolu"},
}, ["image"])
def pic_open(image: str) -> dict:
    return set_current_image(image, by="mcp")


@tool("pic_info", "Görselin boyut, renk modu, format ve EXIF özetini döndürür.", {
    "image": {"type": "string", "description": "Görsel yolu (boşsa aktif görsel)"},
})
def pic_info(image: str = "") -> dict:
    p = Path(cur_image(image))
    with Image.open(p) as im:
        return {
            "ok": True,
            "path": str(p),
            "name": p.name,
            "width": im.width,
            "height": im.height,
            "mode": im.mode,
            "format": im.format,
            "size_bytes": p.stat().st_size,
        }


@tool("pic_render_preview", "Görseli küçük PNG önizleme olarak döndürür (AI görseli doğrudan görür).", {
    "image": {"type": "string", "description": "Görsel yolu (boşsa aktif görsel)"},
    "max_dim": {"type": "integer", "description": "En büyük kenar px (varsayılan 768)"},
})
def pic_render_preview(image: str = "", max_dim: int = 768) -> dict:
    p = Path(cur_image(image))
    with Image.open(p) as im:
        cp = im.convert("RGBA")
        cp.thumbnail((max(128, int(max_dim)), max(128, int(max_dim))), Image.Resampling.LANCZOS)
        buf = io.BytesIO()
        cp.save(buf, format="PNG")
        return {"_image": base64.b64encode(buf.getvalue()).decode("ascii")}


@tool("pic_freq_sep", "Frekans ayrıştırma: düşük frekans (renk/ton) ve yüksek frekans (doku) katmanları çıkarır.", {
    "image": {"type": "string"}, "radius": {"type": "number", "description": "Blur yarıçapı (varsayılan 4.0)"},
})
def pic_freq_sep(image: str = "", radius: float = 4.0) -> dict:
    return PP.frequency_separation(cur_image(image), radius=float(radius))


@tool("pic_seam_carve", "İçeriğe duyarlı (Seam Carving) akıllı boyutlandırma.", {
    "image": {"type": "string"}, "target_w": {"type": "integer"}, "target_h": {"type": "integer"}, "out_path": {"type": "string"},
}, ["target_w", "target_h"])
def pic_seam_carve(target_w: int, target_h: int, image: str = "", out_path: str = "") -> dict:
    return PP.seam_carve_resize(cur_image(image), int(target_w), int(target_h), out_path=out_path)


@tool("pic_clone_lut", "Referans görselin renk gradını kaynak görsele eşleyip .cube 3D LUT üretir.", {
    "src_image": {"type": "string"}, "ref_image": {"type": "string"}, "out_cube": {"type": "string"}, "size": {"type": "integer"},
}, ["src_image", "ref_image", "out_cube"])
def pic_clone_lut(src_image: str, ref_image: str, out_cube: str, size: int = 17) -> dict:
    return PP.clone_lut_from_reference(src_image, ref_image, out_cube, size=int(size))


@tool("pic_cube_to_hald", ".cube 3D LUT dosyasını HaldCLUT PNG'ye dönüştürür.", {
    "cube_path": {"type": "string"}, "out_png": {"type": "string"},
}, ["cube_path", "out_png"])
def pic_cube_to_hald(cube_path: str, out_png: str) -> dict:
    return PP.cube_to_haldclut(cube_path, out_png)


@tool("pic_hdr_merge", "Farklı pozlamalı kareleri Mertens HDR tekniğiyle birleştirir.", {
    "images": {"type": "array", "items": {"type": "string"}}, "out_path": {"type": "string"},
}, ["images", "out_path"])
def pic_hdr_merge(images: list[str], out_path: str) -> dict:
    return PP.hdr_merge_mertens(images, out_path)


@tool("pic_focus_stack", "Makro odaklı kareleri Laplacian focus stacking ile netleştirir.", {
    "images": {"type": "array", "items": {"type": "string"}}, "out_path": {"type": "string"},
}, ["images", "out_path"])
def pic_focus_stack(images: list[str], out_path: str) -> dict:
    return PP.focus_stack_laplacian(images, out_path)


@tool("pic_ecom_pack", "Ürünü e-ticaret stüdyo tuvaline (%12 boşluk + zemin gölgesi) yerleştirir.", {
    "image": {"type": "string"}, "pad_ratio": {"type": "number"}, "size": {"type": "integer"}, "shadow": {"type": "boolean"}, "out_path": {"type": "string"},
})
def pic_ecom_pack(image: str = "", pad_ratio: float = 0.12, size: int = 1200, shadow: bool = True, out_path: str = "") -> dict:
    return PP.ecommerce_studio_pack(cur_image(image), out_path=out_path, pad_ratio=float(pad_ratio), size=int(size), shadow=bool(shadow))


@tool("pic_contact_shadow", "Dekupeli ürüne çift katmanlı AO temas gölgesi ve alt ışık sekmesi ekler.", {
    "image": {"type": "string"}, "bg_color": {"type": "string"}, "pad_ratio": {"type": "number"},
    "size": {"type": "integer"}, "bounce": {"type": "boolean"}, "out_path": {"type": "string"},
})
def pic_contact_shadow(image: str = "", bg_color: str = "#FFFFFF", pad_ratio: float = 0.12, size: int = 1200, bounce: bool = True, out_path: str = "") -> dict:
    return PP.add_contact_shadow(cur_image(image), out_path=out_path, bg_color=bg_color, pad_ratio=float(pad_ratio), size=int(size), bounce=bool(bounce))


@tool("pic_perspective_mockup", "Tasarımı 4 köşe noktasına perspektif mockup olarak giydirir.", {
    "design": {"type": "string"}, "base": {"type": "string"},
    "dst_quad": {"type": "array", "items": {"type": "array", "items": {"type": "number"}}}, "out_path": {"type": "string"},
}, ["design", "base", "dst_quad"])
def pic_perspective_mockup(design: str, base: str, dst_quad: list[list[float]], out_path: str = "") -> dict:
    return PP.perspective_mockup(design, base, dst_quad, out_path=out_path)


@tool("pic_oklch_palette", "Görselden algısal OKLCH renk paleti ve HEX listesi çıkarır.", {
    "image": {"type": "string"}, "count": {"type": "integer"},
})
def pic_oklch_palette(image: str = "", count: int = 6) -> dict:
    return PP.oklch_palette(cur_image(image), count=int(count))


@tool("pic_watermark_embed", "Görsele dayanıklı görünmez Kami telif imzası gömer.", {
    "image": {"type": "string"}, "text": {"type": "string"}, "out_path": {"type": "string"},
}, ["text"])
def pic_watermark_embed(text: str, image: str = "", out_path: str = "") -> dict:
    return PP.embed_blind_watermark(cur_image(image), text, out_path=out_path)


@tool("pic_watermark_read", "Görseldeki görünmez Kami telif imzasını okur.", {
    "image": {"type": "string"},
})
def pic_watermark_read(image: str = "") -> dict:
    return PP.extract_blind_watermark(cur_image(image))


@tool("pic_export_webp_sheet", "Çoklu PNG kareden şeffaf hareketli WebP çıkartma/sprite paketi üretir.", {
    "images": {"type": "array", "items": {"type": "string"}}, "out_path": {"type": "string"}, "duration_ms": {"type": "integer"},
}, ["images"])
def pic_export_webp_sheet(images: list[str], out_path: str = "", duration_ms: int = 140) -> dict:
    return PP.export_webp_sheet(images, out_path=out_path, duration_ms=int(duration_ms))


@tool("pic_macro_list", "Yerleşik ve kayıtlı Kami Picture aksiyon makrolarını listeler.", {})
def pic_macro_list() -> dict:
    return {"ok": True, "macros": PP.list_macros()}


@tool("pic_macro_save", "Yeni aksiyon makrosu kaydeder (resize, adjust, contact_shadow, ecom_pack, freq_sep, watermark, export).", {
    "name": {"type": "string"}, "steps": {"type": "array", "items": {"type": "object"}}, "macro_id": {"type": "string"},
}, ["name", "steps"])
def pic_macro_save(name: str, steps: list[dict[str, Any]], macro_id: str = "") -> dict:
    return PP.save_macro(name, steps, macro_id=macro_id)


@tool("pic_macro_run", "Bir görsele kayıtlı makro veya adım listesi uygular.", {
    "image": {"type": "string"}, "macro": {"description": "Makro ID'si veya adım listesi"}, "out_path": {"type": "string"},
}, ["macro"])
def pic_macro_run(macro: Any, image: str = "", out_path: str = "") -> dict:
    return PP.run_macro(cur_image(image), macro, out_path=out_path)


@tool("pic_macro_batch", "Bir klasör veya dosya listesine toplu aksiyon makrosu uygular.", {
    "target": {"description": "Klasör yolu veya dosya listesi"}, "macro": {"description": "Makro ID'si veya adım listesi"}, "out_dir": {"type": "string"},
}, ["target", "macro"])
def pic_macro_batch(target: Any, macro: Any, out_dir: str = "") -> dict:
    return PP.batch_run_macro(target, macro, out_dir=out_dir)


@tool("pic_send_to_studio", "Görseli doğrudan Kami Studio Medya/Gorseller klasörüne köprüler.", {
    "image": {"type": "string"}, "folder": {"type": "string"},
})
def pic_send_to_studio(image: str = "", folder: str = "Gorseller") -> dict:
    return PP.send_to_studio_asset(cur_image(image), folder=folder)


@tool("pic_ai_status", "Picture AI köprü (IOPaint / ComfyUI) ve VRAM preflight durumunu döner.", {})
def pic_ai_status() -> dict:
    return PP.ai_bridge_status()


def _io():
    """Pencereli (PyInstaller) Kami.exe'de sys.stdin/stdout None olur: devralinan boru tutamaclarini ac."""
    if sys.stdin is not None and sys.stdout is not None:
        return sys.stdin.buffer, sys.stdout.buffer
    import ctypes
    import msvcrt
    k = ctypes.windll.kernel32
    fi = msvcrt.open_osfhandle(k.GetStdHandle(-10), os.O_RDONLY)
    fo = msvcrt.open_osfhandle(k.GetStdHandle(-11), 0)
    return os.fdopen(fi, "rb", buffering=0), os.fdopen(fo, "wb", buffering=0)


def handle(msg: dict) -> dict | None:
    mid, method = msg.get("id"), msg.get("method", "")
    if mid is None:
        return None
    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": mid,
            "result": {
                "protocolVersion": (msg.get("params") or {}).get("protocolVersion") or PROTO,
                "capabilities": {"tools": {}},
                "serverInfo": {"name": "kami-picture", "version": "1.0"},
                "instructions": "Kami Picture Pro MCP sunucusu. Önce pic_open / pic_info ile görseli kontrol et; "
                                "e-ticaret paketi, temas gölgesi, frekans ayrıştırma, LUT klonlama, OKLCH palet, "
                                "aksiyon makroları ve Studio köprüsü için pic_* araçlarını kullan.",
            },
        }
    if method == "ping":
        return {"jsonrpc": "2.0", "id": mid, "result": {}}
    if method == "tools/list":
        return {"jsonrpc": "2.0", "id": mid, "result": {"tools": [t["schema"] for t in TOOLS.values()]}}
    if method == "tools/call":
        prm = msg.get("params") or {}
        t = TOOLS.get(prm.get("name", ""))
        if not t:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32602, "message": "bilinmeyen araç"}}
        try:
            res = t["fn"](**(prm.get("arguments") or {}))
            if isinstance(res, dict) and "_image" in res:
                content = [{"type": "image", "data": res["_image"], "mimeType": "image/png"}]
            else:
                content = [{"type": "text", "text": json.dumps(res, ensure_ascii=False, separators=(",", ":"))}]
            return {"jsonrpc": "2.0", "id": mid, "result": {"content": content}}
        except Exception as exc:
            return {
                "jsonrpc": "2.0",
                "id": mid,
                "result": {"isError": True, "content": [{"type": "text", "text": f"{type(exc).__name__}: {exc}"}]},
            }
    return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"yok: {method}"}}


def main() -> int:
    fin, fout = _io()
    for raw in iter(fin.readline, b""):
        raw = raw.strip()
        if not raw:
            continue
        try:
            msg = json.loads(raw)
        except ValueError:
            continue
        try:
            out = handle(msg)
        except Exception:
            out = {"jsonrpc": "2.0", "id": msg.get("id"), "error": {"code": -32603, "message": traceback.format_exc()[-400:]}}
        if out is not None:
            fout.write((json.dumps(out, ensure_ascii=False) + "\n").encode("utf-8"))
            fout.flush()
    return 0


if __name__ == "__main__":
    sys.exit(main())
