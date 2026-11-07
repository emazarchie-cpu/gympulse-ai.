-- =====================================================================
-- GymPulse AI · Phase 28 · Automatic referrals and HMO members
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds columns and functions; it deletes nothing.
--
-- Referrals
--   Every member gets a personal invite link (?join=<gym code>&ref=<member code>).
--   When a friend signs up through it, gp_referral_link records the referral
--   (status "joined", source "link") against the member who invited them.
--
-- HMO members (companies or health plans paying for staff gym access)
--   members.hmo_provider / hmo_id / hmo_employer / hmo_valid_until
--   gp_hmo_info + gp_hmo_checkin power the HMO QR check-in page
--   (?hmo=<gym code>): the member types their HMO ID or phone once, then gets
--   a personal one-tap check-in link. Check-ins are saved with source "hmo".
-- =====================================================================

begin;

alter table public.referrals add column if not exists source text;            -- 'link' = recorded automatically

alter table public.members add column if not exists hmo_provider    text;
alter table public.members add column if not exists hmo_id          text;
alter table public.members add column if not exists hmo_employer    text;
alter table public.members add column if not exists hmo_valid_until date;
create index if not exists members_gym_hmo_idx on public.members (gym_id, lower(hmo_id)) where hmo_id is not null;

-- Allow the new check-in source. NOT VALID: older rows are left as they are.
alter table public.checkins drop constraint if exists checkins_source_chk;
alter table public.checkins add constraint checkins_source_chk
    check (source in ('front_desk', 'scan', 'kiosk', 'device', 'import', 'unknown', 'hmo', 'portal', 'self'))
    not valid;

-- ---------------------------------------------------------------- referrals
create or replace function public.gp_referral_link(p_code text, p_ref text, p_name text, p_phone text,
                                                   p_email text default null)
returns text
language plpgsql security definer set search_path = public as $$
declare
    g        public.gyms%rowtype;
    referrer uuid;
    friend   uuid;
    digits   text := right(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), 10);
begin
    select * into g from public.gyms where join_code = p_code limit 1;
    if g.id is null or coalesce(p_ref, '') = '' then
        return 'skipped';
    end if;
    select id into referrer from public.members
     where gym_id = g.id and upper(left(replace(id::text, '-', ''), 8)) = upper(left(p_ref, 8))
       and coalesce(archived, false) = false
     limit 1;
    if referrer is null then
        return 'skipped';
    end if;
    select id into friend from public.members
     where gym_id = g.id and id <> referrer
       and ((length(digits) >= 7 and right(regexp_replace(coalesce(phone, ''), '\D', '', 'g'), 10) = digits)
            or (coalesce(p_email, '') <> '' and lower(email) = lower(p_email)))
     order by created_at desc limit 1;
    if friend is null then
        return 'skipped';
    end if;
    if exists (select 1 from public.referrals where gym_id = g.id and friend_member_id = friend) then
        return 'exists';
    end if;
    insert into public.referrals (gym_id, referrer_id, friend_name, friend_phone, friend_member_id, status,
                                  joined_on, source)
    values (g.id, referrer, left(coalesce(nullif(trim(p_name), ''), 'Friend'), 80), nullif(trim(p_phone), ''),
            friend, 'joined', current_date, 'link');
    return 'recorded';
end $$;

revoke all on function public.gp_referral_link(text, text, text, text, text) from public;
grant execute on function public.gp_referral_link(text, text, text, text, text) to anon, authenticated;

-- ---------------------------------------------------------------- HMO check-in
create or replace function public.gp_hmo_info(p_code text)
returns table (business_name text)
language sql security definer set search_path = public as $$
    select coalesce(p.business_name, g.business_name)
      from public.gyms g left join public.profiles p on p.id = g.owner_id
     where g.join_code = p_code
     limit 1;
$$;

create or replace function public.gp_hmo_checkin(p_code text, p_key text default null, p_token text default null)
returns table (status text, first_name text, provider text, token text, visits_month int)
language plpgsql security definer set search_path = public as $$
declare
    g      public.gyms%rowtype;
    m      public.members%rowtype;
    k      text := lower(trim(coalesce(p_key, '')));
    digits text := right(regexp_replace(coalesce(p_key, ''), '\D', '', 'g'), 10);
    n      int;
begin
    select * into g from public.gyms where join_code = p_code limit 1;
    if g.id is null then
        return query select 'no_gym'::text, null::text, null::text, null::text, 0;
        return;
    end if;
    if coalesce(p_token, '') <> '' then
        select * into m from public.members
         where gym_id = g.id and portal_token::text = p_token and hmo_provider is not null
           and coalesce(archived, false) = false
         limit 1;
    elsif k <> '' then
        select * into m from public.members
         where gym_id = g.id and hmo_provider is not null and coalesce(archived, false) = false
           and (lower(trim(hmo_id)) = k
                or (length(digits) >= 7 and right(regexp_replace(coalesce(phone, ''), '\D', '', 'g'), 10) = digits))
         order by created_at desc limit 1;
    end if;
    if m.id is null then
        return query select 'not_found'::text, null::text, null::text, null::text, 0;
        return;
    end if;
    if m.hmo_valid_until is not null and m.hmo_valid_until < current_date then
        return query select 'expired'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text, 0;
        return;
    end if;
    if not exists (select 1 from public.checkins
                    where gym_id = g.id and member_id = m.id and checked_in_at > now() - interval '3 hours') then
        insert into public.checkins (gym_id, member_id, checked_in_at, source) values (g.id, m.id, now(), 'hmo');
        select count(*) into n from public.checkins
         where gym_id = g.id and member_id = m.id and checked_in_at >= date_trunc('month', now());
        return query select 'ok'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text, n;
    else
        select count(*) into n from public.checkins
         where gym_id = g.id and member_id = m.id and checked_in_at >= date_trunc('month', now());
        return query select 'already'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text, n;
    end if;
end $$;

revoke all on function public.gp_hmo_info(text) from public;
revoke all on function public.gp_hmo_checkin(text, text, text) from public;
grant execute on function public.gp_hmo_info(text) to anon, authenticated;
grant execute on function public.gp_hmo_checkin(text, text, text) to anon, authenticated;

commit;

-- Check it worked: should list 4 HMO columns and 3 functions.
select column_name from information_schema.columns
 where table_schema = 'public' and table_name = 'members' and column_name like 'hmo%';
select proname from pg_proc where proname in ('gp_referral_link', 'gp_hmo_info', 'gp_hmo_checkin');
