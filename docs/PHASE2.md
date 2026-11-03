# Phase 2: Retention engine

Goal: turn member risk into retention work that gets finished and recorded.

## What changed

**One lifecycle for every play.** Recommended → Started → In progress → Contacted →
Follow-up due → Resolved / Unsuccessful. The Action Centre board has a column for each
step: To start, In progress, Contacted · follow up, and Done. Each card shows:
- the play's goal (for example "Secure the renewal")
- how and when the member was contacted, and when to follow up
- the controls for the next step: Start, Mark contacted (method plus follow-up days),
  Record outcome, or Contacted again

**One record, shared everywhere.**
- Sending or logging a message in **Follow-ups** marks the member's open play as
  contacted and schedules its follow-up.
- Marking a renewal reminder as sent on **Payments & Renewals** does the same for
  renewal plays.
- Every page writes through the same functions in `gympulse_workspaces.py`:
  `mark_contacted` and `close_action`.

**Explanations everywhere.** The Risk Radar, Action Centre suggestions and member
profiles show the same Why / When / Next explanation as the dashboard. Starting a play
saves that reason on the play.

**Retention plays.** Each play has an objective, a recommended contact method and a
follow-up timing (`PLAY_INFO`). When a member has had no PT sessions, the default
suggestion is now a trainer introduction rather than a free session the gym never
approved.

**Personalised messages, one builder.** The Action Centre and Follow-ups now use the
same message builder. Messages use the member's goal, how long since their last visit,
their renewal date, the best-matched trainer and the next upcoming class.
- **No invented offers.** A renewal message only mentions an offer, or a closing date,
  that the gym typed in. Without one it becomes a friendly renewal check-in.

**Archie** now sees each open play's stage, goal and contact history, plus how many
follow-ups are due.

## Run in Supabase

`sql/phase2_retention.sql` adds `contacted_at`, `contact_method` and `follow_up_on` to
`retention_actions`. It only adds; it deletes nothing. Before you run it, the app still
works and writes contact details into the play's note instead.

## Completion test

1. On the dashboard or the Action Centre, start a play for a high-risk member.
2. Open it on the board: **Start this play**, then **Mark contacted**.
3. It moves to "Contacted · follow up", showing the method and the follow-up date.
4. **Record outcome**: it moves to Done, and Business Insights and the dashboard count it.
