-- =====================================================================
-- GymPulse AI · Security check (read only: changes nothing)
-- Supabase -> SQL Editor -> New query -> paste -> Run.
--
-- One row per table or function, with a plain-language result:
--   OK       safe
--   CHECK    probably fine, but have a look
--   PROBLEM  fix this before real gyms use the app
-- PROBLEM rows are listed first. Send a screenshot of any PROBLEM rows to Claude.
-- =====================================================================

with t as (
    select c.relname as name,
           c.relrowsecurity as rls_on,
           exists (select 1 from information_schema.columns col
                   where col.table_schema = 'public' and col.table_name = c.relname
                     and col.column_name = 'gym_id') as has_gym_id,
           (select count(*) from pg_policies p
             where p.schemaname = 'public' and p.tablename = c.relname) as policies,
           (select count(*) from pg_policies p
             where p.schemaname = 'public' and p.tablename = c.relname
               and ('anon' = any (p.roles) or 'public' = any (p.roles))) as public_policies,
           (select count(*) from pg_policies p
             where p.schemaname = 'public' and p.tablename = c.relname
               and (coalesce(p.qual, '') ilike '%true%' and length(coalesce(p.qual, '')) < 8)) as open_policies,
           (select count(*) from pg_policies p
             where p.schemaname = 'public' and p.tablename = c.relname
               and (coalesce(p.qual, '') || coalesce(p.with_check, '')) ~* '(gp_owns_gym|auth\.uid\(\))') as scoped_policies
    from pg_class c
    where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
),
tables as (
    select
        case
            when not rls_on then 'PROBLEM'
            when open_policies > 0 then 'PROBLEM'
            when public_policies > 0 and name not in ('demo_bookings') then 'PROBLEM'
            when has_gym_id and policies > 0 and scoped_policies = 0 then 'PROBLEM'
            when policies = 0 and name not in ('platform_reports', 'platform_gym_flags', 'admin_audit', 'demo_bookings') then 'CHECK'
            else 'OK'
        end as result,
        'table' as kind,
        name,
        case
            when not rls_on then 'Row-level security is OFF: any signed-in user could read every gym''s rows. '
                                 || 'Fix: alter table public.' || name || ' enable row level security; then add a gym policy.'
            when open_policies > 0 then 'A policy lets everyone through (using true). Replace it with a gym-only policy.'
            when public_policies > 0 and name not in ('demo_bookings') then 'A policy is open to signed-out visitors (anon/public). Check it is meant to be.'
            when has_gym_id and policies > 0 and scoped_policies = 0 then 'Has gym data but no policy limits it to the owner''s gym (gp_owns_gym / auth.uid()).'
            when policies = 0 and name in ('platform_reports', 'platform_gym_flags', 'admin_audit') then 'Locked: only the Admin page (service key) can use it. Correct.'
            when policies = 0 and name = 'demo_bookings' then 'Locked: bookings go through safe functions only. Correct.'
            when policies = 0 then 'Security is on but there are no policies, so the app cannot read it. Fine if unused.'
            else 'Security on, limited to each gym''s own data (' || policies || ' polic' || case when policies = 1 then 'y' else 'ies' end || ').'
        end as what_it_means
    from t
),
funcs as (
    select
        case when p.proname in ('gp_owns_gym', 'email_unsubscribe', 'book_demo', 'demo_taken_slots',
                                'cancel_demo', 'public_trainer', 'device_checkin', 'handle_new_user',
                                'rls_auto_enable') then 'OK' else 'CHECK' end as result,
        'function' as kind,
        p.proname as name,
        case when p.proname in ('gp_owns_gym', 'email_unsubscribe', 'book_demo', 'demo_taken_slots',
                                'cancel_demo', 'public_trainer', 'device_checkin', 'handle_new_user',
                                'rls_auto_enable')
             then case p.proname
                      when 'device_checkin' then 'Check-in kiosk: needs the gym''s secret device key. Correct.'
                      when 'handle_new_user' then 'Creates a profile when someone signs up. Correct.'
                      when 'rls_auto_enable' then 'Supabase helper that switches security on for new tables. Correct.'
                      else 'Known GymPulse function that runs with extra rights on purpose.' end
             else 'Runs with extra rights (security definer). Make sure it only returns what it should.' end
    from pg_proc p
    where p.pronamespace = 'public'::regnamespace and p.prosecdef
),
storage as (
    select case when b.public and b.id <> 'email-assets' then 'CHECK' else 'OK' end,
           'storage bucket', b.id,
           case when b.id = 'email-assets' then 'Public on purpose: logos and banners must show in inboxes. Uploads are limited to each gym''s folder.'
                when b.public then 'Public bucket: anyone with a link can see its files. Make sure nothing private is stored here.'
                else 'Private bucket.' end
    from storage.buckets b
)
select result, kind, name, what_it_means
from (
    select * from tables
    union all select * from funcs
    union all select * from storage
) as everything
order by case result when 'PROBLEM' then 0 when 'CHECK' then 1 else 2 end, kind, name;
