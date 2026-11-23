// Kami Relay (Cloudflare Worker + KV) — v2.5.3
// Telefon (mobil veri dahil) -> link kuyrugu -> Kami her 20 sn'de ceker ve indirir.
// Kami -> olay (indirme bitti vb.) -> telefondaki sayfada liste (+ istege bagli ntfy.sh anlik bildirimi).
// Kimlik: tum /api/* istekleri HMAC-SHA256 imzali: X-Kami-Ts (unix sn) + X-Kami-Sig = hex(HMAC(secret, `${ts}.` + govde)).
//   GET isteklerde govde sabit metindir: health -> "ping", pull -> "pull", liste -> "events". Zaman farki en fazla 300 sn.
// Baglantilar: KV ad alani RELAY, gizli RELAY_SECRET (wrangler secret put RELAY_SECRET), istege bagli NTFY_TOPIC.

const MAX_QUEUE = 200, MAX_EVENTS = 60;

async function hmacHex(secret, msg) {
  const key = await crypto.subtle.importKey("raw", new TextEncoder().encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
  const sig = await crypto.subtle.sign("HMAC", key, new TextEncoder().encode(msg));
  return [...new Uint8Array(sig)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function safeEq(a, b) {
  if (a.length !== b.length) return false;
  let r = 0;
  for (let i = 0; i < a.length; i++) r |= a.charCodeAt(i) ^ b.charCodeAt(i);
  return r === 0;
}

async function verify(req, env, body) {
  if (!env.RELAY_SECRET) return false;
  const ts = req.headers.get("x-kami-ts") || "", sig = (req.headers.get("x-kami-sig") || "").toLowerCase();
  const n = Number(ts);
  if (!ts || !sig || !Number.isFinite(n) || Math.abs(Date.now() / 1000 - n) > 300) return false;
  return safeEq(await hmacHex(env.RELAY_SECRET, `${ts}.${body}`), sig);
}

const J = (obj, status = 200) => new Response(JSON.stringify(obj), {
  status, headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" } });

async function getList(env, key) {
  try { return JSON.parse((await env.RELAY.get(key)) || "[]"); } catch { return []; }
}

export default {
  async fetch(req, env) {
    const url = new URL(req.url);
    const p = url.pathname;
    if (p === "/" || p === "/index.html") {
      return new Response(PAGE, { headers: { "content-type": "text/html; charset=utf-8", "cache-control": "no-store",
        "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'",
        "referrer-policy": "no-referrer" } });
    }
    if (p === "/manifest.webmanifest") {
      return new Response(JSON.stringify({ name: "Kami Relay", short_name: "Kami", start_url: "/", display: "standalone",
        background_color: "#07060B", theme_color: "#07060B" }), { headers: { "content-type": "application/manifest+json" } });
    }
    if (!p.startsWith("/api/")) return new Response("", { status: 404 });

    if (p === "/api/health" && req.method === "GET") {
      if (!(await verify(req, env, "ping"))) return J({ ok: false, error: "auth" }, 401);
      return J({ ok: true, alive: true, queue: (await getList(env, "queue")).length });
    }
    if (p === "/api/queue/push" && req.method === "POST") {      // telefon -> link ekle
      const raw = await req.text();
      if (raw.length > 8192 || !(await verify(req, env, raw))) return J({ ok: false, error: "auth" }, 401);
      let b = {};
      try { b = JSON.parse(raw); } catch { return J({ ok: false, error: "json" }, 400); }
      const links = String(b.url || "").split(/\s+/).filter((u) => /^(https?:\/\/|magnet:\?)/i.test(u)).slice(0, 20);
      if (!links.length) return J({ ok: false, error: "no_link" }, 400);
      const q = await getList(env, "queue");
      for (const u of links) q.push({ url: u.slice(0, 4000), at: Date.now() });
      await env.RELAY.put("queue", JSON.stringify(q.slice(-MAX_QUEUE)));
      return J({ ok: true, added: links.length });
    }
    if (p === "/api/queue/pull" && req.method === "GET") {        // Kami -> kuyrugu al ve bosalt
      if (!(await verify(req, env, "pull"))) return J({ ok: false, error: "auth" }, 401);
      const q = await getList(env, "queue");
      if (q.length) await env.RELAY.put("queue", "[]");
      return J({ ok: true, items: q });
    }
    if (p === "/api/events" && req.method === "POST") {           // Kami -> olay
      const raw = await req.text();
      if (raw.length > 16384 || !(await verify(req, env, raw))) return J({ ok: false, error: "auth" }, 401);
      let ev = {};
      try { ev = JSON.parse(raw); } catch { return J({ ok: false, error: "json" }, 400); }
      const list = await getList(env, "events");
      list.push({ type: String(ev.type || "info").slice(0, 40), payload: ev.payload || {}, ts: Date.now() });
      await env.RELAY.put("events", JSON.stringify(list.slice(-MAX_EVENTS)));
      if (env.NTFY_TOPIC) {
        const title = ev.type === "download.completed" ? "Kami: indirme bitti" : `Kami: ${String(ev.type || "olay")}`;
        const msg = String((ev.payload && (ev.payload.title || ev.payload.message)) || "").slice(0, 300);
        await fetch(`https://ntfy.sh/${encodeURIComponent(env.NTFY_TOPIC)}`, { method: "POST", body: msg || title,
          headers: { Title: title, Tags: "inbox_tray" } }).catch(() => {});
      }
      return J({ ok: true });
    }
    if (p === "/api/events/list" && req.method === "GET") {       // telefon -> son olaylar
      if (!(await verify(req, env, "events"))) return J({ ok: false, error: "auth" }, 401);
      return J({ ok: true, items: (await getList(env, "events")).reverse(), queue: (await getList(env, "queue")).length });
    }
    return J({ ok: false, error: "not_found" }, 404);
  },
};

const PAGE = `<!DOCTYPE html><html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#07060B"><meta name="apple-mobile-web-app-capable" content="yes">
<meta name="apple-mobile-web-app-status-bar-style" content="black-translucent"><link rel="manifest" href="/manifest.webmanifest">
<title>Kami Relay</title><style>
:root{--bg:#07060B;--fg:#EDE9F6;--mut:#8E86A3;--ac:#9D6BFF;--ok:#2EE6A6;--line:#221A33}
*{box-sizing:border-box}html,body{margin:0;background:var(--bg);color:var(--fg);font:500 16px system-ui,-apple-system,sans-serif}
main{max-width:520px;margin:0 auto;padding:calc(env(safe-area-inset-top) + 20px) 18px 40px}
h1{font-size:15px;letter-spacing:4px;color:#C4B5FD;margin:0 0 18px}
textarea,input{width:100%;background:#0F0B17;color:var(--fg);border:1px solid var(--line);padding:14px;font:inherit;outline:none}
textarea:focus,input:focus{border-color:var(--ac)}textarea{min-height:110px;resize:vertical}
button{width:100%;margin-top:10px;padding:15px;border:0;background:var(--ac);color:#0B0910;font:700 15px inherit;letter-spacing:1px}
button.sec{background:transparent;color:var(--mut);border:1px solid var(--line)}
.msg{min-height:22px;margin:10px 0;color:var(--mut);font-size:14px}.ok{color:var(--ok)}
h2{font-size:12px;letter-spacing:3px;color:var(--mut);margin:28px 0 8px}
.ev{border-left:2px solid var(--ac);padding:8px 12px;margin:6px 0;background:#0C0912;font-size:14px}
.ev small{display:block;color:var(--mut);font-size:12px;margin-top:3px}
</style></head><body><main>
<h1>KAMI · RELAY</h1>
<section id="setup" hidden><p class="msg">Bu cihazi eslemek icin Kami'deki Relay gizli anahtarini bir kez gir.</p>
<input id="sec" type="password" autocomplete="off" placeholder="Gizli anahtar"><button id="save">Kaydet</button></section>
<section id="app" hidden>
<textarea id="url" placeholder="Link yapistir (YouTube, magnet, dosya...). Birden cok link alt alta olabilir."></textarea>
<button id="send">KAMI'YE GONDER</button><div class="msg" id="msg"></div>
<h2>SON OLAYLAR <span id="q"></span></h2><div id="evs"></div>
<button class="sec" id="forget">Bu cihazdaki anahtari unut</button></section>
<script>
const $=s=>document.querySelector(s);let SEC=localStorage.getItem("kami_relay_sec")||"";
async function sig(body){const ts=String(Math.floor(Date.now()/1000));const k=await crypto.subtle.importKey("raw",new TextEncoder().encode(SEC),{name:"HMAC",hash:"SHA-256"},false,["sign"]);
const s=await crypto.subtle.sign("HMAC",k,new TextEncoder().encode(ts+"."+body));return{"X-Kami-Ts":ts,"X-Kami-Sig":[...new Uint8Array(s)].map(b=>b.toString(16).padStart(2,"0")).join("")}}
function show(){$("#setup").hidden=!!SEC;$("#app").hidden=!SEC;if(SEC)load()}
$("#save").onclick=()=>{SEC=$("#sec").value.trim();if(SEC){localStorage.setItem("kami_relay_sec",SEC);show()}};
$("#forget").onclick=()=>{localStorage.removeItem("kami_relay_sec");SEC="";show()};
$("#send").onclick=async()=>{const u=$("#url").value.trim();if(!u)return;const body=JSON.stringify({url:u});
$("#msg").textContent="Gonderiliyor...";$("#msg").className="msg";
try{const r=await fetch("/api/queue/push",{method:"POST",headers:{"content-type":"application/json",...await sig(body)},body});const j=await r.json();
if(j.ok){$("#msg").textContent="✓ "+j.added+" link kuyrukta. Kami acikken 20 sn icinde indirmeye baslar.";$("#msg").className="msg ok";$("#url").value="";load()}
else $("#msg").textContent=j.error==="auth"?"Anahtar yanlis ya da saat farki var.":"Hata: "+j.error}catch(e){$("#msg").textContent="Baglanti hatasi"}};
async function load(){try{const r=await fetch("/api/events/list",{headers:await sig("events")});const j=await r.json();if(!j.ok)return;
$("#q").textContent=j.queue?"· kuyrukta "+j.queue:"";$("#evs").innerHTML="";
for(const e of j.items.slice(0,25)){const d=document.createElement("div");d.className="ev";
const t=e.type==="download.completed"?"✓ "+(e.payload.title||"Indirme bitti"):(e.payload.title||e.payload.message||e.type);
d.textContent=t;const s=document.createElement("small");s.textContent=new Date(e.ts).toLocaleString("tr-TR");d.appendChild(s);$("#evs").appendChild(d)}}catch(e){}}
if(navigator.share===undefined){}show();setInterval(()=>{if(SEC&&!document.hidden)load()},15000);
</script></main></body></html>`;
