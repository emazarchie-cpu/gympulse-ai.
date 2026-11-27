-- =====================================================================
-- GymPulse AI · Phase 49 · Open door and check in, from the member's profile (staff only)
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one table, one column and three functions; it deletes nothing.
--
-- A staff member taps "Open door and check in" on a member's profile. GymPulse AI saves a door command.
-- The Hikvision bridge at the gym asks for new commands every 2 seconds, opens the door, and reports back.
-- Only then is the member checked in, and the door log shows "Let in by <staff name>".
-- Members can't do this: only the owner and active staff (gp_owns_gym) can add commands.
--
-- When the internet is down, the staff phone page on the gym's Wi-Fi does the same thing with the member
-- list kept on the gym computer, and door_record() logs it with p_by when the internet is back.
-- =====================================================================

begin;

alter table public.door_config add column if not exists bridge_seen_at timestamptz;

create table if not exists public.door_commands (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    member_id     uuid references public.members (id) on delete set null,
    door          text,
    requested_by  text not null,
    created_at    timestamptz not null default now(),
    taken_at      timestamptz,
    done_at       timestamptz,
    ok            boolean,
    note          text
);
create index if not exists door_commands_gym on public.door_commands (gym_id, created_at desc);
alter table public.door_commands enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'door_commands'
                   and policyname = 'gp_gym_staff') then
        create policy gp_gym_staff on public.door_commands for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

-- The bridge collects new commands (less than 20 seconds old) and marks them taken
create or replace function public.door_commands_take(p_device_key text)
returns json
language plpgsql security definer set search_path = public as $$
declare
    g     uuid;
    rows  json;
begin
    if coalesce(p_device_key, '') = '' then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    insert into door_config (gym_id, bridge_seen_at) values (g, now())
        on conflict (gym_id) do update set bridge_seen_at = now();
    with taken as (
        update door_commands c set taken_at = now()
         where c.gym_id = g and c.taken_at is null and c.created_at > now() - interval '20 seconds'
        returning c.id, c.door, c.requested_by, c.member_id
    )
    select coalesce(json_agg(json_build_object('id', t.id, 'door', t.door, 'by', t.requested_by,
                                               'name', m.full_name)), '[]'::json)
      into rows
      from taken t left join members m on m.id = t.member_id;
    return json_build_object('ok', true, 'commands', rows);
end $$;

-- The bridge reports whether the door opened; only then is the member checked in and logged
create or replace function public.door_command_done(p_device_key text, p_id uuid, p_ok boolean, p_note text default null)
returns json
language plpgsql security definer set search_path = public as $$
declare
    g  uuid;
    c  public.door_commands%rowtype;
begin
    if coalesce(p_device_key, '') = '' then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    update door_commands set done_at = now(), ok = coalesce(p_ok, false), note = left(p_note, 200)
     where id = p_id and gym_id = g and done_at is null
    returning * into c;
    if c.id is null then return json_build_object('ok', true, 'logged', false); end if;
    if c.ok then
        insert into door_events (gym_id, member_id, code, door, allowed, reason)
        values (g, c.member_id,
                case when c.member_id is null then 'STAFF' else upper(left(replace(c.member_id::text, '-', ''), 8)) end,
                left(coalesce(c.door, 'Main door'), 60), true,
                case when c.member_id is null then 'Opened by staff: ' else 'Let in by ' end || left(c.requested_by, 40));
        if c.member_id is not null and not exists (select 1 from checkins k where k.member_id = c.member_id
                                                     and k.checked_in_at between now() - interval '10 minutes'
                                                                             and now() + interval '10 minutes') then
            insert into checkins (gym_id, member_id, source) values (g, c.member_id, 'front_desk');
        end if;
    end if;
    return json_build_object('ok', true, 'logged', true);
end $$;

revoke all on function public.door_commands_take(text) from public;
revoke all on function public.door_command_done(text, uuid, boolean, text) from public;
grant execute on function public.door_commands_take(text) to anon, service_role;
grant execute on function public.door_command_done(text, uuid, boolean, text) to anon, service_role;

-- door_record() gains p_by: who let the member in from the staff phone page while the internet was down
drop function if exists public.door_record(text, text, text, boolean, timestamptz);
create or replace function public.door_record(p_device_key text, p_code text, p_door text, p_allowed boolean,
                                              p_at timestamptz default null, p_by text default null)
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
    elsif p_allowed and coalesce(trim(p_by), '') <> '' then
        why := 'Let in by ' || left(trim(p_by), 40);
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
        insert into checkins (gym_id, member_id, source, checked_in_at)
        values (g, m.id, case when coalesce(trim(p_by), '') <> '' then 'front_desk' else 'device' end, v_at);
    end if;
    return json_build_object('ok', true, 'logged', true, 'reason', why);
end $$;

revoke all on function public.door_record(text, text, text, boolean, timestamptz, text) from public;
grant execute on function public.door_record(text, text, text, boolean, timestamptz, text) to service_role;

commit;
