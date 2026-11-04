-- =====================================================================
-- GymPulse AI · Phase 6 · Founder admin: monthly report log
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- One row per gym, month and channel, so no gym gets the same month's
-- report twice. Row-level security is on with no policies: only the
-- service-role key (the Admin page and the monthly script) can read or
-- write it. Gym owners can't see it.
-- =====================================================================

begin;

create table if not exists public.platform_reports (
    id         uuid primary key default gen_random_uuid(),
    gym_id     uuid not null references public.gyms (id) on delete cascade,
    period     text not null,                 -- 'YYYY-MM'
    channel    text not null check (channel in ('email', 'whatsapp')),
    sent_by    text,
    sent_at    timestamptz not null default now()
);
create unique index if not exists platform_reports_uidx on public.platform_reports (gym_id, period, channel);
alter table public.platform_reports enable row level security;

commit;

-- Check it worked: rls_on = true, policies = 0
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = 'platform_reports') as policies
from pg_class c where c.relname = 'platform_reports' and c.relnamespace = 'public'::regnamespace;
