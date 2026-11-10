-- =====================================================================
-- GymPulse AI · Phase 35 · Personal trainer logins and their workspace
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase13_staff.sql (team logins) and phase34_personal_training.sql.
--
--   gym_staff.role            'staff' (front desk) or 'trainer' (a personal trainer's own login)
--   gym_staff.trainer_id      which trainer (Settings -> Trainers) this login is
--   pt_sessions               personal training sessions: client, date and time, length, status, notes
--   trainer_availability      the hours a trainer works, per weekday
--   trainer_reports           a trainer's weekly report to the owner
-- =====================================================================

begin;

alter table public.gym_staff drop constraint if exists gym_staff_role_check;
alter table public.gym_staff add constraint gym_staff_role_check check (role in ('staff', 'trainer'));
alter table public.gym_staff add column if not exists trainer_id uuid references public.trainers (id) on delete set null;

create table if not exists public.pt_sessions (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    trainer_id  uuid not null references public.trainers (id) on delete cascade,
    member_id   uuid references public.members (id) on delete set null,
    starts_at   timestamptz not null,
    minutes     int not null default 60 check (minutes between 15 and 240),
    status      text not null default 'booked' check (status in ('booked', 'done', 'missed', 'cancelled')),
    notes       text check (notes is null or length(notes) <= 1000),
    created_at  timestamptz not null default now()
);
create index if not exists pt_sessions_trainer_idx on public.pt_sessions (trainer_id, starts_at);
create index if not exists pt_sessions_gym_idx on public.pt_sessions (gym_id, starts_at);

create table if not exists public.trainer_availability (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    trainer_id  uuid not null references public.trainers (id) on delete cascade,
    dow         int not null check (dow between 0 and 6),          -- 0 = Monday
    start_min   int not null check (start_min between 0 and 1435),
    end_min     int not null check (end_min between 5 and 1440),
    unique (trainer_id, dow)
);

create table if not exists public.trainer_reports (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    trainer_id    uuid not null references public.trainers (id) on delete cascade,
    week_start    date not null,
    summary       jsonb not null default '{}'::jsonb,
    body          jsonb not null default '{}'::jsonb,
    submitted_at  timestamptz,
    updated_at    timestamptz not null default now(),
    unique (trainer_id, week_start)
);

do $$
declare t text;
begin
    foreach t in array array['pt_sessions', 'trainer_availability', 'trainer_reports'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

-- On sign-in: which gym a staff login belongs to, now with their role and trainer.
create or replace function public.gp_staff_context()
returns json language sql stable security definer set search_path = public as $$
    select json_build_object(
        'staff', json_build_object('id', s.id, 'full_name', s.full_name, 'email', s.email, 'status', s.status,
                                   'role', s.role, 'trainer_id', s.trainer_id),
        'gym', row_to_json(g),
        'owner', json_build_object('id', p.id, 'full_name', p.full_name, 'business_name', p.business_name,
                                   'settings', p.settings))
    from public.gym_staff s
    join public.gyms g on g.id = s.gym_id
    left join public.profiles p on p.id = g.owner_id
    where s.user_id = auth.uid()
    limit 1;
$$;
revoke all on function public.gp_staff_context() from public;
grant execute on function public.gp_staff_context() to authenticated;

commit;

-- Check it worked: all four should be true.
select to_regclass('public.pt_sessions') is not null as sessions,
       to_regclass('public.trainer_availability') is not null as availability,
       to_regclass('public.trainer_reports') is not null as reports,
       exists (select 1 from information_schema.columns
                where table_name = 'gym_staff' and column_name = 'trainer_id') as trainer_logins;
