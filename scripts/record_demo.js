// Records a walkthrough video of the live app, signed in as the demo gym.
// Runs from .github/workflows/demo-video.yml after the demo gym is reset.
//
//   DEMO_EMAIL=... DEMO_PASSWORD_FILE=/tmp/pw node scripts/record_demo.js out_dir
//
// The password is read from a file and never printed. Each scene gets a caption
// card at the bottom of the screen; the result is a .webm in out_dir.
const { chromium } = require("playwright");
const fs = require("fs");
const path = require("path");

const SITE = process.env.DEMO_SITE || "https://usegympulseai.com";
const EMAIL = process.env.DEMO_EMAIL || "demo@usegympulseai.com";
const PW_FILE = process.env.DEMO_PASSWORD_FILE || "";
const OUT = process.argv[2] || "demo_out";
const W = 1920, H = 1080;

const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

async function settle(page, extra = 1500) {
  // Streamlit shows a running indicator while a page builds
  for (let i = 0; i < 60; i++) {
    const busy = await page.locator('[data-testid="stStatusWidget"]').count().catch(() => 0);
    if (!busy) break;
    await sleep(500);
  }
  await sleep(extra);
}

async function caption(page, title, sub) {
  await page.evaluate(([t, s]) => {
    let el = document.getElementById("gp-cap");
    if (!el) {
      el = document.createElement("div");
      el.id = "gp-cap";
      el.style.cssText = "position:fixed;left:48px;bottom:44px;z-index:2147483647;max-width:880px;" +
        "padding:22px 28px 22px 26px;border-radius:20px;background:rgba(10,15,30,0.92);" +
        "border:1px solid rgba(255,255,255,0.12);border-left:6px solid #B7F34A;" +
        "box-shadow:0 18px 50px rgba(0,0,0,0.45);font-family:Inter,Arial,sans-serif;" +
        "transition:opacity .35s ease, transform .35s ease;pointer-events:none";
      document.body.appendChild(el);
    }
    el.style.opacity = "0"; el.style.transform = "translateY(10px)";
    setTimeout(() => {
      el.innerHTML = `<div style="font-size:34px;font-weight:800;color:#F4F7FB;line-height:1.2">${t}</div>` +
        (s ? `<div style="margin-top:8px;font-size:22px;color:#B9C4D6;line-height:1.45">${s}</div>` : "");
      el.style.opacity = "1"; el.style.transform = "none";
    }, 200);
  }, [title, sub || ""]);
  await sleep(500);
}

async function hideCaption(page) {
  await page.evaluate(() => { const el = document.getElementById("gp-cap"); if (el) el.style.opacity = "0"; });
}

async function card(page, title, sub, ms) {
  // A full-screen title card over the page
  await page.evaluate(([t, s]) => {
    const el = document.createElement("div");
    el.id = "gp-card";
    el.style.cssText = "position:fixed;inset:0;z-index:2147483647;display:flex;flex-direction:column;" +
      "align-items:center;justify-content:center;text-align:center;background:radial-gradient(circle at 50% 40%," +
      "#16223D,#0A0F1E 70%);font-family:Inter,Arial,sans-serif;opacity:0;transition:opacity .5s ease";
    el.innerHTML = `<div style="font-size:30px;letter-spacing:4px;font-weight:800;color:#B7F34A">GYMPULSE AI</div>` +
      `<div style="margin-top:22px;font-size:66px;font-weight:800;color:#F4F7FB;max-width:1400px;line-height:1.15">${t}</div>` +
      (s ? `<div style="margin-top:22px;font-size:30px;color:#B9C4D6;max-width:1200px;line-height:1.4">${s}</div>` : "") +
      `<div style="margin-top:40px;width:220px;height:6px;border-radius:6px;background:linear-gradient(90deg,#B7F34A,#35D6ED)"></div>`;
    document.body.appendChild(el);
    requestAnimationFrame(() => (el.style.opacity = "1"));
  }, [title, sub || ""]);
  await sleep(ms);
  await page.evaluate(() => { const el = document.getElementById("gp-card"); if (el) { el.style.opacity = "0"; setTimeout(() => el.remove(), 500); } });
  await sleep(600);
}

async function scroll(page, px, ms) {
  // Smooth scroll of the Streamlit main area (and the window, whichever scrolls)
  await page.evaluate(async ([px, ms]) => {
    const els = [document.querySelector('[data-testid="stMain"]'), document.querySelector('[data-testid="stAppViewContainer"]'),
                 document.scrollingElement].filter(Boolean);
    const target = els.find((e) => e.scrollHeight > e.clientHeight + 10) || document.scrollingElement;
    const start = target.scrollTop, steps = Math.max(1, Math.round(ms / 16));
    for (let i = 1; i <= steps; i++) {
      const k = i / steps, ease = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      target.scrollTop = start + px * ease;
      await new Promise((r) => setTimeout(r, 16));
    }
  }, [px, ms]);
}

async function toTop(page) {
  await page.evaluate(() => {
    for (const e of [document.querySelector('[data-testid="stMain"]'), document.querySelector('[data-testid="stAppViewContainer"]'),
                     document.scrollingElement]) if (e) e.scrollTop = 0;
  });
}

async function nav(page, label) {
  const link = page.locator('.st-key-top_nav [role="radiogroup"] label', { hasText: label }).first();
  if (await link.count()) {
    await link.click();
  } else {                                   // not in the top bar: open the ☰ menu
    await page.locator('.st-key-top_menu [data-testid="stPopoverButton"]').first().click();
    await sleep(700);
    await page.locator('[data-testid="stPopoverBody"] button', { hasText: label }).first().click();
  }
  await settle(page, 1800);
  await toTop(page);
}

async function scene(page, label, title, sub, plan) {
  try {
    if (label) await nav(page, label);
    await caption(page, title, sub);
    for (const [px, ms, hold] of plan) {
      await sleep(hold);
      if (px) await scroll(page, px, ms);
    }
  } catch (e) {
    console.log(`Scene "${title}" skipped: ${String(e).split("\n")[0]}`);
    try { await page.screenshot({ path: path.join(OUT, `skip-${label || "start"}.png`) }); } catch (_) {}
  }
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const password = PW_FILE && fs.existsSync(PW_FILE) ? fs.readFileSync(PW_FILE, "utf8").trim() : "";
  const browser = await chromium.launch();
  const ctx = await browser.newContext({ viewport: { width: W, height: H }, deviceScaleFactor: 1,
                                         recordVideo: { dir: OUT, size: { width: W, height: H } } });
  const page = await ctx.newPage();
  const t0 = Date.now();                     // the video starts with the page

  // Wake the server first (a sleeping server can take a while), then start the take
  await page.goto(SITE, { waitUntil: "domcontentloaded", timeout: 180000 });
  await page.locator('input[aria-label="Email address"]').first().waitFor({ timeout: 180000 });
  await settle(page, 2500);

  // Where the finished video should start (skips the blank loading frames)
  fs.writeFileSync(path.join(OUT, "start.txt"), String(Math.max(0, (Date.now() - t0) / 1000 - 0.2)));
  await card(page, "Keep more of your gym members", "See who's about to leave, and act before they do.", 4200);
  await caption(page, "usegympulseai.com", "Works alongside GymMaster or any gym software.");
  await scroll(page, 900, 3500);
  await sleep(1200);
  await hideCaption(page);

  // Sign in to the demo gym
  const email = page.locator('input[aria-label="Email address"]').first();
  await email.scrollIntoViewIfNeeded();
  await caption(page, "Sign in", "This is the demo gym, Demo Fitness Lagos, with sample members.");
  await email.click();
  await email.pressSequentially(EMAIL, { delay: 35 });
  if (!password) { console.log("No demo password file: stopping after the landing page."); }
  else {
    const pw = page.locator('input[aria-label="Password"]').first();
    await pw.click();
    await pw.fill(password);
    await sleep(500);
    await page.getByRole("button", { name: "Sign in with email" }).click();
    await page.locator(".st-key-top_nav").first().waitFor({ timeout: 90000 });
    await settle(page, 2500);
    await hideCaption(page);

    await scene(page, null, "Dashboard", "Today's priorities: who to call, renewals due and members drifting away.",
                [[0, 0, 2500], [700, 3000, 1500], [700, 3000, 2000]]);
    await scene(page, "Risk Radar", "Risk Radar", "Every member gets a High, Medium or Low risk of leaving, with the reasons why.",
                [[0, 0, 2500], [800, 3500, 1500], [700, 3000, 2000]]);
    await scene(page, "Action Centre", "Action Centre", "Turn risk into action: assign a play to your team and track it to done.",
                [[0, 0, 2500], [900, 3500, 1500], [800, 3500, 2500]]);
    await scene(page, "Renewals", "Payments & Renewals", "Who's due, who paid, and who's lapsing, in one place.",
                [[0, 0, 2500], [800, 3500, 2000]]);
    await scene(page, "Grow", "Grow", "Renewal reminders, automatic messages, loyalty rewards and referrals.",
                [[0, 0, 2500], [800, 3500, 2000]]);
    await scene(page, "Members", "Members", "Import from GymMaster or Excel, digital waivers, sign-up QR code and a member app.",
                [[0, 0, 3000], [700, 3000, 2000]]);
    await scene(page, "Owner", "Owner", "Your business at a glance: retention, revenue, team access and monthly reports.",
                [[0, 0, 2500], [800, 3500, 2000]]);
    await scene(page, "Follow-ups", "Follow-ups", "Message members by email in your gym's name and logo, and see their replies.",
                [[0, 0, 2500], [600, 3000, 2000]]);
    await hideCaption(page);
  }
  await card(page, "Start your 30-day free trial", "usegympulseai.com", 5000);
  await page.close();
  await ctx.close();
  await browser.close();
  console.log("Recorded.");
})();
