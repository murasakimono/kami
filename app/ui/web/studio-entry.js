"use strict";
// Ana Kami penceresi: Kami Studio komut paleti kaydi (ust barda tek Studio sekmesi vardir)
(() => {
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎬", t: "Kami Studio", sub: "video editörü", run: () => api.studio_show("") },
  ]);
})();
