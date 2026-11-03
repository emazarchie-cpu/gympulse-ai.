-- =====================================================================
-- GymPulse AI · Phase 1 · Gym-level data isolation (Row Level Security)
--
-- READ THIS FIRST. Run STEP 1 on its own and look at the results before
-- running STEP 2.
--
-- What it does: makes Supabase itself refuse to show or change a record
-- unless it belongs to a gym owned by the signed-in user. The app already
-- limits every query to your gym; this is the server-side lock behind it.
--
-- What it does not affect:
--   * the webhook receiver (it uses the service role key, which bypasses RLS)
--   * security-definer functions such as the device check-in and public
--     trainer page functions
--
-- STEP 2 only ADDS policies. If your tables already have policies, those stay
-- in place (Postgres allows a row when any policy allows it).
-- =====================================================================


-- ---------------------------------------------------------------------
-- STEP 1 · Audit (read-only). Run this block alone.
-- ---------------------------------------------------------------------
-- a) Is RLS switched on for each table?  rls_on should be true everywhere.
select c.relname as table_name, c.relrowsecurity as rls_on
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relkind = 'r'
  and c.relname in ('gyms', 'profiles', 'members', 'member_activity', 'retention_actions',
                    'checkins', 'classes', 'trainers', 'messages', 'reminder_log')
order by 1;

-- b) Which policies exist today?
select tablename, policyname, cmd, roles, qual, with_check
from pg_policies where schemaname = 'public' order by tablename, policyname;

-- c) Records whose gym_id points at no gym (should all be 0).
select 'members' as t, count(*) from public.members m
  where not exists (select 1 from public.gyms g where g.id = m.gym_id)
union all select 'member_activity', count(*) from public.member_activity a
  where not exists (select 1 from public.gyms g where g.id = a.gym_id)
union all select 'checkins', count(*) from public.checkins c
  where not exists (select 1 from public.gyms g where g.id = c.gym_id)
union all select 'retention_actions', count(*) from public.retention_actions r
  where not exists (select 1 from public.gyms g where g.id = r.gym_id);

-- d) Check-ins or activity rows whose member belongs to a different gym (should be 0).
select 'checkins' as t, count(*) from public.checkins c join public.members m on m.id = c.member_id
  where m.gym_id <> c.gym_id
union all select 'member_activity', count(*) from public.member_activity a
  join public.members m on m.id = a.member_id where m.gym_id <> a.gym_id
union all select 'retention_actions', count(*) from public.retention_actions r
  join public.members m on m.id = r.member_id where m.gym_id <> r.gym_id;


-- ---------------------------------------------------------------------
-- STEP 2 · Lock each table to its gym's owner. Run after reviewing STEP 1.
-- ---------------------------------------------------------------------
begin;

create or replace function public.gp_owns_gym(gid uuid)
returns boolean language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.gyms g where g.id = gid and g.owner_id = auth.uid());
$$;
revoke all on function public.gp_owns_gym(uuid) from public;
grant execute on function public.gp_owns_gym(uuid) to authenticated;

do $$
declare t text;
begin
    foreach t in array array['members', 'member_activity', 'retention_actions', 'checkins',
                             'classes', 'trainers', 'messages', 'reminder_log'] loop
        if to_regclass('public.' || t) is null then
            continue;
        end if;
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public'
                       and tablename = t and policyname = 'gp_gym_owner') then
            execute format(
                'create policy gp_gym_owner on public.%I for all to authenticated '
                'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;

    alter table public.gyms enable row level security;
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'gyms' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.gyms for all to authenticated
            using (owner_id = auth.uid()) with check (owner_id = auth.uid());
    end if;

    alter table public.profiles enable row level security;
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'profiles' and policyname = 'gp_own_profile') then
        create policy gp_own_profile on public.profiles for all to authenticated
            using (id = auth.uid()) with check (id = auth.uid());
    end if;
end $$;

commit;

-- Re-run STEP 1 (a) and (b): rls_on should now be true for every table, and
-- each table should list a gp_gym_owner (or gp_own_profile) policy.
--
-- To undo STEP 2 for one table:   drop policy gp_gym_owner on public.<table>;
