"use strict";
// Ana Kami penceresi: Kami Studio'ya giris (ust cubuk dugmesi + komut paleti)
(() => {
  function topButton() {
    const st = document.querySelector("#sunak .sk-status");
    if (!st) { setTimeout(topButton, 700); return; }
    if (st.querySelector(".sk-studio")) return;
    const b = document.createElement("button");
    b.className = "sk-room sk-studio"; b.title = "Kami Studio: video editörü (kes, efekt, altyazı, Kami AI ile düzenle)";
    b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><rect x="3" y="5" width="18" height="14" rx="1"/><path d="M3 9h18M7 5v4M12 5v4M17 5v4M10 12.5v4l3.5-2z"/></svg><span>Studio</span><i></i>`;
    b.onclick = () => api.studio_show("");
    st.prepend(b);
  }
  window.addEventListener("pywebviewready", () => topButton());
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎬", t: "Kami Studio", sub: "video editörü", run: () => api.studio_show("") },
  ]);
})();
