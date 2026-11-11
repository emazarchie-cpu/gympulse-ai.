-- =====================================================================
-- GymPulse AI · Phase 37 · HMO plans, weekly session limits, codes and claims
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds columns and two tables; it deletes nothing.
--
-- How HMO gym access works in Nigeria, and what this adds for it:
--   * Gym access depends on the enrollee's plan tier and is capped at a number of sessions a week
--       members.hmo_plan, members.hmo_weekly_limit; hmo_providers.weekly_limit (the HMO's usual cap)
--   * Some HMOs ask the gym for a verification / authorisation code for each visit
--       hmo_providers.needs_code, checkins.hmo_code
--   * The HMO pays the gym per visit or a fixed amount per member each month, after a monthly claim
--       hmo_providers.pay_model + rate; hmo_claims tracks each month's claim: sent, paid, queried
--   * The QR check-in now stops a visit over the weekly cap (the HMO would refuse to pay for it)
--     and asks for the code when the HMO needs one.
-- =====================================================================

begin;

alter table public.members add column if not exists hmo_plan         text;
alter table public.members add column if not exists hmo_weekly_limit integer;
alter table public.checkins add column if not exists hmo_code text;

create table if not exists public.hmo_providers (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    name          text not null,
    pay_model     text not null default 'per_visit' check (pay_model in ('per_visit', 'per_member')),
    rate          numeric(12, 2),
    weekly_limit  integer,
    needs_code    boolean not null default false,
    claims_email  text,
    claim_days    integer not null default 30,
    created_at    timestamptz not null default now(),
    unique (gym_id, name)
);

create table if not exists public.hmo_claims (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    provider      text not null,
    month         date not null,
    visits        integer not null default 0,
    members       integer not null default 0,
    amount        numeric(12, 2) not null default 0,
    status        text not null default 'sent' check (status in ('sent', 'paid', 'part_paid', 'queried')),
    sent_on       date,
    paid_on       date,
    amount_paid   numeric(12, 2),
    note          text,
    created_at    timestamptz not null default now(),
    unique (gym_id, provider, month)
);

do $$
declare t text;
begin
    foreach t in array array['hmo_providers', 'hmo_claims'] loop
        execute format('alter table public.%I enable row level security', t);
        if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = t
                       and policyname = 'gp_gym_owner') then
            execute format('create policy gp_gym_owner on public.%I for all to authenticated '
                           'using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id))', t);
        end if;
    end loop;
end $$;

-- ---------------------------------------------------------------- QR check-in with limits and codes
drop function if exists public.gp_hmo_checkin(text, text, text);
drop function if exists public.gp_hmo_checkin(text, text, text, text);

create or replace function public.gp_hmo_checkin(p_code text, p_key text default null, p_token text default null,
                                                 p_hmo_code text default null)
returns table (status text, first_name text, provider text, token text, visits_month int,
               visits_week int, week_limit int)
language plpgsql security definer set search_path = public as $$
declare
    g      public.gyms%rowtype;
    m      public.members%rowtype;
    hp     public.hmo_providers%rowtype;
    k      text := lower(trim(coalesce(p_key, '')));
    digits text := right(regexp_replace(coalesce(p_key, ''), '\D', '', 'g'), 10);
    code   text := nullif(left(trim(coalesce(p_hmo_code, '')), 40), '');
    lagos  timestamp := now() at time zone 'Africa/Lagos';
    wk     timestamptz := date_trunc('week', lagos) at time zone 'Africa/Lagos';
    mo     timestamptz := date_trunc('month', lagos) at time zone 'Africa/Lagos';
    lim    int;
    n      int;
    w      int;
    seen   boolean;     -- already trained today: a second visit doesn't use up another session
begin
    select * into g from public.gyms where join_code = p_code limit 1;
    if g.id is null then
        return query select 'no_gym'::text, null::text, null::text, null::text, 0, 0, null::int;
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
        return query select 'not_found'::text, null::text, null::text, null::text, 0, 0, null::int;
        return;
    end if;
    select * into hp from public.hmo_providers where gym_id = g.id and name = m.hmo_provider limit 1;
    lim := coalesce(m.hmo_weekly_limit, hp.weekly_limit);
    select count(distinct (checked_in_at at time zone 'Africa/Lagos')::date) into w from public.checkins
     where gym_id = g.id and member_id = m.id and checked_in_at >= wk;
    select count(*) into n from public.checkins
     where gym_id = g.id and member_id = m.id and checked_in_at >= mo;
    seen := exists (select 1 from public.checkins where gym_id = g.id and member_id = m.id
                     and (checked_in_at at time zone 'Africa/Lagos')::date = (lagos)::date);
    if m.hmo_valid_until is not null and m.hmo_valid_until < (lagos)::date then
        return query select 'expired'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text,
                            n, w, lim;
        return;
    end if;
    if exists (select 1 from public.checkins
                where gym_id = g.id and member_id = m.id and checked_in_at > now() - interval '3 hours') then
        return query select 'already'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text,
                            n, w, lim;
        return;
    end if;
    if lim is not null and lim > 0 and w >= lim and not seen then
        return query select 'limit'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text,
                            n, w, lim;
        return;
    end if;
    if coalesce(hp.needs_code, false) and code is null then
        return query select 'need_code'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text,
                            n, w, lim;
        return;
    end if;
    insert into public.checkins (gym_id, member_id, checked_in_at, source, hmo_code)
    values (g.id, m.id, now(), 'hmo', code);
    return query select 'ok'::text, split_part(m.full_name, ' ', 1), m.hmo_provider, m.portal_token::text,
                        n + 1, w + case when seen then 0 else 1 end, lim;
end $$;

revoke all on function public.gp_hmo_checkin(text, text, text, text) from public;
grant execute on function public.gp_hmo_checkin(text, text, text, text) to anon, authenticated;

commit;

-- Check it worked: should say true, true.
select exists (select 1 from information_schema.columns where table_name = 'members'
                and column_name = 'hmo_weekly_limit') as hmo_limits,
       to_regclass('public.hmo_claims') is not null as hmo_claims;
