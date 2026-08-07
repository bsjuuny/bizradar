-- Phase 4: rule-filter category on opportunities + AI analysis results.
-- category is a cheap rule-based filter (NON_IT/LIKELY_IT/UNKNOWN) that runs before any
-- LLM call - see worker/ai/rule_filter.py and docs/DATA_PIPELINE.md. Only LIKELY_IT (and
-- a sampled slice of UNKNOWN) ever reach project_analyses.

alter table opportunities
  add column category text not null default 'UNKNOWN'
  check (category in ('NON_IT', 'LIKELY_IT', 'UNKNOWN'));

create index opportunities_category_idx on opportunities (category);

create table project_analyses (
  id uuid primary key default gen_random_uuid(),
  opportunity_id uuid not null references opportunities (id) on delete cascade,
  status text not null default 'PENDING' check (status in ('PENDING', 'SUCCESS', 'FAILED')),
  project_type text check (
    project_type in (
      'SYSTEM_BUILD', 'MAINTENANCE', 'CONSULTING', 'DATA_ANALYTICS',
      'AI_ML', 'INFRASTRUCTURE', 'OTHER'
    )
  ),
  technologies jsonb not null default '[]',
  required_roles jsonb not null default '[]',
  requirements jsonb not null default '[]',
  risks jsonb not null default '[]',
  summary text,
  model text,
  model_version text,
  prompt_version text,
  analyzed_at timestamptz,
  error_message text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (opportunity_id)
);

create trigger project_analyses_set_updated_at
  before update on project_analyses
  for each row
  execute function extensions.moddatetime('updated_at');

alter table project_analyses enable row level security;

-- Public-derived data: any authenticated user can read; only service_role writes
-- (the worker) - it bypasses RLS, so no insert/update policy is needed here.
create policy project_analyses_select_authenticated on project_analyses
  for select
  to authenticated
  using (true);

grant select on project_analyses to authenticated;
