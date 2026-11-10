"""python -m app.tools.subsync_run <video> <girdi.vtt|srt> <cikti.srt> <ffmpeg_klasoru>
Altyaziyi sese hizalar (ffsubsync: konusma algilama + kaydirma/olcek). Whisper ortaminda calisir.
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


def main(argv: list[str]) -> int:
    from app.tools import load_args
    video, src, out, ffdir = load_args(argv)[:4]
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
    emit(done=out, offset=float(m.group(1)) if m else None)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
