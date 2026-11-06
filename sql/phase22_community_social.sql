-- =====================================================================
-- GymPulse AI · Phase 22 · Community: stories, follows, messages, profiles
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase21_community.sql first.
--
--   community_stories       photo/text stories, shown for 24 hours, then archived
--                           (only the author sees their archive)
--   community_story_views   who has seen a story (for the "seen" ring)
--   community_follows       member follows member (same gym)
--   community_dms           direct messages between members (same gym)
--   community_blocks        a member blocks another (no messages, hidden profile)
--   members.community_bio   short bio on the member's profile
--   members.community_dm    who can message them: everyone / following / nobody
-- Members never read these tables directly: the app reads them on the server,
-- only for the signed-in member's own gym.
-- =====================================================================

begin;

alter table public.members add column if not exists community_bio text;
alter table public.members add column if not exists community_dm  text not null default 'everyone';

create table if not exists public.community_stories (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete cascade,      -- null = posted by the gym
    author_name text not null,
    photo       text,
    body        text not null default '',
    hidden      boolean not null default false,
    created_at  timestamptz not null default now(),
    expires_at  timestamptz not null default now() + interval '24 hours'
);
create index if not exists community_stories_gym_idx on public.community_stories (gym_id, expires_at desc);

create table if not exists public.community_story_views (
    story_id    uuid not null references public.community_stories (id) on delete cascade,
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (story_id, member_id)
);

create table if not exists public.community_follows (
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    follower_id uuid not null references public.members (id) on delete cascade,
    followee_id uuid not null references public.members (id) on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (follower_id, followee_id),
    check (follower_id <> followee_id)
);
create index if not exists community_follows_followee_idx on public.community_follows (followee_id);

create table if not exists public.community_dms (
    id           uuid primary key default gen_random_uuid(),
    gym_id       uuid not null references public.gyms (id) on delete cascade,
    sender_id    uuid not null references public.members (id) on delete cascade,
    recipient_id uuid not null references public.members (id) on delete cascade,
    body         text not null,
    created_at   timestamptz not null default now(),
    read_at      timestamptz
);
create index if not exists community_dms_pair_idx on public.community_dms (gym_id, sender_id, recipient_id, created_at);
create index if not exists community_dms_inbox_idx on public.community_dms (recipient_id, read_at);

create table if not exists public.community_blocks (
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    blocker_id  uuid not null references public.members (id) on delete cascade,
    blocked_id  uuid not null references public.members (id) on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (blocker_id, blocked_id)
);

do $$
declare t text;
begin
    foreach t in array array['community_stories', 'community_story_views', 'community_follows', 'community_dms',
                             'community_blocks'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

commit;

-- Check it worked: 5 tables
select to_regclass('public.community_stories') is not null as stories,
       to_regclass('public.community_follows') is not null as follows,
       to_regclass('public.community_dms') is not null as messages,
       to_regclass('public.community_blocks') is not null as blocks,
       to_regclass('public.community_story_views') is not null as story_views;
