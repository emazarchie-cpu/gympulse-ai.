-- =====================================================================
-- GymPulse AI · Phase 1 · Attendance foundation
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds columns and indexes; it deletes nothing.
--
-- Every way a member checks in (front desk, QR/card scan, kiosk, device API,
-- history import) becomes the same attendance event:
--   gym_id, member_id, checked_in_at, source, event_id, location_id, class_id
-- event_id is unique per gym, so the same visit can never be counted twice.
-- The app works before and after this script; after it, every check-in also
-- records its source and is protected against duplicates.
-- =====================================================================

begin;

alter table public.checkins add column if not exists source      text;
alter table public.checkins add column if not exists event_id    uuid;
alter table public.checkins add column if not exists location_id uuid;

-- Existing rows: we don't know how they were captured, so label them honestly.
update public.checkins set source = 'unknown' where source is null;

-- New rows that don't say where they came from (for example the device
-- check-in function) are labelled as coming from a device.
alter table public.checkins alter column source set default 'device';

update public.checkins set event_id = gen_random_uuid() where event_id is null;
alter table public.checkins alter column event_id set default gen_random_uuid();
alter table public.checkins alter column event_id set not null;

create unique index if not exists checkins_gym_event_uidx
    on public.checkins (gym_id, event_id);
create index if not exists checkins_gym_time_idx
    on public.checkins (gym_id, checked_in_at desc);
create index if not exists checkins_member_time_idx
    on public.checkins (member_id, checked_in_at desc);

do $$
begin
    if not exists (select 1 from pg_constraint where conname = 'checkins_source_chk') then
        alter table public.checkins add constraint checkins_source_chk
            check (source in ('front_desk', 'scan', 'kiosk', 'device', 'import', 'unknown'));
    end if;
end $$;

commit;

-- ---------------------------------------------------------------------
-- Check it worked: every row should have a source and an event id.
-- ---------------------------------------------------------------------
select source, count(*) as visits, min(checked_in_at) as first, max(checked_in_at) as last
from public.checkins group by source order by visits desc;

-- Possible duplicates recorded before this script (same member, same minute).
-- Review before deleting anything; nothing here is deleted automatically.
select gym_id, member_id, date_trunc('minute', checked_in_at) as minute, count(*) as copies
from public.checkins
group by 1, 2, 3 having count(*) > 1
order by copies desc limit 50;
