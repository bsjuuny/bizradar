-- Phase 2: G2B (나라장터) bid announcements - RAW + NORMALIZED only. AI analysis
-- (project_analyses), match scores, and the rule-filter category land in Phase 4/5,
-- once something actually consumes them - see docs/DATABASE.md.

create table opportunities (
  id uuid primary key default gen_random_uuid(),
  source text not null check (source = 'g2b'),
  external_id text not null,
  content_hash text not null,
  title text not null,
  organization text,
  demand_organization text,
  budget_amount numeric,
  estimated_price numeric,
  region_restriction text,
  posted_at timestamptz,
  bid_close_at timestamptz,
  open_at timestamptz,
  source_url text,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique (source, external_id)
);

create trigger opportunities_set_updated_at
  before update on opportunities
  for each row
  execute function extensions.moddatetime('updated_at');

create index opportunities_posted_at_idx on opportunities (posted_at desc);

alter table opportunities enable row level security;

-- Public data: any authenticated user can read. Only service_role writes (the worker) -
-- it bypasses RLS entirely, so no insert/update policy is needed here.
create policy opportunities_select_authenticated on opportunities
  for select
  to authenticated
  using (true);

grant select on opportunities to authenticated;
