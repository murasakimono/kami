// Kami eklentisi medya e2e: trafik yakalama (MP4 + HLS), video ustu buton, YouTube butonu.
// Kullanicinin Kami'sine dokunmaz: tests/e2e/media_harness.py basliksiz test sunucusunu acar,
// Chrome KAMI_BRIDGE_INFO ile o sunucuya baglanir. On kosul: native host kayitli, ffmpeg PATH'te,
// puppeteer-core (proje disi; NODE_PATH ile).  Kullanim: node tests/e2e/ext_media_e2e.js [--youtube]
const http = require("http");
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn, spawnSync } = require("child_process");
const puppeteer = require("puppeteer-core");

const ROOT = path.resolve(__dirname, "..", "..");
const EXT = path.join(ROOT, "extension");
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const withYoutube = process.argv.includes("--youtube");
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok }); console.log(`${ok ? "GECTI" : "KALDI"}  ${name} ${info}`); };

const work = fs.mkdtempSync(path.join(os.tmpdir(), "kami-media-e2e-"));
const media = path.join(work, "www");
fs.mkdirSync(path.join(media, "hls"), { recursive: true });
const ff = (args) => spawnSync("ffmpeg", ["-v", "error", "-y", ...args], { stdio: "inherit" });
ff(["-f", "lavfi", "-i", "testsrc2=size=1280x720:rate=30", "-f", "lavfi", "-i", "sine=f=440", "-t", "6",
    "-c:v", "libx264", "-b:v", "3M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-movflags", "+faststart", path.join(media, "clip.mp4")]);
ff(["-i", path.join(media, "clip.mp4"), "-c", "copy", "-f", "hls", "-hls_time", "2", "-hls_list_size", "0",
    path.join(media, "hls", "index.m3u8")]);

const TYPES = { ".mp4": "video/mp4", ".m3u8": "application/vnd.apple.mpegurl", ".ts": "video/mp2t" };
function serve() {
  const srv = http.createServer((req, res) => {
    const p = decodeURIComponent(req.url.split("?")[0]);
    if (p === "/" || p === "/page.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(`<title>Kami Test Klibi</title><body style="margin:0;background:#111">
        <video id="v" src="/clip.mp4" width="960" height="540" muted controls style="display:block;margin:40px"></video>
        <script>document.getElementById('v').play().catch(()=>{}); fetch('/hls/index.m3u8').then(r=>r.text());</script>`);
      return;
    }
    const file = path.join(media, p);
    if (!file.startsWith(media) || !fs.existsSync(file) || fs.statSync(file).isDirectory()) { res.writeHead(404); res.end(); return; }
    const size = fs.statSync(file).size;
    let start = 0, end = size - 1, code = 200;
    const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || "");
    if (m) { start = +m[1]; if (m[2]) end = Math.min(+m[2], size - 1); code = 206; }
    const h = { "Content-Length": end - start + 1, "Accept-Ranges": "bytes", "Content-Type": TYPES[path.extname(p)] || "application/octet-stream" };
    if (code === 206) h["Content-Range"] = `bytes ${start}-${end}/${size}`;
    srv.hits.push({ p, range: req.headers.range || "", referer: req.headers.referer || "" });
    res.writeHead(code, h);
    if (req.method === "HEAD") return res.end();
    fs.createReadStream(file, { start, end }).pipe(res);
  });
  srv.hits = [];
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

const state = () => { try { return JSON.parse(fs.readFileSync(path.join(work, "kami", "state.json"), "utf8")); } catch (_) { return { items: [], chooses: [] }; } };
async function waitFor(fn, ms = 60000) {
  const t0 = Date.now();
  while (Date.now() - t0 < ms) { const v = fn(); if (v) return v; await sleep(500); }
  return null;
}

async function clickVideoButton(page, mode, videoSel = "video") {
  const box = await page.$eval(videoSel, (v) => { const r = v.getBoundingClientRect(); return { x: r.left, y: r.top, w: r.width, h: r.height }; });
  await page.mouse.move(box.x + box.w / 2, box.y + box.h / 2);
  await sleep(150);
  await page.mouse.move(box.x + box.w / 2 + 20, box.y + box.h / 2 + 10);
  const shown = await page.waitForFunction(() => {
    const h = document.querySelector("kami-video-button");
    return h && h.style.display === "block";
  }, { timeout: 5000 }).then(() => true).catch(() => false);
  if (!shown) return false;
  await page.evaluate((mode) => {
    const r = document.querySelector("kami-video-button").shadowRoot;
    r.querySelector(".main").click();
    r.querySelector(`[data-mode="${mode}"]`).click();
  }, mode);
  return true;
}

(async () => {
  const srv = await serve();
  const base = `http://127.0.0.1:${srv.address().port}`;
  const py = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const harness = spawn(py, [path.join(__dirname, "media_harness.py"), path.join(work, "kami")], { stdio: ["pipe", "pipe", "inherit"] });
  await new Promise((r) => harness.stdout.on("data", (d) => { if (String(d).includes("HAZIR")) r(); }));

  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kami-chrome-"));
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: false, userDataDir: profile, pipe: true, enableExtensions: [EXT],
    env: { ...process.env, KAMI_BRIDGE_INFO: path.join(work, "kami", "bridge.json") },
    args: ["--no-first-run", "--autoplay-policy=no-user-gesture-required", "--window-size=1280,900"],
    defaultViewport: null,
  });
  try {
    const swTarget = await browser.waitForTarget((t) => t.type() === "service_worker" && t.url().includes("service_worker.js"));
    const sw = await swTarget.worker();
    const ping = await sw.evaluate(() => native({ type: "ping" }));
    check("native host -> test Kami ping", ping && ping.ok === true, JSON.stringify(ping));

    // 1) trafik yakalama
    const page = await browser.newPage();
    await page.goto(`${base}/page.html`, { waitUntil: "load" });
    await sleep(2500);
    const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
    const caught = await sw.evaluate((id) => getTabMedia(id), tabId);
    check("MP4 akisi yakalandi", caught.some((m) => m.url.endsWith("/clip.mp4") && m.kind === "video"), JSON.stringify(caught.map((m) => [m.kind, m.url.split("/").pop()])));
    check("HLS (m3u8) yakalandi, .ts parcalari atlandi", caught.some((m) => m.kind === "hls") && !caught.some((m) => m.url.endsWith(".ts")));
    const badge = await sw.evaluate((id) => chrome.action.getBadgeText({ tabId: id }), tabId);
    check("rozette yakalanan sayisi", Number(badge) >= 2, `rozet=${badge}`);

    // 2) video ustu buton -> MP4
    const clicked = await clickVideoButton(page, "mp4");
    check("video ustu buton gorundu", clicked);
    const mp4 = await waitFor(() => state().items.find((d) => d.url.endsWith("/clip.mp4") && d.status === "complete"), 60000);
    check("butonla MP4 Kami'de indi (yt-dlp + aria2)", !!mp4, mp4 ? `${mp4.filename} ${mp4.size}` : JSON.stringify(state().items));
    check("Kami MP4'u Range ile cekti", srv.hits.filter((h) => h.p === "/clip.mp4" && h.range).length >= 1);

    // 3) acilir penceredeki HLS -> MP4 (yt-dlp HLS)
    const hls = caught.find((m) => m.kind === "hls");
    if (hls) {
      const r = await sw.evaluate((u, pg) => sendMedia({ url: u, pageUrl: pg, mode: "mp4", title: "hls testi" }), hls.url, `${base}/page.html`);
      const done = await waitFor(() => state().items.find((d) => d.url === hls.url && (d.status === "complete" || d.status === "error")), 60000);
      check("HLS -> MP4 indi", r.accepted && done && done.status === "complete", done ? `${done.status} ${done.filename} ${done.error}` : "");
      check("HLS isteklerinde Referer var", srv.hits.some((h) => h.p.endsWith(".ts") && h.referer.includes("/page.html")));
    }

    // 4) "Kami'de sec" -> Kami'ye secim istegi
    await page.mouse.move(5, 5); await sleep(2600);
    await clickVideoButton(page, "choose");
    const ch = await waitFor(() => state().chooses.find((c) => c.url.endsWith("/clip.mp4")), 10000);
    check("Kami'de sec istegi ulasti", !!ch);

    // 5) YouTube (istege bagli: ag + YouTube gerekir)
    if (withYoutube) {
      const yt = await browser.newPage();
      await yt.goto("https://www.youtube.com/watch?v=jNQXAC9IVRw", { waitUntil: "domcontentloaded" });
      await yt.waitForSelector("video", { timeout: 20000 }).catch(() => null);
      await sleep(4000);
      const ok = await clickVideoButton(yt, "mp3", "video.html5-main-video, video");
      check("YouTube'da video ustu buton", ok);
      const song = await waitFor(() => state().items.find((d) => d.url.includes("jNQXAC9IVRw") && (d.status === "complete" || d.status === "error")), 90000);
      check("YouTube -> MP3 indi", song && song.status === "complete", song ? `${song.filename} ${song.error}` : "");
    }
  } catch (e) {
    console.error(e);
    check("beklenmeyen hata", false, String(e));
  } finally {
    await browser.close().catch(() => {});
    harness.stdin.end();
    srv.close();
    const failed = results.filter((r) => !r.ok).length;
    console.log(`\n${results.length - failed}/${results.length} gecti`);
    setTimeout(() => process.exit(failed ? 1 : 0), 1500);
  }
})();
