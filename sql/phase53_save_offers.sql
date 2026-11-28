-- =====================================================================
-- GymPulse AI · Phase 53 · "Stay with us" discount when a member asks to cancel
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one table; it deletes nothing.
--
-- When a member taps "Cancel my membership" in the member app (or tells staff on the phone), the gym can offer
-- a discount on one month. Every offer is recorded here, so the rules can be enforced:
--   once per member in 12 months, only for paying members of 60+ days with a current plan, one month only,
--   used once on the next renewal, and lost 45 days after the current plan ends.
-- The member app uses the server key after checking the member's own link; staff use RLS (owner and staff).
-- =====================================================================

begin;

create table if not exists public.save_offers (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    member_id     uuid not null references public.members (id) on delete cascade,
    percent       integer not null check (percent between 5 and 100),
    discount      numeric(12, 2) not null check (discount >= 0),   -- naira off the next renewal
    channel       text not null default 'app' check (channel in ('app', 'staff')),
    reason        text,
    accepted      boolean not null,
    expires_on    date,
    used_at       timestamptz,
    used_ref      text,
    staff         text,
    created_at    timestamptz not null default now()
);
create index if not exists save_offers_member on public.save_offers (member_id, created_at desc);
alter table public.save_offers enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'save_offers'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.save_offers for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;
