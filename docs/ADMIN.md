# Founder admin and automatic monthly reports

Gym owners don't send their own monthly report. GymPulse AI sends it:
- **automatically on the 1st of every month**, by email with the PDF attached, and
- **by hand from the Admin page**, by email or WhatsApp, for any gym and month.

## One-time setup

1. **Supabase:** run `sql/phase6_admin.sql`. It creates a private log of sent reports, so no gym gets the same month twice.
2. **Render → your web service → Environment**, add:
   - `GYMPULSE_ADMINS`: the emails that can open the Admin page, comma-separated (for example your founder login).
   - `SUPABASE_SERVICE_ROLE_KEY`: from Supabase → Project Settings → API → `service_role`. It can read every gym, so keep it on Render only. Never put it in the app's code or share it.
   - `SUPABASE_URL`: the same URL the app already uses.
   - Optional: `REPORTS_FROM` (default `GymPulse AI <reports@usegympulseai.com>`) and `REPORTS_REPLY_TO` (default `emmanuel@usegympulseai.com`).
3. **Automatic sending, free, on GitHub Actions** (`.github/workflows/monthly-reports.yml`):
   - GitHub → the repository → **Settings → Secrets and variables → Actions → New repository secret**. Add `SUPABASE_URL`, `SUPABASE_SERVICE_ROLE_KEY` and `RESEND_API_KEY`, with the same values as on Render.
   - Test it: go to **Actions → Monthly reports → Run workflow**, leave *Dry run* ticked, and run it. The log lists each gym as "would send" or "already sent", and nothing is sent.
   - From then on it runs at 08:00 Lagos time on the 1st of every month. Gyms already emailed from the Admin page are skipped.
   - Prefer Render? A Render Cron Job (`0 7 1 * *`, `python scripts/send_monthly_reports.py`) does the same thing, but it's paid.

## The Admin page

Sign in with an email listed in `GYMPULSE_ADMINS` and open **☰ → Admin**. Pick a month to see every gym's numbers. For each gym you can:
- **Download PDF**
- **Email report**: sends the report from GymPulse AI to the gym owner, with the PDF attached
- **WhatsApp the owner**: opens WhatsApp with the report message ready, written as from Emmanuel at GymPulse AI. Tap **I sent it on WhatsApp** afterwards to log it.

**Email all unsent reports** sends to every gym that hasn't had that month's email yet.
