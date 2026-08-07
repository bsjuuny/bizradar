-- Phase 1: auth + company profile.
-- Opportunities / support_programs / match_scores / saved / watch land in their own
-- migrations in later phases once the source data shapes are known (see docs/DATABASE.md).

create extension if not exists pgcrypto;
create extension if not exists moddatetime schema extensions;

-- ---------------------------------------------------------------------------
-- technologies: shared lookup used by company tech stack (and later matching)
-- ---------------------------------------------------------------------------
create table technologies (
  id uuid primary key default gen_random_uuid(),
  name text not null unique
);

-- ---------------------------------------------------------------------------
-- companies
-- ---------------------------------------------------------------------------
create table companies (
  id uuid primary key default gen_random_uuid(),
  name text not null,
  size_band text not null check (size_band in ('1-5', '6-10', '11-20', '21-50', '51+')),
  industry text,
  region text,
  business_type text,
  founded_year int check (founded_year between 1900 and 2100),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create trigger companies_set_updated_at
  before update on companies
  for each row
  execute function extensions.moddatetime('updated_at');

-- ---------------------------------------------------------------------------
-- company_members: links auth.users to companies.
-- MVP invariant: a user belongs to at most one company (user_id is the PK, not just
-- indexed) - there is no invite/multi-company flow in this MVP.
-- ---------------------------------------------------------------------------
create table company_members (
  user_id uuid primary key references auth.users (id) on delete cascade,
  company_id uuid not null references companies (id) on delete cascade,
  role text not null default 'owner' check (role in ('owner', 'member')),
  created_at timestamptz not null default now()
);

create index company_members_company_id_idx on company_members (company_id);

-- ---------------------------------------------------------------------------
-- company_technologies: join table for a company's declared tech stack
-- ---------------------------------------------------------------------------
create table company_technologies (
  company_id uuid not null references companies (id) on delete cascade,
  technology_id uuid not null references technologies (id) on delete cascade,
  primary key (company_id, technology_id)
);

-- ---------------------------------------------------------------------------
-- worker_heartbeats: local PM2 worker reports in here so the web dashboard can show
-- "data last updated at ...". Written by the worker (service_role), read by the web app.
-- ---------------------------------------------------------------------------
create table worker_heartbeats (
  worker_name text primary key,
  last_seen_at timestamptz not null default now(),
  version text,
  status text not null default 'unknown'
);

-- ---------------------------------------------------------------------------
-- auth_company_id(): the calling user's company_id, or null if they have none yet.
-- security definer so it can read company_members (which has its own restrictive RLS)
-- without policies on every other table needing to reason about that join directly.
-- ---------------------------------------------------------------------------
create or replace function auth_company_id()
returns uuid
language sql
stable
security definer
set search_path = public
as $$
  select company_id from company_members where user_id = auth.uid()
$$;

-- ---------------------------------------------------------------------------
-- RLS
-- ---------------------------------------------------------------------------
alter table technologies enable row level security;
alter table companies enable row level security;
alter table company_members enable row level security;
alter table company_technologies enable row level security;
alter table worker_heartbeats enable row level security;

-- technologies: public reference data, readable by any authenticated user.
-- Written by migrations/service_role only - no insert/update/delete policy for others.
create policy technologies_select_authenticated on technologies
  for select
  to authenticated
  using (true);

-- companies: a user can only see/update their own company. Any authenticated user may
-- create a company row (that's the "create company" onboarding step); linking it to
-- themselves happens via a company_members insert, restricted below.
create policy companies_select_own on companies
  for select
  to authenticated
  using (id = auth_company_id());

create policy companies_insert_authenticated on companies
  for insert
  to authenticated
  with check (true);

create policy companies_update_own on companies
  for update
  to authenticated
  using (id = auth_company_id())
  with check (id = auth_company_id());

-- company_members: a user can only see/create their own membership row.
create policy company_members_select_own on company_members
  for select
  to authenticated
  using (user_id = auth.uid());

create policy company_members_insert_own on company_members
  for insert
  to authenticated
  with check (user_id = auth.uid());

-- company_technologies: scoped to the caller's own company.
create policy company_technologies_select_own on company_technologies
  for select
  to authenticated
  using (company_id = auth_company_id());

create policy company_technologies_insert_own on company_technologies
  for insert
  to authenticated
  with check (company_id = auth_company_id());

create policy company_technologies_delete_own on company_technologies
  for delete
  to authenticated
  using (company_id = auth_company_id());

-- worker_heartbeats: any authenticated user can read; only service_role writes
-- (service_role bypasses RLS, so no insert/update policy is needed here).
create policy worker_heartbeats_select_authenticated on worker_heartbeats
  for select
  to authenticated
  using (true);
