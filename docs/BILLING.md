# Free trial and subscriptions

## Pilot mode (switch at the top of Admin → Billing)
- **Charge gyms: off** = pilot mode:
  - every gym uses every feature free;
  - nobody is locked or sees the Upgrade pop-up;
  - no trial or renewal emails are sent.

  The Subscription page tells gyms they're part of the pilot.
- **Charge gyms: on** = normal billing. When you switch it back on, press **Give every gym a fresh 30-day trial from today** so pilot gyms aren't locked straight away. This changes gyms on a trial or whose trial ended, but not paying or free-access gyms.
- Both switches are recorded in the Admin log.

## How it works for gyms
- Every gym gets a **30-day free trial** of every feature from the day it signs up. Gyms that already existed when billing was switched on get 30 days from that day.
- The website shows the trial and your plans in a **Plans and prices** section: one tile per plan with its monthly and yearly price side by side, and a table comparing what each plan includes.
- Nothing about the trial shows inside the app. GymPulse AI emails the owner **7, 3 and 1 days** before the trial ends, and the day after. Paying gyms get emails **3 and 1 days** before their plan ends, and the day after.
- When the 30th day ends there are **no extra days**. An **Upgrade** pop-up lists the plans, and the app shows only the **Subscription** page until they pay. **No data is ever deleted.** Settings and FAQs stay open.
- **Checkout.** On the Subscription page the owner presses **Choose Starter / Growth / Pro** and goes to a checkout page:
  - billing details (business name, full name, phone, email for receipts);
  - billing address (street, city, state);
  - Monthly or Yearly;
  - payment method;
  - acceptance of the terms.

  An order summary shows the plan, when it starts and renews, and the total.
- **With Paystack connected**, the gym picks one of two payment methods:
  - **Bank transfer**: Paystack shows a one-time account number. The gym transfers from any bank app, Paystack confirms in seconds, and the gym comes back to a **Payment successful** page.
  - **Card or USSD**: Paystack's secure page.

  Either way the plan and its features switch on **automatically** the moment the payment is confirmed.
- **Without Paystack**, the only option is a manual bank transfer to your account, with the invoice number as the reference:
  - The gym sees **"Waiting for your transfer"**, never "thank you", and **nothing is switched on**.
  - You get an email.
  - When the money is in your account, confirm it in **Admin → Billing → Bank transfers to confirm**. That switches the plan on and sends the receipt.

  Banks don't tell GymPulse when money arrives, so manual transfers can't be confirmed automatically.
- **Receipts:** every confirmed payment sends a branded receipt email with a PDF (GP-000001, …) from **billing@usegympulseai.com**:
  - to the gym's billing email and the owner's login email;
  - plus a hidden copy to you, at the "Email for payment notices" address in Admin → Billing or `BILLING_COPY_TO`.

  This covers Paystack payments, transfers you confirm, and Admin → Mark as paid. The Subscription page shows **Billing history** with receipt downloads.
- If they pay during the trial, the paid plan starts when the trial ends.
- Needs `sql/phase12_invoices.sql`.
- **Higher plans unlock more.** Pages a gym's plan doesn't include show an "upgrade to unlock" card:
  - **1 · Essentials:** members, check-in, payments and renewals, Risk Radar, follow-ups, renewal reminder emails, monthly report.
  - **2 · + Growth tools:** Action Centre, Grow (campaigns, loyalty, referrals, challenges), "we missed you" and reward emails, Business Insights.
  - **3 · Everything:** Archie, Model insights, priority support and setup help.

## Set up Paystack (one time)
1. Sign up at paystack.com. You can start as an individual or starter business; registering your business name lifts the limits later.
2. Add the bank account you want to be paid into (Settings → Payouts). Paystack pays your money out to it.
3. Copy your **secret key** (Settings → API Keys & Webhooks). Use the `sk_test_...` key first to try it, then the `sk_live_...` key once Paystack activates your account.
4. Add it as **PAYSTACK_SECRET_KEY** in:
   - Render → your service → **Environment**;
   - GitHub → Settings → Secrets and variables → **Actions** (so the daily job catches any payment where the gym closed the page early).
5. Never paste the key in chat or in code.

Admin → Billing → **Online payments (Paystack)** shows whether it's connected, and has a **Check Paystack for missed payments** button.

## How it works for you
- **Plans, prices and how gyms pay:** a table where each row is a plan, cheapest first. It has the plan name, **Features** level (1, 2 or 3), monthly price, yearly price (leave it blank for 2 months free), who it's for, a one-line description, and **Recommended**. The benefits list on each plan is written for you from its Features level. The starting plans are Starter ₦15,000, Growth ₦30,000 and Pro ₦50,000 a month; change them any time. Bank details and a payment link are optional fallbacks for gyms that prefer to transfer.
- **Each gym:**
  - **Mark as paid** for a bank transfer: pick the plan and 1, 3, 6 or 12 months.
  - **Extend trial 14 days**.
  - **Give free access** (for test accounts and friends).
  - **End subscription**.
  Every change goes in the Admin log.
- Paystack payments email you a "New payment" note. A payment that doesn't match the price is not switched on: you get an email to check it.


## Plans by gym size, WhatsApp included

Every recommended plan includes every feature (access 3). Price follows gym size and the WhatsApp messages
included. Pro and up also include priority WhatsApp support and done-for-you setup (the "Priority help" column),
because those cost the founder's time, not software.

Each plan sets **members**, **WhatsApp renewal reminders and replies a month** and **WhatsApp promotional messages a
month** (Admin → Billing → Plans; "Use the recommended plans" loads the starting set below). These show as benefits on
the website, the Subscription page and the comparison table, with "No extra charges". When a gym's allowance is used
up, those messages go by email until next month, so gyms never pay more and the WhatsApp bill stays capped.
Free trials and pilot mode get 300 renewal and 30 promotional WhatsApp messages (`trial_allowance` in the pricing
settings). The Subscription page shows which plan fits the gym's member count. Admin shows a cost check: the WhatsApp
cost if every included message is used, as a share of the price.

| Plan | Members | ₦ / month | WhatsApp renewals | WhatsApp promo | WhatsApp cost if all used |
|---|---|---|---|---|---|
| Starter | 150 | 20,000 | 250 | 0 | ≈ ₦2,600 (13%) |
| Growth | 500 | 45,000 | 700 | 0 | ≈ ₦7,300 (16%) |
| Pro | 1,500 | 100,000 | 2,000 | 150 | ≈ ₦33,000 (33%) |
| Business | 5,000 | 280,000 | 6,500 | 400 | ≈ ₦99,500 (36%) |
| Enterprise | 20,000 | 750,000 | 24,000 | 1,000 | ≈ ₦330,000 (44%) |


## Plan limits (phase 20)

Run `sql/phase20_plan_limits.sql` once.

- **Members (gentle).** When a paying gym has more active members than its plan covers, the owner sees a reminder on
  the Dashboard and Members pages with 30 days to upgrade (the first day over is kept in
  `gym_subscriptions.over_limit_since`). After 30 days, new members can't be added (registration form and import;
  the sign-up link page warns the owner to switch it off). Everything else keeps working and nothing is deleted.
  Upgrading clears it. Trials and pilot mode have no member limit.
- **Archie.** Each plan includes Archie questions a month (Starter 100, Growth 300, Pro 1,000, Business 3,000,
  Enterprise unlimited; trial 100). Counted in `archie_usage` by `gp_archie_bump()`; the Archie page shows the count,
  and when the limit is reached Archie says so politely until the 1st.
- **Help levels.** standard (Starter, Growth) · priority: WhatsApp support and setup done with them (Pro) ·
  dedicated: + account manager, staff training and a monthly review call (Business, Enterprise). Shown in each plan's
  benefits and the comparison table.
- **Admin → Billing → Usage this month**: per gym plan, members against the limit, Archie and WhatsApp used, and who is
  over the limit.
