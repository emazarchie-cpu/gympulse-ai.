# Phase 3: Connect retention to revenue

Goal: a gym owner can trace a retention play to a confirmed renewal and the money it brought in.

## What changed

**Payments.** Every renewal is one record in a new `payments` table, with amount, date,
plan, the date it covers until, the payment method and the type (renewal, recovered or
new). There are two places to record one:
- **Payments & Renewals → Record a renewal or payment** (new)
- a member's profile → Membership → Record a renewal (now uses the same logic)

Recording a payment also updates the member's plan dates, so the Risk Radar and renewal
reminders stay correct.

**Attribution rules** (`gympulse_revenue.py`):
- A payment is credited to the member's most recent play that was started or contacted
  in the 45 days before the payment.
- Cancelled plays never get credit.
- Each payment is credited to at most one play, and each play to at most one payment.
  A unique index in the database enforces this, so revenue is never double-counted.
- A confirmed renewal closes the credited play as **Retained**. A message on its own
  never does.
- A payment from a member whose membership had already lapsed counts as **recovered**
  revenue.

**Reporting.** Business Insights has a new "Revenue outcomes · last 30 days" section:
- collected
- retained by plays (credited renewals)
- recovered
- renewal rate
- revenue credited by each play

The dashboard's "Revenue retained" card uses credited payments once they're available.
Archie sees the same figures, labelled as recorded. Wherever credit is shown, the app
says it means a play was involved, not proof the member would have left without it.

## Run in Supabase

`sql/phase3_revenue.sql` creates the `payments` table with its indexes and its access
rule. Before you run it, renewals are still saved on the member, the credited play is
still closed as Retained, and reports fall back to renewal dates and recorded outcomes.

## Completion test

1. Start a play for a member whose renewal is due, then mark them contacted.
2. Record their renewal on Payments & Renewals. The note says it was credited to the play.
3. The play is now Done · Retained, and Business Insights shows the amount under
   "Retained by plays".
