-- =====================================================================
-- GymPulse AI · Phase 29 · The Train tab in the member app
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds tables and functions; it deletes nothing.
--
--   workout_sets      every set a member logs (exercise, kg, reps, day)
--   coach_workouts    "Today's workout" posted by the gym, one per day
--   machine_guides    a how-to video and tips per machine, opened by a QR code
--   gp_gym_busy       how busy the gym is now, and the usual pattern for today
--   gp_guide          the public machine guide page (QR code on the machine)
-- =====================================================================

begin;

create table if not exists public.workout_sets (
    id           uuid primary key default gen_random_uuid(),
    gym_id       uuid not null references public.gyms (id) on delete cascade,
    member_id    uuid not null references public.members (id) on delete cascade,
    exercise     text not null check (length(exercise) between 1 and 60),
    weight_kg    numeric(6, 2) not null default 0 check (weight_kg >= 0 and weight_kg < 1000),
    reps         int  not null check (reps between 1 and 200),
    performed_on date not null default current_date,
    created_at   timestamptz not null default now()
);
create index if not exists workout_sets_member_idx on public.workout_sets (member_id, exercise, performed_on desc);
create index if not exists workout_sets_gym_idx on public.workout_sets (gym_id, created_at desc);

create table if not exists public.coach_workouts (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    day         date not null,
    title       text not null check (length(title) between 1 and 80),
    body        text not null check (length(body) between 1 and 2000),
    author      text,
    created_at  timestamptz not null default now(),
    unique (gym_id, day)
);

create table if not exists public.machine_guides (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    name        text not null check (length(name) between 1 and 80),
    exercise    text,
    video_url   text,
    tips        text,
    created_at  timestamptz not null default now()
);
create index if not exists machine_guides_gym_idx on public.machine_guides (gym_id, name);

do $$
declare t text;
begin
    foreach t in array array['workout_sets', 'coach_workouts', 'machine_guides'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

-- How busy is it now (check-ins in the last 90 minutes) and the usual number per hour for today's
-- weekday (average over the last 8 weeks), in Lagos time. Used by the member app (server key).
create or replace function public.gp_gym_busy(p_gym uuid)
returns table (hour int, usual numeric, now_visits int)
language sql security definer set search_path = public as $$
    with local as (
        select (checked_in_at at time zone 'Africa/Lagos') as t from public.checkins
         where gym_id = p_gym and checked_in_at > now() - interval '56 days'
    ), today as (
        select extract(dow from now() at time zone 'Africa/Lagos')::int as dow
    ), hours as (
        select extract(hour from t)::int as h, count(*)::numeric / 8 as usual
          from local, today where extract(dow from t)::int = today.dow
         group by 1
    )
    select g.h, coalesce(hours.usual, 0),
           (select count(*)::int from public.checkins
             where gym_id = p_gym and checked_in_at > now() - interval '90 minutes')
      from generate_series(5, 22) as g(h) left join hours on hours.h = g.h
     order by g.h;
$$;
revoke all on function public.gp_gym_busy(uuid) from public;
grant execute on function public.gp_gym_busy(uuid) to service_role;

-- The public guide page behind a machine's QR code: only the guide itself and the gym's name.
create or replace function public.gp_guide(p_id uuid)
returns table (name text, video_url text, tips text, exercise text, business_name text)
language sql security definer set search_path = public as $$
    select mg.name, mg.video_url, mg.tips, mg.exercise, coalesce(p.business_name, g.business_name)
      from public.machine_guides mg
      join public.gyms g on g.id = mg.gym_id
      left join public.profiles p on p.id = g.owner_id
     where mg.id = p_id;
$$;
revoke all on function public.gp_guide(uuid) from public;
grant execute on function public.gp_guide(uuid) to anon, authenticated;

commit;

-- Check it worked: three tables and two functions.
select to_regclass('public.workout_sets') is not null as workouts,
       to_regclass('public.coach_workouts') is not null as coach_posts,
       to_regclass('public.machine_guides') is not null as guides,
       exists (select 1 from pg_proc where proname = 'gp_gym_busy') as busy,
       exists (select 1 from pg_proc where proname = 'gp_guide') as guide;
