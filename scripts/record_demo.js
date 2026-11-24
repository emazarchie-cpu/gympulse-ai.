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

// Parts of the take to keep, in seconds from the start of the video. Waiting for a
// page to load is cut out, so the finished video goes straight from page to page.
let T0 = 0;
const keep = [];
const now = () => (Date.now() - T0) / 1000;
function pause() { const k = keep[keep.length - 1]; if (k && k[1] === null) k[1] = now(); }
function resume() { pause(); keep.push([now() + 0.15, null]); }

// While a page loads, a small magenta square sits in the bottom-right corner.
// cut_demo.py drops every frame that shows it, so the video never shows loading.
let marking = false;
async function mark(page, on) {
  marking = on;
  await page.evaluate((on) => {
    let el = document.getElementById("gp-cut");
    if (on && !el) {
      el = document.createElement("div");
      el.id = "gp-cut";
      el.style.cssText = "position:fixed;right:0;bottom:0;width:32px;height:32px;background:#FF00FF;z-index:2147483647;pointer-events:none";
      document.body.appendChild(el);
    }
    if (!on && el) el.remove();
  }, on).catch(() => {});
  if (!on) await sleep(250);
}

async function loaded(page, maxMs = 45000) {
  // Done when Streamlit has stopped running, nothing is loading or stale, the page
  // has real content, and its height has held still for about two seconds.
  const t = Date.now();
  let last = -1, still = 0;
  while (Date.now() - t < maxMs) {
    if (marking) await mark(page, true);
    const st = await page.evaluate(() => {
      const q = (s) => document.querySelectorAll(s).length;
      const busy = q('[data-testid="stSkeleton"], [data-testid="stSpinner"], .stSpinner') +
        q('[data-testid="stStatusWidget"]') + q('[data-stale="true"]') +
        (q('.gp-hold') && !q('.gp-done') ? 1 : 0);
      const text = document.body.innerText.slice(0, 6000);
      const loading = /Loading your workspace|Loading\.\.\.|Please wait/i.test(text);
      const m = document.querySelector('[data-testid="stMain"]') || document.body;
      const blocks = q('[data-testid="stMain"] [data-testid="stElementContainer"]');
      return { busy: busy + (loading ? 1 : 0), h: m.scrollHeight, blocks };
    }).catch(() => ({ busy: 1, h: 0, blocks: 0 }));
    if (!st.busy && st.blocks >= 6 && st.h === last) { if (++still >= 5) break; } else still = 0;
    last = st.h;
    await sleep(400);
  }
  await sleep(900);
}

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
  await hideCaption(page);
  await sleep(300);
  pause();                                   // the click and the loading are cut out
  await mark(page, true);
  if (label === "Follow-ups") {              // the speech-bubble button at the top right
    await page.locator('.st-key-top_msg button').first().click();
  } else {
    await page.locator('.st-key-top_nav [role="radiogroup"] label', { hasText: label }).first().click({ timeout: 8000 });
  }
  await sleep(800);
  await loaded(page);
  await toTop(page);
  await sleep(300);
  await mark(page, false);
  resume();
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
    await page.keyboard.press("Escape").catch(() => {});
    await mark(page, false);
    resume();
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
  T0 = Date.now();                           // the video starts with the page

  // Wake the server first (a sleeping server can take a while), then start the take
  await page.goto(SITE, { waitUntil: "domcontentloaded", timeout: 180000 });
  await page.locator('input[aria-label="Email address"]').first().waitFor({ timeout: 180000 });
  await settle(page, 2500);

  // Where the finished video should start (skips the blank loading frames)
  keep.push([Math.max(0, now() - 0.2), null]);
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
    pause();
    await mark(page, true);
    await sleep(1200);
    await page.locator(".st-key-top_nav").first().waitFor({ timeout: 90000 });
    await loaded(page, 45000);
    await hideCaption(page);
    await sleep(400);
    await mark(page, false);
    resume();

    await scene(page, null, "Dashboard", "Today's priorities: who to call, renewals due and members drifting away.",
                [[0, 0, 2800], [700, 3000, 1200], [700, 3000, 1500]]);
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
    await scene(page, "Follow-ups", "Follow-ups", "Message members by WhatsApp or email in your gym's name, and see their replies in one place.",
                [[0, 0, 2500], [600, 3000, 2000]]);
    await hideCaption(page);
  }
  await card(page, "Start your 30-day free trial", "usegympulseai.com", 5000);
  pause();
  fs.writeFileSync(path.join(OUT, "keep.json"), JSON.stringify(keep.filter((k) => k[1] !== null && k[1] - k[0] > 0.3)));
  await page.close();
  await ctx.close();
  await browser.close();
  console.log("Recorded.");
})();
