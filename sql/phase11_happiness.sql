-- =====================================================================
-- GymPulse AI · Phase 11 · Member happiness check
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--  member_feedback        one answer per member per round: a score from
--                         1 (not happy) to 4 (love it) and an optional comment
--  gp_member_feedback()   lets a member answer from the email link without
--                         signing in. It only works with the member's own
--                         private link code (the same one used to unsubscribe),
--                         and it can only save that member's answer.
-- =====================================================================

begin;

create table if not exists public.member_feedback (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    member_id   uuid not null references public.members (id) on delete cascade,
    round       text not null,                       -- e.g. 2026-Q4 or 2026-11
    score       smallint not null check (score between 1 and 4),
    comment     text,
    created_at  timestamptz not null default now(),
    updated_at  timestamptz not null default now()
);
create unique index if not exists member_feedback_once_uidx on public.member_feedback (member_id, round);
create index if not exists member_feedback_gym_idx on public.member_feedback (gym_id, created_at desc);

alter table public.member_feedback enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'member_feedback' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.member_feedback for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

-- Save (or change) a member's answer from the email link. Returns the gym's
-- name so the page can thank the member (the app finds the owner itself).
drop function if exists public.gp_member_feedback(uuid, text, int, text);
create or replace function public.gp_member_feedback(p_token uuid, p_round text, p_score int,
                                                     p_comment text default null)
returns table (business_name text, gym_id uuid, member_name text, first_answer boolean)
language plpgsql security definer set search_path = public as $$
declare
    m record;
    existed boolean;
begin
    if p_score is null or p_score < 1 or p_score > 4 or p_round !~ '^[0-9]{4}-(Q[1-4]|[0-9]{2})$' then
        return;
    end if;
    select mm.id, mm.gym_id, mm.full_name into m from public.members mm where mm.unsub_token = p_token;
    if not found then
        return;
    end if;
    select exists (select 1 from public.member_feedback f where f.member_id = m.id and f.round = p_round) into existed;
    insert into public.member_feedback (gym_id, member_id, round, score, comment)
    values (m.gym_id, m.id, p_round, p_score, nullif(left(coalesce(p_comment, ''), 1000), ''))
    on conflict (member_id, round) do update
        set score = excluded.score,
            comment = coalesce(excluded.comment, public.member_feedback.comment),
            updated_at = now();
    return query select g.business_name, g.id, m.full_name, not existed
                 from public.gyms g where g.id = m.gym_id;
end $$;
revoke all on function public.gp_member_feedback(uuid, text, int, text) from public;
grant execute on function public.gp_member_feedback(uuid, text, int, text) to anon, authenticated;

commit;

-- Check it worked: rls_on = true, 1 policy
select c.relname as table_name, c.relrowsecurity as rls_on,
       (select count(*) from pg_policies p where p.tablename = c.relname) as policies
from pg_class c
where c.relnamespace = 'public'::regnamespace and c.relname = 'member_feedback';
