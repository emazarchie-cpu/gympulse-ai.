# Owner and staff access

The gym owner runs the business. Staff run the gym day to day. Each staff member
has their own login and works in the owner's gym.

## One-time setup
Run `sql/phase13_staff.sql` in Supabase (SQL Editor → New query → paste → Run).
It is safe to run again. It adds:
- `gym_staff`: the team.
- `gp_is_gym_owner()`.
- `gp_staff_context()`.

It also lets **active** staff use the gym's data, and keeps invoices owner-only.

## Adding staff (owner)
Open **Owner → Team & access → Add a staff member**. Enter the person's name and email.
- GymPulse creates their login and emails them a temporary password from GymPulse AI. The password is also shown to you once, so you can share it on WhatsApp.
- They sign in at usegympulseai.com and change the password in **Settings**.
- The email must not already have a GymPulse AI login. Use a work email if needed.
- Per staff member, you can:
  - **Turn access off or on**: they can't use the gym while it's off.
  - **Send password reset**.
  - **Remove from team**: their login is deleted. Members and records they added stay.

## Who sees what

| | Owner | Staff |
|---|---|---|
| Dashboard (priorities, follow-ups) | ✓ with revenue figures | ✓ without revenue figures |
| Members, profiles, Check-in | ✓ | ✓ |
| Payments & Renewals (record payments) | ✓ | ✓ |
| Risk Radar, Action Centre, Follow-ups | ✓ | ✓ |
| Grow tools | ✓ | ✓ except Monthly report and Team. Settings inside Grow (payment details, automatic messages, loyalty) are view-only |
| **Owner page**: business insights, retention rate, revenue, Team & access, Monthly report, subscription summary | ✓ | ✗ |
| Archie | ✓ | ✗ |
| Subscription, payments and receipts | ✓ | ✗ |
| Settings: gym, email branding, trainers, automation, devices | ✓ | ✗ (staff only see their own password) |

When the gym's plan ends, staff see "Please ask the gym owner to renew". Only the owner sees the plans and checkout.

## How it's enforced
- **In the app**: owner-only pages are hidden from staff and redirect to the Dashboard if opened directly.
- **In the database**:
  - `gp_owns_gym()` lets the owner and active staff read and write gym data.
  - Invoices and the staff list are owner-only (`gp_is_gym_owner()`).
  - Staff can read the gym row but not change it.
  - Turned-off staff have no access at all.
- Deleting a gym in Admin also deletes its staff logins.
