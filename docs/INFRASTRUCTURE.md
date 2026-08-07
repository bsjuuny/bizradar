# Infrastructure

## Web (Railway)

- Next.js 16 (App Router, TypeScript strict, Tailwind v4, shadcn/ui), deployed to
  Railway. Config is environment-variable driven - no hardcoded `localhost`.
- `GET /api/health` -> `200 { "status": "ok" }`. This is the Railway healthcheck target.
  It does not check Ollama or the worker - see `docs/ARCHITECTURE.md` for why a local
  Ollama outage must never fail a Railway deploy/healthcheck.
- Listens on `$PORT` (Railway convention), not a hardcoded port.

## Worker (local PC, PM2)

- Single PM2 process, `bizradar-worker` (`ecosystem.config.cjs`), running
  `worker/scheduler/main.py` under APScheduler (`Asia/Seoul`, `max_instances=1`,
  `coalesce=True`, `misfire_grace_time=60`).
- Python interpreter resolution: `BIZRADAR_PYTHON` env var if set, else
  `.venv/Scripts/python.exe` (Windows) / `.venv/bin/python` (macOS/Linux) if present,
  else `python`/`python3` on PATH. Never hardcoded.
- `worker_heartbeats` (Phase 1+ table) records `last_seen_at` so the web dashboard can
  show "data last updated at ...".

## Local setup

```bash
# Web
cd apps/web && npm install
cp ../../.env.example .env.local   # fill in Supabase URL/anon key
npm run dev

# Worker (Windows)
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
copy .env.worker.example .env.worker   # fill in service role key, Ollama, etc.
pm2 start ecosystem.config.cjs

# Worker (macOS/Linux)
python3 -m venv .venv
./.venv/bin/python -m pip install -e ".[dev]"
cp .env.worker.example .env.worker
pm2 start ecosystem.config.cjs
```

## Secrets

`.env`, `.env.local`, `.env.worker`, and anything under `supabase/.temp` are gitignored.
`SUPABASE_SERVICE_ROLE_KEY` only ever lives in `.env.worker` (local) - never in Railway
env vars unless a specific future feature requires it, and never in the browser bundle.
