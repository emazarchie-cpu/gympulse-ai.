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


## Community: stories, profiles, follows and messages (phase 22)

Run `sql/phase22_community_social.sql` once. The Community tab gets a menu: **Feed · Search · Inbox · Me**, and the
member app now stays on the tab you're using.

- **Stories:** a row of rings at the top of the feed (gym first, unseen first, then people you follow). Add a photo
  or text story; it shows for 24 hours, then moves to the member's private **Story archive**. Tap a ring to view,
  with Next / Previous; seen stories get a grey ring. Gyms can post stories and remove any story.
- **Profiles:** photo, name, bio, and counts for posts, followers and following (tap the counts to see the people),
  plus a grid of their posts. Tap any name in the feed, search, followers lists or messages to open a profile, then
  Follow / Unfollow, Message or Block. On your own profile: Edit profile (bio, who can message you) and Story
  archive.
- **Feed:** Everyone / Following filter.
- **Search:** find members by name; with no search, it suggests members to follow.
- **Messages:** an Inbox with unread counts (also shown on the menu) and chat bubbles. Members choose who can message
  them (everyone, people they follow, nobody). Blocking stops messages and hides profiles both ways. Members the
  gym has paused can't message. Limit: 60 messages an hour. The gym does not read members' messages.
- Everything stays within one gym; all reads are on the server, scoped to the signed-in member's gym.


## Community notifications (phase 23)

Run `sql/phase23_community_notifications.sql` once.

- **In the app:** a 🔔 button at the top of the Feed shows "N new notifications". The list shows who followed you
  or messaged you. Tap one to open the chat or their profile; it's marked read. "Mark all as read" clears the list.
  Opening a chat also clears that person's message notification. Several messages from the same person count as
  one notification. Follow / unfollow / follow again notifies at most once a day.
- **By email** (free, through Resend): "Tunde sent you a message" / "Tunde started following you", with a button
  to the member sign-in. At most one email per kind every 30 minutes, and only to members with an email address.
  Members switch it off in Community → Me → Edit profile.
- No WhatsApp, because WhatsApp notifications would cost per message.


## Active members only

By default only members whose plan runs today or later (not suspended or archived) can open the Community tab.
Others see "The community is for active members", with the date their plan ended and a "Renew with Paystack"
button when the gym has a Paystack link. As soon as their end date moves forward (renewal recorded, or a Paystack
payment confirmed), they're back in, with their posts, followers and messages as they left them. Members with no
plan yet are asked to see the front desk. Gyms can turn this off in Members → Member community ("Only members with
an active plan can use it"; stored in the owner's settings as `community.active_only`).


## Community engagement (phase 24)

Run `sql/phase24_community_engage.sql` once. Code: `gympulse_engage.py`.

| Feature | Members | Gym |
|---|---|---|
| **Check-in posts** | After a real check-in today: "📍 You checked in at 7:12. Let your gym know you're here?" with workout, note, photo and sticker. "N training now" (check-ins in the last 2 hours) with faces, people you follow first | — |
| **Streaks** | Weeks in a row with a visit (Mon–Sun). One missed week a calendar month is covered by a freeze automatically. "🔥 N-week streak" on the profile | — |
| **Challenges** | Cards at the top of the feed, Join (posts "I just joined…"), progress bar from real check-ins in the challenge dates, badge when done | Create (name, visits, dates, badge emoji): announced in the feed; finishers get an automatic shout-out post and badge; table of joined and finished |
| **Buddies** | Search → 🤝 Find a buddy: own buddy profile (goal, usual times, a line), list sorted by matching goal and times, "Train together?" sends a ready-made message (respects message settings and blocks) | — |
| **Recognition** | Milestone cards (10, 25, 50, 100… visits, only the highest reached), anniversary cards and a monthly recap card (first week of the month): Share to feed, Save image, Not now. Badges on the profile | ⭐ Member of the week: pinned post, optional framed photo, badge and notification. Reply as coach on any post (Coach badge) |
| **Class feeds** | Feed → Classes: the member's classes (booked or attended, last 14 days and next 7), post a photo and tag classmates (they're notified) | — |
| **Progress posts** | Create a post → 📈 Progress; add an "after" photo for an automatic before / after | — |
| **Nudges** | Up to 3 at the top: "N people you follow trained today", streak at risk (from Thursday), challenge visits left | — |
| **Polls & Q&A** | Vote (results bars after voting); Create a post → ❓ Ask the coach | Post polls (2–4 options); questions listed with "Needs an answer" first; reply as coach |
| **Stickers & frames** | Stickers ("Leg day", "New PB"…) and the gym's branded frame on posts and stories; framed cards to save for Instagram | Member of the week photos get the frame |

Notifications add: tagged in a class post, badge earned, coach replied (in the app only).


## Photo and video editor, reels (phase 25)

Run `sql/phase25_community_media.sql` once. Code: `gympulse_media.py` (Streamlit components v2).

- **Choosing media:** "Choose from your photos / videos" opens the phone's own photo picker (iOS and Android ask
  for permission there and share only what the member picks; a website can't get blanket camera-roll access).
  "Take a photo / Record a video" opens the camera.
- **Editing (photos):** swipe left / right to change the colour filter (Normal, Vivid, Warm, Cool, Mono, Fade, Noir,
  Gym), or tap the filter names; add text (drag it, 7 colours, size, plain or with a background), gym stickers,
  and the gym's frame. The photo is rendered at 1080 × 1350 (posts) or 1080 × 1920 (stories) and uploaded.
- **Drafts:** "Save draft" keeps the edited photo and caption on that phone (browser storage, up to 8); drafts show
  in the picker. Video drafts aren't saved (too big for browser storage).
- **Videos:** up to 60 seconds and 45 MB, for reels and video stories. The filter and text are saved as settings and
  shown over the video when it plays; a cover frame is captured automatically.
- **Reels:** a 🎬 icon in the community menu. Full-height vertical reels, swipe up / down; the visible one plays
  muted (tap 🔇 for sound); double-tap or the heart to like; comments; tap the name for the profile. Reels also
  appear in the feed.
- **Music:** not included yet. Real songs need licences (Instagram and TikTok pay record labels for theirs);
  a royalty-free sound library can be added later.

## Profiles, highlights and the new create screen (phase 26)

Run `sql/phase26_community_profiles.sql` once (safe to run again). It adds a cover photo for each
member, story highlights and pinned posts.

**Profile page** (Community → person icon, or tap any name):

- Cover photo with the profile photo over it. A green ring means they have a live story (tap to watch).
- Name, @handle, and counts: posts, followers, following, likes. Tap followers or following to see the list.
- Someone else: **Follow**, **Message** and **⋯** (block or report). You: **Edit profile** (bio, cover
  photo, who can message you), **Story archive** and **＋** for a new story.
- Chips for streak, badges and goal.
- **Highlights**: circles of saved stories. Open Story archive, pick stories, name the highlight.
- Tabs: posts grid (pinned first), reels, and class posts they were tagged in. Open one of your own posts
  and tap **Pin to top of profile**.

**Create screen** (posts, stories and reels): **Camera**, **Text** (type on a colour background; swipe for
colours) and **Drafts** at the top, then the **Library** with All / Photos / Videos and **Select multiple**.
The phone's own picker opens; GymPulse only gets what the member chooses.

## Training now privacy (phase 27)

Run `sql/phase27_training_now_privacy.sql` once (safe to run again).

- **Members:** Edit profile → "Hide me from Training now". Their photo and name no longer appear in the strip
  other members see after a check-in.
- **Owner:** Community → Settings → "Show members who's training now". Turn it off to hide the strip for
  everyone (good for gyms whose members prefer privacy). No SQL needed for this switch.

## Train tab (phase 29)

Run `sql/phase29_train.sql` once (safe to run again). The member app gets a **Train** tab, for use at the gym
even when nobody else is posting:

- **Today's workout** from the coach at the top (Community → Train → Today's workout, one per day). Exercises
  in it become buttons that open them in the logger.
- **Log**: pick an exercise, see "last time" and "best", log sets in two taps. Beating your best weight (or
  more reps at it) is a **PR** with a "Share my PR with the gym" button (only if the feed is on and they joined).
- **Progress**: workouts this week, personal records with estimated 1-rep max, and a chart per exercise.
- **Gym now**: Quiet / Normal / Busy from check-ins in the last 90 minutes compared with the usual for this hour
  (8-week average for today's weekday), the quietest time later today, and a bar chart.
- **Tools**: rest timer (1, 1½, 2, 3 min, beeps and vibrates) and a plate calculator.

**Machine guides** (Community → Train → Machine guides): add a machine with a video (upload up to 45 MB, or a
YouTube/Instagram link) and tips, download its QR code and stick it on the machine. Scanning opens a public
guide page (`?guide=<id>`): no login.
