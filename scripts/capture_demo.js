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
    if (!st.busy && st.h === last) { if (++still >= 4) break; } else still = 0;
    last = st.h;
    await sleep(400);
  }
  await sleep(1200);
}

async function shot(page, name) {
  await page.setViewportSize({ width: 1440, height: 3200 });
  await sleep(1500);
  await page.evaluate(() => {
    for (const e of [document.querySelector('[data-testid="stMain"]'), document.scrollingElement]) if (e) e.scrollTop = 0;
    document.querySelectorAll('[data-testid="stToast"]').forEach((t) => t.remove());
  });
  await sleep(400);
  await page.screenshot({ path: path.join(OUT, name + ".png") });
  await page.setViewportSize({ width: 1440, height: 900 });
  console.log("captured " + name);
}

async function go(page, label) {
  if (label === "Follow-ups") await page.locator(".st-key-top_msg button").first().click();
  else await page.locator('.st-key-top_nav [role="radiogroup"] label', { hasText: label }).first().click({ timeout: 10000 });
  await sleep(800);
  await loaded(page);
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
  await shot(page, "00-landing");
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
  await page.getByRole("button", { name: "Sign in with email" }).click();
  try {
    await page.locator(".st-key-top_nav").first().waitFor({ timeout: 90000 });
  } catch (e) {
    await page.screenshot({ path: path.join(OUT, "zz-sign-in-failed.png") });
    console.log("Sign-in did not finish; saved zz-sign-in-failed.png");
    await browser.close();
    process.exit(1);
  }
  await loaded(page, 45000);
  await shot(page, "01-dashboard");

  const pages = [["Risk Radar", "02-risk-radar"], ["Action Centre", "03-action-centre"], ["Renewals", "04-renewals"],
                 ["Grow", "05-grow"], ["Members", "06-members"], ["Owner", "07-owner"], ["Follow-ups", "08-follow-ups"]];
  for (const [label, name] of pages) {
    try { await go(page, label); await shot(page, name); }
    catch (e) { console.log(`skipped ${name}: ${String(e).split("\n")[0]}`); await page.keyboard.press("Escape").catch(() => {}); }
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
