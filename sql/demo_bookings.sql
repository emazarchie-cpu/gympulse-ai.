-- =====================================================================
-- GymPulse AI · Demo bookings from the website
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- Visitors book a demo without signing in. They can't read the table: the
-- three functions below are the only way in. They book a slot, see which
-- slots are taken (times only, no names), or cancel with their private link.
-- A unique index makes double-booking a slot impossible.
-- See your bookings in Supabase: Table Editor -> demo_bookings.
-- =====================================================================

begin;

create table if not exists public.demo_bookings (
    id            uuid primary key default gen_random_uuid(),
    full_name     text not null,
    email         text not null,
    phone         text,
    gym_name      text not null,
    members_count text,
    notes         text,
    starts_at     timestamptz not null,
    duration_min  int not null default 30,
    status        text not null default 'booked'
                  check (status in ('booked', 'cancelled', 'done', 'no_show')),
    cancel_token  uuid not null default gen_random_uuid(),
    created_at    timestamptz not null default now()
);

create unique index if not exists demo_bookings_one_per_slot
    on public.demo_bookings (starts_at) where status = 'booked';
create index if not exists demo_bookings_starts_idx on public.demo_bookings (starts_at);

alter table public.demo_bookings enable row level security;
-- No policies on purpose: nobody can read or change rows directly.

create or replace function public.book_demo(
    p_name text, p_email text, p_phone text, p_gym text, p_members text,
    p_notes text, p_starts_at timestamptz, p_duration int default 30)
returns table (booking_id uuid, cancel_token uuid, starts_at timestamptz)
language plpgsql security definer set search_path = public as $$
declare r public.demo_bookings;
begin
    if coalesce(trim(p_name), '') = '' or coalesce(trim(p_gym), '') = '' then
        raise exception 'missing_fields';
    end if;
    if p_email !~* '^[^@\s]+@[^@\s]+\.[^@\s]+$' then
        raise exception 'bad_email';
    end if;
    if p_starts_at < now() + interval '1 hour' or p_starts_at > now() + interval '90 days' then
        raise exception 'bad_time';
    end if;
    if (select count(*) from public.demo_bookings b
        where lower(b.email) = lower(trim(p_email)) and b.status = 'booked'
          and b.starts_at > now()) >= 2 then
        raise exception 'too_many';
    end if;
    begin
        insert into public.demo_bookings (full_name, email, phone, gym_name, members_count,
                                          notes, starts_at, duration_min)
        values (left(trim(p_name), 120), lower(left(trim(p_email), 200)), left(trim(p_phone), 40),
                left(trim(p_gym), 160), left(trim(p_members), 40), left(trim(p_notes), 1000),
                p_starts_at, greatest(15, least(coalesce(p_duration, 30), 90)))
        returning * into r;
    exception when unique_violation then
        raise exception 'slot_taken';
    end;
    return query select r.id, r.cancel_token, r.starts_at;
end $$;

create or replace function public.demo_taken_slots(p_from timestamptz, p_to timestamptz)
returns setof timestamptz
language sql stable security definer set search_path = public as $$
    select b.starts_at from public.demo_bookings b
    where b.status = 'booked' and b.starts_at >= p_from and b.starts_at < p_to;
$$;

create or replace function public.cancel_demo(p_token uuid)
returns table (starts_at timestamptz, full_name text, gym_name text, email text)
language sql security definer set search_path = public as $$
    update public.demo_bookings b set status = 'cancelled'
    where b.cancel_token = p_token and b.status = 'booked' and b.starts_at > now()
    returning b.starts_at, b.full_name, b.gym_name, b.email;
$$;

revoke all on function public.book_demo(text, text, text, text, text, text, timestamptz, int) from public;
revoke all on function public.demo_taken_slots(timestamptz, timestamptz) from public;
revoke all on function public.cancel_demo(uuid) from public;
grant execute on function public.book_demo(text, text, text, text, text, text, timestamptz, int) to anon, authenticated;
grant execute on function public.demo_taken_slots(timestamptz, timestamptz) to anon, authenticated;
grant execute on function public.cancel_demo(uuid) to anon, authenticated;

commit;

-- Check it worked: should list the three functions.
select proname from pg_proc where proname in ('book_demo', 'demo_taken_slots', 'cancel_demo');
