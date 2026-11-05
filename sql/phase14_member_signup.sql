-- =====================================================================
-- GymPulse AI · Phase 14 · Member sign-up link
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- Each gym gets a private sign-up link (usegympulseai.com/?join=<code>) that
-- it can share on WhatsApp or as a QR code at the front desk. Members fill in
-- their own details and appear in the gym's member list, so a gym can go
-- from 0 to all its members without typing them in.
--
--  gyms.join_code       the link's private code (owner can make a new one)
--  gyms.join_enabled    the owner can switch the link off
--  members.joined_via   'link' for members who signed up themselves
--  gp_join_info()       the gym's name for the sign-up page (no member data)
--  gp_member_join()     adds one member through the link; nothing else
-- =====================================================================

begin;

alter table public.gyms add column if not exists join_code text;
alter table public.gyms add column if not exists join_enabled boolean not null default true;
update public.gyms set join_code = substr(md5(random()::text || id::text), 1, 10) where join_code is null;
alter table public.gyms alter column join_code set default substr(md5(random()::text), 1, 10);
create unique index if not exists gyms_join_code_uidx on public.gyms (join_code);

alter table public.members add column if not exists joined_via text;

-- The gym's name for the sign-up page. Returns nothing for an unknown or switched-off link.
create or replace function public.gp_join_info(p_code text)
returns table (business_name text)
language sql stable security definer set search_path = public as $$
    select g.business_name from public.gyms g
    where g.join_code = p_code and g.join_enabled;
$$;
revoke all on function public.gp_join_info(text) from public;
grant execute on function public.gp_join_info(text) to anon, authenticated;

-- Add one member through the link. Requires consent, a name and a phone or email.
-- If the phone or email is already a member of this gym, nothing is added ('exists').
drop function if exists public.gp_member_join(text, text, text, text, text, int, boolean);
create or replace function public.gp_member_join(p_code text, p_name text, p_phone text, p_email text,
                                                 p_goal text, p_age int, p_consent boolean)
returns table (business_name text, status text)
language plpgsql security definer set search_path = public as $$
declare
    g record;
    v_name text := left(btrim(coalesce(p_name, '')), 120);
    v_phone text := left(btrim(coalesce(p_phone, '')), 30);
    v_email text := lower(left(btrim(coalesce(p_email, '')), 160));
    v_digits text := right(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), 10);
    v_age int := case when p_age between 10 and 110 then p_age end;
    v_weight numeric := null;
    v_height numeric := null;
begin
    select gg.id, gg.business_name into g from public.gyms gg where gg.join_code = p_code and gg.join_enabled;
    if not found or not coalesce(p_consent, false) or length(v_name) < 2
       or (length(v_digits) < 7 and v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$') then
        return;
    end if;
    if v_email !~ '^[^@\s]+@[^@\s]+\.[^@\s]+$' then v_email := null; end if;
    if exists (select 1 from public.members m where m.gym_id = g.id
               and ((v_email is not null and lower(m.email) = v_email)
                    or (length(v_digits) >= 7 and right(regexp_replace(coalesce(m.phone, ''), '\D', '', 'g'), 10) = v_digits))) then
        return query select g.business_name, 'exists'::text;
        return;
    end if;
    -- Some databases require these columns; members can update them later with the gym.
    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'members'
               and column_name = 'age' and is_nullable = 'NO') and v_age is null then v_age := 30; end if;
    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'members'
               and column_name = 'weight_kg' and is_nullable = 'NO') then v_weight := 70; end if;
    if exists (select 1 from information_schema.columns where table_schema = 'public' and table_name = 'members'
               and column_name = 'height_cm' and is_nullable = 'NO') then v_height := 170; end if;
    insert into public.members (gym_id, full_name, phone, email, fitness_goal, age, weight_kg, height_cm, joined_via)
    values (g.id, v_name, nullif(v_phone, ''), v_email, nullif(left(coalesce(p_goal, ''), 60), ''),
            v_age, v_weight, v_height, 'link');
    return query select g.business_name, 'created'::text;
end $$;
revoke all on function public.gp_member_join(text, text, text, text, text, int, boolean) from public;
grant execute on function public.gp_member_join(text, text, text, text, text, int, boolean) to anon, authenticated;

commit;

-- Check it worked: every gym has a sign-up code
select business_name, join_code, join_enabled from public.gyms order by business_name;
