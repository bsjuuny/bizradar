# Architecture

## Two independent runtimes

```
Browser -> Railway (Next.js) -> Supabase (Postgres + Auth, RLS)
Local PC -> PM2 -> Python worker -> Public APIs (G2B / BizInfo / K-Startup) -> Ollama -> Supabase
```

The web app and the worker never call each other directly. They only share the Supabase
database. The worker writes analysis results; the web app reads them.

**Why:** Ollama runs locally (`qwen3:8b`, no GPU hosting cost). Railway must never call
Ollama, and a local Ollama outage must never become a Railway incident. See
`/api/health` in `docs/INFRASTRUCTURE.md` - it does not check Ollama for this reason.

## Auth / key boundary

- `NEXT_PUBLIC_SUPABASE_URL` / `NEXT_PUBLIC_SUPABASE_ANON_KEY` - browser-safe, RLS-enforced.
- `SUPABASE_SERVICE_ROLE_KEY` - worker only, loaded from `.env.worker`, never bundled into
  the Next.js build and never committed. Railway does not hold this key unless a specific
  feature later requires it.

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

Phase 0 only: this document describes the target architecture. Only the interfaces
(`BaseCollector`, `AIProvider`) and the PM2/web scaffolding exist so far - no concrete
collector, AI provider, or match engine implementation has landed yet.
