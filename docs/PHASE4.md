# Phase 4: Intelligent automation

Goal: less manual work, with the owner still in control of every message.

## What changed

**Automation rules** (Settings → Team & automation). Turn on "Create plays automatically"
and pick which rules apply:

| Rule | Default play | On by default |
|---|---|---|
| Renewal within 14 days and attendance dropping | Renewal offer (becomes a check-in unless you set an offer) | Yes |
| Member becomes high risk | Each member's suggested play | Yes |
| No check-in for 14 days | WhatsApp check-in | No |
| Membership lapsed in the last 14 days | Personal call | No |

The master switch is off until you turn it on.
- **What runs it:** rules run when the dashboard or Action Centre opens, at most once every
  10 minutes.
- **Daily limit:** you set how many plays rules may create per day (default 10).
- **No duplicates:** members who already have an open play, or were worked recently,
  are skipped.
- **Assignment:** each rule can assign its plays to a staff member.
- **Never sends messages:** automation only creates plays on the board. Every message
  still needs a person to press send, and offers only use terms you type in.

**Team and workload.**
- Add staff names in Settings → Team & automation.
- Every play can be assigned to a staff member.
- The Action Centre shows each person's open, overdue and follow-up-due plays, and can
  filter the board by person.

**Overdue reminders.** The dashboard flags overdue plays and plays due today with a
banner and a one-time notification, plus a button to the board.

**Weekly report** (Business Insights → Weekly report). It is built only from recorded
data: plays started, contacts, outcomes, payments, renewal rate, who needs you next week,
and team workload. You can download it, or email it to yourself once email sending is
connected (`RESEND_API_KEY` and `EMAIL_FROM` on Render).

**Archie** knows the team workload and which rules are on.

## Run in Supabase

`sql/phase4_automation.sql` adds `assigned_to` and `created_by` to plays, and makes sure
`profiles.settings` exists, since staff and rules are saved there. Before you run it,
assignments are written into the play's note.

## Completion test

1. Add two staff names and turn on automation with the high-risk rule assigned to one
   of them. Save.
2. Open the dashboard: "Your automation rules added N plays".
3. The Action Centre shows them in To start, assigned to that person, in the team
   workload. No message has been sent.
