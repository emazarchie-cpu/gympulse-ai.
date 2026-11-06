# Member app (member portal)

Each member gets their own page, with no app to download and no password.

- **usegympulseai.com → Member** (the switch above the sign-in box), or **usegympulseai.com/?member**: the member
  types the email their gym has, gets a 6-digit code by email (valid 10 minutes, 5 wrong tries), types it, and is
  in. No sign-up, no password: the gym, an import or the sign-up link already added them. The answer is the same
  whether or not the email belongs to a member, so nobody can check who is a member. A member of several gyms
  picks which one to open. (`sql/phase19_member_code_login.sql`)
- Private links by email or WhatsApp still work (Members → Member app → Send link).
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


## Community (phase 21)

A **Community** tab in the member app: a private feed for each gym. Run `sql/phase21_community.sql` once (tables,
row-level security and the `community` photo bucket).

- **Members:** accept five short community rules once, then post text and a photo (resized to 1080 px), like ❤️,
  comment, delete their own posts and comments, and report others. Up to 10 posts a day. Members the gym has
  stopped can still read.
- **Gym (Members → Member community):**
  - switch the community on or off;
  - post as the gym and pin a post to the top;
  - see reported posts first;
  - hide or show posts and comments, or mark a report "Looks fine";
  - stop or allow a member posting (owner only).
- Only members of the same gym see the feed. Everything is read on the server, scoped to the member's gym.
- Photos go to Supabase Storage under random file names (public bucket); if storage isn't set up they're stored
  small inside the post.
- Later: one shared community across a brand's branches, and notifications for new comments.
