"""python -m app.tools.translate_run <girdi.vtt|srt> <cikti.srt> <kaynak_dil> <hedef_dil> <motor:nllb|google> <model_klasoru>
Altyazi cevirisi (Whisper ortaminda calisir: ctranslate2 + tokenizers + huggingface_hub orada hazir).
  nllb   : Meta NLLB-200 distilled 1.3B (CTranslate2 int8, ~1.4 GB, ilk kullanimda iner), yerel, GPU; tutarli.
  google : googletrans (resmi olmayan Google Ceviri istemcisi), internet ister; Google degistirirse bozulabilir.
JSON satirlari: {"stage": ...} {"p": 0.4} ... {"done": "<srt>", "lines": n, "engine": ...} | {"error": "..."}"""
from __future__ import annotations

import json
import os
import re
import sys

NLLB_REPO = "JustFrederik/nllb-200-distilled-1.3B-ct2-int8"
NLLB_TOK_REPO = "facebook/nllb-200-distilled-1.3B"   # sadece tokenizer.json (CTranslate2 deposunda yok)
NLLB_CODES = {"tr": "tur_Latn", "en": "eng_Latn", "ja": "jpn_Jpan", "de": "deu_Latn", "fr": "fra_Latn", "es": "spa_Latn",
              "it": "ita_Latn", "ru": "rus_Cyrl", "ar": "arb_Arab", "ko": "kor_Hang", "zh": "zho_Hans", "pt": "por_Latn",
              "nl": "nld_Latn", "pl": "pol_Latn", "az": "azj_Latn", "fa": "pes_Arab", "uk": "ukr_Cyrl", "hi": "hin_Deva"}
TAG = re.compile(r"<[^>]+>|\{[^}]*\}")


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.stdout.flush()


def parse(text: str) -> list[list[str]]:
    """[zaman_satiri, metin] listesi (SRT ve WebVTT)."""
    cues = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "").lstrip("﻿")):
        lines = block.split("\n")
        k = next((i for i, l in enumerate(lines) if "-->" in l), -1)
        if k < 0:
            continue
        a, b = lines[k].split("-->")[:2]
        fix = lambda t: (t.strip().split(" ")[0].replace(".", ",") if t.count(":") == 2 else "00:" + t.strip().split(" ")[0].replace(".", ","))
        body = " ".join(TAG.sub("", l).strip() for l in lines[k + 1:] if l.strip())
        if body:
            cues.append([f"{fix(a)} --> {fix(b)}", body])
    return cues


def wrap(t: str, width: int = 42) -> str:
    """Uzun satiri ortadaki bosluktan ikiye bol (altyazi okunurlugu)."""
    if len(t) <= width:
        return t
    mid = len(t) // 2
    cut = min((i for i, c in enumerate(t) if c == " "), key=lambda i: abs(i - mid), default=-1)
    return t if cut < 0 else t[:cut] + "\n" + t[cut + 1:]


def _cuda_dlls() -> None:
    import importlib.util
    for pkg in ("nvidia.cublas", "nvidia.cudnn", "nvidia.cuda_runtime"):
        try:
            spec = importlib.util.find_spec(pkg)
        except ModuleNotFoundError:
            continue
        for base in (spec.submodule_search_locations or []) if spec else []:
            b = os.path.join(base, "bin")
            if os.path.isdir(b):
                os.add_dll_directory(b)
                os.environ["PATH"] = b + os.pathsep + os.environ.get("PATH", "")


def nllb(texts: list[str], src: str, tgt: str, models: str) -> list[str]:
    _cuda_dlls()
    import ctranslate2
    from huggingface_hub import hf_hub_download, snapshot_download
    from tokenizers import Tokenizer
    emit(stage="model")
    mdir = snapshot_download(NLLB_REPO, cache_dir=models)
    tok = Tokenizer.from_file(hf_hub_download(NLLB_TOK_REPO, "tokenizer.json", cache_dir=models))
    s_code, t_code = NLLB_CODES.get(src, "eng_Latn"), NLLB_CODES.get(tgt, "tur_Latn")
    tr = None
    for dev, ct in (("cuda", "int8_float16"), ("cpu", "int8")):
        try:
            tr = ctranslate2.Translator(mdir, device=dev, compute_type=ct)
            break
        except Exception as exc:
            emit(warn=f"{dev}: {str(exc)[:160]}")
    if tr is None:
        raise RuntimeError("model_load")
    emit(stage="translate")
    out: list[str] = []
    B = 24
    for i in range(0, len(texts), B):
        batch = [[s_code] + tok.encode(t, add_special_tokens=False).tokens + ["</s>"] for t in texts[i:i + B]]
        res = tr.translate_batch(batch, target_prefix=[[t_code]] * len(batch), beam_size=4, max_decoding_length=256)
        for r in res:
            ids = [tok.token_to_id(x) for x in r.hypotheses[0][1:]]
            out.append(tok.decode([x for x in ids if x is not None]).strip())
        emit(p=round(min((i + B) / max(1, len(texts)), 1.0), 3))
    return out


def google(texts: list[str], src: str, tgt: str) -> list[str]:
    import asyncio
    from googletrans import Translator

    async def run() -> list[str]:
        out: list[str] = []
        async with Translator() as t:
            B = 40
            for i in range(0, len(texts), B):
                part = texts[i:i + B]
                res = await t.translate(part, src=src or "auto", dest=tgt)
                out += [r.text for r in (res if isinstance(res, list) else [res])]
                emit(p=round(min((i + B) / max(1, len(texts)), 1.0), 3))
        return out
    emit(stage="translate")
    return asyncio.run(run())


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src_file, out, src, tgt, engine, models = load_args(argv)[:6]
    with open(src_file, encoding="utf-8", errors="replace") as f:
        cues = parse(f.read())
    if not cues:
        emit(error="empty")
        return 2
    texts = [c[1] for c in cues]
    res = nllb(texts, src, tgt, models) if engine == "nllb" else google(texts, src, tgt)
    if len(res) != len(texts):
        emit(error="length_mismatch")
        return 3
    tmp = out + ".part"
    with open(tmp, "w", encoding="utf-8", newline="\n") as f:
        for n, (c, t) in enumerate(zip(cues, res), 1):
            f.write(f"{n}\n{c[0]}\n{wrap(t or c[1])}\n\n")
    os.replace(tmp, out)
    emit(done=out, lines=len(cues), engine=engine)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
