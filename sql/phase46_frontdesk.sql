-- =====================================================================
-- GymPulse AI · Phase 46 · Prospects, cancellation notices and balances owed
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one table and some columns; it deletes nothing.
--
--   prospects                     people who enquired or signed up but haven't paid yet, with their stage
--   members.cancel_*              a member's notice that they want to cancel, the leaving date and outcome
--   members.balance_owed          money the member still owes (part-payments), in naira
-- =====================================================================

begin;

create table if not exists public.prospects (
    id              uuid primary key default gen_random_uuid(),
    gym_id          uuid not null references public.gyms (id) on delete cascade,
    full_name       text not null,
    phone           text,
    email           text,
    source          text not null default 'walk_in',
    stage           text not null default 'new'
                    check (stage in ('new', 'contacted', 'visited', 'joined', 'not_interested')),
    reason          text,
    notes           text,
    member_id       uuid references public.members (id) on delete set null,
    next_follow_up  date,
    contacted_at    timestamptz,
    created_at      timestamptz not null default now(),
    updated_at      timestamptz not null default now()
);
create index if not exists prospects_gym on public.prospects (gym_id, stage, created_at desc);
alter table public.prospects enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'prospects'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.prospects for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

alter table public.members add column if not exists cancel_notice_at timestamptz;
alter table public.members add column if not exists cancel_effective date;
alter table public.members add column if not exists cancel_reason text;
alter table public.members add column if not exists cancel_status text
    check (cancel_status in ('pending', 'saved', 'left'));
alter table public.members add column if not exists balance_owed numeric not null default 0;
alter table public.members add column if not exists balance_note text;

commit;
