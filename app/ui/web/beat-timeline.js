"use strict";
/* Kami Beat Asama 1a: klip tabanli zaman cizelgesi + Web Audio onizleme motoru (window.BeatTimeline).
   - Kanal basliklari beat.js'te (DOM, #tlHeads); burasi cetvel, seritler, klip kartlari, secim, surukleme,
     zoom, calma cizgisi ve oynatmayi yonetir.
   - Klip karti DOM, icindeki dalga formu yalniz GORUNEN parca kadar canvas (1 saatlik beat'te de hafif).
   - Dalga formu karolari: api.beat_waveform_tile(path, rate, index) -> path|rate|index anahtariyla onbellek.
   - Tum klip matematigi window.BeatClips (beat-clips.js) ile; duzenleme opts.edit(label, fn) uzerinden
     yapilir (geri al yigini + otomatik kayit beat.js'te). */
(function (root) {
  const BC = root.BeatClips;
  const BTR = root.BeatTransport;    // R1: izgara / kaydirma / konum ipucu saf hesaplari
  const TILE = 2048;                 // karo basina tepe
  const MAX_RATE = 256;              // Python PEAK_RATE
  const EDGE_PX = 7;                 // kirpma tutamaci genisligi
  const FADE_PX = 12;                // fade ucgeni
  const LONG_SRC_SEC = 600;          // bundan uzun kaynaklar Web Audio'ya cozulmez, <audio> akisiyla calinir
  const MIN_PPS = 1, MAX_PPS = 800;

  const clamp = (v, a, b) => Math.max(a, Math.min(b, v));
  const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const baseName = (p) => String(p || "").split(/[\\/]/).pop();
  const dbToGain = (db) => Math.pow(10, (Number(db) || 0) / 20);

  function trackColor(tr, idx) {
    if (/^#[0-9a-fA-F]{6}$/.test(String(tr.color || ""))) return tr.color;   // 1d: kanal rengi (Kanal ekle)
    if (tr.role === "beat") return "#14F195";
    const vocals = ["#9D6BFF", "#F59E0B", "#38BDF8", "#EC4899", "#A3E635"];
    return vocals[idx % vocals.length];
  }

  function create(opts) {
    const api = opts.api;
    const el = opts.el;            // { scroll, content, ruler, heads, playhead }
    const S = {
      pps: 40,                     // piksel / saniye
      playhead: 0,
      sel: new Set(),
      snapMode: "auto",            // R1: "auto" (zoom'a bagli) | 1..32 | 0 = kapali
      loopSel: "",                 // R1: secili dongu parcasi (ok tuslari): "ls" | "le" | "lm" | ""
      drag: null,
      tiles: new Map(),            // key -> peaks dizisi
      pending: new Set(),
      dur: new Map(),              // path -> kaynak suresi
      frame: 0,
      laneOrder: [],
      cleanAB: "clean",            // 2b: "clean" temizlik dosyasi | "raw" ham kaynak (A/B)
    };

    const proj = () => opts.getProj();
    const tracks = () => proj()?.tracks || [];
    const bpm = () => Number(proj()?.bpm) || 120;
    const t2x = (t) => t * S.pps;
    const x2t = (x) => x / S.pps;

    function projectEnd() {
      let end = 0;
      for (const tr of tracks()) end = Math.max(end, BC.trackEnd(tr.clips || []));
      return end;
    }
    function contentWidth() {
      const end = projectEnd();
      const viewW = el.scroll.clientWidth || 800;
      return Math.max(viewW, Math.ceil(t2x(Math.max(60, end + Math.max(20, end * 0.25)))));
    }
    function findClip(id) {
      for (const tr of tracks()) {
        const c = (tr.clips || []).find((x) => x.id === id);
        if (c) return { tr, clip: c };
      }
      return null;
    }
    /** R1: etkin izgara bolumu (Otomatik: gorunen piksel/saniyeye gore; 0 = kapali). */
    function effDiv() { return BTR.resolveGrid(S.snapMode, S.pps, bpm()); }
    function snapOn(ev) { return effDiv() > 0 && !(ev && ev.altKey); }
    function lyricFlagT() { const v = opts.lyricFlag?.(); return v === null || v === undefined || !Number.isFinite(Number(v)) ? null : Number(v); }
    // Izgara kapali / Alt: piksel -> zaman, yuvarlama yok (yalniz mikro-saniye)
    function snapT(t, ev) { return snapOn(ev) ? BTR.snapTo(t, bpm(), effDiv()) : BC.r6(Math.max(0, t)); }

    // ---- R1: surukleme ipucu balonu (baslangic zamani + bar.vurus) ----
    let tipEl = null;
    function showTip(clientX, clientY, t, label) {
      if (!tipEl) { tipEl = document.createElement("div"); tipEl.className = "kb-drag-tip kb-num"; document.body.appendChild(tipEl); }
      const p = BTR.formatPosition(t, bpm());
      tipEl.innerHTML = `${label ? `<i>${esc(label)}</i>` : ""}<b>${p.time}</b><span>${p.bbt}</span>`;
      tipEl.hidden = false;
      const w = tipEl.offsetWidth || 120;
      tipEl.style.left = clamp(clientX - w / 2, 4, (window.innerWidth || 1200) - w - 4) + "px";
      tipEl.style.top = Math.max(4, clientY - 40) + "px";
    }
    function hideTip() { if (tipEl) tipEl.hidden = true; }

    // ---------------- Cizim ----------------
    function render() {
      const trs = tracks();
      el.content.style.width = contentWidth() + "px";
      const barPx = t2x(240 / bpm());
      el.content.style.setProperty("--bar-px", barPx + "px");
      el.content.style.setProperty("--beat-px", (barPx / 4) + "px");
      S.laneOrder = trs.map((t) => t.id);
      const lanes = trs.map((tr, ti) => {
        const col = trackColor(tr, trs.filter((x, i) => i < ti && x.role !== "beat").length);
        const all = tr.clips || [];
        const clips = BC.stackView(all).map((c) => clipHtml(tr, c, col, all)).join("");
        const empty = !(tr.clips || []).length
          ? `<div class="kb-lane-empty">Boş kanal — "📂 Ses" ile ekle veya buraya çift tıkla</div>` : "";
        return `<div class="kb-tl-lane ${tr.id === opts.selTid() ? "sel" : ""} ${tr.mute ? "muted" : ""}" data-lane="${esc(tr.id)}" style="--tc:${col}">${empty}${clips}</div>` + autoLaneHtml(tr, col);
      }).join("");
      const busLanes = (proj()?.buses || []).map((b) => `<div class="kb-bus-lane ${b.mute ? "muted" : ""}" data-buslane="${esc(b.id)}"></div>`).join("");
      el.content.innerHTML = `<div class="kb-loop-band" id="tlLoopBand" hidden></div>` + lanes + busLanes + `<div class="kb-playhead" id="tlPlayhead"><i class="kb-ph-grip" title="Çalma çizgisini sürükle (ızgaraya yapışır, Alt: serbest)"></i></div>`;
      el.playhead = el.content.querySelector("#tlPlayhead");
      drawLoopBand();
      if (REC) setRecLive(REC);
      drawSections();
      drawPlayhead();
      drawRuler();
      scheduleWaves();
    }

    // ---------------- 2b: otomasyon seritleri (ses / pan) ----------------
    const BA = root.BeatAuto;
    const AUTO_H = 64;
    const AUTO = { sel: null /* {tid, param, idx} */, drag: null };
    function autoParam(tr) { return tr.auto_lane === "pan" ? "pan" : "volume"; }
    function autoPts(tr, param) { return (tr.automation && Array.isArray(tr.automation[param])) ? tr.automation[param] : []; }
    function autoLaneHtml(tr, col) {
      if (!BA || !tr.auto_lane) return "";
      const param = autoParam(tr);
      const sel = AUTO.sel && AUTO.sel.tid === tr.id && AUTO.sel.param === param ? AUTO.sel.idx : -1;
      const w = Math.max(1, parseFloat(el.content.style.width) || contentWidth());
      return `<div class="kb-auto-lane" data-auto="${esc(tr.id)}" data-param="${param}" style="--tc:${col};height:${AUTO_H}px" title="Tıkla: nokta ekle · sürükle: taşı · sağ tık / Delete: sil (ızgaraya yapışır, Alt: serbest)">${BA.laneSvg(autoPts(tr, param), param, t2x, w, AUTO_H, sel)}</div>`;
    }
    function redrawAutoLane(tid) {
      const tr = tracks().find((t) => t.id === tid);
      const ln = el.content.querySelector(`.kb-auto-lane[data-auto="${CSS.escape(tid)}"]`);
      if (!tr || !ln) return;
      const tmp = document.createElement("div");
      tmp.innerHTML = autoLaneHtml(tr, ln.style.getPropertyValue("--tc"));
      ln.replaceWith(tmp.firstChild);
    }
    function autoPointer(ev) {
      const ln = ev.target.closest(".kb-auto-lane");
      const tid = ln.dataset.auto, param = ln.dataset.param;
      const tr = tracks().find((t) => t.id === tid);
      if (!tr || !BA) return;
      ev.preventDefault();
      opts.onSelectTrack?.(tid);
      const rc = ln.getBoundingClientRect();
      const x = ev.clientX - rc.left + 0, y = ev.clientY - rc.top;
      const cx = ev.clientX - el.content.getBoundingClientRect().left;
      const before = opts.snap();
      let pts = autoPts(tr, param);
      let idx = BA.hitPoint(pts, param, cx, y, t2x, AUTO_H);
      if (idx < 0) {                          // bos yere tikla: nokta ekle (ızgaraya yapisik)
        const r = BA.insert(pts, snapT(x2t(cx), ev), BA.vOf(y, param, AUTO_H), param);
        pts = r.points; idx = r.idx;
        tr.automation = Object.assign({ volume: [], pan: [] }, tr.automation || {}, { [param]: pts });
      }
      AUTO.sel = { tid, param, idx };
      redrawAutoLane(tid);
      showTip(ev.clientX, ev.clientY, pts[idx][0], BA.fmt(pts[idx][1], param));
      const mv = (e) => {
        const cur = autoPts(tr, param);
        const t = snapT(x2t(e.clientX - el.content.getBoundingClientRect().left), e);
        const v = BA.vOf(e.clientY - ln.getBoundingClientRect().top, param, AUTO_H);
        const r = BA.move(cur, AUTO.sel.idx, t, v, param);
        tr.automation[param] = r.points;
        redrawAutoLane(tid);
        showTip(e.clientX, e.clientY, r.points[r.idx][0], BA.fmt(r.points[r.idx][1], param));
      };
      const up = () => {
        document.removeEventListener("pointermove", mv);
        document.removeEventListener("pointerup", up);
        hideTip();
        opts.commitFrom?.(param === "pan" ? "Pan otomasyonu" : "Ses otomasyonu", before);
        if (Eng.playing && !Eng.o.rec) play(currentTime());       // duyulan zarf yeniden planlansin
      };
      document.addEventListener("pointermove", mv);
      document.addEventListener("pointerup", up);
    }
    /** Secili otomasyon noktasini siler (Delete). Islediyse true. */
    function autoDeleteSelected() {
      const A = AUTO.sel;
      if (!A) return false;
      const tr = tracks().find((t) => t.id === A.tid);
      if (!tr || !autoPts(tr, A.param)[A.idx]) { AUTO.sel = null; return false; }
      opts.edit?.("Otomasyon noktası silindi", () => { tr.automation[A.param] = BA.remove(autoPts(tr, A.param), A.idx); });
      AUTO.sel = null;
      if (Eng.playing && !Eng.o.rec) play(currentTime());
      return true;
    }

    // ---------------- 1c: bolum seridi ----------------
    const SEC_COL = { intro: "#8E84A8", verse: "#9D6BFF", nakarat: "#F59E0B", "köprü": "#38BDF8", outro: "#6E6588", "ön nakarat": "#EC4899" };
    const secBase = (n) => (root.BeatLyrics ? root.BeatLyrics.sectionBase(n) : String(n || "").toLowerCase());
    const secColor = (n) => SEC_COL[secBase(n)] || "#A3E635";
    function sections() { const a = proj()?.sections; return Array.isArray(a) ? a : []; }
    function drawSections() {
      if (!el.secs) return;
      const secs = sections();
      el.secs.style.width = contentWidth() + "px";
      el.secs.innerHTML = secs.map((sc) => {
        const st = Number(sc.start) || 0, en = Number(sc.end) || 0;
        const bpl = Number(sc.bars_per_line) > 0 ? ` · ${sc.bars_per_line} bar/satır` : "";
        return `<div class="kb-sec" data-sec="${esc(sc.id)}" style="left:${t2x(st)}px;width:${Math.max(2, t2x(en - st))}px;--sc:${secColor(sc.name)}"
          title="${esc(sc.name)}${bpl} — tıkla: döngü bölgesi yap · çift tık: yeniden adlandır · sağ tık: böl / birleştir"><span>${esc(sc.name)}</span></div>`;
      }).join("") || `<div class="kb-sec-empty">Bölüm yok — Beat kanalına ses ekleyince otomatik çıkar ya da "Analiz et"e bas</div>`;
      S.curSec = undefined;
      markCurSec();
      syncSecScroll();
    }
    function syncSecScroll() { if (el.secs) el.secs.style.transform = `translateX(${-el.scroll.scrollLeft}px)`; }
    function sectionAt(t) { return sections().find((sc) => t >= Number(sc.start) && t < Number(sc.end)) || null; }
    function markCurSec() {
      if (!el.secs) return;
      const cur = sectionAt(S.playhead)?.id || "";
      if (cur === S.curSec) return;
      S.curSec = cur;
      el.secs.querySelectorAll(".kb-sec").forEach((d) => d.classList.toggle("cur", d.dataset.sec === cur));
    }
    function startSecRename(id) {
      const d = el.secs?.querySelector(`.kb-sec[data-sec="${CSS.escape(id)}"]`);
      const sc = sections().find((x) => x.id === id);
      if (!d || !sc || d.querySelector("input")) return;
      const inp = document.createElement("input");
      inp.className = "kb-sec-in";
      inp.value = sc.name || "";
      inp.maxLength = 32;
      d.querySelector("span").replaceWith(inp);
      inp.focus(); inp.select();
      let done = false;
      const finish = (ok) => {
        if (done) return;
        done = true;
        const name = inp.value.trim();
        if (ok && name && name !== sc.name) opts.edit(`Bölüm adı: ${name}`, () => { const x = sections().find((q) => q.id === id); if (x) x.name = name; });
        else drawSections();
      };
      inp.addEventListener("keydown", (e) => {
        e.stopPropagation();
        if (e.key === "Enter") { e.preventDefault(); finish(true); } else if (e.key === "Escape") { e.preventDefault(); finish(false); }
      });
      inp.addEventListener("blur", () => finish(true));
      inp.addEventListener("pointerdown", (e) => e.stopPropagation());
    }
    function splitSectionAt(id, t) {
      const sc = sections().find((x) => x.id === id);
      if (!sc) return false;
      const bar = 240 / bpm();
      const tb = Math.round(t / bar) * bar;
      if (tb <= Number(sc.start) + 1e-6 || tb >= Number(sc.end) - 1e-6) { opts.onStatus?.("Bölmek için çalma çizgisini bölümün içine (bar sınırına) getir."); return false; }
      opts.edit(`Bölüm bölündü: ${sc.name}`, () => {
        const arr = proj().sections;
        const i = arr.findIndex((x) => x.id === id);
        const a = arr[i];
        const b = Object.assign({}, a, { id: "s_" + Math.random().toString(16).slice(2, 10), start: BC.r6(tb) });
        a.end = BC.r6(tb);
        arr.splice(i + 1, 0, b);
      });
      return true;
    }
    function mergeSectionPrev(id) {
      const arr = sections();
      const i = arr.findIndex((x) => x.id === id);
      if (i <= 0) { opts.onStatus?.("İlk bölümün öncesi yok."); return; }
      opts.edit(`Bölüm birleştirildi: ${arr[i - 1].name}`, () => {
        const a2 = proj().sections;
        a2[i - 1].end = a2[i].end;
        a2.splice(i, 1);
      });
    }
    if (el.secs) {
      // tek tik kisa gecikmeyle: cift tik (yeniden adlandir) dongu bolgesini yerinden oynatmasin
      let secClickT = 0;
      el.secs.addEventListener("click", (ev) => {
        const d = ev.target.closest(".kb-sec");
        if (!d || ev.target.tagName === "INPUT") return;
        clearTimeout(secClickT);
        if (ev.detail > 1) return;
        const id = d.dataset.sec;
        secClickT = setTimeout(() => opts.onSectionClick?.(sections().find((x) => x.id === id) || null), 220);
      });
      el.secs.addEventListener("dblclick", (ev) => {
        const d = ev.target.closest(".kb-sec");
        clearTimeout(secClickT);
        if (d) { ev.preventDefault(); startSecRename(d.dataset.sec); }
      });
      el.secs.addEventListener("contextmenu", (ev) => {
        const d = ev.target.closest(".kb-sec");
        if (!d) return;
        ev.preventDefault();
        const id = d.dataset.sec;
        const sc = sections().find((x) => x.id === id);
        hideMenu();
        menu = document.createElement("div");
        menu.className = "kb-ctx";
        const inside = sc && S.playhead > Number(sc.start) && S.playhead < Number(sc.end);
        menu.innerHTML = `
          <button data-act="ren">Yeniden adlandır<kbd>çift tık</kbd></button>
          <button data-act="loop">Döngü bölgesi yap<kbd>tık</kbd></button>
          <hr>
          <button data-act="split" ${inside ? "" : "disabled"}>Çalma çizgisinden böl</button>
          <button data-act="merge">Öncekiyle birleştir</button>`;
        document.body.appendChild(menu);
        const mw = menu.offsetWidth, mh = menu.offsetHeight;
        menu.style.left = Math.min(ev.clientX, window.innerWidth - mw - 8) + "px";
        menu.style.top = Math.min(ev.clientY, window.innerHeight - mh - 8) + "px";
        menu.addEventListener("click", (e) => {
          const b = e.target.closest("button");
          if (!b || b.disabled) return;
          hideMenu();
          if (b.dataset.act === "ren") startSecRename(id);
          else if (b.dataset.act === "loop") opts.onSectionClick?.(sc || null);
          else if (b.dataset.act === "split") splitSectionAt(id, S.playhead);
          else if (b.dataset.act === "merge") mergeSectionPrev(id);
        });
      });
    }

    // 2a: klip pan'i etiketi + efekt kuyrugu (tail_sec / head_sec) klip disina tasan soluk serit
    function panTxt(c) {
      const p = Number(c.pan) || 0;
      return Math.abs(p) < 0.005 ? "" : ` · ${p < 0 ? "L" : "R"}${Math.round(Math.abs(p) * 100)}`;
    }
    function tailHtml(c, s, e, col) {
      if (c.muted || !(c.fx || []).some((f) => f && !f.bypass)) return "";
      const tl = Number(c.tail_sec) || 0, hd = Math.min(Number(c.head_sec) || 0, s);
      return (tl > 0 ? `<i class="kb-clip-tail r" style="left:${t2x(e)}px;width:${t2x(tl)}px;--tc:${col}" title="Efekt kuyruğu ${tl.toFixed(1)} sn — sonraki klibin üstüne karışır"></i>` : "")
        + (hd > 0 ? `<i class="kb-clip-tail l" style="left:${t2x(s - hd)}px;width:${t2x(hd)}px;--tc:${col}" title="Ters reverb kabarması ${hd.toFixed(1)} sn"></i>` : "");
    }
    /** 2b: klibin temizlik dosyasi duyuluyor mu (A/B "ham" modunda hayir). */
    function cleanOn(c) {
      const cl = c?.clean;
      return !!(cl && cl.file && !cl.off && (cl.src || c.path) === c.path && S.cleanAB !== "raw");
    }
    /** Dry onizleme kaynagi: gecerli temizlik dosyasi (Python beat_clean.source_path ile ayni kural) ya da ham. */
    function srcOf(c) { return cleanOn(c) ? c.clean.file : c.path; }
    function breathHtml(c) {
      const regs = c.clean?.breath?.regions || opts.breathSuggest?.(c) || [];
      if (!regs.length) return "";
      const si = Number(c.src_in) || 0, so = Number(c.src_out) || 0, L = so - si;
      if (!(L > 0)) return "";
      return regs.map((r, i) => {
        const a = Math.max(Number(r[0]), si), b = Math.min(Number(r[1]), so);
        if (b <= a) return "";
        return `<i class="kb-breath ${r[2] === false ? "off" : ""}" data-breath="${i}" style="left:${((a - si) / L * 100).toFixed(3)}%;width:${((b - a) / L * 100).toFixed(3)}%" title="Nefes ${(b - a).toFixed(2)} sn — tıkla: ${r[2] === false ? "kıs (aç)" : "dokunma (kapat)"}"></i>`;
      }).join("");
    }
    function clipHtml(tr, c, col, all) {
      const [s, e] = BC.clipBounds(c);
      const take = (tr.takes || []).find((t) => t.id === c.take_id);
      const label = take?.label || baseName(c.path) || "Klip";
      const n = c.stack_id ? BC.stackMembers(all, c.stack_id).length : 1;
      const cls = ["kb-clip", S.sel.has(c.id) ? "sel" : "", c.muted ? "muted" : "", n > 1 ? "stacked" : ""].join(" ");
      const gain = Number(c.gain_db) || 0;
      const geo = `left:${t2x(s)}px;width:${Math.max(2, t2x(e - s))}px;--tc:${col}`;
      // deste: arkada kenarlari hafif kayik kartlar (en fazla 2 gorunur) + ustte take sayisi rozeti
      const ghosts = n > 2 ? `<div class="kb-clip-ghost g2" style="${geo}"></div>` : "";
      const ghost1 = n > 1 ? `<div class="kb-clip-ghost g1" style="${geo}"></div>` : "";
      const badge = n > 1 ? `<b class="kb-stack-badge" data-h="stack" title="Take destesi — tıkla: take seç">▤ ${n}</b>` : "";
      const nfx = (c.fx || []).filter((f) => f && !f.bypass).length;   // R4: klibin kendi efekti / kanal efektini atlama
      const fxb = BC.hasClipFx(c) ? `<b class="kb-clipfx-badge" data-h="clipfx" title="Bu klibin kendi efekti var${c.skip_track_fx ? " · kanal efektini atlıyor" : ""} — tıkla: klip efektlerini aç">FX${nfx ? " " + nfx : ""}${c.skip_track_fx ? " ⤳" : ""}</b>` : "";
      const cl = cleanOn(c);   // 2b: temizlik rozeti + nefes isaretleri (tek tek ac/kapa)
      const clb = c.clean?.file ? `<b class="kb-clean-badge ${cl ? "" : "off"}" data-h="clean" title="${cl ? "Temizlenmiş kaynak çalıyor" : "Temizlik var ama ham dinleniyor (A/B)"} — tıkla: Temizle paneli">✧</b>` : "";
      return `${ghosts}${ghost1}${tailHtml(c, s, e, col)}<div class="${cls}" data-clip="${esc(c.id)}" ${n > 1 ? `data-stack="${esc(c.stack_id)}"` : ""} style="${geo}">${badge}${fxb}${clb}${breathHtml(c)}
        <canvas class="kb-clip-wf"></canvas>
        <span class="kb-clip-lbl">${esc(label)}${gain ? ` · ${gain > 0 ? "+" : ""}${gain.toFixed(1)} dB` : ""}${c.muted ? " · sessiz" : ""}${panTxt(c)}</span>
        <i class="kb-fade-h l" data-h="fi" title="Fade in (sürükle)"></i><i class="kb-fade-h r" data-h="fo" title="Fade out (sürükle)"></i>
        <i class="kb-edge l" data-h="ts"></i><i class="kb-edge r" data-h="te"></i>
      </div>`;
    }

    function drawRuler() {
      const cv = el.ruler;
      if (!cv) return;
      const dpr = window.devicePixelRatio || 1;
      const w = cv.clientWidth || 600, h = cv.clientHeight || 28;
      if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
        cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
      }
      const g = cv.getContext("2d");
      g.setTransform(dpr, 0, 0, dpr, 0, 0);
      g.clearRect(0, 0, w, h);
      const sl = el.scroll.scrollLeft;
      syncSecScroll();
      const barSec = 240 / bpm();
      const barPx = t2x(barSec);
      let every = 1;
      while (barPx * every < 44) every *= 2;
      const firstBar = Math.max(0, Math.floor(x2t(sl) / barSec));
      const lastBar = Math.ceil(x2t(sl + w) / barSec);
      g.font = "500 12px 'Chakra Petch', system-ui, sans-serif";
      g.textBaseline = "top";
      const gridDiv = effDiv();
      for (let b = firstBar; b <= lastBar; b++) {
        const x = Math.round(t2x(b * barSec) - sl) + 0.5;
        if (b % every === 0) {
          g.strokeStyle = "rgba(157,107,255,.55)";
          g.beginPath(); g.moveTo(x, 8); g.lineTo(x, h); g.stroke();
          g.fillStyle = "#8E84A8";
          g.fillText(String(b + 1), x + 4, 4);
        } else if (barPx >= 6) {
          g.strokeStyle = "rgba(157,107,255,.25)";
          g.beginPath(); g.moveTo(x, h - 9); g.lineTo(x, h); g.stroke();
        }
        // R1: etkin yapisma izgarasi cetvelde (vurus cizgileri uzun, ince bolumler kisa)
        const sub = gridDiv > 1 ? gridDiv : (gridDiv === 0 && barPx >= 48 ? 4 : 1);
        if (sub > 1 && barPx / sub >= 3) {
          for (let k = 1; k < sub; k++) {
            const onBeat = (k * 4) % sub === 0;
            g.strokeStyle = onBeat ? "rgba(157,107,255,.30)" : "rgba(157,107,255,.16)";
            const bx = Math.round(x + (barPx * k) / sub) + 0.5;
            g.beginPath(); g.moveTo(bx, h - (onBeat ? 7 : 4)); g.lineTo(bx, h); g.stroke();
          }
        }
      }
      // dongu bolgesi (1b): acikken renkli bant, kapaliyken soluk cerceve
      const L = proj()?.loop;
      if (L && Number(L.end) - Number(L.start) > 0) {
        const x0 = t2x(Number(L.start)) - sl, x1 = t2x(Number(L.end)) - sl;
        if (x1 >= 0 && x0 <= w) {
          g.fillStyle = L.on ? "rgba(245,158,11,.22)" : "rgba(142,132,168,.10)";
          g.fillRect(x0, 0, x1 - x0, h);
          g.fillStyle = L.on ? "#F59E0B" : "rgba(142,132,168,.55)";
          g.fillRect(x0, 0, x1 - x0, 3);
          g.fillRect(Math.round(x0), 0, 1, h);
          g.fillRect(Math.round(x1) - 1, 0, 1, h);
        }
      }
      // R3: "Sozler buradan baslar" bayragi
      const lf = lyricFlagT();
      if (lf !== null) {
        const fx = Math.round(t2x(lf) - sl) + 0.5;
        if (fx >= -40 && fx <= w + 4) {
          g.strokeStyle = "#EC4899"; g.lineWidth = 1.5;
          g.beginPath(); g.moveTo(fx, 2); g.lineTo(fx, h); g.stroke(); g.lineWidth = 1;
          g.fillStyle = S.flagHot ? "#F472B6" : "#EC4899";
          g.beginPath(); g.moveTo(fx, 2); g.lineTo(fx + 11, 6); g.lineTo(fx, 10); g.closePath(); g.fill();
          g.font = "600 10px 'Chakra Petch', system-ui, sans-serif";
          g.fillText("SÖZ", fx + 13, 2);
        }
      }
      // calma cizgisi isareti (R1: tutamac - surukle)
      const px = t2x(S.playhead) - sl;
      if (px >= -6 && px <= w + 6) {
        g.fillStyle = "#14F195";
        g.beginPath(); g.moveTo(px - 6, h - 11); g.lineTo(px + 6, h - 11); g.lineTo(px + 6, h - 6); g.lineTo(px, h); g.lineTo(px - 6, h - 6); g.closePath(); g.fill();
      }
    }

    function drawLoopBand() {
      const b = el.content.querySelector("#tlLoopBand");
      if (!b) return;
      const L = proj()?.loop;
      const ok = L && Number(L.end) - Number(L.start) > 0;
      b.hidden = !ok;
      if (!ok) return;
      b.classList.toggle("on", !!L.on);
      b.style.left = t2x(Number(L.start)) + "px";
      b.style.width = Math.max(1, t2x(Number(L.end) - Number(L.start))) + "px";
    }
    /** Dongu bolgesini degistirir (geri al yiginina girmez, proje ile kaydedilir). */
    function setLoop(L, quiet) {
      const P = proj();
      if (!P) return;
      if (L) {
        let a = BC.r6(Math.max(0, Number(L.start) || 0)), b = BC.r6(Math.max(0, Number(L.end) || 0));
        if (b < a) [a, b] = [b, a];
        P.loop = { start: a, end: b, on: L.on !== undefined ? !!L.on : !!P.loop?.on };
      } else P.loop = null;
      drawLoopBand();
      drawRuler();
      if (!quiet) opts.onLoopChange?.(P.loop);
    }

    function drawPlayhead() {
      if (el.playhead) el.playhead.style.transform = `translateX(${t2x(S.playhead)}px)`;
      markCurSec();
      opts.onTime?.(S.playhead);
    }

    // ---- dalga formu karolari ----
    function rateFor() {
      let r = 1;
      while (r < S.pps && r < MAX_RATE) r *= 2;
      return r;
    }
    function tileKey(path, rate, idx) { return `${path}|${rate}|${idx}`; }
    function needTile(path, rate, idx) {
      const k = tileKey(path, rate, idx);
      if (S.tiles.has(k) || S.pending.has(k) || !api()?.beat_waveform_tile) return;
      S.pending.add(k);
      api().beat_waveform_tile(path, rate, idx, TILE).then((r) => {
        S.pending.delete(k);
        S.tiles.set(k, r?.ok ? r.peaks || [] : []);
        if (r?.duration) learnDuration(path, r.duration);
        if (S.tiles.size > 600) {                // kaba LRU: en eskiyi at
          const first = S.tiles.keys().next().value;
          S.tiles.delete(first);
        }
        scheduleWaves();
      }).catch(() => { S.pending.delete(k); S.tiles.set(k, []); });
    }
    function learnDuration(path, d) {
      if (!d || S.dur.get(path) === d) return;
      S.dur.set(path, d);
      for (const tr of tracks()) for (const c of tr.clips || []) {
        if (c.path === path && !(Number(c.src_len) > 0)) c.src_len = BC.r6(d);   // geri al'a girmeyen meta veri
      }
    }
    function peakAt(path, rate, i0, i1) {
      let m = -1;
      for (let i = i0; i <= i1; i++) {
        const idx = Math.floor(i / TILE);
        const arr = S.tiles.get(tileKey(path, rate, idx));
        if (!arr) { needTile(path, rate, idx); continue; }
        const v = arr[i - idx * TILE];
        if (v !== undefined && v > m) m = v;
      }
      return m;
    }

    function scheduleWaves() {
      if (S.frame) return;
      S.frame = requestAnimationFrame(() => { S.frame = 0; drawWaves(); drawRuler(); });
    }

    function drawWaves() {
      const sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
      const rate = rateFor();
      const dpr = window.devicePixelRatio || 1;
      for (const card of el.content.querySelectorAll(".kb-clip")) {
        const hit = findClip(card.dataset.clip);
        const cv = card.querySelector("canvas");
        if (!hit || !cv) continue;
        const c = hit.clip;
        const [s, e] = BC.clipBounds(c);
        const cx0 = t2x(s), cx1 = t2x(e);
        const v0 = Math.max(cx0, sl - 40), v1 = Math.min(cx1, sl + vw + 40);
        if (v1 <= v0) { cv.style.display = "none"; continue; }
        const lbl = card.querySelector(".kb-clip-lbl");   // ad etiketi gorunen kenara yapissin
        if (lbl) lbl.style.left = (Math.max(0, Math.min(sl - cx0, cx1 - cx0 - 60)) + 8) + "px";
        const w = Math.max(1, Math.ceil(v1 - v0)), h = Math.max(20, card.clientHeight - 4);
        cv.style.display = "block";
        cv.style.left = (v0 - cx0) + "px";
        cv.style.width = w + "px";
        cv.style.height = h + "px";
        if (cv.width !== Math.round(w * dpr) || cv.height !== Math.round(h * dpr)) {
          cv.width = Math.round(w * dpr); cv.height = Math.round(h * dpr);
        }
        const g = cv.getContext("2d");
        g.setTransform(dpr, 0, 0, dpr, 0, 0);
        g.clearRect(0, 0, w, h);
        const col = getComputedStyle(card).getPropertyValue("--tc").trim() || "#9D6BFF";
        const top = 16, mid = top + (h - top) / 2, amp = (h - top - 6) / 2;
        const gain = Math.min(2, dbToGain(c.gain_db));
        const fi = Number(c.fade_in) || 0, fo = Number(c.fade_out) || 0, len = e - s;
        g.fillStyle = col;
        g.globalAlpha = c.muted ? 0.35 : 0.9;
        for (let px = 0; px < w; px++) {
          const tl0 = x2t(v0 + px), tl1 = x2t(v0 + px + 1);
          const src0 = c.src_in + (tl0 - s), src1 = c.src_in + (tl1 - s);
          const p = peakAt(c.path, rate, Math.floor(src0 * rate), Math.max(Math.floor(src0 * rate), Math.ceil(src1 * rate) - 1));
          if (p < 0) continue;
          const rel = tl0 - s;
          let env = gain;
          if (fi > 0 && rel < fi) env *= rel / fi;
          if (fo > 0 && rel > len - fo) env *= Math.max(0, (len - rel) / fo);
          const bh = Math.max(1, Math.min(1, p * env) * amp);
          g.fillRect(px, mid - bh, 1, bh * 2);
        }
        g.globalAlpha = 1;
        // fade egrileri
        g.strokeStyle = "rgba(237,233,246,.75)";
        g.lineWidth = 1;
        const ox = cx0 - v0;
        if (fi > 0) {
          g.beginPath(); g.moveTo(ox, h - 2); g.lineTo(ox + t2x(fi), top); g.stroke();
          g.fillStyle = "rgba(6,4,10,.35)";
          g.beginPath(); g.moveTo(ox, top); g.lineTo(ox + t2x(fi), top); g.lineTo(ox, h - 2); g.closePath(); g.fill();
        }
        if (fo > 0) {
          const xe = cx1 - v0;
          g.beginPath(); g.moveTo(xe - t2x(fo), top); g.lineTo(xe, h - 2); g.stroke();
          g.fillStyle = "rgba(6,4,10,.35)";
          g.beginPath(); g.moveTo(xe - t2x(fo), top); g.lineTo(xe, top); g.lineTo(xe, h - 2); g.closePath(); g.fill();
        }
      }
    }

    // ---------------- Zoom / kaydirma ----------------
    function setZoom(pps, anchorX) {
      pps = clamp(pps, MIN_PPS, MAX_PPS);
      const ax = anchorX ?? (t2x(S.playhead) - el.scroll.scrollLeft);
      const safeAx = clamp(ax, 0, el.scroll.clientWidth);
      const tAnchor = x2t(el.scroll.scrollLeft + safeAx);
      S.pps = pps;
      render();
      el.scroll.scrollLeft = Math.max(0, t2x(tAnchor) - safeAx);
      opts.onZoom?.(S.pps);
    }
    const zoomBy = (f, ax) => setZoom(S.pps * f, ax);
    function fit() {
      const end = projectEnd() || 60;
      const vw = (el.scroll.clientWidth || 800) - 40;
      S.pps = clamp(vw / (end * 1.05), MIN_PPS, MAX_PPS);
      render();
      el.scroll.scrollLeft = 0;
      opts.onZoom?.(S.pps);
    }
    function ensureVisible(t) {
      const x = t2x(t), sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
      if (x < sl || x > sl + vw - 30) el.scroll.scrollLeft = Math.max(0, x - vw * 0.15);
    }

    el.scroll.addEventListener("scroll", () => {
      if (el.heads) el.heads.scrollTop = el.scroll.scrollTop;
      scheduleWaves();
    }, { passive: true });
    el.scroll.addEventListener("wheel", (ev) => {
      if (!ev.ctrlKey) {
        // dikey tasma yoksa (birkac kanal) tekerlek yatay kaydirsin
        if (!ev.shiftKey && el.scroll.scrollHeight <= el.scroll.clientHeight + 1 && Math.abs(ev.deltaY) > Math.abs(ev.deltaX)) {
          ev.preventDefault();
          el.scroll.scrollLeft += ev.deltaY;
        }
        return;
      }
      ev.preventDefault();
      const rc = el.scroll.getBoundingClientRect();
      zoomBy(ev.deltaY < 0 ? 1.2 : 1 / 1.2, ev.clientX - rc.left);
    }, { passive: false });
    window.addEventListener("resize", () => { render(); });

    // ---------------- Calma cizgisi / cetvel ----------------
    function setPlayhead(t, keepPlaying = true) {
      S.playhead = Math.max(0, Number(t) || 0);
      drawPlayhead();
      drawRuler();
      if (keepPlaying && Eng.playing) play(S.playhead);
    }
    function rulerT(ev) {
      const rc = el.ruler.getBoundingClientRect();
      return x2t(ev.clientX - rc.left + el.scroll.scrollLeft);
    }
    function rulerSeek(ev) { setPlayhead(snapT(rulerT(ev), ev), false); }
    function rulerX(ev) {
      const rc = el.ruler.getBoundingClientRect();
      return { x: ev.clientX - rc.left + el.scroll.scrollLeft, y: ev.clientY - rc.top };
    }
    function loopHit(ev) {
      const L = proj()?.loop;
      if (!L || !(Number(L.end) > Number(L.start))) return "";
      const { x } = rulerX(ev);
      const x0 = t2x(Number(L.start)), x1 = t2x(Number(L.end));
      if (Math.abs(x - x0) <= 6) return "ls";
      if (Math.abs(x - x1) <= 6) return "le";
      if (x > x0 && x < x1) return "lm";
      return "";
    }
    /** R1/R3: cetvelde neye basildi: calma cizgisi tutamaci > soz bayragi > dongu kenari/ici. */
    function rulerHit(ev) {
      const { x, y } = rulerX(ev);
      if (Math.abs(x - t2x(S.playhead)) <= 7) return "ph";
      const lf = lyricFlagT();
      if (lf !== null) {
        const fx = t2x(lf);
        if (Math.abs(x - fx) <= 4 || (y <= 13 && x >= fx - 2 && x <= fx + 34)) return "flag";
      }
      return loopHit(ev);
    }
    el.ruler.addEventListener("pointermove", (ev) => {
      if (ev.buttons) return;
      const h = rulerHit(ev);
      el.ruler.style.cursor = h === "ph" || h === "ls" || h === "le" || h === "flag" ? "ew-resize" : h === "lm" ? "grab" : "text";
      const hot = h === "flag";
      if (hot !== !!S.flagHot) { S.flagHot = hot; drawRuler(); }
    });
    el.ruler.addEventListener("pointerleave", () => { if (S.flagHot) { S.flagHot = false; drawRuler(); } });
    // Cetvel: tikla = konum; surukle = dongu bolgesi ciz (izgaraya yapisir, Alt: serbest); bandin kenari = boyutla,
    // ici = tasi; calma cizgisi tutamaci = surukle (sessiz); soz bayragi = surukle, cift tik = calma cizgisine;
    // Ctrl+surukle = eski kaydirma (scrub).
    el.ruler.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0 || REC) return;
      const t0 = rulerT(ev);
      const x0 = ev.clientX;
      const mode = ev.ctrlKey ? "scrub" : (rulerHit(ev) || "new");
      const L0 = proj()?.loop ? Object.assign({}, proj().loop) : null;
      const wasPlaying = Eng.playing;
      const flag0 = lyricFlagT();
      let moved = false;
      if (mode === "scrub") { if (wasPlaying) stopEngine(); rulerSeek(ev); }
      if (mode === "ph") { if (wasPlaying) stopEngine(); S.loopSel = ""; }
      if (mode === "ls" || mode === "le" || mode === "lm") S.loopSel = mode;
      else if (mode !== "flag") S.loopSel = "";
      el.ruler.setPointerCapture(ev.pointerId);
      const mv = (e) => {
        if (mode === "scrub") { rulerSeek(e); return; }
        if (!moved && Math.abs(e.clientX - x0) < (mode === "ph" || mode === "flag" ? 1 : 4)) return;
        moved = true;
        const t = rulerT(e);
        if (mode === "ph") {
          setPlayhead(snapT(t, e), false);
          showTip(e.clientX, e.clientY, S.playhead, "Çalma");
          return;
        }
        if (mode === "flag") {
          const nt = snapT(flag0 + (t - t0), e);
          opts.onLyricStart?.(nt, false);
          showTip(e.clientX, e.clientY, nt, "Sözler");
          drawRuler();
          return;
        }
        let tipT = null;
        if (mode === "new") { setLoop({ start: snapT(Math.min(t0, t), e), end: snapT(Math.max(t0, t), e), on: true }, true); tipT = t < t0 ? proj()?.loop?.start : proj()?.loop?.end; }
        else if (mode === "ls") { setLoop({ start: snapT(t, e), end: L0.end }, true); tipT = proj()?.loop?.start; }
        else if (mode === "le") { setLoop({ start: L0.start, end: snapT(t, e) }, true); tipT = proj()?.loop?.end; }
        else if (mode === "lm") {
          const ln = L0.end - L0.start;
          const ns = Math.max(0, snapT(L0.start + (t - t0), e));
          setLoop({ start: ns, end: ns + ln }, true);
          tipT = ns;
        }
        if (tipT != null) showTip(e.clientX, e.clientY, tipT, mode === "le" || (mode === "new" && t >= t0) ? "Döngü sonu" : "Döngü başı");
      };
      const up = (e) => {
        el.ruler.removeEventListener("pointermove", mv);
        el.ruler.removeEventListener("pointerup", up);
        el.ruler.removeEventListener("pointercancel", up);
        hideTip();
        if (mode === "scrub") { if (wasPlaying) play(S.playhead); return; }
        if (mode === "ph") { if (wasPlaying) play(S.playhead); return; }    // birakinca oradan devam
        if (mode === "flag") {
          if (moved) opts.onLyricStart?.(lyricFlagT(), true);
          return;
        }
        if (!moved) {                                  // tiklama: konum
          if (wasPlaying) stopEngine();
          rulerSeek(e);
          if (wasPlaying) play(S.playhead);
          return;
        }
        const P = proj();
        if (P?.loop && P.loop.end - P.loop.start < 0.05) setLoop(L0, true);   // cok kisa: eskiye don
        if (mode === "new") S.loopSel = "lm";
        opts.onLoopChange?.(proj()?.loop);
        if (Eng.playing) play(currentTime());           // yeni dongu hemen gecerli olsun
      };
      el.ruler.addEventListener("pointermove", mv);
      el.ruler.addEventListener("pointerup", up);
      el.ruler.addEventListener("pointercancel", up);
    });
    el.ruler.addEventListener("dblclick", (ev) => {
      if (rulerHit(ev) !== "flag") return;
      opts.onLyricStart?.(BC.r6(S.playhead), true);   // cift tik: bayrak calma cizgisine
      drawRuler();
    });
    function toggleLoop() {
      const P = proj();
      if (!P) return null;
      if (!P.loop || !(P.loop.end - P.loop.start >= 0.05)) {
        // bolge yoksa: secili klibin sinirlari, yoksa calma cizgisinden 4 bar
        const h = [...S.sel].map(findClip).find(Boolean);
        if (h) { const [a, b] = BC.clipBounds(h.clip); setLoop({ start: a, end: b, on: true }, true); }
        else {
          const bar = 240 / bpm();
          const a = BC.snapTime(S.playhead, bpm(), 1);
          setLoop({ start: a, end: a + 4 * bar, on: true }, true);
        }
      } else setLoop({ start: P.loop.start, end: P.loop.end, on: !P.loop.on }, true);
      opts.onLoopChange?.(P.loop);
      if (Eng.playing && !Eng.o.rec) play(currentTime());
      return P.loop;
    }

    // ---------------- R1: ok tusu kaydirma (izgara adimi / 10 ms / 1 ms) ----------------
    /** Secili klip(ler)i kaydirir (deste uyeleri birlikte). Dondurur: en soldaki klibin yeni baslangici ya da null. */
    function nudgeSelected(dir, mode) {
      if (!S.sel.size) return null;
      const group = groupWithStacks([...S.sel]);
      if (!group.length) return null;
      const before = opts.snap();
      const ref = Math.min(...group.map((g) => Number(g.clip.start) || 0));
      let delta = BTR.nudgeTime(ref, dir, mode, bpm(), effDiv()) - ref;
      if (ref + delta < 0) delta = -ref;
      if (Math.abs(delta) < 1e-9) return BC.r6(ref);
      for (const g of group) {
        const tr = tracks().find((t) => t.id === g.trId);
        if (tr) tr.clips = BC.move(tr.clips, g.clip.id, (Number(g.clip.start) || 0) + delta);
      }
      (opts.commitNudge || opts.commitFrom)("Klip kaydırıldı", before);
      render();
      return BC.r6(ref + delta);
    }
    function nudgePlayhead(dir, mode) {
      const t = BTR.nudgeTime(Eng.playing ? currentTime() : S.playhead, dir, mode, bpm(), effDiv());
      setPlayhead(t);
      ensureVisible(t);
      return t;
    }
    /** Dongu secildiyse (cetvelde kenarina/icine basildi): kenari ya da tum bandi kaydirir. */
    function nudgeLoop(dir, mode) {
      const L = proj()?.loop;
      if (!S.loopSel || !L || !(L.end - L.start > 0)) return null;
      const g = (t) => BTR.nudgeTime(t, dir, mode, bpm(), effDiv());
      if (S.loopSel === "ls") { const a = Math.min(g(L.start), L.end - 0.05); setLoop({ start: a, end: L.end }, true); }
      else if (S.loopSel === "le") { const b = Math.max(g(L.end), L.start + 0.05); setLoop({ start: L.start, end: b }, true); }
      else { const a = g(L.start); setLoop({ start: a, end: a + (L.end - L.start) }, true); }
      opts.onLoopChange?.(proj()?.loop);
      if (Eng.playing && !Eng.o.rec) play(currentTime());
      const P = proj().loop;
      return S.loopSel === "le" ? P.end : P.start;
    }

    // ---------------- Secim + surukleme ----------------
    function refreshSelClasses() {
      for (const card of el.content.querySelectorAll(".kb-clip")) card.classList.toggle("sel", S.sel.has(card.dataset.clip));
      opts.onSelection?.(S.sel);
    }
    function select(id, additive) {
      if (additive) { if (S.sel.has(id)) S.sel.delete(id); else S.sel.add(id); }
      else if (!S.sel.has(id)) { S.sel.clear(); S.sel.add(id); }
      refreshSelClasses();
    }
    function clearSel() { S.sel.clear(); refreshSelClasses(); }

    function laneAtY(clientY) {
      for (const ln of el.content.querySelectorAll(".kb-tl-lane")) {
        const r = ln.getBoundingClientRect();
        if (clientY >= r.top && clientY < r.bottom) return ln.dataset.lane;
      }
      return null;
    }
    /** 1e: raftan / fikirlerden surukle-birak: birakilan kanal + izgaraya yapismis zaman (Alt: yapisma kapali). */
    function dropAt(ev) {
      const rc = el.content.getBoundingClientRect();
      return { lane: laneAtY(ev.clientY), t: Math.max(0, snapT(x2t(ev.clientX - rc.left), ev)) };
    }

    // R1: calma cizgisinin bas tutamaci (klip alaninin ustu): surukle; calarken sessiz konum degisimi, birakinca devam
    function startPlayheadDrag(ev) {
      ev.preventDefault();
      ev.stopPropagation();
      const wasPlaying = Eng.playing;
      if (wasPlaying) stopEngine();
      S.loopSel = "";
      const grip = ev.target;
      grip.setPointerCapture(ev.pointerId);
      document.body.classList.add("kb-dragging");
      const rc0 = () => el.content.getBoundingClientRect();
      const mv = (e) => {
        setPlayhead(snapT(x2t(e.clientX - rc0().left), e), false);
        showTip(e.clientX, e.clientY, S.playhead, "Çalma");
      };
      const up = () => {
        grip.removeEventListener("pointermove", mv);
        grip.removeEventListener("pointerup", up);
        grip.removeEventListener("pointercancel", up);
        document.body.classList.remove("kb-dragging");
        hideTip();
        if (wasPlaying) play(S.playhead);
      };
      grip.addEventListener("pointermove", mv);
      grip.addEventListener("pointerup", up);
      grip.addEventListener("pointercancel", up);
    }

    el.content.addEventListener("pointerdown", (ev) => {
      if (ev.button !== 0) return;
      if (ev.target.closest(".kb-ph-grip")) { if (!REC) startPlayheadDrag(ev); return; }
      hideMenu();
      S.loopSel = "";
      if (ev.target.closest(".kb-auto-lane")) { autoPointer(ev); return; }        // 2b
      if (ev.target.closest(".kb-bus-lane")) return;
      if (ev.target.classList?.contains("kb-breath")) {                          // 2b: nefes isaretini ac/kapa
        ev.preventDefault(); ev.stopPropagation();
        const cd = ev.target.closest(".kb-clip"), h = cd && findClip(cd.dataset.clip);
        if (h) opts.onBreathToggle?.(h.tr.id, h.clip.id, +ev.target.dataset.breath);
        return;
      }
      AUTO.sel = null;
      const card = ev.target.closest(".kb-clip");
      const lane = ev.target.closest(".kb-tl-lane");
      if (lane) opts.onSelectTrack?.(lane.dataset.lane);
      const rc = el.content.getBoundingClientRect();
      const tAt = x2t(ev.clientX - rc.left);
      if (!card) {
        if (!ev.shiftKey) clearSel();
        setPlayhead(snapT(tAt, ev));
        return;
      }
      const id = card.dataset.clip;
      const hit = findClip(id);
      if (!hit) return;
      const mode = ev.target.dataset.h || "move";
      if (mode === "stack") { ev.preventDefault(); select(id, false); openStackMenu(card, hit); return; }
      if (mode === "clipfx") { ev.preventDefault(); select(id, false); opts.onClipFx?.(hit.tr.id, id); return; }
      if (mode === "clean") { ev.preventDefault(); select(id, false); opts.onCleanOpen?.(hit.tr.id, id); return; }
      if (mode === "move" && (ev.ctrlKey || ev.metaKey)) {   // R4: Ctrl+surukle = klipte bolge sec ("Bu bolgeye efekt")
        ev.preventDefault();
        select(id, false);
        card.setPointerCapture(ev.pointerId);
        const [cs0, ce0] = BC.clipBounds(hit.clip);
        S.drag = { mode: "region", id, trId: hit.tr.id, x0: ev.clientX, t0: clamp(snapT(tAt, ev), cs0, ce0), cs: cs0, ce: ce0, moved: false, before: opts.snap() };
        showRegion(hit.tr.id, S.drag.t0, S.drag.t0);
        return;
      }
      if (mode === "move") select(id, ev.shiftKey);
      else if (!S.sel.has(id)) select(id, false);
      if (ev.shiftKey && mode === "move" && !S.sel.has(id)) return;   // shift ile secimden cikarildi
      ev.preventDefault();
      card.setPointerCapture(ev.pointerId);
      S.drag = {
        mode, id, trId: hit.tr.id, x0: ev.clientX, t0: tAt, moved: false,
        orig: JSON.parse(JSON.stringify(hit.clip)),
        group: groupWithStacks([...S.sel]),
        members: hit.clip.stack_id ? BC.stackMembers(hit.tr.clips, hit.clip.stack_id) : [JSON.parse(JSON.stringify(hit.clip))],
        before: opts.snap(),
      };
      document.body.classList.add("kb-dragging", `kb-drag-${mode}`);
    });

    el.content.addEventListener("pointermove", (ev) => {
      const card = ev.target.closest?.(".kb-clip");
      if (!S.drag) {
        if (card && !ev.target.dataset.h) card.style.cursor = "grab";
        return;
      }
      const D = S.drag;
      const dxT = x2t(ev.clientX - D.x0);
      if (!D.moved && Math.abs(ev.clientX - D.x0) < 3) return;
      D.moved = true;
      if (D.mode === "region") {
        const rc = el.content.getBoundingClientRect();
        D.t1 = clamp(snapT(x2t(ev.clientX - rc.left), ev), D.cs, D.ce);
        showRegion(D.trId, D.t0, D.t1);
        showTip(ev.clientX, ev.clientY, D.t1, "Bölge");
        return;
      }
      const hit = findClip(D.id);
      if (!hit) return;
      const o = D.orig;
      if (D.mode === "move") {
        let ns = o.start + dxT;                 // 1 piksel cozunurluk; izgara kapali/Alt ise yuvarlama yok
        if (snapOn(ev)) ns = BTR.snapTo(ns, bpm(), effDiv());
        let delta = ns - o.start;
        const minStart = Math.min(...D.group.map((g) => g.clip.start));
        if (minStart + delta < 0) delta = -minStart;
        for (const g of D.group) {
          const tr = tracks().find((t) => t.id === g.trId);
          if (!tr) continue;
          tr.clips = BC.move(tr.clips, g.clip.id, g.clip.start + delta);
        }
      } else if (D.mode === "ts") {            // destede tum take'ler birlikte kirpilir
        const ns = snapT(o.start + dxT, ev);
        for (const m of D.members) { const cur = findClip(m.id); if (cur) Object.assign(cur.clip, BC.trimStart(m, ns)); }
      } else if (D.mode === "te") {
        const [, oe] = BC.clipBounds(o);
        const ne = snapT(oe + dxT, ev);
        for (const m of D.members) { const cur = findClip(m.id); if (cur) Object.assign(cur.clip, BC.trimEnd(m, ne)); }
      } else if (D.mode === "fi") {
        Object.assign(hit.clip, BC.setFade(hit.clip, (Number(o.fade_in) || 0) + dxT, hit.clip.fade_out));
      } else if (D.mode === "fo") {
        Object.assign(hit.clip, BC.setFade(hit.clip, hit.clip.fade_in, (Number(o.fade_out) || 0) - dxT));
      }
      const cur = findClip(D.id);
      if (cur && (D.mode === "move" || D.mode === "ts" || D.mode === "te")) {
        const [cs, ce] = BC.clipBounds(cur.clip);
        showTip(ev.clientX, ev.clientY, D.mode === "te" ? ce : cs, D.mode === "move" ? "Başlangıç" : D.mode === "ts" ? "Baş" : "Son");
      }
      updateCards();
    });

    function endDrag(ev) {
      if (!S.drag) return;
      const D = S.drag;
      S.drag = null;
      hideTip();
      document.body.classList.remove("kb-dragging", `kb-drag-${D.mode}`);
      if (D.mode === "region") {
        const a = Math.min(D.t0, D.t1 ?? D.t0), b = Math.max(D.t0, D.t1 ?? D.t0);
        if (!D.moved || b - a < 0.05) { hideRegion(); return; }
        openRegionMenu(ev.clientX, ev.clientY, D.trId, D.id, a, b);
        return;
      }
      if (!D.moved) return;
      if (opts.snap() !== D.before) {
        const label = { move: "Taşı", ts: "Baştan kırp", te: "Sondan kırp", fi: "Fade in", fo: "Fade out" }[D.mode];
        opts.commitFrom(label, D.before);
        render();
      }
    }
    el.content.addEventListener("pointerup", endDrag);
    el.content.addEventListener("pointercancel", endDrag);

    function updateCards() {
      // surukleme sirasinda yalniz etkilenen kartlarin konum/genisligi
      for (const card of el.content.querySelectorAll(".kb-clip")) {
        const hit = findClip(card.dataset.clip);
        if (!hit) continue;
        const [s, e] = BC.clipBounds(hit.clip);
        card.style.left = t2x(s) + "px";
        card.style.width = Math.max(2, t2x(e - s)) + "px";
        for (let g = card.previousElementSibling; g && g.classList.contains("kb-clip-ghost"); g = g.previousElementSibling) {
          g.style.left = card.style.left; g.style.width = card.style.width;
        }
      }
      const need = contentWidth();
      if (parseFloat(el.content.style.width) < need) el.content.style.width = need + "px";
      scheduleWaves();
    }

    el.content.addEventListener("dblclick", (ev) => {
      if (ev.target.closest(".kb-clip")) return;
      const lane = ev.target.closest(".kb-tl-lane");
      if (!lane) return;
      const rc = el.content.getBoundingClientRect();
      opts.onPickForTrack?.(lane.dataset.lane, snapT(x2t(ev.clientX - rc.left), ev));
    });

    /** Secili kliplerin surukleme grubu; destedeki klip secildiyse tum take'leri birlikte tasinir. */
    function groupWithStacks(ids) {
      const seen = new Set(), out = [];
      for (const id of ids) {
        const h = findClip(id);
        if (!h) continue;
        const mem = h.clip.stack_id ? BC.stackMembers(h.tr.clips, h.clip.stack_id) : [h.clip];
        for (const m of mem) if (!seen.has(m.id)) { seen.add(m.id); out.push({ trId: h.tr.id, clip: JSON.parse(JSON.stringify(m)) }); }
      }
      return out;
    }

    // ---------------- Deste paneli (take secimi) ----------------
    let stackPop = null;
    function hideStackMenu() { if (stackPop) { stackPop.remove(); stackPop = null; } }
    function openStackMenu(card, hit) {
      hideMenu(); hideStackMenu();
      const sid = hit.clip.stack_id;
      if (!sid) return;
      const tr = hit.tr;
      const mem = BC.stackMembers(tr.clips, sid);
      const act = BC.stackActiveId(tr.clips, sid);
      const fmt = (x) => `${Math.floor(x / 60)}:${(x % 60).toFixed(1).padStart(4, "0")}`;
      stackPop = document.createElement("div");
      stackPop.className = "kb-stack-pop";
      stackPop.innerHTML = `<div class="kb-stack-head">Take destesi · ${mem.length}</div>` + mem.slice().reverse().map((m, i) => {
        const tk = (tr.takes || []).find((t) => t.id === m.take_id);
        const lbl = tk?.label || baseName(m.path) || `Take ${mem.length - i}`;
        return `<div class="kb-stack-row ${m.id === act ? "on" : ""}" data-id="${esc(m.id)}" style="--i:${i}">
          <span class="kb-stack-dot"></span><span class="kb-stack-lbl">${esc(lbl)}</span>
          <span class="kb-num kb-stack-len">${fmt(BC.clipLen(m))}</span>
          <button type="button" class="kb-stack-del" data-del="${esc(m.id)}" title="Bu take'i desteden sil">✕</button>
        </div>`;
      }).join("") + `<div class="kb-stack-foot">Seçilen take duyulur ve bounce'a girer</div>`;
      document.body.appendChild(stackPop);
      const rc = card.getBoundingClientRect();
      const pw = stackPop.offsetWidth, ph = stackPop.offsetHeight;
      stackPop.style.left = Math.min(Math.max(8, rc.left), window.innerWidth - pw - 8) + "px";
      stackPop.style.top = (rc.bottom + 6 + ph > window.innerHeight ? Math.max(8, rc.top - ph - 6) : rc.bottom + 6) + "px";
      stackPop.addEventListener("click", (e) => {
        const del = e.target.closest("[data-del]");
        const row = e.target.closest(".kb-stack-row");
        if (del) {
          const id = del.dataset.del;
          opts.edit("Take desteden silindi", () => { tr.clips = BC.stackRemove(tr.clips, id); });
          hideStackMenu();
          const nid = BC.stackActiveId(tr.clips, sid) || id;
          S.sel = new Set(findClip(nid) ? [nid] : []);
          refreshSelClasses();
          return;
        }
        if (!row || row.classList.contains("on")) { hideStackMenu(); return; }
        const id = row.dataset.id;
        const lbl = row.querySelector(".kb-stack-lbl").textContent;
        opts.edit(`Aktif take: ${lbl}`, () => { tr.clips = BC.stackSetActive(tr.clips, sid, id); });
        S.sel = new Set([id]);
        refreshSelClasses();
        hideStackMenu();
        animateTakeIn([id]);
      });
    }
    document.addEventListener("pointerdown", (ev) => {
      if (stackPop && !stackPop.contains(ev.target) && !ev.target.closest?.(".kb-stack-badge")) hideStackMenu();
    });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") hideStackMenu(); });

    // ---------------- R4: bolge secimi (Ctrl+surukle) ----------------
    let REGION = null;     // { trId, clipId, t0, t1 }
    function showRegion(trId, a, b) {
      let d = el.content.querySelector(".kb-region");
      const lane = el.content.querySelector(`.kb-tl-lane[data-lane="${CSS.escape(trId)}"]`);
      if (!lane) return;
      if (!d || d.parentElement !== lane) { d?.remove(); d = document.createElement("div"); d.className = "kb-region"; lane.appendChild(d); }
      const lo = Math.min(a, b), hi = Math.max(a, b);
      d.style.left = t2x(lo) + "px";
      d.style.width = Math.max(2, t2x(hi - lo)) + "px";
      d.dataset.label = `${lo.toFixed(2)}–${hi.toFixed(2)} sn`;
    }
    function hideRegion() { REGION = null; el.content.querySelector(".kb-region")?.remove(); }
    function openRegionMenu(x, y, trId, clipId, a, b) {
      hideMenu();
      REGION = { trId, clipId, t0: a, t1: b };
      menu = document.createElement("div");
      menu.className = "kb-ctx";
      // 2a: efekt atmalari — bolge ayri klip olur, ortaya efekt + kuyruk (delay proje BPM'ine kilitli)
      menu.innerHTML = `<button data-act="regionfx">Bu bölgeye efekt <kbd>${a.toFixed(2)}–${b.toFixed(2)} sn</kbd></button><hr>
        <button data-act="throw" data-kind="throw_delay" data-note="1/4">Yankı at (delay) <kbd>1/4</kbd></button>
        <button data-act="throw" data-kind="throw_delay" data-note="1/8">Yankı at (delay) <kbd>1/8</kbd></button>
        <button data-act="throw" data-kind="throw_delay" data-note="1/8d">Yankı at (delay) <kbd>nokta 1/8</kbd></button>
        <button data-act="throw" data-kind="throw_reverb">Reverb at</button>
        <button data-act="throw" data-kind="throw_phone">Telefon at</button>
        <button data-act="throw" data-kind="throw_reverse">Ters reverb</button><hr><button data-act="cancel">Vazgeç</button>`;
      document.body.appendChild(menu);
      menu.style.left = Math.min(x, window.innerWidth - menu.offsetWidth - 8) + "px";
      menu.style.top = Math.min(y + 8, window.innerHeight - menu.offsetHeight - 8) + "px";
      menu.addEventListener("click", (e) => {
        const btn = e.target.closest("button");
        if (!btn) return;
        const R = REGION;
        hideMenu(); hideRegion();
        if (btn.dataset.act === "regionfx" && R) opts.onRegionFx?.(R.trId, R.clipId, R.t0, R.t1);
        else if (btn.dataset.act === "throw" && R) opts.onThrow?.(R.trId, R.clipId, R.t0, R.t1, btn.dataset.kind, btn.dataset.note || "1/8");
      });
    }
    /** Dongu bandi klibin icindeyse 'Bu bolgeye efekt (dongu)' icin aralik. */
    function loopRangeOn(clip) {
      const L = loopRegion() || (proj()?.loop && Number(proj().loop.end) - Number(proj().loop.start) >= 0.05 ? { a: Number(proj().loop.start), b: Number(proj().loop.end) } : null);
      if (!L) return null;
      const [s, e] = BC.clipBounds(clip);
      const a = Math.max(s, L.a), b = Math.min(e, L.b);
      return b - a >= 0.05 ? { a, b } : null;
    }

    // ---------------- Sag tik menusu ----------------
    let menu = null;
    function hideMenu() { if (menu) { menu.remove(); menu = null; } }
    el.content.addEventListener("contextmenu", (ev) => {
      const aln = ev.target.closest(".kb-auto-lane");
      if (aln && BA) {                         // 2b: sag tik = otomasyon noktasini sil
        ev.preventDefault();
        const tr = tracks().find((t) => t.id === aln.dataset.auto);
        const param = aln.dataset.param;
        if (!tr) return;
        const rc = aln.getBoundingClientRect();
        const i = BA.hitPoint(autoPts(tr, param), param, ev.clientX - el.content.getBoundingClientRect().left, ev.clientY - rc.top, t2x, AUTO_H);
        if (i >= 0) { AUTO.sel = { tid: tr.id, param, idx: i }; autoDeleteSelected(); }
        return;
      }
      const card = ev.target.closest(".kb-clip");
      if (!card) return;
      ev.preventDefault();
      if (!S.sel.has(card.dataset.clip)) select(card.dataset.clip, false);
      const rc = el.content.getBoundingClientRect();
      const tAt = x2t(ev.clientX - rc.left);
      const anyMuted = [...S.sel].some((id) => findClip(id)?.clip.muted);
      const hitC = findClip(card.dataset.clip);
      const lr = hitC ? loopRangeOn(hitC.clip) : null;
      hideMenu();
      menu = document.createElement("div");
      menu.className = "kb-ctx";
      menu.innerHTML = `
        <button data-act="split">Böl<kbd>S</kbd></button>
        <button data-act="dup">Kopyala<kbd>Ctrl+D</kbd></button>
        <button data-act="del">Sil<kbd>Del</kbd></button>
        <hr>
        <button data-act="fade">Fade sıfırla</button>
        <button data-act="mute">${anyMuted ? "Klibin sesini aç" : "Klibi sessize al"}</button>
        ${findClip(card.dataset.clip)?.clip.stack_id ? `<hr><button data-act="stack">Take destesini aç</button>` : ""}
        <hr><button data-act="clipfx">Klip efektleri…</button>
        ${lr ? `<button data-act="loopfx">Bu bölgeye efekt (döngü) <kbd>${lr.a.toFixed(2)}–${lr.b.toFixed(2)}</kbd></button>
        <button data-act="loopthrow" data-kind="throw_delay" data-note="1/8">Döngüye yankı at <kbd>1/8</kbd></button>
        <button data-act="loopthrow" data-kind="throw_reverb">Döngüye reverb at</button>` : `<button data-act="hint" disabled title="Klipte Ctrl+sürükleyerek veya döngü bandıyla aralık seç">Bölgeye efekt / atma: Ctrl+sürükle</button>`}`;
      document.body.appendChild(menu);
      const mw = menu.offsetWidth, mh = menu.offsetHeight;
      menu.style.left = Math.min(ev.clientX, window.innerWidth - mw - 8) + "px";
      menu.style.top = Math.min(ev.clientY, window.innerHeight - mh - 8) + "px";
      menu.addEventListener("click", (e) => {
        const b = e.target.closest("button");
        if (!b) return;
        const act = b.dataset.act;
        hideMenu();
        if (act === "split") {
          const inside = [...S.sel].some((id) => { const h = findClip(id); if (!h) return false; const [s, en] = BC.clipBounds(h.clip); return S.playhead > s && S.playhead < en; });
          splitSelected(inside ? S.playhead : tAt);
        } else if (act === "dup") duplicateSelected();
        else if (act === "del") deleteSelected();
        else if (act === "fade") resetFadeSelected();
        else if (act === "mute") toggleMuteSelected();
        else if (act === "stack") { const h = findClip(card.dataset.clip); if (h) openStackMenu(card, h); }
        else if (act === "clipfx" && hitC) opts.onClipFx?.(hitC.tr.id, hitC.clip.id);
        else if (act === "loopfx" && hitC && lr) opts.onRegionFx?.(hitC.tr.id, hitC.clip.id, lr.a, lr.b);
        else if (act === "loopthrow" && hitC && lr) opts.onThrow?.(hitC.tr.id, hitC.clip.id, lr.a, lr.b, b.dataset.kind, b.dataset.note || "1/8");
      });
    });
    document.addEventListener("pointerdown", (ev) => { if (menu && !menu.contains(ev.target)) { hideMenu(); if (REGION) hideRegion(); } });
    document.addEventListener("keydown", (ev) => { if (ev.key === "Escape") { hideMenu(); if (REGION) hideRegion(); } });

    // ---------------- Komutlar (geri al yigini beat.js'te) ----------------
    function forSel(fnTrack) {
      const ids = [...S.sel];
      for (const tr of tracks()) {
        const mine = ids.filter((id) => (tr.clips || []).some((c) => c.id === id));
        if (mine.length) fnTrack(tr, mine);
      }
    }
    function splitSelected(t) {
      t = t ?? S.playhead;
      let targets = [...S.sel];
      if (!targets.length) {   // secim yoksa: secili kanalda calma cizgisinin altindaki klip
        const tr = tracks().find((x) => x.id === opts.selTid());
        targets = BC.stackView(tr?.clips || []).filter((c) => { const [s, e] = BC.clipBounds(c); return t > s && t < e; }).map((c) => c.id);
      }
      if (!targets.length) { opts.onStatus?.("Çalma çizgisinin altında bölünecek klip yok."); return; }
      opts.edit("Böl", () => {
        for (const tr of tracks()) {
          for (const id of targets) {
            const c0 = (tr.clips || []).find((c) => c.id === id);
            if (!c0) continue;
            // secim sol parcada kalir: sag parca tiklaninca tek basina suruklenebilsin.
            // Destede tum take'ler bolunur; sag parcalar yeni bir deste olur (aktif take ayni kalir).
            const ids = c0.stack_id ? BC.stackMembers(tr.clips, c0.stack_id).map((m) => m.id) : [id];
            const sid2 = c0.stack_id ? BC.newStackId() : "";
            for (const mid of ids) {
              const nid = BC.newId();
              tr.clips = BC.split(tr.clips, mid, t, nid);
              if (sid2) { const r = tr.clips.find((c) => c.id === nid); if (r) r.stack_id = sid2; }
            }
          }
        }
      });
    }
    function duplicateSelected() {
      if (!S.sel.size) return;
      const fresh = [];
      opts.edit("Kopyala", () => forSel((tr, ids) => {
        for (const id of ids) {
          const c0 = tr.clips.find((c) => c.id === id);
          if (c0?.stack_id) {                       // deste: tum take'ler kopyalanir, kopya yeni deste
            const sid2 = BC.newStackId();
            for (const m of BC.stackMembers(tr.clips, c0.stack_id)) {
              const nid = BC.newId();
              tr.clips = BC.duplicate(tr.clips, m.id, nid);
              const d = tr.clips.find((c) => c.id === nid);
              d.stack_id = sid2;
              d.start = BC.clipBounds(c0)[1];
              if (m.id === id) fresh.push(nid);
            }
          } else { const nid = BC.newId(); tr.clips = BC.duplicate(tr.clips, id, nid); fresh.push(nid); }
        }
      }));
      S.sel = new Set(fresh);
      render();
    }
    function deleteSelected() {
      if (!S.sel.size) return;
      opts.edit("Sil", () => forSel((tr, ids) => {
        for (const id of ids) {
          const c0 = tr.clips.find((c) => c.id === id);
          if (c0?.stack_id) { const sid = c0.stack_id; tr.clips = tr.clips.filter((c) => c.stack_id !== sid); }   // tum deste
          else tr.clips = BC.delete(tr.clips, id);
        }
      }));
      S.sel.clear();
      render();
    }
    function resetFadeSelected() {
      opts.edit("Fade sıfırla", () => forSel((tr, ids) => {
        tr.clips = tr.clips.map((c) => (ids.includes(c.id) ? BC.setFade(c, 0, 0) : c));
      }));
    }
    function toggleMuteSelected() {
      const anyMuted = [...S.sel].some((id) => findClip(id)?.clip.muted);
      opts.edit(anyMuted ? "Klip sesi aç" : "Klibi sessize al", () => forSel((tr, ids) => {
        tr.clips = tr.clips.map((c) => (ids.includes(c.id) ? Object.assign({}, c, { muted: !anyMuted }) : c));
      }));
    }
    function pruneSelection() {
      const all = new Set(); for (const tr of tracks()) for (const c of tr.clips || []) all.add(c.id);
      for (const id of [...S.sel]) if (!all.has(id)) S.sel.delete(id);
    }

    // ---------------- Web Audio onizleme motoru (1b: dongu + metronom + sayim, lookahead planlayici) ----------------
    // Tasima "dogrusal zaman" u ile ilerler; dongude u >= b iken zaman cizelgesi a..b'yi doner (BeatTransport.timelineAt).
    // Klipler segment segment (ilk segment + her tur) ~1 s onceden, metronom tiklari ~150 ms onceden AudioContext
    // saatine planlanir; setInterval yalniz planlayiciyi uyandirir, zamanlama Web Audio saatindedir (kayma yok).
    const BT = root.BeatTransport;
    const CLIP_LOOKAHEAD = 1.0, METRO_LOOKAHEAD = 0.15, SCHED_MS = 25, EDGE_RAMP = 0.003;
    const Eng = {
      ctx: null, playing: false, when: 0, uStart: 0, loop: null, nodes: new Set(), buffers: new Map(), loading: new Map(),
      raf: 0, timers: [], els: [], token: 0, sched: 0, segs: [], segNext: null, metroH: 0, metroGain: null, bus: null,
      audible: [], o: {}, anchor: null, lastLaps: 0, lastCount: null, autoStopped: false,
      dry: new Map(), dryLast: new Map(), audTr: new Set(),   // R4: kanal basina kuru dugum + duyulan kanallar
    };
    const Metro = { on: false, vol: 0.6 };
    // 2a: kalici master grafi (her calmada yeniden kurulmaz): kanallar -> mixOut ─┐
    //                                                  referans -> refOut ─┴-> simIn -> [dinleme simulatoru] -> cikis
    // Metronom bu grafa girmez (dogrudan cikis). Simulator yalniz dinlemeyi etkiler; bounce Python'da, bu grafin disinda.
    const Out = { mixOut: null, refOut: null, simIn: null, chain: null, listen: "normal", ab: "A",
                  ref: null /* {path, gain_db, start, buf} */, refNodes: new Set() };

    function ctx() {
      if (!Eng.ctx) {
        Eng.ctx = new (window.AudioContext || window.webkitAudioContext)({ latencyHint: "interactive" });
        const ac = Eng.ctx;
        Out.mixOut = ac.createGain(); Out.refOut = ac.createGain(); Out.simIn = ac.createGain();
        Out.mixOut.gain.value = Out.ab === "A" ? 1 : 0;
        Out.refOut.gain.value = Out.ab === "B" ? 1 : 0;
        Out.mixOut.connect(Out.simIn); Out.refOut.connect(Out.simIn);
        applyListen();
      }
      return Eng.ctx;
    }
    function applyListen() {
      const ac = Eng.ctx;
      if (!ac || !Out.simIn) return;
      try { Out.simIn.disconnect(); } catch {}
      if (Out.chain) root.BeatSim?.dispose(Out.chain);
      Out.chain = null;
      if (root.BeatSim && Out.listen !== "normal") {
        Out.chain = root.BeatSim.build(ac, Out.listen);
        Out.simIn.connect(Out.chain.input);
        Out.chain.output.connect(ac.destination);
      } else Out.simIn.connect(ac.destination);
    }
    /** Dinleme simulatoru profili (yalniz dinleme). Calarken aninda gecer. */
    function setListen(id) {
      Out.listen = root.BeatSim?.PROFILES?.[id] ? id : "normal";
      applyListen();
      return Out.listen;
    }
    /** A/B: 'A' miks, 'B' referans. Ayni zaman konumunda 15 ms rampa ile anlik gecis. */
    function setAB(mode) {
      Out.ab = mode === "B" ? "B" : "A";
      const ac = Eng.ctx;
      if (ac && Out.mixOut) {
        const t = ac.currentTime;
        for (const [g, v] of [[Out.mixOut, Out.ab === "A" ? 1 : 0], [Out.refOut, Out.ab === "B" ? 1 : 0]]) {
          g.gain.cancelScheduledValues(t); g.gain.setValueAtTime(g.gain.value, t); g.gain.linearRampToValueAtTime(v, t + 0.015);
        }
      }
      if (Out.ab === "B" && Eng.playing && Out.ref?.buf && !Out.refNodes.size) startRef(currentTime());
      return Out.ab;
    }
    /** Referans: {path, gain_db, start} | null. Kaynak cozulur (uzunsa <audio> akisi); calarken yeniden baslar. */
    async function setReference(r) {
      if (!r || !r.path) { stopRef(); Out.ref = null; return false; }
      const same = Out.ref && Out.ref.path === r.path;
      Out.ref = Object.assign({}, r, { buf: same ? Out.ref.buf : null });
      if (!Out.ref.buf) {
        ctx();
        const buf = await loadBuffer(r.path);
        if (!Out.ref || Out.ref.path !== r.path) return false;
        Out.ref.buf = buf;
      }
      if (Eng.playing) { stopRef(); startRef(currentTime()); }
      return !!Out.ref.buf;
    }
    function setRefGain(db) {
      if (!Out.ref) return;
      Out.ref.gain_db = Number(db) || 0;
      for (const n of Out.refNodes) if (n.__refGain) n.gain.value = dbToGain(Out.ref.gain_db);
    }
    function stopRef() {
      for (const n of Out.refNodes) { try { n.stop?.(); } catch {} try { n.pause?.(); } catch {} try { n.disconnect?.(); } catch {} }
      Out.refNodes = new Set();
    }
    /** Referans, zaman cizelgesi konumu t'ye denk gelen yerden (start + t, kendi uzunlugunda donerek) calar. */
    function startRef(t) {
      const ac = Eng.ctx, R = Out.ref;
      if (!ac || !R?.buf) return;
      const g = ac.createGain();
      g.__refGain = true;
      g.gain.value = dbToGain(R.gain_db);
      g.connect(Out.refOut);
      Out.refNodes.add(g);
      if (R.buf.stream) {
        const a = new Audio();
        a.crossOrigin = "anonymous"; a.loop = true; a.src = R.buf.url;
        const sn = ac.createMediaElementSource(a);
        sn.connect(g);
        const go = () => { try { a.currentTime = Math.max(0, (Number(R.start) || 0) + t) % Math.max(1, a.duration || 1e9); } catch {} a.play().catch(() => {}); };
        if (a.readyState >= 1) go(); else a.addEventListener("loadedmetadata", go, { once: true });
        Out.refNodes.add(sn); Out.refNodes.add(a);
        return;
      }
      const src = ac.createBufferSource();
      src.buffer = R.buf;
      src.loop = true;
      src.connect(g);
      const dur = R.buf.duration || 1;
      const at = Math.max(ac.currentTime, Eng.playing ? Eng.when : ac.currentTime);
      const off = (((Number(R.start) || 0) + Math.max(0, t) + Math.max(0, ac.currentTime - at)) % dur + dur) % dur;
      src.start(at, off);
      Out.refNodes.add(src);
    }
    async function mediaUrl(path) {
      const r = await api()?.beat_media_url?.(path).catch(() => null);
      if (!r?.ok) return null;
      if (r.duration) learnDuration(path, Number(r.duration));
      return { url: r.direct_url || r.url, duration: Number(r.duration) || 0 };
    }
    function loadBuffer(path) {
      if (Eng.buffers.has(path)) return Promise.resolve(Eng.buffers.get(path));
      if (Eng.loading.has(path)) return Eng.loading.get(path);
      const p = (async () => {
        const m = await mediaUrl(path);
        if (!m) return null;
        const dur = m.duration || S.dur.get(path) || 0;
        if (dur > LONG_SRC_SEC) { const v = { stream: true, url: m.url }; Eng.buffers.set(path, v); return v; }
        const ab = await fetch(m.url).then((r) => r.arrayBuffer());
        const buf = await ctx().decodeAudioData(ab);
        Eng.buffers.set(path, buf);
        return buf;
      })().catch(() => null).finally(() => Eng.loading.delete(path));
      Eng.loading.set(path, p);
      return p;
    }

    /** Proje dongu bolgesi (acik ve gecerliyse) {a, b}. */
    function loopRegion() {
      const L = proj()?.loop;
      if (!L || !L.on) return null;
      const a = Number(L.start) || 0, b = Number(L.end) || 0;
      return b - a >= 0.05 ? { a, b } : null;
    }
    function uNow() { return Eng.uStart + (Eng.ctx.currentTime - Eng.when); }
    function tAtU(u) { const L = Eng.loop; return L ? BT.timelineAt(u, Eng.uStart, L.a, L.b) : u; }

    function stopEngine() {
      Eng.token++;
      clearInterval(Eng.sched); Eng.sched = 0;
      for (const n of Eng.nodes) { try { n.stop?.(); } catch {} try { n.disconnect?.(); } catch {} }
      for (const t of Eng.timers) clearTimeout(t);
      for (const a of Eng.els) { try { a.pause(); a.removeAttribute("src"); a.load(); } catch {} }
      if (Eng.metroGain) { try { Eng.metroGain.disconnect(); } catch {} Eng.metroGain = null; }
      stopRef();
      for (const w of WET.values()) { for (const n of w.nodes || []) { try { n.stop?.(); } catch {} try { n.disconnect?.(); } catch {} } w.nodes = new Set(); }
      Eng.nodes = new Set(); Eng.timers = []; Eng.els = []; Eng.segs = []; Eng.segNext = null; Eng.audible = [];
      Eng.dry = new Map(); Eng.dryLast = new Map(); Eng.audTr = new Set();
      if (Eng.playing) S.playhead = currentTime();
      Eng.playing = false;
      Eng.loop = null;
      Eng.o = {};
      cancelAnimationFrame(Eng.raf);
      opts.onPlayState?.(false);
      drawPlayhead();
      drawRuler();
    }
    function currentTime() {
      if (!Eng.playing || !Eng.ctx) return S.playhead;
      return Math.max(0, tAtU(uNow()));
    }
    function track(node) { Eng.nodes.add(node); return node; }

    /** Klibin [s0, e0) kesitini ctx zamani 'at'ta calar; zarf (gain, fade, segment kenari rampalari) parca parca dogrusal. */
    function scheduleClipPart(tr, c, buf, seg, s0, e0, token) {
      const ac = Eng.ctx;
      const [s, e] = BC.clipBounds(c);
      const len = e - s;
      const at = seg.cs + (s0 - seg.ts);
      const offset = Number(c.src_in) + (s0 - s);
      const dur = e0 - s0;
      const base = dbToGain(c.gain_db);
      const fi = Number(c.fade_in) || 0, fo = Number(c.fade_out) || 0;
      const cutIn = s0 > s + 1e-6 && seg.lap > 0;            // tur basinda kesilen klip: 3 ms rampa (tik olmasin)
      const cutOut = e0 < e - 1e-6 && Number.isFinite(seg.te);
      const env = (t) => {
        const rel = t - s;
        let v = base;
        if (fi > 0 && rel < fi) v *= Math.max(0, rel / fi);
        if (fo > 0 && rel > len - fo) v *= Math.max(0, (len - rel) / fo);
        if (cutIn && t < s0 + EDGE_RAMP) v *= Math.max(0, (t - s0) / EDGE_RAMP);
        if (cutOut && t > e0 - EDGE_RAMP) v *= Math.max(0, (e0 - t) / EDGE_RAMP);
        return v;
      };
      const keys = [s0, e0];
      if (fi > 0) keys.push(s + fi);
      if (fo > 0) keys.push(e - fo);
      if (cutIn) keys.push(s0 + EDGE_RAMP);
      if (cutOut) keys.push(e0 - EDGE_RAMP);
      const pts = [...new Set(keys.filter((t) => t >= s0 && t <= e0).map((t) => Math.round(t * 1e6) / 1e6))].sort((x, y) => x - y);
      const g = track(ac.createGain());
      const toCtx = (t) => seg.cs + (t - seg.ts);
      g.gain.setValueAtTime(env(pts[0]), toCtx(pts[0]));
      for (let i = 1; i < pts.length; i++) g.gain.linearRampToValueAtTime(env(pts[i]), toCtx(pts[i]));
      const dest = Eng.dry.get(tr.id) || Eng.bus.get(tr.id);
      const cp = clamp(Number(c.pan) || 0, -1, 1);
      if (cp && ac.createStereoPanner) {        // 2a: klip pan'i (Python stereo_pan ile ayni W3C formulu)
        const pn = track(ac.createStereoPanner());
        pn.pan.value = cp;
        g.connect(pn); pn.connect(dest);
      } else g.connect(dest);
      if (buf.stream) {
        // uzun kaynak: <audio> akisi (yaklasik senkron, onizleme icin)
        const a = new Audio();
        a.crossOrigin = "anonymous";
        a.preload = "auto";
        a.src = buf.url;
        const srcNode = track(ac.createMediaElementSource(a));
        srcNode.connect(g);
        Eng.els.push(a);
        const begin = () => {
          if (token !== Eng.token) return;
          const go = () => {
            if (token !== Eng.token) return;
            const late = Math.max(0, ac.currentTime - at);
            try { a.currentTime = offset + late; } catch {}
            a.play().catch(() => {});
            Eng.timers.push(setTimeout(() => a.pause(), Math.max(0, dur - late) * 1000));
          };
          if (a.readyState >= 1) go(); else a.addEventListener("loadedmetadata", go, { once: true });
        };
        Eng.timers.push(setTimeout(begin, Math.max(0, (at - ac.currentTime) * 1000)));
      } else {
        const src = ac.createBufferSource();
        src.buffer = buf;
        src.connect(g);
        src.start(Math.max(at, ac.currentTime), offset + Math.max(0, ac.currentTime - at), Math.max(0.001, dur - Math.max(0, ac.currentTime - at)));
        track(src);
        src.onended = () => { Eng.nodes.delete(src); Eng.nodes.delete(g); try { g.disconnect(); } catch {} };
      }
    }

    function scheduleSegment(seg, token) {
      let missing = 0;
      for (const { tr, c } of Eng.audible) {
        const [s, e] = BC.clipBounds(c);
        const s0 = Math.max(s, seg.ts), e0 = Math.min(e, seg.te);
        if (e0 - s0 < 0.002) continue;
        const buf = Eng.buffers.get(srcOf(c));
        if (!buf) { missing++; continue; }
        scheduleClipPart(tr, c, buf, seg, s0, e0, token);
      }
      for (const [tid, w] of WET) if (Eng.audTr.has(tid)) scheduleWetPart(tid, w, seg, 0);
      scheduleAuto(seg);
      return missing;
    }
    /** 2b: kanal ses/pan otomasyonu bu segment icin (dongu turlari ayri segmentler -> her turda yeniden). */
    function scheduleAuto(seg) {
      if (!BA) return;
      const ac = Eng.ctx;
      const toCtx = (t) => seg.cs + (t - seg.ts);
      const from = ac.currentTime;
      for (const tr of tracks()) {
        const a = tr.automation;
        if (!a) continue;
        const vol = BA.normalize(a.volume, "volume"), pan = BA.normalize(a.pan, "pan");
        const te = Number.isFinite(seg.te) ? seg.te : Math.max(seg.ts, ...vol.map((p) => p[0]), ...pan.map((p) => p[0])) + 0.001;
        const g = Eng.bus.get(tr.id), pn = Eng.pan.get(tr.id);
        const base = Number(tr.volume_db) || 0;
        if (vol.length && g) BA.schedule(g.gain, vol, seg.ts, te, toCtx, (db) => dbToGain(base + db), 0.02, 0, from);
        if (pan.length && pn) BA.schedule(pn.pan, pan, seg.ts, te, toCtx, (v) => clamp(v, -1, 1), 0, 0, from);
      }
    }

    // ---------------- R4: efektli onizleme katmani ----------------
    // Python'un bounce ile AYNI yoldan isledigi kanal penceresi [t0, t1) (WET) kanalin kuru klipleri yerine calinir:
    // kuru klipler yine planlanir ama kanalin kuru dugumu (Eng.dry) pencere boyunca 0'a iner; islak kaynak ayni
    // AudioContext saatinde, ornek-dogru konumda (offset = t - t0) baslar. Gecislerde 20 ms capraz gecis.
    // Dongu dikislerinde (pencere tum donguyu kapliyorsa) kuru ses araya girmez, 3 ms kenar rampasi.
    const WET_XF = 0.02;
    const WET = new Map();            // trId -> { buf, t0, t1, sig, nodes:Set }
    function dryLast(tid) { return Eng.dryLast.has(tid) ? Eng.dryLast.get(tid) : 1; }
    function scheduleWetPart(tid, w, seg, fromCtx) {
      const ac = Eng.ctx;
      const dry = Eng.dry.get(tid), bus = Eng.bus.get(tid);
      if (!ac || !dry || !bus || !w?.buf) return;
      const s0 = Math.max(seg.ts, w.t0), e0 = Math.min(seg.te, w.t1);
      if (!(e0 - s0 > 0.005)) return;
      const toCtx = (t) => seg.cs + (t - seg.ts);
      let ca = toCtx(s0);
      const cb = toCtx(e0);
      const from = Math.max(fromCtx || 0, ac.currentTime + 0.01);
      if (cb <= from + 0.005) return;
      const L = Eng.loop;
      const wholeLoop = !!L && w.t0 <= L.a + 1e-6 && w.t1 >= L.b - 1e-6;       // pencere tum donguyu kapliyor
      const seamIn = wholeLoop && seg.lap > 0 && s0 <= seg.ts + 1e-6 && ca >= from;   // onceki tur da islak bitti
      const seamOut = wholeLoop && Number.isFinite(seg.te) && e0 >= seg.te - 1e-6;
      if (ca < from) ca = from;
      const xin = seamIn ? EDGE_RAMP : WET_XF, xout = seamOut ? EDGE_RAMP : WET_XF;
      const g = ac.createGain();
      g.gain.setValueAtTime(0, ca);
      g.gain.linearRampToValueAtTime(1, ca + xin);
      g.gain.setValueAtTime(1, Math.max(ca + xin, cb - xout));
      g.gain.linearRampToValueAtTime(0, cb);
      g.connect(bus);
      const src = ac.createBufferSource();
      src.buffer = w.buf;
      src.connect(g);
      const offset = s0 + (ca - toCtx(s0)) - w.t0;
      src.start(ca, Math.max(0, offset), Math.max(0.001, cb - ca));
      const nodes = w.nodes || (w.nodes = new Set());
      nodes.add(src); nodes.add(g);
      src.onended = () => { nodes.delete(src); nodes.delete(g); try { g.disconnect(); } catch {} };
      if (w.busBuf) {                          // 2b: send -> bus katkisi (post-fader, bus fx/ses dahil) dogrudan miks cikisina
        const g2 = ac.createGain();
        g2.gain.setValueAtTime(0, ca);
        g2.gain.linearRampToValueAtTime(1, ca + xin);
        g2.gain.setValueAtTime(1, Math.max(ca + xin, cb - xout));
        g2.gain.linearRampToValueAtTime(0, cb);
        g2.connect(Out.mixOut);
        const s2 = ac.createBufferSource();
        s2.buffer = w.busBuf;
        s2.connect(g2);
        s2.start(ca, Math.max(0, offset), Math.max(0.001, cb - ca));
        nodes.add(s2); nodes.add(g2);
        s2.onended = () => { nodes.delete(s2); nodes.delete(g2); try { g2.disconnect(); } catch {} };
      }
      // kuru dugum: pencere boyunca 0 (dikiste zaten 0)
      if (!seamIn) {
        dry.gain.setValueAtTime(dryLast(tid), ca);
        dry.gain.linearRampToValueAtTime(0, ca + xin);
      }
      if (!seamOut) {
        dry.gain.setValueAtTime(0, Math.max(ca + xin, cb - xout));
        dry.gain.linearRampToValueAtTime(1, cb);
        Eng.dryLast.set(tid, 1);
      } else Eng.dryLast.set(tid, 0);
    }
    function stopWetNodes(w, at) {
      if (!w?.nodes) return;
      for (const n of w.nodes) {
        try {
          if (n.gain) { n.gain.cancelScheduledValues(at); n.gain.setValueAtTime(n.gain.value, at); n.gain.linearRampToValueAtTime(0, at + WET_XF); }
          else n.stop(at + WET_XF + 0.005);
        } catch {}
      }
      w.nodes = new Set();
    }
    /** Kanalin islak penceresini ayarlar/kaldirir (w = {buf, t0, t1, sig} | null). Calarken anindan itibaren
        yeniden planlanir: eski islak kaynak 20 ms'de kisilir, yenisi ayni anda acilir; w null ise kuru geri gelir. */
    function setWet(tid, w) {
      const old = WET.get(tid);
      const ac = Eng.ctx;
      const now = ac ? ac.currentTime + 0.03 : 0;
      if (old) stopWetNodes(old, now);
      if (w) WET.set(tid, Object.assign({}, w, { nodes: new Set() })); else WET.delete(tid);
      if (!Eng.playing || !ac) return;
      const dry = Eng.dry.get(tid);
      if (!dry) return;
      dry.gain.cancelScheduledValues(now);
      const cur = dry.gain.value;
      dry.gain.setValueAtTime(cur, now);
      Eng.dryLast.set(tid, cur);
      const nw = WET.get(tid);
      const tNow = Math.max(0, tAtU(Eng.uStart + (now - Eng.when)));
      const covers = !!nw && Eng.audTr.has(tid) && tNow >= nw.t0 && tNow < nw.t1 - 0.03;
      if (!covers && cur !== 1) {            // simdi islak yok: kuru 20 ms'de geri gelir
        dry.gain.linearRampToValueAtTime(1, now + WET_XF);
        Eng.dryLast.set(tid, 1);
      }
      if (nw && Eng.audTr.has(tid)) {
        for (const seg of Eng.segs) {
          const segEnd = Number.isFinite(seg.te) ? seg.cs + (seg.te - seg.ts) : Infinity;
          if (segEnd > now) scheduleWetPart(tid, nw, seg, covers ? now : now + WET_XF);
        }
      }
    }
    function wetInfo() {
      const o = {};
      for (const [tid, w] of WET) o[tid] = { t0: w.t0, t1: w.t1, sig: w.sig };
      return o;
    }

    function click(at, accent, strong) {
      const ac = Eng.ctx;
      if (!Eng.metroGain || at < ac.currentTime - 0.005) return;
      const osc = ac.createOscillator();
      const g = ac.createGain();
      osc.frequency.value = accent ? 1760 : 1175;
      const peak = (accent ? 1 : 0.55) * (strong ? 1.15 : 1);
      g.gain.setValueAtTime(0.0001, at);
      g.gain.linearRampToValueAtTime(peak, at + 0.002);
      g.gain.exponentialRampToValueAtTime(0.0005, at + 0.05);
      osc.connect(g); g.connect(Eng.metroGain);
      osc.start(at); osc.stop(at + 0.06);
      osc.onended = () => { try { g.disconnect(); } catch {} };
    }
    /** [lo, hi) ctx penceresindeki tiklar: sayim tiklari (her zaman) + metronom (aciksa, sayim bitince). */
    function scheduleClicks(lo, hi) {
      const cnt = Eng.o.countIn;
      if (cnt) {
        for (const tk of cnt.ticks) {
          const at = Eng.when + (tk.t - Eng.uStart);
          if (at >= lo && at < hi) click(at, tk.accent, true);
        }
      }
      if (!Metro.on) return;
      for (const seg of Eng.segs) {
        const cEnd = Number.isFinite(seg.te) ? seg.cs + (seg.te - seg.ts) : Infinity;
        const wlo = Math.max(lo, seg.cs), whi = Math.min(hi, cEnd);
        if (whi <= wlo) continue;
        for (const tk of BT.metronomeTicks(bpm(), seg.ts + (wlo - seg.cs), seg.ts + (whi - seg.cs))) {
          const at = seg.cs + (tk.t - seg.ts);
          if (cnt && Eng.uStart + (at - Eng.when) < cnt.origin - 1e-6) continue;   // sayim sirasinda yalniz sayim tiklari
          click(at, tk.accent, false);
        }
      }
    }

    function schedTick(token) {
      if (token !== Eng.token || !Eng.playing) return;
      const now = Eng.ctx.currentTime;
      while (Eng.segNext && Eng.segNext.cs < now + CLIP_LOOKAHEAD) {
        const g = Eng.segNext;
        scheduleSegment(g, token);
        Eng.segs.push(g);
        if (Eng.segs.length > 4) Eng.segs.shift();
        const L = Eng.loop;
        Eng.segNext = L && Number.isFinite(g.te) ? { ts: L.a, te: L.b, cs: g.cs + (g.te - g.ts), lap: g.lap + 1 } : null;
      }
      const hi = now + METRO_LOOKAHEAD;
      if (hi > Eng.metroH) { scheduleClicks(Eng.metroH, hi); Eng.metroH = hi; }
    }

    /** Calmayi baslatir. from: zaman cizelgesi konumu (sayimda negatif olabilir).
        o: { loop: {a,b} | null (verilmezse proje dongusu), countIn: {origin, ticks}, rec: bool, force: bool,
             stopAtU, onLap(n), onCount(kalanVurus), onAutoStop() }  */
    async function play(from, o = {}) {
      stopEngine();
      const token = Eng.token;
      const start = Number.isFinite(Number(from)) ? Number(from) : S.playhead;
      const loop = o.loop === undefined ? loopRegion() : o.loop;
      const effLoop = loop && start < loop.b ? loop : null;
      const trs = tracks();
      const hasSolo = trs.some((t) => t.solo);
      const audible = [];
      const lo = effLoop ? Math.min(start, effLoop.a) : start;
      for (const tr of trs) {
        if (tr.mute || (hasSolo && !tr.solo)) continue;
        for (const c of BC.stackView(tr.clips || [])) {
          if (c.muted || !c.path) continue;
          if (BC.clipBounds(c)[1] <= lo) continue;
          audible.push({ tr, c });
        }
      }
      const refOnly = Out.ab === "B" && !!Out.ref?.buf;
      if (!audible.length && !o.force && !Metro.on && !refOnly) { opts.onStatus?.("Çalınacak klip yok (kanallar boş, sessiz veya çalma çizgisi sonda)."); return false; }
      const paths = [...new Set(audible.map((a) => srcOf(a.c)))];
      const slow = paths.some((p) => !Eng.buffers.has(p));
      if (slow) opts.onStatus?.("Önizleme için sesler yükleniyor…");
      const ac = ctx();
      if (ac.state === "suspended") await ac.resume().catch(() => {});
      await Promise.all(paths.map(loadBuffer));
      if (token !== Eng.token) return false;     // bu arada durduruldu / yeniden baslatildi
      const when = ac.currentTime + 0.08;
      Eng.anchor = { u: start, wall: Date.now() + (when - ac.currentTime) * 1000 };   // kayit capasi (ayni saat)
      Eng.when = when; Eng.uStart = start; Eng.loop = effLoop; Eng.playing = true; Eng.o = o; Eng.audible = audible;
      Eng.lastLaps = 0; Eng.lastCount = null; Eng.autoStopped = false;
      Eng.bus = new Map(); Eng.pan = new Map();
      Eng.dry = new Map(); Eng.dryLast = new Map();
      Eng.audTr = new Set(trs.filter((t) => !(t.mute || (hasSolo && !t.solo))).map((t) => t.id));
      for (const tr of trs) {
        const g = track(ac.createGain());
        g.gain.value = dbToGain(tr.volume_db);
        const pan = ac.createStereoPanner ? ac.createStereoPanner() : null;
        if (pan) { pan.pan.value = clamp(Number(tr.pan) || 0, -1, 1); g.connect(pan); pan.connect(Out.mixOut); track(pan); Eng.pan.set(tr.id, pan); }
        else g.connect(Out.mixOut);
        Eng.bus.set(tr.id, g);
        const d = track(ac.createGain());       // R4: kuru klipler buradan; islak pencere boyunca 0
        d.gain.value = 1;
        d.connect(g);
        Eng.dry.set(tr.id, d);
      }
      Eng.metroGain = ac.createGain();                 // metronom yalniz cikisa (kulakliga) gider, kayda girmez
      Eng.metroGain.gain.value = Metro.vol;
      Eng.metroGain.connect(ac.destination);
      if (Out.ref?.buf && !o.rec) startRef(start);      // 2a: referans ayni konumdan paralel calar (A'da sessiz)
      Eng.segs = [];
      Eng.segNext = { ts: start, te: effLoop ? effLoop.b : Infinity, cs: when, lap: 0 };
      Eng.metroH = when;
      schedTick(token);
      Eng.sched = setInterval(() => schedTick(token), SCHED_MS);
      const missing = audible.filter((a) => !Eng.buffers.get(srcOf(a.c))).length;
      if (missing) opts.onStatus?.(`${missing} klibin kaynağı açılamadı (dosya taşınmış olabilir).`);
      else if (slow) opts.onStatus?.(WET.size ? "Önizleme çalıyor." : "Önizleme çalıyor (efektsiz).");
      opts.onPlayState?.(true);
      opts.onPlayStart?.(start, effLoop);
      const endT = projectEnd();
      const beatS = BT.beatSec(bpm());
      const tick = () => {
        if (!Eng.playing || token !== Eng.token) return;
        const u = uNow();
        S.playhead = Math.max(0, tAtU(u));
        drawPlayhead();
        drawRuler();
        if (o.countIn) {
          const left = u < o.countIn.origin ? Math.ceil((o.countIn.origin - u) / beatS - 1e-6) : 0;
          if (left !== Eng.lastCount) { Eng.lastCount = left; o.onCount?.(left); }
        }
        if (Eng.loop) {
          const L = Eng.loop.b - Eng.loop.a;
          const laps = u < Eng.loop.b ? 0 : Math.floor((u - Eng.loop.b) / L) + 1;
          if (laps !== Eng.lastLaps) { Eng.lastLaps = laps; o.onLap?.(laps); }
        }
        if (o.stopAtU != null && u >= o.stopAtU && !Eng.autoStopped) { Eng.autoStopped = true; o.onAutoStop?.(); }
        updateRecLive(u);
        if (opts.follow?.()) {
          const x = t2x(S.playhead), sl = el.scroll.scrollLeft, vw = el.scroll.clientWidth;
          if (x > sl + vw - 40) el.scroll.scrollLeft = x - 60;
          else if (x < sl) el.scroll.scrollLeft = Math.max(0, x - 60);
        }
        if (!Eng.loop && !o.rec && S.playhead > endT + 0.25 && !opts.keepRolling?.() && !(Out.ab === "B" && Out.refNodes.size)) { stopEngine(); return; }
        Eng.raf = requestAnimationFrame(tick);
      };
      Eng.raf = requestAnimationFrame(tick);
      return true;
    }
    function toggle() { if (Eng.playing) stopEngine(); else play(S.playhead); }
    function restartIfPlaying() { if (Eng.playing && !Eng.o.rec) play(currentTime()); }
    function dropBuffer(path) { Eng.buffers.delete(path); }
    function setMetronome(m) {
      if (m.on !== undefined) Metro.on = !!m.on;
      if (m.vol !== undefined) Metro.vol = clamp(Number(m.vol) || 0, 0, 1);
      if (Eng.metroGain) Eng.metroGain.gain.setTargetAtTime(Metro.vol, Eng.ctx.currentTime, 0.02);
    }

    // ---------------- Canli kayit karti (kayit sirasinda serit uzerinde) ----------------
    let REC = null;     // { trId, mode, from, a, b, t0, t1, laps }
    function setRecLive(r) {
      REC = r;
      el.content.querySelector(".kb-rec-live")?.remove();
      if (!r) return;
      const lane = el.content.querySelector(`.kb-tl-lane[data-lane="${CSS.escape(r.trId)}"]`);
      if (!lane) return;
      const d = document.createElement("div");
      d.className = "kb-rec-live";
      d.innerHTML = `<i class="g g2"></i><i class="g g1"></i><div class="top"><span class="dot"></span><b></b></div>`;
      lane.appendChild(d);
      updateRecLive(null);
    }
    function recLap(n) {
      if (!REC) return;
      REC.laps = n;
      const d = el.content.querySelector(".kb-rec-live");
      if (!d) return;
      d.classList.toggle("has1", n >= 1);
      d.classList.toggle("has2", n >= 2);
      const top = d.querySelector(".top");
      top.classList.remove("kb-take-in"); void top.offsetWidth; top.classList.add("kb-take-in");   // "take tamam" kaymasi
      updateRecLive(null);
    }
    function updateRecLive(u) {
      if (!REC) return;
      const d = el.content.querySelector(".kb-rec-live");
      if (!d) return;
      let s, e, txt;
      if (REC.mode === "loop") { s = REC.a; e = REC.b; txt = `Kayıt · Tur ${(REC.laps || 0) + 1}${REC.laps ? ` · ${REC.laps} take hazır` : ""}`; }
      else if (REC.mode === "punch") { s = REC.t0; e = REC.t1; txt = "Punch"; }
      else { s = REC.from; e = Math.max(s + 0.05, u == null ? s : Math.max(s, tAtU(u))); txt = "Kayıt"; }
      d.style.left = t2x(s) + "px";
      d.style.width = Math.max(4, t2x(e - s)) + "px";
      const b = d.querySelector("b");
      if (b.textContent !== txt) b.textContent = txt;
    }

    /** Yeni take kartlarina imza hareketi: destenin ustune kayarak oturur. */
    function animateTakeIn(ids) {
      for (const id of ids || []) {
        const card = el.content.querySelector(`.kb-clip[data-clip="${CSS.escape(id)}"]`);
        if (card) { card.classList.remove("kb-take-in"); void card.offsetWidth; card.classList.add("kb-take-in"); }
      }
    }

    return {
      render, setZoom, zoomBy, fit, ensureVisible, setPlayhead, play, stop: stopEngine, toggle, restartIfPlaying,
      // R4: efektli onizleme katmani
      setWet, wetInfo, hasWet: (tid) => WET.has(tid),
      // 2a: dinleme simulatoru + referans A/B
      setListen, getListen: () => Out.listen, setAB, getAB: () => Out.ab, setReference, setRefGain,
      hasReference: () => !!Out.ref?.buf,
      isPlaying: () => Eng.playing, getPlayhead: () => (Eng.playing ? currentTime() : S.playhead),
      selection: () => S.sel, clearSel, pruneSelection, select,
      splitSelected, duplicateSelected, deleteSelected, resetFadeSelected, toggleMuteSelected,
      setSnap: (m) => { S.snapMode = m === "auto" || m === "" || m == null ? "auto" : (Number(m) || 0); drawRuler(); },
      getSnap: () => S.snapMode, effGrid: effDiv,
      // R1/R2/R3
      nudgeSelected, nudgePlayhead, nudgeLoop, loopSelected: () => S.loopSel, clearLoopSel: () => { S.loopSel = ""; },
      audioCtx: () => ctx(), drawRuler, formatPos: (t) => BTR.formatPosition(t, bpm()),
      pps: () => S.pps, projectEnd, dropBuffer, isDragging: () => !!S.drag,
      trackColor,
      // 1b
      setMetronome, getMetronome: () => ({ on: Metro.on, vol: Metro.vol }), anchor: () => Eng.anchor,
      uNow: () => (Eng.playing ? uNow() : null), loopRegion, setRecLive, recLap, animateTakeIn, findClip,
      toggleLoop, setLoop,
      // 1e
      dropAt,
      // 1c
      sectionAt, renameSection: startSecRename, splitSectionAt, mergeSectionPrev,
      // 2b
      autoDeleteSelected, hasAutoSel: () => !!AUTO.sel, clearAutoSel: () => { AUTO.sel = null; },
      setCleanAB: (m) => { S.cleanAB = m === "raw" ? "raw" : "clean"; render(); restartIfPlaying(); return S.cleanAB; },
      getCleanAB: () => S.cleanAB, srcOf,
      openStackMenu: (id) => { const h = findClip(id); const card = el.content.querySelector(`.kb-clip[data-clip="${CSS.escape(id)}"]`); if (h && card) openStackMenu(card, h); },
    };
  }

  root.BeatTimeline = { create, trackColor };
})(window);
