"use strict";
/* Kami Beat Asama 2a (window.BeatStyle): tarz onayari kartlari + adlib hizli efektleri / efekt atmalari.
   Tarifler (fx zinciri, kuyruk suresi, BPM'e kilitli delay) Python'dan gelir (api.beat_quick_fx ->
   beat_style.quick_fx); buradaki klip islemleri Python beat_style.apply_throw / alternate_pan / apply_adlib ile
   birebir aynidir (node esdegerlik testi) ve BeatClips.regionSplit uzerine kuruludur. */
(function (root) {
  const BC = root.BeatClips;
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const num = (v, d = 0) => { const x = Number(v); return Number.isFinite(x) ? x : d; };
  const pyLess = (a, b) => (a < b ? -1 : a > b ? 1 : 0);      // Python str karsilastirmasi (kod noktasi)

  function setTail(c, recipe) {
    if (num(recipe.tail_sec)) c.tail_sec = Math.max(num(c.tail_sec), num(recipe.tail_sec));
    if (num(recipe.head_sec)) c.head_sec = Math.max(num(c.head_sec), num(recipe.head_sec));
  }
  /** Atma: [t0,t1) ayri klip (10 ms capraz gecis), ortadaki parcaya tarifin fx'i + kuyrugu. {clips, mid_id} */
  function applyThrow(clips, clipId, t0, t1, recipe, ids = null) {
    const r = BC.regionSplit(clips, clipId, t0, t1, BC.XFADE, ids, recipe.fx || []);
    if (r.mid_id) for (const c of r.clips) if (c.id === r.mid_id) setTail(c, recipe);
    return r;
  }
  /** Otomatik pan: baslangic sirasina gore donusumlu -amount / +amount (ayni destedeki take'ler ayni pan). */
  function alternatePan(clips, ids, amount = 0.5) {
    const out = clips.map((c) => Object.assign({}, c));
    const want = new Set(ids || []);
    const tg = out.filter((c) => want.has(c.id));
    const groups = [];
    tg.slice().sort((x, y) => (num(x.start) - num(y.start)) || pyLess(String(x.id), String(y.id))).forEach((c) => {
      const g = String(c.stack_id || c.id);
      if (!groups.includes(g)) groups.push(g);
    });
    const a = Math.max(0, Math.min(1, num(amount)));
    for (const c of tg) {
      const i = groups.indexOf(String(c.stack_id || c.id));
      c.pan = BC.r6(i % 2 === 0 ? -a : a);
    }
    return out;
  }
  /** Adlib hizli efekti (tek islem): append -> klip fx'ine eklenir; autopan; echo_tail -> her klibin son vurusu atma. */
  function applyAdlib(clips, ids, recipe, idGen = null) {
    if (recipe.mode === "autopan") return { clips: alternatePan(clips, ids, num(recipe.amount, 0.5)), ids: [...ids] };
    if (recipe.mode === "echo_tail") {
      let out = clips.map((c) => Object.assign({}, c));
      const made = [];
      const reg = num(recipe.region_sec, 0.5);
      const want = new Set(ids);
      const tg = out.filter((c) => want.has(c.id)).sort((x, y) => num(y.start) - num(x.start));
      for (const c of tg) {
        const [s, e] = BC.clipBounds(c);
        const r = applyThrow(out, c.id, Math.max(s, e - reg), e, recipe, idGen);
        out = r.clips;
        if (r.mid_id) made.push(r.mid_id);
      }
      return { clips: out, ids: made };
    }
    const want = new Set(ids || []);
    const out = clips.map((c) => {
      const d = Object.assign({}, c);
      if (want.has(d.id)) {
        d.fx = (Array.isArray(d.fx) ? d.fx : []).filter((f) => f && typeof f === "object").map((f) => Object.assign({}, f))
          .concat((recipe.fx || []).map((f) => Object.assign({}, f)));
        setTail(d, recipe);
      }
      return d;
    });
    return { clips: out, ids: [...ids] };
  }

  // ---------------- kart izgarasi ----------------
  /** presets: api.beat_style_presets().presets; active: {id, custom}; kind: 'vocal' | 'adlib' (once gosterilir). */
  function cardsHtml(presets, active, kind) {
    const list = (presets || []).slice().sort((a, b) => (b.user - a.user) || ((b.kind === kind) - (a.kind === kind)));
    return list.map((p) => {
      const on = active && active.id === p.id;
      const meter = p.user ? "Kendi önayarın" : (p.vst_total ? `Kurulu eklentiler: ${p.vst_installed}/${p.vst_total}` : "Yerleşik efektler");
      const tip = [p.desc, p.why ? `Neden: ${p.why}` : "", p.plugins?.length ? `Kullanılacak eklentiler: ${p.plugins.join(", ")}` : ""].filter(Boolean).join("\n\n");
      return `<button type="button" class="kb-sty-card ${on ? "on" : ""} ${p.user ? "user" : ""}" data-sty="${esc(p.id)}" title="${esc(tip)}">
        <span class="kb-sty-top"><b>${esc(p.name)}</b><i class="kb-sty-tag">${esc(p.genre)}</i></span>
        <span class="kb-sty-desc">${esc(p.desc)}</span>
        <span class="kb-sty-meter"><span class="kb-sty-bar" style="--k:${p.vst_total ? (p.vst_installed / p.vst_total).toFixed(2) : 0}"></span>${esc(meter)}${on && active.custom ? " · Özel" : ""}</span>
        ${p.user ? `<span class="kb-sty-del" data-stydel="${esc(p.id)}" title="Önayarı sil">✕</span>` : ""}
      </button>`;
    }).join("");
  }

  root.BeatStyle = { applyThrow, alternatePan, applyAdlib, setTail, cardsHtml };
})(typeof window !== "undefined" ? window : globalThis);
