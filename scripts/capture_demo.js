// Takes sharp, tall screenshots of each page of the demo gym, for building the demo video.
// Runs from .github/workflows/demo-shots.yml right after the demo gym is reset.
//
//   DEMO_PASSWORD_FILE=/tmp/pw node scripts/capture_demo.js out_dir
//
// The password is read from a file and never printed. Pages are captured at 2x in a
// very tall window, so each PNG holds the whole page and crops stay crisp.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const SITE = process.env.DEMO_SITE || "https://usegympulseai.com";
const EMAIL = process.env.DEMO_EMAIL || "demo@usegympulseai.com";
const PW_FILE = process.env.DEMO_PASSWORD_FILE || "";
const OUT = process.argv[2] || "shots";
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function loaded(page, maxMs = 30000) {
  const t = Date.now();
  let last = -1, still = 0;
  while (Date.now() - t < maxMs) {
    const st = await page.evaluate(() => {
      const busy = document.querySelectorAll('[data-testid="stSkeleton"], [data-testid="stSpinner"]').length;
      const m = document.querySelector('[data-testid="stMain"]') || document.body;
      return { busy, h: m.scrollHeight };
    }).catch(() => ({ busy: 1, h: 0 }));
    if (!st.busy && st.h === last) { if (++still >= 8) break; } else still = 0;
    last = st.h;
    await sleep(400);
  }
  await sleep(3000);
}

async function problems(page, name) {
  // Error boxes, Python error text or a page wider than the screen: printed so the run log lists them
  const r = await page.evaluate(() => ({
    exc: document.querySelectorAll('[data-testid="stException"]').length,
    err: /Traceback|KeyError|TypeError|AttributeError|ValueError|NameError|IndexError/.test(document.body.innerText),
    alerts: Array.from(document.querySelectorAll('[data-testid="stAlertContentError"]')).map((e) => e.innerText.slice(0, 120)),
    wide: document.documentElement.scrollWidth > window.innerWidth + 2,
  })).catch(() => null);
  if (r && (r.exc || r.err || r.alerts.length || r.wide))
    console.log(`PROBLEM on ${name} (${page.viewportSize().width}px): ${JSON.stringify(r)}`);
}

async function shot(page, name) {
  await problems(page, name);
  // The page in screen-sized parts: name-a.png (top), name-b.png, name-c.png, name-d.png
  const scroller = '[data-testid="stMain"]';
  await page.evaluate((sel) => { document.querySelectorAll('[data-testid="stToast"]').forEach((t) => t.remove());
    for (const e of [document.querySelector(sel), document.scrollingElement]) if (e) e.scrollTop = 0; }, scroller);
  for (const [i, y] of [[0, 0], [1, 700], [2, 1400], [3, 2100]]) {
    const moved = await page.evaluate(([sel, y]) => {
      const e = [document.querySelector(sel), document.scrollingElement].find((x) => x && x.scrollHeight > x.clientHeight + 10);
      if (!e) return y === 0;
      e.scrollTop = y; return y === 0 || Math.abs(e.scrollTop - y) < 650;
    }, [scroller, y]);
    if (!moved) break;
    await sleep(1800);
    await page.screenshot({ path: path.join(OUT, `${name}-${"abcd"[i]}.png`) });
  }
  console.log("captured " + name);
  if (process.env.PHONE_TOO) {
    // the same page at phone size (390 x 844): name-m-a.png, name-m-b.png …
    const big = page.viewportSize();
    await page.setViewportSize({ width: 390, height: 844 });
    await sleep(2500);
    await problems(page, name + "-phone");
    for (const [i, y] of [[0, 0], [1, 700], [2, 1400], [3, 2100], [4, 2800]]) {
      const moved = await page.evaluate(([sel, y]) => {
        const e = [document.querySelector(sel), document.scrollingElement].find((x) => x && x.scrollHeight > x.clientHeight + 10);
        if (!e) return y === 0;
        e.scrollTop = y; return y === 0 || Math.abs(e.scrollTop - y) < 650;
      }, [scroller, y]);
      if (!moved) break;
      await sleep(1200);
      await page.screenshot({ path: path.join(OUT, `${name}-m-${"abcde"[i]}.png`) });
    }
    await page.setViewportSize(big);
    await page.evaluate((sel) => { for (const e of [document.querySelector(sel), document.scrollingElement]) if (e) e.scrollTop = 0; }, scroller);
    await sleep(2000);
  }
}

async function go(page, label) {
  if (label === "Follow-ups") await page.locator(".st-key-top_msg button").first().click();
  else await page.locator('.st-key-top_nav [role="radiogroup"] label', { hasText: label }).first().click({ timeout: 10000 });
  await sleep(1500);
  await loaded(page, 45000);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const password = PW_FILE && fs.existsSync(PW_FILE) ? fs.readFileSync(PW_FILE, "utf8").trim() : "";
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 2 });
  const page = await ctx.newPage();
  await page.goto(SITE, { waitUntil: "domcontentloaded", timeout: 180000 });
  await page.locator('input[aria-label="Email address"]').first().waitFor({ timeout: 180000 });
  await loaded(page);

  if (!password) { console.log("No password file: landing only."); await browser.close(); return; }

  // Same steps as the demo recorder, which signs in reliably
  const email = page.locator('input[aria-label="Email address"]').first();
  await email.scrollIntoViewIfNeeded();
  await email.click();
  await email.pressSequentially(EMAIL, { delay: 25 });
  const pw = page.locator('input[aria-label="Password"]').first();
  await pw.click();
  await pw.fill(password);
  await sleep(500);
  // Up to 3 tries: a busy server sometimes drops the first click
  let ok = false;
  for (let tryN = 1; tryN <= 3 && !ok; tryN++) {
    await page.getByRole("button", { name: "Sign in with email" }).click().catch(() => {});
    ok = await page.locator(".st-key-top_nav").first().waitFor({ timeout: 45000 }).then(() => true).catch(() => false);
    if (!ok) {
      console.log(`sign-in try ${tryN} did not finish`);
      await page.screenshot({ path: path.join(OUT, `zz-sign-in-try${tryN}.png`) });
      const pw2 = page.locator('input[aria-label="Password"]').first();
      if (await pw2.count()) { await pw2.click().catch(() => {}); await pw2.fill(password).catch(() => {}); }
    }
  }
  if (!ok) { await browser.close(); process.exit(1); }
  await loaded(page, 45000);
  await shot(page, "01-dashboard");

  const pages = [["Risk Radar", "02-risk-radar"], ["Action Centre", "03-action-centre"], ["Renewals", "04-renewals"],
                 ["Grow", "05-grow"], ["Members", "06-members"], ["Owner", "07-owner"], ["Follow-ups", "08-follow-ups"],
                 ["Archie", "10-archie"], ["Train", "11-train"], ["Check-in", "12-check-in"]];
  for (const [label, name] of pages) {
    try { await go(page, label); await shot(page, name); }
    catch (e) { console.log(`skipped ${name}: ${String(e).split("\n")[0]}`); await page.keyboard.press("Escape").catch(() => {}); }
  }
  // Pages in the menu (top right)
  for (const [label, name] of [["Settings", "13-settings"], ["Subscription", "14-subscription"],
                               ["Prediction check", "15-prediction-check"], ["FAQs", "16-faqs"]]) {
    try {
      await page.locator(".st-key-top_menu button").first().click({ timeout: 8000 });
      await sleep(1200);
      await page.getByRole("button", { name: label, exact: true }).first().click({ timeout: 8000 });
      await sleep(1500);
      await loaded(page, 45000);
      await shot(page, name);
    } catch (e) { console.log(`skipped ${name}: ${String(e).split("\n")[0]}`); await page.keyboard.press("Escape").catch(() => {}); }
  }
  // One member's profile, opened from the Dashboard's priorities
  try {
    await go(page, "Dashboard");
    await page.locator('[data-testid="stMain"] button', { hasText: /^Profile$/ }).first().click({ timeout: 8000 });
    await sleep(800);
    await loaded(page);
    await shot(page, "09-member-profile");
  } catch (e) { console.log(`skipped profile: ${String(e).split("\n")[0]}`); }
  await browser.close();
})();
