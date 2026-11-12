// Renk temalari: yalnizca mor vurgular (palet degiskenleri, dock, logo, karakter) degisir; zumrut kartlar,
// ilerleme halkasi ve hata/uyari renkleri sabit kalir. Kami ve mini kartta uygulanir.
"use strict";
(function () {
  // [royal, violet, lav, plum, line, arka-isik, dock, dock-hover, karakter/logo filtresi]
  const THEMES = {
    mor:   null,
    kizil: ["#B91C3C", "#F0506E", "#FDB5C2", "#2A1218", "#6A3540", "#30121A", "#1A0E11", "#4A1622", "hue-rotate(95deg) saturate(1.15)"],
    buz:   ["#1D6FD9", "#4FA3F7", "#B5DDFD", "#12202E", "#3D5670", "#0F2033", "#0E141B", "#163A5C", "hue-rotate(-78deg) saturate(.95)"],
    altin: ["#B7791F", "#E8B04A", "#FCE3B0", "#2A2112", "#6A5532", "#2E2310", "#19150C", "#4A3612", "hue-rotate(140deg) saturate(1.2) brightness(1.04)"],
    gece:  ["#3730A3", "#6366F1", "#C7D2FE", "#161838", "#3F4270", "#141A3A", "#0F1020", "#22265A", "hue-rotate(-42deg) saturate(1.05)"],
  };
  let st = null;
  function apply(name) {
    name = THEMES[name] !== undefined ? name : "mor";
    document.documentElement.dataset.accent = name;
    if (!st) { st = document.createElement("style"); st.id = "kamiAccent"; document.head.appendChild(st); }
    const t = THEMES[name];
    if (!t) { st.textContent = ""; return; }
    const [royal, violet, lav, plum, line, glow, dock, dockOn, f] = t;
    st.textContent = `
:root, body.sunak, #sunak { --sk-royal:${royal}; --sk-violet:${violet}; --sk-lav:${lav}; --sk-plum:${plum}; --sk-line:${line}; --accent:${violet}; }
body.sunak { background: radial-gradient(ellipse 55% 50% at 32% 30%, ${glow} 0%, var(--sk-bg) 70%) fixed, var(--sk-bg) !important; }
#sunak .sk-dock button { background:${dock}; }
#sunak .sk-dock button:hover, #sunak .sk-dock button.on { background:${dockOn}; }
#sunak .sk-band { background: linear-gradient(180deg, ${royal}, ${plum}); border-bottom-color: ${violet}; }
#sunak .sk-strip.sel, #sunak .sk-strip.msel { filter: drop-shadow(0 0 12px ${violet}cc); }
#skFog { filter: ${f} blur(30px); }
#sunak .sk-char { filter: ${f} drop-shadow(0 10px 24px rgba(0,0,0,.55)); }
#sunak .sk-altar.drop .sk-char { filter: ${f} drop-shadow(0 0 22px rgba(46,230,166,.85)); }
#sunak .sk-logo, .kc-char, .card-char, img.kami-logo { filter: ${f}; }
`;
  }
  window.kamiAccent = apply;
  async function load() {
    try { const s = await window.pywebview.api.get_settings(); apply(s?.accent_theme || "mor"); } catch { /* yok */ }
  }
  window.addEventListener("pywebviewready", load);
  document.addEventListener("change", (e) => { if (e.target?.name === "accent_theme") apply(e.target.value); });
  setInterval(load, 5000);   // ayar degisince diger pencereler de uyar
})();
