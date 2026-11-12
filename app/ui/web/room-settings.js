// Ayarlar > Kami Oda: odayi ac, baglantiyla katil, Cloudflare TURN anahtari.
"use strict";
(function () {
  async function turnState() {
    const s = await api.room_turn_status();
    $("#turnState").textContent = s.has ? "· kayıtlı" : "· yok";
    $("#turnClear").hidden = !s.has;
  }
  function bind() {
    if (!$("#roomOpenBtn")) return;
    $("#roomOpenBtn").onclick = () => slow("room_open", true);
    $("#roomJoinBtn").onclick = async () => {
      const r = await api.room_join($("#roomJoinUrl").value.trim());
      if (!r.ok) toast("Geçersiz oda bağlantısı", true);
    };
    $("#turnSave").onclick = async () => {
      const id = $("#turnId").value.trim(), tok = $("#turnTok").value.trim();
      if (!id || !tok) return;
      $("#turnSave").disabled = true;
      const r = await slow("room_turn_set", id, tok);
      $("#turnSave").disabled = false; $("#turnTok").value = "";
      toast(r.ok ? "TURN anahtarı doğrulandı ve kaydedildi" : r.error === "bad_format" ? "Anahtar biçimi hatalı" : "Cloudflare anahtarı kabul etmedi", !r.ok);
      if (r.ok) $("#turnId").value = "";
      turnState();
    };
    $("#turnClear").onclick = async () => { await api.room_turn_clear(); turnState(); };
    $("#settingsBtn")?.addEventListener("click", () => setTimeout(turnState, 80));
  }
  // ana ekranin sag ustunde "Oda" dugmesi (motor/kopru yaninda)
  function topButton() {
    const st = document.querySelector("#sunak .sk-status");
    if (!st) { setTimeout(topButton, 600); return; }
    if (st.querySelector(".sk-room")) return;
    const b = document.createElement("button");
    b.className = "sk-room"; b.title = "Kami Oda: sesli oda, ekran paylaşımı, oynatıcı yayını";
    b.innerHTML = `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"><path d="M12 3a3 3 0 0 0-3 3v6a3 3 0 0 0 6 0V6a3 3 0 0 0-3-3zM6 11a6 6 0 0 0 12 0M12 17v4"/></svg><span>Oda</span><i></i>`;
    b.onclick = () => slow("room_open", true);
    st.prepend(b);
    setInterval(async () => { try { const r = await api.room_status(); b.classList.toggle("on", !!r.on); b.querySelector("i").textContent = r.people?.length ? r.people.length : ""; b.title = r.people?.length ? "Odada: " + r.people.join(", ") : "Kami Oda"; } catch { /* yok */ } }, 4000);
  }
  window.addEventListener("pywebviewready", () => { setTimeout(bind, 300); topButton(); });
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎙", t: "Kami Oda", sub: "sesli oda, ekran paylaşımı", run: () => slow("room_open", true) },
    { ic: "🔗", t: "Panodaki bağlantıyla odaya katıl", sub: "trycloudflare davet linki", run: async () => { const u = (await api.read_clipboard()) || ""; const r = await api.room_join(u.trim()); if (!r.ok) toast("Panoda oda bağlantısı yok", true); } },
  ]);
})();
