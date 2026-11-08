-- =====================================================================
-- GymPulse AI · Phase 30 · More in the Train tab
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds tables and a column; it deletes nothing.
--
--   workout_routines    a member's saved workouts ("Push day": bench, shoulder press…)
--   body_logs           body weight, waist and body fat over time
--   members.train_week_goal   workouts a week the member is aiming for (default 3)
--
-- Challenges use community_challenges / community_challenge_entries / community_badges
-- (sql/phase24_community_engage.sql). The old community feed tables are no longer used by the
-- app; they're left in place so nothing is lost.
-- =====================================================================

begin;

alter table public.members add column if not exists train_week_goal int not null default 3
    check (train_week_goal between 1 and 7);

create table if not exists public.workout_routines (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    name        text not null check (length(name) between 1 and 60),
    exercises   text[] not null default '{}',
    created_at  timestamptz not null default now()
);
create index if not exists workout_routines_member_idx on public.workout_routines (member_id, created_at desc);

create table if not exists public.body_logs (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    logged_on   date not null default current_date,
    weight_kg   numeric(5, 1) check (weight_kg is null or weight_kg between 20 and 400),
    waist_cm    numeric(5, 1) check (waist_cm is null or waist_cm between 30 and 250),
    body_fat    numeric(4, 1) check (body_fat is null or body_fat between 2 and 70),
    created_at  timestamptz not null default now(),
    unique (member_id, logged_on)
);

do $$
declare t text;
begin
    foreach t in array array['workout_routines', 'body_logs'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

commit;

-- Check it worked: all three should be true.
select to_regclass('public.workout_routines') is not null as routines,
       to_regclass('public.body_logs') is not null as body,
       exists (select 1 from information_schema.columns
                where table_name = 'members' and column_name = 'train_week_goal') as week_goal;
