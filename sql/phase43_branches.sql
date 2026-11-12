-- GymPulse AI · phase 43: one login, several branches
-- Until now the gyms table allowed one gym per owner (constraint unique_gym_owner), so "Add a branch" failed.
-- This lifts that rule, keeps a fast lookup by owner, and caps branches at 50 per owner (the same limit as the app).
-- Safe to run more than once.

-- 1. Drop the one-gym-per-owner rule, whether it was made as a constraint or as a unique index
alter table public.gyms drop constraint if exists unique_gym_owner;
drop index if exists public.unique_gym_owner;

do $$
declare r record;
begin
    -- any other unique constraint or index on gyms(owner_id) alone
    for r in
        select c.conname from pg_constraint c
        where c.conrelid = 'public.gyms'::regclass and c.contype = 'u'
          and c.conkey = array[(select attnum from pg_attribute
                                where attrelid = 'public.gyms'::regclass and attname = 'owner_id')]::int2[]
    loop
        execute format('alter table public.gyms drop constraint %I', r.conname);
    end loop;
    for r in
        select i.indexrelid::regclass::text as idx from pg_index i
        where i.indrelid = 'public.gyms'::regclass and i.indisunique and not i.indisprimary
          and i.indkey::int2[] = array[(select attnum from pg_attribute
                                       where attrelid = 'public.gyms'::regclass and attname = 'owner_id')]::int2[]
    loop
        execute format('drop index if exists %s', r.idx);
    end loop;
end $$;

-- 2. Keep looking up an owner's gyms fast
create index if not exists gyms_owner_id_idx on public.gyms (owner_id, created_at);

-- 3. At most 50 branches per owner
create or replace function public.gp_branch_cap()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    if (select count(*) from public.gyms where owner_id = new.owner_id) >= 50 then
        raise exception 'GP_BRANCH_LIMIT: you can have up to 50 branches' using errcode = 'P0001';
    end if;
    return new;
end $$;
revoke all on function public.gp_branch_cap() from public;

drop trigger if exists gp_branch_cap on public.gyms;
create trigger gp_branch_cap before insert on public.gyms
    for each row execute function public.gp_branch_cap();
