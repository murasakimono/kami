"""python -m app.tools.studio_face_run <video> <cikti.json> <bas> <sure> <oran>
Dikey otomatik cerceve: yuz (yoksa hareket) merkezini izler, yumusatir. IOPaint ortaminda (opencv) calisir.
Cikti: {"kf": [{"t": kaynak_sn, "cx": 0-1}]}. Satir satir JSON: {"p"} ... {"done"} | {"error"}"""
from __future__ import annotations

import json
import sys


def emit(**kw) -> None:
    sys.stdout.write(json.dumps(kw) + "\n")
    sys.stdout.flush()


def main(argv: list[str]) -> int:
    from app.tools import load_args
    src, out, start, dur, ratio = load_args(argv)[:5]
    start, dur, ratio = float(start), float(dur), float(ratio)
    import cv2
    cap = cv2.VideoCapture(src)
    if not cap.isOpened():
        emit(error="video açılamadı")
        return 2
    fps = cap.get(cv2.CAP_PROP_FPS) or 30
    cap.set(cv2.CAP_PROP_POS_MSEC, start * 1000)
    face = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_frontalface_default.xml")
    prof = cv2.CascadeClassifier(cv2.data.haarcascades + "haarcascade_profileface.xml")
    step = max(1, int(round(fps / 6)))      # saniyede ~6 ornek
    raw: list[tuple[float, float | None]] = []
    prev = None
    i = 0
    while True:
        ok = cap.grab()
        if not ok:
            break
        t = start + i / fps
        if t > start + dur:
            break
        if i % step == 0:
            ok, fr = cap.retrieve()
            if not ok:
                break
            h, w = fr.shape[:2]
            sc = 360 / h
            small = cv2.resize(fr, (int(w * sc), 360))
            g = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            fs = list(face.detectMultiScale(g, 1.15, 5, minSize=(28, 28)))
            if not fs:
                fs = list(prof.detectMultiScale(g, 1.15, 5, minSize=(28, 28)))
            cx = None
            if fs:
                x, y, fw, fh = max(fs, key=lambda r: r[2] * r[3])   # en buyuk yuz = konusan
                cx = (x + fw / 2) / small.shape[1]
            elif prev is not None:   # yuz yok: hareketin agirlik merkezi
                d = cv2.absdiff(g, prev)
                _, m = cv2.threshold(d, 25, 255, cv2.THRESH_BINARY)
                mo = cv2.moments(m)
                if mo["m00"] > 500:
                    cx = mo["m10"] / mo["m00"] / small.shape[1]
            prev = g
            raw.append((t, cx))
            emit(p=round(min(1.0, (t - start) / max(0.1, dur)), 3))
        i += 1
    cap.release()
    # bosluklari doldur, yumusat (kamera operatoru gibi: kucuk titremelere tepki verme)
    last = 0.5
    filled = []
    for t, cx in raw:
        if cx is not None:
            last = cx
        filled.append((t, last))
    sm, v = [], None
    for t, cx in filled:
        v = cx if v is None else (v + (cx - v) * 0.18 if abs(cx - v) > 0.04 else v)
        sm.append((t, v))
    kf, lastv = [], None
    for j, (t, cx) in enumerate(sm):
        if lastv is None or abs(cx - lastv) > 0.01 or j == len(sm) - 1:
            kf.append({"t": round(t, 3), "cx": round(cx, 4)})
            lastv = cx
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"kf": kf, "ratio": ratio}, f)
    emit(done=1, n=len(kf))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Exception as exc:
        emit(error=f"{type(exc).__name__}: {str(exc)[:300]}")
        sys.exit(1)
