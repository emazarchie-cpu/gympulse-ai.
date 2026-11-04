-- =====================================================================
-- GymPulse AI · Phase 9 · Loyalty points and automatic messages
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  loyalty_redemptions  rewards a member has claimed (points are worked out
--                       from check-ins and payments, so only claims are stored)
--  auto_messages        every automatic email sent, so each one goes out at
--                       most once per member per occasion
-- =====================================================================

begin;

create table if not exists public.loyalty_redemptions (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    reward      text not null,
    points      integer not null check (points > 0),
    created_at  timestamptz not null default now()
);
create index if not exists loyalty_redemptions_gym_idx on public.loyalty_redemptions (gym_id, created_at desc);

create table if not exists public.auto_messages (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete cascade,
    kind        text not null,              -- renewal | missed | reward
    ref         text not null,              -- the occasion, e.g. end:2026-11-30
    status      text not null default 'sent',
    sent_at     timestamptz not null default now()
);
create unique index if not exists auto_messages_once_uidx on public.auto_messages (gym_id, member_id, kind, ref);
create index if not exists auto_messages_gym_idx on public.auto_messages (gym_id, sent_at desc);

do $$
declare t text;
begin
    foreach t in array array['loyalty_redemptions', 'auto_messages']
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

-- Check it worked: 2 tables, rls_on = true, 1 policy each
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname in ('loyalty_redemptions', 'auto_messages');
