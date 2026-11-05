-- =====================================================================
-- GymPulse AI · Phase 10 · Free trial and subscriptions
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  gym_subscriptions  one row per gym: trial end date, paid-until date,
--                     price, status (trial / active / free)
--  platform_settings  prices and payment details, set in Admin -> Billing
--  billing_events     trial reminder emails already sent (so none repeat)
--
-- Every existing gym gets a 30-day free trial starting today. New gyms get
-- one automatically when they sign up. Gym owners can READ their own
-- subscription and the prices. Only the Admin page (service key) can change
-- them.
-- =====================================================================

begin;

create table if not exists public.gym_subscriptions (
    gym_id         uuid primary key references public.gyms (id) on delete cascade,
    status         text not null default 'trial' check (status in ('trial', 'active', 'free')),
    trial_ends_on  date not null default (current_date + 30),
    paid_until     date,
    plan           text,
    price          numeric(12, 2),
    note           text,
    created_at     timestamptz not null default now(),
    updated_at     timestamptz not null default now()
);
alter table public.gym_subscriptions enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'gym_subscriptions' and policyname = 'gp_owner_reads_own') then
        create policy gp_owner_reads_own on public.gym_subscriptions for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
end $$;

create table if not exists public.platform_settings (
    key         text primary key,
    value       jsonb not null default '{}'::jsonb,
    updated_at  timestamptz not null default now()
);
alter table public.platform_settings enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'platform_settings' and policyname = 'gp_read_pricing') then
        create policy gp_read_pricing on public.platform_settings for select to authenticated
            using (key = 'pricing');
    end if;
end $$;
insert into public.platform_settings (key, value) values ('pricing', '{}'::jsonb) on conflict (key) do nothing;

create table if not exists public.billing_events (
    id      uuid primary key default gen_random_uuid(),
    gym_id  uuid references public.gyms (id) on delete cascade,
    kind    text not null,
    ref     text not null,
    at      timestamptz not null default now()
);
create unique index if not exists billing_events_once_uidx on public.billing_events (gym_id, ref);
alter table public.billing_events enable row level security;      -- no policies: Admin page only

-- Existing gyms: 30 days free from today (or from sign-up, if that's later)
insert into public.gym_subscriptions (gym_id, status, trial_ends_on)
select g.id, 'trial', greatest(coalesce(g.created_at::date, current_date), current_date) + 30
from public.gyms g
on conflict (gym_id) do nothing;

-- New gyms: start a 30-day trial automatically
create or replace function public.gp_start_trial()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.gym_subscriptions (gym_id, status, trial_ends_on)
    values (new.id, 'trial', current_date + 30)
    on conflict (gym_id) do nothing;
    return new;
end $$;
revoke all on function public.gp_start_trial() from public;

drop trigger if exists gp_start_trial_on_new_gym on public.gyms;
create trigger gp_start_trial_on_new_gym after insert on public.gyms
    for each row execute function public.gp_start_trial();

commit;

-- Check it worked: every gym has a plan
select g.business_name, s.status, s.trial_ends_on
from public.gyms g left join public.gym_subscriptions s on s.gym_id = g.id
order by s.trial_ends_on nulls first;
