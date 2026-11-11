-- =====================================================================
-- GymPulse AI · Phase 40 · Signed subscription agreements
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one table; it deletes nothing.
--
-- Before a gym pays for a plan, the owner signs the Subscription Agreement at checkout
-- (docs/legal/SUBSCRIPTION_AGREEMENT.md). Each signature is kept here: who signed, for which
-- business, their role, when, from which IP, the agreement version and a SHA-256 fingerprint of
-- the exact text they saw, and the plan and price. Rows are written by GymPulse AI's server;
-- the gym can read its own, but nobody can change or delete them from the app.
-- =====================================================================

begin;

create table if not exists public.agreement_signatures (
    id             uuid primary key default gen_random_uuid(),
    gym_id         uuid not null references public.gyms (id) on delete cascade,
    document       text not null default 'subscription',
    version        text not null,
    text_sha256    text not null,
    business_name  text,
    signer_name    text not null,
    signer_role    text,
    signer_email   text,
    signed_at      timestamptz not null default now(),
    ip             text,
    user_agent     text,
    plan           text,
    period         text,
    amount         numeric(12, 2),
    invoice_id     uuid
);
create index if not exists agreement_signatures_gym_idx on public.agreement_signatures (gym_id, signed_at desc);

alter table public.agreement_signatures enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'agreement_signatures'
                   and policyname = 'gp_owner_reads_own') then
        create policy gp_owner_reads_own on public.agreement_signatures for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked: should say true.
select to_regclass('public.agreement_signatures') is not null as agreement_signatures;
