-- Phase 6: CHALLENGE domain. Additive only: existing PUBLIC/ENTERPRISE/SUPPORT/MARKET
-- data and tables are not modified or reset.

create extension if not exists pg_trgm with schema extensions;

create table challenges (
  id uuid primary key default gen_random_uuid(),
  source_id text not null,
  source_name text not null,
  source_type text not null,
  source_priority int not null default 100 check (source_priority >= 0),
  external_id text not null,
  dedupe_key text not null unique,
  content_hash text not null,

  title text not null,
  summary text,
  description text,
  challenge_type text not null default 'OTHER' check (
    challenge_type in (
      'CONTEST', 'HACKATHON', 'AI_COMPETITION', 'DATA_COMPETITION',
      'DEV_COMPETITION', 'IDEA_COMPETITION', 'STARTUP_COMPETITION',
      'AWARD', 'PUBLIC_DATA_COMPETITION', 'OTHER'
    )
  ),
  organizer text,
  host text,
  sponsor text,
  start_date timestamptz,
  end_date timestamptz,
  apply_start_date timestamptz,
  apply_end_date timestamptz,
  result_date timestamptz,

  eligibility text,
  eligibility_type text not null default 'UNKNOWN' check (
    eligibility_type in (
      'ANYONE', 'STUDENT', 'UNIVERSITY', 'GRADUATE_STUDENT', 'EMPLOYEE',
      'DEVELOPER', 'STARTUP', 'COMPANY', 'TEAM', 'REGION_LIMITED',
      'AGE_LIMITED', 'OTHER', 'UNKNOWN'
    )
  ),
  team_min int check (team_min is null or team_min >= 1),
  team_max int check (team_max is null or team_max >= 1),
  region text,
  participation_type text not null default 'UNKNOWN' check (
    participation_type in ('ONLINE', 'OFFLINE', 'HYBRID', 'UNKNOWN')
  ),

  prize text,
  total_prize_amount bigint check (total_prize_amount is null or total_prize_amount >= 0),
  currency text,
  prize_description text,
  source_url text not null,
  application_url text,
  thumbnail_url text,
  required_documents text[] not null default '{}',
  submission_requirements text[] not null default '{}',
  technology_keywords text[] not null default '{}',
  categories text[] not null default '{}',
  tags text[] not null default '{}',
  attachments jsonb not null default '[]',

  ai_policy text not null default 'UNKNOWN' check (
    ai_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  ai_policy_confidence numeric not null default 0 check (ai_policy_confidence between 0 and 1),
  ai_policy_evidence text,
  ai_policy_source_section text,
  generative_ai_policy text not null default 'UNKNOWN' check (
    generative_ai_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  ai_coding_policy text not null default 'UNKNOWN' check (
    ai_coding_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  llm_policy text not null default 'UNKNOWN' check (
    llm_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  ai_image_policy text not null default 'UNKNOWN' check (
    ai_image_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  ai_video_policy text not null default 'UNKNOWN' check (
    ai_video_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  ai_audio_policy text not null default 'UNKNOWN' check (
    ai_audio_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  external_ai_api_policy text not null default 'UNKNOWN' check (
    external_ai_api_policy in ('REQUIRED', 'ALLOWED', 'LIMITED', 'PROHIBITED', 'UNKNOWN')
  ),
  prompt_disclosure_required boolean not null default false,
  ai_usage_disclosure_required boolean not null default false,
  analysis_status text not null default 'RULE_ONLY' check (
    analysis_status in ('PENDING', 'SUCCESS', 'FAILED', 'RULE_ONLY', 'SKIPPED')
  ),
  analysis_error text,
  analysis_model text,
  analysis_prompt_version text,
  analyzed_at timestamptz,

  external_api_policy text,
  open_source_policy text,
  copyright_policy text,
  ownership_policy text,
  original_text text not null,
  search_text text not null,
  status text not null default 'UNKNOWN' check (
    status in ('UPCOMING', 'OPEN', 'CLOSING_SOON', 'CLOSED', 'UNKNOWN')
  ),
  raw_payload jsonb not null,
  collected_at timestamptz not null,
  last_checked_at timestamptz not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source_id, external_id),
  check (team_min is null or team_max is null or team_min <= team_max),
  check (ai_policy <> 'UNKNOWN' or ai_policy_evidence is null)
);

create trigger challenges_set_updated_at
  before update on challenges
  for each row
  execute function extensions.moddatetime('updated_at');

create index challenges_type_status_idx on challenges (challenge_type, status);
create index challenges_apply_end_idx on challenges (apply_end_date);
create index challenges_ai_policy_idx on challenges (ai_policy);
create index challenges_ai_coding_policy_idx on challenges (ai_coding_policy);
create index challenges_organizer_idx on challenges (organizer);
create index challenges_source_external_idx on challenges (source_id, external_id);
create index challenges_content_hash_idx on challenges (content_hash);
create index challenges_search_trgm_idx on challenges using gin (search_text gin_trgm_ops);

alter table challenges enable row level security;
create policy challenges_select_authenticated on challenges
  for select to authenticated using (true);
grant select on challenges to authenticated;

create table challenge_source_status (
  source_id text primary key,
  source_name text not null,
  enabled boolean not null default true,
  last_run_at timestamptz,
  last_success_at timestamptz,
  last_failure_at timestamptz,
  last_status text check (last_status in ('SUCCESS', 'PARTIAL_SUCCESS', 'FAILED', 'TEMP_DISABLED')),
  fetched int not null default 0 check (fetched >= 0),
  error text,
  updated_at timestamptz not null default now()
);

create trigger challenge_source_status_set_updated_at
  before update on challenge_source_status
  for each row
  execute function extensions.moddatetime('updated_at');

alter table challenge_source_status enable row level security;
create policy challenge_source_status_select_authenticated on challenge_source_status
  for select to authenticated using (true);
grant select on challenge_source_status to authenticated;
