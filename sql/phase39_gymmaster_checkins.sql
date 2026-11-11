-- =====================================================================
-- GymPulse AI · Phase 39 · Automatic check-ins from GymMaster (webhook)
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds a table and two functions; it deletes nothing.
--
-- While a gym runs GymPulse AI side by side with GymMaster, GymMaster's Webhook Manager
-- (Settings -> Integrations) can send each member check-in to GymPulse AI as it happens:
--   GymMaster -> supabase/functions/gymmaster-webhook -> gp_gm_checkin() -> checkins (source 'device')
--
--   gym_integrations     one row per gym: the secret in the gym's webhook link, counters, and the last
--                        message received (GymMaster doesn't publish its format, so the first real message
--                        is kept for checking)
--   gp_json_leaves(j)    every key/value in a JSON message, however deeply nested
--   gp_gm_checkin(...)   checks the secret, finds the member (GymMaster member ID, then email, phone,
--                        name), saves the visit once (no repeat within 10 minutes). Only the webhook
--                        (service role) can call it.
-- =====================================================================

begin;

create table if not exists public.gym_integrations (
    gym_id          uuid not null references public.gyms (id) on delete cascade,
    kind            text not null default 'gymmaster',
    secret          text not null,
    created_at      timestamptz not null default now(),
    last_event_at   timestamptz,
    events          integer not null default 0,
    matched         integer not null default 0,
    last_result     text,
    last_payload    jsonb,
    last_unmatched  jsonb,
    primary key (gym_id, kind)
);
alter table public.gym_integrations enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'gym_integrations'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.gym_integrations for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

-- ---------------------------------------------------------------- every key/value in a JSON message
create or replace function public.gp_json_leaves(j jsonb)
returns table (k text, v text)
language sql immutable as $$
    with recursive walk(key, val) as (
        select null::text, j
        union all
        select coalesce(e.key, w.key), e.value
          from walk w
          cross join lateral (
              select o.key, o.value from jsonb_each(case when jsonb_typeof(w.val) = 'object' then w.val
                                                          else '{}'::jsonb end) o
              union all
              select null, a.value from jsonb_array_elements(case when jsonb_typeof(w.val) = 'array' then w.val
                                                                  else '[]'::jsonb end) a
          ) e
    )
    select lower(regexp_replace(key, '[^A-Za-z0-9]', '', 'g')), val #>> '{}'
      from walk
     where key is not null and jsonb_typeof(val) in ('string', 'number', 'boolean');
$$;

-- ---------------------------------------------------------------- one check-in from GymMaster
create or replace function public.gp_gm_checkin(p_gym uuid, p_secret text, p_payload jsonb)
returns text
language plpgsql security definer set search_path = public as $$
declare
    integ  public.gym_integrations%rowtype;
    ev     text;
    mno    text;
    em     text;
    ph     text;
    fn     text;
    ln     text;
    nm     text;
    tm     text;
    at     timestamptz;
    mid    uuid;
    result text;
begin
    select * into integ from public.gym_integrations where gym_id = p_gym and kind = 'gymmaster';
    if integ.gym_id is null or integ.secret is distinct from p_secret then
        return 'bad_key';
    end if;

    select v into ev  from public.gp_json_leaves(p_payload) where k in ('event', 'eventtype', 'type', 'action', 'webhookevent', 'topic') limit 1;
    select v into mno from public.gp_json_leaves(p_payload) where k in ('memberid', 'membernumber', 'memberno', 'membershipnumber',
                                                                       'clientid', 'customerid', 'id', 'barcode', 'cardnumber', 'keyfob')
                                                              and v <> '' order by case k when 'memberid' then 0 when 'membernumber' then 1
                                                                                         when 'id' then 9 else 5 end limit 1;
    select v into em  from public.gp_json_leaves(p_payload) where (k like '%email%' or v ~ '^[^@\s]+@[^@\s]+\.[^@\s]+$') and v like '%@%' limit 1;
    select v into ph  from public.gp_json_leaves(p_payload) where k in ('phone', 'mobile', 'mobilephone', 'cellphone', 'cell', 'phonenumber',
                                                                       'mobilenumber', 'phonecell') and v <> '' limit 1;
    select v into fn  from public.gp_json_leaves(p_payload) where k in ('firstname', 'givenname', 'first') limit 1;
    select v into ln  from public.gp_json_leaves(p_payload) where k in ('surname', 'lastname', 'familyname', 'last') limit 1;
    select v into nm  from public.gp_json_leaves(p_payload) where k in ('name', 'fullname', 'membername') limit 1;
    select v into tm  from public.gp_json_leaves(p_payload) where k in ('checkintime', 'checkin', 'checkindatetime', 'datetime', 'timestamp',
                                                                       'time', 'visittime', 'visitdate', 'createdat', 'created', 'date')
                                                              and v <> '' limit 1;

    if ev is not null and ev !~* '(check|visit|attend|access|entry|door|swipe|scan)' then
        result := 'ignored: ' || left(ev, 40);                 -- e.g. "member updated": not a visit
    else
        -- the member: GymMaster member ID first (saved as member_no on import), then email, phone, name
        if mno is not null then
            select id into mid from public.members
             where gym_id = p_gym and not coalesce(archived, false) and lower(trim(member_no)) = lower(trim(mno)) limit 1;
        end if;
        if mid is null and em is not null then
            select id into mid from public.members
             where gym_id = p_gym and not coalesce(archived, false) and lower(email) = lower(trim(em)) limit 1;
        end if;
        if mid is null and length(regexp_replace(coalesce(ph, ''), '\D', '', 'g')) >= 7 then
            select id into mid from public.members
             where gym_id = p_gym and not coalesce(archived, false)
               and right(regexp_replace(coalesce(phone, ''), '\D', '', 'g'), 10) = right(regexp_replace(ph, '\D', '', 'g'), 10)
             limit 1;
        end if;
        if mid is null then
            nm := coalesce(nullif(trim(coalesce(fn, '') || ' ' || coalesce(ln, '')), ''), nm);
            if nm is not null and (select count(*) from public.members where gym_id = p_gym and not coalesce(archived, false)
                                   and lower(trim(full_name)) = lower(trim(nm))) = 1 then
                select id into mid from public.members
                 where gym_id = p_gym and not coalesce(archived, false) and lower(trim(full_name)) = lower(trim(nm));
            end if;
        end if;

        -- when: the time in the message, else now (epoch seconds or milliseconds also understood)
        begin
            if tm ~ '^\d{12,13}$' then at := to_timestamp(tm::bigint / 1000.0);
            elsif tm ~ '^\d{9,10}$' then at := to_timestamp(tm::bigint);
            elsif tm is not null then at := tm::timestamptz;
            end if;
        exception when others then at := null;
        end;
        if at is null or at > now() + interval '1 hour' or at < now() - interval '7 days' then
            at := now();
        end if;

        if mid is null then
            result := 'no_match';
        elsif exists (select 1 from public.checkins where gym_id = p_gym and member_id = mid
                       and checked_in_at between at - interval '10 minutes' and at + interval '10 minutes') then
            result := 'duplicate';
        else
            insert into public.checkins (gym_id, member_id, checked_in_at, source) values (p_gym, mid, at, 'device');
            result := 'saved';
        end if;
    end if;

    update public.gym_integrations
       set events = events + 1,
           matched = matched + case when result in ('saved', 'duplicate') then 1 else 0 end,
           last_event_at = now(), last_result = result, last_payload = p_payload,
           last_unmatched = case when result = 'no_match' then p_payload else last_unmatched end
     where gym_id = p_gym and kind = 'gymmaster';
    return result;
end $$;

revoke all on function public.gp_gm_checkin(uuid, text, jsonb) from public;
revoke all on function public.gp_gm_checkin(uuid, text, jsonb) from anon, authenticated;

commit;

-- Check it worked: should say true.
select to_regclass('public.gym_integrations') is not null as gymmaster_checkins;
