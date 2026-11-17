"""python -m app.tools.studio_track_run <video> <cikti.json> <bas> <sure> <x> <y> <w> <h>
Hareket takibi: baslangic karesinde verilen kutuyu (0-1, kaynak karesine gore) OpenCV CSRT ile izler.
Cikti: {"kf": [{"t": kaynak_sn, "cx", "cy", "w", "h"}], "lost": [t...]}. Satir satir JSON: {"p"} ... {"done"} | {"error"}"""
from __future__ import annotations

import json
import sys


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw) + "\n")
    sys.stdout.flush()


def _tracker(cv2):
    for name in ("TrackerCSRT_create", "TrackerKCF_create"):
        for mod in (getattr(cv2, "legacy", None), cv2):
            f = getattr(mod, name, None) if mod else None
            if f:
                return f()
    return cv2.TrackerMIL_create()


def smooth(kf: list[dict], a: float = 0.45) -> list[dict]:
    """Ustel yumusatma: titremeyi alir, gecikmeyi kucuk tutar."""
    out, prev = [], None
    for k in kf:
        if prev is None:
            prev = dict(k)
        else:
            prev = {**k, **{q: prev[q] + (k[q] - prev[q]) * a for q in ("cx", "cy", "w", "h")}}
        out.append({q: round(v, 4) if isinstance(v, float) else v for q, v in prev.items()})
    return out


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, out, start, dur, bx, by, bw, bh = load_args(argv)[:8]
    start, dur = float(start), float(dur)
    bx, by, bw, bh = float(bx), float(by), float(bw), float(bh)
    import cv2
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        emit(error="video açılamadı")
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    ok, fr = cap.read()
    if not ok:
        emit(error="kare okunamadı")
        return 2
    H0, W0 = fr.shape[:2]
    sc = min(1.0, 540 / H0)   # hiz icin 540p'de izle
    def small(f):
        return cv2.resize(f, (int(W0 * sc), int(H0 * sc))) if sc < 1 else f
    sw, sh = int(W0 * sc), int(H0 * sc)
    box = (int(bx * sw), int(by * sh), max(4, int(bw * sw)), max(4, int(bh * sh)))
    tr = _tracker(cv2)
    tr.init(small(fr), box)
    step = max(1, int(round(fps / 12)))   # saniyede ~12 anahtar kare
    kf = [{"t": round(start, 3), "cx": bx + bw / 2, "cy": by + bh / 2, "w": bw, "h": bh}]
    lost: list[float] = []
    i = 1
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        t = start + i / fps
        if t > start + dur:
            break
        good, b = tr.update(small(fr))
        if i % step == 0:
            if good:
                x, y, w, h = b
                kf.append({"t": round(t, 3), "cx": (x + w / 2) / sw, "cy": (y + h / 2) / sh, "w": w / sw, "h": h / sh})
            else:
                lost.append(round(t, 2))
            emit(p=round(min(1.0, (t - start) / max(0.1, dur)), 3))
        i += 1
    cap.release()
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"kf": smooth(kf), "lost": lost, "size": [W0, H0]}, f)
    emit(done=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
