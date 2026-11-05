-- =====================================================================
-- GymPulse AI · Phase 19 · Members log in with an email code
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase18_member_portal.sql first.
--
-- On usegympulseai.com members choose "Member", type the email their gym has,
-- and get a 6-digit code by email. No sign-up and no password: the gym (or an
-- import, or the sign-up link) has already added them.
--
--   members.portal_code_hash     the code, scrambled (the code itself is never stored)
--   members.portal_code_expires  codes work for 10 minutes
--   members.portal_code_tries    wrong tries (5 and the code stops working)
-- =====================================================================

begin;

alter table public.members add column if not exists portal_code_hash    text;
alter table public.members add column if not exists portal_code_expires timestamptz;
alter table public.members add column if not exists portal_code_tries   int not null default 0;

commit;

-- Check it worked: 3 rows
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'members' and column_name like 'portal_code%';
