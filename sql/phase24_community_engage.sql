-- =====================================================================
-- GymPulse AI · Phase 24 · Community engagement
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase23_community_notifications.sql first.
--
--   community_posts.kind / meta / class_id   check-in, progress, milestone,
--                         recognition, challenge, poll, question and class posts
--   community_comments.author_role           'coach' for gym and staff replies
--   community_challenges, community_challenge_entries   gym challenges
--   community_poll_votes                      one vote per member per poll
--   community_badges                          badges and shared milestones
--   members.buddy_*                           "Find a buddy" profile
--   community_notifications.kind              adds tag, badge and challenge
-- Streaks (weekly, with one free freeze a month) are worked out from check-ins,
-- so they need no table.
-- =====================================================================

begin;

alter table public.community_posts add column if not exists kind     text not null default 'post';
alter table public.community_posts add column if not exists meta     jsonb;
alter table public.community_posts add column if not exists class_id text;
create index if not exists community_posts_class_idx on public.community_posts (gym_id, class_id) where class_id is not null;
alter table public.community_comments add column if not exists author_role text;

alter table public.members add column if not exists buddy_open  boolean not null default false;
alter table public.members add column if not exists buddy_goal  text;
alter table public.members add column if not exists buddy_times text;     -- e.g. "morning,evening"
alter table public.members add column if not exists buddy_note  text;

create table if not exists public.community_challenges (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    title       text not null,
    goal_visits int  not null check (goal_visits between 1 and 100),
    starts_on   date not null,
    ends_on     date not null,
    badge       text not null default '🏆',
    created_at  timestamptz not null default now()
);
create index if not exists community_challenges_gym_idx on public.community_challenges (gym_id, ends_on desc);

create table if not exists public.community_challenge_entries (
    challenge_id uuid not null references public.community_challenges (id) on delete cascade,
    gym_id       uuid not null references public.gyms (id) on delete cascade,
    member_id    uuid not null references public.members (id) on delete cascade,
    joined_at    timestamptz not null default now(),
    completed_at timestamptz,
    primary key (challenge_id, member_id)
);

create table if not exists public.community_poll_votes (
    post_id     uuid not null references public.community_posts (id) on delete cascade,
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    choice      int  not null check (choice between 0 and 3),
    created_at  timestamptz not null default now(),
    primary key (post_id, member_id)
);

create table if not exists public.community_badges (
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    ref         text not null,               -- e.g. challenge:<id>, visits:50, year:1, motw:2026-W45
    label       text not null,
    created_at  timestamptz not null default now(),
    primary key (member_id, ref)
);

do $$
declare t text;
begin
    foreach t in array array['community_challenges', 'community_challenge_entries', 'community_poll_votes',
                             'community_badges'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

alter table public.community_notifications drop constraint if exists community_notifications_kind_check;
alter table public.community_notifications add constraint community_notifications_kind_check
    check (kind in ('message', 'follow', 'tag', 'badge', 'challenge', 'comment'));
alter table public.community_notifications add column if not exists ref text;

commit;

-- Check it worked
select to_regclass('public.community_challenges') is not null as challenges,
       to_regclass('public.community_poll_votes') is not null as polls,
       to_regclass('public.community_badges') is not null as badges,
       exists (select 1 from information_schema.columns where table_name = 'community_posts' and column_name = 'kind') as post_kinds;
