-- =====================================================================
-- GymPulse AI · Setup check (read-only: changes nothing)
-- Run in Supabase: SQL Editor -> New query -> paste -> Run.
-- Every row should say true. A false row names the file to run.
-- =====================================================================
with col as (
    select table_name || '.' || column_name as c from information_schema.columns where table_schema = 'public'
), fn as (
    select proname, pronargs from pg_proc where pronamespace = 'public'::regnamespace
)
select step, ok from (values
  ('phase1_foundation  checkins.event_id',            exists (select 1 from col where c = 'checkins.event_id')),
  ('phase1_security    gp_owns_gym()',                exists (select 1 from fn where proname = 'gp_owns_gym')),
  ('phase2_retention   retention_actions.contacted_at', exists (select 1 from col where c = 'retention_actions.contacted_at')),
  ('phase3_revenue     payments',                     to_regclass('public.payments') is not null),
  ('phase4_automation  profiles.settings',            exists (select 1 from col where c = 'profiles.settings')),
  ('phase5_growth      member_freezes',               to_regclass('public.member_freezes') is not null),
  ('phase6_admin       platform_reports',             to_regclass('public.platform_reports') is not null),
  ('phase7_admin_tools admin_audit',                  to_regclass('public.admin_audit') is not null),
  ('phase8_plans       member_activity_plan_check',   exists (select 1 from pg_constraint where conname = 'member_activity_plan_check')),
  ('phase9_loyalty     auto_messages',                to_regclass('public.auto_messages') is not null),
  ('phase10_billing    gym_subscriptions',            to_regclass('public.gym_subscriptions') is not null),
  ('phase11_happiness  member_feedback',              to_regclass('public.member_feedback') is not null),
  ('phase12_invoices   billing_invoices',             to_regclass('public.billing_invoices') is not null),
  ('phase13_staff      gym_staff',                    to_regclass('public.gym_staff') is not null),
  ('phase14_signup     gyms.join_code',               exists (select 1 from col where c = 'gyms.join_code')),
  ('phase15_photo      gp_member_join (8 args)',      exists (select 1 from fn where proname = 'gp_member_join' and pronargs = 8)),
  ('phase16_import     member_imports',               to_regclass('public.member_imports') is not null),
  ('phase17_whatsapp   messages.meta + opt-out',      exists (select 1 from col where c = 'messages.meta')
                                                       and exists (select 1 from col where c = 'members.whatsapp_opt_out')),
  ('phase18_portal     members.portal_token',         exists (select 1 from col where c = 'members.portal_token')),
  ('phase18_portal     class_bookings',               to_regclass('public.class_bookings') is not null),
  ('phase19_code_login members.portal_code_hash',     exists (select 1 from col where c = 'members.portal_code_hash')),
  ('phase20_limits     archie_usage',                 to_regclass('public.archie_usage') is not null),
  ('phase21_community  community_posts',              to_regclass('public.community_posts') is not null),
  ('phase22_social     stories, follows, messages', to_regclass('public.community_dms') is not null
                                                       and to_regclass('public.community_stories') is not null),
  ('phase23_notify     community_notifications',      to_regclass('public.community_notifications') is not null),
  ('phase24_engage     challenges, polls, badges',  to_regclass('public.community_challenges') is not null
                                                       and to_regclass('public.community_badges') is not null),
  ('phase25_media      video stories (meta)',       exists (select 1 from col where c = 'community_stories.meta')),
  ('phase26_profiles   cover, highlights, pinned posts', exists (select 1 from col where c = 'members.community_cover')
                                                    and exists (select 1 from col where c = 'community_stories.highlight')
                                                    and exists (select 1 from col where c = 'community_posts.profile_pinned')),
  ('phase27_privacy    hide me from Training now', exists (select 1 from col where c = 'members.community_hide_now')),
  ('phase28_hmo        HMO check-in, invite links',  exists (select 1 from col where c = 'members.hmo_provider')
                                                    and exists (select 1 from fn where proname = 'gp_hmo_checkin')
                                                    and exists (select 1 from fn where proname = 'gp_referral_link')),
  ('phase29_train      workout log, coach posts, guides', to_regclass('public.workout_sets') is not null
                                                    and to_regclass('public.machine_guides') is not null
                                                    and exists (select 1 from fn where proname = 'gp_gym_busy')),
  ('phase30_train      routines, body tracking, goals', to_regclass('public.workout_routines') is not null
                                                    and to_regclass('public.body_logs') is not null
                                                    and exists (select 1 from col where c = 'members.train_week_goal')),
  ('phase31_traffic    accurate Gym now',          exists (select 1 from fn where proname = 'gp_gym_traffic')),
  ('phase32_predcheck  prediction check',          to_regclass('public.prediction_snapshots') is not null),
  ('phase33_passwords  member email + password',  to_regclass('public.member_passwords') is not null),
  ('phase34_pt         members with a personal trainer', exists (select 1 from col where c = 'members.has_pt')),
  ('phase35_trainers   trainer logins and workspace', to_regclass('public.pt_sessions') is not null
                                                    and exists (select 1 from col where c = 'gym_staff.trainer_id')),
  ('security           RLS on every gym table',       not exists (
        select 1 from pg_class c join pg_namespace n on n.oid = c.relnamespace
        where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity
          and c.relname in ('members','member_activity','checkins','retention_actions','payments','messages',
                            'class_bookings','member_imports','gym_staff','billing_invoices','member_feedback',
                            'community_posts','community_comments','community_likes','community_reports','archie_usage',
                            'community_stories','community_follows','community_dms','community_blocks',
                            'community_notifications','community_challenges','community_challenge_entries',
                            'community_poll_votes','community_badges','prediction_snapshots','member_passwords','pt_sessions','trainer_availability','trainer_reports')))
) as t(step, ok);
