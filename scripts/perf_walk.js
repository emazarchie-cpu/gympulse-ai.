// Clicks through every page of the demo gym and times each one, for finding slow pages and errors.
// Runs from .github/workflows/perf-check.yml against the app started by scripts/perf_server.py.
//
//   DEMO_PASSWORD_FILE=/tmp/pw node scripts/perf_walk.js http://localhost:8501 > walk.jsonl
//
// One JSON line per step: what was clicked, when, how long until the page settled, and any
// error box on the page. The password is read from a file and never printed.
const { chromium } = require("playwright");
const fs = require("fs");

const SITE = process.argv[2] || "http://localhost:8501";
const EMAIL = process.env.DEMO_EMAIL || "demo@usegympulseai.com";
const PW_FILE = process.env.DEMO_PASSWORD_FILE || "";
const WIDTH = Number(process.env.WALK_WIDTH || 1440);
const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settled(page, maxMs = 60000) {
  // Done when Streamlit has stopped running and the page height holds still for ~1 s
  const t = Date.now();
  let last = -1, still = 0;
  await sleep(150);
  while (Date.now() - t < maxMs) {
    const s = await page.evaluate(() => {
      const q = (x) => document.querySelectorAll(x).length;
      const busy = q('[data-testid="stStatusWidget"]') + q('[data-stale="true"]') + q('[data-testid="stSpinner"]') +
        q('[data-testid="stSkeleton"]') + (/Loading your workspace/i.test(document.body.innerText.slice(0, 3000)) ? 1 : 0);
      const m = document.querySelector('[data-testid="stMain"]') || document.body;
      return { busy, h: m.scrollHeight };
    }).catch(() => ({ busy: 1, h: 0 }));
    if (!s.busy && s.h === last) { if (++still >= 4) break; } else still = 0;
    last = s.h;
    await sleep(250);
  }
  return Date.now() - t - 1000;   // minus the quiet second we waited to be sure
}

async function problems(page) {
  return page.evaluate(() => ({
    exc: Array.from(document.querySelectorAll('[data-testid="stException"]')).map((e) => e.innerText.slice(0, 400)),
    errors: Array.from(document.querySelectorAll('[data-testid="stAlertContentError"]')).map((e) => e.innerText.slice(0, 200)),
    pytext: (document.body.innerText.match(/(Traceback|KeyError|TypeError|AttributeError|ValueError|NameError|IndexError)[^\n]{0,160}/) || [""])[0],
    wide: document.documentElement.scrollWidth > window.innerWidth + 2,
  })).catch(() => ({}));
}

async function step(page, name, action) {
  const start = Date.now();
  let err = "";
  try { await action(); } catch (e) { err = String(e).split("\n")[0]; }
  const ms = err ? null : await settled(page);
  const p = await problems(page);
  console.log(JSON.stringify({ name, start: start / 1000, ms, err, ...p }));
  if (err) await page.keyboard.press("Escape").catch(() => {});
}

const nav = (page, label) => async () => {
  if (label === "Follow-ups") return page.locator(".st-key-top_msg button").first().click({ timeout: 10000 });
  const tabLink = page.locator('.st-key-top_nav [role="radiogroup"] label', { hasText: label }).first();
  if (await tabLink.isVisible().catch(() => false)) return tabLink.click({ timeout: 10000 });
  // phones: the pages are in the menu
  await page.locator(".st-key-top_menu button").first().click({ timeout: 8000 });
  await sleep(700);
  await page.locator('[class*="st-key-pop_main"] button, [class*="st-key-pop_more"] button',
                     { hasText: new RegExp("^\\s*" + label + "\\s*$") }).first().click({ timeout: 8000 });
};

const tab = (page, label) => async () => {
  // st.tabs, segmented controls and radio pills all count as tabs here
  const cands = [page.getByRole("tab", { name: label }), page.locator('[data-testid="stMain"] [role="radiogroup"] label', { hasText: label }),
                 page.locator('[data-testid="stMain"] button', { hasText: new RegExp("^\\s*" + label.replace(/[&]/g, "\\$&") + "\\s*$") })];
  for (const c of cands) if (await c.count()) { await c.first().click({ timeout: 6000 }); return; }
  throw new Error("no tab called " + label);
};

const menu = (page, label) => async () => {
  await page.locator(".st-key-top_menu button").first().click({ timeout: 8000 });
  await sleep(600);
  await page.getByRole("button", { name: new RegExp(label + "$") }).first().click({ timeout: 8000 });
};

(async () => {
  const password = PW_FILE && fs.existsSync(PW_FILE) ? fs.readFileSync(PW_FILE, "utf8").trim() : "";
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: WIDTH, height: 900 }, locale: "en-NG" });
  const page = await ctx.newPage();
  await step(page, "landing", async () => {
    await page.goto(SITE, { waitUntil: "domcontentloaded", timeout: 180000 });
    await page.locator('input[aria-label="Email address"]').first().waitFor({ timeout: 180000 });
  });
  if (!password) { console.log(JSON.stringify({ name: "stop", err: "no password file" })); await browser.close(); return; }

  await step(page, "sign-in", async () => {
    await page.locator('input[aria-label="Email address"]').first().fill(EMAIL);
    await page.locator('input[aria-label="Password"]').first().fill(password);
    await page.getByRole("button", { name: "Sign in with email" }).click();
    await page.locator(".st-key-top_nav").first().waitFor({ timeout: 90000 });
  });

  const pages = ["Risk Radar", "Action Centre", "Renewals", "Grow", "Members", "Owner", "Follow-ups",
                 "Archie", "Train", "Check-in", "Dashboard"];
  for (const round of ["first", "again"]) {
    for (const label of pages) await step(page, `${label} (${round})`, nav(page, label));
  }
  for (const label of ["Settings", "Subscription", "Prediction check", "FAQs"]) await step(page, label, menu(page, label));

  // Member profiles: from the Dashboard priorities, the Risk Radar list and the Members directory
  await step(page, "Dashboard (back)", nav(page, "Dashboard"));
  await step(page, "Profile from Dashboard", async () =>
    page.locator('[data-testid="stMain"] button', { hasText: /profile$/i }).first().click({ timeout: 8000 }));
  await step(page, "Risk Radar (back)", nav(page, "Risk Radar"));
  await step(page, "Profile from Risk Radar name", async () =>
    page.locator('[class*="st-key-mrow_prio_"] button, [class*="st-key-mopen_prio"] button').first().click({ timeout: 8000 }));
  await step(page, "Members (back)", nav(page, "Members"));
  await step(page, "Profile from Members name", async () =>
    page.locator('[class*="st-key-mrow_dir_"] button').first().click({ timeout: 8000 }));

  // Tabs inside pages (each is a rerun in some places)
  await step(page, "Grow (tabs)", nav(page, "Grow"));
  for (const t of ["Engagement", "New & leaving", "Growth", "Team & reports", "Renewals & messages"])
    await step(page, `Grow tab ${t}`, tab(page, t));
  await step(page, "Owner (tabs)", nav(page, "Owner"));
  for (const t of ["Member lists", "Team & access", "Trainers", "Monthly report", "Subscription & billing", "Business insights"])
    await step(page, `Owner tab ${t}`, tab(page, t));
  await browser.close();
})();
