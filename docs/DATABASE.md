# Database

## Status: Phase 1 (company profile) + Phase 2 (opportunities) tables implemented and
verified against the live project; the rest are NOT_IMPLEMENTED until their phase.

- `20260807120000_phase1_company_profile.sql` + `20260807130000_phase1_grants.sql`:
  `technologies`, `companies`, `company_members`, `company_technologies`,
  `worker_heartbeats`, `auth_company_id()`. Verified with
  `supabase/tests/test_rls_phase1.py`.
- `20260807140000_phase2_opportunities.sql`: `opportunities`. Verified live via
  `worker/collectors/g2b.py` against the real G2B API + this project.

See `docs/VERIFICATION_REPORT.md` for what was actually run.

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
  business type, founded year).
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
  `service_role` writes.

Planned (later phases, see `docs/MVP_SCOPE.md`):

- `project_analyses` - AI output keyed to an opportunity (`model`, `model_version`,
  `prompt_version`, `analyzed_at`, `analysis_status`). (Phase 4)
- `match_scores` - per-company, per-opportunity score breakdown (see
  `docs/DATA_PIPELINE.md#match-engine`). (Phase 5)
- `support_programs` - BizInfo/K-Startup normalized programs + eligibility status. (Phase 6)
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
