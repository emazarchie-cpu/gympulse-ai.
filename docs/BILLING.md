# Free trial and subscriptions

## How it works for gyms
- Every gym gets a **30-day free trial** from the day it signs up. Gyms that already existed when billing was switched on get 30 days from that day.
- Nothing about the trial shows inside the app. GymPulse AI emails the owner **7, 3 and 1 days** before the trial ends, and the day after.
- When the 30th day ends there are **no extra days**. The next time the owner opens the app, an **Upgrade** pop-up lists your plans and prices. The app then shows only the **Subscription** page until they pay. **No data is ever deleted.** Settings and FAQs stay open.
- The Subscription page shows the plans, how to pay (payment link and/or bank details), and an **I've paid** form (with the plan they chose) that emails you.

## How it works for you (Admin → Billing)
- **Plans, prices and how gyms pay:** a table where each row is a plan: its name (e.g. Starter, Growth, Pro), monthly price, optional yearly price, and who it's for (e.g. "Up to 100 members"). Add, rename or remove rows any time. Also set a payment link (Paystack later), bank details, and your WhatsApp and email. Gyms see changes straight away. No code change is needed.
- **For each gym:**
  - **Mark as paid**: pick the plan and 1, 3, 6 or 12 months. The price fills in from the plan, and you can change it for founding gyms.
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
