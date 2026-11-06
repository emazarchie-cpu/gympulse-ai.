-- =====================================================================
-- GymPulse AI · Phase 26 · Community profiles: cover photo, highlights, pins
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase25_community_media.sql first.
--
--   members.community_cover          the cover photo at the top of a profile
--   community_stories.highlight      the highlight a story is saved in (e.g. "PRs")
--   community_posts.profile_pinned   pinned to the top of the member's own profile
-- =====================================================================

begin;

alter table public.members add column if not exists community_cover text;
alter table public.community_stories add column if not exists highlight text;
alter table public.community_posts add column if not exists profile_pinned boolean not null default false;
create index if not exists community_stories_highlight_idx on public.community_stories (member_id, highlight)
    where highlight is not null;

commit;

-- Check it worked: 3 rows
select table_name, column_name from information_schema.columns
where table_schema = 'public' and column_name in ('community_cover', 'highlight', 'profile_pinned');
