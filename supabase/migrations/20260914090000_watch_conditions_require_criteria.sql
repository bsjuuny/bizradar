-- Prevent accidental "match everything" Watch rows. Existing rows are not validated here
-- so the migration can be applied safely; application/worker code also ignores them.
alter table watch_conditions
  add constraint watch_conditions_require_criteria
  check (
    nullif(btrim(keyword), '') is not null
    or category is not null
    or min_budget is not null
    or max_budget is not null
    or min_match_score is not null
  ) not valid;
