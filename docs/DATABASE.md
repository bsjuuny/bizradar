# Database

## Status: Phase 1-5 tables + the K-Startup half of Phase 6's `support_programs`
implemented and verified against the live project; the rest are NOT_IMPLEMENTED until
their phase.

- `20260807120000_phase1_company_profile.sql` + `20260807130000_phase1_grants.sql`:
  `technologies`, `companies`, `company_members`, `company_technologies`,
  `worker_heartbeats`, `auth_company_id()`. Verified with
  `supabase/tests/test_rls_phase1.py`.
- `20260807140000_phase2_opportunities.sql`: `opportunities`. Verified live via
  `worker/collectors/g2b.py` against the real G2B API + this project.
- `20260807150000_phase3_opportunities_search.sql` +
  `20260807160000_phase3_search_trgm.sql`: search over `opportunities`. Verified via
  `apps/web/e2e/opportunities.spec.ts` against the real project.
- `20260807170000_phase4_project_analyses.sql` + `20260807180000_phase4_analyzed_content_hash.sql`:
  `opportunities.category`, `project_analyses`. Verified live via
  `worker/jobs/analyze_job.py` against a real local Ollama instance + this project.
- `20260807190000_phase5_match_engine.sql` + `20260807200000_phase5_technologies_seed.sql`:
  `companies` match-profile columns, `project_analyses` experience/qualification columns,
  `match_scores`, a starter `technologies` vocabulary. Verified live via
  `worker/jobs/match_job.py` against a real company profile + real analyzed
  opportunities.
- `20260809000000_notice_thread_dedup.sql`: `opportunities.bid_ntce_no`/`bid_ntce_ord`/
  `ntce_kind_nm` + the `opportunities_current` view. Verified live against the real
  dataset (3,634 rows -> 3,063 after dedup) - see
  `docs/DATA_PIPELINE.md#notice-thread-deduplication-implemented-2026-08-09`.
- `20260809010000_market_stats_fields.sql`: `opportunities.industry_limited`/
  `participation_limited`/`procurement_category`.
  `20260809020000_refresh_opportunities_current_view.sql`: `CREATE OR REPLACE` on
  `opportunities_current` so its `select o.*` picks up those new columns - see
  `docs/DATA_PIPELINE.md#market-statistics-implemented-2026-08-09` for why that's a
  separate migration, not automatic.
- `20260809030000_company_approval_status.sql` + `20260809031000_fix_approval_status_grant.sql`:
  `companies.approval_status` + the column-level grant fix - see this file's "Gotchas
  hit implementing sign-up approval" section below.
- `20260810000000_kstartup_support_programs.sql`: `support_programs`. Verified live via
  `worker/collectors/kstartup.py` against the real K-Startup API + this project (500
  real announcements collected, idempotent re-run confirmed) - see
  `docs/DATA_PIPELINE.md#support-programs-k-startup-implemented-2026-08-10`.

## Migration workflow

- All schema changes live in `supabase/migrations/*.sql`. Never hand-edit schema in the
  Supabase dashboard as the primary workflow.
- Before applying a migration: `npx supabase db push --dry-run` (remote) or
  `npx supabase db reset` (local). Never run a destructive migration against production
  data without a dry-run first.
- `npx supabase db lint --linked --fail-on error` when available.

## Core tables

Implemented (Phase 1):

- `technologies` - shared lookup for company tech stack (and later matching).
- `companies` - one row per customer company (name, size band, industry, region,
  business type, founded year). Phase 5 added the Match Engine profile fields:
  `budget_min`/`budget_max` (nullable = no preference, treated as "flexible" not
  "unknown" - see `docs/DATA_PIPELINE.md`), `experience_years` (default 0),
  `qualifications` (`text[]`, default `{}`). `approval_status`
  (`PENDING`/`APPROVED`/`REJECTED`, default `APPROVED`) gates a new company to
  `/dashboard` + `/settings` only until a BizRadar operator approves it
  (`apps/web/src/proxy.ts`) - see `docs/PRIVACY.md` and the gotcha below.
- `company_members` - links `auth.users` to `companies` (`user_id` is the primary key -
  a user belongs to at most one company for MVP scope, no invite flow).
- `company_technologies` - join table for a company's declared tech stack.
- `worker_heartbeats` - `worker_name`, `last_seen_at`, `version`, `status`.
- `opportunities` - RAW/NORMALIZED G2B bid announcements (`source` is always `'g2b'` -
  BizInfo/K-Startup go in `support_programs` instead, not here). `title`, `organization`,
  `demand_organization`, `budget_amount`, `estimated_price`, `region_restriction`,
  `posted_at`/`bid_close_at`/`open_at`, `source_url`, plus `raw_payload` (full API item)
  and `content_hash`. Unique on `(source, external_id)` - see
  `docs/DATA_PIPELINE.md#idempotency`. RLS: any authenticated user can `select`; only
  `service_role` writes. Also has `search_vector` (generated `tsvector`, GIN-indexed)
  plus `gin_trgm_ops` trigram indexes on `title`/`organization` for substring search -
  see the Phase 3 gotcha below for why both exist. `category`
  (`NON_IT`/`LIKELY_IT`/`UNKNOWN`) is set by `worker/ai/rule_filter.py` at collection
  time, not a separate job - see `docs/DATA_PIPELINE.md`. Also has `bid_ntce_no`/
  `bid_ntce_ord`/`ntce_kind_nm` (G2B notice-thread identity, extracted from
  `raw_payload`) - see `opportunities_current` below and
  `docs/DATA_PIPELINE.md#notice-thread-deduplication-implemented-2026-08-09`. Also has
  `industry_limited`/`participation_limited`/`procurement_category` (tri-state Y/N/not-
  stated bidding-qualification fields, feed `/market`) - see
  `docs/DATA_PIPELINE.md#market-statistics-implemented-2026-08-09`.
- `opportunities_current` - a `security_invoker` view over `opportunities`, not a table:
  the current (latest, non-cancelled) revision of each G2B notice thread. Every read path
  that browses/analyzes/matches opportunities uses this, not the raw table, which keeps
  every historical revision. RLS: inherits `opportunities`' policy via
  `security_invoker`, plus an explicit `grant select ... to authenticated` (views get no
  grants by default, same as tables - see the Phase 1 gotcha below).
- `project_analyses` - AI output keyed to an opportunity 1:1 (`unique(opportunity_id)`):
  `status` (`PENDING`/`SUCCESS`/`FAILED`), `project_type`, `technologies`/
  `required_roles`/`requirements`/`risks` (jsonb), `summary`, `model`, `model_version`,
  `prompt_version`, `analyzed_at`, `analyzed_content_hash` (the `opportunities
  .content_hash` this row was computed against - re-analysis only happens when either it
  or `prompt_version` changes), `error_message`. Phase 5 added
  `min_experience_years`/`required_qualifications` (AI-extracted, feed the Match Engine).
  RLS: any authenticated user can `select`; only `service_role` writes.
- `match_scores` - one row per (company, opportunity), `unique(company_id,
  opportunity_id)`: 7 category scores (`technology_score` 0-30, `business_type_score`
  0-20, `budget_score`/`experience_score` 0-15, `qualification_score` 0-10,
  `region_score`/`schedule_score` 0-5) plus a generated `total_score` column (Postgres
  sums the 7 for you - can't drift out of sync). RLS: `company_id = auth_company_id()`
  only (not public like `opportunities`/`project_analyses` - a match score is specific
  to one company's fit, not general-purpose data). See
  `docs/DATA_PIPELINE.md#match-engine`.
- `support_programs` - RAW/NORMALIZED K-Startup 사업공고 (`source` is always
  `'kstartup'` - BizInfo lands separately later under the same table, not a new one).
  `title`, `organization`, `department`, `supervising_type` (민간/공공기관/교육기관/
  지자체), `category` (조달분류 아님, K-Startup's own `supt_biz_clsfc`), `region`,
  `target`, `recruiting` (nullable Y/N), `application_start`/`application_end`,
  `description`, `source_url`, plus `raw_payload` and `content_hash`. Unique on
  `(source, external_id)`. `investment_linked` (TIPS/엔젤투자/etc, rule-filter
  classification, default `false`) - see
  `docs/DATA_PIPELINE.md#support-programs-k-startup-implemented-2026-08-10`. RLS: any
  authenticated user can `select`; only `service_role` writes - same pattern as
  `opportunities`.

Planned (later phases, see `docs/MVP_SCOPE.md`):

- BizInfo half of `support_programs` + eligibility status computation. (Phase 6, remainder)
- `saved_opportunities`, `watch_conditions` - per-company user state. (Phase 8)

## Gotchas hit while implementing Phase 1 (see `docs/TROUBLESHOOTING.md` for full detail)

- Raw SQL-created tables don't automatically get `anon`/`authenticated` grants the way
  dashboard-created tables do - RLS policies restrict an existing grant, they don't
  create one. Every migration must `grant select/insert/update/delete` explicitly for
  the operations its policies allow.
- `INSERT ... RETURNING` (i.e. `Prefer: return=representation`, or Supabase JS's
  `.insert().select()`) implicitly re-checks the table's SELECT policy on the new row.
  For a table whose SELECT policy depends on a row created by a *second* insert (like
  `companies` depending on `company_members`), the first insert must generate its own id
  client-side and skip `return=representation`.

## Gotchas hit while implementing Phase 2 (see `docs/TROUBLESHOOTING.md` for full detail)

- The G2B API's real path has an easy-to-miss `ad/` segment, and its service key is
  pre-URL-encoded - encoding it again breaks auth with a misleading error.
- A `curl ... | python -m json.tool` verification command showed mangled Korean text
  (`\udcec...` escaped surrogates) and looked like a real encoding bug in the collector.
  It wasn't - `python -m json.tool` reading piped stdin on Windows used the console's
  default codepage, not UTF-8. Querying the same data with `httpx` directly in Python
  and writing it to a UTF-8 file showed it was correct all along. Lesson: don't trust an
  ad-hoc shell-pipe verification's *encoding* on Windows - verify through the same
  HTTP/JSON stack the application actually uses.

## Gotchas hit while implementing Phase 3 (see `docs/TROUBLESHOOTING.md` for full detail)

- `to_tsvector('simple', ...)` (Postgres has no Korean dictionary) only matches whole
  tokens - searching "교육" against a title containing the compound token "교육여행"
  returns nothing, because there's no stemming to split it. Verified live before writing
  any app code. Added `pg_trgm` + GIN trigram indexes for real substring search via
  `ilike`, which is what the UI actually uses; kept the `tsvector`/GIN column too
  (exact-token search, e.g. by organization name, still has value and does no harm).
- Deleting a route (`app/dashboard/page.tsx` moved under a route group) left a stale
  reference in `.next/types/`, which made `tsc --noEmit` fail on a file that no longer
  existed. Deleting `.next/` and re-running `next build` (which regenerates route types)
  fixed it - this is generated output, never a real code problem.

## Gotchas hit while implementing Phase 4 (see `docs/TROUBLESHOOTING.md` for full detail)

- `supabase-py`'s `.execute().data` is typed as a generic JSON union
  (`bool | str | int | float | Sequence[JSON] | Mapping[str, JSON] | None`), not
  `list[dict[str, Any]]` - mypy correctly refuses `row["id"]` on it. Cast explicitly
  (`cast("list[dict[str, Any]]", ...)`) at the point where you know the actual shape from
  the `.select(...)` call, rather than loosening types elsewhere.
- A PostgREST embed across a `unique(opportunity_id)` foreign key
  (`project_analyses(...)` embedded from `opportunities`) is a true 1:1 relationship at
  the DB level, but the client library still types the embed as an array - normalize it
  (`Array.isArray(x) ? x[0] ?? null : x`) rather than assuming the runtime shape matches
  the "obviously 1:1" schema.

## Gotchas hit while implementing Phase 5 (see `docs/TROUBLESHOOTING.md` for full detail)

- A live-only bug (no unit test caught it, because unit tests construct
  `OpportunityRequirements` directly with real `datetime` objects): PostgREST returns
  `timestamptz` columns as plain JSON strings. `worker/repositories/match_scores.py`
  passed `opportunities.bid_close_at` straight into `OpportunityRequirements` (typed
  `datetime | None`) without parsing it, and the very first opportunity that had a
  non-null deadline crashed `worker/matching/engine.py`'s schedule scoring with
  `TypeError: unsupported operand type(s) for -: 'str' and 'datetime.datetime'`. Fixed
  with an explicit `datetime.fromisoformat()` parse in the repository layer, and added a
  unit test using the exact string PostgREST returned.
- A live analysis run (before Phase 5's schema even existed) showed a real LLM failure
  mode: `required_qualifications` came back with the same certification name repeated
  ~15 times, truncated mid-string, and the *next* item then timed out - almost certainly
  the same repetition loop costing enough tokens to blow the budget. Not a Phase 5
  finding exactly, but it's what motivated adding `maxItems` to every array in the
  extraction JSON schema and an order-preserving dedupe validator on `ProjectExtraction`
  - see `docs/DATA_PIPELINE.md`.
- `companies.business_type` is free text (from Phase 1's onboarding form), not an enum,
  while `project_analyses.project_type` is a controlled enum. Rather than migrate an
  already-shipped form/column, Business Type matching uses keyword fuzzy-matching
  (`worker/matching/engine.py:BUSINESS_TYPE_KEYWORDS`) - a deliberate, documented
  trade-off, not an oversight.

## Gotchas hit implementing sign-up approval (2026-08-09)

- **Column-level `REVOKE` does not override an existing table-wide `GRANT`.** The first
  attempt to lock down `companies.approval_status` was
  `revoke update (approval_status) on companies from authenticated;` - this looked
  correct and applied without error, but a live attack test (sign up a throwaway user,
  PATCH their own company's `approval_status` via the anon key + their session token)
  showed it did nothing: the self-approval succeeded (200, row actually changed).
  Confirmed via `supabase db query --linked` against
  `information_schema.column_privileges`: `authenticated` still had `UPDATE` on that
  column. Root cause - the table-wide `grant update on companies to authenticated`
  (Phase 1) already grants UPDATE on every column, present and future; a column-specific
  `REVOKE` only removes an *explicit column-level* grant entry, and there wasn't one to
  remove. Fix: `revoke update on companies from authenticated` (the whole table), then
  re-`grant update (col1, col2, ...)` on only the columns that should stay writable,
  explicitly excluding `approval_status`. Re-verified live after the fix: the same
  attack now gets a 403, and a normal settings save (name/budget/etc.) still succeeds.
  **Lesson: don't assume a `REVOKE` worked because it ran without error - verify against
  `information_schema` and/or a real attack attempt, especially alongside an existing
  table-wide `GRANT`.**
- Since `authenticated` has zero write access to `approval_status` by design, approving a
  company can only be done with `service_role` - the one deliberate, narrowly-scoped
  exception to "the web app never holds `SUPABASE_SERVICE_ROLE_KEY`" (see
  `docs/ARCHITECTURE.md` and `apps/web/src/lib/supabase/admin.ts`).

## RLS (must pass before Phase 1 is considered done)

- User A can read/write only their own company's rows (`companies`,
  `saved_opportunities`, `watch_conditions`, `company_members`).
- User A cannot read User B's company data, and cannot read User B's
  `saved_opportunities` even for a public `opportunities` row.
- `opportunities` and `support_programs` are readable by any authenticated user
  (public data), writable only by the `service_role` (the worker).
- RLS is never disabled to make a test pass - see `docs/TESTING.md`.

## Constraints

Every table above gets real DB constraints (`NOT NULL`, `UNIQUE`, `FOREIGN KEY`, `CHECK`)
in the migration itself - the application layer is not trusted as the only guard.
