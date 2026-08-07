-- Phase 5: Match Engine data model. Rule-based scoring (worker/matching/engine.py) needs
-- real signals on both sides - company profile fields to score against, and a couple of
-- AI-extracted opportunity fields that Phase 4's schema didn't capture yet.

-- Company-side signals. Nullable budget range = no preference declared (treated as "no
-- constraint" by the scorer, not "unknown"); experience_years/qualifications default to
-- empty rather than null since "0 years" / "no quals" are meaningful, checkable values.
alter table companies
  add column budget_min numeric,
  add column budget_max numeric,
  add column experience_years int not null default 0 check (experience_years >= 0),
  add column qualifications text[] not null default '{}';

-- Opportunity-side signals the AI extracts but Phase 4's schema didn't capture.
alter table project_analyses
  add column min_experience_years int,
  add column required_qualifications jsonb not null default '[]';

create table match_scores (
  id uuid primary key default gen_random_uuid(),
  company_id uuid not null references companies (id) on delete cascade,
  opportunity_id uuid not null references opportunities (id) on delete cascade,
  technology_score numeric not null check (technology_score between 0 and 30),
  business_type_score numeric not null check (business_type_score between 0 and 20),
  budget_score numeric not null check (budget_score between 0 and 15),
  experience_score numeric not null check (experience_score between 0 and 15),
  qualification_score numeric not null check (qualification_score between 0 and 10),
  region_score numeric not null check (region_score between 0 and 5),
  schedule_score numeric not null check (schedule_score between 0 and 5),
  total_score numeric generated always as (
    technology_score + business_type_score + budget_score + experience_score +
    qualification_score + region_score + schedule_score
  ) stored,
  computed_at timestamptz not null default now(),
  unique (company_id, opportunity_id)
);

create index match_scores_company_total_idx on match_scores (company_id, total_score desc);

create trigger match_scores_set_computed_at
  before update on match_scores
  for each row
  execute function extensions.moddatetime('computed_at');

alter table match_scores enable row level security;

-- Company-scoped, not public: only the company's own members should see their match
-- scores against opportunities, and only service_role (the worker) computes them.
create policy match_scores_select_own on match_scores
  for select
  to authenticated
  using (company_id = auth_company_id());

grant select on match_scores to authenticated;
