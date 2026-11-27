-- =====================================================================
-- GymPulse AI · Phase 48 · Staff open the door from their phone on the gym's Wi-Fi
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one function; it deletes nothing.
--
-- The Hikvision bridge (door_bridge/) serves an "Open door" page on the gym's Wi-Fi. Staff enter their PIN
-- and the door opens through the local network, with or without internet. Each opening is sent here when
-- the internet is up, and shows in Door access -> At the door today as "Opened by staff".
--
--   door_staff_open(p_device_key, p_staff, p_door, p_at)
-- =====================================================================

begin;

create or replace function public.door_staff_open(p_device_key text, p_staff text, p_door text,
                                                  p_at timestamptz default null)
returns json
language plpgsql security definer set search_path = public as $$
declare
    g        uuid;
    v_at     timestamptz := least(coalesce(p_at, now()), now());
    v_staff  text := left(coalesce(nullif(trim(p_staff), ''), 'Staff'), 40);
    v_door   text := left(coalesce(nullif(p_door, ''), 'Main door'), 60);
begin
    if coalesce(p_device_key, '') = '' then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    select id into g from gyms where device_key = p_device_key;
    if g is null then return json_build_object('ok', false, 'error', 'invalid key'); end if;
    if v_at < now() - interval '14 days' then
        return json_build_object('ok', true, 'logged', false, 'why', 'too old');
    end if;
    if exists (select 1 from door_events e where e.gym_id = g and e.code = 'STAFF'
                 and e.reason = 'Opened by staff: ' || v_staff
                 and e.at between v_at - interval '2 seconds' and v_at + interval '2 seconds') then
        return json_build_object('ok', true, 'logged', false, 'why', 'already logged');
    end if;
    insert into door_events (gym_id, member_id, code, door, allowed, reason, at)
    values (g, null, 'STAFF', v_door, true, 'Opened by staff: ' || v_staff, v_at);
    return json_build_object('ok', true, 'logged', true);
end $$;

revoke all on function public.door_staff_open(text, text, text, timestamptz) from public;
grant execute on function public.door_staff_open(text, text, text, timestamptz) to service_role;

commit;
