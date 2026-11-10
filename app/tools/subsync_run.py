"""python -m app.tools.subsync_run <video> <girdi.vtt|srt> <cikti.srt> <ffmpeg_klasoru> [whisper_model_klasoru] [model]
Altyaziyi sese hizalar. Once Whisper: sesteki konusma/sarki satirlarinin zamanlari ile altyazi satirlari
karsilastirilir (capraz iliski, +-120 sn) -> muzikli videolarda da tutar. Olmazsa ffsubsync (VAD). Whisper ortaminda calisir.
JSON: {"stage": "sync"} ... {"done": "<srt>", "offset": sn} | {"error": "..."}"""
from __future__ import annotations

import io
import json
import re
import sys
from contextlib import redirect_stderr, redirect_stdout


def emit(**kw) -> None:
    sys.__stdout__.write(json.dumps(kw, ensure_ascii=False) + "\n")
    sys.__stdout__.flush()


TS = re.compile(r"(\d+):(\d\d):(\d\d)[,.](\d{3})")


def _sec(m) -> float:
    return int(m.group(1)) * 3600 + int(m.group(2)) * 60 + int(m.group(3)) + int(m.group(4)) / 1000


def _fmt(t: float) -> str:
    ms = max(0, int(round(t * 1000)))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _cues(text: str) -> list[tuple[float, float, str]]:
    out = []
    for block in re.split(r"\n\s*\n", text.replace("\r", "").lstrip("\ufeff")):
        lines = block.split("\n")
        k = next((i for i, l in enumerate(lines) if "-->" in l), -1)
        if k < 0:
            continue
        a, b = lines[k].split("-->")[:2]
        ma, mb = TS.search(a if a.count(":") == 2 else "00:" + a), TS.search(b if b.split()[0].count(":") == 2 else "00:" + b)
        if ma and mb:
            out.append((_sec(ma), _sec(mb), "\n".join(lines[k + 1:]).strip()))
    return out


def whisper_offset(video: str, cues, models: str, model: str) -> float | None:
    import numpy as np
    from app.tools.whisper_run import _cuda_dlls
    _cuda_dlls()
    from faster_whisper import WhisperModel
    m = None
    for dev, ct in (("cuda", "float16"), ("cpu", "int8")):
        try:
            m = WhisperModel(model, device=dev, compute_type=ct, download_root=models)
            break
        except Exception:
            continue
    if m is None:
        return None
    emit(stage="whisper")
    segs, _ = m.transcribe(video, beam_size=1, vad_filter=True, vad_parameters={"min_silence_duration_ms": 300})
    segl = [(s.start, s.end, (s.text or "").strip()) for s in segs if (s.text or "").strip()]
    ref = [(a0, a1) for a0, a1, _t in segl]
    if len(ref) < 3 or len(cues) < 3:
        return None
    # 1) ayni dildeyse metin eslestirme: her altyazi satiri icin en benzer Whisper satiri -> farklarin medyani
    import difflib
    norm = lambda x: re.sub(r"[^\w ]+", "", re.sub(r"<[^>]+>|\{[^}]*\}", "", x.lower())).strip()
    W = [(a0, norm(t)) for a0, _a1, t in segl]
    diffs = []
    for c0, _c1, t in cues:
        nt = norm(t)
        if len(nt) < 6:
            continue
        best = max(W, key=lambda w: difflib.SequenceMatcher(None, nt, w[1]).quick_ratio() and difflib.SequenceMatcher(None, nt, w[1]).ratio())
        r = difflib.SequenceMatcher(None, nt, best[1]).ratio()
        if r >= 0.6 and abs(best[0] - c0) <= 120:
            diffs.append(best[0] - c0)
    if len(diffs) >= 3:
        diffs.sort()
        med = diffs[len(diffs) // 2]
        close = [d for d in diffs if abs(d - med) < 1.0]   # tekrar eden nakaratlar disarida
        if len(close) >= max(3, len(diffs) // 3):
            emit(stage="text_match", matches=len(close))
            return round(sum(close) / len(close), 2)
    # 2) farkli dil / metin tutmadi: konusma zamanlarinin capraz iliskisi
    R = 100   # 10 ms cozunurluk
    end = int((max(ref[-1][1], cues[-1][1]) + 130) * R)
    a, b = np.zeros(end, np.float32), np.zeros(end, np.float32)
    for s0, s1 in ref:
        a[int(s0 * R):int(s1 * R)] = 1
    for c0, c1, _t in cues:
        b[int(c0 * R):int(c1 * R)] = 1
    n = 1 << (2 * end - 1).bit_length()
    corr = np.fft.irfft(np.fft.rfft(a, n) * np.conj(np.fft.rfft(b, n)), n)
    lim = 120 * R
    cand = np.concatenate([corr[:lim], corr[-lim:]])   # kaydirma +0..+120 sn ve -120..0 sn
    i = int(np.argmax(cand))
    shift = i if i < lim else i - 2 * lim
    return shift / R


def main(argv: list[str]) -> int:
    from app.tools import load_args
    args = load_args(argv)
    video, src, out, ffdir = args[:4]
    models = args[4] if len(args) > 4 else ""
    model = args[5] if len(args) > 5 else "large-v3-turbo"
    if models:
        try:
            with open(src, encoding="utf-8", errors="replace") as f:
                cues = _cues(f.read())
            off = whisper_offset(video, cues, models, model)
            if off is not None:
                with open(out, "w", encoding="utf-8", newline="\n") as f:
                    for n, (c0, c1, t) in enumerate(cues, 1):
                        f.write(f"{n}\n{_fmt(c0 + off)} --> {_fmt(c1 + off)}\n{t}\n\n")
                emit(done=out, offset=round(off, 2), method="whisper")
                return 0
        except Exception as exc:
            emit(warn=f"whisper hizalama: {type(exc).__name__}: {str(exc)[:160]}")
    from ffsubsync.ffsubsync import make_parser, run
    emit(stage="sync")
    args = make_parser().parse_args([video, "-i", src, "-o", out, "--ffmpeg-path", ffdir, "--max-offset-seconds", "120",
                                  "--reference-stream", "a:0"])
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):   # ffsubsync gunlugu JSON satirlarini bozmasin
        res = run(args)
    if res.get("retval", 1) != 0:
        emit(error=(buf.getvalue().strip().splitlines() or ["sync_failed"])[-1][:200])
        return 2
    m = re.search(r"offset seconds:\s*(-?[\d.]+)", buf.getvalue())
    emit(done=out, offset=float(m.group(1)) if m else None, method="ffsubsync")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
