# Phase 1: Foundation

Goal: member records and attendance you can trust, flowing
**Member Management → Check-in → Risk Radar** without manual steps.

## What the audit found

| Area | Before | Now |
|---|---|---|
| New members | Registration saved only name, contact and body details. Plan and fee had to be typed again in the Risk Radar's data tools, so new members were invisible to the radar until then. | Registration also asks for plan, monthly fee and membership end date. The member is scored straight away. |
| Attendance | Check-ins from the front desk, scans and devices were stored without saying where they came from, and nothing stopped the same visit being saved twice. | Every check-in is one standard event (`source`, `event_id`). Duplicates are blocked in the app (10-minute window) and, after the SQL, by a unique index. |
| History | Past attendance could only be typed in as monthly counts. | **Check-in → Import history** loads a CSV of real visits. Re-importing the same file adds nothing. |
| Timestamps | Times with and without fractions of a second were mixed, and the ones without were silently dropped when reading check-ins and completed actions. | All database timestamps are read in ISO 8601, so no visit is lost. |
| Risk Radar | Already preferred real check-ins over typed numbers for scored members. | Unchanged, plus the dashboard shows how many members are scored from check-ins and who can't be scored yet. |
| Assessment pages | Member Assessment and Batch Assessment were separate scoring tools outside the member record. | Removed. Their scoring logic (`prepare_member_data`, `assess_members`) still powers the Risk Radar. |
| Data isolation | Most queries filtered by gym, but some updates and deletes used only the record id. | Every read, update and delete on gym tables is limited to the signed-in owner's gym in one place (`GYM_SCOPED_TABLES` in `gympulse_workspaces.py`). Writes for another gym are refused. |

## What you need to run in Supabase

1. **`sql/phase1_foundation.sql`** (safe to run, adds columns and indexes only).
   After it, check-ins record their source and duplicates are blocked by the database.
2. **`sql/phase1_security.sql`**, in two steps:
   - Run **STEP 1** alone and read the results: which tables have Row Level Security
     switched on today, which policies exist, and any records linked to the wrong gym
     (those counts should be 0).
   - Then run **STEP 2** to add Row Level Security policies that limit every table to
     the gym's owner. Afterwards, check that sign-in, the trainer share page and device
     check-in still work.

The app works before and after both scripts.

## Completion test

1. Register a member with a plan, fee and end date in **Members**.
2. Check them in on **Check-in**.
3. Open **Risk Radar** or the member's profile: they are scored, with "days since last
   visit" coming from the check-in, and the renewal countdown from the end date.

Tested on sample data in a local preview, including importing the same visit file twice.
