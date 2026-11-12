-- GymPulse AI · phase 44: one free trial per owner, not one per branch
-- Before: every new gym (branch) started its own 30-day free trial, so an owner could keep adding branches to
-- stay free. Now:
--   * an owner's first gym gets the 30-day trial, as before;
--   * a new branch shares the trial that's already running (it ends the same day);
--   * an owner with a branch on a paid plan gets 7 days to set a new branch up before it needs a plan;
--   * an owner whose trial is over and who hasn't paid gets no new trial: the branch needs a plan straight away.
-- Gyms with free access (pilots, set in Admin) count as paid. Admin can still extend any trial.
-- Safe to run more than once.

-- When a new gym's trial should end, given the owner's other gyms
create or replace function public.gp_branch_trial_end(p_owner uuid, p_gym uuid, p_created date)
returns date language sql stable security definer set search_path = public as $$
    with others as (
        select s.* from public.gyms g join public.gym_subscriptions s on s.gym_id = g.id
        where g.owner_id = p_owner and g.id <> p_gym and g.created_at::date <= p_created
    )
    select case
        when not exists (select 1 from others) then p_created + 29                    -- first gym: full trial
        when exists (select 1 from others where status = 'free'
                        or (status = 'active' and paid_until >= p_created))
            then p_created + 6                                                       -- paying owner: 7 days to set up
        when exists (select 1 from others where status = 'trial' and trial_ends_on >= p_created)
            then least(p_created + 29, (select max(trial_ends_on) from others where status = 'trial'))
                                                                                     -- share the running trial
        else p_created - 1                                                           -- trial used up: pay first
    end
$$;
revoke all on function public.gp_branch_trial_end(uuid, uuid, date) from public;

create or replace function public.gp_start_trial()
returns trigger language plpgsql security definer set search_path = public as $$
begin
    insert into public.gym_subscriptions (gym_id, status, trial_ends_on)
    values (new.id, 'trial', public.gp_branch_trial_end(new.owner_id, new.id, current_date))
    on conflict (gym_id) do nothing;
    return new;
end $$;
revoke all on function public.gp_start_trial() from public;

drop trigger if exists gp_start_trial_on_new_gym on public.gyms;
create trigger gp_start_trial_on_new_gym after insert on public.gyms
    for each row execute function public.gp_start_trial();

-- Branches added before this fix: bring their trial in line (only ever shortens a trial, never lengthens one,
-- and never touches an owner's first gym or a gym that has paid or has free access)
update public.gym_subscriptions s
set trial_ends_on = public.gp_branch_trial_end(g.owner_id, g.id, g.created_at::date), updated_at = now()
from public.gyms g
where s.gym_id = g.id and s.status = 'trial'
  and exists (select 1 from public.gyms o where o.owner_id = g.owner_id and o.id <> g.id
              and o.created_at < g.created_at)
  and public.gp_branch_trial_end(g.owner_id, g.id, g.created_at::date) < s.trial_ends_on;

-- Check: every branch and its trial end
select g.owner_id, g.business_name, g.created_at::date as added, s.status, s.trial_ends_on, s.paid_until
from public.gyms g join public.gym_subscriptions s on s.gym_id = g.id
where g.owner_id in (select owner_id from public.gyms group by owner_id having count(*) > 1)
order by g.owner_id, g.created_at;
