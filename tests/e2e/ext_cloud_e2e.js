// Kami eklentisi bulut e2e: paylasim sayfasinda sabit "Kami ile indir" butonu + rozet, tikla -> Kami secim penceresi,
// MEGA'da video butonu yok, kisisel diskte ipucu. Gercek siteler (ag gerekir). Kullanicinin Kami'sine dokunmaz.
// Kullanim: NODE_PATH=<puppeteer-core> node tests/e2e/ext_cloud_e2e.js
const fs = require("fs");
const path = require("path");
const os = require("os");
const { spawn } = require("child_process");
const puppeteer = require("puppeteer-core");

const ROOT = path.resolve(__dirname, "..", "..");
const EXT = path.join(ROOT, "extension");
const CHROME = "C:/Program Files/Google/Chrome/Application/chrome.exe";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));
const results = [];
const check = (name, ok, info = "") => { results.push({ name, ok }); console.log(`${ok ? "GECTI" : "KALDI"}  ${name} ${info}`); };
const work = fs.mkdtempSync(path.join(os.tmpdir(), "kami-cloud-e2e-"));
const state = () => { try { return JSON.parse(fs.readFileSync(path.join(work, "kami", "state.json"), "utf8")); } catch (_) { return { items: [], chooses: [] }; } };
async function waitFor(fn, ms) { const end = Date.now() + ms; while (Date.now() < end) { const v = fn(); if (v) return v; await sleep(300); } return null; }

const YANDEX = "https://disk.yandex.ru/d/4Z0GsDwfR4gkPA";
const MEGA = "https://mega.nz/file/ijBwXbDK";   // anahtarsiz da paylasim sayfasidir

async function cloudButton(page) {
  return page.evaluate(() => {
    const h = document.querySelector("kami-cloud-button");
    if (!h || !h.shadowRoot) return null;
    let open = false; try { open = h.matches(":popover-open"); } catch (_) {}
    return { open, label: h.shadowRoot.querySelector(".label").textContent, hint: h.shadowRoot.querySelector(".main").classList.contains("hint") };
  });
}

(async () => {
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

    await page.goto(YANDEX, { waitUntil: "domcontentloaded" });
    const yb = await (async () => { for (let i = 0; i < 20; i++) { const b = await cloudButton(page); if (b && b.open) return b; await sleep(500); } return cloudButton(page); })();
    check("Yandex paylasiminda sayfa butonu (popover acik)", yb && yb.open && !yb.hint, JSON.stringify(yb));
    const tabId = await sw.evaluate(async () => (await chrome.tabs.query({ active: true, lastFocusedWindow: true }))[0].id);
    const badge = await sw.evaluate((id) => chrome.action.getBadgeText({ tabId: id }), tabId);
    check("simgede bulut rozeti", badge === "☁", JSON.stringify(badge));
    await page.evaluate(() => document.querySelector("kami-cloud-button").shadowRoot.querySelector(".main").click());
    const yurl = page.url();   // Yandex disk.360.yandex.ru'ya yonlendirebilir
    const ch = await waitFor(() => state().chooses.find((c) => c.url === yurl), 10000);
    check("butona tiklama -> Kami secim penceresi (Yandex linki)", !!ch, JSON.stringify(ch));

    // popup yolu: page-add mesaji (sag tiki ezen siteler)
    const pr = await sw.evaluate((u) => sendPage(u), YANDEX);
    check("popup 'Bu sayfayi Kami ile indir' yolu", pr && pr.ok && pr.accepted, JSON.stringify(pr));

    await page.goto(MEGA, { waitUntil: "domcontentloaded" });
    await sleep(6000);
    const mb = await cloudButton(page);
    check("MEGA paylasiminda sayfa butonu", mb && mb.open, JSON.stringify(mb));
    const vb = await sw.evaluate((u) => sendMedia({ url: "https://gfs.userstorage.mega.co.nz/dl/x", pageUrl: u, mode: "mp4" }), MEGA + "#" + "A".repeat(43));
    const mch = await waitFor(() => state().chooses.find((c) => c.url.startsWith(MEGA)), 8000);
    check("MEGA video butonu -> bulut (yt-dlp degil)", vb && vb.accepted && !!mch && !state().items.length, JSON.stringify(vb));

    await page.goto("https://disk.yandex.ru/client/disk", { waitUntil: "domcontentloaded" });
    await sleep(4000);
    const pb = await cloudButton(page);
    check("kisisel Yandex diskinde ipucu (giris sayfasina yonlenmediyse)", !pb || pb.hint || !pb.open, JSON.stringify(pb) + " " + page.url());
  } catch (e) {
    console.error(e); check("beklenmeyen hata", false, String(e));
  } finally {
    await browser.close().catch(() => {});
    harness.stdin.end();
    const failed = results.filter((r) => !r.ok).length;
    console.log(`\n${results.length - failed}/${results.length} gecti`);
    setTimeout(() => process.exit(failed ? 1 : 0), 1500);
  }
})();
