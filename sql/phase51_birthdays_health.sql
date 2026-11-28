-- =====================================================================
-- GymPulse AI · Phase 51 · Birthdays and health questions at sign-up
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It adds columns; it deletes nothing.
--
--   members.date_of_birth        for birthday wishes (Grow -> Automatic messages) and the age
--   members.health_notes         what the member chose to tell the gym about health conditions or injuries
--   members.health_cleared       the member said a doctor has not told them to avoid exercise (true/false)
--   members.health_consent_at    when the member agreed the gym may keep this to keep them safe (NDPA)
-- Health answers are only saved with consent, and only staff of that gym can read them (members RLS).
-- =====================================================================

begin;

alter table public.members add column if not exists date_of_birth date;
alter table public.members add column if not exists health_notes text;
alter table public.members add column if not exists health_cleared boolean;
alter table public.members add column if not exists health_consent_at timestamptz;

-- The member sign-up link (gympulse_signup.py): the same join as before, plus an optional date of birth and
-- health answers. Like the photo step, these are saved only on a member this call has just created, so a
-- sign-up link can never change an existing member; health answers only with the member's consent.
create or replace function public.gp_member_join(p_code text, p_name text, p_phone text, p_email text, p_goal text,
                                                 p_age integer, p_consent boolean, p_photo text, p_dob date,
                                                 p_health_notes text, p_health_cleared boolean,
                                                 p_health_consent boolean)
returns table(business_name text, status text)
language plpgsql security definer set search_path = public as $$
declare
    r        record;
    v_email  text := lower(btrim(coalesce(p_email, '')));
    v_digits text := right(regexp_replace(coalesce(p_phone, ''), '\D', '', 'g'), 10);
    v_dob    date := case when p_dob between date '1920-01-01' and current_date - 3650 then p_dob end;
    v_id     uuid;
begin
    select * into r from public.gp_member_join(p_code, p_name, p_phone, p_email, p_goal, p_age, p_consent, p_photo);
    if not found then
        return;
    end if;
    if r.status = 'created' then
        select m2.id into v_id from public.members m2 join public.gyms g on g.id = m2.gym_id
         where g.join_code = p_code and m2.joined_via = 'link'
           and ((v_email <> '' and lower(m2.email) = v_email)
                or (length(v_digits) >= 7 and right(regexp_replace(coalesce(m2.phone, ''), '\D', '', 'g'), 10) = v_digits))
         order by m2.created_at desc limit 1;
        if v_id is not null then
            update public.members m set
                date_of_birth = coalesce(v_dob, m.date_of_birth),
                health_notes = case when coalesce(p_health_consent, false)
                                    then nullif(left(btrim(coalesce(p_health_notes, '')), 1000), '') end,
                health_cleared = case when coalesce(p_health_consent, false) then p_health_cleared end,
                health_consent_at = case when coalesce(p_health_consent, false) then now() end
             where m.id = v_id;
        end if;
    end if;
    return query select r.business_name, r.status;
end $$;
revoke all on function public.gp_member_join(text, text, text, text, text, integer, boolean, text, date, text, boolean, boolean) from public;
grant execute on function public.gp_member_join(text, text, text, text, text, integer, boolean, text, date, text, boolean, boolean) to anon, authenticated;

commit;
