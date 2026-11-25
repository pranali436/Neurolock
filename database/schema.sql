-- Run this in Supabase SQL Editor.
create extension if not exists pgcrypto;

create table if not exists public.profiles (
  id uuid primary key references auth.users(id) on delete cascade,
  display_name text,
  created_at timestamptz not null default now()
);

create table if not exists public.keystroke_templates (
  user_id uuid primary key references auth.users(id) on delete cascade,
  feature_vector jsonb not null,
  sample_count integer not null default 0,
  updated_at timestamptz not null default now()
);

create table if not exists public.user_files (
  id uuid primary key default gen_random_uuid(),
  user_id uuid not null references auth.users(id) on delete cascade,
  original_name text not null,
  object_path text not null unique,
  content_type text,
  size_bytes bigint not null default 0,
  created_at timestamptz not null default now()
);

create table if not exists public.security_events (
  id uuid primary key default gen_random_uuid(),
  user_id uuid references auth.users(id) on delete set null,
  event_type text not null,
  details jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now()
);

alter table public.profiles enable row level security;
alter table public.keystroke_templates enable row level security;
alter table public.user_files enable row level security;
alter table public.security_events enable row level security;

-- Users can only see/edit their own profile.
create policy "profile owner select" on public.profiles
for select to authenticated using (auth.uid() = id);
create policy "profile owner insert" on public.profiles
for insert to authenticated with check (auth.uid() = id);
create policy "profile owner update" on public.profiles
for update to authenticated using (auth.uid() = id) with check (auth.uid() = id);

-- No direct browser access to biometric templates, file metadata or security logs.
-- The FastAPI server accesses these tables after validating the user's Supabase token.

-- Create a private storage bucket. If this statement is blocked, create the bucket
-- manually in Dashboard → Storage and set Public bucket = OFF.
insert into storage.buckets (id, name, public, file_size_limit)
values ('neurolock-files', 'neurolock-files', false, 52428800)
on conflict (id) do nothing;

-- Storage objects are owned by a user through the first folder segment (auth.uid()).
create policy "users upload own files" on storage.objects
for insert to authenticated
with check (bucket_id = 'neurolock-files' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "users list own files" on storage.objects
for select to authenticated
using (bucket_id = 'neurolock-files' and (storage.foldername(name))[1] = auth.uid()::text);
create policy "users delete own files" on storage.objects
for delete to authenticated
using (bucket_id = 'neurolock-files' and (storage.foldername(name))[1] = auth.uid()::text);

-- Failed-authentication counters: one row per user + failure type.
-- This table already exists in the NeuroLock project. It is declared here with
-- "if not exists" so a fresh setup matches the deployed schema, without
-- creating a duplicate object.
create table if not exists public.auth_failure_counters (
  user_id uuid not null references auth.users(id) on delete cascade,
  failure_type text not null,
  window_started_at timestamptz not null default now(),
  failure_count integer not null default 0,
  alert_sent boolean not null default false,
  updated_at timestamptz not null default now(),
  primary key (user_id, failure_type)
);

alter table public.auth_failure_counters enable row level security;
-- No policies: only the service-role backend may read/write these counters.

-- Increment a failure counter for a known user. The 15-minute window is fixed
-- from the first failure (window_started_at); when it expires the counter
-- restarts at 1. Returns should_alert = true exactly when the 3rd failure is
-- recorded, so the backend emails the account owner once per window.
create or replace function public.record_auth_failure(
  p_user_id uuid,
  p_failure_type text
)
returns table (failure_count integer, should_alert boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_window constant interval := interval '15 minutes';
  v_count integer;
  v_window_started timestamptz;
  v_alert_sent boolean;
  v_should_alert boolean := false;
begin
  select c.failure_count, c.window_started_at, c.alert_sent
    into v_count, v_window_started, v_alert_sent
    from public.auth_failure_counters c
   where c.user_id = p_user_id
     and c.failure_type = p_failure_type
   for update;

  if v_count is null or v_window_started < now() - v_window then
    insert into public.auth_failure_counters
      (user_id, failure_type, window_started_at, failure_count, alert_sent, updated_at)
    values
      (p_user_id, p_failure_type, now(), 1, false, now())
    on conflict (user_id, failure_type) do update
      set window_started_at = now(),
          failure_count = 1,
          alert_sent = false,
          updated_at = now();
    v_count := 1;
    v_alert_sent := false;
  else
    update public.auth_failure_counters c
       set failure_count = c.failure_count + 1,
           updated_at = now()
     where c.user_id = p_user_id
       and c.failure_type = p_failure_type
     returning c.failure_count into v_count;
  end if;

  if v_count >= 3 and v_alert_sent is distinct from true then
    update public.auth_failure_counters c
       set alert_sent = true,
           updated_at = now()
     where c.user_id = p_user_id
       and c.failure_type = p_failure_type;
    v_should_alert := true;
  end if;

  return query select v_count, v_should_alert;
end;
$$;

-- Password failures are keyed by email at the API boundary. Unknown emails
-- return no rows, so only registered accounts are counted.
create or replace function public.record_password_failure_by_email(
  p_email text
)
returns table (user_id uuid, user_email text, failure_count integer, should_alert boolean)
language plpgsql
security definer
set search_path = public
as $$
declare
  v_user_id uuid;
  v_email text;
begin
  select u.id, u.email
    into v_user_id, v_email
    from auth.users u
   where lower(u.email) = lower(btrim(p_email))
   limit 1;

  if v_user_id is null then
    return;
  end if;

  return query
    select v_user_id, v_email, r.failure_count, r.should_alert
      from public.record_auth_failure(v_user_id, 'password') as r;
end;
$$;

-- Clear a user's counter after successful authentication.
create or replace function public.reset_auth_failure(
  p_user_id uuid,
  p_failure_type text
)
returns void
language plpgsql
security definer
set search_path = public
as $$
begin
  delete from public.auth_failure_counters c
   where c.user_id = p_user_id
     and c.failure_type = p_failure_type;
end;
$$;

-- Account-lockout check used by POST /api/login before authentication.
-- locked = true while a 15-minute window with 3+ password failures is still
-- open; retry_after_seconds is the remaining time until that window expires.
create or replace function public.get_password_lockout_by_email(
  p_email text
)
returns table (
  locked boolean,
  failure_count integer,
  retry_after_seconds integer
)
language sql
stable
security definer
set search_path = public
as $$
  select
    (c.failure_count >= 3
       and c.window_started_at + interval '15 minutes' > now()) as locked,
    c.failure_count,
    greatest(
      0,
      ceil(extract(epoch from (c.window_started_at + interval '15 minutes' - now())))
    )::integer as retry_after_seconds
  from public.auth_failure_counters c
  join auth.users u on u.id = c.user_id
  where c.failure_type = 'password'
    and lower(u.email) = lower(btrim(p_email))
  limit 1;
$$;

-- Backend-only: keep these helpers off the public PostgREST surface.
revoke all on function public.record_auth_failure(uuid, text) from public, anon, authenticated;
revoke all on function public.record_password_failure_by_email(text) from public, anon, authenticated;
revoke all on function public.reset_auth_failure(uuid, text) from public, anon, authenticated;
revoke all on function public.get_password_lockout_by_email(text) from public, anon, authenticated;
grant execute on function public.record_auth_failure(uuid, text) to service_role;
grant execute on function public.record_password_failure_by_email(text) to service_role;
grant execute on function public.reset_auth_failure(uuid, text) to service_role;
grant execute on function public.get_password_lockout_by_email(text) to service_role;
