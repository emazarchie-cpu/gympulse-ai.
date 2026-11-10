-- =====================================================================
-- GymPulse AI · Phase 33 · Members sign in with email and password
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds a table; it deletes nothing.
--
-- member_passwords   one row per membership that has set a password.
--   hash             the password, scrambled with PBKDF2 and a random salt (never the password itself)
--   tries            wrong passwords in a row; 10 locks sign-in for 15 minutes
--   locked_until     when sign-in opens again after too many wrong tries
--
-- Row level security is on with NO policies: gym owners and staff can't read it, only the app's
-- server (service role) can. The 6-digit email code still works for first sign-in and
-- "forgot password".
-- =====================================================================

begin;

create table if not exists public.member_passwords (
    member_id     uuid primary key references public.members (id) on delete cascade,
    gym_id        uuid not null references public.gyms (id) on delete cascade,
    hash          text not null,
    tries         int not null default 0,
    locked_until  timestamptz,
    updated_at    timestamptz not null default now()
);

alter table public.member_passwords enable row level security;
revoke all on public.member_passwords from anon, authenticated;

commit;

-- Check it worked: should say true.
select to_regclass('public.member_passwords') is not null as member_passwords;
