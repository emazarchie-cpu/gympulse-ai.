-- =====================================================================
-- GymPulse AI · Phase 12 · Invoices and receipts
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  billing_invoices   one row per checkout: who is paying (billing details),
--                     the plan, the amount, how they paid and when. Paid rows
--                     are the gym's receipts (GP-000001, GP-000002, ...).
--
-- Gym owners can READ their own invoices (to see and download receipts).
-- Only the server (service key) creates or changes them.
-- =====================================================================

begin;

create table if not exists public.billing_invoices (
    id              uuid primary key default gen_random_uuid(),
    number          bigint generated always as identity,
    gym_id          uuid not null references public.gyms (id) on delete cascade,
    plan            text not null,
    period          text not null check (period in ('monthly', 'yearly', 'custom')),
    months          integer not null default 1,
    amount          numeric(12, 2) not null check (amount >= 0),
    currency        text not null default 'NGN',
    status          text not null default 'pending' check (status in ('pending', 'paid', 'cancelled')),
    method          text not null default 'paystack' check (method in ('paystack', 'transfer', 'admin')),
    reference       text,
    billing_name    text,
    billing_email   text,
    billing_phone   text,
    business_name   text,
    address         text,
    city            text,
    state           text,
    period_start    date,
    period_end      date,
    created_at      timestamptz not null default now(),
    paid_at         timestamptz,
    receipt_sent_at timestamptz
);
create unique index if not exists billing_invoices_number_uidx on public.billing_invoices (number);
create unique index if not exists billing_invoices_ref_uidx on public.billing_invoices (reference) where reference is not null;
create index if not exists billing_invoices_gym_idx on public.billing_invoices (gym_id, created_at desc);

alter table public.billing_invoices enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'billing_invoices' and policyname = 'gp_owner_reads_invoices') then
        create policy gp_owner_reads_invoices on public.billing_invoices for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked: rls_on = true, 1 policy
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname = 'billing_invoices';
