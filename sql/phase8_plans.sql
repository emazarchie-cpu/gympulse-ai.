-- =====================================================================
-- GymPulse AI · Phase 8 · More membership plans
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- Plans: Daily, Weekly, 2 weeks, Monthly, 2 months, Quarterly, 6 months,
-- Yearly (and Annual, the old name for Yearly, so existing members keep
-- working). Removes any older rule that only allowed Monthly, Quarterly
-- and Annual, then adds one rule with the full list.
-- =====================================================================

begin;

do $$
declare c record;
begin
    for c in
        select con.conname, rel.relname
        from pg_constraint con
        join pg_class rel on rel.oid = con.conrelid
        join pg_namespace nsp on nsp.oid = rel.relnamespace
        where nsp.nspname = 'public' and con.contype = 'c'
          and rel.relname in ('member_activity', 'payments')
          and (pg_get_constraintdef(con.oid) ilike '%membership_type%'
               or pg_get_constraintdef(con.oid) ilike '%plan%')
    loop
        execute format('alter table public.%I drop constraint %I', c.relname, c.conname);
    end loop;
end $$;

alter table public.member_activity add constraint member_activity_plan_check
    check (membership_type is null or membership_type in
           ('Daily', 'Weekly', '2 weeks', 'Monthly', '2 months', 'Quarterly', '6 months', 'Yearly', 'Annual'));

commit;

-- Check it worked: one row, member_activity_plan_check
select conname, pg_get_constraintdef(oid) from pg_constraint where conname = 'member_activity_plan_check';
