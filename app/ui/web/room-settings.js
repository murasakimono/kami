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
  window.addEventListener("pywebviewready", () => setTimeout(bind, 300));
  window.KPAL = window.KPAL || [];
  window.KPAL.push(() => [
    { ic: "🎙", t: "Kami Oda", sub: "sesli oda, ekran paylaşımı", run: () => slow("room_open", true) },
    { ic: "🔗", t: "Panodaki bağlantıyla odaya katıl", sub: "trycloudflare davet linki", run: async () => { const u = (await api.read_clipboard()) || ""; const r = await api.room_join(u.trim()); if (!r.ok) toast("Panoda oda bağlantısı yok", true); } },
  ]);
})();
