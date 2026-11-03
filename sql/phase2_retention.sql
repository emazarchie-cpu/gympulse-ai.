-- =====================================================================
-- GymPulse AI · Phase 2 · Retention play lifecycle
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds columns and an index; it deletes nothing.
--
-- A play moves through: Recommended -> Started -> In progress -> Contacted
-- -> Follow-up due -> Resolved / Unsuccessful.
-- `status` keeps its three values (To do, In progress, Done). These columns
-- record who was contacted, how, when, and when to follow up, and the
-- Action Centre and Follow-ups both write to them.
-- Before this script the app still works: contact details are written into
-- the play's note instead.
-- =====================================================================

begin;

alter table public.retention_actions add column if not exists contacted_at   timestamptz;
alter table public.retention_actions add column if not exists contact_method text;
alter table public.retention_actions add column if not exists follow_up_on   date;
alter table public.retention_actions add column if not exists details        jsonb;
alter table public.retention_actions add column if not exists trainer_id     uuid;

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'retention_contact_method_chk') then
        alter table public.retention_actions add constraint retention_contact_method_chk
            check (contact_method is null
                   or contact_method in ('WhatsApp', 'Call', 'Email', 'In person', 'SMS'));
    end if;
end $$;

create index if not exists retention_actions_gym_open_idx
    on public.retention_actions (gym_id, status, due_date);

commit;

-- Check it worked: the new columns should be listed.
select column_name, data_type
from information_schema.columns
where table_schema = 'public' and table_name = 'retention_actions'
  and column_name in ('contacted_at', 'contact_method', 'follow_up_on', 'details', 'trainer_id')
order by column_name;
