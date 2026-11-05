# Grow: the retention toolkit

The **Grow** page in the top bar has eleven tools. Every number comes from recorded data: members, check-ins, payments and plays.

## One-time setup (GymPulse AI owner)

Run `sql/phase5_growth.sql` in Supabase (SQL Editor → New query → paste → Run). The check at the end should list 9 tables, each with `rls_on = true` and 1 policy. Until it runs, each tool shows "Run sql/phase5_growth.sql…" instead of breaking.

## The tools

| Tool | What it does |
|---|---|
| **Collect renewals** | Lists everyone due in the next 14 days or lapsed in the last 30. Builds a WhatsApp message with the amount, the gym's bank details, a payment reference (e.g. `GP-ADA-1F3C`) and an optional Paystack payment page link. **I've sent it** moves the member to *Waiting for payment*. **Mark as paid** records the payment, extends the membership and credits the play that earned it. A reminder appears after 3 days. |
| **Gym updates** | Tell members when something isn't right: power or generator, air conditioning, water, equipment, opening hours, or anything else. Then tell them again when it's fixed. GymPulse writes a calm note you can edit, and emails it with your logo to members who came in the last 30 days (or everyone with a running membership). It also gives you one copy for your WhatsApp Status or members' group, so nobody gets flooded with messages. Updates from the last 60 days are listed. |
| **Happiness** | Answers to the one-tap happiness check: share of happy members, unhappy members to reach out to (with their comment, a WhatsApp button and their profile), all comments, and the trend over time. Needs `sql/phase11_happiness.sql`. |
| **Celebrate** | Member of the month (most days trained, then the biggest jump) with a ready WhatsApp Status post and a message asking the member first. Also lists milestones reached in the last 30 days. |
| **New members** | Six steps over the first 90 days: welcome, third-visit check-in, meet a trainer (day 14), 30-day progress check, 60-day goal review and a 90-day celebration. Members with no visit in their first week get a red alert and a rescue message. Members with fewer than 4 visits in their first month are marked *quiet start*. Each new member also has a target, for staff only: **5 visits in the first 30 days** and **20 in the first 60 days** (members who hit these usually stay). The page shows who has hit it, who is on track, and a *Falling behind* list for the team. Steps a member has already passed are skipped. |
| **Class invites** | Members who trained 3+ times in the last 60 days but haven't been checked in to a class in 120 days. Members who only use the equipment cancel more often. Each gets a friendly invitation that names the next classes (Email or WhatsApp). Needs classes on the Check-in page. |
| **Freeze** | Pauses a membership for up to 3 months (travel, December, Ramadan, exams, injury). The member is hidden from risk lists while frozen, and their end date moves forward by the freeze length. Freezes start and end on their own dates, and members get a welcome-back message in the week they return. Includes a "freeze instead of cancel" script. |
| **Why they left** | Sends lapsed members a one-question WhatsApp survey with 8 numbered reasons. If they reply with a number through the WhatsApp inbox, the reason is filled in for you. Shows the share of each reason, with advice for the top one. |
| **Progress** | Log weight, waist, body fat or a personal best in seconds. A shout-out is drafted only when the numbers show real progress in the direction of the member's goal: at least 2kg, or a better personal best. |
| **Referrals** | Bring-a-friend from invite → visited → joined → reward given, with the reward the gym sets (default "1 free week"). Flags when a friend's phone number matches a new member. Includes a top-referrers board. |
| **Challenges** | Visits challenges with a target and a reward. Every real check-in counts, one per day, so the leaderboard updates by itself. Share it to the members' WhatsApp group in one tap. |
| **Corporate** | Company plans with seats, a monthly fee and an HR contact. Link staff to the company and see the team's attendance over the last 30 days. Download a PDF report for HR or send a summary on WhatsApp. |
| **Team** | A leaderboard of who worked which plays, members kept, save rate, and money kept. Money only counts renewal payments credited to that person's plays. |
| **Season planner** | The Nigerian year: New Year rush, Valentine's, Ramadan and Eid (estimated dates), Easter, rainy season, summer travel, back to routine, pre-December and Detty December. Each has what to do and a ready message, and is flagged 14 days ahead. Also shows the gym's own monthly visits. |
| **Monthly report** | View only: last month or this month so far, with the **retention rate** (members kept out of those whose membership was running at the start of the month, against the ~97% a month industry average), members kept, money kept, collected, new members, visits, top staff member and top exit reason, plus a PDF download. Gyms don't send it themselves. GymPulse AI emails it to every gym owner on the 1st of each month (see `docs/ADMIN.md`). In the first week of each month it also appears on the Dashboard. |

## Email first, WhatsApp for what's urgent

- Every message has **Send email** as the main button. The email goes out as a letter with the gym's logo, brand colour, footer and chosen background (White or Black, set in Settings → Email & branding). Emoji are left out of emails.
- **WhatsApp** is the second button. Renewal requests, payment reminders and first-week rescues are marked *important*, with a suggestion to also send them on WhatsApp so the member sees them the same day.
- Emailing a renewal request moves the member to *Waiting for payment* automatically.
- **Bank details are off by default in emails.** A gym can switch on a single calm P.S. under the sign-off (Collect renewals → Your payment details → "Add my bank details to renewal emails"). The email still leads with the invitation, so it never reads like chasing money. The email opens with the member's real progress (visits since joining and in the last 30 days, and their goal), says their spot is still there, invites them to renew at the front desk ("it takes two minutes"), and asks them to reply with the day they're coming. Two buttons: *Tell us when you're coming* (opens the gym's WhatsApp or email) and *Pay securely with Paystack*, which appears only if the gym added a Paystack link.
- An optional **perk for renewing in person**, set by the gym in Collect renewals → Your payment details, is added to both versions. GymPulse never invents offers.
- The WhatsApp version sends the same invitation and puts the payment options (Paystack link, then bank transfer with a reference) at the end, as an option.
- Members who unsubscribed, or who have no email address, can only be reached on WhatsApp.
- HR reports and the weekly report are emailed with their PDF attached. The monthly report comes from GymPulse AI itself.

## PDFs

Every PDF has the gym's logo and brand colour in the header and a small GymPulse AI mark in the footer. If the logo is dark, the header switches to white so the logo stays visible. Amounts are written as NGN, there are no emoji, and file names use only letters, numbers and dashes, so they download on every phone.

## Notes

- Members pay the gym directly. GymPulse never handles the money, and payments are marked as paid by the gym.
- WhatsApp buttons open the chat with the message ready to send (`wa.me` links). They work without the WhatsApp Business API.
- Ramadan and Eid dates are estimates, because they depend on the moon sighting.

## Loyalty points and automatic messages

Run `sql/phase9_loyalty.sql` once in Supabase.

**Loyalty (Grow → Loyalty)**
- Members earn points only from recorded activity: **points per visit** (one per day), a **strong-week bonus** for training N times in a week, and an **on-time renewal bonus** for a renewal paid before the plan ended. Points count from the date you choose.
- You set the rewards (for example 200 = free smoothie, 500 = free PT session, 1,000 = one week free).
- **Ready for a reward** lists members with enough points. Email or WhatsApp them, then tap **Mark reward as claimed** to take the points off.
- A leaderboard shows each member's points and how far they are from their next reward.

**Automatic messages (Grow → Automatic messages)**
- **Renewal reminder**, N days before a plan ends (default 3).
- **We missed you**, after N days without a check-in (default 10, active members only). It can offer a pause ("if now isn't a good time... we can pause your membership"); this is on by default.
- **New member check-in**, about two weeks after joining. It's warmer and more practical if they've barely come in.
- **How was your first week?**, 7 days after joining.
- **Milestones**: 25, 50, 100, 150, 200, 300 and 500 visits; 12 weeks in a row with 3+ visits; joining anniversaries. Only celebrated within 2 weeks of happening.
- **Loyalty level up**, when levels are on (Grow → Loyalty → Levels: e.g. Bronze 0, Silver 1,000, Gold 3,000 points, each with an optional perk). Claiming gifts never lowers a level.
- **Happiness check**, every 3 months (or monthly): "How happy are you with the gym?" with four one-tap buttons. The answer is saved on a small page with no sign-in, where the member can add a comment. "Not happy" and "It's okay" answers are emailed to the owner straight away. Only members who joined 30+ days ago and haven't unsubscribed get it. Needs `sql/phase11_happiness.sql`.
- **Monthly progress note**, in the first week of the month, only to members who trained 4+ times last month ("you trained 11 times in October, up from 8").
- **Reward ready**, when a member has enough points (needs loyalty on).
- All of them start switched off. They go out every morning at 08:30 Lagos time from `.github/workflows/auto-messages.yml`, which uses the same repository secrets as Monthly reports. You can also tap **Send today's … now**.
- Each member gets each message at most once per occasion, and at most one automatic email a day (renewal, we missed you, first week, new member check-in, milestone, level up, reward, progress, then happiness check). Unsubscribed members are skipped. Members with no email are listed with a WhatsApp button. There's a daily cap (default 80), because Resend's free plan allows 100 emails a day.
- Renewal emails use the same invitation as Collect renewals: a Paystack button if you've added a link, and your bank details as a P.S. only if you switched that on.
