"""python -m app.tools.kasa_embed_run @args.json   (Kami Kasa ortaminda: fastembed + onnxruntime, CPU)
Kalici sunucu: stdin'den satir satir JSON istek, stdout'a satir satir JSON cevap. Modeller ilk istekte yuklenir.
  {"op": "text", "texts": [...]}            -> {"vecs": [[...]]}   cok dilli MiniLM (384) - transkript/baslik anlami
  {"op": "image", "paths": [...]}           -> {"vecs": [[...]]}   CLIP ViT-B/32 gorsel (512)
  {"op": "clip_text", "texts": [...]}       -> {"vecs": [[...]], "en": [...]}  CLIP metin (512); Turkce -> Ingilizce cevrilir
  {"op": "ping"}                            -> {"ok": true}
Args dosyasi: [model_klasoru]"""
from __future__ import annotations

import json
import os
import sys

TEXT_MODEL = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CLIP_IMG = "Qdrant/clip-ViT-B-32-vision"
CLIP_TXT = "Qdrant/clip-ViT-B-32-text"
_M: dict = {}


def out(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def _model(kind: str, cache: str):
    if kind not in _M:
        from fastembed import ImageEmbedding, TextEmbedding
        if kind == "text":
            _M[kind] = TextEmbedding(TEXT_MODEL, cache_dir=cache)
        elif kind == "image":
            _M[kind] = ImageEmbedding(CLIP_IMG, cache_dir=cache)
        else:
            _M[kind] = TextEmbedding(CLIP_TXT, cache_dir=cache)
    return _M[kind]


def _to_en(texts: list[str]) -> list[str]:
    """CLIP metin kodlayicisi Ingilizce; Turkce sorgu cevrilir (internet yoksa oldugu gibi)."""
    res = []
    for t in texts:
        try:
            from deep_translator import GoogleTranslator
            res.append(GoogleTranslator(source="auto", target="en").translate(t) or t)
        except Exception:
            res.append(t)
    return res


def handle(req: dict, cache: str) -> dict:
    op = req.get("op")
    if op == "ping":
        return {"ok": True}
    if op == "text":
        return {"vecs": [v.tolist() for v in _model("text", cache).embed([str(t)[:2000] for t in req.get("texts") or []])]}
    if op == "image":
        paths = [p for p in req.get("paths") or [] if os.path.isfile(p)]
        return {"vecs": [v.tolist() for v in _model("image", cache).embed(paths)] if paths else []}
    if op == "clip_text":
        en = _to_en([str(t)[:300] for t in req.get("texts") or []])
        return {"vecs": [v.tolist() for v in _model("clip_text", cache).embed(en)], "en": en}
    return {"error": f"bad_op {op}"}


def main(argv: list[str]) -> int:
    if argv and argv[0].startswith("@"):
        with open(argv[0][1:], encoding="utf-8") as f:
            argv = json.load(f)
    cache = argv[0] if argv else os.path.join(os.path.expanduser("~"), ".cache", "kami_kasa")
    os.makedirs(cache, exist_ok=True)
    out(ready=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        rid = None
        try:
            req = json.loads(line)
            rid = req.get("id")
            res = handle(req, cache)
        except Exception as exc:
            res = {"error": f"{type(exc).__name__}: {str(exc)[:300]}"}
        out(id=rid, **res)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
