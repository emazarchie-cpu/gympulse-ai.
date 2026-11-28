-- =====================================================================
-- GymPulse AI · Phase 54 · Faster shop: barcodes and undo
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one column and one function; it deletes nothing.
--
--   shop_products.barcode   the number under a product's barcode, so a USB scanner adds it to the sale
--   shop_void(p_sale_id)    undo a sale: marks it voided, puts the stock back and takes it off the
--                           member's balance if it was added there. Runs as the signed-in staff member (RLS).
-- =====================================================================

begin;

alter table public.shop_products add column if not exists barcode text;
create index if not exists shop_products_barcode on public.shop_products (gym_id, barcode) where barcode is not null;

create or replace function public.shop_void(p_sale_id uuid)
returns json
language plpgsql security invoker set search_path = public as $$
declare
    s   public.shop_sales%rowtype;
    it  jsonb;
begin
    select * into s from shop_sales where id = p_sale_id;
    if s.id is null or not public.gp_owns_gym(s.gym_id) then
        return json_build_object('ok', false, 'error', 'Sale not found');
    end if;
    if s.voided then
        return json_build_object('ok', true, 'already', true);
    end if;
    for it in select * from jsonb_array_elements(s.items) loop
        update shop_products set stock = stock + coalesce((it ->> 'qty')::integer, 0)
         where id = (it ->> 'product_id')::uuid and gym_id = s.gym_id and stock is not null;
    end loop;
    if s.method = 'account' and s.member_id is not null then
        update members set balance_owed = greatest(coalesce(balance_owed, 0) - s.total, 0)
         where id = s.member_id and gym_id = s.gym_id;
    end if;
    update shop_sales set voided = true where id = s.id;
    return json_build_object('ok', true);
end $$;
revoke all on function public.shop_void(uuid) from public;
grant execute on function public.shop_void(uuid) to authenticated;

commit;
