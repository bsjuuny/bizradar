-- Final G2B award results are published by a separate API from bid announcements.
-- Keep the upstream identity and raw payload so parsing can be corrected without
-- losing source evidence. Multiple classifications/rebids may exist per notice.

create table g2b_award_results (
  id uuid primary key default gen_random_uuid(),
  external_id text not null unique,
  bid_ntce_no text not null,
  bid_ntce_ord integer not null default 0,
  bid_classification_no text not null default '0',
  rebid_no integer not null default 0,
  title text,
  winner_name text not null,
  winner_business_no text,
  winner_representative text,
  winner_address text,
  award_amount numeric,
  award_rate numeric,
  planned_price numeric,
  participant_count integer,
  opened_at timestamptz,
  awarded_at date,
  raw_payload jsonb not null,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  check (award_amount is null or award_amount >= 0),
  check (award_rate is null or award_rate >= 0),
  check (participant_count is null or participant_count >= 0)
);

create index g2b_award_results_notice_idx
  on g2b_award_results (bid_ntce_no, bid_ntce_ord, opened_at desc);

create trigger g2b_award_results_set_updated_at
  before update on g2b_award_results
  for each row
  execute function extensions.moddatetime('updated_at');

alter table g2b_award_results enable row level security;

create policy g2b_award_results_select_authenticated on g2b_award_results
  for select
  to authenticated
  using (true);

grant select on g2b_award_results to authenticated;
