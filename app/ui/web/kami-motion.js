// Kami 2.0 Cohesive Motion & Micro-Interaction Engine
// Saf CSS/WAAPI yardimcilari: shake, hold-0.6s, morphDone, Sonner toast deck,
// glider pill, proximity border glow, instant sequential tooltips, odometer roll, FLIP, radial theme wipe.
"use strict";

(() => {
  if (window.KamiMotion) return;

  const isReduced = () =>
    window.matchMedia?.("(prefers-reduced-motion: reduce)")?.matches ||
    document.body?.classList?.contains("no-anim") ||
    document.body?.classList?.contains("km-reduced");

  // 1. M2: Gercek hata sarsintisi (Yalniz bos URL / hatali girdi aninda)
  function shake(el) {
    if (!el || isReduced()) return;
    el.classList.remove("km-err-shake");
    void el.offsetWidth;
    el.classList.add("km-err-shake");
    clearTimeout(el._kmShakeT);
    el._kmShakeT = setTimeout(() => el.classList.remove("km-err-shake"), 320);
  }

  // 2. M5: Donusen Kopyala / Kaydet dugmesi (checkmark cizimi)
  function morphDone(btn, label = "Kopyalandı", ms = 1500) {
    if (!btn) return;
    if (!btn._kmOrigHtml) btn._kmOrigHtml = btn.innerHTML;
    clearTimeout(btn._kmMorphT);
    btn.classList.add("km-morph-ok");
    btn.innerHTML = `<span class="km-morph-wrap"><svg class="km-morph-svg" viewBox="0 0 24 24"><path d="M5 13l4 4L19 7"/></svg><span>${label}</span></span>`;
    btn._kmMorphT = setTimeout(() => {
      btn.classList.remove("km-morph-ok");
      if (btn._kmOrigHtml != null) btn.innerHTML = btn._kmOrigHtml;
    }, ms);
  }

  // 3. M4: Basili Tutarak Onayla (Hold 0.6s SVG halka dolumu — yalniz yikici toplu temizlikte)
  function attachHold(btn, onConfirm, opts = {}) {
    if (!btn || btn.dataset.kmHoldBound === "1") return;
    btn.dataset.kmHoldBound = "1";
    const holdMs = Math.max(250, Number(opts.ms || 600));
    btn.classList.add("km-hold-btn");
    if (!btn.title) btn.title = "Onaylamak için 0.6 sn basılı tut";

    const origText = opts.label || btn.textContent || "";
    btn.textContent = "";
    const svg = document.createElementNS("http://www.w3.org/2000/svg", "svg");
    svg.setAttribute("class", "km-hold-ring");
    svg.setAttribute("viewBox", "0 0 18 18");
    svg.innerHTML = `<circle class="km-hr-bg" cx="9" cy="9" r="7"></circle><circle class="km-hr-fg" cx="9" cy="9" r="7"></circle>`;
    const lbl = document.createElement("span");
    lbl.className = "km-hold-lbl";
    lbl.textContent = origText;
    btn.append(svg, lbl);

    let timer = 0;
    let triggered = false;

    const cancelHold = () => {
      clearTimeout(timer);
      timer = 0;
      btn.classList.remove("holding");
    };

    const startHold = () => {
      if (btn.disabled || timer) return;
      triggered = false;
      btn.classList.remove("km-hold-ok");
      btn.classList.add("holding");
      timer = setTimeout(() => {
        timer = 0;
        triggered = true;
        btn.classList.remove("holding");
        btn.classList.add("km-hold-ok");
        setTimeout(() => btn.classList.remove("km-hold-ok"), 650);
        try {
          onConfirm?.();
        } catch (err) {
          console.error("KamiMotion hold callback error:", err);
        }
      }, isReduced() ? 10 : holdMs);
    };

    btn.addEventListener("pointerdown", (e) => {
      if (e.button !== 0 || btn.disabled) return;
      e.preventDefault();
      startHold();
    });
    btn.addEventListener("pointerup", cancelHold);
    btn.addEventListener("pointerleave", cancelHold);
    btn.addEventListener("pointercancel", cancelHold);
    btn.addEventListener("keydown", (e) => {
      if ((e.key === "Enter" || e.key === " ") && !e.repeat) {
        e.preventDefault();
        startHold();
      }
    });
    btn.addEventListener("keyup", (e) => {
      if (e.key === "Enter" || e.key === " ") cancelHold();
    });
    btn.addEventListener("click", (e) => {
      if (triggered) { triggered = false; return; }
      // Tek tiklamada kullaniciya ipucu ver, yanlislikla silme
      e.preventDefault();
      e.stopImmediatePropagation();
      toast("Onaylamak için 0.6 sn basılı tut");
    });
  }

  // 4. M6: Sonner Tarzi Katmanli Bildirim Destesi
  function ensureDeck() {
    let deck = document.getElementById("kmToastDeck");
    if (!deck) {
      deck = document.createElement("div");
      deck.id = "kmToastDeck";
      document.body?.appendChild(deck);
    }
    return deck;
  }

  function reindexDeck(deck) {
    const cards = [...deck.querySelectorAll(".km-toast:not(.leaving)")];
    // Yeniden eskiye --i: 0, 1, 2
    cards.reverse().forEach((el, idx) => {
      el.style.setProperty("--i", String(idx));
      el.style.display = idx > 2 ? "none" : "";
    });
  }

  function dismissCard(card) {
    if (!card || card.classList.contains("leaving")) return;
    clearTimeout(card._kmT);
    card.classList.add("leaving");
    const deck = card.parentElement;
    if (deck) reindexDeck(deck);
    setTimeout(() => {
      card.remove();
      if (deck) reindexDeck(deck);
    }, 220);
  }

  function toast(msg, isErr = false, sticky = false) {
    const text = String(msg || "").trim();
    if (!text) return;
    const deck = ensureDeck();
    if (sticky) {
      const existing = [...deck.querySelectorAll(".km-toast:not(.leaving)")].find(
        (x) => x.dataset.sticky === "1" && x.dataset.msg === text
      );
      if (existing) return existing;
    }
    const card = document.createElement("div");
    card.className = "km-toast entering" + (isErr ? " err" : "");
    card.dataset.msg = text;
    if (sticky) card.dataset.sticky = "1";
    const span = document.createElement("span");
    span.textContent = text;
    const xBtn = document.createElement("button");
    xBtn.type = "button";
    xBtn.className = "km-toast-x";
    xBtn.textContent = "✕";
    xBtn.onclick = (e) => { e.stopPropagation(); dismissCard(card); };
    card.append(span, xBtn);
    card.onclick = () => dismissCard(card);
    deck.appendChild(card);

    // En fazla 3 aktif kart
    const active = [...deck.querySelectorAll(".km-toast:not(.leaving)")];
    while (active.length > 3) dismissCard(active.shift());

    requestAnimationFrame(() => {
      card.classList.remove("entering");
      reindexDeck(deck);
    });
    if (!sticky) card._kmT = setTimeout(() => dismissCard(card), isErr ? 4500 : 3400);
    return card;
  }

  function dismissSticky(matchText) {
    const deck = document.getElementById("kmToastDeck");
    if (!deck) return;
    deck.querySelectorAll('.km-toast[data-sticky="1"]').forEach((c) => {
      if (!matchText || c.dataset.msg === matchText) dismissCard(c);
    });
  }

  // 5. M7: Kayan Kapsul Sekme Gostergesi (Glider)
  function bindGlider(container, itemSelector, activeClass = "on") {
    if (!container || container.dataset.kmGlider === "1") return;
    container.dataset.kmGlider = "1";
    container.classList.add("km-glider-host");
    let glider = container.querySelector(":scope > .km-glider");
    if (!glider) {
      glider = document.createElement("div");
      glider.className = "km-glider";
      container.prepend(glider);
    }

    const sync = () => {
      const active = container.querySelector(`${itemSelector}.${activeClass}`);
      if (!active || active.offsetParent === null) {
        glider.classList.remove("on");
        return;
      }
      const cr = container.getBoundingClientRect();
      const ar = active.getBoundingClientRect();
      const left = ar.left - cr.left + container.scrollLeft - container.clientLeft;
      const top = ar.top - cr.top + container.scrollTop - container.clientTop;
      glider.style.width = `${Math.round(ar.width)}px`;
      glider.style.height = `${Math.round(ar.height)}px`;
      glider.style.transform = `translate3d(${Math.round(left)}px, ${Math.round(top)}px, 0)`;
      glider.classList.add("on");
    };

    const obs = new MutationObserver(() => requestAnimationFrame(sync));
    obs.observe(container, { attributes: true, subtree: true, childList: true, attributeFilter: ["class"] });
    container.addEventListener("click", () => requestAnimationFrame(sync));
    window.addEventListener("resize", sync);
    requestAnimationFrame(sync);
    return sync;
  }

  // 6. M8: Imlec Yakinligi Kenar Isigi (rAF throttled, yalniz hareket aninda)
  let _glowBound = false;
  function initProximityGlow() {
    if (_glowBound) return;
    _glowBound = true;
    const SELECTOR = ".sk-g, .cl-drive, .gcard, .qa-card, .acard, .eco-card";
    let rafId = 0;
    let lastE = null;
    const hotSet = new Set();

    const paint = () => {
      rafId = 0;
      const e = lastE;
      if (!e || isReduced()) return;
      const cards = document.querySelectorAll(SELECTOR);
      const nextHot = new Set();
      for (const el of cards) {
        if (!el.classList.contains("km-glow")) el.classList.add("km-glow");
        const r = el.getBoundingClientRect();
        if (!r.width || !r.height) continue;
        const pad = 160;
        if (e.clientX >= r.left - pad && e.clientX <= r.right + pad &&
            e.clientY >= r.top - pad && e.clientY <= r.bottom + pad) {
          el.style.setProperty("--km-x", `${e.clientX - r.left}px`);
          el.style.setProperty("--km-y", `${e.clientY - r.top}px`);
          el.style.setProperty("--km-on", "1");
          nextHot.add(el);
        } else if (hotSet.has(el)) {
          el.style.setProperty("--km-on", "0");
        }
      }
      hotSet.clear();
      nextHot.forEach((x) => hotSet.add(x));
    };

    document.addEventListener("pointermove", (e) => {
      lastE = e;
      if (!rafId) rafId = requestAnimationFrame(paint);
    }, { passive: true });

    const clearAll = () => {
      hotSet.forEach((el) => el.style.setProperty("--km-on", "0"));
      hotSet.clear();
    };
    document.addEventListener("pointerleave", clearAll);
    window.addEventListener("blur", clearAll);
  }

  // 7. M9: Anlik Ardisik Ipucu (Ilk 300ms, komsuya 0ms)
  let _tipBound = false;
  function initInstantTooltips() {
    if (_tipBound) return;
    _tipBound = true;
    const BAR_SEL = ".pc-top button, #tlbar button, .rd-top button, .pl-deck button, .top button, .m-top button";
    let tipEl = null;
    let showTimer = 0;
    let warmUntil = 0;
    let curTarget = null;

    const getTip = () => {
      if (!tipEl) {
        tipEl = document.createElement("div");
        tipEl.id = "kmTip";
        document.body?.appendChild(tipEl);
      }
      return tipEl;
    };

    const place = (target) => {
      const text = target?.dataset?.kmTip;
      if (!text) return;
      const tip = getTip();
      tip.textContent = text;
      const r = target.getBoundingClientRect();
      const tw = tip.offsetWidth || 80;
      const th = tip.offsetHeight || 26;
      const x = Math.max(8, Math.min(window.innerWidth - tw - 8, r.left + r.width / 2 - tw / 2));
      const y = r.bottom + 8 + th <= window.innerHeight ? r.bottom + 8 : Math.max(8, r.top - th - 8);
      tip.style.setProperty("--tx", `${Math.round(x)}px`);
      tip.style.setProperty("--ty", `${Math.round(y)}px`);
      tip.classList.add("on");
      warmUntil = Date.now() + 550;
    };

    document.addEventListener("pointerover", (e) => {
      const b = e.target.closest?.(BAR_SEL);
      if (!b) return;
      if (b.getAttribute("title") && !b.dataset.kmTip) {
        b.dataset.kmTip = b.getAttribute("title");
        b.removeAttribute("title");
      }
      if (!b.dataset.kmTip) return;
      curTarget = b;
      clearTimeout(showTimer);
      if (Date.now() < warmUntil) place(b);
      else showTimer = setTimeout(() => { if (curTarget === b) place(b); }, 300);
    }, { passive: true });

    document.addEventListener("pointerout", (e) => {
      const b = e.target.closest?.(BAR_SEL);
      if (!b || b !== curTarget) return;
      curTarget = null;
      clearTimeout(showTimer);
      tipEl?.classList.remove("on");
      warmUntil = Date.now() + 500;
    }, { passive: true });

    window.addEventListener("blur", () => {
      curTarget = null;
      clearTimeout(showTimer);
      tipEl?.classList.remove("on");
    });
  }

  // 8. M10: Mekanik Sayac Rakam Donusu (Odometer / NumberFlow)
  function rollNumber(el, valueStr) {
    if (!el) return;
    const str = String(valueStr ?? "0");
    if (isReduced()) {
      el.textContent = str;
      return;
    }
    const sig = [...str].map((ch) => (/\d/.test(ch) ? "D" : ch)).join("");
    if (el.dataset.kmOdoSig !== sig) {
      el.dataset.kmOdoSig = sig;
      el.classList.add("km-odo");
      el.innerHTML = [...str].map((ch) => {
        if (/\d/.test(ch)) {
          return `<span class="km-odo-col"><span class="km-odo-track" data-d="${ch}"><span>0</span><span>1</span><span>2</span><span>3</span><span>4</span><span>5</span><span>6</span><span>7</span><span>8</span><span>9</span></span></span>`;
        }
        return `<span class="km-odo-sep">${ch}</span>`;
      }).join("");
      el.querySelectorAll(".km-odo-track").forEach((tr) => {
        tr.style.transform = `translateY(-${Number(tr.dataset.d) * 1.15}em)`;
      });
      return;
    }
    const cols = el.querySelectorAll(".km-odo-track");
    let di = 0;
    for (const ch of str) {
      if (/\d/.test(ch) && cols[di]) {
        if (cols[di].dataset.d !== ch) {
          cols[di].dataset.d = ch;
          cols[di].style.transform = `translateY(-${Number(ch) * 1.15}em)`;
        }
        di++;
      }
    }
  }

  // 9. M11: FLIP Liste & Katman Siralama Fizigi
  function flip(container, mutateFn, itemSelector = ":scope > *") {
    if (!container || typeof mutateFn !== "function") return mutateFn?.();
    if (isReduced()) return mutateFn();
    const items = [...container.querySelectorAll(itemSelector)];
    const first = new Map();
    items.forEach((el, idx) => {
      const k = el.dataset.id || el.dataset.i || el.dataset.key || String(idx);
      first.set(k, el.getBoundingClientRect());
    });
    mutateFn();
    const after = [...container.querySelectorAll(itemSelector)];
    after.forEach((el, idx) => {
      const k = el.dataset.id || el.dataset.i || el.dataset.key || String(idx);
      const a = first.get(k);
      if (!a) return;
      const b = el.getBoundingClientRect();
      const dx = a.left - b.left;
      const dy = a.top - b.top;
      if (!dx && !dy) return;
      el.style.transition = "none";
      el.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
      requestAnimationFrame(() => {
        el.style.transition = "transform 280ms var(--km-ease-out)";
        el.style.transform = "translate3d(0, 0, 0)";
        setTimeout(() => {
          if (el.style.transform === "translate3d(0, 0, 0)") {
            el.style.transform = "";
            el.style.transition = "";
          }
        }, 300);
      });
    });
  }

  // 10. M14: Radyal Dairesel Tema Gecisi (View Transitions API)
  function radialThemeTransition(evtOrEl, applyFn) {
    if (isReduced() || typeof document.startViewTransition !== "function") {
      return applyFn?.();
    }
    let x = window.innerWidth / 2;
    let y = window.innerHeight / 2;
    if (evtOrEl && typeof evtOrEl.clientX === "number") {
      x = evtOrEl.clientX;
      y = evtOrEl.clientY;
    } else if (evtOrEl?.getBoundingClientRect) {
      const r = evtOrEl.getBoundingClientRect();
      x = r.left + r.width / 2;
      y = r.top + r.height / 2;
    }
    const root = document.documentElement;
    root.style.setProperty("--vt-x", `${Math.round(x)}px`);
    root.style.setProperty("--vt-y", `${Math.round(y)}px`);
    root.classList.add("km-radial-vt");
    try {
      const vt = document.startViewTransition(() => applyFn?.());
      vt.finished.finally(() => root.classList.remove("km-radial-vt"));
      return vt;
    } catch {
      root.classList.remove("km-radial-vt");
      return applyFn?.();
    }
  }

  // 11. M12: Bildirim zili cinlama tetigi
  function ringBell() {
    const b = document.querySelector('[data-sk="notifs"]');
    if (!b || isReduced()) return;
    b.classList.remove("km-ringing");
    void b.offsetWidth;
    b.classList.add("km-ringing");
    clearTimeout(b._kmBellT);
    b._kmBellT = setTimeout(() => b.classList.remove("km-ringing"), 560);
  }

  // 12. A1: Kademeli liste / kart girisi (ilk 12 oge, bitince temizlenir)
  function cascade(container, itemSel = ":scope > *", max = 12) {
    if (!container || isReduced()) return;
    const list = [...container.querySelectorAll(itemSel)];
    const cap = Math.min(list.length, max);
    for (let i = 0; i < cap; i++) {
      const el = list[i];
      el.style.setProperty("--km-ci", String(i));
      el.classList.add("km-cascade-item");
      const done = () => {
        clearTimeout(el._kmCasT);
        el.classList.remove("km-cascade-item");
        el.style.removeProperty("--km-ci");
      };
      el.addEventListener("animationend", done, { once: true });
      clearTimeout(el._kmCasT);
      el._kmCasT = setTimeout(done, 280 + i * 22 + 120);
    }
  }

  // 13. A2: Canli calan mini ekolayzer cubuklari
  function eqHtml(paused = false) {
    return `<span class="km-eq${paused ? " paused" : ""}" aria-hidden="true"><i></i><i></i><i></i></span>`;
  }

  // 14. A5: Surukleme sirasinda manyetik portal halkasi & birakma emilimi
  let _dragBound = false;
  function initDragPortals() {
    if (_dragBound) return;
    _dragBound = true;
    const DRAG_ZONES = ".cv-drop, .pc-stage, #rdStage";
    const ABSORB_ZONES = "#k20AiDropZone, .cv-drop, .pc-stage, #rdStage, #chat";
    document.addEventListener("dragover", (e) => {
      if (!e.dataTransfer?.types?.includes("Files")) return;
      const z = e.target?.closest?.(DRAG_ZONES);
      if (z) z.classList.add("drag");
    });
    document.addEventListener("dragleave", (e) => {
      const z = e.target?.closest?.(DRAG_ZONES);
      if (z && (!e.relatedTarget || !z.contains(e.relatedTarget))) z.classList.remove("drag");
    });
    const clearDrag = (e) => {
      document.querySelectorAll(".cv-drop.drag, .pc-stage.drag, #rdStage.drag").forEach((z) => z.classList.remove("drag"));
      if (e?.type !== "drop" || isReduced()) return;
      const z = e.target?.closest?.(ABSORB_ZONES);
      if (!z) return;
      z.classList.remove("km-absorb");
      void z.offsetWidth;
      z.classList.add("km-absorb");
      clearTimeout(z._kmAbsT);
      z._kmAbsT = setTimeout(() => z.classList.remove("km-absorb"), 300);
    };
    document.addEventListener("drop", clearDrag, true);
    document.addEventListener("dragend", clearDrag, true);
  }

  // 15. Bootstrap
    // M10: Bitiş halka nabzı (tamamlanan öğede tek seferlik genişleyen halka)
  function pulseRing(el) {
    if (!el || isReduced()) return;
    el.classList.remove("km-pulse-ring");
    void el.offsetWidth;
    el.classList.add("km-pulse-ring");
    clearTimeout(el._kmPulseT);
    el._kmPulseT = setTimeout(() => el.classList.remove("km-pulse-ring"), 600);
  }

  // M9: Kart eğilmesi (tilt) — hover'da 3D derinlik
  function initMicro() {
    if (isReduced()) return;
    document.querySelectorAll(".gcard, .qa-card, .acard").forEach((c) => c.classList.add("km-tilt"));
  }

  // M12: Kıvılcım patlaması (bırakma/tamamlama anında)
  function sparkBurst(el) {
    if (!el || isReduced()) return;
    el.classList.remove("km-spark-burst");
    void el.offsetWidth;
    el.classList.add("km-spark-burst");
    clearTimeout(el._kmSparkT);
    el._kmSparkT = setTimeout(() => el.classList.remove("km-spark-burst"), 600);
  }

  // M11: Tılsım dalgası (liste yenilenince kademeli geçiş)
  function wave(el) {
    if (!el || isReduced()) return;
    el.classList.remove("km-wave");
    void el.offsetWidth;
    el.classList.add("km-wave");
    clearTimeout(el._kmWaveT);
    el._kmWaveT = setTimeout(() => el.classList.remove("km-wave"), 900);
  }

function bootstrap() {
    initProximityGlow();
    initInstantTooltips();
    initDragPortals();
    initMicro();
    const bindKnownGliders = () => {
      const cl = document.getElementById("clTabs");
      if (cl) bindGlider(cl, ".cl-tab", "on");
      const st = document.querySelector(".st-nav");
      if (st) bindGlider(st, "button", "on");
      const sp = document.querySelector("aside.side");
      if (sp) bindGlider(sp, ".nav-b", "on");
      const rd = document.querySelector("nav.rd-tabs");
      if (rd) bindGlider(rd, "button", "on");
    };
    bindKnownGliders();
    document.addEventListener("click", (e) => {
      const cBtn = e.target.closest?.("[data-km-copy]");
      if (cBtn) { morphDone(cBtn, "Kopyalandı"); return; }
      const sg = e.target.closest?.("#sgdbSave");
      if (sg && document.getElementById("sgdbIn")?.value?.trim()) { morphDone(sg, "Kaydedildi"); return; }
      const sw = e.target.closest?.("#swSave");
      if (sw && document.getElementById("swKey")?.value?.trim()) { morphDone(sw, "Kaydedildi"); return; }
    });
    // Sonradan eklenen .st-nav / #clTabs icin hafif observer (baglaninca kendini durdurur)
    if (document.body && (!document.querySelector(".st-nav") || !document.getElementById("clTabs"))) {
      const mo = new MutationObserver(() => {
        bindKnownGliders();
        if (document.querySelector(".st-nav")?.dataset?.kmGlider && document.getElementById("clTabs")?.dataset?.kmGlider) {
          mo.disconnect();
        }
      });
      mo.observe(document.body, { childList: true, subtree: true });
      setTimeout(() => mo.disconnect(), 12000);
    }
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootstrap, { once: true });
  else bootstrap();

  window.KamiMotion = {
    shake,
    morphDone,
    attachHold,
    toast,
    dismissSticky,
    bindGlider,
    initProximityGlow,
    initInstantTooltips,
    rollNumber,
    flip,
    radialThemeTransition,
    ringBell,
    cascade,
    eqHtml,
    initDragPortals,
    pulseRing,
    sparkBurst,
    wave,
  };
})();
