-- =====================================================================
-- GymPulse AI · Phase 5 · Growth tools
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds tables, one column, indexes and
-- access rules. Every table is private to the gym that owns it.
--
--  payment_requests  renewals asked for by bank transfer or payment link
--  onboarding_steps  the first-90-days programme, one row per step done
--  exit_reasons      why a member left
--  member_freezes    paused memberships (travel, December, Ramadan, injury)
--  progress_logs     weigh-ins, measurements and personal bests
--  companies         corporate memberships; members.company_id links staff
--  referrals         bring-a-friend invites and rewards
--  challenges        group challenges; challenge_entries holds who joined
-- =====================================================================

begin;

create table if not exists public.payment_requests (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete cascade,
    amount      numeric(12, 2) not null check (amount >= 0),
    plan        text,
    reference   text not null,
    channel     text,
    status      text not null default 'pending' check (status in ('pending', 'paid', 'cancelled')),
    paid_at     timestamptz,
    method      text,
    created_at  timestamptz not null default now()
);
create index if not exists payment_requests_gym_idx on public.payment_requests (gym_id, created_at desc);

create table if not exists public.onboarding_steps (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    step        text not null,
    done_at     timestamptz not null default now(),
    created_at  timestamptz not null default now()
);
create unique index if not exists onboarding_steps_uidx on public.onboarding_steps (member_id, step);

create table if not exists public.exit_reasons (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete set null,
    reason      text not null,
    note        text,
    source      text,
    created_at  timestamptz not null default now()
);
create index if not exists exit_reasons_gym_idx on public.exit_reasons (gym_id, created_at desc);

create table if not exists public.member_freezes (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    starts_on   date not null,
    ends_on     date not null,
    reason      text,
    status      text not null default 'scheduled' check (status in ('scheduled', 'active', 'ended', 'cancelled')),
    extended    boolean not null default false,
    created_at  timestamptz not null default now(),
    check (ends_on >= starts_on)
);
create index if not exists member_freezes_gym_idx on public.member_freezes (gym_id, ends_on);

create table if not exists public.progress_logs (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    logged_on   date not null default current_date,
    weight_kg   numeric(6, 2),
    waist_cm    numeric(6, 2),
    body_fat    numeric(5, 2),
    pb_name     text,
    pb_value    numeric(8, 2),
    note        text,
    logged_by   text,
    created_at  timestamptz not null default now()
);
create index if not exists progress_logs_member_idx on public.progress_logs (member_id, logged_on);

create table if not exists public.companies (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    name        text not null,
    hr_name     text,
    hr_email    text,
    hr_phone    text,
    seats       integer,
    monthly_fee numeric(12, 2),
    created_at  timestamptz not null default now()
);
alter table public.members add column if not exists company_id uuid references public.companies (id) on delete set null;

create table if not exists public.referrals (
    id                uuid primary key default gen_random_uuid(),
    gym_id            uuid not null references public.gyms (id) on delete cascade,
    referrer_id       uuid references public.members (id) on delete cascade,
    friend_name       text not null,
    friend_phone      text,
    friend_member_id  uuid references public.members (id) on delete set null,
    status            text not null default 'invited' check (status in ('invited', 'visited', 'joined', 'rewarded')),
    reward            text,
    joined_on         date,
    rewarded_at       timestamptz,
    created_at        timestamptz not null default now()
);
create index if not exists referrals_gym_idx on public.referrals (gym_id, created_at desc);

create table if not exists public.challenges (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    name          text not null,
    starts_on     date not null,
    ends_on       date not null,
    target_visits integer not null default 12,
    reward        text,
    created_at    timestamptz not null default now(),
    check (ends_on >= starts_on)
);
create table if not exists public.challenge_entries (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    challenge_id  uuid not null references public.challenges (id) on delete cascade,
    member_id     uuid not null references public.members (id) on delete cascade,
    created_at    timestamptz not null default now()
);
create unique index if not exists challenge_entries_uidx on public.challenge_entries (challenge_id, member_id);

-- Access: each gym only sees its own rows (helper from sql/phase1_security.sql)
do $$
declare t text;
begin
    foreach t in array array['payment_requests', 'onboarding_steps', 'exit_reasons', 'member_freezes',
                             'progress_logs', 'companies', 'referrals', 'challenges', 'challenge_entries']
    loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public'
                       and tablename = t and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

commit;

-- Check it worked: 9 tables, each with rls_on = true and 1 policy.
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace
  and c.relname in ('payment_requests', 'onboarding_steps', 'exit_reasons', 'member_freezes',
                    'progress_logs', 'companies', 'referrals', 'challenges', 'challenge_entries')
order by 1;
