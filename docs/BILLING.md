# Free trial and subscriptions

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
