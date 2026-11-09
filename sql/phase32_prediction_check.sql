-- =====================================================================
-- GymPulse AI · Phase 32 · Prediction check
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds a table; it deletes nothing.
--
-- prediction_snapshots   every member's risk score frozen on the day a check starts (the 1st of
--                        each month, or "Start a check today"), so at the end of the 30 days the
--                        app can compare what it predicted with who actually left.
--   outcome              left empty = worked out automatically; 'left' or 'stayed' = the owner's
--                        own correction.
-- member_id has no foreign key on purpose: if a member is deleted, their prediction stays so it
-- can still be checked (a deleted member counts as having left).
-- =====================================================================

begin;

create table if not exists public.prediction_snapshots (
    id              uuid primary key default gen_random_uuid(),
    gym_id          uuid not null references public.gyms (id) on delete cascade,
    member_id       uuid not null,
    taken_on        date not null,
    full_name       text,
    probability     numeric(5, 4) not null check (probability between 0 and 1),
    risk            text not null check (risk in ('High', 'Medium', 'Low')),
    drivers         text,
    days_away       int,
    membership_end  date,
    outcome         text check (outcome in ('left', 'stayed')),
    created_at      timestamptz not null default now(),
    unique (gym_id, member_id, taken_on)
);
create index if not exists prediction_snapshots_gym_idx on public.prediction_snapshots (gym_id, taken_on desc);

alter table public.prediction_snapshots enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'prediction_snapshots' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.prediction_snapshots for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked: should say true.
select to_regclass('public.prediction_snapshots') is not null as prediction_check;
