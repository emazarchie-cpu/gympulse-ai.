-- =====================================================================
-- GymPulse AI · Phase 20 · Plan limits (members and Archie)
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--   gym_subscriptions.over_limit_since  first day a paying gym had more active
--                                       members than its plan covers (30 days
--                                       to upgrade, then no new members)
--   archie_usage                        Archie questions per gym per month
--   gp_archie_bump()                    adds one question (owner or staff only)
-- =====================================================================

begin;

alter table public.gym_subscriptions add column if not exists over_limit_since date;

create table if not exists public.archie_usage (
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    month       text not null,                      -- e.g. 2026-11
    questions   int  not null default 0,
    updated_at  timestamptz not null default now(),
    primary key (gym_id, month)
);
alter table public.archie_usage enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'archie_usage' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.archie_usage for select to authenticated
            using (public.gp_owns_gym(gym_id));
    end if;
end $$;

create or replace function public.gp_archie_bump(p_gym uuid, p_month text)
returns int
language plpgsql security definer set search_path = public as $$
declare
    v int;
begin
    if not public.gp_owns_gym(p_gym) or p_month !~ '^\d{4}-\d{2}$' then
        return null;
    end if;
    insert into public.archie_usage (gym_id, month, questions) values (p_gym, p_month, 1)
    on conflict (gym_id, month) do update set questions = archie_usage.questions + 1, updated_at = now()
    returning questions into v;
    return v;
end $$;
revoke all on function public.gp_archie_bump(uuid, text) from public, anon;
grant execute on function public.gp_archie_bump(uuid, text) to authenticated, service_role;

commit;

-- Check it worked: the new column and table
select (select count(*) from information_schema.columns where table_name = 'gym_subscriptions'
        and column_name = 'over_limit_since') as over_limit_column,
       to_regclass('public.archie_usage') is not null as archie_usage_table;
