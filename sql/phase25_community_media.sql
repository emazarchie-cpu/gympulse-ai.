-- =====================================================================
-- GymPulse AI · Phase 25 · Video stories and reels
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase24_community_engage.sql first.
--
--   community_stories.meta   video stories: the video link, filter and text on top
-- Reels are community_posts with kind 'reel'; their video link, filter and text
-- are kept in community_posts.meta (added in phase 24). Videos are stored in the
-- "community" storage bucket (up to 50 MB each on Supabase's free plan).
-- =====================================================================

begin;

alter table public.community_stories add column if not exists meta jsonb;

update storage.buckets set file_size_limit = 52428800 where id = 'community' and file_size_limit is null;

commit;

-- Check it worked
select exists (select 1 from information_schema.columns where table_name = 'community_stories'
               and column_name = 'meta') as story_meta;
