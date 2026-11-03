# Supabase: what's left to run

Phase 1 is done (`phase1_foundation.sql` and `phase1_security.sql` were run on 3 Nov 2026).

Run these in order: SQL Editor → New query → paste the whole file → Run. Each one only adds
columns, tables or indexes and deletes nothing, so running one twice is safe. The app works
before and after each.

| Order | File | What it switches on | Check after running |
|---|---|---|---|
| 1 | `sql/phase2_retention.sql` | Contact method, contact date and follow-up date on plays | Lists `contact_method`, `contacted_at`, `details`, `follow_up_on`, `trainer_id` |
| 2 | `sql/phase3_revenue.sql` | The `payments` table: payment history, credit to plays, recovered revenue | One row: `payments`, `rls_on = true`, `policies = 1` |
| 3 | `sql/phase4_automation.sql` | `assigned_to` and `created_by` on plays, and `profiles.settings` | Lists `assigned_to`, `created_by` |

If a script shows an error, copy the red message and send it to Claude. Don't change the
SQL yourself.

## After running them

1. Settings → **Team & automation**: add your staff, and turn on automation if you want it.
   It is off until you switch it on.
2. Business Insights → **Save today as my pilot baseline** on the day you start measuring.
3. Record the next renewal on **Payments & Renewals** to start the payment history.
