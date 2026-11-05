-- =====================================================================
-- GymPulse AI · Phase 13 · Staff logins (owner and staff access)
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  gym_staff            people the owner added in Owner -> Team & access.
--                       Each has their own login and works in the owner's gym.
--  gp_is_gym_owner()    true only for the gym's owner (owner-only data)
--  gp_owns_gym()        now true for the owner AND active staff, so staff can
--                       work with members, check-ins, payments and plays
--  gp_staff_context()   on sign-in, tells the app which gym a staff login
--                       belongs to (and whether their access is switched on)
--
-- Owner-only in the database: invoices and receipts, the staff list.
-- Owner-only in the app: Owner page (business insights, team, reports),
-- Archie, Subscription, gym settings and email branding.
-- =====================================================================

begin;

create table if not exists public.gym_staff (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    user_id       uuid unique references auth.users (id) on delete cascade,
    email         text not null,
    full_name     text,
    role          text not null default 'staff' check (role in ('staff')),
    status        text not null default 'active' check (status in ('active', 'disabled')),
    created_at    timestamptz not null default now(),
    last_seen_at  timestamptz
);
create unique index if not exists gym_staff_email_uidx on public.gym_staff (gym_id, lower(email));
alter table public.gym_staff enable row level security;

create or replace function public.gp_is_gym_owner(gid uuid)
returns boolean language sql stable security definer set search_path = public as $$
    select exists (select 1 from public.gyms g where g.id = gid and g.owner_id = auth.uid());
$$;
revoke all on function public.gp_is_gym_owner(uuid) from public;
grant execute on function public.gp_is_gym_owner(uuid) to authenticated;

-- Owner or active staff (used by every gym-data policy). Keeps the existing
-- parameter name, because Postgres won't rename it in place.
do $$
declare pname text;
begin
    select coalesce(p.proargnames[1], 'gid') into pname
    from pg_proc p where p.proname = 'gp_owns_gym' and p.pronamespace = 'public'::regnamespace limit 1;
    execute format($f$
        create or replace function public.gp_owns_gym(%I uuid)
        returns boolean language sql stable security definer set search_path = public as $b$
            select exists (select 1 from public.gyms g where g.id = $1 and g.owner_id = auth.uid())
                or exists (select 1 from public.gym_staff s
                           where s.gym_id = $1 and s.user_id = auth.uid() and s.status = 'active');
        $b$ $f$, coalesce(pname, 'gid'));
end $$;
revoke all on function public.gp_owns_gym(uuid) from public;
grant execute on function public.gp_owns_gym(uuid) to authenticated;

do $$
begin
    -- the staff list: the owner sees their team, each staff member sees their own row
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'gym_staff' and policyname = 'gp_owner_reads_staff') then
        create policy gp_owner_reads_staff on public.gym_staff for select to authenticated
            using (public.gp_is_gym_owner(gym_id) or user_id = auth.uid());
    end if;
    -- staff can read (not change) the gym they work in
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'gyms' and policyname = 'gp_staff_reads_gym') then
        create policy gp_staff_reads_gym on public.gyms for select to authenticated
            using (exists (select 1 from public.gym_staff s
                           where s.gym_id = gyms.id and s.user_id = auth.uid() and s.status = 'active'));
    end if;
    -- receipts and invoices: owner only
    if to_regclass('public.billing_invoices') is not null then
        drop policy if exists gp_owner_reads_invoices on public.billing_invoices;
        create policy gp_owner_reads_invoices on public.billing_invoices for select to authenticated
            using (public.gp_is_gym_owner(gym_id));
    end if;
end $$;

-- Which gym does this staff login work in? Returns nothing for owners.
create or replace function public.gp_staff_context()
returns json language sql stable security definer set search_path = public as $$
    select json_build_object(
        'staff', json_build_object('id', s.id, 'full_name', s.full_name, 'email', s.email, 'status', s.status),
        'gym', row_to_json(g),
        'owner', json_build_object('id', p.id, 'full_name', p.full_name, 'business_name', p.business_name,
                                   'settings', p.settings))
    from public.gym_staff s
    join public.gyms g on g.id = s.gym_id
    left join public.profiles p on p.id = g.owner_id
    where s.user_id = auth.uid()
    limit 1;
$$;
revoke all on function public.gp_staff_context() from public;
grant execute on function public.gp_staff_context() to authenticated;

commit;

-- Check it worked: gym_staff with rls_on = true and 1 policy
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname = 'gym_staff';
