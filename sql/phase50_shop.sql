-- =====================================================================
-- GymPulse AI · Phase 50 · Shop and day passes at the front desk
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds two tables and one function; it deletes nothing.
--
-- The front desk sells water, drinks, supplements, merchandise and day passes, paid by cash, bank transfer
-- or POS card, or added to a member's balance ("on account", shown in Balances owed).
-- A walk-in who buys a day pass and leaves a phone number becomes a prospect, so someone follows up.
--
--   shop_products   what the gym sells: name, type, price, stock (blank = not counted)
--   shop_sales      every sale: items, total, how it was paid, who sold it
--   shop_sell(...)  records a sale in one step: prices from the product list, stock down, balance up,
--                   day-pass walk-in to prospects. Runs as the signed-in staff member, so RLS applies.
-- =====================================================================

begin;

create table if not exists public.shop_products (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    name          text not null,
    category      text not null default 'other'
                  check (category in ('drink', 'supplement', 'food', 'merch', 'day_pass', 'other')),
    price         numeric(12, 2) not null check (price >= 0),
    stock         integer,                       -- null: not counted (services, day passes)
    low_stock_at  integer not null default 5,
    active        boolean not null default true,
    created_at    timestamptz not null default now()
);
create index if not exists shop_products_gym on public.shop_products (gym_id, active, name);

create table if not exists public.shop_sales (
    id            uuid primary key default gen_random_uuid(),
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    member_id     uuid references public.members (id) on delete set null,
    buyer_name    text,
    buyer_phone   text,
    items         jsonb not null,                -- [{"product_id", "name", "qty", "price"}]
    total         numeric(12, 2) not null check (total >= 0),
    method        text not null check (method in ('cash', 'transfer', 'pos', 'account')),
    day_passes    integer not null default 0,
    staff         text,
    voided        boolean not null default false,
    created_at    timestamptz not null default now()
);
create index if not exists shop_sales_gym_at on public.shop_sales (gym_id, created_at desc);

alter table public.shop_products enable row level security;
alter table public.shop_sales enable row level security;
do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'shop_products'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.shop_products for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'public' and tablename = 'shop_sales'
                   and policyname = 'gp_gym_owner') then
        create policy gp_gym_owner on public.shop_sales for all to authenticated
            using (public.gp_owns_gym(gym_id)) with check (public.gp_owns_gym(gym_id));
    end if;
end $$;

-- p_items: [{"product_id": "...", "qty": 2}, ...]. Prices always come from shop_products.
create or replace function public.shop_sell(p_gym_id uuid, p_member_id uuid, p_buyer_name text, p_buyer_phone text,
                                            p_items jsonb, p_method text, p_staff text)
returns json
language plpgsql security invoker set search_path = public as $$
declare
    it        jsonb;
    p         public.shop_products%rowtype;
    q         integer;
    lines     jsonb := '[]'::jsonb;
    v_total   numeric(12, 2) := 0;
    v_passes  integer := 0;
    v_sale    uuid;
    v_phone   text := nullif(regexp_replace(coalesce(p_buyer_phone, ''), '[^0-9+]', '', 'g'), '');
    v_name    text := nullif(trim(coalesce(p_buyer_name, '')), '');
    v_note    text;
begin
    if not public.gp_owns_gym(p_gym_id) then
        return json_build_object('ok', false, 'error', 'not allowed');
    end if;
    if p_method not in ('cash', 'transfer', 'pos', 'account') then
        return json_build_object('ok', false, 'error', 'Choose how they paid');
    end if;
    if p_method = 'account' and p_member_id is null then
        return json_build_object('ok', false, 'error', 'Only a member can add it to their balance');
    end if;
    for it in select * from jsonb_array_elements(coalesce(p_items, '[]'::jsonb)) loop
        q := greatest(coalesce((it ->> 'qty')::integer, 0), 0);
        continue when q = 0;
        p := null;
        select * into p from shop_products where id = (it ->> 'product_id')::uuid and gym_id = p_gym_id;
        if p.id is null then                         -- undo the whole sale, stock included
            raise exception 'A product was removed. Refresh and try again.';
        end if;
        lines := lines || jsonb_build_object('product_id', p.id, 'name', p.name, 'qty', q, 'price', p.price);
        v_total := v_total + p.price * q;
        if p.category = 'day_pass' then v_passes := v_passes + q; end if;
        if p.stock is not null then
            update shop_products set stock = stock - q where id = p.id;
        end if;
    end loop;
    if jsonb_array_length(lines) = 0 then
        return json_build_object('ok', false, 'error', 'Add at least one item');
    end if;

    insert into shop_sales (gym_id, member_id, buyer_name, buyer_phone, items, total, method, day_passes, staff)
    values (p_gym_id, p_member_id, v_name, v_phone, lines, v_total, p_method, v_passes, left(p_staff, 60))
    returning id into v_sale;

    if p_method = 'account' then
        update members set balance_owed = coalesce(balance_owed, 0) + v_total,
                           balance_note = left(trim(both ' ;' from coalesce(balance_note, '') || '; Shop '
                                          || to_char(now() at time zone 'Africa/Lagos', 'DD Mon')), 200)
         where id = p_member_id and gym_id = p_gym_id;
    end if;

    -- A walk-in on a day pass with a phone number: a prospect to follow up (once per number)
    if v_passes > 0 and p_member_id is null and v_phone is not null
       and not exists (select 1 from prospects x where x.gym_id = p_gym_id
                         and regexp_replace(coalesce(x.phone, ''), '[^0-9]', '', 'g')
                             = regexp_replace(v_phone, '[^0-9]', '', 'g')) then
        v_note := 'Bought a day pass on ' || to_char(now() at time zone 'Africa/Lagos', 'DD Mon YYYY') || '.';
        insert into prospects (gym_id, full_name, phone, source, stage, notes, next_follow_up)
        values (p_gym_id, coalesce(v_name, 'Day pass visitor'), v_phone, 'walk_in', 'visited', v_note,
                (now() at time zone 'Africa/Lagos')::date + 1);
    end if;

    return json_build_object('ok', true, 'sale_id', v_sale, 'total', v_total, 'day_passes', v_passes);
end $$;

revoke all on function public.shop_sell(uuid, uuid, text, text, jsonb, text, text) from public;
grant execute on function public.shop_sell(uuid, uuid, text, text, jsonb, text, text) to authenticated;

commit;
