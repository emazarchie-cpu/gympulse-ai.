-- =====================================================================
-- GymPulse AI · Branded retention emails
-- Run once in Supabase: SQL Editor -> New query -> paste -> Run.
-- Safe to run again. It only adds columns, a function, a storage bucket
-- and access rules.
--
--  * members.email_opt_out / unsub_token: every email has an unsubscribe
--    link, and GymPulse never emails a member who unsubscribed.
--  * email-assets bucket: gyms' logos, photos and email banners. Images are
--    public so they show in inboxes; each gym can only upload into its own
--    folder.
-- =====================================================================

begin;

alter table public.members add column if not exists email_opt_out boolean not null default false;
alter table public.members add column if not exists unsub_token uuid not null default gen_random_uuid();
create unique index if not exists members_unsub_token_uidx on public.members (unsub_token);

create or replace function public.email_unsubscribe(p_token uuid)
returns table (business_name text)
language sql security definer set search_path = public as $$
    with m as (
        update public.members set email_opt_out = true
        where unsub_token = p_token
        returning gym_id
    )
    select g.business_name from m join public.gyms g on g.id = m.gym_id;
$$;
revoke all on function public.email_unsubscribe(uuid) from public;
grant execute on function public.email_unsubscribe(uuid) to anon, authenticated;

-- Image hosting for email logos, photos and banners
insert into storage.buckets (id, name, public)
values ('email-assets', 'email-assets', true)
on conflict (id) do update set public = true;

do $$
begin
    if not exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                   and policyname = 'gp_email_assets_write') then
        create policy gp_email_assets_write on storage.objects for insert to authenticated
            with check (bucket_id = 'email-assets'
                        and public.gp_owns_gym(((storage.foldername(name))[1])::uuid));
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                   and policyname = 'gp_email_assets_update') then
        create policy gp_email_assets_update on storage.objects for update to authenticated
            using (bucket_id = 'email-assets'
                   and public.gp_owns_gym(((storage.foldername(name))[1])::uuid));
    end if;
    if not exists (select 1 from pg_policies where schemaname = 'storage' and tablename = 'objects'
                   and policyname = 'gp_email_assets_read') then
        create policy gp_email_assets_read on storage.objects for select to public
            using (bucket_id = 'email-assets');
    end if;
end $$;

commit;

-- Check it worked
select (select count(*) from information_schema.columns
        where table_name = 'members' and column_name in ('email_opt_out', 'unsub_token')) as member_columns,
       (select count(*) from storage.buckets where id = 'email-assets') as bucket;
