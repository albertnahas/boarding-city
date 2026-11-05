// Smoke test: opens every city in site/repos.json in headless Chromium, checks for console errors and that the
// main UI is present, plays the first walkthrough and opens The Daily Commit.
// Setup once:  npm i -D playwright && npx playwright install chromium
// Run:         node scripts/smoke.cjs   (PW_CHROMIUM=/path/to/chrome uses another Chromium build)
const path = require("path"), fs = require("fs");
const { chromium } = require("playwright");
const site = path.join(__dirname, "..", "site");
const repos = JSON.parse(fs.readFileSync(path.join(site, "repos.json"), "utf8"));
(async () => {
  const b = await chromium.launch({ executablePath: process.env.PW_CHROMIUM || undefined, args: ["--allow-file-access-from-files", "--use-gl=angle", "--use-angle=swiftshader", "--enable-unsafe-swiftshader"] });
  let failed = 0;
  {
    const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    p.on("pageerror", e => errs.push(e.message));
    p.on("console", m => m.type() === "error" && errs.push(m.text()));
    await p.goto("file://" + path.join(site, "index.html"));
    await p.waitForTimeout(3000);
    const listed = await p.evaluate(() => typeof REPOS !== "undefined" ? REPOS.length : 0);
    const ok = !errs.length && listed === repos.length;
    failed += !ok;
    console.log(`${ok ? "PASS" : "FAIL"} shell: errors=${JSON.stringify(errs)} repos listed=${listed}/${repos.length}`);
    await p.close();
  }
  for (const r of repos) {
    const p = await b.newPage({ viewport: { width: 1280, height: 800 } });
    const errs = [];
    p.on("pageerror", e => errs.push(e.message));
    p.on("console", m => m.type() === "error" && errs.push(m.text()));
    await p.goto("file://" + path.join(site, r.key, "demo.html"));
    await p.waitForTimeout(4000);
    const ui = await p.evaluate(() => ["fogHud", "nav", "paperBtn", "galleryBtn", "player"].filter(id => !document.getElementById(id)));
    await p.click("#paperBtn"); await p.waitForTimeout(500);
    const paperOpen = await p.evaluate(() => !!document.querySelector("#paper") && getComputedStyle(document.querySelector("#paper")).display !== "none");
    await p.click("#paperClose").catch(() => {});
    await p.click("#galleryBtn"); await p.waitForTimeout(400);
    await p.click("li.flowitem").catch(() => {}); await p.waitForTimeout(3000);
    const playing = await p.evaluate(() => !!(window.cityAPI && window.cityAPI.flow && window.cityAPI.flow.state()));
    const ok = !errs.length && !ui.length && paperOpen && playing;
    failed += !ok;
    console.log(`${ok ? "PASS" : "FAIL"} ${r.key}: errors=${JSON.stringify(errs)} missing=${JSON.stringify(ui)} paper=${paperOpen} flow=${playing}`);
    await p.screenshot({ path: path.join(__dirname, "..", ".cache", `smoke_${r.key}.png`) }).catch(() => {});
    await p.close();
  }
  await b.close();
  process.exit(failed ? 1 : 0);
})();
