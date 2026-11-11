-- =====================================================================
-- GymPulse AI · Phase 42 · Membership Agreement and Waiver signed by each member
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one table; it deletes nothing.
--
-- Each member signs the gym's Membership Agreement and Waiver (docs/legal/MEMBER_AGREEMENT.md),
-- at the front desk on the gym's device or through their personal signing link. Kept here: the
-- version, a SHA-256 fingerprint of the exact text they saw (with their details filled in), their
-- drawn signature, health answers, emergency contact, when, from where and how they signed.
-- The gym (owner and staff) can read and add its own; members sign through GymPulse AI's server.
-- =====================================================================

begin;

create table if not exists public.member_waivers (
    id               uuid primary key default gen_random_uuid(),
    gym_id           uuid not null references public.gyms (id) on delete cascade,
    member_id        uuid not null references public.members (id) on delete cascade,
    version          text not null,
    text_sha256      text not null,
    signer_name      text not null,
    signature_image  text,
    agreement_text   text,
    health           jsonb not null default '{}'::jsonb,
    emergency_name   text,
    emergency_phone  text,
    signed_via       text not null default 'link' check (signed_via in ('front_desk', 'link')),
    signed_at        timestamptz not null default now(),
    ip               text,
    user_agent       text
);
create index if not exists member_waivers_member_idx on public.member_waivers (member_id, signed_at desc);
create index if not exists member_waivers_gym_idx on public.member_waivers (gym_id, signed_at desc);

alter table public.member_waivers enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'member_waivers'
                   and policyname = 'gp_gym_reads_own') then
        create policy gp_gym_reads_own on public.member_waivers for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'member_waivers'
                   and policyname = 'gp_gym_adds_own') then
        create policy gp_gym_adds_own on public.member_waivers for insert to authenticated
            with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

alter table public.member_waivers add column if not exists agreement_text text;   -- the exact text signed

commit;

-- Check it worked: should say true.
select to_regclass('public.member_waivers') is not null as member_waivers;
