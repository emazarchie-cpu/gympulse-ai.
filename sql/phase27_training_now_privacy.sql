-- =====================================================================
-- GymPulse AI · Phase 27 · "Hide me from Training now"
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds one column; it deletes nothing.
--
-- members.community_hide_now: the member chose not to appear in the
-- "Training now" strip other members see after a check-in.
-- (The gym-wide on/off switch lives in the owner's settings: no SQL.)
-- =====================================================================

alter table public.members add column if not exists community_hide_now boolean not null default false;

-- Check it worked: one row, community_hide_now.
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'members' and column_name = 'community_hide_now';
