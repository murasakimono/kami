// Kami eklentisi Real-Debrid e2e: sayfadaki magnet/.torrent algilama (rozet + liste), "RD'ye gonder"
// (magnet -> /v1/rd url, .torrent -> tarayici indirir, icerik base64), popup gorunumu (bulut butonu tasmasi + torrent bolumu).
// Yerel test sayfasi + sahte Kami (media_harness, RD taklidi). Kullanicinin Kami'sine dokunmaz.
// Kullanim: NODE_PATH=<puppeteer-core> node tests/e2e/ext_rd_e2e.js [ekran_goruntusu_klasoru]
const fs = require("fs");
const path = require("path");
const os = require("os");
const http = require("http");
const { spawn } = require("child_process");
const puppeteer = require("puppeteer-core");

const ROOT = path.resolve(__dirname, "..", "..");
const EXT = path.join(ROOT, "extension");
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const SHOTS = process.argv[2] || os.tmpdir();
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok }); console.log(`${ok ? "GECTI" : "KALDI"}  ${name} ${info}`); };
const work = fs.mkdtempSync(path.join(os.tmpdir(), "kami-rd-e2e-"));
const state = () => { try { return JSON.parse(fs.readFileSync(path.join(work, "kami", "state.json"), "utf8")); } catch (_) { return { rd: [] }; } };
async function waitFor(fn, ms) { const end = Date.now() + ms; while (Date.now() < end) { const v = fn(); if (v) return v; await sleep(300); } return null; }

const MAGNET1 = "magnet:?xt=urn:btih:dd8255ecdc7ca55fb0bbf81323d87062db1f6d1c&dn=Big+Buck+Bunny";
const MAGNET2 = "magnet:?xt=urn:btih:08ada5a7a6183aae1e09d831df6748d566095a10&dn=Sintel";
const TORRENT = Buffer.from("d8:announce20:http://t.example/ann4:infod6:lengthi1e4:name5:a.txtee");
const PAGE = `<!doctype html><title>RD test</title><h1>Torrentler</h1>
<a href="${MAGNET1}">Big Buck Bunny</a><br><a href="${MAGNET2}">🧲</a><br><a href="/files/ubuntu.iso.torrent">ubuntu.iso.torrent</a>
<a href="/other.html">baska</a><div id="later"></div>`;

(async () => {
  const srv = http.createServer((req, res) => {
    if (req.url.endsWith(".torrent")) { res.writeHead(200, { "Content-Type": "application/x-bittorrent" }); res.end(TORRENT); return; }
    res.writeHead(200, { "Content-Type": "text/html; charset=utf-8" }); res.end(PAGE);
  }).listen(0, "127.0.0.1");
  await new Promise((r) => srv.on("listening", r));
  const BASE = `http://127.0.0.1:${srv.address().port}`;

  const py = path.join(ROOT, ".venv", "Scripts", "python.exe");
  const harness = spawn(py, [path.join(__dirname, "media_harness.py"), path.join(work, "kami")], { stdio: ["pipe", "pipe", "inherit"] });
  await new Promise((r) => harness.stdout.on("data", (d) => { if (String(d).includes("HAZIR")) r(); }));
  const profile = fs.mkdtempSync(path.join(os.tmpdir(), "kami-chrome-"));
  const browser = await puppeteer.launch({
    executablePath: CHROME, headless: false, userDataDir: profile, pipe: true, enableExtensions: [EXT],
    env: { ...process.env, KAMI_BRIDGE_INFO: path.join(work, "kami", "bridge.json") },
    args: ["--no-first-run", "--window-size=1280,900"], defaultViewport: null,
  });
  try {
    const sw = await (await browser.waitForTarget((t) => t.type() === "service_worker" && t.url().includes("service_worker.js"))).worker();
    const page = await browser.newPage();
    await page.goto(BASE + "/", { waitUntil: "domcontentloaded" });
    await sleep(1500);
    const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
    let list = await sw.evaluate((id) => chrome.storage.session.get(`tl:${id}`).then((g) => g[`tl:${id}`] || []), tabId);
    check("sayfada 2 magnet + 1 .torrent bulundu (diger link yok)", list.length === 3 && !list.some((l) => l.url.includes("other")), JSON.stringify(list.map((l) => l.text)));
    check("ad yoksa magnet dn= adi kullanilir", list.some((l) => l.text === "Sintel"));
    const badge = await sw.evaluate((id) => chrome.action.getBadgeText({ tabId: id }), tabId);
    check("simgede 🧲 rozeti", badge === "🧲", JSON.stringify(badge));

    // dinamik sayfa: sonradan eklenen link de yakalanir
    await page.evaluate(() => { document.getElementById("later").innerHTML = '<a href="magnet:?xt=urn:btih:abc&dn=Sonradan">x</a>'; });
    await sleep(3000);
    list = await sw.evaluate((id) => chrome.storage.session.get(`tl:${id}`).then((g) => g[`tl:${id}`] || []), tabId);
    check("sonradan eklenen magnet yakalandi", list.length === 4, String(list.length));

    const r1 = await sw.evaluate((u, p) => sendRd(u, p), MAGNET1, BASE + "/");
    const m = await waitFor(() => state().rd.find((c) => c.kind === "magnet" && c.value === MAGNET1), 5000);
    check("magnet -> Kami /v1/rd -> RD add_magnet", r1 && r1.accepted && !!m, JSON.stringify(r1));
    const r2 = await sw.evaluate((u, p) => sendRd(u, p), BASE + "/files/ubuntu.iso.torrent", BASE + "/");
    const t = await waitFor(() => state().rd.find((c) => c.kind === "torrent"), 5000);
    check(".torrent -> tarayici indirir, icerik RD add_torrent_bytes", r2 && r2.accepted && t && t.size === TORRENT.length && t.value.startsWith("d8:announce"), JSON.stringify(t));
    const r3 = await sw.evaluate(() => sendRd("https://1fichier.com/?abc", ""));
    const l = await waitFor(() => state().rd.find((c) => c.kind === "link"), 5000);
    check("hoster linki (sag tik) -> RD add_link", r3 && r3.accepted && !!l, JSON.stringify(r3));
    const menus = await sw.evaluate(() => new Promise((res) => chrome.contextMenus.update("kami-rd", {}, () => res(!chrome.runtime.lastError))));
    check("sag tik menusunde 'Real-Debrid'e gonder' var", menus === true);

    // popup: torrent bolumu
    await page.bringToFront();
    await sw.evaluate(() => chrome.action.openPopup());
    const pt = await browser.waitForTarget((x) => x.url().endsWith("popup.html"), { timeout: 5000 }).catch(() => null);
    if (pt) {
      const pp = await pt.asPage();
      await sleep(1200);
      const info = await pp.evaluate(() => ({ title: document.getElementById("torrentsTitle").textContent,
        n: document.querySelectorAll("#torrentList li").length, hidden: document.getElementById("torrents").hidden }));
      check("popup'ta torrent bolumu (4 link)", !info.hidden && info.n === 4, JSON.stringify(info));
      await pp.screenshot({ path: path.join(SHOTS, "popup_torrents.png") });
      await pp.close();
    } else check("popup acilamadi (openPopup)", false);

    // popup: bulut sayfasinda buton metni tasmiyor (Yandex paylasimi)
    await page.goto("https://disk.yandex.ru/d/4Z0GsDwfR4gkPA", { waitUntil: "domcontentloaded" });
    await sleep(3000);
    const tl2 = await sw.evaluate((id) => chrome.storage.session.get(`tl:${id}`).then((g) => g[`tl:${id}`] || []), tabId);
    check("baska sayfaya gecince eski torrent listesi silinir", tl2.length === 0, String(tl2.length));
    await sw.evaluate(() => chrome.action.openPopup());
    const pt2 = await browser.waitForTarget((x) => x.url().endsWith("popup.html") , { timeout: 5000 }).catch(() => null);
    if (pt2) {
      const pp = await pt2.asPage();
      await sleep(1000);
      const b = await pp.evaluate(() => { const el = document.getElementById("page"); return { text: el.innerText, sw: el.scrollWidth, cw: el.clientWidth, sh: el.scrollHeight, ch: el.clientHeight }; });
      check("popup bulut butonu tasmiyor", b.sw <= b.cw && b.sh <= b.ch && /Kami/.test(b.text), JSON.stringify(b));
      await pp.screenshot({ path: path.join(SHOTS, "popup_cloud.png") });
    } else check("popup acilamadi (bulut)", false);
  } catch (e) {
    console.error(e); check("beklenmeyen hata", false, String(e));
  } finally {
    await browser.close().catch(() => {});
    harness.stdin.end();
    srv.close();
    const failed = results.filter((r) => !r.ok).length;
    console.log(`\n${results.length - failed}/${results.length} gecti`);
    setTimeout(() => process.exit(failed ? 1 : 0), 1500);
  }
})();
