// Kami Oda sabit adres: https://<ad>.<hesap>.workers.dev/<oda>/
// Kami her acilista Cloudflare quick tunnel adresini buraya bildirir (POST /_kami/set, gizli anahtarla);
// gelen istekler o anki tunele aktarilir. Kami kapaliysa "su an odada degil" sayfasi doner.
// Baglantilar: KV ad alani ROOM, gizli SET_KEY (wrangler secret put SET_KEY).

const OFFLINE = (host) => `<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#07060B"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><title>Kami Oda</title>
<style>html,body{margin:0;height:100%;background:#07060B;color:#EDE9F6;font:500 16px system-ui,sans-serif}
.b{height:100%;display:grid;place-items:center;text-align:center;padding:24px;background:radial-gradient(ellipse 60% 50% at 50% 35%,#1E1430,#07060B 72%)}
.r{width:130px;height:130px;margin:0 auto 22px;border-radius:50%;border:2px dashed #6D28D9;display:grid;place-items:center;animation:s 14s linear infinite}
.r b{font-size:30px;letter-spacing:3px;color:#C4B5FD;animation:s 14s linear infinite reverse}
@keyframes s{to{transform:rotate(360deg)}} p{color:#8E86A3;line-height:1.6;max-width:340px;margin:8px auto}
i{display:inline-block;width:8px;height:8px;border-radius:50%;background:#F5B94A;margin-right:8px;animation:p 1.4s infinite}@keyframes p{50%{opacity:.3}}</style></head>
<body><div class="b"><div><div class="r"><b>KAMI</b></div><h2 style="margin:0;font-size:20px">Oda şu an kapalı</h2>
<p>${host || "Ev sahibi"} şu an Kami'de değil. Kami açıldığında bu sayfa kendiliğinden odaya bağlanır.</p>
<p style="font-size:13px"><i></i>bekleniyor…</p></div></div>
<script>setInterval(()=>fetch(location.href,{cache:"no-store"}).then(r=>{if(r.status!==503)location.reload()}).catch(()=>{}),8000)</script></body></html>`;

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    if (url.pathname === "/_kami/set" && req.method === "POST") {
      if (!env.SET_KEY || req.headers.get("x-kami-key") !== env.SET_KEY) return new Response("no", { status: 403 });
      const b = await req.json().catch(() => ({}));
      if (!/^https:\/\/[a-z0-9-]+\.trycloudflare\.com$/.test(b.target || "") && b.target !== "") return new Response("bad", { status: 400 });
      await env.ROOM.put("target", b.target || "");
      if (b.host) await env.ROOM.put("host", String(b.host).slice(0, 40));
      return new Response("ok");
    }
    if (url.pathname === "/" || url.pathname === "/favicon.ico") return new Response("", { status: 404 });
    const target = await env.ROOM.get("target", { cacheTtl: 30 });
    const offline = async () => new Response(OFFLINE(await env.ROOM.get("host", { cacheTtl: 300 })), {
      status: 503, headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store" } });
    if (!target) return offline();
    const up = new URL(url.pathname + url.search, target);
    const init = { method: req.method, headers: new Headers(req.headers), redirect: "manual" };
    init.headers.delete("host");
    if (!["GET", "HEAD"].includes(req.method)) init.body = await req.arrayBuffer();
    try {
      const r = await fetch(up, init);
      if ([502, 503, 530].includes(r.status) && req.method === "GET" && (req.headers.get("accept") || "").includes("text/html")) return offline();
      const h = new Headers(r.headers);
      h.set("cache-control", h.get("cache-control") || "no-store");
      return new Response(r.body, { status: r.status, headers: h });
    } catch {
      return req.method === "GET" ? offline() : new Response("offline", { status: 503 });
    }
  },
};
