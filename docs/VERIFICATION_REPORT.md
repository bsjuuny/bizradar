# Verification Report

**검증일**: 2026-08-07
**Node**: v24.14.0 (npm 11.9.0)
**Python**: 3.13.13 (venv at repo root, `.venv/`)
**pm2**: 6.0.14
**git**: 2.53.0.windows.1
**Ollama**: not installed / not on PATH (checked both bash `which` and PowerShell
`Get-Command` - neither found it). Blocks Phase 4 only; everything else in Phase 0
is independent of it.
**npx supabase**: available via `npx --yes supabase@latest` (2.111.0), no project linked
yet.

## Commands actually executed

### Web (`apps/web`)

| Command | Result |
|---|---|
| `npm run lint` | PASS - no output, 0 errors |
| `npm run typecheck` | PASS - `tsc --noEmit`, 0 errors |
| `npm run test:run` | PASS - 1 test file, 1 test (`GET /api/health` -> 200 `{status:"ok"}`) |
| `npm run build` | PASS - Turbopack production build, 3 routes (`/`, `/_not-found`, `/api/health`) |

### Worker (repo root, `.venv` active)

| Command | Result |
|---|---|
| `ruff check worker` | PASS - all checks passed |
| `ruff format --check worker` | PASS - 19 files already formatted |
| `pytest` | PASS - 5 passed (`test_config.py` x2, `test_base_collector.py` x2, `test_ai_base.py` x1) |
| `mypy worker` | PASS - no issues in 19 source files |

### PM2 boot check

`pm2 start ecosystem.config.cjs` -> `bizradar-worker` came up `online`, resolved the
`.venv` Python interpreter, logged `"bizradar-worker starting (no jobs registered yet)"`
and `"Scheduler started"` as structured JSON, and stayed at `0` restarts over the check
window. Stopped and deleted the process afterward (`pm2 stop` + `pm2 delete`) since it
has no jobs yet and shouldn't be left running unattended; sibling PM2 processes
(`scheduler`, `cron-trending-rankings`, `culture-hub-cardnews-review`) were left
untouched.

### Migration validation

Not applicable yet - no migrations exist (`supabase/migrations/` is empty). Nothing to
`db push --dry-run` or `db lint` against.

### Mock pipeline

NOT_IMPLEMENTED. No collector exists yet to run in `DATA_MODE=mock` - fixtures
directories (`fixtures/g2b`, `fixtures/bizinfo`, `fixtures/kstartup`) are placeholders.

### Live pipeline

NOT TESTED (no collector, no API keys configured).

### Ollama test

NOT TESTED - Ollama is not installed on this machine (see Troubleshooting doc).

## Errors encountered and fixed this session

1. `create-next-app` reported "path is not writable" when run from the bash/MSYS shell
   despite correct ACLs on the target directory - re-ran the same command from
   PowerShell, which succeeded. Root cause: shell/path-translation issue, not a real
   permissions problem.
2. `npm install` for Vitest/Testing Library failed on a peer-dependency conflict between
   `shadcn` CLI's pinned `@babel/*` versions and `@vitejs/plugin-react`'s newer peer
   range. Installed with `--legacy-peer-deps` (dev-tooling-only conflict, not a runtime
   dependency issue).
3. First test run failed: `Cannot find package '@testing-library/dom'` (undeclared peer
   dependency of `@testing-library/react`). Installed it explicitly.
4. Vitest warned about CJS/ESM config loading and `__dirname` under the native config
   loader. Renamed `vitest.config.ts` -> `vitest.config.mts` and switched to
   `import.meta.dirname`.
5. `ruff check worker` failed on a >100-char line (`worker/collectors/base.py`) and a
   `datetime.now(timezone.utc)` vs `datetime.now(UTC)` suggestion in a test file. Fixed
   both, re-ran, clean.
6. `mypy worker` failed with a Liskov substitution violation: the test's `DummyCollector`
   narrowed `normalize`/`validate`/`persist` parameter types from `BaseModel` to a
   concrete subtype, which is unsound against the declared base signature. Fixed by
   making `BaseCollector` generic (`BaseCollector[TNormalized: BaseModel]`, PEP 695
   syntax) instead of loosening the subclass - re-ran, clean. `ruff` initially flagged
   the first attempt (`Generic[TNormalized]` with a separate `TypeVar`) for using the
   old-style generic syntax; switched to the PEP 695 `class BaseCollector[T: Bound](ABC)`
   form ruff expects at `target-version = "py312"`.

No test was skipped, weakened, or mocked-around to reach green; every fix above changed
the actual source (or a genuinely wrong test), not the checks themselves.

## Known issues

- `shadcn` CLI ended up as a `devDependency` of `apps/web` (from `shadcn init`) - kept
  intentionally so `npx shadcn add <component>` keeps working, but its Babel pins are the
  reason the Vitest install needed `--legacy-peer-deps` (see Troubleshooting #2).
- `c:/github/bizradar/apps/web` and `c:/github/bizradar` (root) each briefly had their own
  empty, broken `.git` directories from `create-next-app`'s `git init` (despite `--no-git`
  being passed) and from a pre-existing broken `.git` at `c:/github` respectively. Removed
  the stray nested one in `apps/web`; `bizradar` itself is now the single real repo root.

## Not implemented (by design, Phase 0 scope only)

Everything past repository scaffolding and testing foundation: Supabase project/migrations,
auth, company profile, all three collectors, AI provider implementation, match engine,
support eligibility, market aggregation, saved/watch features, RLS policies, Playwright
smoke test, Railway deployment. See `docs/MVP_SCOPE.md` for the phase breakdown.

## Completion status table

| Component | Status |
|---|---|
| Web Build | PASS |
| Authentication | NOT TESTED (not implemented - Phase 1) |
| Company Profile | NOT TESTED (not implemented - Phase 1) |
| G2B Collector | NOT TESTED (not implemented - Phase 2) |
| Project Normalization | NOT TESTED (not implemented - Phase 2) |
| AI Analysis | NOT TESTED (not implemented - Phase 4; Ollama also not installed locally) |
| Match Engine | NOT TESTED (not implemented - Phase 5) |
| Support Collector | NOT TESTED (not implemented - Phase 6) |
| Support Matching | NOT TESTED (not implemented - Phase 6) |
| Market Aggregation | NOT TESTED (not implemented - Phase 7) |
| Saved | NOT TESTED (not implemented - Phase 8) |
| Watch | NOT TESTED (not implemented - Phase 8) |
| RLS | NOT TESTED (no Supabase project/migrations yet - Phase 1) |
| Tests (Phase 0 scope) | PASS (web: 1/1, worker: 5/5) |
| Railway Ready | PARTIAL (`/api/health` exists and builds; env-var-driven; never deployed to Railway) |
| PM2 Worker Ready | PASS (`pm2 start ecosystem.config.cjs` -> `bizradar-worker` online, resolved `.venv` interpreter, APScheduler started, structured JSON log emitted, 0 restarts over the check window; stopped and deleted afterward since no jobs are registered yet) |
