-- =====================================================================
-- GymPulse AI · Phase 36 · Corporate plan renewals
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds three columns; it deletes nothing.
--
--   companies.billing_cycle    how often the company pays: monthly, quarterly or yearly
--   companies.next_renewal     the date the company's next payment is due
--   companies.hr_reminded_for  the renewal date HR was last reminded about (so they get one email, not one a day)
--
-- Staff on a company plan no longer get "renew and pay" reminders. Instead the company's HR contact gets one
-- email a week before the plan renews, with the amount due and the staff on the plan.
-- =====================================================================

alter table public.companies add column if not exists billing_cycle text not null default 'monthly';
alter table public.companies add column if not exists next_renewal date;
alter table public.companies add column if not exists hr_reminded_for date;

alter table public.companies drop constraint if exists companies_billing_cycle_chk;
alter table public.companies add constraint companies_billing_cycle_chk
    check (billing_cycle in ('monthly', 'quarterly', 'yearly'));

-- Check it worked: should say true.
select exists (select 1 from information_schema.columns
               where table_name = 'companies' and column_name = 'next_renewal') as corporate_renewals;
