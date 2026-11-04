# Grow: the retention toolkit

The **Grow** page in the top bar has eleven tools. Every number comes from recorded data: members, check-ins, payments and plays.

## One-time setup (GymPulse AI owner)

Run `sql/phase5_growth.sql` in Supabase (SQL Editor → New query → paste → Run). The check at the end should list 9 tables, each with `rls_on = true` and 1 policy. Until it runs, each tool shows "Run sql/phase5_growth.sql…" instead of breaking.

## The tools

| Tool | What it does |
|---|---|
| **Collect renewals** | Lists everyone due in the next 14 days or lapsed in the last 30. Builds a WhatsApp message with the amount, the gym's bank details, a payment reference (e.g. `GP-ADA-1F3C`) and an optional Paystack payment page link. **I've sent it** moves the member to *Waiting for payment*. **Mark as paid** records the payment, extends the membership and credits the play that earned it. A reminder appears after 3 days. |
| **New members** | Six steps over the first 90 days: welcome, third-visit check-in, meet a trainer (day 14), 30-day progress check, 60-day goal review and a 90-day celebration. Members with no visit in their first week get a red alert and a rescue message. Steps a member has already passed are skipped. |
| **Freeze** | Pauses a membership for up to 3 months (travel, December, Ramadan, exams, injury). The member is hidden from risk lists while frozen, and their end date moves forward by the freeze length. Freezes start and end on their own dates, and members get a welcome-back message in the week they return. Includes a "freeze instead of cancel" script. |
| **Why they left** | Sends lapsed members a one-question WhatsApp survey with 8 numbered reasons. If they reply with a number through the WhatsApp inbox, the reason is filled in for you. Shows the share of each reason, with advice for the top one. |
| **Progress** | Log weight, waist, body fat or a personal best in seconds. A shout-out is drafted only when the numbers show real progress in the direction of the member's goal: at least 2kg, or a better personal best. |
| **Referrals** | Bring-a-friend from invite → visited → joined → reward given, with the reward the gym sets (default "1 free week"). Flags when a friend's phone number matches a new member. Includes a top-referrers board. |
| **Challenges** | Visits challenges with a target and a reward. Every real check-in counts, one per day, so the leaderboard updates by itself. Share it to the members' WhatsApp group in one tap. |
| **Corporate** | Company plans with seats, a monthly fee and an HR contact. Link staff to the company and see the team's attendance over the last 30 days. Download a PDF report for HR or send a summary on WhatsApp. |
| **Team** | A leaderboard of who worked which plays, members kept, save rate, and money kept. Money only counts renewal payments credited to that person's plays. |
| **Season planner** | The Nigerian year: New Year rush, Valentine's, Ramadan and Eid (estimated dates), Easter, rainy season, summer travel, back to routine, pre-December and Detty December. Each has what to do and a ready message, and is flagged 14 days ahead. Also shows the gym's own monthly visits. |
| **Monthly report** | Last month (or this month so far) in one WhatsApp-ready message and a PDF: members kept, money kept, collected, new members, visits, top staff member and top exit reason. In the first week of each month it appears on the Dashboard, and if email sending is set up it's emailed to the owner once. |

## Email first, WhatsApp for what's urgent

- Every message has **Send email** as the main button. The email goes out as a letter with the gym's logo, brand colour, footer and chosen background (White or Black, set in Settings → Email & branding). Emoji are left out of emails.
- **WhatsApp** is the second button. Renewal requests, payment reminders and first-week rescues are marked *important*, with a suggestion to also send them on WhatsApp so the member sees them the same day.
- Emailing a renewal request moves the member to *Waiting for payment* automatically.
- **Payment emails never contain bank details.** In an inbox they look like scams. Instead, the email opens with the member's real progress (visits since joining and in the last 30 days, and their goal), says their spot is still there, invites them to renew at the front desk ("it takes two minutes"), and asks them to reply with the day they're coming. Two buttons: *Tell us when you're coming* (opens the gym's WhatsApp or email) and *Pay securely with Paystack*, which appears only if the gym added a Paystack link.
- An optional **perk for renewing in person**, set by the gym in Collect renewals → Your payment details, is added to both versions. GymPulse never invents offers.
- The WhatsApp version sends the same invitation and puts the payment options (Paystack link, then bank transfer with a reference) at the end, as an option.
- Members who unsubscribed, or who have no email address, can only be reached on WhatsApp.
- HR reports, the monthly report and the weekly report are emailed with their PDF attached.

## PDFs

Every PDF has the gym's logo and brand colour in the header and a small GymPulse AI mark in the footer. If the logo is dark, the header switches to white so the logo stays visible. Amounts are written as NGN, there are no emoji, and file names use only letters, numbers and dashes, so they download on every phone.

## Notes

- Members pay the gym directly. GymPulse never handles the money, and payments are marked as paid by the gym.
- WhatsApp buttons open the chat with the message ready to send (`wa.me` links). They work without the WhatsApp Business API.
- Ramadan and Eid dates are estimates, because they depend on the moon sighting.
