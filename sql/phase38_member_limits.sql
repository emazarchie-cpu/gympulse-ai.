-- =====================================================================
-- GymPulse AI · Phase 38 · Member limits enforced by the database
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds two columns, a counting function and two triggers; it deletes nothing.
--
-- A plan's price depends on how many members a gym has, so the limit can't be dodged:
--   * gym_subscriptions.member_limit   the paid plan's member limit (set by GymPulse when a plan is paid for;
--                                      owners can only read this table)
--   * members.archived_at              when a member was archived. Members archived in the last 30 days still
--                                      count when choosing a plan (no "archive 900, buy the small plan, bring
--                                      them back")
--   * gp_billable_members(gym)         active members + members archived in the last 30 days
--   * Adding members or bringing archived members back is refused when it takes a paying gym past its limit:
--       - growing past the limit: 30 days to upgrade, with up to 10% extra room in that time
--       - after the 30 days: nothing above the limit
--     This covers the app, imports, member sign-up links and anyone calling the database directly.
--     GymPulse's own server jobs (service role) are not limited.
-- =====================================================================

begin;

alter table public.gym_subscriptions add column if not exists member_limit integer;
alter table public.gym_subscriptions add column if not exists over_limit_since date;
alter table public.members add column if not exists archived_at timestamptz;

-- ---------------------------------------------------------------- archived_at stamp
create or replace function public.gp_stamp_archived()
returns trigger language plpgsql as $$
begin
    if coalesce(new.archived, false) and not coalesce(old.archived, false) then
        new.archived_at := now();
    elsif not coalesce(new.archived, false) then
        new.archived_at := null;
    end if;
    return new;
end $$;

drop trigger if exists gp_stamp_archived on public.members;
create trigger gp_stamp_archived before update of archived on public.members
    for each row execute function public.gp_stamp_archived();

-- ---------------------------------------------------------------- counting
create or replace function public.gp_billable_members(p_gym uuid)
returns int
language sql stable security definer set search_path = public as $$
    select count(*)::int from public.members
     where gym_id = p_gym
       and (not coalesce(archived, false) or archived_at > now() - interval '30 days');
$$;
revoke all on function public.gp_billable_members(uuid) from public;
grant execute on function public.gp_billable_members(uuid) to authenticated;

-- ---------------------------------------------------------------- the limit itself
create or replace function public.gp_check_member_limit(p_gym uuid)
returns void
language plpgsql security definer set search_path = public as $$
declare
    s       public.gym_subscriptions%rowtype;
    n       int;
    lim     int;
    ceiling int;
    today   date := (now() at time zone 'Africa/Lagos')::date;
begin
    if coalesce(nullif(current_setting('request.jwt.claims', true), '')::jsonb ->> 'role', '') = 'service_role' then
        return;                                          -- GymPulse's own server jobs
    end if;
    select * into s from public.gym_subscriptions where gym_id = p_gym;
    if s.gym_id is null or s.status <> 'active' or coalesce(s.member_limit, 0) <= 0
       or (s.paid_until is not null and s.paid_until < today) then
        return;                                          -- trial, free access, ended or no limit
    end if;
    lim := s.member_limit;
    select count(*) into n from public.members where gym_id = p_gym and not coalesce(archived, false);
    if n <= lim then
        if s.over_limit_since is not null then
            update public.gym_subscriptions set over_limit_since = null where gym_id = p_gym;
        end if;
        return;
    end if;
    if s.over_limit_since is null then
        update public.gym_subscriptions set over_limit_since = today where gym_id = p_gym;
        s.over_limit_since := today;
    end if;
    ceiling := case when s.over_limit_since > today - 30 then lim + greatest(ceil(lim * 0.1)::int, 1) else lim end;
    if n > ceiling then
        raise exception 'GP_MEMBER_LIMIT: Your plan covers up to % members. Upgrade your plan to add more members.', lim
            using errcode = 'P0001';
    end if;
end $$;
revoke all on function public.gp_check_member_limit(uuid) from public;

-- One check per statement, so a batch import is all or nothing.
create or replace function public.gp_members_limit_ins()
returns trigger language plpgsql security definer set search_path = public as $$
declare g uuid;
begin
    for g in select distinct gym_id from new_rows where not coalesce(archived, false) loop
        perform public.gp_check_member_limit(g);
    end loop;
    return null;
end $$;

create or replace function public.gp_members_limit_upd()
returns trigger language plpgsql security definer set search_path = public as $$
declare g uuid;
begin
    for g in select distinct n.gym_id from new_rows n join old_rows o on o.id = n.id
              where not coalesce(n.archived, false) and (coalesce(o.archived, false) or o.gym_id <> n.gym_id) loop
        perform public.gp_check_member_limit(g);
    end loop;
    return null;
end $$;

drop trigger if exists gp_members_limit_ins on public.members;
create trigger gp_members_limit_ins after insert on public.members
    referencing new table as new_rows for each statement execute function public.gp_members_limit_ins();
drop trigger if exists gp_members_limit_upd on public.members;
create trigger gp_members_limit_upd after update on public.members
    referencing old table as old_rows new table as new_rows
    for each statement execute function public.gp_members_limit_upd();

-- ---------------------------------------------------------------- fill in limits for gyms already paying
update public.gym_subscriptions s
   set member_limit = coalesce(
        (select (p ->> 'members')::int
           from public.platform_settings ps, jsonb_array_elements(coalesce(ps.value -> 'plans', '[]'::jsonb)) p
          where ps.key = 'pricing' and lower(p ->> 'name') = lower(split_part(s.plan, ' · ', 1))
            and (p ->> 'members') ~ '^\d+$'
          limit 1),
        case lower(split_part(s.plan, ' · ', 1))
            when 'starter' then 150 when 'growth' then 500 when 'pro' then 1500
            when 'business' then 5000 when 'enterprise' then 20000 end)
 where s.status = 'active' and s.member_limit is null and s.plan is not null;

commit;

-- Check it worked: should say true, true.
select exists (select 1 from information_schema.columns where table_name = 'gym_subscriptions'
                and column_name = 'member_limit') as member_limits,
       exists (select 1 from pg_trigger where tgname = 'gp_members_limit_ins') as limit_trigger;
