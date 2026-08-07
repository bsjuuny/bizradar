# BizRadar

B2B SaaS MVP that helps IT/SI companies (5-50 employees) discover public-sector IT
projects and government support programs, and track the public IT market.

Status: **Phase 0 (repository + architecture + testing foundation) in progress.** See
`docs/MVP_SCOPE.md` for the phase plan and `docs/VERIFICATION_REPORT.md` for what has
actually been implemented and verified so far.

## Structure

```
apps/web/     Next.js (Railway) - reads Supabase, never calls Ollama
worker/       Python (local PC, PM2) - collectors, AI analysis, matching, scheduler
supabase/     migrations, RLS tests, seed data
fixtures/     mock API responses for DATA_MODE=mock (g2b, bizinfo, kstartup)
docs/         architecture, database, data pipeline, infra, testing, troubleshooting
```

See `docs/ARCHITECTURE.md` for why web and worker are two independent runtimes that only
share the Supabase database.

## Quick start

**Web**

```bash
cd apps/web
npm install
cp ../../.env.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_* once a project exists
npm run dev
```

**Worker - Windows**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.worker.example .env.worker
pm2 start ecosystem.config.cjs
```

**Worker - macOS / Linux**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
cp .env.worker.example .env.worker
pm2 start ecosystem.config.cjs
```

## Verifying changes

```bash
# apps/web
npm run lint && npm run typecheck && npm run test:run && npm run build

# worker (venv active, run from repo root)
ruff check worker && ruff format --check worker && pytest && mypy worker
```

See `docs/TESTING.md` for what's covered and the testing policy (no skipping tests to
turn them green, no disabling RLS to make a test pass).
