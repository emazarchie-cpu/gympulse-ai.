-- =====================================================================
-- GymPulse AI · Phase 16 · Smoother member import
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again.
--
-- When a gym brings its members over from GymMaster, Mindbody, Excel etc.:
--   members.plan_name     the plan's name in the old software ("Gold 12 Months")
--   members.member_no     the member ID / card number in the old software
--   members.member_since  when they first joined (from the old software)
--   members.import_batch  which import created the member (so it can be undone)
--   member_imports        a log of imports: when, from where, and what came in
-- The import works without this file; this adds the plan names, member numbers
-- and the "Undo import" button.
-- =====================================================================

begin;

alter table public.members add column if not exists plan_name    text;
alter table public.members add column if not exists member_no    text;
alter table public.members add column if not exists member_since date;
alter table public.members add column if not exists import_batch uuid;
create index if not exists members_import_batch_idx on public.members (import_batch)
    where import_batch is not null;

create table if not exists public.member_imports (
    id          uuid primary key default gen_random_uuid(),
    gym_id      uuid not null references public.gyms (id) on delete cascade,
    source      text,
    file_name   text,
    summary     jsonb not null default '{}'::jsonb,
    created_by  uuid default auth.uid(),
    created_at  timestamptz not null default now(),
    undone_at   timestamptz
);
create index if not exists member_imports_gym_idx on public.member_imports (gym_id, created_at desc);

alter table public.member_imports enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public'
                   and tablename = 'member_imports' and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.member_imports for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

commit;

-- Check it worked: 4 member columns and the imports table
select column_name from information_schema.columns
where table_schema = 'public' and table_name = 'members'
  and column_name in ('plan_name', 'member_no', 'member_since', 'import_batch');
select count(*) as imports_logged from public.member_imports;
