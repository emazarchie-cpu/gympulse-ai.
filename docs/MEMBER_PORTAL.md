# Member app (member portal)

Each member gets their own page, with no app to download and no password.

- **usegympulseai.com/?member**: the member enters the phone number or email their gym has. GymPulse sends a
  private link by email (and WhatsApp once it's set up). The answer is the same whether or not the contact
  belongs to a member, so nobody can check who is a member.
- **usegympulseai.com/?me=<private link>**: the member's page.

| Tab | What's there |
|---|---|
| Home | Plan, end date and status (Active / Ends in N days / Ended); **Renew** with the gym's Paystack link and bank details (with the member's payment reference); visits this month, weeks in a row, all visits, last visit; check-in QR code; reward points and next reward (when loyalty is on) |
| Classes | Classes in the next 14 days; **Book** / **Cancel**. The gym sees who booked under Check-in → Classes |
| Messages | Messages from the gym (email and WhatsApp) and the member's own; a box to message the gym, which lands in Follow-ups → Inbox labelled "Member app" |
| My details | Phone, email, goal, photo; **Get a new link** (older links stop working) |

Members can add the page to their phone's home screen. The gym's side is **Members → Member app**: the link and QR
code for the front desk, a message for the WhatsApp group, how many members have opened their page, and
**Send link** for one member.

Setup: run `sql/phase18_member_portal.sql` once. For WhatsApp links, submit the `gp_member_portal` template in
Admin → WhatsApp. Pages are read on the server with `SUPABASE_SERVICE_ROLE_KEY` and only ever for the member the
link belongs to.
