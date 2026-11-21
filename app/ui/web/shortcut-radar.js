// Kısayol Radarı (Fikir 2): az bilinen kısayolları ara sıra ipucu olarak göster.
"use strict";
(() => {
  const HINTS = [
    ["Ctrl+K", "Komut paleti"],
    ["Alt+F9", "Ekran kaydı başlat/durdur"],
    ["Alt+F10", "Son anları klip olarak kaydet"],
    ["Ctrl+Shift+S", "Bu şarkı ne? (sistem sesini tanı)"],
    ["Ctrl+Shift+G", "Çalan şarkıyı günlüğe ekle"],
    ["F", "Player tam ekran"],
    ["M", "Player sessize al"],
    ["Ctrl+Shift+L", "Ekrandan al ve düzenle (Kami Lens)"],
    ["J / L", "Player 10 sn geri/ileri"],
    ["← / →", "Player 5 sn geri/ileri"],
  ];
  const KEY = "kami.shortcutRadar";
  let idx = 0;
  try { idx = parseInt(localStorage.getItem(KEY) || "0", 10) || 0; } catch {}
  const show = () => {
    const [k, desc] = HINTS[idx % HINTS.length];
    idx = (idx + 1) % HINTS.length;
    try { localStorage.setItem(KEY, String(idx)); } catch {}
    if (window.KamiMotion?.toast) KamiMotion.toast("💡 " + k + " — " + desc, false);
  };
  setTimeout(show, 30000);        // ilk ipucu 30 sn sonra
  setInterval(show, 240000);      // sonra her 4 dakikada bir
})();
