# Free trial and subscriptions

## How it works for gyms
- Every gym gets a **30-day free trial** from the day it signs up. Gyms that already existed when billing was switched on get 30 days from that day.
- A line at the top of every page shows the days left. It turns into a warning in the last 7 days.
- GymPulse AI emails the owner **7, 3 and 1 days** before the trial ends, and the day after. This is part of the daily 8:30 run.
- When the trial ends there are **3 days of grace** with a warning. After that the app shows the **Subscription** page until the gym pays. **No data is ever deleted.** Settings and FAQs stay open.
- The Subscription page (☰ → Subscription) shows the price, the payment link and/or bank details, and an **I've paid** form that emails you.

## How it works for you (Admin → Billing)
- **Prices and how gyms pay:** set the monthly price (and optionally a yearly one), a payment link (Paystack later), bank details, and your WhatsApp and email. Gyms see these straight away. No code change is needed.
- **For each gym:**
  - **Mark as paid** for 1, 3, 6 or 12 months, at that gym's price. Founding gyms can keep a special price.
  - **Extend trial 14 days.**
  - **Give free access**, for test accounts, friends or partners. They're never asked to pay.
  - **End subscription.**
- Totals show gyms on trial, paying, ended-not-paid, and monthly income.
- Every action is recorded in the Admin log. Admin accounts are never locked.

## Set up
1. Run `sql/phase10_billing.sql` in Supabase. It gives every existing gym a 30-day trial starting today, and new gyms get one automatically.
2. Admin → Billing → **Give free access** to your test gyms.
3. Admin → Billing → **Prices and how gyms pay:** enter the price when you've decided.

If the SQL hasn't been run, nothing is locked.
