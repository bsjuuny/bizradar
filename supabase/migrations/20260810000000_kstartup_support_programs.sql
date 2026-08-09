-- Phase 6 (partial): K-Startup 공고 - RAW + NORMALIZED, same pattern as opportunities
-- (Phase 2). BizInfo lands separately later; this table is source-agnostic (`source`
-- distinguishes them) so it doesn't need to change shape when that happens.
-- `investment_linked` is a rule-filter classification (worker/ai/investment_filter.py),
-- computed at collection time - same design as opportunities.category. See
-- docs/DATA_PIPELINE.md#support-programs.

create table support_programs (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source = 'kstartup'),
  external_id text not null,
  content_hash text not null,
  title text not null,
  organization text,
  department text,
  supervising_type text,
  category text,
  region text,
  target text,
  recruiting boolean,
  investment_linked boolean not null default false,
  application_start timestamptz,
  application_end timestamptz,
  description text,
  source_url text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source, external_id)
);

create trigger support_programs_set_updated_at
  before update on support_programs
  for each row
  execute function extensions.moddatetime('updated_at');

create index support_programs_application_end_idx on support_programs (application_end desc);
create index support_programs_investment_linked_idx on support_programs (investment_linked)
  where investment_linked;

alter table support_programs enable row level security;

-- Public data, same as opportunities: any authenticated user can read; only
-- service_role writes.
create policy support_programs_select_authenticated on support_programs
  for select
  to authenticated
  using (true);

grant select on support_programs to authenticated;
