-- =====================================================================
-- GymPulse AI · Phase 4 · Staff assignment and automation
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds columns and an index.
--
-- assigned_to: which staff member owns a play (names come from
--              Settings -> Team & automation).
-- created_by:  'rule:<id>' when an automation rule created the play.
-- Before this script the app still works and writes both into the note.
-- Automation rules themselves are stored in profiles.settings; no new table.
-- =====================================================================

begin;

alter table public.retention_actions add column if not exists assigned_to text;
alter table public.retention_actions add column if not exists created_by  text;

create index if not exists retention_actions_gym_assignee_idx
    on public.retention_actions (gym_id, assigned_to) where status <> 'Done';

-- Settings (staff list, automation rules) are saved in profiles.settings.
-- Make sure that column exists.
alter table public.profiles add column if not exists settings jsonb not null default '{}'::jsonb;

commit;

select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'retention_actions'
  and column_name in ('assigned_to', 'created_by');
