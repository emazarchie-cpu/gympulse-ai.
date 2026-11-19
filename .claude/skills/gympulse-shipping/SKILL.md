---
name: gympulse-shipping
description: How to ship any code change to GymPulse AI - branch, check, commit, pull request, squash-merge, and confirm the Render deploy. Use for every change to the repository, however small.
---

# Shipping a change to GymPulse AI

## Branch
Start every task from the latest main:
```bash
git fetch -q origin main && git checkout -q -B <working-branch> origin/main
```
Use the branch name the session gives you. Never push straight to `main`.

## Before committing
- `python3 -m py_compile <changed .py files>` must pass.
- For anything visible, render it and look at a screenshot at 1366px and 390px wide (see `gympulse-ui`).
- For SQL, write a new numbered file in `sql/` (e.g. `phase45_*.sql`). The founder runs it in the Supabase
  SQL editor; say exactly which file to run and what it does. Never assume it has been run.
- Workflows in `.github/workflows/` run on `ubuntu-24.04` when they need a browser (Playwright doesn't
  support newer images yet).

## Commit and PR
- One commit per change with a plain-English message: what changed and why.
- Never put model names in commits, PR titles or bodies.
- End commit messages and PR bodies with the attribution lines the session provides.
- Push with `git push -u origin <branch>` (retry network errors with backoff).
- Open a PR into `main` with a short description: what changed for the founder or gyms, and how it was checked.
- Squash-merge it when the checks above passed, unless the founder asked to review first.

## After merging
- Render deploys automatically in a few minutes. When it matters, confirm on the live site
  (https://usegympulseai.com) that the change is there.
- Tell the founder in plain words what changed, where to see it, and anything they must do
  (run SQL, add a secret, hard-refresh with Ctrl+Shift+R).
- Report honestly: say what was checked and what wasn't (e.g. "not seen on your live account yet").

## Where things live
| Thing | Place |
|---|---|
| App entry, top nav, routing | `app.py` |
| Shared UI helpers (page_header, kpi_row, table, chips) | `gympulse_workspaces.py` |
| Global styles | `gympulse_design.py` (`CSS`, `POLISH_CSS`, `APP_CSS`) |
| Billing, Paystack | `gympulse_billing.py`, `gympulse_invoices.py` |
| WhatsApp | `gympulse_whatsapp.py`, `supabase/functions/whatsapp-webhook`, `docs/WHATSAPP.md` |
| Member emails | `gympulse_campaigns.py`, `gympulse_email.py` |
| Scheduled jobs | `.github/workflows/` (auto-messages, paystack-sync, monthly reports, demo gym) |
| Secrets | Render env vars, GitHub Actions secrets, Supabase function secrets: never in code |
