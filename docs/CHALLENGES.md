# CHALLENGE

CHALLENGE adds authenticated discovery pages for contests, hackathons, AI/data/development
competitions, startup competitions, awards, and public-data competitions. It is additive:
the existing opportunity tables and PUBLIC/ENTERPRISE/SUPPORT/MARKET flows are unchanged.

## Supported source and collection

The initial production source is the official, publicly accessible, server-rendered
`data.go.kr` notice board (`data-go-kr-notices`, `OFFICIAL_HTML`, priority 10). The adapter
searches challenge-related terms, follows official detail pages, preserves the source URL
and attachment links, and does not bypass login, CAPTCHA, or access controls.

The source registry is in `worker/challenges/sources.py`. A source failure is isolated;
bounded retries handle timeouts, 429 (`Retry-After`), and transient 5xx responses. 403/404
are not repeatedly retried. Three consecutive failures open an in-process circuit for 15
minutes. Status is exposed by authenticated `GET /api/challenges/sources`.

With the repository virtual environment active, run one collection manually:

```powershell
$env:DATA_MODE='live'
python -c "from worker.jobs.challenge_job import run; print(run(max_records=5).model_dump_json(indent=2))"
```

For deterministic local verification, keep `DATA_MODE=mock`; the checked-in HTML fixtures
exercise the same parser and normalizer. The scheduler uses `CHALLENGE_COLLECTION_CRON`
(default every six hours). PM2 still starts the single existing worker scheduler.

## Domain and API

Supported types are `CONTEST`, `HACKATHON`, `AI_COMPETITION`, `DATA_COMPETITION`,
`DEV_COMPETITION`, `IDEA_COMPETITION`, `STARTUP_COMPETITION`, `AWARD`,
`PUBLIC_DATA_COMPETITION`, and `OTHER`.

Authenticated endpoints:

- `GET /api/challenges` — paginated summary DTO with search and filters
- `GET /api/challenges/:id` — full detail DTO
- `GET /api/challenges/categories` — type/status/policy filter values
- `GET /api/challenges/sources` — collection health

The list query deliberately excludes descriptions, original text, attachments, and raw
payload. Search covers the normalized title, organizer, description, category, and
technology text. Filters cover type, status, overall AI policy, AI Coding policy,
participation, individual/team, prize, organizer, and technology.

## AI policy safety

Policy values are `REQUIRED`, `ALLOWED`, `LIMITED`, `PROHIBITED`, and `UNKNOWN`.
An affirmative value is accepted only with source evidence. Missing or ambiguous language
is always `UNKNOWN`; absence of a prohibition is never treated as permission.

Collection first saves a deterministic, conservative rule result. Optional local Ollama
analysis uses a JSON schema, extracts JSON from markdown/explanatory text, validates enums,
and performs one repair attempt. If Ollama times out or returns invalid output, the record
remains available and a rule fallback is stored with `analysis_status=FAILED`. Records with
no AI-related terms skip the LLM. Unchanged `content_hash` values retain prior analysis;
failed records are not retried indefinitely and content changes requeue analysis.

Set `CHALLENGE_AI_ANALYSIS_ENABLED=true` only when local Ollama is available. The default is
`false`, so collection does not depend on the LLM.

## Environment

Web:

```text
FEATURE_CHALLENGE=true
```

Worker:

```text
FEATURE_CHALLENGE=true
CHALLENGE_COLLECTION_ENABLED=true
CHALLENGE_COLLECTION_CRON=0 */6 * * *
CHALLENGE_REQUEST_TIMEOUT=15
CHALLENGE_MAX_RETRIES=3
CHALLENGE_AI_ANALYSIS_ENABLED=false
```

Apply the additive database migration after linking the intended Supabase project:

```powershell
npx supabase db push --dry-run
npx supabase db push
```

No reset, truncate, or destructive migration is required.

## Verification

```powershell
# repository root
.\.venv\Scripts\ruff.exe check worker
.\.venv\Scripts\ruff.exe format --check worker
.\.venv\Scripts\pytest.exe -q
.\.venv\Scripts\mypy.exe worker

# apps/web
npm.cmd run lint
npm.cmd run typecheck
npm.cmd run test:run
npm.cmd run build
```

Fixtures and tests cover date/prize/type/eligibility/status parsing, URL normalization,
deduplication, source-to-persistence flow, 429, bounded 503 and timeout retries, invalid
HTML, source isolation, invalid LLM JSON, LLM timeout fallback, and UNKNOWN safety.

## Known limitations

- The initial source is intentionally limited to one stable official notice board.
- Attachment links (including HWP) are retained and displayed, but binary contents are not
  downloaded or parsed. This avoids an SSRF/download surface; policies found only inside an
  attachment remain `UNKNOWN` until a separately hardened extractor is introduced.
- The circuit breaker is process-local and resets when the worker restarts.
- HTML-source layout changes can reduce collected records; malformed records are skipped and
  surfaced through structured logs/source status without stopping the scheduler.
