"use strict";
/* Kami Beat Asama 2a (window.BeatSim): "Başka cihazda nasıl duyulur" dinleme simülatörü.
   Yalnız DİNLEMEYİ etkiler: zaman çizelgesinin master çıkışına (miks + referans) Web Audio filtre zinciri olarak
   takılır; bounce/önizleme render'ı bu zincirden hiç geçmez.

   Profiller makul yaklaşık eğrilerdir (ölçülmüş cihaz eğrisi değil). Araştırma notları:
   - Telefon hoparlörü: 1 cm civarı mikro hoparlör + küçük kabin -> ~300-500 Hz altı neredeyse yok (dik düşüş),
     2-4 kHz'de belirgin tepe (konuşma bölgesi rezonansı), ~12 kHz üstü düşer; tek hoparlör/mono toplanır; düşük
     maksimum ses basıncı nedeniyle telefonlar agresif sınırlayıcı + hafif doygunluk uygular.
   - AirPods (kulak içi, Harman kulak içi hedefine yakın ayar): hafif bas yükseltmesi (~+3 dB 100 Hz altı),
     8-10 kHz üstü hafif düşüş.
   - Araba: kabin kazancı (küçük kapalı hacim) ~60-100 Hz'i belirgin yükseltir, ~150 Hz civarında kabin/kapı
     rezonansı, döşeme yüksekleri yutar; sürücü bir hoparlöre çok yakın olduğundan stereo görüntü daralır
     (kısmi mono yönelim).
   - Laptop: 2 küçük yan/alt hoparlör -> ~200 Hz altı yok, ince ve orta-tiz ağırlıklı; hoparlörler yakın -> dar
     stereo.
   - Mono: L+R toplamı (faz iptali ve kaybolan genişlik efektlerini duymak için; Bluetooth hoparlör / kulüp PA).
   - Club (kulüp PA): sub-bas belirgin, üst-orta hafif geri (yüksek seviyede kulak koruması / eşit ses eğrileri
     nedeniyle). Yüksek ses seviyesi uyarısı yok.
   profileNodes(id) saf fonksiyondur (node testli); build(ac, id) bu listeden Web Audio düğüm zinciri kurar. */
(function (root) {
  const PROFILES = {
    normal: { label: "Normal", badge: "", nodes: [] },
    phone: {
      label: "Telefon hoparlörü", badge: "Telefon simülasyonu",
      nodes: [
        { t: "biquad", type: "highpass", f: 400, q: 0.9 },
        { t: "biquad", type: "highpass", f: 400, q: 0.7 },
        { t: "biquad", type: "peaking", f: 3000, q: 1.1, g: 5 },
        { t: "biquad", type: "lowpass", f: 12000, q: 0.7 },
        { t: "width", w: 0 },
        { t: "shaper", k: 0.35 },
        { t: "comp", thr: -18, ratio: 6, knee: 6, att: 0.003, rel: 0.1 },
      ],
    },
    airpods: {
      label: "AirPods", badge: "AirPods simülasyonu",
      nodes: [
        { t: "biquad", type: "lowshelf", f: 100, q: 0.7, g: 3 },
        { t: "biquad", type: "highshelf", f: 9000, q: 0.7, g: -2.5 },
      ],
    },
    car: {
      label: "Araba", badge: "Araba simülasyonu",
      nodes: [
        { t: "biquad", type: "lowshelf", f: 85, q: 0.7, g: 5 },
        { t: "biquad", type: "peaking", f: 150, q: 1.5, g: 3 },
        { t: "biquad", type: "highshelf", f: 10000, q: 0.7, g: -2 },
        { t: "width", w: 0.5 },
      ],
    },
    laptop: {
      label: "Laptop", badge: "Laptop simülasyonu",
      nodes: [
        { t: "biquad", type: "highpass", f: 200, q: 0.9 },
        { t: "biquad", type: "highpass", f: 200, q: 0.7 },
        { t: "biquad", type: "peaking", f: 4000, q: 1.0, g: 3 },
        { t: "biquad", type: "lowpass", f: 15000, q: 0.7 },
        { t: "width", w: 0.4 },
      ],
    },
    mono: { label: "Mono", badge: "Mono dinleme", nodes: [{ t: "width", w: 0 }] },
    club: {
      label: "Kulüp (club)", badge: "Kulüp simülasyonu",
      nodes: [
        { t: "biquad", type: "lowshelf", f: 55, q: 0.7, g: 4 },
        { t: "biquad", type: "peaking", f: 3500, q: 0.8, g: -1.5 },
        { t: "biquad", type: "highshelf", f: 12000, q: 0.7, g: -1 },
      ],
    },
  };
  const ORDER = ["normal", "phone", "airpods", "car", "laptop", "mono", "club"];

  /** Profil -> filtre parametre listesi (kopya). Bilinmeyen kimlik -> normal (bos zincir). */
  function profileNodes(id) {
    const p = PROFILES[id] || PROFILES.normal;
    return p.nodes.map((n) => Object.assign({}, n));
  }
  function profile(id) {
    const k = PROFILES[id] ? id : "normal";
    return { id: k, label: PROFILES[k].label, badge: PROFILES[k].badge, nodes: profileNodes(k) };
  }
  const list = () => ORDER.map((k) => ({ id: k, label: PROFILES[k].label, badge: PROFILES[k].badge }));

  /** Genislik matrisi: L' = a*L + b*R, R' = b*L + a*R  (w=1 degismez, w=0 mono (L+R)/2). */
  function widthMatrix(w) {
    w = Math.max(0, Math.min(1, Number(w)));
    return { a: (1 + w) / 2, b: (1 - w) / 2 };
  }
  /** Yumusak kirpma egrisi (tanh, k: 0..1 doygunluk). Birim kazancli bolgede ~dogrusal. */
  function shaperCurve(k, n = 1024) {
    const c = new Float32Array(n);
    const d = 1 + 9 * Math.max(0, Math.min(1, Number(k)));
    const norm = Math.tanh(d);
    for (let i = 0; i < n; i++) { const x = (i / (n - 1)) * 2 - 1; c[i] = Math.tanh(d * x) / norm; }
    return c;
  }

  /** Web Audio zinciri: {input, output, nodes}. Normal profilde input === output'a dogrudan baglidir. */
  function build(ac, id) {
    const input = ac.createGain();
    const output = ac.createGain();
    const made = [input, output];
    let cur = input;
    for (const n of profileNodes(id)) {
      if (n.t === "biquad") {
        const b = ac.createBiquadFilter();
        b.type = n.type; b.frequency.value = n.f; b.Q.value = n.q ?? 0.707;
        if (n.g != null) b.gain.value = n.g;
        cur.connect(b); cur = b; made.push(b);
      } else if (n.t === "width") {
        const { a, b } = widthMatrix(n.w);
        const sp = ac.createChannelSplitter(2), mg = ac.createChannelMerger(2);
        const g = [a, b, b, a].map((v) => { const x = ac.createGain(); x.gain.value = v; return x; });
        cur.connect(sp);
        sp.connect(g[0], 0); sp.connect(g[1], 1); g[0].connect(mg, 0, 0); g[1].connect(mg, 0, 0);   // L'
        sp.connect(g[2], 0); sp.connect(g[3], 1); g[2].connect(mg, 0, 1); g[3].connect(mg, 0, 1);   // R'
        cur = mg; made.push(sp, mg, ...g);
      } else if (n.t === "shaper") {
        const ws = ac.createWaveShaper();
        ws.curve = shaperCurve(n.k);
        ws.oversample = "2x";
        cur.connect(ws); cur = ws; made.push(ws);
      } else if (n.t === "comp") {
        const c = ac.createDynamicsCompressor();
        c.threshold.value = n.thr; c.ratio.value = n.ratio; c.knee.value = n.knee; c.attack.value = n.att; c.release.value = n.rel;
        cur.connect(c); cur = c; made.push(c);
      }
    }
    cur.connect(output);
    return { input, output, nodes: made, id: PROFILES[id] ? id : "normal" };
  }
  function dispose(chain) {
    for (const n of chain?.nodes || []) { try { n.disconnect(); } catch {} }
  }

  root.BeatSim = { PROFILES, ORDER, list, profile, profileNodes, widthMatrix, shaperCurve, build, dispose };
})(typeof window !== "undefined" ? window : globalThis);
