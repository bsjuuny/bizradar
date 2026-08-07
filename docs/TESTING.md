# Testing

## Web (`apps/web`)

```bash
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit, strict mode
npm run test         # vitest (watch)
npm run test:run    # vitest run (CI)
npm run build        # next build - must succeed
npm run test:e2e    # Playwright - core user flow, against the real linked Supabase project
```

Playwright (`apps/web/e2e/`) is reserved for the core user flow smoke test (login ->
onboarding -> dashboard -> logout, plus the signup call) - not a large E2E suite. It runs
against the real linked Supabase project (no local/mocked backend), creates its own
throw-away auth users via the Admin API, and cleans them up in `afterAll` even on
failure. Requires `.env.worker` and `apps/web/.env.local` to be filled in.

## Worker (repo root, venv active)

```bash
ruff check worker
ruff format --check worker
pytest
mypy worker
```

## Rules

- A failing test is never made to pass by skipping it, weakening its assertions, or
  mocking around the behavior under test. If a test is wrong, say why in the commit/PR,
  don't silently loosen it.
- RLS is tested with real Supabase policies active, never with RLS disabled for the test
  run (see `docs/DATABASE.md#rls`).
- A bug fix always gets a regression test that reproduces the bug first, then the fix,
  then the same test passing, then the surrounding module's tests, then the full suite.

## What's actually covered right now (Phase 0 + Phase 1 + Phase 2)

- `worker/tests/test_config.py` - `Settings` defaults (`data_mode=mock`, local Ollama
  URL/model, no Supabase creds required to import).
- `worker/tests/test_base_collector.py` - `BaseCollector` can't be instantiated directly;
  `run()` isolates a per-record failure from the rest of the batch.
- `worker/tests/test_ai_base.py` - `AIProvider` can't be instantiated directly.
- `apps/web/src/app/api/health/route.test.ts` - `/api/health` returns 200 + `{status:
  "ok"}`.
- `supabase/tests/test_rls_phase1.py` - RLS against the real project: A reads own
  company/not B's, B not A's, membership row isolation, public-read/service-role-write
  on `worker_heartbeats`, anon/authenticated writes to `worker_heartbeats` rejected.
- `apps/web/e2e/core-flow.spec.ts` - unauthenticated `/dashboard` redirects to `/login`;
  login -> onboarding (company creation) -> dashboard (shows the created company) ->
  logout -> session actually gone; signup calls `auth.signUp()` and correctly handles
  both outcomes (check-email state, or the shared dev mailer's rate limit surfaced as an
  error instead of crashing - see `docs/TROUBLESHOOTING.md`).

- `worker/tests/test_g2b_collector.py` - response parsing (success/empty/service-error/
  non-JSON), field normalization against a real recorded response, pagination, dedup
  across pages, `max_records` capping, missing-API-key handling, per-record persist
  failure isolation. All offline (`httpx.MockTransport` / recorded fixtures).
- `worker/tests/test_g2b_job.py`, `worker/tests/test_logging_config.py` - job
  success/failure/partial-failure logging, and the JSON log formatter.
- Live (not part of `pytest` - see `docs/VERIFICATION_REPORT.md`): ran
  `G2BCollector` against the real API + real Supabase project, twice, to confirm
  idempotent upsert (same row count, only `updated_at` moves) with correct Korean text.

Nothing beyond this has a test yet - there is no AI provider, match engine, support
program, saved/watch feature, or further UI page to test until their respective phases
land.
