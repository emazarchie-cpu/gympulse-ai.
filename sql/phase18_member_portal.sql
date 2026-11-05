-- =====================================================================
-- GymPulse AI · Phase 18 · Member portal
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- Members open their own page at usegympulseai.com/?me=<their private link>:
-- membership and renewal, check-in QR code, visits and rewards, classes,
-- messages with the gym, and their details. No passwords: they ask for a
-- link by email or WhatsApp at usegympulseai.com/?member.
--
--   members.portal_token     the private link (a new one signs out old links)
--   members.portal_sent_at   when a link was last sent (stops repeated sends)
--   members.portal_seen_at   when they last opened their page
--   class_bookings           members booking a place in a class
--   gp_portal_find()         members with a phone number or email (server key only)
-- =====================================================================

begin;

alter table public.members add column if not exists portal_token uuid default gen_random_uuid();
update public.members set portal_token = gen_random_uuid() where portal_token is null;
create unique index if not exists members_portal_token_uidx on public.members (portal_token);
alter table public.members add column if not exists portal_sent_at timestamptz;
alter table public.members add column if not exists portal_seen_at timestamptz;

create table if not exists public.class_bookings (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    class_id    text not null,
    member_id   uuid not null references public.members (id) on delete cascade,
    created_at  timestamptz not null default now()
);
create unique index if not exists class_bookings_once_uidx on public.class_bookings (class_id, member_id);
create index if not exists class_bookings_gym_idx on public.class_bookings (gym_id, class_id);

alter table public.class_bookings enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'class_bookings' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.class_bookings for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

-- Members (in any gym) with this email or phone number. Only the server key can call it.
create or replace function public.gp_portal_find(p_contact text)
returns table (member_id uuid, gym_id uuid)
language plpgsql stable security definer set search_path = public as $$
declare
    v_email text := lower(btrim(coalesce(p_contact, '')));
    v_last10 text := right(regexp_replace(coalesce(p_contact, ''), '\D', '', 'g'), 10);
begin
    if position('@' in v_email) > 1 then
        return query select m.id, m.gym_id from public.members m
            where lower(btrim(m.email)) = v_email and not coalesce(m.archived, false);
    elsif length(v_last10) >= 7 then
        return query select m.id, m.gym_id from public.members m
            where right(regexp_replace(coalesce(m.phone, ''), '\D', '', 'g'), 10) = v_last10
              and not coalesce(m.archived, false);
    end if;
end $$;
revoke all on function public.gp_portal_find(text) from public, anon, authenticated;
grant execute on function public.gp_portal_find(text) to service_role;

commit;

-- Check it worked: every member has a private link
select count(*) as members, count(portal_token) as with_link from public.members;
