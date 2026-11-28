-- =====================================================================
-- GymPulse AI · Phase 55 · Order and pay by QR code (self-checkout)
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It changes one check, adds three columns and one function; it deletes nothing.
--
-- Customers scan the gym's shop QR code, choose items and pay through Paystack (transfer, card or USSD) to the
-- gym's own bank account. When Paystack confirms, the server records the sale by itself with an order number;
-- the front desk sees it in Online orders and taps Handed over.
--
--   shop_sales.method        adds 'online' (paid through Paystack)
--   shop_sales.pay_ref       the Paystack reference: each payment is recorded once
--   shop_sales.order_no      a short number per day ("Order 12") the customer shows at the desk
--   shop_sales.handed_over_at  when staff gave them their items
--   shop_record_online(...)  server only (service role): prices from the product list, stock down, day-pass
--                            walk-in to prospects; refuses a payment smaller than the order
-- =====================================================================

begin;

alter table public.shop_sales drop constraint if exists shop_sales_method_check;
alter table public.shop_sales add constraint shop_sales_method_check
    check (method in ('cash', 'transfer', 'pos', 'account', 'online'));
alter table public.shop_sales add column if not exists pay_ref text;
alter table public.shop_sales add column if not exists order_no integer;
alter table public.shop_sales add column if not exists handed_over_at timestamptz;
create unique index if not exists shop_sales_pay_ref on public.shop_sales (pay_ref) where pay_ref is not null;

create or replace function public.shop_record_online(p_gym_id uuid, p_items jsonb, p_buyer_name text,
                                                     p_buyer_phone text, p_ref text, p_paid numeric)
returns json
language plpgsql security definer set search_path = public as $$
declare
    it        jsonb;
    p         public.shop_products%rowtype;
    q         integer;
    lines     jsonb := '[]'::jsonb;
    v_total   numeric(12, 2) := 0;
    v_passes  integer := 0;
    v_no      integer;
    v_old     public.shop_sales%rowtype;
    v_phone   text := nullif(regexp_replace(coalesce(p_buyer_phone, ''), '[^0-9+]', '', 'g'), '');
    v_name    text := nullif(left(trim(coalesce(p_buyer_name, '')), 80), '');
    v_day     date := (now() at time zone 'Africa/Lagos')::date;
begin
    if coalesce(p_ref, '') = '' then return json_build_object('ok', false, 'error', 'no reference'); end if;
    select * into v_old from shop_sales where pay_ref = p_ref;
    if v_old.id is not null then                                      -- already recorded: same answer again
        return json_build_object('ok', true, 'order_no', v_old.order_no, 'total', v_old.total, 'items', v_old.items,
                                 'already', true);
    end if;
    for it in select * from jsonb_array_elements(coalesce(p_items, '[]'::jsonb)) loop
        q := least(greatest(coalesce((it ->> 'qty')::integer, 0), 0), 50);
        continue when q = 0;
        p := null;
        select * into p from shop_products where id = (it ->> 'product_id')::uuid and gym_id = p_gym_id;
        continue when p.id is null;
        lines := lines || jsonb_build_object('product_id', p.id, 'name', p.name, 'qty', q, 'price', p.price);
        v_total := v_total + p.price * q;
        if p.category = 'day_pass' then v_passes := v_passes + q; end if;
    end loop;
    if jsonb_array_length(lines) = 0 then return json_build_object('ok', false, 'error', 'empty order'); end if;
    if coalesce(p_paid, 0) + 0.5 < v_total then
        return json_build_object('ok', false, 'error', 'underpaid', 'total', v_total);
    end if;
    for it in select * from jsonb_array_elements(lines) loop
        update shop_products set stock = stock - (it ->> 'qty')::integer
         where id = (it ->> 'product_id')::uuid and stock is not null;
    end loop;
    perform pg_advisory_xact_lock(hashtext(p_gym_id::text || v_day::text));   -- order numbers in turn
    select coalesce(max(order_no), 0) + 1 into v_no from shop_sales
     where gym_id = p_gym_id and method = 'online'
       and (created_at at time zone 'Africa/Lagos')::date = v_day;
    insert into shop_sales (gym_id, buyer_name, buyer_phone, items, total, method, day_passes, staff, pay_ref, order_no)
    values (p_gym_id, v_name, v_phone, lines, v_total, 'online', v_passes, 'Self-checkout', p_ref, v_no);
    if v_passes > 0 and v_phone is not null
       and not exists (select 1 from prospects x where x.gym_id = p_gym_id
                         and regexp_replace(coalesce(x.phone, ''), '[^0-9]', '', 'g')
                             = regexp_replace(v_phone, '[^0-9]', '', 'g')) then
        insert into prospects (gym_id, full_name, phone, source, stage, notes, next_follow_up)
        values (p_gym_id, coalesce(v_name, 'Day pass visitor'), v_phone, 'walk_in', 'visited',
                'Bought a day pass online on ' || to_char(v_day, 'DD Mon YYYY') || '.', v_day + 1);
    end if;
    return json_build_object('ok', true, 'order_no', v_no, 'total', v_total, 'items', lines);
end $$;
revoke all on function public.shop_record_online(uuid, jsonb, text, text, text, numeric) from public, anon, authenticated;
grant execute on function public.shop_record_online(uuid, jsonb, text, text, text, numeric) to service_role;

commit;
