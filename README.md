# BizRadar

B2B SaaS MVP that helps IT/SI companies (5-50 employees) discover public-sector IT
projects and government support programs, and track the public IT market.

Status: **Phase 0 (repo/testing foundation), Phase 1 (Supabase auth + company profile),
and Phase 2 (G2B collector) done.** See `docs/MVP_SCOPE.md` for the phase plan and
`docs/VERIFICATION_REPORT.md` for what has actually been implemented and verified so far.

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
cp ../../.env.example .env.local   # fill in NEXT_PUBLIC_SUPABASE_URL / _ANON_KEY
npm run dev
```

Visit `/signup` or `/login`. New users are sent through `/onboarding` (company profile
creation) before reaching `/dashboard`. Auth/RLS setup is documented in
`docs/DATABASE.md` and `docs/ARCHITECTURE.md`.

**Worker - Windows**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.worker.example .env.worker   # fill in SUPABASE_SERVICE_ROLE_KEY, G2B_API_KEY
pm2 start ecosystem.config.cjs
```

**Worker - macOS / Linux**

```bash
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
cp .env.worker.example .env.worker
pm2 start ecosystem.config.cjs
```

This starts `g2b-collect` (hourly) - see `docs/DATA_PIPELINE.md` for the G2B API's two
non-obvious gotchas (path, key encoding) before touching `worker/collectors/g2b.py`.

## Verifying changes

```bash
# apps/web
npm run lint && npm run typecheck && npm run test:run && npm run build
npm run test:e2e    # needs .env.worker + apps/web/.env.local filled in (real Supabase project)

# worker (venv active, run from repo root)
ruff check worker && ruff format --check worker && pytest && mypy worker

# supabase (needs `npx supabase link`, see docs/DATABASE.md)
npx supabase db push --dry-run
python supabase/tests/test_rls_phase1.py
```

See `docs/TESTING.md` for what's covered and the testing policy (no skipping tests to
turn them green, no disabling RLS to make a test pass).
