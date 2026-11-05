-- =====================================================================
-- GymPulse AI · Phase 17 · WhatsApp channel
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
--   messages                  every WhatsApp/email message in and out (the
--                             Follow-ups inbox). Adds: wa_to (the number),
--                             meta (what each reply button does), updated_at.
--   members.whatsapp_opt_out  true once a member replies STOP
--   gp_wa_route()             which gym/member a WhatsApp number belongs to
--                             (only the webhook's server key can use it)
-- =====================================================================

begin;

create table if not exists public.messages (
    id           uuid primary key default gen_random_uuid(),
    gym_id       uuid not null references public.gyms (id) on delete cascade,
    member_id    uuid references public.members (id) on delete set null,
    channel      text not null default 'whatsapp',
    direction    text not null default 'out',
    subject      text,
    body         text,
    status       text,
    provider_id  text,
    is_read      boolean not null default false,
    created_at   timestamptz not null default now()
);
alter table public.messages add column if not exists wa_to      text;
alter table public.messages add column if not exists meta       jsonb;
alter table public.messages add column if not exists updated_at timestamptz;
create index if not exists messages_provider_idx on public.messages (provider_id) where provider_id is not null;
create index if not exists messages_wa_to_idx on public.messages (wa_to, created_at desc) where wa_to is not null;
create index if not exists messages_gym_idx on public.messages (gym_id, created_at desc);

alter table public.messages enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'messages' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.messages for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

alter table public.members add column if not exists whatsapp_opt_out boolean not null default false;

-- The gym and member a WhatsApp number is talking to: the gym that messaged
-- that number most recently, otherwise a member with that phone number.
create or replace function public.gp_wa_route(p_digits text)
returns table (gym_id uuid, member_id uuid)
language plpgsql stable security definer set search_path = public as $$
declare
    v_last10 text := right(regexp_replace(coalesce(p_digits, ''), '\D', '', 'g'), 10);
begin
    if length(v_last10) < 7 then
        return;
    end if;
    return query
        select m.gym_id, m.member_id from public.messages m
        where m.channel = 'whatsapp' and m.direction = 'out' and right(m.wa_to, 10) = v_last10
        order by m.created_at desc limit 1;
    if found then
        return;
    end if;
    return query
        select mb.gym_id, mb.id from public.members mb
        where right(regexp_replace(coalesce(mb.phone, ''), '\D', '', 'g'), 10) = v_last10
        order by mb.created_at desc limit 1;
end $$;
revoke all on function public.gp_wa_route(text) from public, anon, authenticated;
grant execute on function public.gp_wa_route(text) to service_role;

commit;

-- Check it worked: 3 new message columns and the opt-out column
select table_name, column_name from information_schema.columns
where table_schema = 'public' and ((table_name = 'messages' and column_name in ('wa_to', 'meta', 'updated_at'))
   or (table_name = 'members' and column_name = 'whatsapp_opt_out'));
