-- =====================================================================
-- GymPulse AI · Phase 41 · Hand-drawn signatures on the Subscription Agreement
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one column; it deletes nothing.
--
-- At checkout the gym owner draws their signature with a finger or mouse. The drawing is kept with
-- the signature record (a small PNG as a data URL) and printed on their signed PDF.
-- =====================================================================

alter table public.agreement_signatures add column if not exists signature_image text;

-- Check it worked: should say true.
select exists (select 1 from information_schema.columns where table_name = 'agreement_signatures'
                and column_name = 'signature_image') as drawn_signatures;
