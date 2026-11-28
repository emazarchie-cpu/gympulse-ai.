-- =====================================================================
-- GymPulse AI · Phase 52 · Class timetable for the gym's own website
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds one function; it deletes nothing.
--
-- usegympulseai.com/?timetable=<join code> shows the gym's classes for the next 14 days (class name and time
-- only, no member data), so the gym can link to it or put it on its website. It works only while the gym's
-- member sign-up link is switched on, using the same public join code.
-- =====================================================================

begin;

create or replace function public.gp_public_timetable(p_code text)
returns json
language sql security definer set search_path = public stable as $$
    select case when g.id is null then json_build_object('ok', false)
           else json_build_object('ok', true, 'gym', g.business_name, 'classes',
                coalesce((select json_agg(json_build_object('name', c.name, 'starts_at', c.starts_at)
                                          order by c.starts_at)
                            from classes c
                           where c.gym_id = g.id and c.starts_at >= now() - interval '1 hour'
                             and c.starts_at < now() + interval '14 days'), '[]'::json)) end
      from (select 1) one
      left join gyms g on g.join_code = p_code and g.join_enabled and coalesce(p_code, '') <> '';
$$;
revoke all on function public.gp_public_timetable(text) from public;
grant execute on function public.gp_public_timetable(text) to anon, authenticated;

commit;
