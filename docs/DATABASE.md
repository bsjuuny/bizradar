# Database

## Status: NOT_IMPLEMENTED (Phase 1)

No Supabase migration has been written yet. This document records the schema and RLS
design so Phase 1 implements it consistently, rather than inventing it ad hoc.

## Migration workflow

- All schema changes live in `supabase/migrations/*.sql`. Never hand-edit schema in the
  Supabase dashboard as the primary workflow.
- Before applying a migration: `npx supabase db push --dry-run` (remote) or
  `npx supabase db reset` (local). Never run a destructive migration against production
  data without a dry-run first.
- `npx supabase db lint --linked --fail-on error` when available.

## Planned core tables (Phase 1+)

- `companies` - one row per customer company (name, size band, industry, region, tech
  stack relations).
- `company_members` - links `auth.users` to `companies` (a user belongs to exactly one
  company for MVP scope).
- `opportunities` - RAW/NORMALIZED public-data records (`source`, `external_id`,
  `content_hash`, raw payload, normalized fields). Unique on `(source, external_id)` -
  see `docs/DATA_PIPELINE.md#idempotency`.
- `project_analyses` - AI output keyed to an opportunity (`model`, `model_version`,
  `prompt_version`, `analyzed_at`, `analysis_status`).
- `match_scores` - per-company, per-opportunity score breakdown (see
  `docs/DATA_PIPELINE.md#match-engine`).
- `support_programs` - BizInfo/K-Startup normalized programs + eligibility status.
- `saved_opportunities`, `watch_conditions` - per-company user state.
- `worker_heartbeats` - `worker_name`, `last_seen_at`, `version`, `status`.

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
