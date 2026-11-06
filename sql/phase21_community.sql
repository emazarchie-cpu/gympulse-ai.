-- =====================================================================
-- GymPulse AI · Phase 21 · Member community
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase18_member_portal.sql first.
--
-- A private feed for each gym inside the member app: members post text and
-- photos, like and comment; the gym posts announcements and moderates.
--   community_posts / community_comments / community_likes / community_reports
--   members.community_agreed_at   when the member accepted the community rules
--   members.community_blocked     the gym stopped this member posting
--   gyms.community_enabled        the gym can switch the community off
--   storage bucket "community"    post photos (resized by the app)
-- Members never read these tables directly: the app reads them on the server,
-- only for the signed-in member's own gym.
-- =====================================================================

begin;

alter table public.members add column if not exists community_agreed_at timestamptz;
alter table public.members add column if not exists community_blocked boolean not null default false;
alter table public.gyms add column if not exists community_enabled boolean not null default true;

create table if not exists public.community_posts (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete cascade,     -- null = posted by the gym
    author_name text not null,
    body        text not null default '',
    photo       text,
    pinned      boolean not null default false,
    hidden      boolean not null default false,
    created_at  timestamptz not null default now()
);
create index if not exists community_posts_gym_idx on public.community_posts (gym_id, created_at desc);

create table if not exists public.community_comments (
    id          uuid primary key default gen_random_uuid(),
    post_id     uuid not null references public.community_posts (id) on delete cascade,
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid references public.members (id) on delete cascade,
    author_name text not null,
    body        text not null,
    hidden      boolean not null default false,
    created_at  timestamptz not null default now()
);
create index if not exists community_comments_post_idx on public.community_comments (post_id, created_at);

create table if not exists public.community_likes (
    post_id     uuid not null references public.community_posts (id) on delete cascade,
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    created_at  timestamptz not null default now(),
    primary key (post_id, member_id)
);

create table if not exists public.community_reports (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    post_id     uuid references public.community_posts (id) on delete cascade,
    comment_id  uuid references public.community_comments (id) on delete cascade,
    member_id   uuid references public.members (id) on delete set null,
    reason      text,
    resolved    boolean not null default false,
    created_at  timestamptz not null default now()
);
create index if not exists community_reports_gym_idx on public.community_reports (gym_id, resolved);

do $$
declare t text;
begin
    foreach t in array array['community_posts', 'community_comments', 'community_likes', 'community_reports'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

-- Photo storage (public read by unguessable file name; uploads only with the server key)
insert into storage.buckets (id, name, public)
values ('community', 'community', true)
on conflict (id) do nothing;

commit;

-- Check it worked: 4 tables and the bucket
select to_regclass('public.community_posts') is not null as posts,
       to_regclass('public.community_comments') is not null as comments,
       to_regclass('public.community_likes') is not null as likes,
       to_regclass('public.community_reports') is not null as reports,
       exists (select 1 from storage.buckets where id = 'community') as photo_bucket;
