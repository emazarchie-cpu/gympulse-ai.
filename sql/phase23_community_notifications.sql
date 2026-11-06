-- =====================================================================
-- GymPulse AI · Phase 23 · Community notifications
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase22_community_social.sql first.
--
--   community_notifications         "Tunde followed you", "Bola sent you a message"
--                                   (shown in the member app; emailed at most every
--                                   30 minutes per kind)
--   members.community_email_notify  the member wants these by email (default on)
-- =====================================================================

begin;

alter table public.members add column if not exists community_email_notify boolean not null default true;

create table if not exists public.community_notifications (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,   -- who is notified
    actor_id    uuid references public.members (id) on delete cascade,            -- who did it
    kind        text not null check (kind in ('message', 'follow')),
    created_at  timestamptz not null default now(),
    read_at     timestamptz,
    emailed_at  timestamptz
);
create index if not exists community_notifications_member_idx
    on public.community_notifications (member_id, read_at, created_at desc);

alter table public.community_notifications enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'community_notifications' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.community_notifications for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked
select to_regclass('public.community_notifications') is not null as notifications_table;
