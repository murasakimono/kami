// Alt basiliyken tiklanan linkler tarayicida kalsin: arka plana kisa sureli "atla" isareti gonder.
(() => {
  const mark = (e) => {
    if (!e.altKey) return;
    try { chrome.runtime.sendMessage({ type: "alt-bypass" }); } catch (_) { /* eklenti yeniden yuklendiyse */ }
  };
  window.addEventListener("mousedown", mark, true);
  window.addEventListener("click", mark, true);
})();
