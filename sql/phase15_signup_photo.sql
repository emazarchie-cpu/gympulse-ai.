-- =====================================================================
-- GymPulse AI · Phase 15 · Photo on the member sign-up link
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. Needs phase14_member_signup.sql first.
--
-- Members who join through the gym's sign-up link can add a photo.
-- The app resizes it (small JPEG) before sending; this only accepts a small
-- JPEG image and stores it on the new member. Everything else works exactly
-- like gp_member_join in phase 14.
-- =====================================================================

begin;

drop function if exists public.gp_member_join(text, text, text, text, text, int, boolean, text);
create or replace function public.gp_member_join(p_code text, p_name text, p_phone text, p_email text,
                                                 p_goal text, p_age int, p_consent boolean, p_photo text)
returns table (business_name text, status text)
language plpgsql security definer set search_path = public as $$
declare
    r record;
    v_photo text := case when p_photo like 'data:image/jpeg;base64,%' and length(p_photo) < 400000
                         then p_photo end;
    v_email text := lower(btrim(coalesce(p_email, '')));
    v_digits text := right(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), 10);
begin
    select * into r from public.gp_member_join(p_code, p_name, p_phone, p_email, p_goal, p_age, p_consent);
    if not found then
        return;
    end if;
    if r.status = 'created' and v_photo is not null then
        update public.members m set photo = v_photo
        where m.id = (select m2.id from public.members m2 join public.gyms g on g.id = m2.gym_id
                      where g.join_code = p_code and m2.joined_via = 'link'
                        and ((v_email <> '' and lower(m2.email) = v_email)
                             or (length(v_digits) >= 7
                                 and right(regexp_replace(coalesce(m2.phone, ''), '\D', '', 'g'), 10) = v_digits))
                      order by m2.created_at desc limit 1);
    end if;
    return query select r.business_name, r.status;
end $$;
revoke all on function public.gp_member_join(text, text, text, text, text, int, boolean, text) from public;
grant execute on function public.gp_member_join(text, text, text, text, text, int, boolean, text) to anon, authenticated;

commit;
