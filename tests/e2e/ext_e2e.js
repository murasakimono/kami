// Kami eklentisi uctan uca testi: gecici profilli Chrome + Extensions.loadUnpacked + gercek Kami.
// On kosul: Kami acik (indirme klasorunu ayarlardan gecici bir klasore alin), native host kayitli,
// puppeteer-core kurulu (proje disinda: npm i puppeteer-core; NODE_PATH ile gosterin).
// Kullanim: node tests/e2e/ext_e2e.js <extension_dir> <chrome_download_dir>
const http = require("http");
const crypto = require("crypto");
const fs = require("fs");
const path = require("path");
const os = require("os");
const puppeteer = require("puppeteer-core");

const [extDir, chromeDl] = process.argv.slice(2);
const CHROME = "C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe";
const big = crypto.randomBytes(30 * 1024 * 1024);
const exe = Buffer.concat([Buffer.from("MZ"), crypto.randomBytes(2 * 1024 * 1024)]);
const small = Buffer.from("kucuk dosya\n".repeat(800));

function serve() {
  const files = { "/big.bin": big, "/alt.bin": big, "/menu.bin": big, "/setup.exe": exe, "/small.txt": small };
  const srv = http.createServer((req, res) => {
    const p = req.url.split("?")[0];
    if (p === "/" || p === "/page.html") {
      res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" });
      res.end(`<a id="big" href="/big.bin">big</a> <a id="small" href="/small.txt">small</a>
               <a id="exe" href="/setup.exe">exe</a> <a id="alt" href="/alt.bin">alt</a>`);
      return;
    }
    const data = files[p];
    if (!data) { res.writeHead(404); res.end(); return; }
    let start = 0, end = data.length - 1, code = 200;
    const m = /bytes=(\d+)-(\d*)/.exec(req.headers.range || "");
    if (m) { start = +m[1]; if (m[2]) end = +m[2]; code = 206; }
    const h = { "Content-Length": end - start + 1, "Accept-Ranges": "bytes", "Content-Type": "application/octet-stream",
                "Content-Disposition": `attachment; filename="${path.basename(p)}"` };
    if (code === 206) h["Content-Range"] = `bytes ${start}-${end}/${data.length}`;
    srv.hits.push({ p, cookie: req.headers.cookie || "", ua: req.headers["user-agent"] || "", range: req.headers.range || "" });
    res.writeHead(code, h);
    if (req.method === "HEAD") return res.end();
    res.end(data.subarray(start, end + 1));
  });
  srv.hits = [];
  return new Promise((r) => srv.listen(0, "127.0.0.1", () => r(srv)));
}

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok }); console.log(`${ok ? "GECTI" : "KALDI"}  ${name} ${info}`); };

(async () => {
  const srv = await serve();
  const base = `http://127.0.0.1:${srv.address().port}`;
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kami-chrome-"));
  // tarayicinin kendi indirdikleri kullanicinin Indirilenler klasorune degil test klasorune gitsin
  fs.mkdirSync(path.join(profile, "Default"), { recursive: true });
  fs.writeFileSync(path.join(profile, "Default", "Preferences"), JSON.stringify({
    download: { default_directory: chromeDl, prompt_for_download: false, directory_upgrade: true },
  }));
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: false, userDataDir: profile, pipe: true,
    enableExtensions: [extDir],
    args: ["--no-first-run", "--no-default-browser-check", "--window-size=900,600"],
  });
  try {
    const swTarget = await browser.waitForTarget((t) => t.type() === "service_worker" && t.url().endsWith("service_worker.js"), { timeout: 15000 });
    const extId = new URL(swTarget.url()).host;
    check("eklenti yuklendi, ID sabit key'den", extId === "aanjhajdcflkkppfpmoagpbbcdpffapi", extId);
    const sw = await swTarget.worker();

    const ping = await sw.evaluate(() => chrome.runtime.sendNativeMessage("com.metehan.kami", { type: "ping" }));
    check("native host -> Kami ping", ping && ping.ok === true, JSON.stringify(ping));

    const page = await browser.newPage();
    const cdp = await page.createCDPSession();
    await cdp.send("Browser.setDownloadBehavior", { behavior: "default" }).catch(() => {});
    await page.setCookie({ name: "oturum", value: "abc123", domain: "127.0.0.1", path: "/" });
    await page.goto(`${base}/page.html`);

    const dlState = () => sw.evaluate(() => chrome.downloads.search({}).then((l) => l.map((d) => ({ url: d.url, state: d.state }))));

    // 1) buyuk dosya -> Kami devralir, tarayicida kalmaz
    await page.click("#big");
    await sleep(4000);
    let dls = await dlState();
    const bigHit = srv.hits.filter((h) => h.p === "/big.bin");
    check("buyuk dosya Kami'ye gecti (tarayici listesinde yok)", !dls.some((d) => d.url.endsWith("/big.bin")), JSON.stringify(dls));
    check("Kami cok baglantiyla cekti (Range istekleri)", bigHit.filter((h) => h.range).length > 1, `istek=${bigHit.length}`);
    check("cerez ve User-Agent Kami'ye aktarildi", bigHit.some((h) => h.range && h.cookie.includes("oturum=abc123") && /Chrome/.test(h.ua)));

    // 2) kucuk dosya (<1 MB) -> tarayici indirir
    await page.click("#small");
    await sleep(3000);
    dls = await dlState();
    check("kucuk dosya tarayicida kaldi", dls.some((d) => d.url.endsWith("/small.txt")), JSON.stringify(dls));

    // 3) Alt + tik -> tarayici indirir
    await page.keyboard.down("Alt");
    await page.click("#alt");
    await page.keyboard.up("Alt");
    await sleep(3000);
    dls = await dlState();
    check("Alt+tik tarayicida kaldi", dls.some((d) => d.url.endsWith("/alt.bin")), JSON.stringify(dls));

    // 4) .exe -> Kami onay ister
    await page.click("#exe");
    await sleep(3000);
    dls = await dlState();
    check(".exe Kami'ye gecti (onay bekliyor)", !dls.some((d) => d.url.endsWith("/setup.exe")), JSON.stringify(dls));

    // 5) sag tik menusu isleyicisi (menu UI'si CDP ile acilamaz; isleyici dogrudan cagrilir)
    const before = srv.hits.filter((h) => h.p === "/menu.bin").length;
    await sw.evaluate((u, p) => onMenuClicked({ menuItemId: "kami-download", linkUrl: u, pageUrl: p }, null), `${base}/menu.bin`, `${base}/page.html`);
    await sleep(3000);
    const menuHits = srv.hits.filter((h) => h.p === "/menu.bin").slice(before);
    dls = await dlState();
    check("sag tik -> Kami indirdi", menuHits.filter((h) => h.range).length > 1 && !dls.some((d) => d.url.endsWith("/menu.bin")), `istek=${menuHits.length}`);
    const menus = await sw.evaluate(() => new Promise((r) => chrome.contextMenus.update("kami-download", {}, () => r(!chrome.runtime.lastError))));
    check("sag tik menusu kayitli", menus === true);
  } finally {
    await browser.close();
    srv.close();
    fs.rmSync(profile, { recursive: true, force: true });
  }
  const failed = results.filter((r) => !r.ok).length;
  console.log(`\n${results.length - failed}/${results.length} gecti`);
  process.exit(failed ? 1 : 0);
})().catch((e) => { console.error(e); process.exit(2); });
