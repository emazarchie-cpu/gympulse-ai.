-- =====================================================================
-- GymPulse AI · Phase 3 · Payments and revenue attribution
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only creates a table, indexes and a policy.
--
-- One row per renewal or payment. A payment can be credited to at most one
-- retention play, and each play to at most one payment (unique index), so
-- the same money is never counted twice in reports.
-- =====================================================================

begin;

create table if not exists public.payments (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    member_id     uuid references public.members (id) on delete set null,
    amount        numeric(12, 2) not null check (amount >= 0),
    paid_on       date not null default current_date,
    covers_until  date,
    plan          text,
    kind          text not null default 'renewal'
                  check (kind in ('new', 'renewal', 'recovered', 'other')),
    method        text,
    action_id     uuid references public.retention_actions (id) on delete set null,
    note          text,
    created_at    timestamptz not null default now()
);

create index if not exists payments_gym_paid_idx on public.payments (gym_id, paid_on desc);
create index if not exists payments_member_idx  on public.payments (member_id, paid_on desc);
create unique index if not exists payments_one_credit_per_play_uidx
    on public.payments (action_id) where action_id is not null;

alter table public.payments enable row level security;

-- Uses the helper created by sql/phase1_security.sql.
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'payments' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.payments for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked: should return one row, rls_on = true.
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = 'payments') as policies
from pg_class c where c.relname = 'payments' and c.relnamespace = 'public'::regnamespace;
