-- =====================================================================
-- GymPulse AI · Phase 34 · Members who already have a personal trainer
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds two columns; it deletes nothing.
--
--   members.has_pt          true when the member pays for personal training
--   members.pt_trainer_id   their trainer (from Settings -> Trainers), optional
--
-- GymPulse then stops suggesting "Trainer intro" and "Free PT session" to these members, and uses
-- their own trainer for goal reviews.
-- =====================================================================

alter table public.members add column if not exists has_pt boolean not null default false;
alter table public.members add column if not exists pt_trainer_id uuid;

-- Check it worked: should say true.
select exists (select 1 from information_schema.columns
               where table_name = 'members' and column_name = 'has_pt') as personal_training;
