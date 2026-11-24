"""Kami Beat Asama 1c: mikrofon asistani + mikrofon yeri asistani.

Akis: "Mikrofonu test et" -> 5 sn sessizlik (ortam gurultusu) + 5 sn normal sesle okuma, tek kayit.
Saf hesaplar (test edilebilir): mic_metrics (gurultu tabani, tepe, ortalama, SNR, derece + oneriler),
reverb_estimate (kisa vadeli enerji dusus hizindan KABA RT60 + 0-100 yankililik skoru), placement_advice.
Hicbiri kesin olcum iddia etmez: arayuzde "tahmini" diye etiketlenir.
"""
from __future__ import annotations

import logging
import math
import threading
import time
from typing import Any

log = logging.getLogger(__name__)

TEST_SR = 48000
NOISE_S = 5.0
SPEECH_S = 5.0
CLIP_DBFS = -1.0
QUIET_DBFS = -24.0
NOISE_GOOD = -60.0
NOISE_OK = -50.0
FRAME_S = 0.010


def _db(x: float) -> float:
    return 20.0 * math.log10(x) if x > 1e-6 else -120.0


def _rms(x) -> float:
    import numpy as np
    x = np.asarray(x, dtype="float64").reshape(-1)
    return float(np.sqrt(np.mean(x * x))) if len(x) else 0.0


def frame_db(x, sr: int, frame_s: float = FRAME_S):
    """Kisa vadeli RMS seviyesi (dBFS), cakismasiz frame_s pencereler."""
    import numpy as np
    x = np.asarray(x, dtype="float64").reshape(-1)
    hop = max(1, int(round(frame_s * sr)))
    n = len(x) // hop
    if n <= 0:
        return np.zeros(0)
    fr = x[: n * hop].reshape(n, hop)
    r = np.sqrt(np.mean(fr * fr, axis=1))
    return 20.0 * np.log10(np.maximum(r, 1e-6))


def mic_metrics(noise, speech, sr: int) -> dict[str, Any]:
    """noise: sessizlik bolumu, speech: okuma bolumu (mono float, tam olcek = 1.0)."""
    import numpy as np
    noise = np.asarray(noise, dtype="float64").reshape(-1)
    speech = np.asarray(speech, dtype="float64").reshape(-1)
    noise_db = round(_db(_rms(noise)), 1)
    peak_db = round(_db(float(np.max(np.abs(speech))) if len(speech) else 0.0), 1)
    fdb = frame_db(speech, sr, 0.05)
    gate = max(noise_db + 6.0, peak_db - 40.0)
    act = fdb[fdb > gate] if len(fdb) else fdb
    if len(act):
        avg_db = round(10.0 * math.log10(float(np.mean(10.0 ** (act / 10.0)))), 1)
    else:
        avg_db = round(_db(_rms(speech)), 1)
    snr = round(avg_db - noise_db, 1)
    noise_rating = "iyi" if noise_db < NOISE_GOOD else ("orta" if noise_db < NOISE_OK else "kötü")
    level_rating = "patlıyor" if peak_db > CLIP_DBFS else ("kısık" if avg_db < QUIET_DBFS else "iyi")
    snr_rating = "iyi" if snr >= 40 else ("orta" if snr >= 25 else "kötü")
    tips: list[str] = []
    if peak_db > CLIP_DBFS:
        tips.append("Ses patlıyor (tepe −1 dBFS üstünde): kazancı düşür ya da mikrofondan biraz uzaklaş.")
    elif avg_db < QUIET_DBFS:
        tips.append("Ses çok kısık (ortalama −24 dBFS altında): mikrofona yaklaş ya da kazancı artır.")
    if noise_rating == "kötü":
        tips.append("Ortam gürültüsü yüksek: fan/klima/buzdolabı gibi sürekli sesleri kapat, kapıyı-pencereyi kapat.")
    elif noise_rating == "orta":
        tips.append("Ortam gürültüsü kabul edilebilir ama daha sessiz bir saatte ya da odada daha temiz olur.")
    if not tips:
        tips.append("Seviyeler iyi görünüyor — bu ayarla kayda geçebilirsin.")
    return {
        "noise_db": noise_db, "peak_db": peak_db, "avg_db": avg_db, "snr_db": snr,
        "noise_rating": noise_rating, "level_rating": level_rating, "snr_rating": snr_rating,
        "clipping": peak_db > CLIP_DBFS, "too_quiet": avg_db < QUIET_DBFS, "tips": tips,
    }


def reverb_estimate(speech, sr: int, noise_db: float | None = None) -> dict[str, Any]:
    """Kaba yankililik tahmini: 10 ms enerji zarfinda hece tepelerinden sonraki dususlerin egimi (dB/sn).
    Her belirgin tepeden sonraki 300 ms icindeki en dusuk noktaya kadar egim olculur (kuru odada hece sonu
    hizla gurultu tabanina iner; yankili odada kuyruk dususu yavaslatir ve bosluklari doldurur). Egimlerin
    medyaninin RT60 karsiligi (60 / egim) doner. Harmonik agirlikli seste dalgalanma tahmini dusurebilir. Skor 0 (kuru) .. 100 (cok yankili)."""
    import numpy as np
    env = frame_db(speech, sr, FRAME_S)
    if len(env) < 20:
        return {"ok": False, "error": "too_short", "rt60": 0.0, "score": 0, "label": "bilinmiyor", "decays": 0}
    if len(env) >= 3:   # 3 kare hareketli ortalama (tek kare titremesi dususu bolmesin)
        env = np.convolve(np.pad(env, 1, mode="edge"), np.ones(3) / 3.0, mode="valid")
    floor = float(noise_db) if noise_db is not None else float(np.percentile(env, 10))
    top = float(np.max(env))
    if top - floor < 15.0:
        return {"ok": False, "error": "low_signal", "rt60": 0.0, "score": 0, "label": "bilinmiyor", "decays": 0}
    start_min = max(floor + 20.0, top - 30.0)
    stop_at = floor + 6.0
    rts: list[float] = []
    n = len(env)
    look = int(round(0.3 / FRAME_S))
    for i in range(1, n - 2):
        if env[i] < start_min or env[i] < env[max(0, i - 10):i + 11].max():
            continue                                  # yalniz +-100 ms icindeki en yuksek tepe (hece basina bir)
        m, j = i, i + 1
        while j < min(n, i + look) and env[j] <= env[i]:
            if env[j] < env[m]:
                m = j
            if env[j] <= stop_at:                     # gurultu tabanina indi: dusus burada biter
                break
            j += 1
        drop = env[i] - env[m]
        if drop < 3.0 or m - i < 2:
            continue
        slope = -drop / ((m - i) * FRAME_S)           # tepe -> bosluk dibi ortalama egimi, dB/sn (negatif)
        if slope < -1.0:
            rts.append(60.0 / -slope)
    if not rts:
        rt = 0.15   # hic yavas dusus yok: cok kuru (dususler 2 kareden kisa)
    else:
        rt = float(np.median(rts))
    rt = round(min(3.0, rt), 2)
    score = int(round(max(0.0, min(100.0, (rt - 0.2) / 0.8 * 100.0))))
    label = "kuru" if rt < 0.4 else ("orta" if rt < 0.65 else "yankılı")
    return {"ok": True, "rt60": rt, "score": score, "label": label, "decays": len(rts)}


def placement_advice(metrics: dict[str, Any], reverb: dict[str, Any]) -> list[str]:
    """Mikrofon yeri onerileri (pratik, oda ici). Olcum kaba oldugu icin dil "tahmini/deneyebilirsin"."""
    tips = ["Mesafe: ağızla mikrofon arası 30-60 cm (yaklaşık bir karış-iki karış); pop filtresi kullan, "
            "mikrofonu ağzın biraz yanına/üstüne çevir."]
    label = str((reverb or {}).get("label") or "")
    if label == "yankılı":
        tips += [
            "Oda yankılı görünüyor (tahmini): yumuşak eşyalı bir köşeye geç — gardırobun/elbise dolabının önü iyi bir başlangıç.",
            "Arkana ve yanlarına yorgan/battaniye as ya da yatağın üstüne yorgan serip ona dönük kaydet.",
            "Çıplak duvar, cam ve boş oda ortasından uzak dur; mikrofonun arkasında da yumuşak yüzey olsun.",
            "Not: Aşama 2'de yankı temizleme gelecek; yine de kaynağında azaltmak her zaman daha temiz.",
        ]
    elif label == "orta":
        tips += [
            "Biraz oda yankısı var (tahmini): kaydı dolabın önüne ya da perdeli/halılı köşeye almayı dene.",
            "Arkana bir battaniye asmak bile fark eder; mikrofonu boş duvara dönük koyma.",
        ]
    elif label == "kuru":
        tips.append("Oda yeterince kuru görünüyor (tahmini) — bu konum iyi.")
    else:
        tips.append("Yankı tahmini için okuma kısmı yetersiz kaldı: 5 saniye boyunca normal sesle, aralıksız oku.")
    if (metrics or {}).get("noise_rating") == "kötü":
        tips.append("Gürültü kaynağına (bilgisayar fanı, pencere) mikrofonun arkasını dön; kardioid mikrofonlar arkadan az alır.")
    return tips


def analyze_test(rec, sr: int, noise_s: float = NOISE_S) -> dict[str, Any]:
    """Tek test kaydini (once sessizlik, sonra okuma) bolup tum karti uretir. Gecis bolgesinden 0.3 sn atilir."""
    import numpy as np
    x = np.asarray(rec, dtype="float64").reshape(-1)
    cut = int(round(noise_s * sr))
    guard = int(round(0.3 * sr))
    noise = x[int(0.2 * sr):max(int(0.2 * sr) + 1, cut - guard)]
    speech = x[min(len(x), cut + guard):]
    if len(speech) < sr:
        return {"ok": False, "error": "too_short"}
    m = mic_metrics(noise, speech, sr)
    rv = reverb_estimate(speech, sr, m["noise_db"])
    return {"ok": True, "metrics": m, "reverb": rv, "placement": placement_advice(m, rv), "t": time.time()}


# ---------------------------------------------------------------- canli test (sounddevice)
_LOCK = threading.Lock()
STATUS: dict[str, Any] = {"running": False, "phase": "", "remaining": 0.0, "level_db": -120.0}


def test_status() -> dict[str, Any]:
    with _LOCK:
        return dict(STATUS)


def run_mic_test(device_id: int = -1, noise_s: float = NOISE_S, speech_s: float = SPEECH_S) -> dict[str, Any]:
    """Arka plan isi: 10 sn tek kayit; STATUS (asama, kalan sure, anlik seviye) arayuzce yoklanir."""
    try:
        import numpy as np
        import sounddevice as sd
    except Exception:
        return {"ok": False, "error": "sounddevice_missing"}
    try:
        from app.core import kami_booth
        if kami_booth.RECORDER.status().get("recording"):
            return {"ok": False, "error": "busy"}
    except Exception:
        pass
    with _LOCK:
        if STATUS.get("running"):
            return {"ok": False, "error": "busy"}
        STATUS.update({"running": True, "phase": "noise", "remaining": noise_s, "level_db": -120.0})
    total = noise_s + speech_s
    try:
        dev = None if device_id is None or int(device_id) < 0 else int(device_id)
        buf = sd.rec(int(round(total * TEST_SR)), samplerate=TEST_SR, channels=1, dtype="float32", device=dev)
        t0 = time.monotonic()
        while True:
            el = time.monotonic() - t0
            if el >= total + 0.05:
                break
            pos = min(len(buf), int(el * TEST_SR))
            win = buf[max(0, pos - int(0.1 * TEST_SR)):pos, 0]
            lvl = _db(float(np.max(np.abs(win)))) if len(win) else -120.0
            with _LOCK:
                STATUS.update({"phase": "noise" if el < noise_s else "speech",
                               "remaining": round(max(0.0, (noise_s - el) if el < noise_s else (total - el)), 1),
                               "level_db": round(lvl, 1)})
            time.sleep(0.08)
        sd.wait()
        res = analyze_test(np.asarray(buf).reshape(-1), TEST_SR, noise_s)
        return res
    except Exception as exc:
        log.exception("Mikrofon testi hatasi")
        return {"ok": False, "error": str(exc)[:140]}
    finally:
        with _LOCK:
            STATUS.update({"running": False, "phase": "done", "remaining": 0.0})
