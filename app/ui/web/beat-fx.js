"use strict";
/* Kami Beat Revize 4 (window.BeatFx):
   - Efekt semasi (Python beat_fx.FX_SCHEMA -> api.beat_fx_schema) ile parametre paneli: yerlesik efektlerde
     surguler (ad, birim, aralik; log olcekli frekans/zaman), VST3'te eklentinin parametreleri (ilk 24 onemli +
     arama) ve "Eklentinin kendi penceresini ac" (ayri surec; kapaninca durum state_b64 olarak fx kaydina yazilir).
   - Efektli onizleme yoneticisi: secili (veya tum) kanallarin calma konumu cevresindeki penceresini Python'a
     bounce ile ayni yoldan isletir (api.beat_preview_render), sonucu zaman cizelgesinin islak katmanina koyar
     (BeatTimeline.setWet). Kanal imzasi (fx + klipler) degisince eski islak ses aninda birakilir (kuru calar),
     300 ms debounce ile yeniden istenir; hazir olunca 20 ms capraz gecisle efektliye gecer. */
(function (root) {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const S = { schema: {}, available: { pedalboard: false, vst: false, editor: false }, vstTop: 24 };

  function setSchema(r) {
    if (r?.schema) S.schema = r.schema;
    if (r?.available) S.available = r.available;
    if (r?.vst_top) S.vstTop = r.vst_top;
  }
  const schema = () => S.schema;
  const available = () => S.available;

  function defaultFx(type) {
    const sc = S.schema[type];
    if (!sc) return null;
    const o = { type };
    for (const p of sc.params) o[p.key] = p.default;
    return o;
  }
  function label(fx) {
    if (fx?.name) return fx.name;
    const t = String(fx?.type || "").toLowerCase();
    return S.schema[t]?.label || ({ vst3: "VST3" }[t]) || fx?.type || "FX";
  }

  // ---- surgu <-> deger (log olcek: frekans, atak/birakma) ----
  const SL = 1000;
  function toSlider(p, v) {
    v = clamp(Number(v), p.min, p.max);
    if (p.scale === "log") return Math.round(SL * Math.log(v / p.min) / Math.log(p.max / p.min));
    return Math.round(SL * (v - p.min) / (p.max - p.min));
  }
  function fromSlider(p, x) {
    const f = clamp(Number(x) / SL, 0, 1);
    let v = p.scale === "log" ? p.min * Math.pow(p.max / p.min, f) : p.min + f * (p.max - p.min);
    const st = p.step || 0.01;
    v = Math.round(v / st) * st;
    return Number(clamp(v, p.min, p.max).toFixed(st < 0.01 ? 4 : st < 1 ? 2 : 0));
  }
  function fmt(p, v) {
    v = Number(v);
    if (p.unit === "%") return `${Math.round(v * 100)}%`;
    if (p.unit === "Hz") return v >= 1000 ? `${(v / 1000).toFixed(v >= 10000 ? 1 : 2)} kHz` : `${Math.round(v)} Hz`;
    if (p.unit === ":1") return `${v.toFixed(1)}:1`;
    if (p.unit === "dB") return `${v > 0 ? "+" : ""}${v.toFixed(1)} dB`;
    if (p.unit === "ms") return `${v < 10 ? v.toFixed(1) : Math.round(v)} ms`;
    if (p.unit === "sn") return `${v.toFixed(3)} sn`;
    if (p.unit === "st") return `${v > 0 ? "+" : ""}${v.toFixed(1)} st`;
    return v.toFixed(2);
  }
  /** Rafta modul altinda kisa ozet (semadan ilk 2 parametre). */
  function summary(fx) {
    if (!fx) return "";
    const t = String(fx.type || "").toLowerCase();
    if (t === "vst3") {
      const n = Object.keys(fx.params || {}).length;
      return [fx.state_b64 ? "Ayar kayıtlı" : "", n ? `${n} parametre` : ""].filter(Boolean).join(" · ") || "VST3 Plugin";
    }
    const sc = S.schema[t];
    if (!sc) return "Aktif";
    return sc.params.slice(0, 2).map((p) => fmt(p, fx[p.key] ?? p.default)).join(" · ");
  }
  /** Kanal/klip onayarindan farkli mi (Ozel etiketi icin). */
  function chainEquals(a, b) {
    const norm = (l) => JSON.stringify((l || []).map((f) => { const o = Object.assign({}, f); delete o.name; return o; }));
    return norm(a) === norm(b);
  }

  // ---------------- Parametre paneli ----------------
  /** o: { el, fx, title, api, runJob, onInput(), onCommit(label), onStatus(t) }  — fx yerinde degistirilir. */
  function openPanel(o) {
    const fx = o.fx;
    const t = String(fx.type || "").toLowerCase();
    const el = o.el;
    el.hidden = false;
    el.dataset.type = t;
    const head = `<div class="kb-fxp-head"><b>${esc(o.title || label(fx))}</b>
      <span class="kb-fxp-sub">${t === "vst3" ? "VST3" : esc(S.schema[t]?.group || "")}</span>
      <button type="button" class="btn ic" data-fxp="reset" title="Varsayılanlara dön">↺</button>
      <button type="button" class="btn ic" data-fxp="close" title="Paneli kapat (Esc)">✕</button></div>`;
    if (t === "vst3") return openVst(o, head);
    const sc = S.schema[t];
    if (!sc) { el.innerHTML = head + `<div class="kb-mut">Bu modülün düzenlenebilir parametresi yok.</div>`; wire(o); return; }
    el.innerHTML = head + `<div class="kb-fxp-rows">` + sc.params.map((p) => {
      const v = fx[p.key] ?? p.default;
      return `<label class="kb-fxp-row" title="${esc(p.label)}: ${fmt(p, p.min)} … ${fmt(p, p.max)} (çift tık: varsayılan ${fmt(p, p.default)})">
        <span class="kb-fxp-lbl">${esc(p.label)}</span>
        <input type="range" min="0" max="${SL}" step="1" value="${toSlider(p, v)}" data-key="${esc(p.key)}">
        <span class="kb-fxp-val kb-num" data-val="${esc(p.key)}">${fmt(p, v)}</span>
      </label>`;
    }).join("") + `</div><div class="kb-fxp-foot kb-mut">${S.available.pedalboard ? "Değişiklik ~1 sn içinde efektli önizlemede duyulur." : "⚠ pedalboard kurulu değil: önizleme/bounce bu efekti atlar (yalnız Gain uygulanır)."}</div>`;
    wire(o);
  }

  function wire(o) {
    const el = o.el, fx = o.fx;
    const t = String(fx.type || "").toLowerCase();
    const sc = S.schema[t];
    let before = null;
    el.oninput = (e) => {
      const inp = e.target.closest("input[type=range][data-key]");
      if (!inp) return;
      if (before === null) before = o.snap();
      if (t === "vst3") {
        fx.params = Object.assign({}, fx.params || {}, { [inp.dataset.key]: Number(inp.value) / SL });
        const v = el.querySelector(`[data-val="${CSS.escape(inp.dataset.key)}"]`);
        if (v) v.textContent = `${Math.round(Number(inp.value) / SL * 100)}%`;
      } else {
        const p = sc.params.find((x) => x.key === inp.dataset.key);
        fx[p.key] = fromSlider(p, inp.value);
        const v = el.querySelector(`[data-val="${CSS.escape(p.key)}"]`);
        if (v) v.textContent = fmt(p, fx[p.key]);
      }
      o.onInput?.();
    };
    el.onchange = (e) => {
      if (!e.target.closest("input[type=range][data-key]")) return;
      const b = before; before = null;
      if (b !== null) o.onCommit?.(`${label(fx)}: parametre`, b);
    };
    el.ondblclick = (e) => {
      const inp = e.target.closest("input[type=range][data-key]");
      if (!inp || t === "vst3" || !sc) return;
      const p = sc.params.find((x) => x.key === inp.dataset.key);
      const b = o.snap();
      fx[p.key] = p.default;
      inp.value = toSlider(p, p.default);
      el.querySelector(`[data-val="${CSS.escape(p.key)}"]`).textContent = fmt(p, p.default);
      o.onInput?.();
      o.onCommit?.(`${label(fx)}: ${p.label} varsayılan`, b);
    };
    el.onclick = (e) => {
      const b = e.target.closest("[data-fxp]");
      if (!b) return;
      const act = b.dataset.fxp;
      if (act === "close") { closePanel(el); o.onClose?.(); }
      else if (act === "reset") {
        const bf = o.snap();
        if (t === "vst3") { delete fx.params; delete fx.state_b64; }
        else if (sc) for (const p of sc.params) fx[p.key] = p.default;
        o.onCommit?.(`${label(fx)}: varsayılan`, bf);
        o.reopen?.();
      } else if (act === "editor") openEditor(o, b);
      else if (act === "more") { o.vstLimit = (o.vstLimit || S.vstTop) + 48; loadVst(o); }
    };
  }

  function closePanel(el) { el.hidden = true; el.innerHTML = ""; el.oninput = el.onchange = el.onclick = el.ondblclick = null; }

  function openVst(o, head) {
    const el = o.el, fx = o.fx;
    const av = S.available;
    const edTitle = !av.pedalboard ? "pedalboard kurulu değil — eklenti penceresi açılamaz"
      : !av.editor ? "Eklenti penceresi yalnız Windows'ta açılır" : "Eklentinin kendi arayüzünü ayrı pencerede aç; kapatınca ayar bu modüle kaydedilir";
    el.innerHTML = head + `<div class="kb-fxp-vst">
        <button type="button" class="btn ok" data-fxp="editor" ${av.editor ? "" : "disabled"} title="${esc(edTitle)}">🎛 Eklentinin kendi penceresini aç</button>
        <input type="search" class="kb-fxp-q" placeholder="Parametre ara…" value="">
        <span class="kb-mut kb-fxp-state">${fx.state_b64 ? "✓ Pencere ayarı kayıtlı" : ""}</span>
      </div>
      ${av.editor ? "" : `<div class="kb-fxp-foot kb-mut">${esc(edTitle)}.</div>`}
      <div class="kb-fxp-rows" data-vst-rows><div class="kb-mut">${av.vst ? "Parametreler okunuyor…" : "pedalboard yok: VST parametreleri okunamıyor (Windows'ta denenecek)."}</div></div>`;
    wire(o);
    let qt = 0;
    el.querySelector(".kb-fxp-q").oninput = (e) => { clearTimeout(qt); qt = setTimeout(() => { o.vstQuery = e.target.value; loadVst(o); }, 200); };
    if (av.vst) loadVst(o);
  }

  async function loadVst(o) {
    const el = o.el, fx = o.fx;
    const box = el.querySelector("[data-vst-rows]");
    if (!box) return;
    const r = await o.api()?.beat_vst_params?.(fx.path, o.vstQuery || "", o.vstLimit || S.vstTop).catch(() => null);
    if (!el.contains(box)) return;
    if (!r?.ok) { box.innerHTML = `<div class="kb-mut">Parametreler okunamadı: ${esc(r?.error || "?")}</div>`; return; }
    const cur = fx.params || {};
    box.innerHTML = r.params.map((p) => {
      const raw = cur[p.key] ?? p.raw;
      return `<label class="kb-fxp-row" title="${esc(p.label)}${p.unit ? " (" + esc(p.unit) + ")" : ""} — eklenti değeri: ${esc(p.text)}">
        <span class="kb-fxp-lbl">${esc(p.label)}</span>
        <input type="range" min="0" max="${SL}" step="1" value="${Math.round(clamp(raw, 0, 1) * SL)}" data-key="${esc(p.key)}">
        <span class="kb-fxp-val kb-num" data-val="${esc(p.key)}">${cur[p.key] != null ? Math.round(raw * 100) + "%" : esc(p.text || Math.round(raw * 100) + "%")}</span>
      </label>`;
    }).join("") + (r.more ? `<button type="button" class="btn" data-fxp="more">+ ${r.more} parametre daha (toplam ${r.total})</button>` : "")
      + (r.params.length ? "" : `<div class="kb-mut">Eşleşen parametre yok.</div>`);
  }

  async function openEditor(o, btn) {
    const fx = o.fx;
    const old = btn.textContent;
    btn.disabled = true;
    btn.textContent = "Pencere açık… kapatınca kaydedilir";
    o.onStatus?.(`${label(fx)} penceresi açıldı — ayarlayıp pencereyi kapatınca kaydedilir.`);
    try {
      const r = await o.runJob("beat_vst_editor", [fx.path, fx.state_b64 || "", fx.params || {}]);
      if (!r?.ok) { o.onStatus?.(`Eklenti penceresi: ${r?.error || "hata"}`); return; }
      const b = o.snap();
      fx.state_b64 = r.state_b64 || "";
      // surgulerle ayarlananlar pencerede de degismis olabilir: yalniz onceden izlenen anahtarlar guncellenir
      const keep = {};
      for (const k of Object.keys(fx.params || {})) if (r.params && k in r.params) keep[k] = r.params[k];
      if (Object.keys(keep).length) fx.params = keep; else delete fx.params;
      o.onCommit?.(`${label(fx)}: pencere ayarı kaydedildi`, b);
      o.reopen?.();
    } finally {
      if (btn.isConnected) { btn.disabled = false; btn.textContent = old; }
    }
  }

  // ---------------- Efektli onizleme yoneticisi ----------------
  const WIN_DUR = 15;          // sn: calma konumundan itibaren islenen pencere
  const DEBOUNCE = 300;
  const REFILL = 4;            // pencerenin sonuna bu kadar kala sonraki pencere istenir

  /** Kanalda duyulan efekt var mi (Python track_has_fx ile ayni kural). */
  // ---- 2b: send/bus + vokale yer acma (Python beat_mixbus ile ayni kurallar) ----
  const SEND_OFF_DB = -60;
  function activeSends(tr, buses) {
    const s = tr?.sends;
    if (!s || typeof s !== "object") return {};
    const live = new Set((buses || []).filter((b) => b && !b.mute).map((b) => b.id));
    const out = {};
    for (const [k, v] of Object.entries(s)) if (live.has(k) && v !== null && Number(v) > SEND_OFF_DB) out[k] = Number(v);
    return out;
  }
  function makeRoomOn(tr) {
    const m = tr?.make_room;
    return !!(m && m.on && tr.role !== "vocal" && Number(m.depth_db ?? 3) > 0);
  }
  function vocalKeys(P, exceptId) {
    const trs = (P?.tracks || []).filter((t) => t.id !== exceptId);
    const solo = (P?.tracks || []).some((t) => t.solo);
    return trs.filter((t) => t.role === "vocal" && !t.mute && !(solo && !t.solo));
  }
  /** P (proje) verilirse send/make_room de sayilir: kanal Python'da islenmeli mi. */
  function trackHasFx(tr, P) {
    if ((tr.fx || []).some((f) => f && !f.bypass) || tr.denoise) return true;
    if ((tr.clips || []).some((c) => !c.muted && (c.fx || []).some((f) => f && !f.bypass))) return true;
    if (!P) return false;
    if (Object.keys(activeSends(tr, P.buses)).length) return true;
    return makeRoomOn(tr) && vocalKeys(P, tr.id).length > 0;
  }
  /** Islenen sesi degistiren her seyin imzasi (ses seviyesi/pan/mute haric: onlar Web Audio'da).
      2b: temizlik dosyasi (+ A/B), send'liyse surgu + ses otomasyonu + bus'lar + BPM, make_room'luysa vokal imzalari. */
  function clipSig(c, ab) {
    const cl = c.clean && c.clean.file && !c.clean.off && ab !== "raw" ? c.clean.file : "";
    return [c.id, c.path, c.src_in, c.src_out, c.start, c.gain_db, c.fade_in, c.fade_out,
      !!c.muted, c.stack_id || "", !!c.stack_active, c.fx || null, !!c.skip_track_fx,
      Number(c.pan) || 0, Number(c.tail_sec) || 0, Number(c.head_sec) || 0, cl];       // 2a: klip pan'i + kuyruk
  }
  function trackSig(tr, P, ab) {
    const clips = (tr.clips || []).map((c) => clipSig(c, ab));
    const extra = [];
    if (P) {
      const sends = activeSends(tr, P.buses);
      if (Object.keys(sends).length) extra.push(["s", sends, Number(tr.volume_db) || 0, tr.automation?.volume || [],
        (P.buses || []).filter((b) => b.id in sends), Number(P.bpm) || 120]);
      if (makeRoomOn(tr)) extra.push(["m", tr.make_room, vocalKeys(P, tr.id).map((k) => [k.id, Number(k.volume_db) || 0,
        k.automation?.volume || [], (k.fx || []), (k.clips || []).map((c) => clipSig(c, ab))])]);
    }
    return JSON.stringify([tr.fx || [], !!tr.denoise, clips, extra]);
  }
  /** A/B "ham" modunda Python'a giden kopyadan temizlik alanlari cikarilir (render ham kaynagi okur). */
  function stripClean(tr) {
    const c = JSON.parse(JSON.stringify(tr));
    for (const k of c.clips || []) delete k.clean;
    return c;
  }

  /** o: { api, tl(), getProj(), selTid(), onState({text, kind, title}) } */
  function createPreview(o) {
    const st = {
      enabled: localStorage.getItem("kb_fx_preview") !== "0",
      scope: localStorage.getItem("kb_fx_preview_scope") === "all" ? "all" : "sel",
      tr: new Map(),          // trId -> { req, timer, busy, want, skipped, engine, err }
      tick: 0,
    };
    const tl = () => o.tl();
    const ab = () => tl()?.getCleanAB?.() || "clean";
    function targets() {
      const P = o.getProj();
      if (!st.enabled || !P) return [];
      const trs = P.tracks || [];
      const list = st.scope === "all" ? trs : trs.filter((t) => t.id === o.selTid());
      return list.filter((t) => (t.clips || []).length && trackHasFx(t, P));
    }
    function ent(id) { if (!st.tr.has(id)) st.tr.set(id, { req: 0, timer: 0, busy: false }); return st.tr.get(id); }
    function dropWet(id) { if (tl()?.hasWet(id)) tl().setWet(id, null); }

    function refresh(immediate) {
      const T = tl();
      if (!T) return;
      const P = o.getProj();
      const want = new Set(targets().map((t) => t.id));
      const sel = o.selTid();
      const order = (P?.tracks || []).slice().sort((a, b) => (b.id === sel) - (a.id === sel));   // secili kanal once
      for (const tr of order) {
        const e = ent(tr.id);
        if (!want.has(tr.id)) { clearTimeout(e.timer); e.req++; e.busy = false; dropWet(tr.id); continue; }
        const sig = trackSig(tr, P, ab());
        const w = T.wetInfo()[tr.id];
        if (w && w.sig !== sig) dropWet(tr.id);        // eski efekt: aninda kuruya don
        const ph = T.getPlayhead();
        const good = w && w.sig === sig && ph >= w.t0 - 1e-3 && (ph < w.t1 - REFILL || isLoopWin(w));
        if (good || (e.busy && e.sig === sig)) continue;
        if (w && w.sig === sig) request(tr.id, sig, 0);     // ayni zincir, pencere bitiyor: beklemeden
        else request(tr.id, sig, immediate ? 0 : DEBOUNCE);
      }
      syncState();
    }
    function isLoopWin(w) {
      const L = tl()?.loopRegion?.();
      return !!L && w.t0 <= L.a + 1e-3 && w.t1 >= L.b - 1e-3;
    }
    function request(id, sig, delay) {
      const e = ent(id);
      clearTimeout(e.timer);
      e.sig = sig;
      e.busy = true;
      const my = ++e.req;
      e.timer = setTimeout(() => run(id, sig, my), delay);
      syncState();
    }
    async function run(id, sig, my) {
      const e = ent(id);
      const P = o.getProj(), T = tl();
      const tr = (P?.tracks || []).find((t) => t.id === id);
      if (!tr || !T || my !== e.req) return;
      const start = Math.max(0, T.getPlayhead() - 0.25);
      const raw = ab() === "raw";
      const snapTr = raw ? stripClean(tr) : JSON.parse(JSON.stringify(tr));
      const loop = P.loop ? JSON.parse(JSON.stringify(P.loop)) : {};
      // 2b: ctx = diger kanallar (vokale yer acma anahtari) + bus'lar + BPM
      const ctx = { tracks: (P.tracks || []).filter((t) => t.id !== id).map((t) => (raw ? stripClean(t) : JSON.parse(JSON.stringify(t)))),
                    buses: JSON.parse(JSON.stringify(P.buses || [])), bpm: Number(P.bpm) || 120 };
      let r = null;
      try { r = await o.api()?.beat_preview_render?.(P.id, id, start, WIN_DUR, "", snapTr, loop, ctx); } catch (err) { r = { ok: false, error: String(err) }; }
      if (my !== e.req) return;                  // daha yeni istek var
      if (!r?.ok) {
        e.busy = false;
        if (r?.error !== "superseded") { e.err = r?.error || "?"; syncState(); }
        return;
      }
      if (r.dry) { e.busy = false; dropWet(id); syncState(); return; }
      const buf = await decode(r.path).catch(() => null);
      const busBuf = r.bus_path ? await decode(r.bus_path).catch(() => null) : null;
      if (my !== e.req) return;
      e.busy = false;
      if (!buf) { e.err = "decode"; syncState(); return; }
      const cur = (o.getProj()?.tracks || []).find((t) => t.id === id);
      if (!cur || trackSig(cur, o.getProj(), ab()) !== sig) { refresh(); return; }   // bu arada degisti
      e.err = ""; e.skipped = r.skipped || []; e.engine = r.engine || (r.cached ? e.engine : "");
      T.setWet(id, { buf, busBuf, t0: r.t0, t1: r.t1, sig });
      syncState();
    }
    async function decode(path) {
      const m = await o.api()?.beat_media_url?.(path);
      if (!m?.ok) throw new Error("url");
      const ab = await fetch(m.direct_url || m.url).then((x) => x.arrayBuffer());
      return await tl().audioCtx().decodeAudioData(ab);
    }
    function syncState() {
      const T = tl();
      const tg = targets();
      let text, kind = "", title = "";
      if (!st.enabled) { text = "Önizleme: efektsiz"; title = "Efektli önizleme kapalı — hızlı kuru önizleme"; }
      else if (!tg.length) { text = "Önizleme: efektsiz"; title = "Seçili kanalda efekt yok"; }
      else {
        const busy = tg.some((t) => ent(t.id).busy);
        const ready = tg.filter((t) => T?.hasWet(t.id)).length;
        const errs = tg.map((t) => ent(t.id).err).filter(Boolean);
        const skipped = [...new Set(tg.flatMap((t) => ent(t.id).skipped || []))];
        if (busy) { text = "Önizleme: işleniyor…"; kind = "busy"; }
        else if (ready === tg.length) { text = skipped.length ? "Önizleme: kısmen efektli" : "Önizleme: efektli"; kind = skipped.length ? "warn" : "on"; }
        else if (errs.length) { text = "Önizleme: efektsiz (hata)"; kind = "warn"; title = errs.join(", "); }
        else { text = "Önizleme: efektsiz"; }
        if (skipped.length) title = `Atlanan modüller: ${skipped.join(", ")}${S.available.pedalboard ? "" : " — pedalboard kurulu değil"}`;
        if (!title) title = tg.map((t) => t.name).join(", ");
      }
      o.onState?.({ text, kind, title, enabled: st.enabled, scope: st.scope });
    }
    function setEnabled(on) {
      st.enabled = !!on;
      localStorage.setItem("kb_fx_preview", st.enabled ? "1" : "0");
      refresh(true);
    }
    function setScope(sc) {
      st.scope = sc === "all" ? "all" : "sel";
      localStorage.setItem("kb_fx_preview_scope", st.scope);
      refresh(true);
    }
    // calarken pencere kaydirma (sonraki pencere) icin hafif yoklama
    st.tick = setInterval(() => { if (st.enabled && tl()?.isPlaying()) refresh(); }, 500);
    return { refresh, setEnabled, setScope, state: () => ({ enabled: st.enabled, scope: st.scope }), syncState };
  }

  root.BeatFx = {
    setSchema, schema, available, defaultFx, label, summary, fmt, toSlider, fromSlider, chainEquals,
    openPanel, closePanel, createPreview, trackHasFx, trackSig, activeSends, makeRoomOn,
  };
})(typeof window !== "undefined" ? window : globalThis);
