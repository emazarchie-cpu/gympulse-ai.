-- =====================================================================
-- GymPulse AI · Phase 7 · Admin tools
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  platform_gym_flags  per-gym admin settings: pause monthly reports, private note
--  admin_audit         a log of every admin action (suspend, delete, pause...)
--
-- Row-level security is on with no policies: only the service-role key
-- (the Admin page) can read or write these. Gym owners can't see them.
-- =====================================================================

begin;

create table if not exists public.platform_gym_flags (
    gym_id          uuid primary key references public.gyms (id) on delete cascade,
    reports_paused  boolean not null default false,
    note            text,
    updated_at      timestamptz not null default now()
);
alter table public.platform_gym_flags enable row level security;

create table if not exists public.admin_audit (
    id           uuid primary key default gen_random_uuid(),
    actor        text,
    action       text not null,
    gym_id       uuid,                 -- kept after a gym is deleted, so no foreign key
    gym_name     text,
    owner_email  text,
    detail       jsonb not null default '{}'::jsonb,
    at           timestamptz not null default now()
);
create index if not exists admin_audit_at_idx on public.admin_audit (at desc);
alter table public.admin_audit enable row level security;

commit;

-- Check it worked: both tables, rls_on = true, policies = 0
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname in ('platform_gym_flags', 'admin_audit');
