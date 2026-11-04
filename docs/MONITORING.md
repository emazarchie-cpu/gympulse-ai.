# Error alerts (Sentry)

When something breaks, Sentry emails you with what went wrong and where, before a gym has to tell you.

## Set up (10 minutes, free plan)
1. Sign up at **sentry.io**, then create a project: platform **Python**, name `gympulse-ai`.
2. Copy the **DSN**. It looks like `https://abc123@o123.ingest.sentry.io/456`.
3. **Render → your web service → Environment:** add `SENTRY_DSN` with that value, then save. The app restarts.
4. **GitHub → Settings → Secrets and variables → Actions:** add `SENTRY_DSN` too, so the monthly reports and the daily automatic messages report their errors.
5. In Sentry → **Alerts**, keep the default "email me on a new issue".

Without `SENTRY_DSN`, nothing is sent and the app works as before.

## What gets reported
- Any page that crashes (the red error box).
- The gym workspace failing to load.
- Monthly reports or automatic emails that fail to send.

## Privacy
No names, emails, phone numbers, page contents or request bodies are sent. Email addresses and phone numbers in error messages are replaced with `[email]` and `[phone]`, and local variables are never included. See `gympulse_monitoring.py`.
