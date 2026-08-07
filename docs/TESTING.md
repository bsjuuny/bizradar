# Testing

## Web (`apps/web`)

```bash
npm run lint        # ESLint
npm run typecheck   # tsc --noEmit, strict mode
npm run test         # vitest (watch)
npm run test:run    # vitest run (CI)
npm run build        # next build - must succeed
```

Playwright is reserved for a small smoke suite over the core user flow (signup -> company
setup -> dashboard) once that flow exists - not a large E2E suite.

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

## What's actually covered right now (Phase 0)

- `worker/tests/test_config.py` - `Settings` defaults (`data_mode=mock`, local Ollama
  URL/model, no Supabase creds required to import).
- `worker/tests/test_base_collector.py` - `BaseCollector` can't be instantiated directly;
  `run()` isolates a per-record failure from the rest of the batch.
- `worker/tests/test_ai_base.py` - `AIProvider` can't be instantiated directly.
- `apps/web/src/app/api/health/route.test.ts` - `/api/health` returns 200 + `{status:
  "ok"}`.

Nothing beyond this has a test yet - there is no collector, AI provider, match engine,
migration, or UI page to test until their respective phases land.
