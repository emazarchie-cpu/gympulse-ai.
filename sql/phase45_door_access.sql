-- =====================================================================
-- GymPulse AI · Phase 45 · Door access: let paid members in, keep others out
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds two tables, one column and one function; it deletes nothing.
--
-- A reader at the gym door (QR scanner, card or key-fob reader, or a door controller that can call a web
-- address) sends the member's code. door_check() decides:
--   allowed  active membership (end date today or later, plus the gym's grace days), or valid HMO cover
--   denied   unknown code, archived, suspended, frozen today, no plan set, or expired
-- Every attempt is logged in door_events. An allowed entry also counts as a check-in (source 'device'), once
-- per 10 minutes, so attendance and the risk scores update by themselves.
--
--   door_config      one row per gym: on/off, grace days, the door opener link (optional)
--   door_events      every attempt at the door, allowed or denied, with the reason
--   members.door_card   the number on a member's card or fob, when it isn't their member code
--   door_check(p_device_key, p_code, p_door)   called by the door screen and the door-access web link
-- =====================================================================

begin;

alter table public.gyms add column if not exists device_key text;
update public.gyms set device_key = replace(gen_random_uuid()::text, '-', '') where device_key is null;

alter table public.members add column if not exists door_card text;
-- Face or fingerprint at the door: when the member agreed, and when they withdrew (NDPA: sensitive data)
alter table public.members add column if not exists biometric_consent_at timestamptz;
alter table public.members add column if not exists biometric_withdrawn_at timestamptz;
create index if not exists members_door_card on public.members (gym_id, upper(door_card)) where door_card is not null;

create table if not exists public.door_config (
    gym_id        uuid primary key references public.gyms (id) on delete cascade,
    enabled       boolean not null default true,
    grace_days    integer not null default 0 check (grace_days between 0 and 30),
    opener_url    text,
    updated_at    timestamptz not null default now()
);
-- Send the renewal message (WhatsApp/email, with the pay link) to members stopped because their plan expired
alter table public.door_config add column if not exists renew_message boolean not null default true;

create table if not exists public.door_events (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    member_id     uuid references public.members (id) on delete set null,
    code          text,
    door          text,
    allowed       boolean not null,
    reason        text not null,
    at            timestamptz not null default now()
);
create index if not exists door_events_gym_at on public.door_events (gym_id, at desc);

alter table public.door_config enable row level security;
alter table public.door_events enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'door_config'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.door_config for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'door_events'
                   and policyname = 'gp_gym_owner_read') then
        create policy gp_gym_owner_read on public.door_events for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
end $$;

create or replace function public.door_check(p_device_key text, p_code text, p_door text default 'Main door')
returns json
language plpgsql security definer set search_path = public as $$
declare
    g       uuid;
    cfg     public.door_config%rowtype;
    m       public.members%rowtype;
    code    text := upper(regexp_replace(coalesce(p_code, ''), '[^A-Za-z0-9]', '', 'g'));
    today   date := (now() at time zone 'Africa/Lagos')::date;
    ok      boolean := false;
    why     text;
    until   date;
    frozen  boolean;
begin
    if coalesce(p_device_key, '') = '' then
        return json_build_object('ok', false, 'error', 'invalid key');
    end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select * into cfg from door_config where gym_id = g;
    if length(code) < 4 then
        return json_build_object('ok', true, 'allow', false, 'reason', 'Code not recognised');
    end if;
    -- Door access switched off: the link only records visits (check-in devices without a door), no membership check
    if cfg.gym_id is not null and not cfg.enabled then
        select * into m from members
         where gym_id = g and coalesce(archived, false) = false
           and (upper(left(replace(id::text, '-', ''), 8)) = code
                or upper(regexp_replace(coalesce(door_card, ''), '[^A-Za-z0-9]', '', 'g')) = code)
         limit 1;
        if m.id is null then
            return json_build_object('ok', true, 'allow', false, 'reason', 'Code not recognised');
        end if;
        if not exists (select 1 from checkins c where c.member_id = m.id
                         and c.checked_in_at > now() - interval '10 minutes') then
            insert into checkins (gym_id, member_id, source) values (g, m.id, 'device');
        end if;
        return json_build_object('ok', true, 'allow', true, 'reason', 'Checked in', 'name', m.full_name);
    end if;
    -- Leaving: an exit reader always opens (fire safety) and only logs who left
    if lower(coalesce(p_door, '')) like '%exit%' then
        select * into m from members
         where gym_id = g and (upper(left(replace(id::text, '-', ''), 8)) = code
                               or upper(regexp_replace(coalesce(door_card, ''), '[^A-Za-z0-9]', '', 'g')) = code)
         limit 1;
        insert into door_events (gym_id, member_id, code, door, allowed, reason)
        values (g, m.id, left(code, 40), left(p_door, 60), true, 'Left the gym');
        return json_build_object('ok', true, 'allow', true, 'reason', 'Left the gym',
                                 'name', m.full_name, 'opener', cfg.opener_url);
    end if;

    select * into m from members
     where gym_id = g and (upper(left(replace(id::text, '-', ''), 8)) = code
                           or upper(regexp_replace(coalesce(door_card, ''), '[^A-Za-z0-9]', '', 'g')) = code)
     order by archived nulls first
     limit 1;

    if m.id is null then
        why := 'Code not recognised';
    elsif coalesce(m.archived, false) then
        why := 'Not a current member';
    elsif coalesce(m.suspended, false) then
        why := 'Membership suspended';
    else
        select exists (select 1 from member_freezes f where f.member_id = m.id
                         and coalesce(f.status, 'active') not in ('cancelled', 'ended')
                         and today between f.starts_on and coalesce(f.ends_on, f.starts_on))
          into frozen;
        if frozen then
            why := 'Membership on hold (frozen)';
        elsif coalesce(m.hmo_provider, '') <> '' and m.hmo_valid_until >= today then
            ok := true; until := m.hmo_valid_until; why := 'HMO cover active';
        elsif m.membership_end is null then
            why := 'No membership plan recorded';
        elsif m.membership_end + coalesce(cfg.grace_days, 0) >= today then
            ok := true; until := m.membership_end;
            why := case when m.membership_end >= today then 'Membership active' else 'Within grace days' end;
        else
            why := 'Membership expired ' || to_char(m.membership_end, 'DD Mon YYYY');
        end if;
    end if;

    insert into door_events (gym_id, member_id, code, door, allowed, reason)
    values (g, m.id, left(code, 40), left(coalesce(p_door, 'Main door'), 60), ok, why);

    if ok and not exists (select 1 from checkins c where c.member_id = m.id
                            and c.checked_in_at > now() - interval '10 minutes') then
        insert into checkins (gym_id, member_id, source) values (g, m.id, 'device');
    end if;

    return json_build_object('ok', true, 'allow', ok, 'reason', why,
                             'name', case when m.id is null then null else m.full_name end,
                             'until', until, 'opener', case when ok then cfg.opener_url end);
end $$;

revoke all on function public.door_check(text, text, text) from public;
grant execute on function public.door_check(text, text, text) to anon, authenticated, service_role;

-- The gym's name for the door screen (needs the device key)
create or replace function public.door_gym_name(p_device_key text)
returns text
language sql security definer set search_path = public stable as $$
    select business_name from gyms where coalesce(p_device_key, '') <> '' and device_key = p_device_key limit 1;
$$;
revoke all on function public.door_gym_name(text) from public;
grant execute on function public.door_gym_name(text) to anon, authenticated, service_role;

commit;
