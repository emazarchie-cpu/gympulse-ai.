# Book a demo

**How it works:**
- "Book a 15-minute demo" on the landing page opens `usegympulseai.com/?demo=book`.
- The visitor enters their name, email, WhatsApp number, gym name and member count, then picks a date and a free time slot (Lagos time).
- Confirming the booking does three things:
  - saves it in Supabase (`demo_bookings`); a time can't be booked twice;
  - shows a confirmation page with a Google Meet button, an Add to Google Calendar button and a calendar invite file;
  - emails the client a branded confirmation (Meet link, calendar invite, cancel link) and emails you the booking details with the same invite, so it goes straight into your Google Calendar.
- The cancel link frees the time again and emails you.

## Set-up (one time)

1. **Supabase:** run `sql/demo_bookings.sql` in the SQL Editor.
2. **Your Google Meet link:** open Google Calendar, create an event called "GymPulse AI demos" with Google Meet, and copy its Meet link. That link stays the same, so every demo uses it.
3. **Render:** go to your service → Environment and add:

| Name | Value |
|---|---|
| `DEMO_MEET_LINK` | your Meet link, for example `https://meet.google.com/abc-defg-hij` |
| `DEMO_OWNER_EMAIL` | where bookings are sent (default `emmanuel@usegympulseai.com`) |
| `DEMO_EMAIL_FROM` | optional, default `Emmanuel from GymPulse AI <emmanuel@usegympulseai.com>` |
| `DEMO_DAYS` | optional, default `Mon,Tue,Wed,Thu,Fri` |
| `DEMO_HOURS` | optional, first and last start time, default `10:00-16:30` |
| `RESEND_API_KEY`, `EMAIL_FROM` | email sending, from resend.com (also used by Follow-ups) |

Without the email settings, bookings are still saved and the confirmation page still gives the client the Meet link and calendar invite, but no emails are sent.

You can see every booking in Supabase → Table Editor → `demo_bookings`.
