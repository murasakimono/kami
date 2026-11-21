"""Real-ESRGAN / RIFE ONNX -> TensorRT .engine derleyici (alt surec, trt venv'inde calisir).

Neden gerekli: TRT 11'den itibaren vs-mlrt eklentisi ONNX kabul etmiyor, hazir .engine istiyor;
TensorRT'nin ONNX parser'i ve builder'i Python baglarindan cagrilmali.

Kullanim:
  python -m app.tools.trt_build_engine <model.onnx> <model.engine> [--fp16] [--max-w 1920] [--max-h 1080]
Cikti: JSON satiri {"ok": true, "engine": ..., "mb": ..., "seconds": ...} veya {"ok": false, "error": ...}
"""
from __future__ import annotations

import argparse
import json
import sys
import time

MB = 1 << 20


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("onnx")
    ap.add_argument("engine")
    ap.add_argument("--fp16", action="store_true")
    ap.add_argument("--min-size", type=int, default=64)
    ap.add_argument("--opt", type=int, default=256)
    ap.add_argument("--max-w", type=int, default=1920)
    ap.add_argument("--max-h", type=int, default=1080)
    ap.add_argument("--workspace", type=int, default=2048, help="MB")
    a = ap.parse_args()

    try:
        import tensorrt_bindings as trt
        logger = trt.Logger(trt.Logger.WARNING)
        builder = trt.Builder(logger)
        network = builder.create_network()          # TRT 11: EXPLICIT_BATCH tek mod
        parser = trt.OnnxParser(network, logger)
        with open(a.onnx, "rb") as f:
            data = f.read()
        if not parser.parse(data):
            errs = [str(parser.get_error(i)) for i in range(parser.num_errors)]
            print(json.dumps({"ok": False, "error": "onnx parse: " + " | ".join(errs)[:300]}), flush=True)
            return 2

        inp = network.get_input(0)
        config = builder.create_builder_config()
        config.set_memory_pool_limit(trt.MemoryPoolType.WORKSPACE, a.workspace * MB)
        if a.fp16:
            # TRT 11: BuilderFlag.FP16 kaldirildi -> ara katmanlari HALF yap (G/Ç float32 kalir,
            # boylece vs-mlrt'nin besledigi float32 tensörlerle uyumlu olur)
            try:
                config.set_flag(trt.BuilderFlag.FP16)
            except AttributeError:
                n = 0
                for i in range(network.num_layers):
                    layer = network.get_layer(i)
                    try:
                        if layer.precision == trt.DataType.FLOAT:
                            layer.precision = trt.DataType.HALF
                            n += 1
                    except Exception:   # noqa: BLE001 - bazi katmanlar sabit hassasiyetli
                        pass
        if any(int(d) < 0 for d in inp.shape):      # dinamik: farkli cozunurlukler icin profil
            prof = builder.create_optimization_profile()
            prof.set_shape(inp.name, (1, 3, a.min_size, a.min_size),
                           (1, 3, a.opt, a.opt), (1, 3, a.max_h, a.max_w))
            config.add_optimization_profile(prof)

        t0 = time.time()
        blob = builder.build_serialized_network(network, config)
        if blob is None:
            print(json.dumps({"ok": False, "error": "engine derlenemedi"}), flush=True)
            return 3
        # TRT 11 bu baglamada IHostMemory dondurur (bytes degil): once ham veriye cevir
        try:
            raw = bytes(blob)
        except TypeError:
            raw = bytes(memoryview(blob))
        if not raw:
            print(json.dumps({"ok": False, "error": "engine bos"}), flush=True)
            return 4
        with open(a.engine, "wb") as f:
            f.write(raw)
        print(json.dumps({"ok": True, "engine": a.engine, "mb": round(len(raw) / 1e6, 1),
                          "seconds": round(time.time() - t0, 1), "input": inp.name,
                          "shape": list(inp.shape)}), flush=True)
        return 0
    except Exception as exc:   # noqa: BLE001 - alt surec: hatayi JSON olarak ilet
        print(json.dumps({"ok": False, "error": f"{type(exc).__name__}: {exc}"[:300]}), flush=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
