-- Phase 8 slice: saved opportunities and watch conditions.
-- This supports the first customer-facing decision workflow: a daily response queue.

create table saved_opportunities (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  opportunity_id uuid not null references opportunities (id) on delete cascade,
  status text not null default 'REVIEWING'
    check (status in ('REVIEWING', 'RESPONDING', 'ON_HOLD', 'DECLINED')),
  owner_name text,
  note text,
  saved_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (company_id, opportunity_id)
);

create index saved_opportunities_company_status_idx
  on saved_opportunities (company_id, status, updated_at desc);

create table watch_conditions (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  name text not null,
  keyword text,
  category text check (category in ('LIKELY_IT', 'NON_IT', 'UNKNOWN')),
  min_budget numeric,
  max_budget numeric,
  min_match_score numeric check (min_match_score between 0 and 100),
  active boolean not null default true,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

create index watch_conditions_company_active_idx
  on watch_conditions (company_id, active, created_at desc);

create trigger saved_opportunities_set_updated_at
  before update on saved_opportunities
  for each row
  execute function extensions.moddatetime('updated_at');

create trigger watch_conditions_set_updated_at
  before update on watch_conditions
  for each row
  execute function extensions.moddatetime('updated_at');

alter table saved_opportunities enable row level security;
alter table watch_conditions enable row level security;

create policy saved_opportunities_select_own on saved_opportunities
  for select
  to authenticated
  using (company_id = auth_company_id());

create policy saved_opportunities_insert_own on saved_opportunities
  for insert
  to authenticated
  with check (company_id = auth_company_id());

create policy saved_opportunities_update_own on saved_opportunities
  for update
  to authenticated
  using (company_id = auth_company_id())
  with check (company_id = auth_company_id());

create policy saved_opportunities_delete_own on saved_opportunities
  for delete
  to authenticated
  using (company_id = auth_company_id());

create policy watch_conditions_select_own on watch_conditions
  for select
  to authenticated
  using (company_id = auth_company_id());

create policy watch_conditions_insert_own on watch_conditions
  for insert
  to authenticated
  with check (company_id = auth_company_id());

create policy watch_conditions_update_own on watch_conditions
  for update
  to authenticated
  using (company_id = auth_company_id())
  with check (company_id = auth_company_id());

create policy watch_conditions_delete_own on watch_conditions
  for delete
  to authenticated
  using (company_id = auth_company_id());

grant select, insert, update, delete on saved_opportunities to authenticated;
grant select, insert, update, delete on watch_conditions to authenticated;
