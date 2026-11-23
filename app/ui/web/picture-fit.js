// v2.5.5: Picture ust cubugu varsayilan pencere boyunda sagdan tasiyordu.
// Sigmadiginda once simgesi olan butonlarin yazisi gizlenir (yazi title'a gecer), yine sigmazsa dosya bilgisi gizlenir.
(() => {
  const st = document.createElement("style");
  st.textContent = `
    .pc-top { min-width: 0; overflow: hidden; }
    .pc-top #pcName { min-width: 0; max-width: 28vw; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .pc-top button { flex: none; white-space: nowrap; }
    .pc-top.pf-c1 button.pf-ic > span[data-tr] { display: none; }
    .pc-top.pf-c2 #pcInfo { display: none; }
    .pc-top.pf-c2 #pcName { max-width: 16vw; }`;
  document.head.appendChild(st);
  const bar = document.querySelector(".pc-top");
  if (!bar) return;
  const tag = () => {
    bar.querySelectorAll("button").forEach((b) => {
      const sp = b.querySelector(":scope > span[data-tr]");
      if (!sp) return;
      const rest = [...b.childNodes].filter((n) => n !== sp).map((n) => n.nodeType === 3 ? n.textContent.trim() : (n.tagName === "svg" ? "svg" : "")).join("");
      b.classList.toggle("pf-ic", !!rest);
      const lbl = sp.textContent.trim();
      if (lbl && (!b.title || b.title.length <= 2)) b.title = b.title ? `${lbl} (${b.title})` : lbl;
    });
  };
  const over = () => bar.scrollWidth > bar.clientWidth + 1;
  const fit = () => {
    tag();
    bar.classList.remove("pf-c1", "pf-c2");
    if (over()) bar.classList.add("pf-c1");
    if (over()) bar.classList.add("pf-c2");
  };
  let raf = 0;
  const kick = () => { cancelAnimationFrame(raf); raf = requestAnimationFrame(fit); };
  new ResizeObserver(kick).observe(bar);
  new MutationObserver(kick).observe(bar, { childList: true, subtree: true, characterData: true });
  kick();
})();
