-- =====================================================================
-- GymPulse AI · Phase 47 · Door access that keeps working when the internet drops
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds two functions; it deletes nothing.
--
-- The Hikvision bridge (door_bridge/) copies each member's paid-until date onto the door terminal every few
-- minutes, so the terminal decides by itself, even with no internet. It then sends back every entry the
-- terminal recorded, including ones it had to hold while the internet was down.
--
--   door_roster(p_device_key)                         every current member: code, card, name, paid until
--   door_record(p_device_key, p_code, p_door, p_allowed, p_at)   logs one entry the terminal already decided
-- The rules are the same as door_check() in phase 45.
-- =====================================================================

begin;

create or replace function public.door_roster(p_device_key text)
returns json
language plpgsql security definer set search_path = public stable as $$
declare
    g      uuid;
    cfg    public.door_config%rowtype;
    today  date := (now() at time zone 'Africa/Lagos')::date;
    rows   json;
begin
    if coalesce(p_device_key, '') = '' then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select * into cfg from door_config where gym_id = g;

    select coalesce(json_agg(r order by r.code), '[]'::json) into rows from (
        select upper(left(replace(m.id::text, '-', ''), 8)) as code,
               nullif(upper(regexp_replace(coalesce(m.door_card, ''), '[^A-Za-z0-9]', '', 'g')), '') as card,
               left(coalesce(m.full_name, ''), 32) as name,
               case
                   -- Door access off: the terminal only records visits, so every current member is let in
                   when cfg.gym_id is not null and not cfg.enabled then date '2037-12-31'
                   when coalesce(m.suspended, false) then null
                   when exists (select 1 from member_freezes f where f.member_id = m.id
                                  and coalesce(f.status, 'active') not in ('cancelled', 'ended')
                                  and today between f.starts_on and coalesce(f.ends_on, f.starts_on)) then null
                   else greatest(case when coalesce(m.hmo_provider, '') <> '' then m.hmo_valid_until end,
                                 m.membership_end + coalesce(cfg.grace_days, 0))
               end as until
          from members m
         where m.gym_id = g and coalesce(m.archived, false) = false
    ) r;
    return json_build_object('ok', true, 'today', today, 'members', rows);
end $$;

revoke all on function public.door_roster(text) from public;
grant execute on function public.door_roster(text) to service_role;

create or replace function public.door_record(p_device_key text, p_code text, p_door text, p_allowed boolean,
                                              p_at timestamptz default null)
returns json
language plpgsql security definer set search_path = public as $$
declare
    g        uuid;
    cfg      public.door_config%rowtype;
    m        public.members%rowtype;
    v_code   text := upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'));
    v_door   text := left(coalesce(nullif(p_door, ''), 'Main door'), 60);
    v_at     timestamptz := least(coalesce(p_at, now()), now());
    v_exit   boolean;
    v_day    date;
    why      text;
    frozen   boolean;
begin
    if coalesce(p_device_key, '') = '' then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    if length(v_code) < 4 then return json_build_object('ok', true, 'logged', false); end if;
    if v_at < now() - interval '14 days' then
        return json_build_object('ok', true, 'logged', false, 'why', 'too old');
    end if;
    v_day := (v_at at time zone 'Africa/Lagos')::date;
    v_exit := lower(v_door) like '%exit%';
    select * into cfg from door_config where gym_id = g;

    select * into m from members mm
     where mm.gym_id = g and (upper(left(replace(mm.id::text, '-', ''), 8)) = v_code
                              or upper(regexp_replace(coalesce(mm.door_card, ''), '[^A-Za-z0-9]', '', 'g')) = v_code)
     order by mm.archived nulls first
     limit 1;

    -- The bridge may send the same entry twice (it resends after a lost connection)
    if exists (select 1 from door_events e where e.gym_id = g and e.code = left(v_code, 40)
                 and e.at between v_at - interval '2 seconds' and v_at + interval '2 seconds') then
        return json_build_object('ok', true, 'logged', false, 'why', 'already logged');
    end if;

    if v_exit then
        why := 'Left the gym';
    elsif m.id is null then
        why := 'Code not recognised';
    elsif p_allowed then
        why := case when cfg.gym_id is not null and not cfg.enabled then 'Checked in'
                    when m.membership_end is not null and m.membership_end < v_day then 'Within grace days'
                    else 'Membership active' end;
    elsif coalesce(m.archived, false) then
        why := 'Not a current member';
    elsif coalesce(m.suspended, false) then
        why := 'Membership suspended';
    else
        select exists (select 1 from member_freezes f where f.member_id = m.id
                         and coalesce(f.status, 'active') not in ('cancelled', 'ended')
                         and v_day between f.starts_on and coalesce(f.ends_on, f.starts_on))
          into frozen;
        if frozen then
            why := 'Membership on hold (frozen)';
        elsif m.membership_end is null and coalesce(m.hmo_provider, '') = '' then
            why := 'No membership plan recorded';
        elsif m.membership_end is not null and m.membership_end + coalesce(cfg.grace_days, 0) < v_day then
            why := 'Membership expired ' || to_char(m.membership_end, 'DD Mon YYYY');
        else
            why := 'Refused by the terminal';
        end if;
    end if;

    insert into door_events (gym_id, member_id, code, door, allowed, reason, at)
    values (g, m.id, left(v_code, 40), v_door, coalesce(p_allowed, false) or v_exit, why, v_at);

    if p_allowed and m.id is not null and not v_exit
       and not exists (select 1 from checkins c where c.member_id = m.id
                         and c.checked_in_at between v_at - interval '10 minutes' and v_at + interval '10 minutes') then
        insert into checkins (gym_id, member_id, source, checked_in_at) values (g, m.id, 'device', v_at);
    end if;
    return json_build_object('ok', true, 'logged', true, 'reason', why);
end $$;

revoke all on function public.door_record(text, text, text, boolean, timestamptz) from public;
grant execute on function public.door_record(text, text, text, boolean, timestamptz) to service_role;

commit;
