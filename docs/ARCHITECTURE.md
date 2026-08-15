# Architecture

## Two independent runtimes

```
Browser -> Railway (Next.js) -> Supabase (Postgres + Auth, RLS)
Local PC -> PM2 -> Python worker -> Public APIs (G2B / BizInfo / K-Startup) -> Ollama -> Supabase
```

The web app and the worker never call each other directly. They only share the Supabase
database. The worker writes analysis results; the web app reads them.

**Why:** Ollama runs locally (`qwen3.5:9b`, no GPU hosting cost). Railway must never call
Ollama, and a local Ollama outage must never become a Railway incident. See
`/api/health` in `docs/INFRASTRUCTURE.md` - it does not check Ollama for this reason.

## Auth / key boundary

- `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` - browser-safe, RLS-enforced.
- `SUPABASE_SERVICE_ROLE_KEY` - worker only, loaded from `.env.worker`, never bundled into
  the Next.js build and never committed. Railway does not hold this key unless a specific
  feature later requires it - as of 2026-08-09, one does: `apps/web/src/lib/supabase/
  admin.ts` uses it, server-side only, exclusively for company-approval actions gated by
  `requireAdmin()`. `authenticated` has no UPDATE privilege on `companies
  .approval_status` at all (see `docs/DATABASE.md`'s Phase 6 gotchas) precisely so no
  client-reachable code path can approve a company - service_role is the only way to
  flip it, which is why this one narrow exception exists. Never referenced from a
  `"use client"` file.

## Data flow (per source: G2B, BizInfo, K-Startup)

```
RAW -> NORMALIZED -> ANALYZED -> MATCHED
```

Each stage is a separate representation; the AI stage never overwrites the raw API
response. See `docs/DATA_PIPELINE.md` for the collector interface and idempotency rules.

## AI provider abstraction

`worker/ai/base.py` defines `AIProvider` (`classify_project`, `extract_project`,
`summarize_project`, `extract_support_conditions`). `OllamaProvider` is the only
implementation planned for the MVP (Phase 4); the interface exists so
Groq/OpenRouter/OpenAI/Claude providers can be added later without touching callers.

## Match scoring

Match Engine is a deterministic rule engine (`worker/matching/`), not an LLM call - see
`docs/DATA_PIPELINE.md#match-engine` for the point breakdown. This keeps scores
explainable and reproducible, and keeps Ollama off the hot path for every dashboard read.

## Status

Phase 0-5 done: auth + company profile, the G2B collector, Project Radar UI, AI analysis,
and the Match Engine (`worker/matching/engine.py`, no LLM - rule-based) are implemented
and verified against the real linked project, the real G2B API, a real local Ollama
instance, and a real browser (Playwright). BizInfo/K-Startup collectors and everything
past them are per `docs/MVP_SCOPE.md`'s phase plan.

`OllamaProvider` is the first concrete `AIProvider` - it's the architecture's proof point
that Railway never touches Ollama: the worker calls `http://127.0.0.1:11434` directly
from the local PC, analyzes, and writes results to Supabase; the web app only ever reads
`project_analyses`/`match_scores`, never calls the model itself. The Match Engine keeps
that boundary too, in the other direction: it's deliberately rule-based so a company's
match percentage is deterministic and explainable, not another LLM call in the hot path
of every dashboard read.
