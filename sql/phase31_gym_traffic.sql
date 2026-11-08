-- =====================================================================
-- GymPulse AI · Phase 31 · Accurate "Gym now"
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds a function.
--
-- gp_gym_traffic(gym, visit minutes) returns, for every weekday and half hour, the average number of
-- people INSIDE the gym (not just arriving): each check-in counts as present from its time until the
-- average visit length later. Averages only use days that actually have check-ins, so a new gym isn't
-- diluted by empty weeks. Today isn't averaged in (it's still happening). Repeat scans by the same member
-- on the same day count once.
-- Also returns how many people are inside right now and how many days of data each weekday has.
-- =====================================================================

create or replace function public.gp_gym_traffic(p_gym uuid, p_minutes int default 75)
returns table (dow int, slot int, avg_people numeric, days int, now_inside int)
language sql security definer set search_path = public as $$
    with visits as (                                   -- first check-in per member per local day
        select distinct on (member_id, (checked_in_at at time zone 'Africa/Lagos')::date)
               (checked_in_at at time zone 'Africa/Lagos') as t
          from public.checkins
         where gym_id = p_gym and checked_in_at > now() - interval '56 days' and member_id is not null
           and (checked_in_at at time zone 'Africa/Lagos')::date < (now() at time zone 'Africa/Lagos')::date
         order by member_id, (checked_in_at at time zone 'Africa/Lagos')::date, checked_in_at
    ), present as (                                    -- every half hour each visit covers
        select s from visits,
               generate_series(date_trunc('hour', t) + floor(extract(minute from t) / 30) * interval '30 minutes',
                               t + (greatest(15, least(p_minutes, 300)) * interval '1 minute') - interval '1 second',
                               interval '30 minutes') as s
    ), per_day as (
        select s::date as d, extract(dow from s)::int as dow,
               (extract(hour from s) * 2 + floor(extract(minute from s) / 30))::int as slot, count(*) as n
          from present group by 1, 2, 3
    ), days as (                                       -- days with any check-ins, per weekday
        select extract(dow from t)::int as dow, count(distinct t::date)::int as days from visits group by 1
    )
    select p.dow, p.slot, round(sum(p.n)::numeric / max(dd.days), 2), max(dd.days),
           (select count(distinct member_id)::int from public.checkins
             where gym_id = p_gym and checked_in_at > now() - (greatest(15, least(p_minutes, 300)) * interval '1 minute'))
      from per_day p join days dd on dd.dow = p.dow
     group by p.dow, p.slot
     order by p.dow, p.slot;
$$;
revoke all on function public.gp_gym_traffic(uuid, int) from public;
grant execute on function public.gp_gym_traffic(uuid, int) to service_role;   -- the app's server only

-- Check it worked: should say true.
select exists (select 1 from pg_proc where proname = 'gp_gym_traffic') as traffic;
