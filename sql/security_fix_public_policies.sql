-- =====================================================================
-- GymPulse AI · Security fix: remove old policies open to signed-out visitors
-- Supabase -> SQL Editor -> New query -> paste -> Run.  Safe to run again.
--
-- The security check found older policies on 6 gym tables that apply to
-- "public" (everyone, including signed-out visitors). Each table also has
-- the correct gym-only policy (gp_gym_owner), so the old ones are removed.
-- The app doesn't need them: the check-in kiosk (device_checkin) and the
-- public trainer page (public_trainer) use their own safe functions.
--
-- Step 1 makes sure every table has the gym-only policy.
-- Step 2 removes any policy on these tables that applies to public or anon.
-- The final query lists the policies left. Each should be gp_gym_owner,
-- for "authenticated".
-- =====================================================================

begin;

do $$
declare
    t text;
    p record;
begin
    foreach t in array array['checkins', 'classes', 'member_activity', 'reminder_log',
                             'retention_actions', 'trainers', 'members', 'messages', 'payments']
    loop
        if to_regclass('public.' || t) is null then
            continue;
        end if;
        execute format('alter table public.%I enable row level security', t);

        -- 1. the gym-only policy every gym table should have
        if not exists (select 1 from pg_policies where schemaname = 'public'
                       and tablename = t and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;

        -- 2. remove anything open to everyone or to signed-out visitors
        for p in
            select policyname from pg_policies
            where schemaname = 'public' and tablename = t
              and ('public' = any (roles) or 'anon' = any (roles))
        loop
            execute format('drop policy %I on public.%I', p.policyname, t);
            raise notice 'Removed policy "%" on %', p.policyname, t;
        end loop;
    end loop;
end $$;

commit;

-- What's left (expect gp_gym_owner / authenticated on each table)
select tablename as table_name, policyname as policy, array_to_string(roles, ', ') as applies_to, cmd as allows
from pg_policies
where schemaname = 'public'
  and tablename in ('checkins', 'classes', 'member_activity', 'reminder_log', 'retention_actions',
                    'trainers', 'members', 'messages', 'payments')
order by tablename, policyname;
