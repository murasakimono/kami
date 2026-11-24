"use strict";
/* Kami Beat Asama 2b (window.BeatClean): "Temizle" paneli — oner -> onayla, YIKICI DEGIL.
   - Hedef: secili klip ya da kanalin tum klipleri (her kaynak dosya ayri islenir; ayni dosyayi kullanan klipler
     ayni temizlik dosyasini paylasir).
   - Oner: api.beat_clean_analyze (arka plan) -> gurultu tabani + nefes bolgeleri + tik sayisi; panel onerilen
     ac/kapa + siddeti kurar, nefesler zaman cizelgesinde ince isaretlerle gorunur (tikla: tek tek ac/kapa).
   - Uygula: api.beat_clean_apply (arka plan + ilerleme) -> recordings/_clean/<kaynak>_<ayar>.wav; klibe
     clean = {noise, breath, click, file, src, key} yazilir (tek geri al). Ham dosya hic degismez.
   - Temizligi kaldir: clean alani silinir. A/B: Temiz / Ham (zaman cizelgesi kaynagi degistirir, efektli onizleme
     Python'a ham kopyayi yollar).
   - Gelismis model (resemble-enhance, MIT): yalniz "Gelismis temizlik modelini indir" dugmesiyle, boyut ve
     kaynak gosterilip onay alindiktan sonra kurulur. */
(function (root) {
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const DEF = {
    noise: { on: true, strength: 50, method: "auto" },
    breath: { on: true, mode: "reduce", db: -10, regions: [] },
    click: { on: true, strength: 50 },
  };
  const clone = (o) => JSON.parse(JSON.stringify(o));

  /** o: { el, api, runJob, getProj, edit, onStatus, tl(), onApplied() } */
  function create(o) {
    const st = {
      target: null,                // { tid, cid|"" }
      settings: clone(DEF),
      sugg: new Map(),             // path -> analiz sonucu (nefes bolgeleri burada; uygulanana kadar projeye yazilmaz)
      busy: false,
      model: null,
    };
    const P = () => o.getProj();
    const $ = (sel) => o.el.querySelector(sel);

    function targetClips() {
      const T = st.target;
      const tr = (P()?.tracks || []).find((t) => t.id === T?.tid);
      if (!tr) return { tr: null, clips: [] };
      const clips = (tr.clips || []).filter((c) => c.path && (!T.cid || c.id === T.cid));
      return { tr, clips };
    }
    const pathsOf = (clips) => [...new Set(clips.map((c) => c.path))];
    function regionsFor(path) {
      const { clips } = targetClips();
      const c = clips.find((x) => x.path === path && x.clean?.breath?.regions);
      if (c) return clone(c.clean.breath.regions);
      return clone(st.sugg.get(path)?.breath?.regions || []);
    }
    /** Zaman cizelgesi: henuz uygulanmamis onerilen nefesler (klipte clean yoksa). */
    function breathSuggest(c) {
      if (c.clean?.breath?.regions) return null;
      return st.sugg.get(c.path)?.breath?.regions || null;
    }

    function open(tid, cid) {
      st.target = { tid, cid: cid || "" };
      st.note = null;
      const { tr, clips } = targetClips();
      const withClean = clips.find((c) => c.clean);
      if (withClean) {
        const cl = withClean.clean;
        st.settings = { noise: Object.assign({}, DEF.noise, cl.noise), breath: Object.assign({}, DEF.breath, cl.breath, { regions: [] }),
                        click: Object.assign({}, DEF.click, cl.click) };
      }
      o.el.hidden = false;
      render();
      loadModel();
      if (!clips.length) setNote(tr ? "Bu hedefte ses klibi yok." : "Kanal seç.");
    }
    function close() { o.el.hidden = true; st.target = null; o.tl()?.render(); }
    function setNote(t, kind) {
      st.note = { t: t || "", kind: kind || "" };          // render() sonrasi da kalsin
      const n = $("#clNote");
      if (n) { n.textContent = st.note.t; n.dataset.kind = st.note.kind; }
    }
    function prog(on, pct, txt) {
      const b = $("#clProg");
      if (!b) return;
      b.hidden = !on;
      b.querySelector("i").style.width = `${Math.max(2, Math.min(100, pct || 0))}%`;
      b.querySelector("span").textContent = txt || "";
    }

    function render() {
      const { tr, clips } = targetClips();
      const s = st.settings;
      const nClean = clips.filter((c) => c.clean).length;
      const ab = o.tl()?.getCleanAB?.() || "clean";
      const sug = pathsOf(clips).map((p) => st.sugg.get(p)).filter(Boolean);
      const why = sug.length ? [sug[0].noise.why, `${sug.reduce((a, x) => a + x.breath.regions.length, 0)} nefes bulundu (silinmez, kısılır)`,
        `${sug.reduce((a, x) => a + x.click.count, 0)} ağız sesi/tık`] : [];
      const adv = st.model?.installed;
      o.el.innerHTML = `
        <div class="kb-cl-head">
          <b>TEMİZLE</b><span class="kb-mut">${tr ? esc(tr.name) : "—"}${st.target?.cid ? " · seçili klip" : ` · kanaldaki ${clips.length} klip`}${nClean ? ` · ${nClean} temizlenmiş` : ""}</span>
          <span class="kb-cl-ab" role="group" title="Temiz / ham karşılaştırma (yalnız dinleme)">
            <button type="button" class="btn ${ab === "clean" ? "on" : ""}" data-clab="clean">Temiz</button><button type="button" class="btn ${ab === "raw" ? "on" : ""}" data-clab="raw">Ham</button>
          </span>
          <button type="button" class="btn ic" id="clClose" title="Kapat">✕</button>
        </div>
        <div class="kb-cl-rows">
          <div class="kb-cl-row">
            <label class="kb-chk"><input type="checkbox" data-cl="noise.on" ${s.noise.on ? "checked" : ""}><span>Gürültü</span></label>
            <input type="range" min="0" max="100" step="1" data-cl="noise.strength" value="${s.noise.strength}" title="Şiddet"><b class="kb-num">${Math.round(s.noise.strength)}</b>
            <select class="kb-sel" data-cl="noise.method" title="Yöntem">
              <option value="auto" ${s.noise.method === "auto" ? "selected" : ""}>Yerel (spektral kapı)</option>
              <option value="ffmpeg" ${s.noise.method === "ffmpeg" ? "selected" : ""}>ffmpeg afftdn</option>
              <option value="advanced" ${s.noise.method === "advanced" ? "selected" : ""} ${adv ? "" : "disabled"}>Gelişmiş (resemble-enhance)${adv ? "" : " — kurulu değil"}</option>
            </select>
          </div>
          <div class="kb-cl-row">
            <label class="kb-chk"><input type="checkbox" data-cl="breath.on" ${s.breath.on ? "checked" : ""}><span>Nefes</span></label>
            <input type="range" min="-18" max="-6" step="1" data-cl="breath.db" value="${s.breath.db}" title="Kısma miktarı (dB)" ${s.breath.mode === "remove" ? "disabled" : ""}><b class="kb-num">${s.breath.mode === "remove" ? "sil" : `${s.breath.db} dB`}</b>
            <label class="kb-chk" title="Nefesi kısmak yerine tamamen sessize al"><input type="checkbox" data-cl="breath.remove" ${s.breath.mode === "remove" ? "checked" : ""}><span>Tamamen sil</span></label>
          </div>
          <div class="kb-cl-row">
            <label class="kb-chk"><input type="checkbox" data-cl="click.on" ${s.click.on ? "checked" : ""}><span>Ağız sesi</span></label>
            <input type="range" min="0" max="100" step="1" data-cl="click.strength" value="${s.click.strength}" title="Hassasiyet (yüksek = daha çok tık yakalar)"><b class="kb-num">${Math.round(s.click.strength)}</b>
          </div>
        </div>
        <div class="kb-cl-why kb-mut">${why.map((w) => `<span>• ${esc(w)}</span>`).join("") || "“Öner” kaydı inceler: gürültü tabanı, nefesler (zaman çizelgesinde işaretlenir, tıkla aç/kapa), ağız sesleri."}</div>
        <div class="kb-cl-actions">
          <button type="button" class="btn" id="clSuggest" ${clips.length && !st.busy ? "" : "disabled"}>Öner</button>
          <button type="button" class="btn ok" id="clApply" ${clips.length && !st.busy ? "" : "disabled"}>Uygula</button>
          <button type="button" class="btn" id="clRemove" ${nClean && !st.busy ? "" : "disabled"} title="Ham kayda dön (temizlik dosyası silinmez, yeniden uygulamak anında olur)">Temizliği kaldır</button>
          <span class="kb-cl-prog" id="clProg" hidden><i></i><span></span></span>
          <span class="kb-cl-note" id="clNote" data-kind="${esc(st.note?.kind || "")}">${esc(st.note?.t || "")}</span>
        </div>
        <div class="kb-cl-adv kb-mut" id="clAdv">${advHtml()}</div>`;
    }
    function advHtml() {
      const m = st.model;
      if (!m) return "";
      if (m.installed) return `Gelişmiş temizlik modeli kurulu (${esc(m.name)}, ${esc(m.license)}).`;
      return `<button type="button" class="btn" id="clModel" title="${esc(m.source)}">Gelişmiş temizlik modelini indir</button>
        <span>${esc(m.name)} · ~${m.size_mb} MB · ${esc(m.license)} · ${esc(m.source)} · ${esc(m.extra)}</span>`;
    }
    async function loadModel() {
      const r = await o.api()?.beat_clean_model_info?.().catch(() => null);
      if (r?.ok) { st.model = r; const a = $("#clAdv"); if (a) a.innerHTML = advHtml(); }
    }

    function setField(path, v) {
      const [a, b] = path.split(".");
      if (path === "breath.remove") { st.settings.breath.mode = v ? "remove" : "reduce"; return; }
      st.settings[a][b] = v;
    }
    o.el.addEventListener("input", (e) => {
      const k = e.target.dataset.cl;
      if (!k || e.target.type !== "range") return;
      setField(k, Number(e.target.value));
      const lbl = e.target.nextElementSibling;
      if (lbl) lbl.textContent = k === "breath.db" ? `${e.target.value} dB` : e.target.value;
    });
    o.el.addEventListener("change", (e) => {
      const k = e.target.dataset.cl;
      if (!k) return;
      setField(k, e.target.type === "checkbox" ? e.target.checked : (e.target.type === "range" ? Number(e.target.value) : e.target.value));
      if (k === "breath.remove") render();
    });
    o.el.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b) return;
      if (b.id === "clClose") close();
      else if (b.dataset.clab) setAB(b.dataset.clab);
      else if (b.id === "clSuggest") suggest();
      else if (b.id === "clApply") apply();
      else if (b.id === "clRemove") remove();
      else if (b.id === "clModel") installModel();
    });

    function setAB(m) {
      o.tl()?.setCleanAB?.(m);
      o.onApplied?.();
      render();
      o.onStatus?.(m === "raw" ? "A/B: ham kayıt dinleniyor" : "A/B: temizlenmiş kayıt dinleniyor");
    }

    async function suggest() {
      const { clips } = targetClips();
      const paths = pathsOf(clips);
      if (!paths.length) return;
      st.busy = true; render();
      let done = 0;
      for (const p of paths) {
        prog(true, done / paths.length * 100, "İnceleniyor…");
        const r = await o.runJob("beat_clean_analyze", [p], async () => {
          const g = await o.api()?.beat_clean_progress?.().catch(() => null);
          if (g) prog(true, (done + (g.pct || 0) / 100) / paths.length * 100, g.text);
        });
        done++;
        if (r?.ok) st.sugg.set(p, r);
        else setNote("Öneri alınamadı: " + (r?.error || "?"), "warn");
      }
      st.busy = false;
      const first = st.sugg.get(paths[0]);
      if (first) {          // onerilen ac/kapa + siddet (yontem ve kullanicinin "tamamen sil" secimi korunur)
        const any = paths.map((p) => st.sugg.get(p)).filter(Boolean);
        st.settings.noise.on = any.some((x) => x.noise.suggest.on);
        st.settings.noise.strength = Math.max(...any.map((x) => x.noise.suggest.strength));
        st.settings.breath.on = any.some((x) => x.breath.regions.length);
        st.settings.click.on = any.some((x) => x.click.count > 0);
      }
      prog(false);
      render();
      o.tl()?.render();
      setNote("Öneri hazır — ayarları gözden geçir, nefes işaretlerine tıklayarak tek tek aç/kapat, sonra “Uygula”.", "on");
    }

    function settingsFor(path) {
      const s = clone(st.settings);
      s.breath.regions = regionsFor(path);
      return s;
    }
    async function apply(onlyPaths) {
      const { tr, clips } = targetClips();
      const paths = onlyPaths || pathsOf(clips);
      if (!tr || !paths.length) return;
      st.busy = true; render();
      const results = new Map();
      let done = 0;
      for (const p of paths) {
        const r = await o.runJob("beat_clean_apply", [p, settingsFor(p)], async () => {
          const g = await o.api()?.beat_clean_progress?.().catch(() => null);
          if (g) prog(true, (done + (g.pct || 0) / 100) / paths.length * 100, g.text);
        });
        done++;
        if (r?.ok && r.clean) results.set(p, r);
        else if (r?.error === "nothing_selected") { setNote("Hiçbir işlem seçili değil.", "warn"); break; }
        else setNote("Temizlik başarısız: " + (r?.error || "?"), "warn");
      }
      st.busy = false;
      prog(false);
      if (results.size) {
        o.edit(`Temizlik uygulandı (${results.size} kaynak)`, () => {
          for (const c of clips) { const r = results.get(c.path); if (r) c.clean = clone(r.clean); }
        });
        for (const p of results.keys()) st.sugg.delete(p);
        const notes = [...results.values()].flatMap((r) => r.info?.notes || []);
        const inf = [...results.values()].map((r) => r.info).filter(Boolean);
        setNote(`Temizlik hazır${inf.length ? ` · ${inf.reduce((a, x) => a + x.breaths, 0)} nefes kısıldı · ${inf.reduce((a, x) => a + x.clicks, 0)} tık · gürültü: ${inf.map((x) => x.noise_method || "—").join("/")}` : " (önbellekten)"}${notes.length ? " · " + notes.join("; ") : ""}`, "on");
        o.onApplied?.();
      }
      render();
    }
    function remove() {
      const { clips } = targetClips();
      o.edit("Temizlik kaldırıldı (ham kayıt)", () => { for (const c of clips) delete c.clean; });
      o.onApplied?.();
      render();
      setNote("Ham kayda dönüldü.");
    }
    /** Zaman cizelgesinde nefes isaretine tiklandi. */
    function toggleBreath(tid, cid, i) {
      const tr = (P()?.tracks || []).find((t) => t.id === tid);
      const c = tr?.clips?.find((x) => x.id === cid);
      if (!c) return;
      if (c.clean?.breath?.regions?.[i]) {
        // uygulanmis temizlik: ayni kaynagi kullanan kliplerde degistir + arka planda yeniden uret
        const on = c.clean.breath.regions[i][2] === false;
        o.edit(on ? "Nefes kısılacak" : "Nefese dokunulmayacak", () => {
          for (const x of tr.clips) if (x.path === c.path && x.clean?.breath?.regions?.[i]) x.clean.breath.regions[i][2] = on;
        });
        st.target = { tid, cid: "" };
        st.settings = { noise: Object.assign({}, DEF.noise, c.clean.noise), breath: Object.assign({}, DEF.breath, c.clean.breath),
                        click: Object.assign({}, DEF.click, c.clean.click) };
        apply([c.path]);
        return;
      }
      const sg = st.sugg.get(c.path);
      if (sg?.breath?.regions?.[i]) {
        sg.breath.regions[i][2] = sg.breath.regions[i][2] === false;
        o.tl()?.render();
      }
    }
    async function installModel() {
      const m = st.model;
      if (!m) return;
      if (!root.confirm?.(`${m.name} indirilsin mi?\n\nBoyut: ~${m.size_mb} MB model + PyTorch\nKaynak: ${m.source}\nLisans: ${m.license}\n\nKurulum ayar klasörüne yapılır; uygulama dosyalarına dokunulmaz.`)) return;
      const a = $("#clAdv");
      if (a) a.textContent = "Gelişmiş model kuruluyor…";
      const r = await o.runJob("beat_clean_model_install", [true], async () => {
        const g = await o.api()?.beat_clean_model_info?.().catch(() => null);
        if (g?.progress && a) a.textContent = `Kuruluyor %${g.progress.pct || 0} — ${g.progress.text || ""}`;
      });
      await loadModel();
      o.onStatus?.(r?.ok ? "Gelişmiş temizlik modeli kuruldu." : "Gelişmiş model kurulamadı: " + (r?.error || "?"));
      render();
    }

    return { open, close, render, toggleBreath, breathSuggest, isOpen: () => !o.el.hidden, target: () => st.target };
  }

  root.BeatClean = { create, DEF };
})(typeof window !== "undefined" ? window : globalThis);
